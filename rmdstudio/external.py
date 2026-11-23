"""Discovery and launching of RStudio, Rscript and Pandoc."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from . import paths

_cache: dict[str, str | None] = {}


def _first_existing(candidates: list[str | Path]) -> str | None:
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        try:
            if path.is_file():
                return str(path)
        except OSError:
            continue
    return None


def _which(*names: str) -> str | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def find_rstudio(override: str = "") -> str | None:
    if override and Path(override).is_file():
        return override
    cached = _cache.get("rstudio")
    if cached:
        return cached
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    local_app = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        _which("rstudio", "rstudio.exe"),
        Path(program_files) / "RStudio" / "rstudio.exe",
        Path(program_files) / "RStudio" / "bin" / "rstudio.exe",
        Path(local_app) / "Programs" / "RStudio" / "rstudio.exe",
        Path(local_app) / "RStudio" / "rstudio.exe",
    ]
    result = _first_existing(candidates)
    _cache["rstudio"] = result
    return result


def find_rscript(override: str = "") -> str | None:
    if override and Path(override).is_file():
        return override
    cached = _cache.get("rscript")
    if cached:
        return cached
    program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    local_app = Path(os.environ.get("LOCALAPPDATA", ""))
    candidates: list[str | Path] = [
        _which("Rscript", "Rscript.exe"),
    ]
    for root in (program_files / "R", local_app / "Programs" / "R", local_app / "R"):
        try:
            installs = sorted(root.glob("R-*"), reverse=True)
        except OSError:
            installs = []
        for install in installs:
            candidates.append(install / "bin" / "Rscript.exe")
            candidates.append(install / "bin" / "x64" / "Rscript.exe")
    result = _first_existing(candidates)
    _cache["rscript"] = result
    return result


def find_pandoc(override: str = "") -> str | None:
    if override and Path(override).is_file():
        return override
    cached = _cache.get("pandoc")
    if cached:
        return cached
    program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    local_app = Path(os.environ.get("LOCALAPPDATA", ""))
    candidates: list[str | Path] = [
        _which("pandoc", "pandoc.exe"),
        program_files / "RStudio" / "resources" / "app" / "bin" / "quarto" / "bin" / "tools" / "pandoc.exe",
        program_files / "RStudio" / "resources" / "app" / "bin" / "pandoc" / "pandoc.exe",
        program_files / "RStudio" / "resources" / "app" / "bin" / "quarto" / "bin" / "pandoc.exe",
        local_app / "Pandoc" / "pandoc.exe",
        program_files / "Pandoc" / "pandoc.exe",
    ]
    result = _first_existing(candidates)
    _cache["pandoc"] = result
    return result


def clear_cache() -> None:
    _cache.clear()


def open_in_rstudio(path: Path, override: str = "") -> bool:
    exe = find_rstudio(override)
    if not exe:
        return False
    try:
        flags = 0
        if os.name == "nt":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen([exe, str(path)], cwd=str(path.parent), creationflags=flags)
        return True
    except OSError:
        return False


def open_path(path: Path) -> bool:
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def rmarkdown_environment(pandoc_override: str = "") -> dict[str, str]:
    """RStudio normally sets RSTUDIO_PANDOC for rmarkdown; do the same.

    R also needs a writable temporary directory. Some locked-down Windows
    sessions make the system TEMP folder read-only for child processes, so
    point R at the application's own runtime folder as a fallback.
    """
    env = os.environ.copy()
    pandoc = find_pandoc(pandoc_override)
    if pandoc:
        env["RSTUDIO_PANDOC"] = str(Path(pandoc).parent)
    try:
        rtemp = paths.app_data_dir() / "rtemp"
        rtemp.mkdir(parents=True, exist_ok=True)
        env["TMPDIR"] = str(rtemp)
        env["TMP"] = str(rtemp)
        env["TEMP"] = str(rtemp)
    except OSError:
        pass
    return env


def knit_to_html(path: Path, rscript_override: str = "") -> tuple[bool, str]:
    """Run rmarkdown::render on a file, synchronously. Returns (ok, log)."""
    rscript = find_rscript(rscript_override)
    if not rscript:
        return False, "Rscript was not found. Set its path in Settings."
    posix = path.as_posix().replace("'", "\\'")
    expression = (
        "rmarkdown::render("
        f"'{posix}', output_format='html_document', quiet=TRUE, envir=new.env())"
    )
    try:
        completed = subprocess.run(
            [rscript, "-e", expression],
            cwd=str(path.parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
            env=rmarkdown_environment(),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    log = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode == 0, log.strip() or f"Rscript exited with code {completed.returncode}."


def pandoc_html(markdown_text: str, pandoc_override: str = "") -> str | None:
    """Convert Markdown to an HTML fragment using Pandoc, if available."""
    pandoc = find_pandoc(pandoc_override)
    if not pandoc:
        return None
    try:
        completed = subprocess.run(
            [pandoc, "-f", "markdown+smart", "-t", "html"],
            input=markdown_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout


def pandoc_markdown_to_json(markdown_text: str, pandoc_override: str = "") -> dict | None:
    pandoc = find_pandoc(pandoc_override)
    if not pandoc:
        return None
    try:
        completed = subprocess.run(
            [pandoc, "-f", "markdown+smart", "-t", "json"],
            input=markdown_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    import json

    try:
        return json.loads(completed.stdout)
    except ValueError:
        return None


def self_check() -> dict[str, str | None]:
    return {
        "rstudio": find_rstudio(),
        "rscript": find_rscript(),
        "pandoc": find_pandoc(),
        "python": sys.executable,
    }
