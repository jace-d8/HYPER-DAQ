@echo off
REM HYPER-DAQ launcher (Windows). Activates the venv, then runs launch.py.
REM Double-click this file (or a shortcut pointing to it) to start the app.

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

python launch.py
if errorlevel 1 (
    echo HYPER-DAQ exited with an error.
    pause
)
