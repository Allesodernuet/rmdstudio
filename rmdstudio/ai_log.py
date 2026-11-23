"""Append-only AI usage log (JSON Lines)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import paths


def resolve_ai_log_path(
    document_path: Path | None,
    project_root: Path | None,
    setting: str,
) -> Path:
    value = (setting or "").strip()
    if value:
        candidate = Path(value).expanduser()
        if candidate.is_absolute():
            return candidate
        if project_root is not None:
            return project_root / candidate
        if document_path is not None:
            return document_path.parent / candidate
        return paths.app_data_dir() / candidate
    if project_root is not None:
        return project_root / "ai-usage.jsonl"
    if document_path is not None:
        return document_path.parent / "ai-usage.jsonl"
    return paths.app_data_dir() / "ai-usage.jsonl"


def setting_value_for(path: Path, project_root: Path | None, document_path: Path | None) -> str:
    base = project_root if project_root is not None else (document_path.parent if document_path else None)
    if base is not None:
        try:
            return path.resolve().relative_to(base.resolve()).as_posix()
        except ValueError:
            pass
    return str(path)


def append_record(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except OSError:
            pass
