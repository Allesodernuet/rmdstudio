"""Build the executable, optional signed release and Inno Setup installer."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable
VERSION = "0.4.0"


def run(command: list[str]) -> None:
    print(">", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def find_iscc() -> Path | None:
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe",
    ]
    which = shutil.which("iscc")
    if which:
        candidates.append(Path(which))
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate
    return None


def sign_file(path: Path) -> None:
    thumbprint = os.environ.get("RMD_SIGN_THUMBPRINT", "").strip()
    if not thumbprint:
        return
    script = ROOT / "tools" / "sign.ps1"
    run([
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", str(script),
        "-File", str(path),
        "-Thumbprint", thumbprint,
    ])


def write_install_launcher(release: Path, installer_name: str) -> Path:
    launcher = release / "INSTALL.cmd"
    launcher.write_text(
        "@echo off\n"
        "setlocal\n"
        "rem GitHub rewrites spaces in asset names to dots. Match either form.\n"
        "set \"SRC=\"\n"
        "for %%F in (\"%~dp0Rmd*Setup*.exe\") do set \"SRC=%%~fF\"\n"
        "if not defined SRC (\n"
        "  echo Installer not found next to this script.\n"
        "  pause\n"
        "  exit /b 1\n"
        ")\n"
        "rem Stage in an ASCII temp path; some Inno Setup builds fail when\n"
        "rem launched directly from a folder whose path contains non-ASCII chars.\n"
        "set \"DST=%TEMP%\\Rmd Studio Setup.exe\"\n"
        "copy /Y \"%SRC%\" \"%DST%\" >nul\n"
        "if errorlevel 1 (\n"
        "  echo Could not copy the installer to the temp folder.\n"
        "  pause\n"
        "  exit /b 1\n"
        ")\n"
        "start \"\" /wait \"%DST%\" %*\n"
        "set \"CODE=%ERRORLEVEL%\"\n"
        "del \"%DST%\" >nul 2>nul\n"
        "exit /b %CODE%\n",
        encoding="ascii",
    )
    return launcher


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
    sign_file(target)
    size_mb = target.stat().st_size / (1024 * 1024)
    print(f"\nBuilt {target} ({size_mb:.1f} MB)")
    print("The exe is self-contained. Windows may show a SmartScreen warning because it is unsigned.")

    iscc = find_iscc()
    if iscc is None:
        print("Inno Setup was not found; installer was not built.")
        return
    run([str(iscc), str(ROOT / "installer" / "RmdStudio.iss")])
    installer = release / f"Rmd Studio Setup {VERSION}.exe"
    if not installer.is_file():
        raise SystemExit(f"Installer compiler finished but {installer} was not produced.")
    sign_file(installer)
    launcher = write_install_launcher(release, installer.name)
    print(f"Built {installer}")
    print(f"Launcher {launcher}")
    print("If you are in a folder with non-ASCII characters, run INSTALL.cmd instead of the setup exe.")


if __name__ == "__main__":
    main()
