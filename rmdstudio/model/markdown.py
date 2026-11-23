"""QTextDocument -> R Markdown serialization.

The serializer emits ordinary, semantic Markdown for things Markdown can
express (headings, emphasis, lists, quotes, tables, links, code). Presentational
properties that Markdown cannot express (font, size, colour, highlight, line
spacing, paragraph spacing) are emitted as Pandoc attribute spans / fenced divs
when ``preserve_visual`` is enabled. Pandoc's HTML writer understands those;
PDF and Word writers generally do not.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QTextBlock,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFormat,
    QTextImageFormat,
    QTextList,
    QTextListFormat,
    QTextTable,
)

from .style import (
    DEFAULT_COLOR,
    DEFAULT_FAMILY,
    DEFAULT_SIZE,
    KIND_CHUNK_HEADER,
    KIND_CHUNK_LINE,
    KIND_HEADING,
    KIND_HR,
    KIND_PARAGRAPH,
    KIND_QUOTE,
    KIND_RAW,
    PROP_BLOCK_KIND,
    PROP_BLOCK_LINE_SPACING,
    PROP_BLOCK_SPACE_AFTER,
    PROP_BLOCK_SPACE_BEFORE,
    PROP_CHUNK_ID,
    PROP_IMAGE_ALT,
    PROP_IMAGE_WIDTH,
    PROP_INLINE_CODE,
    PROP_QUOTE_LEVEL,
    PROP_RAW_INLINE,
    PROP_TABLE_HEADER,
    Defaults,
    block_chunk_id,
    block_kind,
)


@dataclass
class SerializeOptions:
    preserve_visual: bool = True
    defaults: Defaults = field(default_factory=Defaults)
    document_dir: Path | None = None


@dataclass
class SerializeResult:
    markdown: str
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Front matter helpers
# ---------------------------------------------------------------------------

def split_front_matter(text: str) -> tuple[str, str]:
    """Return (yaml without fences, body)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if text.startswith("\ufeff"):
        text = text[1:]
    lines = text.split("\n")
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() in ("---", "..."):
                yaml_text = "\n".join(lines[1:index])
                body = "\n".join(lines[index + 1:])
                if body.startswith("\n"):
                    body = body[1:]
                return yaml_text, body
    return "", text


def _clean_yaml(yaml_text: str) -> str:
    text = yaml_text.replace("\r\n", "\n").strip("\n")
    lines = text.split("\n")
    if lines and lines[0].strip() in ("---", "..."):
        lines = lines[1:]
    if lines and lines[-1].strip() in ("---", "..."):
        lines = lines[:-1]
    return "\n".join(lines).strip("\n")


def join_rmd(yaml_text: str, body: str) -> str:
    yaml_clean = _clean_yaml(yaml_text)
    body = body.replace("\r\n", "\n").strip("\n")
    if yaml_clean:
        return f"---\n{yaml_clean}\n---\n\n{body}\n"
    return body + ("\n" if body else "")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def serialize_rmd(
    doc: QTextDocument,
    yaml_text: str = "",
    options: SerializeOptions | None = None,
) -> SerializeResult:
    options = options or SerializeOptions()
    warnings: list[str] = []
    body = _serialize_body(doc, options, warnings)
    text = join_rmd(yaml_text, body)
    deduped: list[str] = []
    for warning in warnings:
        if warning not in deduped:
            deduped.append(warning)
    return SerializeResult(text, deduped)


# ---------------------------------------------------------------------------
# Traversal
# ---------------------------------------------------------------------------

def _iter_blocks(doc: QTextDocument) -> Iterable[QTextBlock]:
    block = doc.begin()
    while block.isValid():
        yield block
        block = block.next()


