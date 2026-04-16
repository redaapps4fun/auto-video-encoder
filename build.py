"""PyInstaller build script for Auto Video Encoder.

Usage:
    python build.py              # windowed one-folder build (default)
    python build.py --onefile    # windowed single-file binary
    python build.py --console    # keep console window visible (debugging)
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ICON = ROOT / "icon_r.ico"
ENTRY = ROOT / "main.py"
NAME = "AutoVideoEncoder"
SEP = ";" if sys.platform == "win32" else ":"


def _binary_name() -> str:
    if sys.platform == "win32":
        return f"{NAME}.exe"
    if sys.platform == "darwin":
        return f"{NAME}.app"
    return NAME


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Build Auto Video Encoder")
    parser.add_argument("--onefile", action="store_true", help="Single-file binary")
    parser.add_argument("--console", action="store_true", help="Show console window")
    args = parser.parse_args()

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", NAME,
        "--add-data", f"{ICON}{SEP}.",
        "--add-data", f"{ROOT / 'preset resolutions.txt'}{SEP}.",
        "--hidden-import", "PySide6.QtWidgets",
        "--hidden-import", "PySide6.QtGui",
        "--hidden-import", "PySide6.QtCore",
        "--noconfirm",
        "--clean",
    ]

    if ICON.exists() and sys.platform != "linux":
        cmd.extend(["--icon", str(ICON)])

    onefile = args.onefile
    windowed = not args.console

    # macOS .app bundles are always directories; --onefile is incompatible
    if sys.platform == "darwin" and windowed:
        onefile = False

    cmd.append("--onefile" if onefile else "--onedir")

    if windowed:
        cmd.append("--windowed")

    cmd.append(str(ENTRY))

    print(f"Running: {' '.join(cmd)}\n")
    subprocess.run(cmd, check=True)

    if args.onefile:
        out = ROOT / "dist" / _binary_name()
    else:
        out = ROOT / "dist" / NAME / _binary_name()

    print(f"\nBuild complete: {out}")


if __name__ == "__main__":
    main()
