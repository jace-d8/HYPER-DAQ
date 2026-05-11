@echo off
REM One-time setup: activates the venv and creates the HYPER-DAQ desktop shortcut.
REM Save your icon image as assets\icon.png first, then double-click this.

cd /d "%~dp0"

if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
) else if exist "venv\Scripts\activate.bat" (
    call "venv\Scripts\activate.bat"
) else (
    echo No virtual environment found ^(.venv or venv^). Aborting.
    pause
    exit /b 1
)

python setup_shortcut.py
pause