def _top_items(doc: QTextDocument) -> list[tuple[int, int, object]]:
    items: list[tuple[int, int, object]] = []
    for frame in doc.rootFrame().childFrames():
        if isinstance(frame, QTextTable):
            items.append((frame.firstPosition(), 1, frame))
    for block in _iter_blocks(doc):
        cursor = QTextCursor(doc)
        cursor.setPosition(block.position())
        if cursor.currentTable() is not None:
            continue
        items.append((block.position(), 0, block))
    items.sort(key=lambda item: (item[0], item[1]))
    return items


def _serialize_body(doc: QTextDocument, options: SerializeOptions, warnings: list[str]) -> str:
    items = _top_items(doc)
    parts: list[str] = []
    index = 0
    while index < len(items):
        _pos, kind, obj = items[index]
        if kind == 1:
            parts.append(_serialize_table(obj, options, warnings))
            index += 1
            continue
        block: QTextBlock = obj  # type: ignore[assignment]
        block_type = block_kind(block)
        if block_type in (KIND_CHUNK_HEADER, KIND_CHUNK_LINE):
            text, index = _consume_chunk(items, index, options, warnings)
            if text:
                parts.append(text)
            continue
        if block.textList() is not None:
            text, index = _consume_list(items, index, options, warnings)
            if text:
                parts.append(text)
            continue
        if block_type == KIND_QUOTE:
            text, index = _consume_quote(items, index, options, warnings)
            if text:
                parts.append(text)
            continue
        if block_type == KIND_HR:
            parts.append("---")
            index += 1
            continue
        if block_type == KIND_RAW:
            raw = block.text().replace("\u2028", "\n")
            if raw.strip():
                parts.append(raw)
            index += 1
            continue
        content = _serialize_block_content(block, options, warnings)
        if not content.strip():
            index += 1
            continue
        level = block.blockFormat().headingLevel()
        content = _protect_line_start(content)
        if level >= 1:
            content = f"{'#' * min(6, level)} {content}"
        content = _wrap_block_style(block, content, options, warnings)
        parts.append(content)
        index += 1
    body = "\n\n".join(part.strip("\n") for part in parts if part.strip())
    return body.rstrip() + ("\n" if body.strip() else "")


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------

def _consume_chunk(
    items: list[tuple[int, int, object]],
    index: int,
    options: SerializeOptions,
    warnings: list[str],
) -> tuple[str, int]:
    first = items[index][2]
    block: QTextBlock = first  # type: ignore[assignment]
    chunk_id = block_chunk_id(block)
    blocks: list[QTextBlock] = []
    j = index
    while j < len(items):
        _pos, kind, obj = items[j]
        if kind != 0:
            break
        candidate: QTextBlock = obj  # type: ignore[assignment]
        if block_chunk_id(candidate) != chunk_id:
            break
        if block_kind(candidate) not in (KIND_CHUNK_HEADER, KIND_CHUNK_LINE):
            break
        blocks.append(candidate)
        j += 1
    header = "{r}"
    code_blocks: list[QTextBlock] = []
    for candidate in blocks:
        if block_kind(candidate) == KIND_CHUNK_HEADER:
            header = candidate.text().strip() or "{r}"
        else:
            code_blocks.append(candidate)
    if not code_blocks and blocks and block_kind(blocks[0]) == KIND_CHUNK_LINE:
        code_blocks = blocks
    if not header.startswith("{"):
        header = "{" + header + "}"
    if "`" in header or "\n" in header:
        warnings.append("A code-chunk header contained a backtick or newline; it was cleaned up.")
        header = header.replace("`", "").replace("\n", " ").strip()
        if not header.startswith("{"):
            header = "{" + header + "}"
    code = "\n".join(b.text().replace("\u2028", "\n") for b in code_blocks)
    fence = "`" * max(3, _longest_backtick_run(code) + 1)
    lines = [f"{fence}{header}", code, fence]
    return "\n".join(lines), j


