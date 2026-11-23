"""Operations on the rich QTextDocument model."""
from __future__ import annotations

import uuid
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QTextBlock,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFormat,
    QTextImageFormat,
    QTextListFormat,
    QTextTable,
    QTextTableCellFormat,
    QTextTableFormat,
)

from .. import theme
from .style import (
    CODE_BG,
    CODE_HEADER_BG,
    DEFAULT_COLOR,
    DEFAULT_FAMILY,
    DEFAULT_SIZE,
    HIGHLIGHT_COLOR,
    KIND_CHUNK_HEADER,
    KIND_CHUNK_LINE,
    KIND_HEADING,
    KIND_HR,
    KIND_PARAGRAPH,
    KIND_QUOTE,
    KIND_RAW,
    MONO_FAMILY,
    PROP_BLOCK_KIND,
    PROP_BLOCK_LINE_SPACING,
    PROP_BLOCK_SPACE_AFTER,
    PROP_BLOCK_SPACE_BEFORE,
    PROP_CHUNK_ID,
    PROP_IMAGE_ALT,
    PROP_IMAGE_WIDTH,
    PROP_INLINE_CODE,
    PROP_LIST_LEVEL,
    PROP_QUOTE_LEVEL,
    PROP_RAW_INLINE,
    PROP_TABLE_HEADER,
    QUOTE_BG,
    Defaults,
    block_kind,
    code_char_format,
    default_char_format,
    set_block_chunk_id,
    set_block_kind,
)


def selected_blocks(cursor: QTextCursor) -> list[QTextBlock]:
    doc = cursor.document()
    start = cursor.selectionStart()
    end = cursor.selectionEnd()
    block = doc.findBlock(start)
    blocks: list[QTextBlock] = []
    if not block.isValid():
        return blocks
    while block.isValid() and block.position() <= end:
        blocks.append(block)
        block = block.next()
    if not blocks:
        blocks.append(cursor.block())
    return blocks


def _block_cursor(block: QTextBlock) -> QTextCursor:
    cursor = QTextCursor(block.document())
    cursor.setPosition(block.position())
    return cursor


def reset_paragraph(cursor: QTextCursor, defaults: Defaults | None = None) -> None:
    defaults = defaults or Defaults()
    for block in selected_blocks(cursor):
        bc = _block_cursor(block)
        fmt = QTextBlockFormat(block.blockFormat())
        fmt.setHeadingLevel(0)
        fmt.setProperty(PROP_BLOCK_KIND, KIND_PARAGRAPH)
        fmt.setLeftMargin(0)
        fmt.setRightMargin(0)
        fmt.setTopMargin(0)
        fmt.setBottomMargin(0)
        bc.setBlockFormat(fmt)
        bc.setBlockCharFormat(default_char_format(defaults))


def apply_paragraph_style(cursor: QTextCursor, style: str, defaults: Defaults | None = None) -> None:
    defaults = defaults or Defaults()
    if style == "normal":
        reset_paragraph(cursor, defaults)
        return
    for block in selected_blocks(cursor):
        bc = _block_cursor(block)
        fmt = QTextBlockFormat(block.blockFormat())
        fmt.setLeftMargin(0)
        fmt.setRightMargin(0)
        if style.startswith("h") and style[1:].isdigit():
            level = max(1, min(6, int(style[1:])))
            sizes = {1: 25.0, 2: 19.5, 3: 15.5, 4: 13.0, 5: 12.0, 6: 11.5}
            fmt.setHeadingLevel(level)
            fmt.setProperty(PROP_BLOCK_KIND, KIND_HEADING)
            fmt.setTopMargin(14 if level <= 2 else 10)
            fmt.setBottomMargin(5)
            bc.setBlockFormat(fmt)
            char = default_char_format(defaults)
            char.setFontPointSize(sizes[level])
            char.setFontWeight(QFont.Weight.Bold)
            char.setForeground(QColor("#f7efdf"))
            bc.setBlockCharFormat(char)
        elif style == "quote":
            fmt.setHeadingLevel(0)
            fmt.setProperty(PROP_BLOCK_KIND, KIND_QUOTE)
            fmt.setProperty(PROP_QUOTE_LEVEL, 1)
            fmt.setLeftMargin(20)
            fmt.setRightMargin(10)
            fmt.setTopMargin(6)
            fmt.setBottomMargin(6)
            fmt.setBackground(QColor(QUOTE_BG))
            bc.setBlockFormat(fmt)
            char = default_char_format(defaults)
            char.setFontItalic(True)
            bc.setBlockCharFormat(char)
        elif style == "code":
            # A plain fenced block is represented as a raw block elsewhere;
            # this path is only used for backwards compatibility.
            fmt.setProperty(PROP_BLOCK_KIND, KIND_PARAGRAPH)
            bc.setBlockFormat(fmt)


