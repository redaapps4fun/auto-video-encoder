"""HandBrakeRunner - launch HandBrakeCLI, parse progress, build command args.

Provides both a synchronous interface (for the worker thread) and signal-based
progress reporting that the GUI can connect to.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal


def get_output_format(source_ext: str, override: str = "auto") -> tuple[str, str]:
    """Return (handbrake_format_flag, output_extension) for a source extension.

    If *override* is not ``"auto"`` / ``"Auto"``, it is used directly.
    """
    if override and override.lower() not in ("auto", ""):
        fmt = override
        ext_map = {"av_mkv": ".mkv", "av_mp4": ".mp4", "av_webm": ".webm"}
        return fmt, ext_map.get(fmt, ".mkv")

    ext = source_ext.lower()
    if ext in (".mp4", ".m4v"):
        return "av_mp4", ".mp4"
    return "av_mkv", ".mkv"


def build_args(config_data: dict, source: str, output: str) -> list[str]:
    """Build the full HandBrakeCLI argument list from config and paths.

    Dispatches to the correct builder based on ``config_data["encoding_mode"]``.
    """
    mode = config_data.get("encoding_mode", "abr")
    source_ext = Path(source).suffix

    if mode == "abr":
        return _build_abr_args(config_data, source, output, source_ext)
    elif mode == "crf":
        return _build_crf_args(config_data, source, output, source_ext)
    else:
        return _build_advanced_args(config_data, source, output, source_ext)


# ---------------------------------------------------------------------------
#  ABR mode
# ---------------------------------------------------------------------------

def _build_abr_args(cfg: dict, src: str, out: str, src_ext: str) -> list[str]:
    from ui.resources import ABR_PRESETS

    abr = cfg.get("abr", {})
    preset = abr.get("preset", "720p")
    if preset in ABR_PRESETS:
        p = ABR_PRESETS[preset]
        width, height, vb = p["width"], p["height"], p["vb"]
    else:
        width = abr.get("custom_width", 1280)
        height = abr.get("custom_height", 720)
        vb = abr.get("custom_vb", 1000)

    encoder = abr.get("encoder", "nvenc_h265")
    ab = abr.get("audio_bitrate", 128)
    fmt_override = cfg.get("advanced", {}).get("container", {}).get("format", "auto")
    hb_fmt, _ = get_output_format(src_ext, fmt_override)

    return [
        "-i", src, "-o", out,
        "--encoder", encoder,
        "--vb", str(vb),
        "--ab", str(ab),
        "--aencoder", "av_aac",
        "--width", str(width),
        "--height", str(height),
        "--loose-anamorphic",
        "--format", hb_fmt,
    ]


# ---------------------------------------------------------------------------
#  CRF mode
# ---------------------------------------------------------------------------

def _build_crf_args(cfg: dict, src: str, out: str, src_ext: str) -> list[str]:
    from ui.resources import ABR_PRESETS

    crf = cfg.get("crf", {})
    quality = crf.get("quality", 22)
    encoder = crf.get("encoder", "nvenc_h265")
    ab = crf.get("audio_bitrate", 128)
    audio_enc = crf.get("audio_encoder", "av_aac")
    fmt_override = cfg.get("advanced", {}).get("container", {}).get("format", "auto")
    hb_fmt, _ = get_output_format(src_ext, fmt_override)

    args = [
        "-i", src, "-o", out,
        "--encoder", encoder,
        "--quality", str(quality),
        "--ab", str(ab),
        "--aencoder", audio_enc,
        "--format", hb_fmt,
    ]

    res_preset = crf.get("resolution_preset", "720p")
    if res_preset != "Source":
        if res_preset in ABR_PRESETS:
            p = ABR_PRESETS[res_preset]
            args += ["--width", str(p["width"]), "--height", str(p["height"])]
        else:
            w = crf.get("custom_width", 1280)
            h = crf.get("custom_height", 720)
            args += ["--width", str(w), "--height", str(h)]
        args.append("--loose-anamorphic")

    return args


# ---------------------------------------------------------------------------
#  Advanced mode
# ---------------------------------------------------------------------------

def _build_advanced_args(cfg: dict, src: str, out: str, src_ext: str) -> list[str]:
    adv = cfg.get("advanced", {})
    v = adv.get("video", {})
    a = adv.get("audio", {})
    p = adv.get("picture", {})
    f = adv.get("filters", {})
    s = adv.get("subtitles", {})
    c = adv.get("container", {})

    args = ["-i", src, "-o", out]

    # -- Video ---------------------------------------------------------
    args += ["--encoder", v.get("encoder", "nvenc_h265")]

    rc = v.get("rate_control", "quality")
    if rc == "quality":
        q = v.get("quality", 22.0)
        args += ["--quality", str(q)]
    else:
        args += ["--vb", str(v.get("vb", 1000))]

    _add_opt(args, "--encoder-preset", v.get("encoder_preset"))
    _add_opt(args, "--encoder-tune", v.get("encoder_tune"))
    _add_opt(args, "--encoder-profile", v.get("encoder_profile"))
    _add_opt(args, "--encoder-level", v.get("encoder_level"))

    if v.get("multi_pass"):
        args.append("--multi-pass")
        if v.get("turbo"):
            args.append("--turbo")

    fr = v.get("framerate", "")
    if fr and fr != "Same as source":
        args += ["--rate", str(fr)]
        fm = v.get("framerate_mode", "vfr")
        if fm == "cfr":
            args.append("--cfr")
        elif fm == "pfr":
            args.append("--pfr")

    _add_opt(args, "--encopts", v.get("encopts"))

    hw = v.get("hw_decoding", "")
    if hw and hw.lower() != "off":
        args += ["--enable-hw-decoding", hw]

    hdr = v.get("hdr_metadata", "")
    if hdr and hdr.lower() != "off":
        args += ["--hdr-dynamic-metadata", hdr]

    # -- Audio ---------------------------------------------------------
    args += ["--aencoder", a.get("encoder", "av_aac")]
    args += ["--ab", str(a.get("bitrate", 128))]

    aq = a.get("quality")
    if aq is not None:
        args += ["--aq", str(aq)]

    mx = a.get("mixdown", "")
    if mx and mx != "stereo":
        args += ["--mixdown", mx]

    sr = a.get("samplerate", "auto")
    if sr and sr.lower() != "auto":
        args += ["--arate", sr]

    drc = a.get("drc", 0.0)
    if drc > 0:
        args += ["--drc", str(drc)]

    gain = a.get("gain", 0.0)
    if gain != 0:
        args += ["--gain", str(gain)]

    tracks = a.get("tracks", "")
    if tracks and tracks != "1":
        args += ["--audio", tracks]

    lang = a.get("lang_list", "")
    if lang:
        args += ["--audio-lang-list", lang]

    if a.get("keep_names"):
        args.append("--keep-aname")

    # -- Picture -------------------------------------------------------
    w = p.get("width", 0)
    h = p.get("height", 0)
    if w and h:
        args += ["--width", str(w), "--height", str(h)]

    mw = p.get("max_width")
    if mw:
        args += ["--maxWidth", str(mw)]
    mh = p.get("max_height")
    if mh:
        args += ["--maxHeight", str(mh)]

    anam = p.get("anamorphic", "loose")
    anam_map = {
        "none": "--non-anamorphic",
        "auto": "--auto-anamorphic",
        "loose": "--loose-anamorphic",
        "custom": "--custom-anamorphic",
    }
    anam_flag = anam_map.get(anam.lower(), "--loose-anamorphic")
    args.append(anam_flag)

    mod = p.get("modulus", 2)
    if mod and mod != 2:
        args += ["--modulus", str(mod)]

    crop_mode = p.get("crop_mode", "auto")
    if crop_mode.lower() != "auto":
        args += ["--crop-mode", crop_mode.lower()]
        if crop_mode.lower() == "custom":
            crop = p.get("crop", "0:0:0:0")
            if crop and crop != "0:0:0:0":
                args += ["--crop", crop]

    cr = p.get("color_range", "auto")
    if cr and cr.lower() != "auto":
        args += ["--color-range", cr.lower()]

    cm = p.get("color_matrix", "")
    if cm and cm.lower() != "auto":
        matrix_map = {"bt.2020": "2020", "bt.709": "709", "bt.601": "601", "pal": "pal"}
        args += ["--color-matrix", matrix_map.get(cm.lower(), cm)]

    rot = p.get("rotate", 0)
    hflip = p.get("hflip", False)
    if rot or hflip:
        args += ["--rotate", f"angle={rot}:hflip={1 if hflip else 0}"]

    # -- Filters -------------------------------------------------------
    _add_filter(args, f, "deinterlace", {
        "yadif": "-d", "bwdif": "--bwdif", "decomb": "--decomb",
    })

    comb = f.get("comb_detect", "off")
    if comb.lower() not in ("off", ""):
        if comb.lower() == "default":
            args.append("--comb-detect")
        else:
            args += ["--comb-detect", comb.lower()]

    if f.get("detelecine"):
        args.append("--detelecine")

    dn = f.get("denoise", "off")
    if dn.lower() == "hqdn3d":
        strength = f.get("denoise_strength", "")
        args += ["--hqdn3d"] if not strength else ["--hqdn3d", strength]
    elif dn.lower() == "nlmeans":
        strength = f.get("denoise_strength", "")
        args += ["--nlmeans"] if not strength else ["--nlmeans", strength]
        tune = f.get("denoise_tune", "")
        if tune and tune != "none":
            args += ["--nlmeans-tune", tune]

    cs = f.get("chroma_smooth", "off")
    if cs.lower() not in ("off", ""):
        args += ["--chroma-smooth", cs.lower()]
        cs_tune = f.get("chroma_smooth_tune", "")
        if cs_tune:
            args += ["--chroma-smooth-tune", cs_tune]

    sh = f.get("sharpen", "off")
    if sh.lower() == "unsharp":
        strength = f.get("sharpen_strength", "")
        args += ["--unsharp"] if not strength else ["--unsharp", strength]
        tune = f.get("sharpen_tune", "")
        if tune:
            args += ["--unsharp-tune", tune]
    elif sh.lower() == "lapsharp":
        strength = f.get("sharpen_strength", "")
        args += ["--lapsharp"] if not strength else ["--lapsharp", strength]
        tune = f.get("sharpen_tune", "")
        if tune:
            args += ["--lapsharp-tune", tune]

    db = f.get("deblock", "off")
    if db.lower() not in ("off", ""):
        args += ["--deblock", db.lower()]
        db_tune = f.get("deblock_tune", "")
        if db_tune:
            args += ["--deblock-tune", db_tune]

    if f.get("grayscale"):
        args.append("--grayscale")

    cspace = f.get("colorspace", "")
    if cspace and cspace.lower() not in ("off", ""):
        cs_map = {
            "bt.2020": "bt2020", "bt.709": "bt709",
            "bt.601-525": "bt601-6-525", "bt.601-625": "bt601-6-625",
        }
        args += ["--colorspace", cs_map.get(cspace.lower(), cspace)]

    # -- Subtitles -----------------------------------------------------
    st = s.get("tracks", "")
    if st:
        args += ["--subtitle", st]

    slang = s.get("lang_list", "")
    if slang:
        args += ["--subtitle-lang-list", slang]

    if s.get("all"):
        args.append("--all-subtitles")
    elif s.get("first_only"):
        args.append("--first-subtitle")

    sburn = s.get("burn", "")
    if sburn:
        args += ["--subtitle-burned", str(sburn)]

    sdef = s.get("default")
    if sdef is not None:
        args += ["--subtitle-default", str(sdef)]

    sforced = s.get("forced", "")
    if sforced:
        args += ["--subtitle-forced", sforced]

    srt = s.get("srt_file", "")
    if srt:
        args += ["--srt-file", srt]
        _add_opt(args, "--srt-offset", s.get("srt_offset"))
        _add_opt(args, "--srt-lang", s.get("srt_lang"))
        _add_opt(args, "--srt-codeset", s.get("srt_codeset"))
        if s.get("srt_burn"):
            args.append("--srt-burn")
        if s.get("srt_default"):
            args.append("--srt-default")

    ssa = s.get("ssa_file", "")
    if ssa:
        args += ["--ssa-file", ssa]
        _add_opt(args, "--ssa-offset", s.get("ssa_offset"))
        _add_opt(args, "--ssa-lang", s.get("ssa_lang"))
        if s.get("ssa_burn"):
            args.append("--ssa-burn")
        if s.get("ssa_default"):
            args.append("--ssa-default")

    if s.get("keep_names"):
        args.append("--keep-subname")

    # -- Container / Output --------------------------------------------
    hb_fmt, _ = get_output_format(src_ext, c.get("format", "auto"))
    args += ["--format", hb_fmt]

    if c.get("chapters", True):
        args.append("--markers")

    if c.get("optimize") and hb_fmt == "av_mp4":
        args.append("--optimize")

    if c.get("ipod_atom") and hb_fmt == "av_mp4":
        args.append("--ipod-atom")

    if c.get("align_av"):
        args.append("--align-av")

    if c.get("keep_metadata", True):
        args.append("--keep-metadata")

    if c.get("inline_params"):
        args.append("--inline-parameter-sets")

    return args


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _add_opt(args: list[str], flag: str, value: Any):
    """Append ``[flag, value]`` only if *value* is truthy."""
    if value:
        args += [flag, str(value)]


def _add_filter(args: list[str], filters: dict, key: str, flag_map: dict):
    """Add a deinterlace-style filter flag if enabled."""
    val = filters.get(key, "off")
    if val.lower() in ("off", ""):
        return
    flag = flag_map.get(val.lower())
    if flag:
        preset = filters.get(f"{key}_preset", "")
        if preset:
            args += [flag, preset]
        else:
            args.append(flag)


# ---------------------------------------------------------------------------
#  Progress regex
# ---------------------------------------------------------------------------

_PROGRESS_RE = re.compile(
    r"Encoding: task (\d+) of (\d+), ([\d.]+) %"
    r"(?: \(([\d.]+) fps, avg ([\d.]+) fps, ETA (\S+)\))?"
)


def parse_progress(line: str) -> dict | None:
    """Parse a HandBrake stderr progress line.

    Returns a dict like::

        {
            "task": 1,
            "total_tasks": 1,
            "percent": 69.57,
            "fps": 104.61,
            "avg_fps": 101.67,
            "eta": "00h00m37s",
            "raw": "Encoding: task 1 of 1, 69.57 % ..."
        }

    or ``None`` if the line isn't a progress update.
    """
    m = _PROGRESS_RE.search(line)
    if not m:
        return None
    return {
        "task": int(m.group(1)),
        "total_tasks": int(m.group(2)),
        "percent": float(m.group(3)),
        "fps": float(m.group(4)) if m.group(4) else 0.0,
        "avg_fps": float(m.group(5)) if m.group(5) else 0.0,
        "eta": m.group(6) or "",
        "raw": line.strip(),
    }


class HandBrakeRunner(QObject):
    """Manages a single HandBrakeCLI encoding process.

    Runs synchronously (blocking) and emits signals for progress updates.
    Designed to be called from the EncoderEngine's worker thread.
    """

    progress_updated = Signal(str)
    encoding_finished = Signal(bool)

    def __init__(self, handbrake_path: str | Path, parent: QObject | None = None):
        super().__init__(parent)
        self._exe = str(handbrake_path)
        self._process: subprocess.Popen | None = None
        self._cancelled = False

    @property
    def exe(self) -> str:
        return self._exe

    @exe.setter
    def exe(self, value: str | Path):
        self._exe = str(value)

    @property
    def pid(self) -> int:
        if self._process and self._process.poll() is None:
            return self._process.pid
        return 0

    def cancel(self):
        """Request cancellation of the running encode."""
        self._cancelled = True
        if self._process and self._process.poll() is None:
            self._process.terminate()

    def encode(self, args: list[str]) -> bool:
        """Run HandBrakeCLI with *args* (should NOT include the exe path).

        Blocks until the encode finishes.  Emits ``progress_updated`` as
        HandBrake reports progress on stderr.  Returns ``True`` on success.
        """
        self._cancelled = False
        cmd = [self._exe] + args

        import sys
        kwargs: dict[str, Any] = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.PIPE,
            "text": False,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW

        try:
            self._process = subprocess.Popen(cmd, **kwargs)
        except FileNotFoundError:
            self.encoding_finished.emit(False)
            return False

        buf = b""
        while True:
            chunk = self._process.stderr.read(256)
            if not chunk:
                break
            buf += chunk
            while b"\r" in buf or b"\n" in buf:
                idx_r = buf.find(b"\r")
                idx_n = buf.find(b"\n")
                if idx_r == -1:
                    idx = idx_n
                elif idx_n == -1:
                    idx = idx_r
                else:
                    idx = min(idx_r, idx_n)

                line = buf[:idx].decode("utf-8", errors="replace").strip()
                buf = buf[idx + 1:]

                if line.startswith("Encoding:"):
                    self.progress_updated.emit(line)

        self._process.wait()
        success = self._process.returncode == 0 and not self._cancelled
        self._process = None
        self.encoding_finished.emit(success)
        return success

    def make_temp_output(self, suffix: str = ".mkv") -> str:
        """Generate a timestamped temp file path for encoding output."""
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return str(Path(tempfile.gettempdir()) / f"compresor_encoded_{stamp}{suffix}")
