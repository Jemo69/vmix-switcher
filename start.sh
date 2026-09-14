#!/usr/bin/env bash
# ===================================================
#  vMix Web Switcher - One-click launcher (macOS/Linux)
#  Non-technical: double-click (macOS) or run ./start.sh
#  It checks Python, installs what's missing, and starts.
# ===================================================
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "==================================================="
echo "       vMix Web Switcher Launcher (Python)"
echo "==================================================="

if command -v python3 >/dev/null 2>&1; then
    BASE_PY="python3"
elif command -v python >/dev/null 2>&1; then
    BASE_PY="python"
else
    echo ""
    echo "[ERROR] Python 3 is not installed!"
    echo "  macOS:   install from https://www.python.org/downloads/"
    echo "           or run:  brew install python"
    echo "  Ubuntu:  sudo apt install python3 python3-venv python3-pip"
    exit 1
fi

# Set up or use isolated virtualenv to prevent PEP 668 externally-managed errors
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment (.venv)..."
    "$BASE_PY" -m venv .venv 2>/dev/null || true
fi

if [ -f ".venv/bin/python" ]; then
    PY_CMD=".venv/bin/python"
else
    PY_CMD="$BASE_PY"
fi

echo "Checking Python dependencies (first run takes a minute)..."
"$PY_CMD" -m pip install -r requirements.txt --quiet --disable-pip-version-check || {
    echo "[WARNING] pip install had warnings, continuing anyway..."
}

echo ""
echo "Starting vMix Web Switcher..."
echo "Open http://localhost:3000 in your browser."
echo "Keep this terminal open while using the switcher."
echo ""

# Try to open the browser automatically (best effort, never fatal)
(
    sleep 3
    if command -v open >/dev/null 2>&1; then
        open "http://localhost:3000" >/dev/null 2>&1 || true       # macOS
    elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "http://localhost:3000" >/dev/null 2>&1 || true   # Linux
    fi
) &

"$PY_CMD" run.py
