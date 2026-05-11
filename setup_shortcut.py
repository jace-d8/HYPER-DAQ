"""One-shot helper to create a HYPER-DAQ desktop shortcut on Windows.

Steps:
    1. Save your icon image as ``assets/icon.png`` (any reasonable size — the
       larger HYPER logo PNG works great).
    2. Double-click ``setup_shortcut.bat`` (or, with venv active, run
       ``python setup_shortcut.py``).
    3. A "HYPER-DAQ.lnk" appears on your Desktop, with the HYPER icon.
       Double-click it to launch the app.

Converts the PNG to a multi-resolution .ico (Windows prefers this) and uses
PowerShell to create the .lnk, so the only dependency outside the stdlib is
Pillow (which is already in your venv via openpyxl).
"""

from __future__ import annotations

import os
import subprocess
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
ICON_PNG = ASSETS / "icon.png"
ICON_ICO = ASSETS / "icon.ico"
LAUNCHER = ROOT / "launch.bat"


def _convert_png_to_ico(png_path: Path, ico_path: Path) -> None:
    """Generate a multi-resolution .ico from a PNG using Pillow."""
    try:
        from PIL import Image
    except ImportError:
        print("Pillow is not installed in this venv.")
        print("Run:    pip install Pillow")
        sys.exit(1)

    img = Image.open(png_path).convert("RGBA")
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ico_path, format="ICO", sizes=sizes)


def _resolve_desktop() -> Path:
    """Find the user's Desktop, accounting for OneDrive redirection."""
    candidates = []
    user = os.environ.get("USERPROFILE", os.path.expanduser("~"))
    one_drive = os.environ.get("OneDrive") or os.environ.get("OneDriveConsumer")
    if one_drive:
        candidates.append(Path(one_drive) / "Desktop")
    candidates.append(Path(user) / "OneDrive" / "Desktop")
    candidates.append(Path(user) / "Desktop")
    for c in candidates:
        if c.exists():
            return c
    # Fallback: create the non-OneDrive Desktop.
    fallback = Path(user) / "Desktop"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _create_shortcut_windows(target: Path, icon: Path, name: str = "HYPER-DAQ") -> Path:
    """Place a .lnk on the user's Desktop pointing at `target`, with `icon`."""
    desktop = _resolve_desktop()
    lnk_path = desktop / f"{name}.lnk"

    # PowerShell + WScript.Shell — no pywin32 dependency.
    # NB: paths use single quotes; backslashes are literal inside single-quoted
    # PowerShell strings, so Windows paths embed cleanly.
    ps_script = (
        f"$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut('{lnk_path}'); "
        f"$s.TargetPath = '{target}'; "
        f"$s.WorkingDirectory = '{target.parent}'; "
        f"$s.IconLocation = '{icon}'; "
        f"$s.Description = 'HYPER-DAQ - sensor data acquisition'; "
        f"$s.WindowStyle = 1; "  # normal window so errors are visible
        f"$s.Save()"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("PowerShell failed to create the shortcut.")
        if result.stdout:
            print("stdout:", result.stdout)
        if result.stderr:
            print("stderr:", result.stderr)
        sys.exit(1)
    return lnk_path


def main() -> int:
    if sys.platform != "win32":
        print("setup_shortcut.py only runs on Windows (.lnk files are Windows-specific).")
        return 1

    print("Repo root:", ROOT)
    print("Looking for icon at:", ICON_PNG)

    if not ICON_PNG.exists():
        print()
        print("Icon not found. Save your HYPER logo PNG to:")
        print("   ", ICON_PNG)
        print("Then re-run this script.")
        return 1
    if not LAUNCHER.exists():
        print("Launcher missing:", LAUNCHER)
        return 1

    print("Converting icon.png -> icon.ico (multi-resolution)...")
    _convert_png_to_ico(ICON_PNG, ICON_ICO)

    print("Creating desktop shortcut...")
    lnk = _create_shortcut_windows(LAUNCHER, ICON_ICO)

    print()
    print("Done. Shortcut placed at:")
    print("   ", lnk)
    print("Double-click it to launch HYPER-DAQ.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        # Force the traceback to stdout (the .bat keeps stdout visible via pause).
        print("Unexpected error:")
        traceback.print_exc(file=sys.stdout)
        sys.exit(1)
