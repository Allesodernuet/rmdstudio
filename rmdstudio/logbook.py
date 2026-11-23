"""Append-only writing/build log bookkeeping."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from . import paths


def resolve_log_path(document_path: Path | None, setting: str) -> Path | None:
    """Resolve the user's designated log file against the document folder."""
    value = (setting or "").strip()
    if value:
        candidate = Path(value).expanduser()
        if candidate.is_absolute():
            return candidate
        if document_path is not None:
            return document_path.parent / candidate
        return paths.app_data_dir() / candidate
    if document_path is not None:
        return document_path.parent / "build.log"
    return None


def setting_value_for(path: Path, document_path: Path | None) -> str:
    """Prefer a portable relative setting when the file sits beside the document."""
    if document_path is not None:
        try:
            return path.resolve().relative_to(document_path.parent.resolve()).as_posix()
        except ValueError:
            pass
    return str(path)


def read_log(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def append_entry(path: Path, text: str) -> str:
    """Append a timestamped entry atomically enough for a single-writer log."""
    text = text.strip("\n")
    if not text.strip():
        return ""
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = text.splitlines() or [""]
    is_markdown = path.suffix.lower() in (".md", ".markdown")
    if is_markdown:
        entry = f"- **{stamp}** — {lines[0]}\n"
        entry += "".join(f"  {line}\n" for line in lines[1:])
    else:
        entry = f"[{stamp}] {lines[0]}\n"
        entry += "".join(f"  {line}\n" for line in lines[1:])
    needs_separator = False
    try:
        if path.is_file() and path.stat().st_size:
            with open(path, "rb") as handle:
                handle.seek(-1, os.SEEK_END)
                needs_separator = handle.read(1) != b"\n"
    except OSError:
        needs_separator = False
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        if needs_separator:
            handle.write("\n")
        handle.write(entry)
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except OSError:
            pass
    return entry
