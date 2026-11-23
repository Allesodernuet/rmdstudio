"""Generate assets/icon.png and assets/icon.ico from the painted logo."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from rmdstudio.icons import logo_pixmap  # noqa: E402


def main() -> None:
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    app = QApplication.instance() or QApplication([])
    png = assets / "icon.png"
    ico = assets / "icon.ico"
    logo_pixmap(512).save(str(png), "PNG")
    image = Image.open(png).convert("RGBA")
    image.save(
        ico,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"Wrote {png}")
    print(f"Wrote {ico}")
    del app


if __name__ == "__main__":
    main()
