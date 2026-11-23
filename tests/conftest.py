import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault(
    "RMDSTUDIO_SETTINGS",
    str(Path(tempfile.mkdtemp(prefix="rmdstudio-tests-")) / "settings.ini"),
)

import pytest


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
