@echo off
title vMix Web Switcher (Python)
echo ===================================================
echo       vMix Web Switcher Launcher (Python)
echo ===================================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    where py >nul 2>nul
    if %errorlevel% neq 0 (
        echo [ERROR] Python 3 is not installed!
        echo Please download and install Python from https://www.python.org/
        echo (Make sure to check "Add Python to PATH" during installation)
        echo.
        pause
        exit /b 1
    )
    set PY_CMD=py
) else (
    set PY_CMD=python
)

echo Checking Python packages...
%PY_CMD% -m pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [WARNING] Pip install had warnings, continuing...
)

echo Starting vMix Web Switcher...
start "" http://localhost:3000
%PY_CMD% run.py
pause
