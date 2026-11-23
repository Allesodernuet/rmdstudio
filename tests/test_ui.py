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
