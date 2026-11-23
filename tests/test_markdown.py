from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QTextBlockFormat, QTextCursor, QTextDocument, QTextListFormat

from rmdstudio.model import blocks
from rmdstudio.model.markdown import SerializeOptions, serialize_rmd, split_front_matter
from rmdstudio.model.style import Defaults


def _doc():
    return QTextDocument()


def test_front_matter_split_join():
    text = "---\ntitle: \"Test\"\noutput: html_document\n---\n\n# Hello\n"
    yaml, body = split_front_matter(text)
    assert "title: \"Test\"" in yaml
    assert body.lstrip().startswith("# Hello")


def test_semantic_formatting(qapp):
    doc = _doc()
    cursor = QTextCursor(doc)
    blocks.apply_paragraph_style(cursor, "h1")
    cursor.insertText("Title")
    cursor.insertBlock()
    blocks.reset_paragraph(cursor)
    cursor.insertText("A ")
    blocks.toggle_bold(cursor)
    cursor.insertText("bold")
    blocks.toggle_bold(cursor)
    cursor.insertText(" and ")
    blocks.toggle_italic(cursor)
    cursor.insertText("italic")
    blocks.toggle_italic(cursor)
    cursor.insertText(" and ")
    blocks.toggle_underline(cursor)
    cursor.insertText("under")
    blocks.toggle_underline(cursor)
    cursor.insertText(" and ")
    blocks.toggle_strike(cursor)
    cursor.insertText("gone")
    blocks.toggle_strike(cursor)
    cursor.insertText(".")
    result = serialize_rmd(doc, "", SerializeOptions(preserve_visual=False, defaults=Defaults()))
    markdown = result.markdown
    assert "\n# Title\n" in "\n" + markdown
    assert "**bold**" in markdown
    assert "*italic*" in markdown
    assert "[under]{.underline}" in markdown
    assert "~~gone~~" in markdown


def test_link_and_inline_code(qapp):
    doc = _doc()
    cursor = QTextCursor(doc)
    cursor.insertText("Read ")
    blocks.insert_link(cursor, "the docs", "https://example.com/a b")
    cursor.insertText(" and ")
    blocks.insert_inline_code(cursor, "x <- 1", Defaults())
    result = serialize_rmd(doc, "", SerializeOptions(preserve_visual=False, defaults=Defaults()))
    assert "[the docs](<https://example.com/a b>)" in result.markdown
    assert "`x <- 1`" in result.markdown


def test_lists_and_indent(qapp):
    doc = _doc()
    cursor = QTextCursor(doc)
    cursor.insertText("one")
    fmt = QTextListFormat()
    fmt.setStyle(QTextListFormat.Style.ListDisc)
    fmt.setIndent(1)
    cursor.createList(fmt)
    cursor.insertBlock()
    cursor.insertText("two")
    cursor.insertBlock()
    nested = QTextListFormat()
    nested.setStyle(QTextListFormat.Style.ListDecimal)
    nested.setIndent(2)
    cursor.createList(nested)
    cursor.insertText("nested")
    result = serialize_rmd(doc, "", SerializeOptions(preserve_visual=False, defaults=Defaults()))
    assert "- one" in result.markdown
    assert "- two" in result.markdown
    assert "  1. nested" in result.markdown


def test_chunk_and_hr(qapp):
    doc = _doc()
    cursor = QTextCursor(doc)
    blocks.insert_chunk(cursor, "{r setup, echo=FALSE}", "x <- 1\ny <- 2", Defaults())
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertBlock()
    cursor.setBlockFormat(QTextBlockFormat())
    blocks.insert_hr(cursor, Defaults())
    result = serialize_rmd(doc, "", SerializeOptions(preserve_visual=False, defaults=Defaults()))
    assert "```{r setup, echo=FALSE}" in result.markdown
    assert "x <- 1\ny <- 2" in result.markdown
    assert "---" in result.markdown


def test_table(qapp):
    doc = _doc()
    cursor = QTextCursor(doc)
    table = blocks.create_table(cursor, 2, 2, True, Defaults())
    cell = table.cellAt(1, 0).firstCursorPosition()
    cell.insertText("Mean")
    cell = table.cellAt(1, 1).firstCursorPosition()
    cell.insertText("20.1")
    result = serialize_rmd(doc, "", SerializeOptions(preserve_visual=False, defaults=Defaults()))
    assert "| Column 1 | Column 2 |" in result.markdown
    assert "| Mean | 20.1 |" in result.markdown


def test_visual_styles(qapp):
    doc = _doc()
    cursor = QTextCursor(doc)
    cursor.insertText("Styled")
    cursor.select(QTextCursor.SelectionType.WordUnderCursor)
    blocks.set_font_family(cursor, "Courier New")
    blocks.set_font_size(cursor, 14)
    blocks.set_text_color(cursor, QColor("#e35b5b"))
    blocks.set_highlight(cursor, QColor("#6b5427"))
    cursor.clearSelection()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    blocks.set_alignment(cursor, Qt.AlignmentFlag.AlignHCenter)
    blocks.set_line_spacing(cursor, 1.5)
    rich = serialize_rmd(doc, "", SerializeOptions(preserve_visual=True, defaults=Defaults()))
    assert 'style="' in rich.markdown
    assert "font-size: 14pt" in rich.markdown
    assert "color: #e35b5b" in rich.markdown
    plain = serialize_rmd(doc, "", SerializeOptions(preserve_visual=False, defaults=Defaults()))
    assert "style=" not in plain.markdown
    assert ":::" not in plain.markdown


def test_escaping(qapp):
    doc = _doc()
    cursor = QTextCursor(doc)
    cursor.insertText("- not a list #tag *stars* [brackets] 1. not numbered")
    result = serialize_rmd(doc, "", SerializeOptions(preserve_visual=False, defaults=Defaults()))
    line = result.markdown.strip().splitlines()[-1]
    assert line.startswith("\\-")
    assert "#tag" in line
    assert "\\*stars\\*" in line
