"""Shared constants and QTextFormat helpers."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor, QFont, QTextBlock, QTextCharFormat, QTextFormat

DEFAULT_FAMILY = "Georgia"
DEFAULT_SIZE = 11.5
MONO_FAMILY = "Consolas"
DEFAULT_COLOR = "#f2ebdd"
PAGE_BG = "#1e2125"
CODE_BG = "#171a1e"
CODE_HEADER_BG = "#20242a"
QUOTE_BG = "#22252a"
HIGHLIGHT_COLOR = "#6b5427"

# User-property ids for R Markdown-specific constructs. QTextFormat keeps
# these through undo/redo and copy/paste inside the document.
_UP = int(QTextFormat.Property.UserProperty)
PROP_BLOCK_KIND = _UP + 1
PROP_CHUNK_ID = _UP + 2
PROP_CHUNK_HEADER = _UP + 3
PROP_RAW_MD = _UP + 4
PROP_INLINE_CODE = _UP + 5
PROP_RAW_INLINE = _UP + 6
PROP_IMAGE_ALT = _UP + 7
PROP_IMAGE_WIDTH = _UP + 8
PROP_TABLE_HEADER = _UP + 9
PROP_TABLE_ALIGN = _UP + 10
PROP_QUOTE_LEVEL = _UP + 11
PROP_LIST_LEVEL = _UP + 12
PROP_HEADING_LEVEL = _UP + 13
PROP_BLOCK_LINE_SPACING = _UP + 14
PROP_BLOCK_SPACE_BEFORE = _UP + 15
PROP_BLOCK_SPACE_AFTER = _UP + 16
PROP_TABLE_HEADER_BG = _UP + 17

# Block kinds.
KIND_PARAGRAPH = "paragraph"
KIND_HEADING = "heading"
KIND_QUOTE = "quote"
KIND_CHUNK_HEADER = "chunk_header"
KIND_CHUNK_LINE = "chunk_line"
KIND_RAW = "raw"
KIND_HR = "hr"

HEADING_SIZES = {1: 25.0, 2: 19.5, 3: 15.5, 4: 13.0, 5: 12.0, 6: 11.5}
HEADING_WEIGHTS = {1: 700, 2: 700, 3: 700, 4: 700, 5: 700, 6: 700}


@dataclass(frozen=True)
class Defaults:
    family: str = DEFAULT_FAMILY
    size: float = DEFAULT_SIZE
    color: str = DEFAULT_COLOR

    def char_format(self) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setFontFamilies([self.family])
        fmt.setFontPointSize(self.size)
        fmt.setForeground(QColor(self.color))
        return fmt


def default_char_format(defaults: Defaults | None = None) -> QTextCharFormat:
    return (defaults or Defaults()).char_format()


def code_char_format(defaults: Defaults | None = None) -> QTextCharFormat:
    d = defaults or Defaults()
    fmt = d.char_format()
    fmt.setFontFamilies([MONO_FAMILY])
    fmt.setFontPointSize(max(8.5, d.size - 1.0))
    fmt.setForeground(QColor("#e8ddc6"))
    return fmt


def block_kind(block: QTextBlock) -> str:
    value = block.blockFormat().property(PROP_BLOCK_KIND)
    if value is None:
        return KIND_PARAGRAPH
    text = str(value)
    return text or KIND_PARAGRAPH


def set_block_kind(fmt, kind: str) -> None:
    fmt.setProperty(PROP_BLOCK_KIND, kind)


def block_chunk_id(block: QTextBlock) -> str | None:
    value = block.blockFormat().property(PROP_CHUNK_ID)
    if value is None:
        return None
    text = str(value)
    return text or None


def set_block_chunk_id(fmt, chunk_id: str) -> None:
    fmt.setProperty(PROP_CHUNK_ID, chunk_id)


def is_chunk_block(block: QTextBlock) -> bool:
    return block_kind(block) in (KIND_CHUNK_HEADER, KIND_CHUNK_LINE)


def font_weight_bold(fmt: QTextCharFormat) -> bool:
    return fmt.fontWeight() >= QFont.Weight.DemiBold


def is_solid(color_brush) -> bool:
    from PySide6.QtCore import Qt

    return color_brush.style() == Qt.BrushStyle.SolidPattern


def color_name(color: QColor) -> str:
    return color.name(QColor.NameFormat.HexRgb).lower()
