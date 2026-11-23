from __future__ import annotations

from pathlib import Path

import pytest

from rmdstudio.sync import ExternalConflict, FileSync


def test_atomic_save(qapp, tmp_path: Path):
    path = tmp_path / "doc.Rmd"
    sync = FileSync()
    sync.reset(path, "")
    sync.save("hello\n")
    assert path.read_text(encoding="utf-8") == "hello\n"
    sync.save("world\n")
    assert path.read_text(encoding="utf-8") == "world\n"
    assert not list(tmp_path.glob("*.tmp"))


def test_external_change_signal(qapp, tmp_path: Path):
    path = tmp_path / "doc.Rmd"
    path.write_text("original\n", encoding="utf-8")
    sync = FileSync()
    sync.reset(path, "original\n")
    changes: list[str] = []
    sync.external_changed.connect(changes.append)
    path.write_text("changed outside\n", encoding="utf-8")
    sync._check_external()
    assert changes == [str(path)]


def test_conflict_and_force(qapp, tmp_path: Path):
    path = tmp_path / "doc.Rmd"
    path.write_text("original\n", encoding="utf-8")
    sync = FileSync()
    sync.reset(path, "original\n")
    path.write_text("external\n", encoding="utf-8")
    with pytest.raises(ExternalConflict):
        sync.save("mine\n")
    sync.save("mine\n", force=True)
    assert path.read_text(encoding="utf-8") == "mine\n"
