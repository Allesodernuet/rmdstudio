from __future__ import annotations

import os
from pathlib import Path

import pytest


def test_window_selftest(qapp, tmp_path: Path, monkeypatch):
    from rmdstudio.main_window import MainWindow

    window = MainWindow()
    assert window.selftest()
    window._saved_generation = window._generation
    window.close()


def test_new_quarto_document(qapp):
    from rmdstudio.main_window import MainWindow

    window = MainWindow()
    window.new_quarto_document()
    assert window._is_quarto
    assert "format: pdf" in window.front_edit.toPlainText()
    assert window.action_knit.text() == "Render PDF"
    window._saved_generation = window._generation
    window.close()


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
