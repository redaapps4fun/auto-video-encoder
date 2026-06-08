"""Environment helpers for spawning external CLI tools from PyInstaller builds."""

from __future__ import annotations

import os
import sys


def _is_bundle_lib_path(path: str, meipass: str) -> bool:
    """Return True if *path* points at PyInstaller's extracted bundle libs."""
    if not path:
        return False
    if meipass and path.startswith(meipass):
        return True
    # PyInstaller one-file extracts to /tmp/_MEIxxxxxx/
    if "/_MEI" in path:
        return True
    return False


def env_for_external_tool() -> dict[str, str] | None:
    """Build an environment dict safe for system-installed CLI tools.

    On Linux PyInstaller builds, ``LD_LIBRARY_PATH`` includes the bundle's
    private libs (including an older ``libstdc++.so.6``). Child processes
    inherit that and system binaries like HandBrakeCLI/ffprobe fail with
    GLIBCXX version errors. Strip bundle paths before spawning externals.

    Returns ``None`` when the default inherited environment is fine.
    """
    if not (getattr(sys, "frozen", False) and sys.platform == "linux"):
        return None

    env = os.environ.copy()
    meipass = getattr(sys, "_MEIPASS", "")

    for var in ("LD_LIBRARY_PATH", "LD_PRELOAD"):
        val = env.get(var, "")
        if not val:
            continue
        cleaned = [
            p for p in val.split(":")
            if p and not _is_bundle_lib_path(p, meipass)
        ]
        if cleaned:
            env[var] = ":".join(cleaned)
        else:
            env.pop(var, None)

    return env


def external_subprocess_kwargs() -> dict:
    """Extra keyword args for subprocess.run / Popen when calling external tools."""
    env = env_for_external_tool()
    if env is not None:
        return {"env": env}
    return {}
