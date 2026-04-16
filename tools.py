"""Download and manage HandBrakeCLI + ffprobe binaries.

Platform-aware download from:
  - ffprobe:      https://ffbinaries.com/api
  - HandBrakeCLI: https://github.com/HandBrake/HandBrake/releases

Binaries are stored in a persistent per-user directory so they survive
PyInstaller temp-dir cleanup and app reinstalls.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

APP_DATA_NAME = "AutoVideoEncoder"

FFBINARIES_API = "https://ffbinaries.com/api/v1/version/latest"
HANDBRAKE_RELEASES_API = (
    "https://api.github.com/repos/HandBrake/HandBrake/releases/latest"
)

ProgressCallback = Callable[[int, int], None]  # (bytes_done, total_bytes)


# ------------------------------------------------------------------
#  Platform helpers
# ------------------------------------------------------------------

def _platform_key_ffbinaries() -> str:
    """Map current OS/arch to the ffbinaries API key."""
    system = platform.system().lower()
    machine = platform.machine().lower()
    is_64 = sys.maxsize > 2**32

    if system == "windows":
        return "windows-64" if is_64 else "windows-32"
    if system == "darwin":
        return "osx-64"
    # Linux
    if "aarch64" in machine or "arm64" in machine:
        return "linux-arm64"
    if "arm" in machine:
        return "linux-armhf"
    return "linux-64" if is_64 else "linux-32"


def _platform_suffix_handbrake() -> str | None:
    """Return the HandBrakeCLI asset name suffix for this platform.

    Returns None on Linux (no standalone CLI binary available).
    """
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "windows":
        if "aarch64" in machine or "arm64" in machine:
            return "win-aarch64.zip"
        return "win-x86_64.zip"
    if system == "darwin":
        return ".dmg"
    return None


def _exe_name(tool: str) -> str:
    """Return the expected binary filename for the current OS."""
    if sys.platform == "win32":
        return f"{tool}.exe"
    return tool


# ------------------------------------------------------------------
#  Persistent tools directory
# ------------------------------------------------------------------

def get_tools_dir() -> Path:
    """Return (and create) the platform-specific persistent tools directory."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))

    tools = base / APP_DATA_NAME / "tools"
    tools.mkdir(parents=True, exist_ok=True)
    return tools


def get_tool_path(tool: str) -> Path:
    """Expected absolute path where a tool binary lives."""
    return get_tools_dir() / _exe_name(tool)


def tools_present() -> dict[str, bool]:
    """Check which tools are already installed in the tools directory."""
    return {
        "handbrake": get_tool_path("HandBrakeCLI").is_file(),
        "ffprobe": get_tool_path("ffprobe").is_file(),
    }


def tool_valid(path: str) -> bool:
    """Return True if the path points to an existing executable file."""
    if not path:
        return False
    p = Path(path)
    return p.is_file()


# ------------------------------------------------------------------
#  Download helpers
# ------------------------------------------------------------------

