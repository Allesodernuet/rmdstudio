from __future__ import annotations

import os
from pathlib import Path

import pytest

from rmdstudio.main_window import MODE_MARKDOWN, MODE_QUARTO, MODE_RMD, MainWindow, document_mode_for_path


def test_window_selftest(qapp, tmp_path: Path, monkeypatch):
    window = MainWindow()
    assert window.selftest()
    window._saved_generation = window._generation
    window.close()


def test_new_document_defaults_to_markdown(qapp):
    window = MainWindow()
    window.new_document()
    assert window._mode == MODE_MARKDOWN
    assert window.front_edit.toPlainText() == ""
    assert window.front_panel.isHidden()
    assert not window.action_front.isVisible()
    assert not window.action_knit.isVisible()
    assert not window.action_chunk.isVisible()
    assert not window.action_cite.isVisible()
    assert not window.action_visual.isVisible()
    assert window.doc_title_label.text().startswith("Untitled.md")
    assert window.mode_label.text() == "Markdown"
    window._saved_generation = window._generation
    window.close()


def test_new_quarto_document(qapp):
    window = MainWindow()
    window.new_quarto_document()
    assert window._mode == MODE_QUARTO
    assert "format: pdf" in window.front_edit.toPlainText()
    assert window.action_knit.isVisible()
    assert window.action_front.isVisible()
    assert window.action_chunk.isVisible()
    assert window.action_knit.text() == "Render PDF"
    window._saved_generation = window._generation
    window.close()


def test_new_rmd_document(qapp):
    window = MainWindow()
    window.new_rmd_document()
    assert window._mode == MODE_RMD
    assert "output: pdf_document" in window.front_edit.toPlainText()
    assert window.action_knit.isVisible()
    assert window.action_knit.text() == "Knit to PDF"
    window._saved_generation = window._generation
    window.close()


def test_markdown_save_has_no_yaml(qapp, tmp_path: Path):
    window = MainWindow()
    window.new_document()
    window.editor.textCursor().insertText("Hello Markdown")
    path = tmp_path / "note.md"
    window.path = path
    window.editor.set_base_path(tmp_path)
    window.sync.reset(path, "")
    window._force_next_save = True
    assert window._write_to_path(force=True, silent=True)
    text = path.read_text(encoding="utf-8")
    assert not text.startswith("---")
    assert "Hello Markdown" in text
    window._saved_generation = window._generation
    window.close()


def test_save_as_defaults_to_markdown(qapp, tmp_path: Path, monkeypatch):
    import rmdstudio.main_window as main_window

    window = MainWindow()
    window.new_document()
    window.editor.textCursor().insertText("Hello Markdown")
    target = tmp_path / "note"
    monkeypatch.setattr(
        main_window.QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (str(target), "Markdown (*.md *.markdown)"),
    )
    assert window.save_as()
    assert window._mode == MODE_MARKDOWN
    assert window.path == tmp_path / "note.md"
    text = window.path.read_text(encoding="utf-8")
    assert not text.startswith("---")
    assert "Hello Markdown" in text
    window._saved_generation = window._generation
    window.close()


def test_save_as_quarto_switches_mode(qapp, tmp_path: Path, monkeypatch):
    import rmdstudio.main_window as main_window

    window = MainWindow()
    window.new_document()
    window.editor.textCursor().insertText("Body")
    target = tmp_path / "note.qmd"
    monkeypatch.setattr(
        main_window.QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (str(target), "All files (*)"),
    )
    assert window.save_as()
    assert window._mode == MODE_QUARTO
    assert "format: pdf" in window.front_edit.toPlainText()
    text = target.read_text(encoding="utf-8")
    assert text.startswith("---")
    assert "format: pdf" in text
    window._saved_generation = window._generation
    window.close()


def test_open_markdown_keeps_front_matter_hidden(qapp, tmp_path: Path):
    path = tmp_path / "note.md"
    path.write_text("---\ntitle: Test\n---\n\nBody\n", encoding="utf-8")
    window = MainWindow()
    assert window.open_path(path, check_save=False)
    assert window._mode == MODE_MARKDOWN
    assert "title: Test" in window.front_edit.toPlainText()
    assert window.front_panel.isHidden()
    assert not window.action_front.isVisible()
    window._saved_generation = window._generation
    window.close()


def test_document_mode_for_path():
    assert document_mode_for_path(Path("note.md")) == MODE_MARKDOWN
    assert document_mode_for_path(Path("note.markdown")) == MODE_MARKDOWN
    assert document_mode_for_path(Path("note.Rmd")) == MODE_RMD
    assert document_mode_for_path(Path("note.qmd")) == MODE_QUARTO


def test_project_root_detection(qapp, tmp_path: Path):
    from rmdstudio.main_window import MainWindow

    root = tmp_path / "project"
    root.mkdir()
    (root / "_quarto.yml").write_text("project:\n  type: default\n", encoding="utf-8")
    nested = root / "chapter"
    nested.mkdir()
    doc = nested / "doc.qmd"
    doc.write_text("---\ntitle: Test\nformat: pdf\n---\n\n# Test\n", encoding="utf-8")
    window = MainWindow()
    assert window._detect_project_root(doc) == root
    window._saved_generation = window._generation
    window.close()