def set_heading(cursor: QTextCursor, level: int, defaults: Defaults | None = None) -> None:
    if level <= 0:
        reset_paragraph(cursor, defaults)
    else:
        apply_paragraph_style(cursor, f"h{level}", defaults)


def toggle_quote(cursor: QTextCursor, defaults: Defaults | None = None) -> None:
    blocks = selected_blocks(cursor)
    if blocks and all(block_kind(b) == KIND_QUOTE for b in blocks):
        reset_paragraph(cursor, defaults)
    else:
        apply_paragraph_style(cursor, "quote", defaults)


def set_line_spacing(cursor: QTextCursor, factor: float) -> None:
    for block in selected_blocks(cursor):
        fmt = QTextBlockFormat(block.blockFormat())
        if abs(factor - 1.0) < 0.001:
            fmt.setLineHeight(0, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
            fmt.clearProperty(PROP_BLOCK_LINE_SPACING)
        else:
            fmt.setLineHeight(factor * 100.0, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
            fmt.setProperty(PROP_BLOCK_LINE_SPACING, float(factor))
        _block_cursor(block).setBlockFormat(fmt)


def set_paragraph_spacing(cursor: QTextCursor, before_pt: float, after_pt: float) -> None:
    for block in selected_blocks(cursor):
        fmt = QTextBlockFormat(block.blockFormat())
        fmt.setTopMargin(before_pt / 0.75)
        fmt.setBottomMargin(after_pt / 0.75)
        if before_pt:
            fmt.setProperty(PROP_BLOCK_SPACE_BEFORE, float(before_pt))
        else:
            fmt.clearProperty(PROP_BLOCK_SPACE_BEFORE)
        if after_pt:
            fmt.setProperty(PROP_BLOCK_SPACE_AFTER, float(after_pt))
        else:
            fmt.clearProperty(PROP_BLOCK_SPACE_AFTER)
        _block_cursor(block).setBlockFormat(fmt)


def toggle_bold(cursor: QTextCursor) -> None:
    fmt = QTextCharFormat()
    current = cursor.charFormat()
    if current.fontWeight() >= QFont.Weight.DemiBold:
        fmt.setFontWeight(QFont.Weight.Normal)
    else:
        fmt.setFontWeight(QFont.Weight.Bold)
    cursor.mergeCharFormat(fmt)


def toggle_italic(cursor: QTextCursor) -> None:
    fmt = QTextCharFormat()
    fmt.setFontItalic(not cursor.charFormat().fontItalic())
    cursor.mergeCharFormat(fmt)


def toggle_underline(cursor: QTextCursor) -> None:
    fmt = QTextCharFormat()
    fmt.setFontUnderline(not cursor.charFormat().fontUnderline())
    cursor.mergeCharFormat(fmt)


def toggle_strike(cursor: QTextCursor) -> None:
    fmt = QTextCharFormat()
    fmt.setFontStrikeOut(not cursor.charFormat().fontStrikeOut())
    cursor.mergeCharFormat(fmt)


def toggle_superscript(cursor: QTextCursor) -> None:
    fmt = QTextCharFormat()
    if cursor.charFormat().verticalAlignment() == QTextCharFormat.VerticalAlignment.AlignSuperScript:
        fmt.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignNormal)
    else:
        fmt.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignSuperScript)
    cursor.mergeCharFormat(fmt)


def toggle_subscript(cursor: QTextCursor) -> None:
    fmt = QTextCharFormat()
    if cursor.charFormat().verticalAlignment() == QTextCharFormat.VerticalAlignment.AlignSubScript:
        fmt.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignNormal)
    else:
        fmt.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignSubScript)
    cursor.mergeCharFormat(fmt)


def set_text_color(cursor: QTextCursor, color: QColor) -> None:
    fmt = QTextCharFormat()
    fmt.setForeground(color)
    cursor.mergeCharFormat(fmt)


def set_highlight(cursor: QTextCursor, color: QColor | None) -> None:
    fmt = QTextCharFormat()
    if color is None:
        fmt.setBackground(Qt.BrushStyle.NoBrush)
    else:
        fmt.setBackground(color)
    cursor.mergeCharFormat(fmt)