def _consume_list(
    items: list[tuple[int, int, object]],
    index: int,
    options: SerializeOptions,
    warnings: list[str],
) -> tuple[str, int]:
    lines: list[str] = []
    counters: dict[tuple[int, int], int] = {}
    ordered_at_level: dict[int, bool] = {}
    j = index
    while j < len(items):
        _pos, kind, obj = items[j]
        if kind != 0:
            break
        block: QTextBlock = obj  # type: ignore[assignment]
        lst: QTextList | None = block.textList()
        if lst is None or block_kind(block) in (
            KIND_CHUNK_HEADER,
            KIND_CHUNK_LINE,
            KIND_RAW,
            KIND_HR,
        ):
            break
        fmt = lst.format()
        level = max(0, fmt.indent() - 1)
        ordered = fmt.style() in (
            QTextListFormat.Style.ListDecimal,
            QTextListFormat.Style.ListLowerAlpha,
            QTextListFormat.Style.ListUpperAlpha,
            QTextListFormat.Style.ListLowerRoman,
            QTextListFormat.Style.ListUpperRoman,
        )
        if level in ordered_at_level and ordered_at_level[level] != ordered:
            if lines and lines[-1] != "":
                lines.append("")
        ordered_at_level[level] = ordered
        content = _serialize_block_content(block, options, warnings)
        content = _protect_line_start(content)
        indent = "  " * level
        if ordered:
            key = (level, id(lst))
            if key not in counters:
                try:
                    counters[key] = max(1, fmt.start()) - 1
                except Exception:
                    counters[key] = 0
            counters[key] += 1
            number = counters[key]
            marker = f"{number}. "
        else:
            marker = "- "
            if fmt.style() != QTextListFormat.Style.ListDisc:
                warnings.append("Markdown only supports one bullet style; bullets were normalised to '-'.")
        lines.append(f"{indent}{marker}{content}".rstrip())
        j += 1
    return "\n".join(lines), j


def _consume_quote(
    items: list[tuple[int, int, object]],
    index: int,
    options: SerializeOptions,
    warnings: list[str],
) -> tuple[str, int]:
    chunks: list[str] = []
    j = index
    while j < len(items):
        _pos, kind, obj = items[j]
        if kind != 0:
            break
        block: QTextBlock = obj  # type: ignore[assignment]
        if block_kind(block) != KIND_QUOTE:
            break
        level_value = block.blockFormat().property(PROP_QUOTE_LEVEL)
        try:
            level = max(1, int(level_value)) if level_value is not None else 1
        except (TypeError, ValueError):
            level = 1
        content = _serialize_block_content(block, options, warnings)
        if content.strip():
            prefix = ">" * level + " "
            chunks.append("\n".join(prefix + line for line in content.split("\n")))
        else:
            chunks.append(">" * level)
        j += 1
    return "\n>\n".join(chunks), j


def _wrap_block_style(
    block: QTextBlock,
    content: str,
    options: SerializeOptions,
    warnings: list[str],
) -> str:
    if not options.preserve_visual:
        return content
    if block_kind(block) in (KIND_RAW, KIND_HR, KIND_CHUNK_HEADER, KIND_CHUNK_LINE, KIND_QUOTE):
        return content
    if "\n\n" in content:
        return content
    fmt = block.blockFormat()
    styles: list[str] = []
    alignment = fmt.alignment()
    if alignment & Qt.AlignmentFlag.AlignHCenter:
        styles.append("text-align: center")
    elif alignment & Qt.AlignmentFlag.AlignRight:
        styles.append("text-align: right")
    elif alignment & Qt.AlignmentFlag.AlignJustify:
        styles.append("text-align: justify")
    line_value = fmt.property(PROP_BLOCK_LINE_SPACING)
    if line_value is not None:
        try:
            line = float(line_value)
            if abs(line - 1.0) > 0.001:
                styles.append(f"line-height: {line:g}")
        except (TypeError, ValueError):
            pass
    before = fmt.property(PROP_BLOCK_SPACE_BEFORE)
    after = fmt.property(PROP_BLOCK_SPACE_AFTER)
    try:
        if before is not None and float(before) > 0:
            styles.append(f"margin-top: {float(before):g}pt")
        if after is not None and float(after) > 0:
            styles.append(f"margin-bottom: {float(after):g}pt")
    except (TypeError, ValueError):
        pass
    if not styles:
        return content
    return f"::: {{style=\"{'; '.join(styles)}\"}}\n{content}\n:::"


