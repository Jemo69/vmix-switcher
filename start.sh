#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "==================================================="
echo "       vMix Web Switcher Launcher (Python)"
echo "==================================================="

if command -v python3 >/dev/null 2>&1; then
    PY_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PY_CMD="python"
else
    echo "[ERROR] Python 3 is not installed!"
    echo "Please install Python 3.9+ from https://www.python.org/"
    exit 1
fi

echo "Checking Python dependencies..."
$PY_CMD -m pip install -r requirements.txt --quiet

echo "Starting vMix Web Switcher..."
$PY_CMD run.py
