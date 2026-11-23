"""Small vector icon set drawn with QPainter (no external assets)."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)

from . import theme

_CACHE: dict[tuple[str, str, str], QIcon] = {}
_LOGO_CACHE: dict[int, QPixmap] = {}


def _pen(painter: QPainter, color: QColor, width: float = 1.8) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    return pen


def _text(painter: QPainter, text: str, fg: QColor, *, bold: bool = False, italic: bool = False,
          size: int = 19) -> None:
    font = QFont(theme.UI_FONT)
    font.setPixelSize(size)
    font.setBold(bold)
    font.setItalic(italic)
    painter.setFont(font)
    painter.setPen(fg)
    painter.drawText(QRectF(0, 0, 32, 32), Qt.AlignmentFlag.AlignCenter, text)


def _draw_glyph(name: str, painter: QPainter, fg: QColor, accent: QColor) -> None:
    _pen(painter, fg, 1.8)

    if name == "new":
        painter.drawRoundedRect(QRectF(7, 4, 17, 24), 2, 2)
        painter.drawLine(QPointF(19, 4), QPointF(24, 9))
        painter.drawLine(QPointF(19, 4), QPointF(19, 9))
        painter.drawLine(QPointF(19, 9), QPointF(24, 9))
        _pen(painter, accent, 2.2)
        painter.drawLine(QPointF(15.5, 14.5), QPointF(15.5, 22.5))
        painter.drawLine(QPointF(11.5, 18.5), QPointF(19.5, 18.5))

    elif name == "open":
        path = QPainterPath()
        path.moveTo(4, 12)
        path.lineTo(4, 26)
        path.quadTo(4, 27.5, 5.5, 27.5)
        path.lineTo(26.5, 27.5)
        path.quadTo(28, 27.5, 28, 26)
        path.lineTo(28, 13)
        path.quadTo(28, 11.5, 26.5, 11.5)
        path.lineTo(15, 11.5)
        path.lineTo(12, 8)
        path.lineTo(5.5, 8)
        path.quadTo(4, 8, 4, 9.5)
        painter.drawPath(path)

    elif name in ("save", "save_as"):
        path = QPainterPath()
        path.moveTo(6, 4.5)
        path.lineTo(22.5, 4.5)
        path.lineTo(26.5, 8.5)
        path.lineTo(26.5, 27)
        path.lineTo(5.5, 27)
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawRoundedRect(QRectF(10, 4.5, 8, 6.5), 1, 1)
        painter.drawRoundedRect(QRectF(10, 17, 12, 10), 1, 1)
        if name == "save_as":
            _pen(painter, accent, 2.0)
            painter.drawLine(QPointF(22, 20), QPointF(27, 25))
            painter.drawLine(QPointF(27, 20), QPointF(22, 25))

    elif name in ("undo", "redo"):
        painter.save()
        if name == "redo":
            painter.translate(32, 0)
            painter.scale(-1, 1)
        path = QPainterPath()
        path.moveTo(10, 9)
        path.lineTo(5, 13)
        path.lineTo(10, 17)
        painter.drawPath(path)
        path = QPainterPath()
        path.moveTo(5.5, 13)
        path.cubicTo(13, 11.5, 21.5, 13, 24.5, 18.5)
        path.cubicTo(27, 23, 23.5, 27, 18.5, 26.5)
        _pen(painter, accent, 1.8)
        painter.drawPath(path)
        painter.restore()

    elif name == "bold":
        _text(painter, "B", fg, bold=True)
    elif name == "italic":
        _text(painter, "I", fg, italic=True)
    elif name == "underline":
        _text(painter, "U", fg)
        _pen(painter, accent, 2.0)
        painter.drawLine(QPointF(9, 28), QPointF(23, 28))
    elif name == "strike":
        _text(painter, "S", fg)
        _pen(painter, accent, 2.0)
        painter.drawLine(QPointF(7, 20.5), QPointF(25, 20.5))
    elif name in ("superscript", "subscript"):
        base = QFont(theme.UI_FONT)
        base.setPixelSize(18)
        painter.setFont(base)
        painter.setPen(fg)
        painter.drawText(QRectF(3, 5, 15, 20), Qt.AlignmentFlag.AlignCenter, "x")
        small = QFont(theme.UI_FONT)
        small.setPixelSize(11)
        small.setBold(True)
        painter.setFont(small)
        painter.setPen(accent)
        top = 3 if name == "superscript" else 17
        painter.drawText(QRectF(17, top, 11, 12), Qt.AlignmentFlag.AlignCenter, "2")
    elif name == "align_left":
        for y, x1, x2 in ((9, 6, 26), (14, 6, 20), (19, 6, 26), (24, 6, 17)):
            painter.drawLine(QPointF(x1, y), QPointF(x2, y))
    elif name == "align_center":
        for y, x1, x2 in ((9, 6, 26), (14, 11, 21), (19, 6, 26), (24, 13, 19)):
            painter.drawLine(QPointF(x1, y), QPointF(x2, y))
    elif name == "align_right":
        for y, x1, x2 in ((9, 6, 26), (14, 12, 26), (19, 6, 26), (24, 15, 26)):
            painter.drawLine(QPointF(x1, y), QPointF(x2, y))
    elif name == "align_justify":
        for y, x1, x2 in ((9, 6, 26), (14, 6, 26), (19, 6, 26), (24, 6, 22)):
            painter.drawLine(QPointF(x1, y), QPointF(x2, y))
    elif name == "list_bullet":
        for y in (10, 16, 22):
            painter.setBrush(fg)
            painter.drawEllipse(QPointF(7.5, y), 1.5, 1.5)
            painter.drawLine(QPointF(12, y), QPointF(26, y))
    elif name == "list_number":
        font = QFont(theme.UI_FONT)
        font.setPixelSize(9)
        painter.setFont(font)
        painter.setPen(fg)
        for text, y in (("1", 11), ("2", 17), ("3", 23)):
            painter.drawText(QRectF(4.5, y - 5, 7, 9), Qt.AlignmentFlag.AlignCenter, text)
            painter.drawLine(QPointF(13, y), QPointF(26, y))
    elif name == "indent":
        painter.drawLine(QPointF(6, 9), QPointF(26, 9))
        painter.drawLine(QPointF(6, 15), QPointF(26, 15))
        painter.drawLine(QPointF(6, 21), QPointF(26, 21))
        painter.drawLine(QPointF(6, 27), QPointF(26, 27))
        _pen(painter, accent, 2.2)
        path = QPainterPath()
        path.moveTo(18, 16)
        path.lineTo(23, 19)
        path.lineTo(18, 22)
        painter.drawPath(path)
    elif name == "outdent":
        painter.drawLine(QPointF(6, 9), QPointF(26, 9))
        painter.drawLine(QPointF(6, 15), QPointF(26, 15))
        painter.drawLine(QPointF(6, 21), QPointF(26, 21))
        painter.drawLine(QPointF(6, 27), QPointF(26, 27))
        _pen(painter, accent, 2.2)
        path = QPainterPath()
        path.moveTo(23, 16)
        path.lineTo(18, 19)
        path.lineTo(23, 22)
        painter.drawPath(path)
    elif name == "copy":
        painter.drawRoundedRect(QRectF(5, 9, 15, 18), 2, 2)
        painter.drawRoundedRect(QRectF(12, 4, 15, 18), 2, 2)
    elif name == "cut":
        painter.drawEllipse(QRectF(5, 5, 7, 7))
        painter.drawEllipse(QRectF(5, 20, 7, 7))
        painter.drawLine(QPointF(11, 8), QPointF(26, 25))
        painter.drawLine(QPointF(11, 24), QPointF(26, 7))
        painter.drawLine(QPointF(18, 16), QPointF(21, 16))
    elif name == "paste":
        painter.drawRoundedRect(QRectF(6, 7, 20, 22), 2, 2)
        painter.drawRoundedRect(QRectF(11, 3, 10, 6), 2, 2)
        painter.drawLine(QPointF(10, 14), QPointF(22, 14))
        painter.drawLine(QPointF(10, 19), QPointF(22, 19))
        painter.drawLine(QPointF(10, 24), QPointF(18, 24))
    elif name == "link":
        painter.save()
        painter.rotate(-45)
        painter.drawRoundedRect(QRectF(4, 13, 13, 7), 3.5, 3.5)
        painter.drawRoundedRect(QRectF(15, 13, 13, 7), 3.5, 3.5)
        painter.drawLine(QPointF(15, 16.5), QPointF(18, 16.5))
        painter.restore()
    elif name == "image":
        painter.drawRoundedRect(QRectF(4, 7, 24, 18), 2, 2)
        painter.drawEllipse(QRectF(9, 11, 4, 4))
        path = QPainterPath()
        path.moveTo(5, 23)
        path.lineTo(12, 16)
        path.lineTo(16, 20)
        path.lineTo(21, 14)
        path.lineTo(28, 23)
        painter.drawPath(path)
    elif name == "table":
        painter.drawRoundedRect(QRectF(5, 6, 22, 20), 2, 2)
        painter.drawLine(QPointF(5, 12), QPointF(27, 12))
        painter.drawLine(QPointF(5, 19), QPointF(27, 19))
        painter.drawLine(QPointF(14, 6), QPointF(14, 26))
        painter.drawLine(QPointF(20, 6), QPointF(20, 26))
    elif name == "rule":
        painter.drawLine(QPointF(4, 16), QPointF(28, 16))
        painter.setBrush(accent)
        painter.drawEllipse(QPointF(16, 16), 2.2, 2.2)
    elif name == "code":
        _pen(painter, fg, 1.9)
        painter.drawLine(QPointF(12, 9), QPointF(5, 16))
        painter.drawLine(QPointF(5, 16), QPointF(12, 23))
        painter.drawLine(QPointF(20, 9), QPointF(27, 16))
        painter.drawLine(QPointF(27, 16), QPointF(20, 23))
        _pen(painter, accent, 1.5)
        painter.drawLine(QPointF(18, 7), QPointF(14, 25))
    elif name == "chunk":
        painter.drawRoundedRect(QRectF(4, 6, 24, 20), 4, 4)
        font = QFont(theme.MONO_FONT)
        font.setPixelSize(15)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(accent)
        painter.drawText(QRectF(0, 5, 32, 22), Qt.AlignmentFlag.AlignCenter, "R")
        _pen(painter, fg, 1.4)
        painter.drawLine(QPointF(7, 11), QPointF(9, 11))
        painter.drawLine(QPointF(7, 11), QPointF(7, 21))
        painter.drawLine(QPointF(7, 21), QPointF(9, 21))
        painter.drawLine(QPointF(25, 11), QPointF(23, 11))
        painter.drawLine(QPointF(25, 11), QPointF(25, 21))
        painter.drawLine(QPointF(25, 21), QPointF(23, 21))
    elif name == "inline_r":
        painter.setBrush(accent)
        _pen(painter, accent, 1.5)
        painter.drawEllipse(QRectF(8, 8, 16, 16))
        font = QFont(theme.MONO_FONT)
        font.setPixelSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#1a1711"))
        painter.drawText(QRectF(8, 8, 16, 16), Qt.AlignmentFlag.AlignCenter, "R")
    elif name == "preview":
        path = QPainterPath()
        path.moveTo(3, 16)
        path.cubicTo(9, 7, 23, 7, 29, 16)
        path.cubicTo(23, 25, 9, 25, 3, 16)
        painter.drawPath(path)
        painter.setBrush(accent)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(16, 16), 3.2, 3.2)
    elif name == "frontmatter":
        painter.drawRoundedRect(QRectF(6, 4, 20, 24), 2, 2)
        painter.drawLine(QPointF(6, 10), QPointF(26, 10))
        painter.drawLine(QPointF(10, 15), QPointF(22, 15))
        painter.drawLine(QPointF(10, 19), QPointF(22, 19))
        painter.drawLine(QPointF(10, 23), QPointF(18, 23))
        _pen(painter, accent, 1.6)
        painter.drawLine(QPointF(6, 10), QPointF(26, 10))
    elif name == "rstudio":
        painter.drawRoundedRect(QRectF(3, 4, 26, 24), 5, 5)
        _pen(painter, accent, 1.6)
        painter.drawEllipse(QRectF(9, 8, 14, 14))
        font = QFont(theme.MONO_FONT)
        font.setPixelSize(12)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(fg)
        painter.drawText(QRectF(9, 8, 14, 14), Qt.AlignmentFlag.AlignCenter, "R")
    elif name == "knit":
        painter.setBrush(accent)
        _pen(painter, accent, 1.6)
        poly = QPolygonF([QPointF(11, 7), QPointF(25, 16), QPointF(11, 25)])
        painter.drawPolygon(poly)
        _pen(painter, fg, 1.2)
        painter.drawLine(QPointF(5, 16), QPointF(9, 16))
    elif name in ("find", "replace"):
        painter.drawEllipse(QRectF(6, 6, 15, 15))
        _pen(painter, accent, 2.4)
        painter.drawLine(QPointF(19, 19), QPointF(27, 27))
        if name == "replace":
            _pen(painter, fg, 1.4)
            painter.drawLine(QPointF(9, 13.5), QPointF(18, 13.5))
    elif name == "settings":
        for y, x1, x2, knob in ((9, 6, 26, 20), (16, 6, 26, 11), (23, 6, 26, 18)):
            _pen(painter, fg, 1.6)
            painter.drawLine(QPointF(x1, y), QPointF(x2, y))
            _pen(painter, accent, 1.8)
            painter.drawEllipse(QPointF(knob, y), 2.0, 2.0)
    elif name == "color":
        _text(painter, "A", fg, bold=True)
        _pen(painter, accent, 3.0)
        painter.drawLine(QPointF(7, 28), QPointF(25, 28))
    elif name == "highlight":
        painter.save()
        painter.translate(16, 15)
        painter.rotate(45)
        _pen(painter, fg, 1.5)
        painter.drawRoundedRect(QRectF(-7, -5, 14, 10), 1, 1)
        painter.setBrush(accent)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(QRectF(-7, 2, 14, 3))
        painter.restore()
        _pen(painter, accent, 2.4)
        painter.drawLine(QPointF(6, 28), QPointF(26, 28))
    elif name == "spacing":
        for y in (8, 13, 23, 28):
            painter.drawLine(QPointF(5, y), QPointF(27, y))
        _pen(painter, accent, 1.8)
        path = QPainterPath()
        path.moveTo(16, 15)
        path.lineTo(12, 19)
        path.lineTo(20, 19)
        path.closeSubpath()
        painter.drawPath(path)
        path = QPainterPath()
        path.moveTo(16, 21)
        path.lineTo(12, 17)
        path.lineTo(20, 17)
        path.closeSubpath()
        painter.drawPath(path)
    elif name == "paragraph":
        _text(painter, "¶", fg, size=22)
    elif name == "quote":
        _text(painter, "“”", fg, size=20)
    elif name == "clear":
        _text(painter, "T", fg, bold=True)
        _pen(painter, accent, 2.0)
        painter.drawLine(QPointF(8, 25), QPointF(24, 9))
        painter.drawLine(QPointF(8, 9), QPointF(24, 25))
    elif name == "close":
        _pen(painter, fg, 2.0)
        painter.drawLine(QPointF(9, 9), QPointF(23, 23))
        painter.drawLine(QPointF(23, 9), QPointF(9, 23))
    elif name == "plus":
        _pen(painter, fg, 2.0)
        painter.drawLine(QPointF(16, 7), QPointF(16, 25))
        painter.drawLine(QPointF(7, 16), QPointF(25, 16))
    elif name == "check":
        _pen(painter, accent, 2.4)
        painter.drawLine(QPointF(6, 17), QPointF(13, 24))
        painter.drawLine(QPointF(13, 24), QPointF(26, 9))
    elif name == "warning":
        _pen(painter, accent, 1.8)
        path = QPainterPath()
        path.moveTo(16, 5)
        path.lineTo(29, 27)
        path.lineTo(3, 27)
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawLine(QPointF(16, 12), QPointF(16, 20))
        painter.setBrush(fg)
        painter.drawEllipse(QPointF(16, 24), 1.1, 1.1)
    elif name == "external":
        painter.drawRoundedRect(QRectF(4, 11, 17, 17), 2, 2)
        _pen(painter, accent, 1.8)
        painter.drawLine(QPointF(15, 6), QPointF(27, 6))
        painter.drawLine(QPointF(27, 6), QPointF(27, 18))
        painter.drawLine(QPointF(27, 6), QPointF(14, 19))
    elif name == "word_count":
        _text(painter, "123", fg, bold=True, size=13)
    elif name == "chevron_down":
        _pen(painter, fg, 2.0)
        painter.drawLine(QPointF(9, 13), QPointF(16, 20))
        painter.drawLine(QPointF(16, 20), QPointF(23, 13))
    elif name == "info":
        _pen(painter, fg, 1.8)
        painter.drawEllipse(QRectF(5, 5, 22, 22))
        painter.drawLine(QPointF(16, 14), QPointF(16, 22))
        painter.setBrush(fg)
        painter.drawEllipse(QPointF(16, 10), 1.2, 1.2)
    else:
        _pen(painter, fg, 1.8)
        painter.drawRoundedRect(QRectF(6, 6, 20, 20), 3, 3)
        _text(painter, "?", fg, bold=True)


def icon(name: str, color: str = theme.TEXT, accent: str = theme.ACCENT) -> QIcon:
    key = (name, color, accent)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    result = QIcon()
    for size in (16, 20, 24, 32, 48):
        pixmap = QPixmap(size * 2, size * 2)
        pixmap.setDevicePixelRatio(2.0)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.scale(size / 32.0, size / 32.0)
        _draw_glyph(name, painter, QColor(color), QColor(accent))
        painter.end()
        result.addPixmap(pixmap, QIcon.Mode.Normal)
        disabled = QPixmap(pixmap)
        painter = QPainter(disabled)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(disabled.rect(), QColor(theme.FAINT))
        painter.end()
        result.addPixmap(disabled, QIcon.Mode.Disabled)
    _CACHE[key] = result
    return result


def logo_pixmap(size: int = 256) -> QPixmap:
    if size in _LOGO_CACHE:
        return _LOGO_CACHE[size]
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    scale = size / 256.0
    painter.scale(scale, scale)
    gradient = QLinearGradient(0, 0, 256, 256)
    gradient.setColorAt(0, QColor("#23262b"))
    gradient.setColorAt(1, QColor("#15171a"))
    painter.setBrush(gradient)
    _pen(painter, QColor("#3a3f47"), 2.0)
    painter.drawRoundedRect(QRectF(8, 8, 240, 240), 44, 44)
    font = QFont(theme.DOC_FONT)
    font.setPixelSize(142)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor(theme.TEXT))
    painter.drawText(QRectF(20, 2, 216, 208), Qt.AlignmentFlag.AlignCenter, "R")
    _pen(painter, QColor(theme.ACCENT), 10.0)
    painter.drawLine(QPointF(68, 202), QPointF(188, 202))
    font = QFont(theme.MONO_FONT)
    font.setPixelSize(30)
    painter.setFont(font)
    painter.setPen(QColor(theme.MUTED))
    painter.drawText(QRectF(20, 205, 216, 40), Qt.AlignmentFlag.AlignCenter, ".Rmd")
    painter.end()
    _LOGO_CACHE[size] = pixmap
    return pixmap


def app_icon() -> QIcon:
    result = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        result.addPixmap(logo_pixmap(size))
    return result