# ---------------------------------------------------------------------------
# Inline content
# ---------------------------------------------------------------------------

def _serialize_block_content(
    block: QTextBlock,
    options: SerializeOptions,
    warnings: list[str],
) -> str:
    block_format = block.charFormat()
    pieces: list[str] = []
    iterator = block.begin()
    while not iterator.atEnd():
        fragment = iterator.fragment()
        if fragment.isValid():
            fmt = fragment.charFormat()
            text = fragment.text()
            if fmt.isImageFormat():
                image = fmt.toImageFormat()
                pieces.append(_serialize_image(image, fmt, options, warnings))
            else:
                pieces.append(_serialize_text(text, fmt, block_format, block, options, warnings))
        iterator += 1
    return "".join(pieces)


def _serialize_text(
    text: str,
    fmt: QTextCharFormat,
    block_char: QTextCharFormat,
    block: QTextBlock,
    options: SerializeOptions,
    warnings: list[str],
) -> str:
    if not text:
        return ""
    if bool(fmt.property(PROP_RAW_INLINE)):
        return text
    segments = text.split("\u2028")
    serialized = [
        _serialize_segment(segment, fmt, block_char, block, options, warnings)
        for segment in segments
    ]
    return "\\\n".join(serialized)


def _serialize_segment(
    text: str,
    fmt: QTextCharFormat,
    block_char: QTextCharFormat,
    block: QTextBlock,
    options: SerializeOptions,
    warnings: list[str],
) -> str:
    if not text:
        return ""
    lead_match = re.match(r"^\s*", text)
    lead = lead_match.group(0) if lead_match else ""
    trail_match = re.search(r"\s*$", text)
    trail = trail_match.group(0) if trail_match else ""
    core_end = len(text) - len(trail) if trail else len(text)
    core = text[len(lead):core_end]
    if not core:
        return text

    inline_code = bool(fmt.property(PROP_INLINE_CODE))
    anchor = fmt.isAnchor() and bool(fmt.anchorHref())
    href = fmt.anchorHref() if anchor else ""

    if inline_code:
        core_out = _code_span(core.replace("\n", " "))
    else:
        core_out = _escape_text(core)
        bold = fmt.fontWeight() >= QFont.Weight.DemiBold and block_char.fontWeight() < QFont.Weight.DemiBold
        italic = fmt.fontItalic() and not block_char.fontItalic()
        strike = fmt.fontStrikeOut() and not block_char.fontStrikeOut()
        underline = fmt.fontUnderline() and not block_char.fontUnderline()
        if anchor:
            underline = False
        if bold and italic:
            core_out = f"***{core_out}***"
        elif bold:
            core_out = f"**{core_out}**"
        elif italic:
            core_out = f"*{core_out}*"
        if strike:
            core_out = f"~~{core_out}~~"

        vertical = fmt.verticalAlignment()
        base_vertical = block_char.verticalAlignment()
        if vertical == QTextCharFormat.VerticalAlignment.AlignSuperScript and base_vertical != vertical:
            core_out = f"^{core_out}^"
        elif vertical == QTextCharFormat.VerticalAlignment.AlignSubScript and base_vertical != vertical:
            core_out = f"~{core_out}~"

        attrs: list[str] = []
        if underline:
            attrs.append(".underline")
        style = _presentational_style(fmt, block_char, options, anchor=anchor)
        if style:
            attrs.append(f'style="{style}"')
        if attrs:
            attr_text = " ".join(attrs)
            core_out = f"[{core_out}]{{{attr_text}}}"

    if anchor:
        core_out = f"[{core_out}]({_link_target(href)})"
    return lead + core_out + trail