def set_font_family(cursor: QTextCursor, family: str) -> None:
    fmt = QTextCharFormat()
    fmt.setFontFamilies([family])
    cursor.mergeCharFormat(fmt)


def set_font_size(cursor: QTextCursor, size: float) -> None:
    fmt = QTextCharFormat()
    fmt.setFontPointSize(size)
    cursor.mergeCharFormat(fmt)


def set_alignment(cursor: QTextCursor, alignment: Qt.AlignmentFlag) -> None:
    for block in selected_blocks(cursor):
        fmt = QTextBlockFormat(block.blockFormat())
        fmt.setAlignment(alignment)
        _block_cursor(block).setBlockFormat(fmt)


def toggle_list(cursor: QTextCursor, ordered: bool) -> None:
    block = cursor.block()
    existing = block.textList()
    if existing is not None:
        style = existing.format().style()
        matching = (
            ordered
            and style
            in (
                QTextListFormat.Style.ListDecimal,
                QTextListFormat.Style.ListLowerAlpha,
                QTextListFormat.Style.ListUpperAlpha,
                QTextListFormat.Style.ListLowerRoman,
                QTextListFormat.Style.ListUpperRoman,
            )
        ) or (
            not ordered
            and style
            in (
                QTextListFormat.Style.ListDisc,
                QTextListFormat.Style.ListCircle,
                QTextListFormat.Style.ListSquare,
            )
        )
        if matching:
            # Remove the selected blocks from their lists.
            for item in selected_blocks(cursor):
                lst = item.textList()
                if lst is not None:
                    try:
                        lst.remove(item)
                    except Exception:
                        pass
                fmt = QTextBlockFormat(item.blockFormat())
                fmt.setIndent(0)
                _block_cursor(item).setBlockFormat(fmt)
            return
    fmt = QTextListFormat()
    fmt.setStyle(QTextListFormat.Style.ListDecimal if ordered else QTextListFormat.Style.ListDisc)
    fmt.setIndent(1)
    cursor.createList(fmt)


def change_list_indent(cursor: QTextCursor, delta: int) -> None:
    block = cursor.block()
    lst = block.textList()
    if lst is None:
        return
    fmt = QTextListFormat(lst.format())
    fmt.setIndent(max(1, min(8, fmt.indent() + delta)))
    lst.setFormat(fmt)


def insert_inline_code(cursor: QTextCursor, text: str = "", defaults: Defaults | None = None) -> None:
    d = defaults or Defaults()
    fmt = QTextCharFormat()
    fmt.setFontFamilies([MONO_FAMILY])
    fmt.setFontPointSize(max(8.5, d.size - 1.0))
    fmt.setForeground(QColor("#e6cda3"))
    fmt.setBackground(QColor("#292c31"))
    fmt.setProperty(PROP_INLINE_CODE, True)
    if cursor.hasSelection():
        cursor.mergeCharFormat(fmt)
    else:
        cursor.insertText(text, fmt)


def clear_inline_code(cursor: QTextCursor, defaults: Defaults | None = None) -> None:
    d = defaults or Defaults()
    fmt = QTextCharFormat()
    fmt.setProperty(PROP_INLINE_CODE, False)
    fmt.setFontFamilies([d.family])
    fmt.setFontPointSize(d.size)
    fmt.setForeground(QColor(d.color))
    fmt.setBackground(Qt.BrushStyle.NoBrush)
    cursor.mergeCharFormat(fmt)


def insert_link(cursor: QTextCursor, text: str, href: str) -> None:
    fmt = QTextCharFormat()
    fmt.setAnchor(True)
    fmt.setAnchorHref(href)
    fmt.setForeground(QColor(theme.BLUE))
    fmt.setFontUnderline(True)
    had_selection = cursor.hasSelection()
    if had_selection:
        cursor.mergeCharFormat(fmt)
        end = cursor.selectionEnd()
    else:
        before = QTextCharFormat(cursor.charFormat())
        cursor.insertText(text, fmt)
        end = cursor.position()
        cursor.setCharFormat(before)
    if had_selection:
        cursor.setPosition(end)
        cursor.setCharFormat(cursor.block().charFormat())


