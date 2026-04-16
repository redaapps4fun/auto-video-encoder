"""PyInstaller build script for Auto Video Encoder.

Usage:
    python build.py              # windowed one-folder build (default)
    python build.py --onefile    # windowed single-file .exe
    python build.py --console    # keep console window visible (debugging)
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ICON = ROOT / "icon_r.ico"
ENTRY = ROOT / "main.py"
NAME = "AutoVideoEncoder"


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Build Auto Video Encoder .exe")
    parser.add_argument("--onefile", action="store_true", help="Single-file exe")
    parser.add_argument("--console", action="store_true", help="Show console window")
    args = parser.parse_args()

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", NAME,
        "--icon", str(ICON),
        "--add-data", f"{ICON}{';' if sys.platform == 'win32' else ':'}.",
        "--add-data", f"{ROOT / 'preset resolutions.txt'}{';' if sys.platform == 'win32' else ':'}.",
        "--hidden-import", "PySide6.QtWidgets",
        "--hidden-import", "PySide6.QtGui",
        "--hidden-import", "PySide6.QtCore",
        "--noconfirm",
        "--clean",
    ]

    if args.onefile:
        cmd.append("--onefile")
    else:
        cmd.append("--onedir")

    if not args.console:
        cmd.append("--windowed")

    cmd.append(str(ENTRY))

    print(f"Running: {' '.join(cmd)}\n")
    subprocess.run(cmd, check=True)

    if args.onefile:
        out = ROOT / "dist" / f"{NAME}.exe"
    else:
        out = ROOT / "dist" / NAME / f"{NAME}.exe"

    print(f"\nBuild complete: {out}")


if __name__ == "__main__":
    main()
