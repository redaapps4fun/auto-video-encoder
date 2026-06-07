"""HeadlessBridge - Qt coordinator for headless web UI."""

from __future__ import annotations

import logging
import json
from collections import deque
from datetime import datetime
from threading import Lock
from typing import Any, Callable

from PySide6.QtCore import QObject, QThread, Signal, Slot

from config import ConfigManager
from encoder_engine import EncoderEngine
from processed_registry import ProcessedRegistry
from tools import (
    download_ffprobe,
    download_handbrake,
    handbrake_available_for_download,
    tool_valid,
)

log = logging.getLogger("compresor")


class _DownloadWorker(QThread):
    progress = Signal(int, int)
    finished_ok = Signal(str, str)
    finished_err = Signal(str, str)

    def __init__(self, tool: str, parent: QObject | None = None):
        super().__init__(parent)
        self._tool = tool

    def run(self):
        try:
            if self._tool == "handbrake":
                path = download_handbrake(
                    lambda done, total: self.progress.emit(done, total)
                )
            else:
                path = download_ffprobe(
                    lambda done, total: self.progress.emit(done, total)
                )
            self.finished_ok.emit(self._tool, str(path))
        except Exception as exc:
            self.finished_err.emit(self._tool, str(exc))


class HeadlessBridge(QObject):
    """Owns config and encoder lifecycle; fans out events to web clients."""

    _LOG_BUFFER_SIZE = 500

    def __init__(self, config: ConfigManager, parent: QObject | None = None):
        super().__init__(parent)
        self._config = config
        self._engine: EncoderEngine | None = None
        self._state = "idle"
        self._stats = {
            "total": 0,
            "encoded": 0,
            "copied": 0,
            "skipped": 0,
            "registry_skipped": 0,
            "queued": 0,
        }
        self._progress = ""
        self._last_status = "Ready"
        self._logs: deque[str] = deque(maxlen=self._LOG_BUFFER_SIZE)
        self._event_callbacks: list[Callable[[dict], None]] = []
        self._callback_lock = Lock()
        self._download_worker: _DownloadWorker | None = None
        self._registry = ProcessedRegistry()

    @property
    def config(self) -> ConfigManager:
        return self._config

    @property
    def is_running(self) -> bool:
        return self._engine is not None and self._engine.state != "idle"

    def register_event_callback(self, callback: Callable[[dict], None]):
        with self._callback_lock:
            self._event_callbacks.append(callback)

    def unregister_event_callback(self, callback: Callable[[dict], None]):
        with self._callback_lock:
            if callback in self._event_callbacks:
                self._event_callbacks.remove(callback)

    def _emit_event(self, event: dict):
        with self._callback_lock:
            callbacks = list(self._event_callbacks)
        for cb in callbacks:
            try:
                cb(event)
            except Exception:
                pass

    def _append_log(self, msg: str):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {msg}"
        self._logs.append(line)
        self._last_status = msg
        log.info(msg)
        self._emit_event({"type": "log", "message": line})

    def get_status_snapshot(self) -> dict:
        return {
            "state": self._state,
            "stats": dict(self._stats),
            "progress": self._progress,
            "status": self._last_status,
            "running": self.is_running,
            "logs": list(self._logs),
        }

    @Slot()
    def start_engine(self):
        if self.is_running:
            return

        if self._engine is not None:
            self._engine.deleteLater()
            self._engine = None

        self._engine = EncoderEngine(self._config)
        self._engine.log_message.connect(self._on_log)
        self._engine.stats_updated.connect(self._on_stats)
        self._engine.progress_updated.connect(self._on_progress)
        self._engine.state_changed.connect(self._on_state_changed)
        self._engine.error_occurred.connect(self._on_error)
        self._engine.finished.connect(self._on_engine_finished)
        self._engine.start()

    @Slot()
    def stop_engine(self):
        if self._engine:
            self._engine.stop()

    @Slot(str)
    def apply_config(self, data_json: str):
        data = json.loads(data_json)
        old_source = self._config.get("source_base", "")
        old_output = self._config.get("output_base", "")
        self._config.load_from_dict(data)
        new_source = self._config.get("source_base", "")
        new_output = self._config.get("output_base", "")
        if old_source != new_source or old_output != new_output:
            self._append_log(
                f"Paths updated — source: {new_source or '(empty)'}, "
                f"output: {new_output or '(empty)'}"
            )
            if self.is_running and old_source != new_source and self._engine:
                self._engine.request_rescan()
        self._emit_event({"type": "config_saved"})

    @Slot(str)
    def clear_processed_history(self, payload_json: str):
        payload = json.loads(payload_json) if payload_json else {}
        source = payload.get("source") or self._config.get("source_base", "")
        count = self._registry.clear(source or None)
        scope = source or "all sources"
        self._append_log(f"Cleared {count} processed-file record(s) for {scope}.")
        self._emit_event({"type": "processed_history_cleared", "count": count})

    @Slot(str)
    def download_tool(self, tool: str):
        if tool not in ("handbrake", "ffprobe"):
            raise ValueError(f"Unknown tool: {tool}")
        if self._download_worker and self._download_worker.isRunning():
            raise RuntimeError("A download is already in progress")
        if tool == "handbrake" and not handbrake_available_for_download():
            raise RuntimeError("HandBrakeCLI auto-download is not available on this platform")

        self._download_worker = _DownloadWorker(tool, self)
        self._download_worker.progress.connect(self._on_download_progress)
        self._download_worker.finished_ok.connect(self._on_download_ok)
        self._download_worker.finished_err.connect(self._on_download_err)
        self._download_worker.start()
        self._emit_event({"type": "download", "tool": tool, "status": "started"})

    def get_tools_status(self) -> dict[str, Any]:
        hb_path = self._config.get("handbrake_cli", "")
        ff_path = self._config.get("ffprobe", "")
        return {
            "handbrake_ok": tool_valid(hb_path),
            "ffprobe_ok": tool_valid(ff_path),
            "handbrake_path": hb_path,
            "ffprobe_path": ff_path,
            "handbrake_downloadable": handbrake_available_for_download(),
        }

    @Slot(str)
    def _on_log(self, msg: str):
        self._append_log(msg)

    @Slot(dict)
    def _on_stats(self, stats: dict):
        self._stats = dict(stats)
        self._emit_event({"type": "stats", "stats": self._stats})

    @Slot(str)
    def _on_progress(self, line: str):
        self._progress = line
        self._emit_event({"type": "progress", "progress": line})

    @Slot(str)
    def _on_state_changed(self, state: str):
        self._state = state
        self._emit_event({"type": "state", "state": state})
        if state != "idle":
            self._emit_event({"type": "engine", "running": True})

    @Slot(str)
    def _on_error(self, msg: str):
        self._append_log(f"ERROR: {msg}")
        self._emit_event({"type": "error", "message": msg})

    @Slot()
    def _on_engine_finished(self):
        self._progress = ""
        self._state = "idle"
        self._engine = None
        self._emit_event({"type": "engine", "running": False})
        self._emit_event({"type": "progress", "progress": ""})
        self._emit_event({"type": "state", "state": "idle"})

    @Slot(int, int)
    def _on_download_progress(self, done: int, total: int):
        self._emit_event({
            "type": "download",
            "status": "progress",
            "done": done,
            "total": total,
        })

    @Slot(str, str)
    def _on_download_ok(self, tool: str, path: str):
        key = "handbrake_cli" if tool == "handbrake" else "ffprobe"
        self._config.set(key, path)
        self._config.save()
        self._append_log(f"Downloaded {tool}: {path}")
        self._emit_event({
            "type": "download",
            "tool": tool,
            "status": "complete",
            "path": path,
        })

    @Slot(str, str)
    def _on_download_err(self, tool: str, message: str):
        self._append_log(f"Download failed ({tool}): {message}")
        self._emit_event({
            "type": "download",
            "tool": tool,
            "status": "error",
            "message": message,
        })