def insert_chunk(cursor: QTextCursor, header: str, code: str = "", defaults: Defaults | None = None) -> str:
    d = defaults or Defaults()
    chunk_id = uuid.uuid4().hex
    header = header.strip()
    if not header:
        header = "{r}"
    if not header.startswith("{"):
        header = "{" + header + "}"
    # If the cursor is not at the start of an empty block, add one.
    if cursor.block().text().strip():
        cursor.insertBlock()
    block = cursor.block()
    fmt = QTextBlockFormat()
    fmt.setProperty(PROP_BLOCK_KIND, KIND_CHUNK_HEADER)
    fmt.setProperty(PROP_CHUNK_ID, chunk_id)
    fmt.setBackground(QColor(CODE_HEADER_BG))
    fmt.setLeftMargin(14)
    fmt.setRightMargin(12)
    fmt.setTopMargin(10)
    fmt.setBottomMargin(2)
    cursor.setBlockFormat(fmt)
    hdr_fmt = code_char_format(d)
    hdr_fmt.setFontPointSize(max(8.0, d.size - 2.0))
    hdr_fmt.setForeground(QColor(theme.ACCENT))
    hdr_fmt.setFontWeight(QFont.Weight.DemiBold)
    cursor.setBlockCharFormat(hdr_fmt)
    cursor.insertText(header)

    cursor.insertBlock()
    line = cursor.block()
    lfmt = QTextBlockFormat()
    lfmt.setProperty(PROP_BLOCK_KIND, KIND_CHUNK_LINE)
    lfmt.setProperty(PROP_CHUNK_ID, chunk_id)
    lfmt.setBackground(QColor(CODE_BG))
    lfmt.setLeftMargin(14)
    lfmt.setRightMargin(12)
    lfmt.setTopMargin(0)
    lfmt.setBottomMargin(0)
    cursor.setBlockFormat(lfmt)
    cursor.setBlockCharFormat(code_char_format(d))
    if code:
        cursor.insertText(code.replace("\n", "\u2028"))
    code_end = cursor.position()

    cursor.insertBlock()
    nfmt = QTextBlockFormat()
    nfmt.setBackground(Qt.BrushStyle.NoBrush)
    nfmt.setLeftMargin(0)
    nfmt.setTopMargin(8)
    cursor.setBlockFormat(nfmt)
    cursor.setBlockCharFormat(default_char_format(d))
    # Leave the caret at the end of the code line. Storing the position avoids
    # relying on a QTextBlock handle that can go stale after the extra block.
    cursor.setPosition(code_end)
    return chunk_id


def add_chunk_line(cursor: QTextCursor, chunk_id: str, defaults: Defaults | None = None) -> None:
    d = defaults or Defaults()
    cursor.insertBlock()
    block = cursor.block()
    fmt = QTextBlockFormat()
    fmt.setProperty(PROP_BLOCK_KIND, KIND_CHUNK_LINE)
    fmt.setProperty(PROP_CHUNK_ID, chunk_id)
    fmt.setBackground(QColor(CODE_BG))
    fmt.setLeftMargin(14)
    fmt.setRightMargin(12)
    fmt.setTopMargin(0)
    fmt.setBottomMargin(0)
    cursor.setBlockFormat(fmt)
    cursor.setBlockCharFormat(code_char_format(d))


def insert_hr(cursor: QTextCursor, defaults: Defaults | None = None) -> None:
    if cursor.block().text().strip():
        cursor.insertBlock()
    fmt = QTextBlockFormat()
    fmt.setProperty(PROP_BLOCK_KIND, KIND_HR)
    fmt.setAlignment(Qt.AlignmentFlag.AlignCenter)
    fmt.setTopMargin(12)
    fmt.setBottomMargin(12)
    cursor.setBlockFormat(fmt)
    char = QTextCharFormat()
    char.setForeground(QColor(theme.BORDER_STRONG))
    char.setFontPointSize(8)
    cursor.insertText("─" * 46, char)
    cursor.insertBlock()
    cursor.setBlockFormat(QTextBlockFormat())
    cursor.setBlockCharFormat(default_char_format(defaults))


def insert_raw_block(cursor: QTextCursor, raw_markdown: str, defaults: Defaults | None = None) -> None:
    d = defaults or Defaults()
    if cursor.block().text().strip():
        cursor.insertBlock()
    fmt = QTextBlockFormat()
    fmt.setProperty(PROP_BLOCK_KIND, KIND_RAW)
    fmt.setBackground(QColor(CODE_BG))
    fmt.setLeftMargin(14)
    fmt.setRightMargin(12)
    fmt.setTopMargin(8)
    fmt.setBottomMargin(8)
    cursor.setBlockFormat(fmt)
    char = code_char_format(d)
    char.setForeground(QColor("#b9b2a4"))
    cursor.setBlockCharFormat(char)
    display = raw_markdown.replace("\r\n", "\n").replace("\n", "\u2028")
    cursor.insertText(display)
    cursor.insertBlock()
    cursor.setBlockFormat(QTextBlockFormat())
    cursor.setBlockCharFormat(default_char_format(d))


