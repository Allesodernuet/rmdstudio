from __future__ import annotations

from PySide6.QtCore import QMimeData

from rmdstudio.editor import MarkdownEditor
from rmdstudio.model.markdown import SerializeOptions, serialize_rmd
from rmdstudio.model.style import Defaults


def test_word_html_paste_is_cleaned(qapp):
    editor = MarkdownEditor()
    editor.document().clear()
    mime = QMimeData()
    mime.setHtml(
        '<h1 style="font-family:Calibri;font-size:22pt;color:#000000">Title</h1>'
        '<p style="font-family:Calibri;font-size:11pt;line-height:1.5"><b>bold</b> '
        'and <span style="font-family:Arial;font-size:20pt;color:#ff0000">plain</span></p>'
    )
    editor.insertFromMimeData(mime)
    result = serialize_rmd(editor.document(), "", SerializeOptions(preserve_visual=True, defaults=Defaults()))
    assert "# Title" in result.markdown
    assert "**bold**" in result.markdown
    assert "font-family" not in result.markdown
    assert "color:" not in result.markdown
