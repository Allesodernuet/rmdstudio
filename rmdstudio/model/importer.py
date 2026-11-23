"""R Markdown -> QTextDocument import.

R Markdown code chunks are not Pandoc Markdown, so fenced blocks are split out
first and replaced by markers. Pandoc then parses the prose, including Pandoc
spans and fenced divs, and the markers are replaced with styled chunk blocks.
If Pandoc is unavailable the document is opened as a read-only-looking raw
block so no source is lost.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextListFormat,
    QTextTable,
    QTextTableCellFormat,
    QTextTableFormat,
)

from .. import external, theme
from . import blocks
from .style import (
    DEFAULT_COLOR,
    DEFAULT_FAMILY,
    DEFAULT_SIZE,
    HIGHLIGHT_COLOR,
    KIND_HEADING,
    KIND_QUOTE,
    MONO_FAMILY,
    PROP_BLOCK_LINE_SPACING,
    PROP_BLOCK_SPACE_AFTER,
    PROP_BLOCK_SPACE_BEFORE,
    PROP_IMAGE_ALT,
    PROP_IMAGE_WIDTH,
    PROP_INLINE_CODE,
    PROP_QUOTE_LEVEL,
    PROP_RAW_INLINE,
    PROP_TABLE_HEADER,
    QUOTE_BG,
    Defaults,
    default_char_format,
)


@dataclass
class ImportResult:
    warnings: list[str] = field(default_factory=list)
    used_pandoc: bool = True


@dataclass
class ChunkSegment:
    header: str
    code: str


@dataclass
class CodeSegment:
    raw: str


# ---------------------------------------------------------------------------
# Splitting R chunks out of the source
# ---------------------------------------------------------------------------

def _is_r_chunk(info: str) -> bool:
    info = info.strip()
    if not (info.startswith("{") and info.endswith("}")):
        return False
    inner = info[1:-1].strip()
    return bool(re.match(r"^[rR](?:\s|,|$)", inner))


def split_code_blocks(body: str) -> tuple[str, dict[str, ChunkSegment | CodeSegment]]:
    lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    prose: list[str] = []
    segments: dict[str, ChunkSegment | CodeSegment] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if not match:
            prose.append(line)
            index += 1
            continue
        fence = match.group(1)
        info = match.group(2).strip()
        char = fence[0]
        close_re = re.compile(rf"^ {{0,3}}{re.escape(char)}{{{len(fence)},}}\s*$")
        end = index + 1
        while end < len(lines) and not close_re.match(lines[end]):
            end += 1
        if end >= len(lines):
            prose.append(line)
            index += 1
            continue
        raw = "\n".join(lines[index:end + 1])
        code = "\n".join(lines[index + 1:end])
        if _is_r_chunk(info):
            segments_key = f"RmdStudioChunk{len(segments):04d}"
            segments[segments_key] = ChunkSegment(info, code)
        else:
            segments_key = f"RmdStudioChunk{len(segments):04d}"
            segments[segments_key] = CodeSegment(raw)
        while prose and prose[-1] == "":
            prose.pop()
        prose.extend(["", segments_key, ""])
        index = end + 1
    return "\n".join(prose), segments


# ---------------------------------------------------------------------------
# Importer
# ---------------------------------------------------------------------------

class RmdImporter:
    def __init__(self, document: QTextDocument, defaults: Defaults | None = None,
                 document_dir: Path | None = None):
        self.doc = document
        self.defaults = defaults or Defaults()
        self.document_dir = document_dir
        self.cursor = QTextCursor(document)
        self.fresh = True
        self.warnings: list[str] = []
        self.segments: dict[str, ChunkSegment | CodeSegment] = {}
        self._warned: set[str] = set()

    # -- warnings ---------------------------------------------------------
    def warn(self, message: str) -> None:
        if message not in self._warned:
            self._warned.add(message)
            self.warnings.append(message)

    # -- public -----------------------------------------------------------
    def import_body(self, body: str, pandoc_override: str = "") -> ImportResult:
        self.doc.clear()
        self.cursor = QTextCursor(self.doc)
        self.fresh = True
        prose, segments = split_code_blocks(body)
        self.segments = segments
        ast = external.pandoc_markdown_to_json(prose, pandoc_override)
        if ast is None:
            self.doc.clear()
            self.cursor = QTextCursor(self.doc)
            self._fallback_as_raw(body)
            self.warn(
                "Pandoc was not found, so this file was opened as raw Markdown blocks. "
                "Install RStudio/Pandoc or set the Pandoc path in Settings for visual editing."
            )
            return ImportResult(self.warnings, used_pandoc=False)
        try:
            self._insert_blocks(ast.get("blocks", []))
        except Exception as exc:
            self.doc.clear()
            self.cursor = QTextCursor(self.doc)
            self._fallback_as_raw(body)
            self.warn(f"The R Markdown importer could not parse this file: {exc}")
            return ImportResult(self.warnings, used_pandoc=False)
        self._remove_trailing_empty()
        self.cursor.movePosition(QTextCursor.MoveOperation.Start)
        return ImportResult(self.warnings, used_pandoc=True)

    def _fallback_as_raw(self, body: str) -> None:
        # Preserve the source exactly. It is displayed as one monospace raw
        # block so that saving does not silently rewrite the Markdown.
        source = body.replace("\r\n", "\n").strip("\n")
        if source:
            blocks.insert_raw_block(self.cursor, source, self.defaults)

    # -- block machinery --------------------------------------------------
    def _new_block(self, keep_list: bool = False):
        if not self.fresh:
            self.cursor.insertBlock()
        block = self.cursor.block()
        if not keep_list:
            lst = block.textList()
            if lst is not None:
                try:
                    lst.remove(block)
                except Exception:
                    pass
        fmt = QTextBlockFormat()
        self.cursor.setBlockFormat(fmt)
        self.cursor.setBlockCharFormat(default_char_format(self.defaults))
        self.fresh = False
        return block

    def _set_cursor_after(self, block) -> None:
        if block.isValid():
            self.cursor.setPosition(block.position())
            self.fresh = True

    def _after_chunk(self, chunk_id: str) -> None:
        block = self.doc.begin()
        last = None
        while block.isValid():
            fmt = block.blockFormat()
            if fmt.property(blocks.PROP_CHUNK_ID) == chunk_id:
                last = block
            block = block.next()
        if last is not None and last.next().isValid():
            self._set_cursor_after(last.next())
        else:
            self.fresh = False

    def _remove_trailing_empty(self) -> None:
        last = self.doc.lastBlock()
        if last.previous().isValid() and not last.text().strip():
            cursor = QTextCursor(self.doc)
            cursor.setPosition(last.position())
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
            cursor.removeSelectedText()

    def _marker(self, block_ast: dict) -> str | None:
        if block_ast.get("t") not in ("Para", "Plain"):
            return None
        inlines = block_ast.get("c") or []
        text = "".join(_inline_plain(inline) for inline in inlines).strip()
        return text if text in self.segments else None

    def _insert_blocks(self, block_list: list[dict], quote_level: int = 0,
                       div_style: dict[str, str] | None = None,
                       div_classes: list[str] | None = None) -> None:
        for block_ast in block_list or []:
            marker = self._marker(block_ast)
            if marker is not None:
                segment = self.segments.get(marker)
                if isinstance(segment, ChunkSegment):
                    self._new_block()
                    chunk_id = blocks.insert_chunk(self.cursor, segment.header, segment.code, self.defaults)
                    self._after_chunk(chunk_id)
                elif isinstance(segment, CodeSegment):
                    block = self._new_block()
                    blocks.insert_raw_block(self.cursor, segment.raw, self.defaults)
                    self._set_cursor_after(block.next())
                continue
            kind = block_ast.get("t")
            if kind == "Null":
                continue
            if kind in ("Para", "Plain"):
                block = self._new_block()
                if quote_level:
                    self._apply_quote(block, quote_level)
                if div_style or div_classes:
                    self._apply_div(block, div_style or {}, div_classes or [])
                self._insert_inlines(self.cursor, block_ast.get("c") or [], self.cursor.block().charFormat())
            elif kind == "Header":
                level, _attr, inlines = block_ast["c"]
                block = self._new_block()
                blocks.apply_paragraph_style(self.cursor, f"h{max(1, min(6, int(level)))}", self.defaults)
                if quote_level:
                    self._apply_quote(block, quote_level, keep_heading=True)
                if div_style or div_classes:
                    self._apply_div(block, div_style or {}, div_classes or [])
                self._insert_inlines(self.cursor, inlines, self.cursor.block().charFormat())
            elif kind == "CodeBlock":
                _attr, code = block_ast["c"]
                info = ""
                attr = block_ast["c"][0]
                if attr and attr[1]:
                    info = attr[1][0]
                fence = "`" * max(3, _longest_run(code, "`") + 1)
                raw = f"{fence}{info}\n{code}\n{fence}"
                block = self._new_block()
                blocks.insert_raw_block(self.cursor, raw, self.defaults)
                self._set_cursor_after(block.next())
            elif kind == "BlockQuote":
                self._insert_blocks(block_ast.get("c") or [], quote_level + 1, div_style, div_classes)
            elif kind == "BulletList":
                self._insert_list(block_ast.get("c") or [], ordered=False, level=max(0, quote_level - 1))
            elif kind == "OrderedList":
                list_attr, items = block_ast["c"]
                start = int(list_attr[0]) if list_attr else 1
                style = list_attr[1] if len(list_attr) > 1 else "Decimal"
                self._insert_list(items, ordered=True, level=max(0, quote_level - 1), start=start, style=style)
            elif kind == "Table":
                self._insert_table(block_ast, div_style)
            elif kind == "HorizontalRule":
                block = self._new_block()
                blocks.insert_hr(self.cursor, self.defaults)
                self._set_cursor_after(block.next())
            elif kind == "RawBlock":
                _format, text = block_ast["c"]
                block = self._new_block()
                blocks.insert_raw_block(self.cursor, text, self.defaults)
                self._set_cursor_after(block.next())
            elif kind == "Div":
                attr, inner = block_ast["c"]
                classes, style = _parse_attr(attr)
                merged = dict(div_style or {})
                merged.update(style)
                merged_classes = list(div_classes or []) + classes
                self._insert_blocks(inner, quote_level, merged, merged_classes)
            elif kind == "LineBlock":
                block = self._new_block()
                lines = block_ast.get("c") or []
                for line_index, inlines in enumerate(lines):
                    if line_index:
                        self.cursor.insertText("\u2028")
                    self._insert_inlines(self.cursor, inlines, default_char_format(self.defaults))
            elif kind == "DefinitionList":
                self._insert_definition_list(block_ast.get("c") or [])
            elif kind == "Figure":
                self._insert_figure(block_ast)
            else:
                self.warn(f"Unsupported Pandoc block '{kind}' was skipped.")
                self.cursor.insertText(f"[{kind}]")

    def _apply_quote(self, block, level: int, keep_heading: bool = False) -> None:
        fmt = QTextBlockFormat(block.blockFormat())
        fmt.setProperty(blocks.PROP_BLOCK_KIND, KIND_QUOTE)
        fmt.setProperty(PROP_QUOTE_LEVEL, level)
        fmt.setLeftMargin(18 + 14 * (level - 1))
        fmt.setRightMargin(8)
        fmt.setTopMargin(5)
        fmt.setBottomMargin(5)
        fmt.setBackground(QColor(QUOTE_BG))
        helper = QTextCursor(block.document())
        helper.setPosition(block.position())
        helper.setBlockFormat(fmt)
        char = QTextCharFormat(block.charFormat())
        if not keep_heading:
            char.setFontItalic(True)
            char.setForeground(QColor(self.defaults.color))
        self.cursor.setBlockCharFormat(char)

    def _apply_div(self, block, style: dict[str, str], classes: list[str]) -> None:
        fmt = QTextBlockFormat(block.blockFormat())
        changed = False
        for key, value in style.items():
            key = key.strip().lower()
            value = value.strip()
            if key == "text-align":
                align = {
                    "left": Qt.AlignmentFlag.AlignLeft,
                    "center": Qt.AlignmentFlag.AlignHCenter,
                    "right": Qt.AlignmentFlag.AlignRight,
                    "justify": Qt.AlignmentFlag.AlignJustify,
                }.get(value.lower())
                if align is not None:
                    fmt.setAlignment(align)
                    changed = True
            elif key == "line-height":
                num = _css_number(value)
                if num > 0:
                    fmt.setProperty(PROP_BLOCK_LINE_SPACING, float(num))
                    fmt.setLineHeight(num * 100.0, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
                    changed = True
            elif key in ("margin-top", "margin-bottom"):
                num = _css_length_pt(value)
                prop = PROP_BLOCK_SPACE_BEFORE if key == "margin-top" else PROP_BLOCK_SPACE_AFTER
                fmt.setProperty(prop, float(num))
                if key == "margin-top":
                    fmt.setTopMargin(num / 0.75)
                else:
                    fmt.setBottomMargin(num / 0.75)
                changed = True
        if "center" in classes:
            fmt.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            changed = True
        if changed:
            helper = QTextCursor(block.document())
            helper.setPosition(block.position())
            helper.setBlockFormat(fmt)
        unknown = [c for c in classes if c not in ("center", "rmd-studio", "columns", "column")]
        if unknown:
            self.warn(f"Div classes were not preserved: {', '.join(unknown)}")

    def _insert_list(self, items: list[list[dict]], ordered: bool, level: int,
                     start: int = 1, style: str = "Decimal") -> None:
        fmt = QTextListFormat()
        fmt.setIndent(level + 1)
        fmt.setStart(max(1, start))
        if ordered:
            fmt.setStyle(_qt_list_style(style))
        else:
            fmt.setStyle(QTextListFormat.Style.ListDisc)
        first_block = True
        parent_list = None
        for item in items:
            if first_block:
                self._new_block()
                parent_list = self.cursor.createList(fmt)
                first_block = False
            else:
                if not self.fresh:
                    self.cursor.insertBlock()
                block = self.cursor.block()
                self.fresh = False
                existing = block.textList()
                if parent_list is not None:
                    if existing is None:
                        parent_list.add(block)
                    elif existing != parent_list:
                        try:
                            existing.remove(block)
                        except Exception:
                            pass
                        parent_list.add(block)
                self.cursor.setBlockCharFormat(default_char_format(self.defaults))
            self.cursor.setBlockCharFormat(default_char_format(self.defaults))
            content_index = 0
            if item and item[0].get("t") in ("Para", "Plain"):
                self._insert_inlines(self.cursor, item[0].get("c") or [], default_char_format(self.defaults))
                content_index = 1
            for inner in item[content_index:]:
                kind = inner.get("t")
                if kind == "BulletList":
                    self._insert_list(inner.get("c") or [], ordered=False, level=level + 1)
                elif kind == "OrderedList":
                    attr, nested = inner["c"]
                    self._insert_list(nested, ordered=True, level=level + 1,
                                      start=int(attr[0]) if attr else 1,
                                      style=attr[1] if len(attr) > 1 else "Decimal")
                elif kind in ("Para", "Plain"):
                    self.warn("A list item with several paragraphs was flattened.")
                    self._new_block()
                    fmt_block = QTextBlockFormat(self.cursor.block().blockFormat())
                    fmt_block.setLeftMargin(22 + level * 18)
                    self.cursor.setBlockFormat(fmt_block)
                    self._insert_inlines(self.cursor, inner.get("c") or [], default_char_format(self.defaults))
                elif kind == "CodeBlock":
                    _attr, code = inner["c"]
                    raw = f"```\n{code}\n```"
                    block = self._new_block()
                    blocks.insert_raw_block(self.cursor, raw, self.defaults)
                    self._set_cursor_after(block.next())
                elif kind == "BlockQuote":
                    self._insert_blocks(inner.get("c") or [], quote_level=level + 1)
                else:
                    self.warn(f"Unsupported block inside a list: {kind}")

    # -- tables -----------------------------------------------------------
    def _insert_table(self, block_ast: dict, div_style: dict[str, str] | None) -> None:
        content = block_ast.get("c") or []
        if len(content) < 5:
            self.warn("A table could not be imported.")
            return
        head = content[3]
        bodies = content[4]
        foot = content[5] if len(content) > 5 else [None, []]
        colspecs = content[2]
        head_rows = head[1] if head else []
        body_rows: list[list] = []
        for body in bodies or []:
            body_rows.extend(body[3])
        foot_rows = foot[1] if foot and isinstance(foot, list) and len(foot) > 1 else []
        rows = list(head_rows) + list(body_rows) + list(foot_rows)
        if not rows:
            return
        columns = max(len(colspecs), max((len(row[1]) for row in rows), default=1))
        fmt = QTextTableFormat()
        fmt.setBorder(1)
        fmt.setBorderBrush(QColor(theme.BORDER))
        fmt.setCellPadding(6)
        fmt.setCellSpacing(0)
        try:
            fmt.setBorderCollapse(True)
        except Exception:
            pass
        fmt.setProperty(PROP_TABLE_HEADER, bool(head_rows))
        table = self.cursor.insertTable(len(rows), columns, fmt)
        header_bg = QTextTableCellFormat()
        header_bg.setBackground(QColor("#282b31"))
        for row_index, row in enumerate(rows):
            cells = row[1] if len(row) > 1 else []
            for col_index, cell_ast in enumerate(cells):
                if col_index >= columns:
                    break
                cell = table.cellAt(row_index, col_index)
                if row_index < len(head_rows):
                    cell.setFormat(header_bg)
                cell_cursor = cell.firstCursorPosition()
                cell_base = default_char_format(self.defaults)
                if row_index < len(head_rows):
                    cell_base.setFontWeight(QFont.Weight.Bold)
                cell_cursor.setBlockCharFormat(cell_base)
                cell_cursor.setCharFormat(cell_base)
                alignment = Qt.AlignmentFlag.AlignLeft
                if col_index < len(colspecs):
                    spec = colspecs[col_index]
                    if isinstance(spec, list) and spec:
                        spec = spec[0]
                    spec_name = spec.get("t", "AlignDefault") if isinstance(spec, dict) else str(spec)
                    alignment = _qt_alignment(spec_name)
                    if alignment != Qt.AlignmentFlag.AlignLeft:
                        bf = QTextBlockFormat(cell_cursor.blockFormat())
                        bf.setAlignment(alignment)
                        cell_cursor.setBlockFormat(bf)
                cell_blocks = cell_ast[4] if len(cell_ast) > 4 else []
                if cell_ast[2] > 1 or cell_ast[3] > 1:
                    self.warn("Merged table cells were imported without spans.")
                inlines: list[dict] = []
                for block_index, inner in enumerate(cell_blocks):
                    if block_index:
                        inlines.append({"t": "LineBreak"})
                    if inner.get("t") in ("Para", "Plain"):
                        inlines.extend(inner.get("c") or [])
                    elif inner.get("t") == "CodeBlock":
                        inlines.append({"t": "Code", "c": [["", [], []], inner["c"][1]]})
                self._insert_inlines(cell_cursor, inlines, cell_base)
        last = table.lastPosition()
        trailing = self.doc.findBlock(min(last + 1, max(0, self.doc.characterCount() - 1)))
        if trailing.isValid():
            self._set_cursor_after(trailing)
        else:
            self.fresh = False

    def _insert_definition_list(self, items: list) -> None:
        for item in items:
            term, definitions = item
            block = self._new_block()
            fmt = QTextCharFormat(default_char_format(self.defaults))
            fmt.setFontWeight(QFont.Weight.Bold)
            self._insert_inlines(self.cursor, term, fmt)
            for definition in definitions:
                for inner in definition:
                    if inner.get("t") in ("Para", "Plain"):
                        self._new_block()
                        self._insert_inlines(self.cursor, inner.get("c") or [], default_char_format(self.defaults))

    def _insert_figure(self, block_ast: dict) -> None:
        content = block_ast.get("c") or []
        if len(content) < 3:
            return
        _attr, caption, inner_blocks = content
        self._insert_blocks(inner_blocks)

    # -- inlines ----------------------------------------------------------
    def _insert_inlines(self, cursor: QTextCursor, inlines: list[dict], fmt: QTextCharFormat) -> None:
        for inline in inlines or []:
            kind = inline.get("t")
            if kind == "Str":
                cursor.insertText(inline.get("c", ""), fmt)
            elif kind == "Space":
                cursor.insertText(" ", fmt)
            elif kind == "SoftBreak":
                cursor.insertText(" ", fmt)
            elif kind == "LineBreak":
                cursor.insertText("\u2028", fmt)
            elif kind == "Emph":
                child = QTextCharFormat(fmt)
                child.setFontItalic(True)
                self._insert_inlines(cursor, inline.get("c") or [], child)
            elif kind == "Strong":
                child = QTextCharFormat(fmt)
                child.setFontWeight(QFont.Weight.Bold)
                self._insert_inlines(cursor, inline.get("c") or [], child)
            elif kind == "Strikeout":
                child = QTextCharFormat(fmt)
                child.setFontStrikeOut(True)
                self._insert_inlines(cursor, inline.get("c") or [], child)
            elif kind in ("Superscript", "Subscript"):
                child = QTextCharFormat(fmt)
                child.setVerticalAlignment(
                    QTextCharFormat.VerticalAlignment.AlignSuperScript
                    if kind == "Superscript"
                    else QTextCharFormat.VerticalAlignment.AlignSubScript
                )
                self._insert_inlines(cursor, inline.get("c") or [], child)
            elif kind in ("SmallCaps", "Underline"):
                child = QTextCharFormat(fmt)
                if kind == "Underline":
                    child.setFontUnderline(True)
                else:
                    child.setFontCapitalization(QFont.Capitalization.AllSmallCaps)
                    self.warn("Small caps do not have a portable Markdown representation.")
                self._insert_inlines(cursor, inline.get("c") or [], child)
            elif kind == "Code":
                _attr, text = inline["c"]
                child = QTextCharFormat(fmt)
                child.setFontFamilies([MONO_FAMILY])
                child.setFontPointSize(max(8.5, self.defaults.size - 1.0))
                child.setForeground(QColor("#e6cda3"))
                child.setBackground(QColor("#292c31"))
                child.setProperty(PROP_INLINE_CODE, True)
                cursor.insertText(text, child)
            elif kind == "Link":
                _attr, label, target = inline["c"]
                url = target[0] if isinstance(target, list) and target else str(target)
                child = QTextCharFormat(fmt)
                child.setAnchor(True)
                child.setAnchorHref(url)
                child.setForeground(QColor(theme.BLUE))
                child.setFontUnderline(True)
                self._insert_inlines(cursor, label, child)
            elif kind == "Image":
                self._insert_image(cursor, inline, fmt)
            elif kind == "Math":
                math_type, text = inline["c"]
                source = f"$${text}$$" if math_type == "DisplayMath" else f"${text}$"
                child = QTextCharFormat(fmt)
                child.setProperty(PROP_RAW_INLINE, True)
                cursor.insertText(source.replace("\n", " "), child)
            elif kind == "RawInline":
                _format, text = inline["c"]
                child = QTextCharFormat(fmt)
                child.setProperty(PROP_RAW_INLINE, True)
                cursor.insertText(text.replace("\n", " "), child)
            elif kind == "Quoted":
                quote_type, inner = inline["c"]
                open_quote, close_quote = ("‘", "’") if quote_type == "SingleQuote" else ("“", "”")
                cursor.insertText(open_quote, fmt)
                self._insert_inlines(cursor, inner, fmt)
                cursor.insertText(close_quote, fmt)
            elif kind == "Cite":
                citations, _inner = inline["c"]
                source = _citation_source(citations)
                child = QTextCharFormat(fmt)
                child.setProperty(PROP_RAW_INLINE, True)
                cursor.insertText(source, child)
                self.warn("Citations were preserved as their Pandoc keys rather than as rendered citations.")
            elif kind == "Span":
                attr, inner = inline["c"]
                classes, styles = _parse_attr(attr)
                child = QTextCharFormat(fmt)
                for key, value in styles.items():
                    _apply_inline_css(child, key, value)
                if "underline" in classes:
                    child.setFontUnderline(True)
                if "mark" in classes:
                    child.setBackground(QColor(HIGHLIGHT_COLOR))
                if "superscript" in classes:
                    child.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignSuperScript)
                if "subscript" in classes:
                    child.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignSubScript)
                known = {"underline", "mark", "superscript", "subscript", "smallcaps", "nocase"}
                unknown = [c for c in classes if c not in known]
                if unknown:
                    self.warn(f"Span classes were not preserved: {', '.join(unknown)}")
                self._insert_inlines(cursor, inner, child)
            elif kind == "Note":
                child = QTextCharFormat(fmt)
                child.setProperty(PROP_RAW_INLINE, True)
                cursor.insertText("[^note]", child)
                self.warn("Footnote bodies are not supported yet; the reference was kept as [^note].")
            elif kind == "Underline":
                child = QTextCharFormat(fmt)
                child.setFontUnderline(True)
                self._insert_inlines(cursor, inline.get("c") or [], child)
            else:
                text = _inline_plain(inline)
                if text:
                    cursor.insertText(text, fmt)
                else:
                    self.warn(f"Unsupported inline '{kind}' was skipped.")

    def _insert_image(self, cursor: QTextCursor, inline: dict, fmt: QTextCharFormat) -> None:
        attr, alt_inlines, target = inline["c"]
        alt = _inlines_text(alt_inlines)
        url = target[0] if isinstance(target, list) and target else str(target)
        _classes, styles = _parse_attr(attr)
        width = 0.0
        width_attr = _attr_key(attr, "width")
        if width_attr:
            if width_attr.strip().endswith("%"):
                width = float(width_attr.strip()[:-1] or 0)
            else:
                pixels = _css_length_pt(width_attr) / 0.75
                width = max(0.0, min(100.0, pixels / 640.0 * 100.0))
        if "width" in styles:
            value = styles["width"].strip()
            if value.endswith("%"):
                width = float(value[:-1] or 0)
        path = None
        if url and not re.match(r"^[a-z]+://", url, re.IGNORECASE):
            path = Path(url)
            if not path.is_absolute() and self.document_dir is not None:
                path = self.document_dir / path
        elif url.startswith("file:///"):
            from urllib.parse import unquote

            path = Path(unquote(url[8:]))
        if path is not None and path.is_file():
            name = url
            if Path(url).is_absolute():
                if self.document_dir is not None:
                    try:
                        name = path.resolve().relative_to(self.document_dir.resolve()).as_posix()
                    except ValueError:
                        name = path.as_posix()
                else:
                    name = path.as_posix()
            blocks.insert_image(cursor, name, alt, width, 640)
        else:
            source = f"![{alt}]({url})"
            child = QTextCharFormat(fmt)
            child.setProperty(PROP_RAW_INLINE, True)
            cursor.insertText(source, child)
            self.warn(f"Remote or missing image preserved as Markdown: {url}")

    def _citation_source(self, citations: list[dict]) -> str:
        parts: list[str] = []
        for citation in citations or []:
            prefix = _inlines_text(citation.get("citationPrefix") or []).strip()
            suffix = _inlines_text(citation.get("citationSuffix") or []).strip()
            ident = citation.get("citationId", "")
            mode = citation.get("citationMode", {}).get("t", "")
            body = f"@{ident}"
            if mode == "SuppressAuthor":
                body = "-" + body
            if prefix:
                body = prefix + " " + body
            if suffix:
                body = body + " " + suffix
            parts.append(body)
        if len(parts) == 1 and not parts[0].startswith("-"):
            return "[" + parts[0] + "]"
        return "[" + "; ".join(parts) + "]"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def import_body(
    document: QTextDocument,
    body: str,
    defaults: Defaults | None = None,
    document_dir: Path | None = None,
    pandoc_override: str = "",
) -> ImportResult:
    return RmdImporter(document, defaults, document_dir).import_body(body, pandoc_override)


def import_rmd(
    document: QTextDocument,
    text: str,
    defaults: Defaults | None = None,
    document_dir: Path | None = None,
    pandoc_override: str = "",
) -> tuple[str, ImportResult]:
    from .markdown import split_front_matter

    yaml_text, body = split_front_matter(text)
    result = import_body(document, body, defaults, document_dir, pandoc_override)
    return yaml_text, result


# ---------------------------------------------------------------------------
# Pandoc AST helpers
# ---------------------------------------------------------------------------

def _inline_plain(inline: dict) -> str:
    kind = inline.get("t")
    c = inline.get("c")
    if kind == "Str":
        return str(c)
    if kind in ("Space", "SoftBreak", "LineBreak"):
        return " "
    if kind in ("Emph", "Strong", "Strikeout", "Superscript", "Subscript", "SmallCaps", "Underline"):
        return "".join(_inline_plain(child) for child in c or [])
    if kind == "Code":
        return c[1] if isinstance(c, list) and len(c) > 1 else ""
    if kind == "Math":
        return c[1] if isinstance(c, list) and len(c) > 1 else ""
    if kind == "RawInline":
        return c[1] if isinstance(c, list) and len(c) > 1 else ""
    if kind in ("Link", "Span"):
        return "".join(_inline_plain(child) for child in (c[1] if kind == "Link" else c[1]) or [])
    if kind == "Image":
        return "".join(_inline_plain(child) for child in c[1] or [])
    if kind == "Quoted":
        return "“" + "".join(_inline_plain(child) for child in c[1] or []) + "”"
    if kind == "Cite":
        return "".join(_inline_plain(child) for child in c[1] or [])
    return ""


def _inlines_text(inlines: list[dict]) -> str:
    return "".join(_inline_plain(inline) for inline in inlines or [])


def _parse_attr(attr) -> tuple[list[str], dict[str, str]]:
    if not attr or not isinstance(attr, (list, tuple)):
        return [], {}
    classes = list(attr[1]) if len(attr) > 1 else []
    styles: dict[str, str] = {}
    if len(attr) > 2:
        for pair in attr[2]:
            if len(pair) >= 2 and pair[0] == "style":
                for part in pair[1].split(";"):
                    if ":" in part:
                        key, value = part.split(":", 1)
                        styles[key.strip()] = value.strip()
    return classes, styles


def _attr_key(attr, key: str) -> str | None:
    if len(attr) > 2:
        for pair in attr[2]:
            if len(pair) >= 2 and pair[0] == key:
                return pair[1]
    return None


def _apply_inline_css(fmt: QTextCharFormat, key: str, value: str) -> None:
    key = key.strip().lower()
    value = value.strip()
    if key == "font-family":
        fmt.setFontFamilies([value.strip("'\"")])
    elif key == "font-size":
        fmt.setFontPointSize(_css_length_pt(value))
    elif key == "color":
        color = QColor(value)
        if color.isValid():
            fmt.setForeground(color)
    elif key == "background-color":
        color = QColor(value)
        if color.isValid():
            fmt.setBackground(color)
    elif key == "font-weight":
        if value.lower() in ("bold", "bolder") or (value.isdigit() and int(value) >= 600):
            fmt.setFontWeight(QFont.Weight.Bold)
    elif key == "font-style" and value.lower() == "italic":
        fmt.setFontItalic(True)
    elif key == "text-decoration" and "underline" in value.lower():
        fmt.setFontUnderline(True)
    elif key == "letter-spacing":
        fmt.setFontLetterSpacing(_css_length_pt(value))


def _css_length_pt(value: str) -> float:
    value = value.strip().lower()
    match = re.match(r"^(-?[\d.]+)\s*(pt|px|em|rem|%)?", value)
    if not match:
        return 0.0
    number = float(match.group(1))
    unit = match.group(2) or "pt"
    if unit == "px":
        return number * 0.75
    if unit in ("em", "rem"):
        return number * 11.5
    return number


def _css_number(value: str) -> float:
    match = re.match(r"^(-?[\d.]+)", value.strip())
    return float(match.group(1)) if match else 0.0


def _qt_alignment(kind: str):
    if kind == "AlignCenter":
        return Qt.AlignmentFlag.AlignHCenter
    if kind == "AlignRight":
        return Qt.AlignmentFlag.AlignRight
    if kind == "AlignLeft":
        return Qt.AlignmentFlag.AlignLeft
    return Qt.AlignmentFlag.AlignLeft


def _qt_list_style(style):
    if isinstance(style, dict):
        style = style.get("t", "Decimal")
    return {
        "LowerAlpha": QTextListFormat.Style.ListLowerAlpha,
        "UpperAlpha": QTextListFormat.Style.ListUpperAlpha,
        "LowerRoman": QTextListFormat.Style.ListLowerRoman,
        "UpperRoman": QTextListFormat.Style.ListUpperRoman,
    }.get(str(style), QTextListFormat.Style.ListDecimal)


def _longest_run(text: str, char: str) -> int:
    longest = 0
    for match in re.finditer(re.escape(char) + "+", text):
        longest = max(longest, len(match.group(0)))
    return longest
