"""ConfigManager - load/save settings from config.json with defaults.

Handles:
- JSON config persistence next to the executable / script
- Deep-merge of saved values over defaults (new keys auto-appear on upgrade)
- INI migration from legacy compresor.ini on first launch
- Platform-aware default paths for HandBrakeCLI and ffprobe
"""

from __future__ import annotations

import json
import os
import sys
import configparser
from copy import deepcopy
from pathlib import Path
from typing import Any


def _default_handbrake_path() -> str:
    from tools import get_tool_path
    managed = get_tool_path("HandBrakeCLI")
    if managed.is_file():
        return str(managed)
    if sys.platform == "win32":
        prog = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        system = prog / "HandBrake" / "HandBrakeCLI.exe"
        if system.exists():
            return str(system)
    return ""


def _default_ffprobe_path() -> str:
    from tools import get_tool_path
    managed = get_tool_path("ffprobe")
    if managed.is_file():
        return str(managed)
    return ""


def _base_defaults() -> dict:
    return {
        "source_base": "",
        "output_base": "",
        "handbrake_cli": _default_handbrake_path(),
        "ffprobe": _default_ffprobe_path(),
        "delete_source": True,
        "video_extensions": [
            ".mkv", ".mp4", ".avi", ".mov", ".wmv",
            ".m4v", ".ts", ".flv", ".mpg", ".mpeg",
        ],
        "replace_in_place": False,
        "auto_start_watcher": False,
        "encoding_mode": "abr",

        "abr": {
            "preset": "720p",
            "encoder": "nvenc_h265",
            "custom_width": 1280,
            "custom_height": 720,
            "custom_vb": 1000,
            "audio_bitrate": 128,
        },

        "crf": {
            "quality": 22,
            "encoder": "nvenc_h265",
            "resolution_preset": "720p",
            "custom_width": 1280,
            "custom_height": 720,
            "audio_encoder": "av_aac",
            "audio_bitrate": 128,
        },

        "advanced": {
            "video": {
                "encoder": "nvenc_h265",
                "rate_control": "quality",
                "quality": 22.0,
                "vb": 1000,
                "encoder_preset": "",
                "encoder_tune": "",
                "encoder_profile": "",
                "encoder_level": "",
                "multi_pass": False,
                "turbo": False,
                "framerate": "",
                "framerate_mode": "vfr",
                "encopts": "",
                "hw_decoding": "",
                "hdr_metadata": "",
            },
            "audio": {
                "encoder": "av_aac",
                "bitrate": 128,
                "quality": None,
                "mixdown": "stereo",
                "samplerate": "auto",
                "drc": 0.0,
                "gain": 0.0,
                "tracks": "1",
                "lang_list": "",
                "keep_names": False,
            },
            "picture": {
                "width": 1280,
                "height": 720,
                "max_width": None,
                "max_height": None,
                "anamorphic": "loose",
                "modulus": 2,
                "crop_mode": "auto",
                "crop": "0:0:0:0",
                "color_range": "auto",
                "color_matrix": "",
                "rotate": 0,
                "hflip": False,
            },
            "filters": {
                "deinterlace": "off",
                "deinterlace_preset": "",
                "comb_detect": "off",
                "detelecine": False,
                "denoise": "off",
                "denoise_strength": "",
                "denoise_tune": "",
                "chroma_smooth": "off",
                "chroma_smooth_tune": "",
                "sharpen": "off",
                "sharpen_strength": "",
                "sharpen_tune": "",
                "deblock": "off",
                "deblock_tune": "",
                "grayscale": False,
                "colorspace": "",
            },
            "subtitles": {
                "tracks": "",
                "lang_list": "",
                "all": False,
                "first_only": False,
                "burn": "",
                "default": None,
                "forced": "",
                "srt_file": "",
                "srt_offset": "",
                "srt_lang": "",
                "srt_codeset": "",
                "srt_burn": False,
                "srt_default": False,
                "ssa_file": "",
                "ssa_offset": "",
                "ssa_lang": "",
                "ssa_burn": False,
                "ssa_default": False,
                "keep_names": False,
            },
            "container": {
                "format": "auto",
                "chapters": True,
                "optimize": False,
                "ipod_atom": False,
                "align_av": False,
                "keep_metadata": True,
                "inline_params": False,
            },
        },
    }


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into a copy of *base*.

    Keys in *base* that are missing from *override* are preserved (handles
    upgrades where new config keys are added).  Keys in *override* that don't
    exist in *base* are kept too (user custom keys).
    """
    result = deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


# Map from INI encoder display name -> internal flag
_INI_ENCODER_MAP = {
    "NVENC H.265 (GPU)": "nvenc_h265",
    "x265 (CPU - Best Quality)": "x265",
    "x264 (CPU - Fast)": "x264",
}


def _migrate_ini(ini_path: Path) -> dict | None:
    """Read a legacy compresor.ini and return a config dict, or None."""
    if not ini_path.exists():
        return None

    cp = configparser.ConfigParser()
    try:
        cp.read(str(ini_path), encoding="utf-8")
    except Exception:
        try:
            cp.read(str(ini_path), encoding="utf-16")
        except Exception:
            return None

    if "Config" not in cp:
        return None

    sec = cp["Config"]
    encoder_display = sec.get("Encoder", "NVENC H.265 (GPU)")
    encoder_flag = _INI_ENCODER_MAP.get(encoder_display, "nvenc_h265")

    target_kbps = _safe_int(sec.get("TargetKbps", "1128"), 1128)
    audio_kbps = 128
    video_kbps = max(target_kbps - audio_kbps, 100)

    width = _safe_int(sec.get("OutWidth", "1280"), 1280)
    height = _safe_int(sec.get("OutHeight", "720"), 720)

    exts_str = sec.get("VideoExts", ".mkv .mp4 .avi .mov .wmv .m4v .ts .flv .mpg .mpeg")
    exts = [e.strip().lower() for e in exts_str.split() if e.strip()]

    preset = _match_abr_preset(width, height, video_kbps)

    return {
        "source_base": sec.get("SourceBase", ""),
        "output_base": sec.get("OutputBase", ""),
        "handbrake_cli": sec.get("HandBrakeCLI", _default_handbrake_path()),
        "ffprobe": sec.get("FFProbe", _default_ffprobe_path()),
        "delete_source": sec.get("DeleteSource", "1") == "1",
        "video_extensions": exts,
        "encoding_mode": "abr",
        "abr": {
            "preset": preset,
            "encoder": encoder_flag,
            "custom_width": width,
            "custom_height": height,
            "custom_vb": video_kbps,
            "audio_bitrate": audio_kbps,
        },
        "crf": {
            "encoder": encoder_flag,
        },
        "advanced": {
            "video": {"encoder": encoder_flag},
            "picture": {"width": width, "height": height},
        },
    }


def _match_abr_preset(width: int, height: int, vb: int) -> str:
    """Return the closest ABR preset name, or 'Custom'."""
    from ui.resources import ABR_PRESETS
    for name, p in ABR_PRESETS.items():
        if p["width"] == width and p["height"] == height and abs(p["vb"] - vb) < 50:
            return name
    return "Custom"


def _safe_int(value: str, default: int) -> int:
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _persistent_config_dir() -> Path:
    """Return a persistent directory for config.json.

    In frozen (PyInstaller) builds sys._MEIPASS is a temp dir that is wiped
    on exit, so we must store config in the platform app-data directory.
    In dev mode we use the project root (next to the source files).
    """
    if getattr(sys, "frozen", False):
        from tools import get_tools_dir
        app_data = get_tools_dir().parent  # .../AutoVideoEncoder/
        app_data.mkdir(parents=True, exist_ok=True)
        return app_data
    return Path(__file__).parent


class ConfigManager:
    """Load, save, and access config.json with defaults and INI migration."""

    def __init__(self, config_dir: str | Path | None = None):
        if config_dir is None:
            config_dir = _persistent_config_dir()
        self._dir = Path(config_dir)
        self._json_path = self._dir / "config.json"
        self._ini_path = self._dir / "compresor.ini"
        self._data: dict = _base_defaults()
        self._load()

    def _load(self):
        if self._json_path.exists():
            try:
                with open(self._json_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self._data = _deep_merge(_base_defaults(), saved)
            except (json.JSONDecodeError, OSError):
                self._data = _base_defaults()
            return

        ini = self._find_ini()
        if ini is not None:
            migrated = _migrate_ini(ini)
            if migrated:
                self._data = _deep_merge(_base_defaults(), migrated)
                self.save()
                return

        self._data = _base_defaults()

    def _find_ini(self) -> Path | None:
        """Locate compresor.ini for migration.

        Checks the config dir first, then the exe's directory (frozen builds)
        or the source tree (dev mode).
        """
        if self._ini_path.exists():
            return self._ini_path
        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).parent
            candidate = exe_dir / "compresor.ini"
            if candidate.exists():
                return candidate
        return None

    def save(self):
        try:
            with open(self._json_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except OSError:
            pass

    def get(self, key: str, default: Any = None) -> Any:
        """Get a top-level config value."""
        return self._data.get(key, default)

    def set(self, key: str, value: Any):
        """Set a top-level config value."""
        self._data[key] = value

    def get_nested(self, *keys: str, default: Any = None) -> Any:
        """Get a nested config value by key path.

        Example: config.get_nested("abr", "encoder") -> "nvenc_h265"
        """
        node = self._data
        for k in keys:
            if isinstance(node, dict) and k in node:
                node = node[k]
            else:
                return default
        return node

    def set_nested(self, *keys_and_value: Any):
        """Set a nested config value.  Last argument is the value.

        Example: config.set_nested("abr", "encoder", "x265")
        """
        if len(keys_and_value) < 2:
            raise ValueError("Need at least one key and a value")
        *keys, value = keys_and_value
        node = self._data
        for k in keys[:-1]:
            if k not in node or not isinstance(node[k], dict):
                node[k] = {}
            node = node[k]
        node[keys[-1]] = value

    def get_section(self, key: str) -> dict:
        """Return a full section dict (e.g. 'abr', 'crf', 'advanced')."""
        return deepcopy(self._data.get(key, {}))

    def set_section(self, key: str, data: dict):
        """Replace a full section dict."""
        self._data[key] = deepcopy(data)

    @property
    def data(self) -> dict:
        """Full config dict (read-only reference for engine)."""
        return self._data

    @property
    def json_path(self) -> Path:
        return self._json_path

    def get_active_encoder(self) -> str:
        """Return the encoder flag for the currently selected mode."""
        mode = self.get("encoding_mode", "abr")
        if mode == "abr":
            return self.get_nested("abr", "encoder", default="nvenc_h265")
        elif mode == "crf":
            return self.get_nested("crf", "encoder", default="nvenc_h265")
        else:
            return self.get_nested("advanced", "video", "encoder", default="nvenc_h265")

    def get_active_resolution(self) -> tuple[int, int]:
        """Return (width, height) for the currently selected mode."""
        from ui.resources import ABR_PRESETS
        mode = self.get("encoding_mode", "abr")
        if mode == "abr":
            preset = self.get_nested("abr", "preset", default="720p")
            if preset in ABR_PRESETS:
                p = ABR_PRESETS[preset]
                return (p["width"], p["height"])
            return (
                self.get_nested("abr", "custom_width", default=1280),
                self.get_nested("abr", "custom_height", default=720),
            )
        elif mode == "crf":
            rp = self.get_nested("crf", "resolution_preset", default="720p")
            if rp == "Source":
                return (0, 0)
            if rp in ABR_PRESETS:
                p = ABR_PRESETS[rp]
                return (p["width"], p["height"])
            return (
                self.get_nested("crf", "custom_width", default=1280),
                self.get_nested("crf", "custom_height", default=720),
            )
        else:
            return (
                self.get_nested("advanced", "picture", "width", default=1280),
                self.get_nested("advanced", "picture", "height", default=720),
            )

    def get_target_kbps(self) -> int | None:
        """Return total target kbps for bitrate prediction, or None if CRF mode."""
        mode = self.get("encoding_mode", "abr")
        if mode == "abr":
            vb = self.get_nested("abr", "custom_vb", default=1000)
            ab = self.get_nested("abr", "audio_bitrate", default=128)
            from ui.resources import ABR_PRESETS
            preset = self.get_nested("abr", "preset", default="720p")
            if preset in ABR_PRESETS:
                vb = ABR_PRESETS[preset]["vb"]
            return vb + ab
        elif mode == "crf":
            return None
        else:
            rc = self.get_nested("advanced", "video", "rate_control", default="quality")
            if rc in ("bitrate", "constant_bitrate"):
                vb = self.get_nested("advanced", "video", "vb", default=1000)
                ab = self.get_nested("advanced", "audio", "bitrate", default=128)
                return vb + ab
            return None