def _presentational_style(
    fmt: QTextCharFormat,
    block_char: QTextCharFormat,
    options: SerializeOptions,
    anchor: bool = False,
) -> str:
    if not options.preserve_visual:
        return ""
    defaults = options.defaults
    base_families = block_char.fontFamilies() or []
    base_family = base_families[0] if base_families else defaults.family
    families = fmt.fontFamilies() or []
    family = families[0] if families else ""
    base_size = block_char.fontPointSize() or defaults.size
    size = fmt.fontPointSize()
    base_color = _solid_color(block_char.foreground())
    if base_color is None:
        base_color = QColor(defaults.color)
    color = _solid_color(fmt.foreground())
    base_background = _solid_color(block_char.background())
    background = _solid_color(fmt.background())
    styles: list[str] = []
    if family and family.lower() != base_family.lower() and family.lower() != defaults.family.lower():
        styles.append(f"font-family: '{_css_family(family)}'")
    if size > 0 and abs(size - base_size) > 0.15:
        styles.append(f"font-size: {size:g}pt")
    if not anchor and color is not None and color != base_color:
        styles.append(f"color: {_css_color(color)}")
    if background is not None and background.alpha() > 0 and background != base_background:
        styles.append(f"background-color: {_css_color(background)}")
    spacing = fmt.fontLetterSpacing()
    if abs(spacing) > 0.01:
        styles.append(f"letter-spacing: {spacing:g}pt")
    return "; ".join(styles)


def _serialize_image(
    image: QTextImageFormat,
    fmt: QTextCharFormat,
    options: SerializeOptions,
    warnings: list[str],
) -> str:
    alt_value = fmt.property(PROP_IMAGE_ALT)
    alt = str(alt_value) if alt_value is not None else ""
    alt = alt.replace("\n", " ").replace("]", "\\]")
    width_value = fmt.property(PROP_IMAGE_WIDTH)
    width = 0.0
    try:
        if width_value is not None:
            width = float(width_value)
    except (TypeError, ValueError):
        width = 0.0
    name = image.name().strip()
    if not name:
        return alt
    if name.startswith("data:"):
        warnings.append("A pasted image was stored as inline data and could not be written to a file.")
        return alt or "[image]"
    if name.startswith("file:///"):
        from urllib.parse import unquote

        name = unquote(name[8:])
    path = Path(name)
    if path.is_absolute():
        if options.document_dir is not None:
            try:
                path = path.resolve().relative_to(options.document_dir.resolve())
                name = path.as_posix()
            except ValueError:
                warnings.append(f"Image is outside the document folder: {name}")
                name = path.as_posix()
        else:
            warnings.append(f"Image uses an absolute path: {name}")
    if options.document_dir is not None and not (options.document_dir / name).exists() and not path.is_absolute():
        warnings.append(f"Image file was not found next to the document: {name}")
    target = f"<{name}>" if re.search(r"[\s()]", name) else name
    title = f'{{width={width:g}%}}' if width > 0 else ""
    return f"![{alt}]({target}){title}"


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

