#!/usr/bin/env python3
"""
Build standalone executable of vMix Web Switcher using PyInstaller.
Run: python build_exe.py
"""
import sys
import subprocess
import shutil
from pathlib import Path

def build():
    root_dir = Path(__file__).resolve().parent
    public_dir = root_dir / "public"
    
    if not public_dir.exists():
        print(f"[ERROR] public directory not found at {public_dir}")
        sys.exit(1)

    print("Checking PyInstaller...")
    try:
        import PyInstaller
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # Path separator for --add-data differs by OS (: on Linux/Mac, ; on Windows)
    sep = ";" if sys.platform.startswith("win") else ":"
    add_data_arg = f"{public_dir}{sep}public"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=vmix-switcher",
        "--onefile",
        f"--add-data={add_data_arg}",
        "--clean",
        str(root_dir / "run.py")
    ]

    print(f"Running build command: {' '.join(cmd)}")
    subprocess.check_call(cmd)

    print("\n==================================================")
    print("Build complete! Executable is located in the 'dist' folder:")
    dist_dir = root_dir / "dist"
    for item in dist_dir.glob("vmix-switcher*"):
        print(f" 👉 {item}")
    print("==================================================\n")

if __name__ == "__main__":
    build()
