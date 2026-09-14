@echo off
REM ===================================================
REM  vMix Web Switcher - One-click launcher (Windows)
REM  Non-technical: just double-click this file.
REM  It checks Python, installs what's missing, opens
REM  the browser, and starts the switcher.
REM ===================================================
title vMix Web Switcher (Python)
cd /d "%~dp0"

REM --- Find Python ---
where python >nul 2>nul
if %errorlevel% neq 0 (
    where py >nul 2>nul
    if %errorlevel% neq 0 (
        echo.
        echo  [ERROR] Python 3 is not installed!
        echo.
        echo  Please install it first (free, 2 minutes):
        echo    1. Go to https://www.python.org/downloads/
        echo    2. Download Python 3.11 or newer
        echo    3. IMPORTANT: check "Add python.exe to PATH" during install
        echo    4. Then double-click start.bat again
        echo.
        pause
        exit /b 1
    )
    set PY_CMD=py
) else (
    set PY_CMD=python
)

REM Use virtual environment if possible to avoid permission or path issues
if not exist ".venv" (
    echo Creating virtual environment (.venv)...
    %PY_CMD% -m venv .venv >nul 2>nul
)

if exist ".venv\Scripts\python.exe" (
    set RUN_PY=.venv\Scripts\python.exe
) else (
    set RUN_PY=%PY_CMD%
)

echo  Checking Python packages (first run takes a minute)...
%RUN_PY% -m pip install -r requirements.txt --quiet --disable-pip-version-check
if %errorlevel% neq 0 (
    echo  [WARNING] Pip install had warnings, continuing anyway...
)

echo.
echo  Starting vMix Web Switcher...
echo  The app will open at http://localhost:3000
echo  Keep this window open while using the switcher.
echo.

REM Open browser after a short delay so the server is up
start "" /min cmd /c "timeout /t 4 /nobreak >nul & start "" http://localhost:3000"

%RUN_PY% run.py
if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] The switcher stopped with an error.
    echo  Common fixes:
    echo   - Port 3000 in use? Close the other copy and retry.
    echo   - No internet on first run? pip needs it once to download packages.
    echo.
)
pause
