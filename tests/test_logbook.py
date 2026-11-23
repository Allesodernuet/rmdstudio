from __future__ import annotations

from pathlib import Path

from rmdstudio import logbook


def test_resolve_default_log_next_to_document(tmp_path: Path):
    doc = tmp_path / "paper.Rmd"
    assert logbook.resolve_log_path(doc, "") == tmp_path / "build.log"


def test_relative_and_absolute_settings(tmp_path: Path):
    doc = tmp_path / "paper.Rmd"
    assert logbook.resolve_log_path(doc, "logs/work.log") == tmp_path / "logs" / "work.log"
    absolute = tmp_path / "elsewhere" / "work.log"
    assert logbook.resolve_log_path(doc, str(absolute)) == absolute


def test_append_plain_entries(tmp_path: Path):
    path = tmp_path / "build.log"
    logbook.append_entry(path, "First note\nwith detail")
    logbook.append_entry(path, "Second note")
    text = path.read_text(encoding="utf-8")
    assert "First note\n  with detail" in text
    assert "Second note" in text
    assert text.count("[") >= 2
    assert not text.endswith("\n\n")


def test_append_markdown_entries(tmp_path: Path):
    path = tmp_path / "work.md"
    logbook.append_entry(path, "Markdown note")
    text = path.read_text(encoding="utf-8")
    assert "- **" in text
    assert "Markdown note" in text
