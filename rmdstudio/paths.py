"""Application data and bundled resource paths."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

from . import APP_NAME


_data_dir: Path | None = None


def workspace_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _can_write(directory: Path) -> bool:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def app_data_dir() -> Path:
    global _data_dir
    if _data_dir is not None:
        return _data_dir
    roaming = os.environ.get("APPDATA")
    local = os.environ.get("LOCALAPPDATA")
    home = Path.home()
    candidates: list[Path] = []
    if roaming:
        candidates.append(Path(roaming) / APP_NAME)
    if local:
        candidates.append(Path(local) / APP_NAME)
    candidates.append(home / APP_NAME)
    candidates.append(workspace_root() / "userdata")
    try:
        candidates.append(Path(tempfile.gettempdir()) / "RmdStudioData")
    except Exception:
        pass
    for candidate in candidates:
        if _can_write(candidate):
            _data_dir = candidate
            return candidate
    fallback = workspace_root() / "userdata"
    try:
        fallback.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    _data_dir = fallback
    return fallback


def settings_path() -> Path:
    try:
        return app_data_dir() / "settings.ini"
    except OSError:
        return workspace_root() / "settings.ini"


def log_path() -> Path:
    try:
        folder = app_data_dir() / "logs"
        folder.mkdir(parents=True, exist_ok=True)
        return folder / "app.log"
    except OSError:
        return workspace_root() / "rmdstudio.log"


def preview_dir() -> Path:
    folder = app_data_dir() / "preview"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def tinytex_dir() -> Path:
    """Install TinyTeX outside roaming profiles when LOCALAPPDATA is usable."""
    local = os.environ.get("LOCALAPPDATA")
    if local:
        folder = Path(local) / "RmdStudio"
        if _can_write(folder):
            return folder / "TinyTeX"
    return app_data_dir() / "TinyTeX"


def resource_path(relative: str) -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / relative
    return workspace_root() / relative


def sample_path() -> Path | None:
    source = resource_path("samples/Welcome.Rmd")
    if not source.is_file():
        return None
    try:
        target = app_data_dir() / "Welcome.Rmd"
        if not target.is_file() or target.stat().st_size != source.stat().st_size:
            shutil.copy2(source, target)
        return target
    except OSError:
        return source


def copy_to_assets(source: Path, document_path: Path) -> str:
    """Copy an image next to the document and return a Markdown-safe relative path."""
    assets = document_path.parent / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    stem = "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in source.stem).strip(" _")
    if not stem:
        stem = "image"
    candidate = assets / f"{stem}{source.suffix.lower()}"
    counter = 2
    while candidate.exists() and candidate.resolve() != source.resolve():
        candidate = assets / f"{stem}-{counter}{source.suffix.lower()}"
        counter += 1
    if candidate.resolve() != source.resolve():
        shutil.copy2(source, candidate)
    return candidate.relative_to(document_path.parent).as_posix()
