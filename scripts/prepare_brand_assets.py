"""Derive UI-ready brand assets from the original artwork in resources/assets/logo.

The original files are never modified. Currently produces:

* smollabs_mascot_clean.png – the transparent mascot with the clipped orbit
  fragment in the top-left corner removed (it reads as a stray shard once the
  mascot is extruded in 3D).

Run after replacing the artwork:  python scripts/prepare_brand_assets.py
"""

from pathlib import Path

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter

LOGO_DIR = Path(__file__).resolve().parent.parent / "resources" / "assets" / "logo"


def main() -> None:
    app = QGuiApplication([])  # noqa: F841 - needed for QPainter on images
    image = QImage(str(LOGO_DIR / "smollabs_mascot.png")).convertToFormat(
        QImage.Format.Format_ARGB32
    )
    painter = QPainter(image)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
    painter.fillRect(QRect(0, 0, 145, 62), Qt.GlobalColor.transparent)
    painter.end()
    out = LOGO_DIR / "smollabs_mascot_clean.png"
    image.save(str(out))
    print(f"wrote {out.relative_to(LOGO_DIR.parent.parent.parent)}")


if __name__ == "__main__":
    main()
