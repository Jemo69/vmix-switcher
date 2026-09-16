#!/usr/bin/env python3
"""
Build standalone executable of vMix Web Switcher using PyInstaller.

Works on Windows, macOS, and Linux. Produces a single file in dist/:
  - Windows: dist/vmix-switcher-windows.exe
  - macOS:   dist/vmix-switcher-macos
  - Linux:   dist/vmix-switcher-linux

Usage:
    pip install -r requirements-build.txt
    python build_exe.py            # onefile build (default, easiest to share)
    python build_exe.py --onedir   # folder build (faster startup, for testing)
    python build_exe.py --debug    # verbose PyInstaller output

The executable is fully self-contained:
  - Web UI (public/) is bundled inside
  - config.json is created NEXT TO the exe on first run (not inside),
    so settings survive updates.
"""
import argparse
import subprocess
import sys
from pathlib import Path

HIDDEN_IMPORTS = [
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "fastapi",
    "starlette",
    "pydantic",
    "websockets",
    "websockets.legacy",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    "mss",
]


def build(onedir: bool = False, debug: bool = False) -> Path:
    root_dir = Path(__file__).resolve().parent
    public_dir = root_dir / "public"
    entry = root_dir / "run.py"

    if not public_dir.exists():
        print(f"[ERROR] public/ directory not found at {public_dir}")
        sys.exit(1)
    if not entry.exists():
        print(f"[ERROR] entry point not found at {entry}")
        sys.exit(1)

    print("Checking PyInstaller...")
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "pyinstaller>=6.0"]
        )

    # --add-data separator differs by OS (: on macOS/Linux, ; on Windows)
    sep = ";" if sys.platform.startswith("win") else ":"
    add_data_arg = f"{public_dir}{sep}public"

    if sys.platform.startswith("win"):
        out_name = "vmix-switcher-windows"
    elif sys.platform == "darwin":
        out_name = "vmix-switcher-macos"
    else:
        out_name = "vmix-switcher-linux"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        f"--name={out_name}",
        "--onefile" if not onedir else "--onedir",
        "--console",  # keep console so users see the LAN URL + password
        f"--add-data={add_data_arg}",
        "--clean",
        "--noconfirm",
    ]
    for mod in HIDDEN_IMPORTS:
        cmd.append(f"--hidden-import={mod}")
    # Exclude rarely-needed extras to slim the binary
    for mod in ("tkinter", "PyQt5", "PyQt6", "PySide6", "matplotlib", "scipy"):
        cmd.append(f"--exclude-module={mod}")
    if debug:
        cmd.append("--log-level=DEBUG")
    cmd.append(str(entry))

    print(f"Running: {' '.join(cmd)}")
    subprocess.check_call(cmd, cwd=root_dir)

    dist_dir = root_dir / "dist"
    if onedir:
        result = dist_dir / out_name / (out_name + (".exe" if sys.platform.startswith("win") else ""))
        if not result.exists():
            result = dist_dir / out_name
    else:
        ext = ".exe" if sys.platform.startswith("win") else ""
        result = dist_dir / (out_name + ext)

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    print("\n==================================================")
    print("Build complete!")
    print(f"  -> {result}")
    print("Share this single file -- no Python needed on the other PC.")
    print("First run creates config.json next to the exe.")
    print("==================================================\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build vMix Switcher executable")
    parser.add_argument("--onedir", action="store_true", help="Folder build instead of single file")
    parser.add_argument("--debug", action="store_true", help="Verbose PyInstaller logs")
    args = parser.parse_args()
    build(onedir=args.onedir, debug=args.debug)