def create_table(cursor: QTextCursor, rows: int, columns: int, header: bool = True,
                 defaults: Defaults | None = None) -> QTextTable:
    d = defaults or Defaults()
    fmt = QTextTableFormat()
    fmt.setBorder(1)
    fmt.setBorderBrush(QColor(theme.BORDER))
    fmt.setCellPadding(7)
    fmt.setCellSpacing(0)
    try:
        fmt.setBorderCollapse(True)
    except Exception:
        pass
    fmt.setProperty(PROP_TABLE_HEADER, header)
    table = cursor.insertTable(max(1, rows), max(1, columns), fmt)
    header_cell = QTextTableCellFormat()
    header_cell.setBackground(QColor("#282b31"))
    for col in range(table.columns()):
        cell = table.cellAt(0, col)
        cell.setFormat(header_cell)
        c = cell.firstCursorPosition()
        cf = default_char_format(d)
        cf.setFontWeight(QFont.Weight.Bold)
        cf.setForeground(QColor("#e8d9bd"))
        c.setBlockCharFormat(cf)
        c.setCharFormat(cf)
        c.insertText(f"Column {col + 1}")
    for row in range(1, table.rows()):
        for col in range(table.columns()):
            cell = table.cellAt(row, col)
            c = cell.firstCursorPosition()
            c.setCharFormat(default_char_format(d))
    first = table.cellAt(0, 0).firstCursorPosition()
    cursor.setPosition(first.position())
    cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
    return table


def table_from_cursor(cursor: QTextCursor) -> QTextTable | None:
    return cursor.currentTable()


def insert_image(cursor: QTextCursor, name: str, alt: str = "", width_percent: float = 0.0,
                 visual_width: int = 640) -> None:
    fmt = QTextImageFormat()
    fmt.setName(name)
    fmt.setProperty(PROP_IMAGE_ALT, alt)
    fmt.setProperty(PROP_IMAGE_WIDTH, float(width_percent))
    if width_percent > 0:
        fmt.setWidth(max(40.0, visual_width * width_percent / 100.0))
    cursor.insertImage(fmt)


def add_image_file(cursor: QTextCursor, path: Path, alt: str = "", width_percent: float = 0.0,
                   visual_width: int = 640) -> None:
    insert_image(cursor, path.as_posix(), alt, width_percent, visual_width)


def delete_table(cursor: QTextCursor) -> None:
    table = cursor.currentTable()
    if table is None:
        return
    start = table.firstPosition()
    end = table.lastPosition()
    c = QTextCursor(cursor.document())
    c.setPosition(start)
    c.setPosition(min(end + 1, cursor.document().characterCount() - 1), QTextCursor.MoveMode.KeepAnchor)
    c.removeSelectedText()
    c.insertBlock()
    c.setBlockCharFormat(default_char_format())
    cursor.setPosition(c.position())


def table_toggle_header(cursor: QTextCursor) -> None:
    table = cursor.currentTable()
    if table is None:
        return
    current = table.format().property(PROP_TABLE_HEADER)
    is_header = bool(current) if current is not None else True
    new_value = not is_header
    fmt = QTextTableFormat(table.format())
    fmt.setProperty(PROP_TABLE_HEADER, new_value)
    table.setFormat(fmt)
    header_cell = QTextTableCellFormat()
    if new_value:
        header_cell.setBackground(QColor("#282b31"))
    else:
        header_cell.setBackground(Qt.BrushStyle.NoBrush)
    for col in range(table.columns()):
        cell = table.cellAt(0, col)
        cell.setFormat(header_cell)
        for block in _cell_blocks(cell):
            c = _block_cursor(block)
            cf = QTextCharFormat()
            cf.setFontWeight(QFont.Weight.Bold if new_value else QFont.Weight.Normal)
            c.select(QTextCursor.SelectionType.BlockUnderCursor)
            c.mergeCharFormat(cf)


def _cell_blocks(cell):
    block = cell.firstCursorPosition().block()
    last = cell.lastCursorPosition().block()
    while block.isValid():
        yield block
        if block == last:
            break
        block = block.next()
