"""EncoderEngine - QThread-based state machine for folder watching and encoding.

Ports the full logic from Encoder.ahk (DriveEngine / BeginProcessFile /
ProcessUnlockedFile / OnEncodingComplete) into a Python worker thread that
emits Qt signals for the GUI.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, QTimer

from config import ConfigManager
from ffprobe import FFProbeRunner, FFProbeError
from handbrake import (
    HandBrakeRunner,
    build_args,
    get_output_format,
)


def _fmt_size(size_bytes: int) -> str:
    return f"{size_bytes / 1048576:.2f} MB"


def _is_video_file(path: Path, extensions: set[str]) -> bool:
    return path.suffix.lower() in extensions


def _check_file_lock(path: Path) -> bool:
    """Return True if the file can be opened for reading (not locked)."""
    try:
        with open(path, "rb") as f:
            f.read(1)
        return True
    except (OSError, PermissionError):
        return False


class EncoderEngine(QObject):
    """Core encoder state machine.

    Runs entirely on a worker thread.  All communication with the GUI happens
    via Qt signals.
    """

    log_message = Signal(str)
    stats_updated = Signal(dict)
    progress_updated = Signal(str)
    state_changed = Signal(str)
    error_occurred = Signal(str)

    # Emitted when the engine stops (user stop or fatal error)
    finished = Signal()

    def __init__(self, config: ConfigManager, parent: QObject | None = None):
        super().__init__(parent)
        self._config = config
        self._state = "idle"
        self._file_queue: list[str] = []
        self._done_files: set[str] = set()
        self._hb_runner: HandBrakeRunner | None = None
        self._probe: FFProbeRunner | None = None

        self._stats_total = 0
        self._stats_encoded = 0
        self._stats_copied = 0
        self._stats_skipped = 0

        self._cur_file = ""
        self._cur_output_dir = ""
        self._cur_file_name = ""
        self._cur_file_base = ""
        self._cur_orig_size = 0
        self._temp_encoded = ""

        self._lock_retries = 0
        self._stop_requested = False

        self._timer: QTimer | None = None

        self._thread: QThread | None = None

    @property
    def state(self) -> str:
        return self._state

    def _set_state(self, new_state: str):
        self._state = new_state
        self.state_changed.emit(new_state)

    def _log(self, msg: str):
        self.log_message.emit(msg)

    def _emit_stats(self):
        self.stats_updated.emit({
            "total": self._stats_total,
            "encoded": self._stats_encoded,
            "copied": self._stats_copied,
            "skipped": self._stats_skipped,
            "queued": len(self._file_queue),
        })

    def _video_extensions(self) -> set[str]:
        exts = self._config.get("video_extensions", [])
        return {e.lower() for e in exts}

    # ------------------------------------------------------------------
    #  Public API (called from GUI thread)
    # ------------------------------------------------------------------

    def start(self):
        """Start the engine on a background thread."""
        if self._state != "idle":
            return

        cfg = self._config
        source = cfg.get("source_base", "")
        hb_path = cfg.get("handbrake_cli", "")
        ff_path = cfg.get("ffprobe", "")

        if not source or not Path(source).is_dir():
            self.error_occurred.emit(f"Source folder not found:\n{source}")
            return
        if not hb_path or not Path(hb_path).exists():
            self.error_occurred.emit(f"HandBrakeCLI not found:\n{hb_path}")
            return
        if not ff_path or not Path(ff_path).exists():
            self.error_occurred.emit(f"ffprobe not found:\n{ff_path}")
            return

        self._stop_requested = False
        self._file_queue.clear()
        self._done_files.clear()
        self._stats_total = 0
        self._stats_encoded = 0
        self._stats_copied = 0
        self._stats_skipped = 0

        self._probe = FFProbeRunner(ff_path)
        self._hb_runner = HandBrakeRunner(hb_path)
        self._hb_runner.progress_updated.connect(self.progress_updated)

        self._thread = QThread()
        self.moveToThread(self._thread)
        self._thread.started.connect(self._run)
        self._thread.start()

    def stop(self):
        """Request the engine to stop gracefully."""
        self._stop_requested = True
        if self._hb_runner:
            self._hb_runner.cancel()

    def wait(self, timeout_ms: int = 10000):
        """Block until the worker thread finishes."""
        if self._thread and self._thread.isRunning():
            self._thread.wait(timeout_ms)

    # ------------------------------------------------------------------
    #  Worker thread entry
    # ------------------------------------------------------------------

    def _run(self):
        """Main loop running on the worker thread."""
        cfg = self._config

        self._log("=" * 50)
        self._log("Encoder started")
        self._log(f"HandBrakeCLI : {cfg.get('handbrake_cli')}")
        self._log(f"ffprobe      : {cfg.get('ffprobe')}")
        self._log(f"Source       : {cfg.get('source_base')}")
        self._log(f"Output       : {cfg.get('output_base')}")

        mode = cfg.get("encoding_mode", "abr")
        encoder = cfg.get_active_encoder()
        w, h = cfg.get_active_resolution()
        target = cfg.get_target_kbps()
        self._log(f"Mode         : {mode.upper()}  |  Encoder: {encoder}"
                  + (f"  |  {w}x{h}" if w and h else "")
                  + (f"  |  Target: {target} kbps" if target else ""))
        self._log(f"Delete source: {'Yes' if cfg.get('delete_source') else 'No'}")
        self._log("=" * 50)

        self._scan_existing_files()

        self._set_state("processing")

        while not self._stop_requested:
            if self._state == "processing":
                if not self._file_queue:
                    self._set_state("watching")
                    self._log("Queue empty. Watching for new files...")
                    continue
                next_file = self._file_queue.pop(0)
                self._emit_stats()
                self._process_file(next_file)

            elif self._state == "watching":
                self._scan_for_new_files()
                if self._file_queue:
                    self._set_state("processing")
                    continue
                time.sleep(2)

            else:
                time.sleep(1)

        self._set_state("idle")
        self._log("Encoder stopped.")
        self.finished.emit()

        if self._thread:
            self._thread.quit()

    # ------------------------------------------------------------------
    #  Scanning
    # ------------------------------------------------------------------

    def _scan_existing_files(self):
        self._log("Scanning source folder for existing files...")
        source = Path(self._config.get("source_base", ""))
        exts = self._video_extensions()

        for root, dirs, files in os.walk(source):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            if self._stop_requested:
                return
            for fname in sorted(files):
                fp = Path(root) / fname
                if _is_video_file(fp, exts):
                    self._file_queue.append(str(fp))
                    self._done_files.add(str(fp))

        count = len(self._file_queue)
        if count:
            self._log(f"Found {count} existing file(s) to process.")
        else:
            self._log("No existing files found. Switching to watch mode.")
        self._emit_stats()

    def _scan_for_new_files(self):
        source = Path(self._config.get("source_base", ""))
        exts = self._video_extensions()
        found = 0

        for root, dirs, files in os.walk(source):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            if self._stop_requested:
                return
            for fname in files:
                fp = str(Path(root) / fname)
                if fp not in self._done_files and _is_video_file(Path(fp), exts):
                    self._done_files.add(fp)
                    self._file_queue.append(fp)
                    self._log(f"New file detected: {fp}")
                    found += 1

        if found:
            self._emit_stats()

    # ------------------------------------------------------------------
    #  Process one file
    # ------------------------------------------------------------------

    def _process_file(self, file_path: str):
        path = Path(file_path)

        if not path.exists():
            self._log(f"File no longer exists, skipping: {file_path}")
            return

        self._stats_total += 1
        self._emit_stats()

        self._log("-" * 54)
        self._log(f"Processing : {file_path}")

        if not _check_file_lock(path):
            self._wait_for_lock(file_path)
            if self._stop_requested:
                return
            if not _check_file_lock(path):
                self._log("ERROR: File still locked after all retries. Skipping.")
                self._stats_skipped += 1
                self._emit_stats()
                return

        self._process_unlocked_file(file_path)

    def _wait_for_lock(self, file_path: str):
        retries = 11
        while retries > 0 and not self._stop_requested:
            self._log(f"File locked, retrying in 5s... ({retries} retries left)")
            time.sleep(5)
            if _check_file_lock(Path(file_path)):
                return
            retries -= 1

    def _process_unlocked_file(self, file_path: str):
        cfg = self._config
        source_base = cfg.get("source_base", "").rstrip(os.sep)
        output_base = cfg.get("output_base", "").rstrip(os.sep)
        replace_in_place = cfg.get("replace_in_place", False)
        delete_source = cfg.get("delete_source", True)

        path = Path(file_path)
        orig_size = path.stat().st_size
        self._log(f"Original size      : {_fmt_size(orig_size)}")

        # Resolve output path (mirrors subfolder structure)
        rel = path.relative_to(source_base)
        file_name = rel.name
        file_base = rel.stem
        rel_dir = str(rel.parent) if str(rel.parent) != "." else ""

        if replace_in_place:
            output_dir = str(path.parent)
        else:
            output_dir = os.path.join(output_base, rel_dir) if rel_dir else output_base

        if not Path(output_dir).exists():
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            self._log(f"Created output dir : {output_dir}")

        # -- Probe resolution ------------------------------------------
        probe = self._probe
        try:
            width, height = probe.get_resolution(file_path)
            if width and height:
                self._log(f"Resolution         : {width}x{height}")
            else:
                self._log("WARNING: Could not read resolution. Will attempt encoding.")
        except FFProbeError as e:
            self._log(f"WARNING: ffprobe error: {e}")
            width, height = 0, 0

        # Resolution check (skip if source height below target)
        _, target_h = cfg.get_active_resolution()
        if target_h > 0 and height > 0 and height < target_h:
            self._log("Resolution below output target -- copying original.")
            self._copy_original(file_path, output_dir, file_name, delete_source)
            self._stats_copied += 1
            self._emit_stats()
            self._log("-" * 54)
            return

        # -- Probe duration / bitrate prediction -----------------------
        target_kbps = cfg.get_target_kbps()

        try:
            duration = probe.get_duration(file_path)
        except FFProbeError:
            duration = 0.0

        if duration > 0:
            orig_kbps = round((orig_size * 8) / (duration * 1000), 1)
            self._log(f"Duration           : {round(duration, 1)}s")
            self._log(f"Original bitrate   : {orig_kbps} kbps")

            if target_kbps:
                predict_mb = probe.predict_output_size_mb(duration, target_kbps)
                self._log(f"Predicted output   : {predict_mb} MB  (target {target_kbps} kbps)")

                if orig_kbps <= target_kbps:
                    self._log("Bitrate already at or below target -- copying original.")
                    self._copy_original(file_path, output_dir, file_name, delete_source)
                    self._stats_skipped += 1
                    self._emit_stats()
                    self._log("-" * 54)
                    return
        else:
            self._log("WARNING: Could not read duration. Proceeding with encode.")

        # -- Encode ----------------------------------------------------
        src_ext = path.suffix
        fmt_override = cfg.get_nested("advanced", "container", "format", default="auto")
        _, out_ext = get_output_format(src_ext, fmt_override)

        temp_output = self._hb_runner.make_temp_output(suffix=out_ext)
        args = build_args(cfg.data, file_path, temp_output)

        mode = cfg.get("encoding_mode", "abr")
        encoder = cfg.get_active_encoder()
        w, h = cfg.get_active_resolution()
        if mode == "abr":
            self._log(f"Encoding : {encoder} / ABR / {w}x{h}")
        elif mode == "crf":
            q = cfg.get_nested("crf", "quality", default=22)
            self._log(f"Encoding : {encoder} / CRF {q}" + (f" / {w}x{h}" if w else ""))
        else:
            self._log(f"Encoding : {encoder} / Advanced mode")

        self._set_state("encoding")
        success = self._hb_runner.encode(args)

        if self._stop_requested:
            try:
                Path(temp_output).unlink(missing_ok=True)
            except OSError:
                pass
            return

        self.progress_updated.emit("")

        # -- Post-encode -----------------------------------------------
        self._on_encoding_complete(
            success, file_path, temp_output, output_dir,
            file_name, file_base, out_ext, orig_size, delete_source,
        )
        self._set_state("processing")

    # ------------------------------------------------------------------
    #  Post-encode
    # ------------------------------------------------------------------

    def _on_encoding_complete(
        self, success: bool, source_path: str, temp_output: str,
        output_dir: str, file_name: str, file_base: str,
        out_ext: str, orig_size: int, delete_source: bool,
    ):
        temp_path = Path(temp_output)

        if not success or not temp_path.exists() or temp_path.stat().st_size == 0:
            self._log("ERROR: Encoding produced no output. Falling back to original.")
            self._copy_original(source_path, output_dir, file_name, delete_source)
            self._stats_copied += 1
            self._emit_stats()
            self._log("-" * 54)
            return

        encoded_size = temp_path.stat().st_size
        self._log(f"Encoded size       : {_fmt_size(encoded_size)}")

        if encoded_size >= orig_size:
            saving = round(abs(1 - encoded_size / orig_size) * 100, 1)
            self._log(f"Encoded file LARGER than original ({saving}% bigger). Using original.")
            temp_path.unlink(missing_ok=True)
            self._copy_original(source_path, output_dir, file_name, delete_source)
            self._stats_copied += 1
        else:
            saving = round((1 - encoded_size / orig_size) * 100, 1)
            final_name = file_base + out_ext
            final_path = os.path.join(output_dir, final_name)

            replace_in_place = self._config.get("replace_in_place", False)
            if replace_in_place:
                try:
                    Path(source_path).unlink()
                except OSError:
                    pass
                shutil.move(str(temp_path), final_path)
            else:
                shutil.move(str(temp_path), final_path)
                if delete_source:
                    try:
                        Path(source_path).unlink()
                    except OSError:
                        pass

            self._log(f"Saved encoded file : {final_path}")
            self._log(f"Space saved        : {saving}%")
            self._stats_encoded += 1

        if delete_source:
            self._log(f"Source deleted      : {file_name}")
        else:
            self._log(f"Source kept         : {file_name}")

        self._emit_stats()
        self._log("-" * 54)

    # ------------------------------------------------------------------
    #  File operations
    # ------------------------------------------------------------------

    def _copy_original(self, source: str, output_dir: str, file_name: str, delete_source: bool):
        dest = os.path.join(output_dir, file_name)
        replace_in_place = self._config.get("replace_in_place", False)

        if replace_in_place:
            self._log(f"Kept original      : {file_name}")
            return

        try:
            shutil.copy2(source, dest)
        except OSError as e:
            self._log(f"ERROR: Failed to copy original: {e}")
            return

        if delete_source:
            try:
                Path(source).unlink()
            except OSError:
                pass
            self._log(f"Copied original. Source deleted.")
        else:
            self._log(f"Copied original. Source kept.")
