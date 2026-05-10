"""HYPER-DAQ launcher.

Starts the sensor backend and the GUI as coordinated child processes.
No console windows — backend output goes to /logs/, GUI shows its own window.

Usage:
    python launch.py
or double-click launch.bat (which activates the venv first).
"""

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_MAIN = ROOT / "src" / "backend" / "main.py"
FRONTEND_GUI = ROOT / "src" / "frontend" / "gui.py"
MANIFEST = ROOT / "data" / "sensor_manifest.json"
BACKEND_STARTUP_TIMEOUT = 30.0  # seconds


def main() -> int:
    env = os.environ.copy()
    # PYTHONPATH lets `from src.* import ...` work from anywhere.
    env["PYTHONPATH"] = str(ROOT)

    # Stale manifest from a previous crash would make us think backend is ready
    # immediately. Clear it before starting.
    try:
        MANIFEST.unlink()
    except FileNotFoundError:
        pass

    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW

    backend = subprocess.Popen(
        [sys.executable, str(BACKEND_MAIN)],
        cwd=str(ROOT),
        env=env,
        creationflags=creationflags,
    )

    deadline = time.monotonic() + BACKEND_STARTUP_TIMEOUT
    while not MANIFEST.exists():
        if backend.poll() is not None:
            sys.stderr.write(
                f"Backend exited before manifest appeared (exit code "
                f"{backend.returncode}). Check the latest file in /logs/.\n"
            )
            return 1
        if time.monotonic() > deadline:
            sys.stderr.write(
                "Backend startup timed out (no manifest after "
                f"{BACKEND_STARTUP_TIMEOUT:.0f}s). Check the latest file in /logs/.\n"
            )
            backend.terminate()
            return 1
        time.sleep(0.2)

    gui = subprocess.Popen(
        [sys.executable, str(FRONTEND_GUI)],
        cwd=str(FRONTEND_GUI.parent),
        env=env,
        creationflags=creationflags,
    )

    try:
        gui.wait()
    except KeyboardInterrupt:
        pass
    finally:
        # Backend shuts down cleanly via its finally handlers when terminated.
        # GUI is hard-stopped if still running (window already closed otherwise).
        for proc in (gui, backend):
            if proc.poll() is None:
                proc.terminate()
        for proc in (gui, backend):
            try:
                proc.wait(timeout=10.0)
            except subprocess.TimeoutExpired:
                proc.kill()

    return 0


if __name__ == "__main__":
    sys.exit(main())
