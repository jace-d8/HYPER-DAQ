"""One-shot helper to create a HYPER-DAQ desktop shortcut on Windows.

Steps:
    1. Save your icon image as ``assets/icon.png`` (any reasonable size — the
       larger HYPER logo PNG works great).
    2. From the repo root, with the venv active, run:
           python setup_shortcut.py
    3. A "HYPER-DAQ.lnk" appears on your Desktop, with the HYPER icon.
       Double-click it to launch the app.

The script converts the PNG to a multi-resolution .ico (Windows shortcuts
prefer this), then uses PowerShell to materialise the .lnk so we don't need
pywin32. Both Pillow (for PNG→ICO) and PowerShell (for .lnk) are the only
external dependencies; Pillow is already in your venv (pulled in by openpyxl).
"""

from __future__ import annotations

import os
import subprocess
import sys
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
        sys.exit(
            "Pillow not installed. Run: pip install Pillow\n"
            "(or `pip install -r requirements.txt` if you have one)."
        )

    img = Image.open(png_path).convert("RGBA")
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ico_path, format="ICO", sizes=sizes)


def _create_shortcut_windows(target: Path, icon: Path, name: str = "HYPER-DAQ") -> Path:
    """Create a .lnk on the user's Desktop pointing at target, with icon."""
    desktop = Path(os.path.join(os.path.expanduser("~"), "Desktop"))
    if not desktop.exists():
        # OneDrive-redirected Desktop, etc.
        alt = Path(os.environ.get("USERPROFILE", "")) / "Desktop"
        desktop = alt if alt.exists() else desktop
    desktop.mkdir(parents=True, exist_ok=True)
    lnk_path = desktop / f"{name}.lnk"

    # Use PowerShell's WScript.Shell COM object — no pip dependencies.
    ps_script = (
        f"$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut('{lnk_path}'); "
        f"$s.TargetPath = '{target}'; "
        f"$s.WorkingDirectory = '{target.parent}'; "
        f"$s.IconLocation = '{icon}'; "
        f"$s.Description = 'HYPER-DAQ — sensor data acquisition'; "
        f"$s.WindowStyle = 7; "  # minimised — we don't want the bat console
        f"$s.Save()"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        check=True,
    )
    return lnk_path


def main() -> int:
    if sys.platform != "win32":
        sys.exit("setup_shortcut.py only runs on Windows (lnk files are Windows-specific).")

    if not ICON_PNG.exists():
        sys.exit(
            f"Icon not found: {ICON_PNG}\n"
            "Save your HYPER logo PNG to that path, then re-run this script."
        )
    if not LAUNCHER.exists():
        sys.exit(f"Launcher missing: {LAUNCHER}")

    print(f"Converting {ICON_PNG.name} → {ICON_ICO.name} (multi-resolution) ...")
    _convert_png_to_ico(ICON_PNG, ICON_ICO)

    print("Creating desktop shortcut ...")
    lnk = _create_shortcut_windows(LAUNCHER, ICON_ICO)

    print(f"\nDone. Shortcut placed at: {lnk}")
    print("Double-click it to launch HYPER-DAQ.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