def _serialize_table(table: QTextTable, options: SerializeOptions, warnings: list[str]) -> str:
    rows = table.rows()
    columns = table.columns()
    if rows < 1 or columns < 1:
        return ""
    merged = False
    for row in range(rows):
        for col in range(columns):
            cell = table.cellAt(row, col)
            if cell.rowSpan() > 1 or cell.columnSpan() > 1:
                merged = True
                break
        if merged:
            break
    if merged:
        warnings.append("Merged table cells are not representable in a Markdown pipe table; spans were flattened.")
    header_value = table.format().property(PROP_TABLE_HEADER)
    has_header = True if header_value is None else bool(header_value)

    grid: list[list[str]] = []
    for row in range(rows):
        row_cells: list[str] = []
        for col in range(columns):
            cell = table.cellAt(row, col)
            covered = cell.row() != row or cell.column() != col
            if covered:
                row_cells.append("")
                continue
            content = _cell_text(cell, options, warnings)
            row_cells.append(content if content else "")
        grid.append(row_cells)

    alignments = []
    for col in range(columns):
        block = table.cellAt(0, col).firstCursorPosition().block()
        alignment = block.blockFormat().alignment()
        if alignment & Qt.AlignmentFlag.AlignHCenter:
            alignments.append("center")
        elif alignment & Qt.AlignmentFlag.AlignRight:
            alignments.append("right")
        else:
            alignments.append("left")

    def line(cells: list[str]) -> str:
        return "| " + " | ".join(cell.replace("|", "\\|").replace("\n", " ") for cell in cells) + " |"

    if has_header:
        header = grid[0]
        data = grid[1:]
    else:
        header = ["" for _ in range(columns)]
        data = grid
    separator = []
    for alignment in alignments:
        if alignment == "center":
            separator.append(":---:")
        elif alignment == "right":
            separator.append("---:")
        else:
            separator.append("---")
    lines = [line(header), "| " + " | ".join(separator) + " |"]
    lines.extend(line(row) for row in data)
    return "\n".join(lines)


def _cell_text(cell, options: SerializeOptions, warnings: list[str]) -> str:
    blocks: list[str] = []
    block = cell.firstCursorPosition().block()
    last = cell.lastCursorPosition().block()
    while block.isValid():
        blocks.append(_serialize_block_content(block, options, warnings).strip())
        if block == last:
            break
        block = block.next()
    if len(blocks) > 1:
        warnings.append("Multi-paragraph table cells were joined with spaces.")
    return " ".join(part for part in blocks if part).strip()


# ---------------------------------------------------------------------------
# Escaping and formatting helpers
# ---------------------------------------------------------------------------

_ESCAPE_CHARS = "\\`*_[]<>$~^"


def _escape_text(text: str) -> str:
    out: list[str] = []
    for char in text:
        if char in _ESCAPE_CHARS:
            out.append("\\" + char)
        else:
            out.append(char)
    return "".join(out)


def _protect_line_start(line: str) -> str:
    match = re.match(r"^(\s*)([#>])(?=\s)", line)
    if match:
        return f"{match.group(1)}\\{match.group(2)}{line[match.end():]}"
    match = re.match(r"^(\s*)([-+])(\s)", line)
    if match:
        return f"{match.group(1)}\\{match.group(2)}{match.group(3)}{line[match.end():]}"
    match = re.match(r"^(\s*)(\d+)([.)])(\s)", line)
    if match:
        return f"{match.group(1)}{match.group(2)}\\{match.group(3)}{match.group(4)}{line[match.end():]}"
    if re.match(r"^\s*(-{3,}|={3,})\s*$", line):
        return "\\" + line.lstrip()
    return line


def _code_span(text: str) -> str:
    fence = "`"
    while fence in text:
        fence += "`"
    if text.startswith("`") or text.endswith("`") or (text.startswith(" ") and text.endswith(" ")):
        return f"{fence} {text} {fence}"
    return f"{fence}{text}{fence}"


def _longest_backtick_run(text: str) -> int:
    longest = 0
    for match in re.finditer(r"`+", text):
        longest = max(longest, len(match.group(0)))
    return longest


def _link_target(href: str) -> str:
    href = href.replace("\n", "")
    if re.search(r"[\s()]", href):
        return f"<{href}>"
    return href


def _solid_color(brush: QBrush) -> QColor | None:
    if brush.style() == Qt.BrushStyle.NoBrush:
        return None
    if brush.style() == Qt.BrushStyle.SolidPattern:
        color = brush.color()
        if color.isValid():
            return color
    return None


def _css_color(color: QColor) -> str:
    if color.alpha() >= 255:
        return color.name(QColor.NameFormat.HexRgb).lower()
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alphaF():.2f})"


def _css_family(family: str) -> str:
    return family.replace("'", "").replace('"', "")
