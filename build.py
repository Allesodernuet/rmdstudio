"""Build the standalone Windows executable."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable


def run(command: list[str]) -> None:
    print(">", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> None:
    icon = ROOT / "assets" / "icon.ico"
    if not icon.is_file():
        run([PYTHON, str(ROOT / "tools" / "make_icon.py")])
    run([
        PYTHON, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        str(ROOT / "RmdStudio.spec"),
    ])
    built = ROOT / "dist" / "Rmd Studio.exe"
    if not built.is_file():
        raise SystemExit(f"Build finished but {built} was not produced.")
    release = ROOT / "release"
    release.mkdir(exist_ok=True)
    target = release / "Rmd Studio.exe"
    shutil.copy2(built, target)
    size_mb = target.stat().st_size / (1024 * 1024)
    print(f"\nBuilt {target} ({size_mb:.1f} MB)")
    print("The exe is self-contained. Windows may show a SmartScreen warning because it is unsigned.")


if __name__ == "__main__":
    main()