def _download_file(url: str, dest: Path,
                   progress: ProgressCallback | None = None,
                   retries: int = 3) -> Path:
    """Download *url* to *dest* with optional progress reporting and retries."""
    import ssl
    import time

    ctx = ssl.create_default_context()

    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "AutoVideoEncoder/2.0"}
            )
            with urllib.request.urlopen(req, timeout=120, context=ctx) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                done = 0
                with open(dest, "wb") as f:
                    while True:
                        chunk = resp.read(64 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        done += len(chunk)
                        if progress:
                            progress(done, total)
            return dest
        except (ssl.SSLError, urllib.error.URLError, OSError) as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(2 * attempt)
                continue
    raise RuntimeError(f"Download failed after {retries} attempts: {last_exc}")


def _fetch_json(url: str) -> dict:
    """GET a JSON endpoint and return parsed dict."""
    req = urllib.request.Request(url, headers={"User-Agent": "AutoVideoEncoder/2.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


# ------------------------------------------------------------------
#  ffprobe download
# ------------------------------------------------------------------

def download_ffprobe(progress: ProgressCallback | None = None) -> Path:
    """Download ffprobe for the current platform and return its path.

    Raises RuntimeError on failure.
    """
    api = _fetch_json(FFBINARIES_API)
    key = _platform_key_ffbinaries()
    bins = api.get("bin", {}).get(key)
    if not bins or "ffprobe" not in bins:
        raise RuntimeError(
            f"No ffprobe binary available for platform '{key}' at ffbinaries.com"
        )

    zip_url = bins["ffprobe"]
    tools = get_tools_dir()
    tmp_zip = Path(tempfile.mktemp(suffix=".zip", dir=tools))

    try:
        _download_file(zip_url, tmp_zip, progress)
        with zipfile.ZipFile(tmp_zip) as zf:
            target_name = _exe_name("ffprobe")
            for info in zf.infolist():
                if info.filename.lower().endswith(target_name.lower()):
                    info.filename = target_name
                    zf.extract(info, tools)
                    break
            else:
                raise RuntimeError(
                    f"ffprobe binary not found inside downloaded zip"
                )
    finally:
        tmp_zip.unlink(missing_ok=True)

    out = tools / target_name
    if sys.platform != "win32":
        out.chmod(0o755)
    return out


# ------------------------------------------------------------------
#  HandBrakeCLI download
# ------------------------------------------------------------------

def handbrake_available_for_download() -> bool:
    """Whether a direct HandBrakeCLI download exists for this platform."""
    return _platform_suffix_handbrake() is not None


HANDBRAKE_LINUX_INSTRUCTIONS = (
    "HandBrakeCLI is not available as a standalone download for Linux.\n\n"
    "Install via Flatpak:\n"
    "  flatpak install fr.handbrake.ghb\n\n"
    "Then run as:\n"
    "  flatpak run --command=HandBrakeCLI fr.handbrake.ghb\n\n"
    "Or install your distro's handbrake-cli package, then provide the path."
)


def download_handbrake(progress: ProgressCallback | None = None) -> Path:
    """Download HandBrakeCLI for the current platform and return its path.

    Raises RuntimeError on failure or if platform is not supported.
    """
    suffix = _platform_suffix_handbrake()
    if suffix is None:
        raise RuntimeError(HANDBRAKE_LINUX_INSTRUCTIONS)

    release = _fetch_json(HANDBRAKE_RELEASES_API)
    assets = release.get("assets", [])

    asset_url = None
    for a in assets:
        name = a.get("name", "")
        if name.startswith("HandBrakeCLI") and name.endswith(suffix) and not name.endswith(".sig"):
            asset_url = a["browser_download_url"]
            break

    if not asset_url:
        raise RuntimeError(
            f"Could not find HandBrakeCLI asset matching '*{suffix}' "
            f"in the latest GitHub release."
        )

    tools = get_tools_dir()

    if suffix.endswith(".zip"):
        tmp_zip = Path(tempfile.mktemp(suffix=".zip", dir=tools))
        try:
            _download_file(asset_url, tmp_zip, progress)
            with zipfile.ZipFile(tmp_zip) as zf:
                target_name = _exe_name("HandBrakeCLI")
                for info in zf.infolist():
                    if info.filename.lower().endswith(target_name.lower()):
                        info.filename = target_name
                        zf.extract(info, tools)
                        break
                else:
                    raise RuntimeError(
                        "HandBrakeCLI binary not found inside downloaded zip"
                    )
        finally:
            tmp_zip.unlink(missing_ok=True)

    elif suffix.endswith(".dmg"):
        tmp_dmg = Path(tempfile.mktemp(suffix=".dmg", dir=tools))
        try:
            _download_file(asset_url, tmp_dmg, progress)
            _extract_from_dmg(tmp_dmg, tools)
        finally:
            tmp_dmg.unlink(missing_ok=True)

    out = tools / _exe_name("HandBrakeCLI")
    if not out.is_file():
        raise RuntimeError("HandBrakeCLI binary was not extracted successfully")

    if sys.platform != "win32":
        out.chmod(0o755)
    return out


def _extract_from_dmg(dmg_path: Path, dest_dir: Path):
    """Mount a macOS .dmg and copy HandBrakeCLI out of it."""
    import subprocess

    mount_point = Path(tempfile.mkdtemp(prefix="hb_dmg_"))
    try:
        subprocess.run(
            ["hdiutil", "attach", str(dmg_path), "-mountpoint", str(mount_point),
             "-nobrowse", "-quiet"],
            check=True, capture_output=True,
        )
        cli = None
        for f in mount_point.rglob("HandBrakeCLI"):
            cli = f
            break
        if cli is None:
            raise RuntimeError("HandBrakeCLI not found inside DMG")
        shutil.copy2(str(cli), str(dest_dir / "HandBrakeCLI"))
    finally:
        subprocess.run(
            ["hdiutil", "detach", str(mount_point), "-quiet"],
            capture_output=True,
        )
        shutil.rmtree(mount_point, ignore_errors=True)
