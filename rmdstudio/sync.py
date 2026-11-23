"""Atomic file writing and external-change detection."""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal


class ExternalConflict(Exception):
    pass


def file_hash(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


class FileSync(QObject):
    external_changed = Signal(str)
    saved = Signal(str)
    error = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._path: Path | None = None
        self._last_hash: str | None = None
        self._external_hash: str | None = None
        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._schedule_check)
        self._watcher.directoryChanged.connect(self._schedule_check)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(320)
        self._timer.timeout.connect(self._check_external)

    @property
    def path(self) -> Path | None:
        return self._path

    @property
    def last_hash(self) -> str | None:
        return self._last_hash

    def reset(self, path: Path | None, text: str = "") -> None:
        self._path = path
        self._last_hash = file_hash(path) if path and path.is_file() else _text_hash(text)
        self._external_hash = None
        self._rewatch()

    def baseline_from_text(self, text: str) -> None:
        self._last_hash = _text_hash(text)
        self._external_hash = None

    def save(self, text: str, force: bool = False) -> None:
        path = self._path
        if path is None:
            raise OSError("No file path has been selected.")
        if path.exists() and not force:
            disk_hash = file_hash(path)
            if disk_hash is not None and self._last_hash is not None and disk_hash != self._last_hash:
                if disk_hash != _text_hash(text):
                    raise ExternalConflict(str(path))
        _atomic_write(path, text)
        self._last_hash = _text_hash(text)
        self._external_hash = None
        self._rewatch()
        self.saved.emit(str(path))

    def _rewatch(self) -> None:
        watched = self._watcher.files()
        if watched:
            self._watcher.removePaths(watched)
        watched_dirs = self._watcher.directories()
        if watched_dirs:
            self._watcher.removePaths(watched_dirs)
        if self._path is None:
            return
        try:
            self._watcher.addPath(str(self._path.parent))
        except Exception:
            pass
        if self._path.is_file():
            try:
                self._watcher.addPath(str(self._path))
            except Exception:
                pass

    def _schedule_check(self, *_args) -> None:
        self._timer.start()

    def _check_external(self) -> None:
        path = self._path
        if path is None:
            return
        if not path.exists():
            if self._external_hash != "<missing>":
                self._external_hash = "<missing>"
                self.external_changed.emit(str(path))
            self._rewatch()
            return
        current = file_hash(path)
        if current is None:
            return
        if self._last_hash is not None and current != self._last_hash:
            if current != self._external_hash:
                self._external_hash = current
                self.external_changed.emit(str(path))
        else:
            self._external_hash = None
        self._rewatch()


def _text_hash(text: str) -> str:
    digest = hashlib.sha256()
    digest.update(text.encode("utf-8"))
    return digest.hexdigest()


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        os.replace(temp_path, path)
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")
