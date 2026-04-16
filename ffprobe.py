"""FFProbeRunner - resolution, duration, and bitrate detection via ffprobe.

All methods are synchronous (subprocess.run) and intended to be called from
the encoder engine's worker thread, never from the GUI thread.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


class FFProbeError(Exception):
    """Raised when ffprobe is missing or returns an error."""


class FFProbeRunner:
    """Thin wrapper around the ffprobe CLI binary."""

    def __init__(self, ffprobe_path: str | Path):
        self._exe = str(ffprobe_path)

    @property
    def exe(self) -> str:
        return self._exe

    @exe.setter
    def exe(self, value: str | Path):
        self._exe = str(value)

    def _run(self, args: list[str], file_path: str) -> str:
        """Execute ffprobe with *args* against *file_path* and return stdout."""
        cmd = [self._exe] + args + [file_path]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=_creation_flags(),
            )
        except FileNotFoundError:
            raise FFProbeError(f"ffprobe not found at: {self._exe}")
        except subprocess.TimeoutExpired:
            raise FFProbeError(f"ffprobe timed out on: {file_path}")
        return result.stdout.strip()

    def get_resolution(self, file_path: str | Path) -> tuple[int, int]:
        """Return (width, height) of the first video stream, or (0, 0)."""
        out = self._run(
            ["-v", "error",
             "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-of", "csv=p=0"],
            str(file_path),
        )
        m = re.search(r"(\d+),(\d+)", out)
        if m:
            return int(m.group(1)), int(m.group(2))
        return 0, 0

    def get_duration(self, file_path: str | Path) -> float:
        """Return duration in seconds, or 0.0 on failure."""
        out = self._run(
            ["-v", "error",
             "-show_entries", "format=duration",
             "-of", "csv=p=0"],
            str(file_path),
        )
        m = re.search(r"[\d.]+", out)
        if m:
            try:
                return float(m.group(0))
            except ValueError:
                pass
        return 0.0

    def get_bitrate(self, file_path: str | Path, file_size_bytes: int) -> float:
        """Calculate actual bitrate in kbps from file size and duration.

        Returns 0.0 if duration cannot be determined.
        """
        duration = self.get_duration(file_path)
        if duration <= 0:
            return 0.0
        return round((file_size_bytes * 8) / (duration * 1000), 1)

    def get_full_info(self, file_path: str | Path) -> dict:
        """Return resolution, duration, and file-size-based bitrate in one call.

        Minimises ffprobe invocations by combining queries.

        Returns:
            {
                "width": int,
                "height": int,
                "duration": float,   # seconds
                "bitrate": float,    # kbps (0 if duration unknown)
            }
        """
        out = self._run(
            ["-v", "error",
             "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-show_entries", "format=duration",
             "-of", "csv=p=0"],
            str(file_path),
        )
        width, height, duration = 0, 0, 0.0

        lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
        for line in lines:
            res_match = re.match(r"^(\d+),(\d+)$", line)
            if res_match:
                width = int(res_match.group(1))
                height = int(res_match.group(2))
                continue
            dur_match = re.match(r"^([\d.]+)$", line)
            if dur_match:
                try:
                    duration = float(dur_match.group(1))
                except ValueError:
                    pass

        file_size = Path(file_path).stat().st_size if Path(file_path).exists() else 0
        bitrate = 0.0
        if duration > 0 and file_size > 0:
            bitrate = round((file_size * 8) / (duration * 1000), 1)

        return {
            "width": width,
            "height": height,
            "duration": duration,
            "bitrate": bitrate,
        }

    def predict_output_size_mb(self, duration: float, target_kbps: int) -> float:
        """Predict output file size in MB given duration and total target kbps."""
        if duration <= 0 or target_kbps <= 0:
            return 0.0
        return round((target_kbps * 1000 / 8) * duration / 1048576, 2)


def _creation_flags() -> int:
    """Return CREATE_NO_WINDOW on Windows to hide console popups."""
    import sys
    if sys.platform == "win32":
        return 0x08000000  # CREATE_NO_WINDOW
    return 0
