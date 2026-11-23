"""The rich text editing surface."""
from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Callable
from urllib.parse import unquote

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextImageFormat,
)
from PySide6.QtWidgets import QTextEdit

from . import theme
from .model import blocks
from .model.style import (
    DEFAULT_COLOR,
    DEFAULT_FAMILY,
    DEFAULT_SIZE,
    KIND_CHUNK_HEADER,
    KIND_CHUNK_LINE,
    KIND_HEADING,
    KIND_QUOTE,
    MONO_FAMILY,
    PROP_IMAGE_ALT,
    PROP_IMAGE_WIDTH,
    Defaults,
    block_chunk_id,
    block_kind,
    default_char_format,
)

ImageHandler = Callable[[QImage | Path], tuple[str, str] | None]


class MarkdownEditor(QTextEdit):
    contextChanged = Signal()

    def __init__(self, defaults: Defaults | None = None, parent=None):
        super().__init__(parent)
        self.defaults = defaults or Defaults()
        self.image_handler: ImageHandler | None = None
        self.setObjectName("Editor")
        self.setAcceptRichText(True)
        self.setAcceptDrops(True)
        self.setPlaceholderText("Start writing. Your Markdown source follows along.")
        self.setTabChangesFocus(False)
        self.setCursorWidth(2)
        self.setWordWrapMode(self.wordWrapMode())
        self._apply_fonts()
        self.document().setDocumentMargin(44)
        self.document().setUndoRedoEnabled(True)
        self.cursorPositionChanged.connect(self.contextChanged)
        self.selectionChanged.connect(self.contextChanged)

    def _apply_fonts(self) -> None:
        font = QFont(DEFAULT_FAMILY, int(self.defaults.size))
        font.setPointSizeF(self.defaults.size)
        self.setFont(font)
        self.document().setDefaultFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance("    "))
        palette = self.palette()
        palette.setColor(palette.ColorRole.Text, QColor(self.defaults.color))
        palette.setColor(palette.ColorRole.Base, QColor(theme.PAGE))
        self.setPalette(palette)

    def reset_document(self) -> None:
        self.clear()
        self.document().setDocumentMargin(44)
        self.setCurrentCharFormat(default_char_format(self.defaults))
        self.document().clearUndoRedoStacks()
        # Ensure the very first block has sane defaults.
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        cursor.setBlockFormat(QTextBlockFormat())
        blocks.reset_paragraph(cursor, self.defaults)
        self.setTextCursor(cursor)

    def set_base_path(self, folder: Path | None) -> None:
        from PySide6.QtCore import QUrl

        self.document().setBaseUrl(QUrl.fromLocalFile(str(folder) + "/") if folder is not None else QUrl())

    # -- keyboard ---------------------------------------------------------
    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._handle_return():
                event.accept()
                return
        if key == Qt.Key.Key_Tab:
            if self._handle_tab(backwards=False):
                event.accept()
                return
        if key == Qt.Key.Key_Backtab:
            if self._handle_tab(backwards=True):
                event.accept()
                return
        super().keyPressEvent(event)

    def _handle_return(self) -> bool:
        cursor = self.textCursor()
        block = cursor.block()
        kind = block_kind(block)
        if kind in (KIND_CHUNK_HEADER, KIND_CHUNK_LINE):
            chunk_id = block_chunk_id(block)
            if not chunk_id:
                return False
            if kind == KIND_CHUNK_HEADER:
                blocks.add_chunk_line(cursor, chunk_id, self.defaults)
                self.setTextCursor(cursor)
                return True
            at_start = cursor.positionInBlock() == 0
            if at_start and block.text() == "":
                # Double Enter on an empty code line exits the chunk.
                cursor.beginEditBlock()
                fmt = QTextBlockFormat()
                cursor.setBlockFormat(fmt)
                cursor.setBlockCharFormat(default_char_format(self.defaults))
                cursor.endEditBlock()
                self.setTextCursor(cursor)
                return True
            blocks.add_chunk_line(cursor, chunk_id, self.defaults)
            self.setTextCursor(cursor)
            return True
        if block.textList() is not None and block.text() == "" and cursor.positionInBlock() == 0:
            cursor.beginEditBlock()
            lst = block.textList()
            if lst is not None:
                try:
                    lst.remove(block)
                except Exception:
                    pass
            cursor.setBlockFormat(QTextBlockFormat())
            cursor.setBlockCharFormat(default_char_format(self.defaults))
            cursor.endEditBlock()
            self.setTextCursor(cursor)
            return True
        if kind == KIND_HEADING or block.blockFormat().headingLevel() > 0:
            cursor.beginEditBlock()
            cursor.insertBlock()
            blocks.reset_paragraph(cursor, self.defaults)
            cursor.endEditBlock()
            self.setTextCursor(cursor)
            return True
        if kind == KIND_QUOTE:
            if cursor.block().text() == "" and cursor.positionInBlock() == 0:
                cursor.beginEditBlock()
                blocks.reset_paragraph(cursor, self.defaults)
                cursor.endEditBlock()
                self.setTextCursor(cursor)
                return True
        return False

    def _handle_tab(self, backwards: bool) -> bool:
        cursor = self.textCursor()
        if cursor.currentTable() is not None:
            table = cursor.currentTable()
            cell = table.cellAt(cursor)
            row = cell.row()
            column = cell.column() + (-1 if backwards else 1)
            if column < 0:
                row -= 1
                column = table.columns() - 1
            elif column >= table.columns():
                row += 1
                column = 0
            if row < 0:
                row = table.rows() - 1
            if row >= table.rows():
                row = 0
            new_cursor = table.cellAt(row, column).firstCursorPosition()
            new_cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            self.setTextCursor(new_cursor)
            return True
        if cursor.block().textList() is not None:
            blocks.change_list_indent(cursor, -1 if backwards else 1)
            return True
        if block_kind(cursor.block()) in (KIND_CHUNK_HEADER, KIND_CHUNK_LINE):
            cursor.insertText("    ")
            return True
        # A four-space indent at the start of a Markdown line would turn the
        # paragraph into a code block, so use a modest visual indent in prose.
        cursor.insertText("  " if cursor.positionInBlock() == 0 else "    ")
        return True

    @staticmethod
    def _clipboard_text() -> str:
        from PySide6.QtWidgets import QApplication

        return QApplication.clipboard().text()

    # -- paste / drop -----------------------------------------------------
    def insertFromMimeData(self, source) -> None:
        if source.hasImage() and self.image_handler is not None:
            image = source.imageData()
            if isinstance(image, QImage):
                result = self.image_handler(image)
                if result:
                    self._insert_image(result[0], result[1])
                    return
        if source.hasUrls() and self.image_handler is not None:
            urls = [url for url in source.urls() if url.isLocalFile()]
            if len(urls) == 1:
                path = Path(urls[0].toLocalFile())
                if path.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"):
                    result = self.image_handler(path)
                    if result:
                        self._insert_image(result[0], result[1])
                        return
        if source.hasHtml():
            # Word/HTML paste keeps useful character formatting, but Word's
            # exported CSS is mostly presentational noise. Drop font/colour/
            # spacing declarations while keeping semantic weight/style/spans.
            from PySide6.QtGui import QTextDocumentFragment

            html = self._clean_pasted_html(source.html())
            cursor = self.textCursor()
            cursor.beginEditBlock()
            cursor.insertFragment(QTextDocumentFragment.fromHtml(html))
            cursor.setCharFormat(cursor.block().charFormat())
            cursor.endEditBlock()
            self.setTextCursor(cursor)
            self._extract_inline_images()
            return
        super().insertFromMimeData(source)

    def _extract_inline_images(self) -> None:
        """Turn data:/file: images from pasted HTML into local assets."""
        if self.image_handler is None:
            return
        replacements: list[tuple[int, str, str]] = []
        block = self.document().begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid():
                    fmt = fragment.charFormat()
                    if fmt.isImageFormat():
                        image = fmt.toImageFormat()
                        name = image.name()
                        result = None
                        if name.startswith("data:image/"):
                            image_data = self._data_uri_image(name)
                            if image_data is not None:
                                result = self.image_handler(image_data)
                        elif name.startswith("file:///"):
                            path = Path(unquote(name[8:]))
                            if path.is_file():
                                result = self.image_handler(path)
                        if result:
                            replacements.append((fragment.position(), result[0], result[1]))
                iterator += 1
            block = block.next()
        for position, name, alt in replacements:
            fmt = QTextImageFormat()
            fmt.setName(name)
            fmt.setProperty(PROP_IMAGE_ALT, alt)
            fmt.setProperty(PROP_IMAGE_WIDTH, 80.0)
            fmt.setWidth(max(160.0, (self.viewport().width() - 100) * 0.8))
            cursor = QTextCursor(self.document())
            cursor.setPosition(position)
            cursor.setPosition(position + 1, QTextCursor.MoveMode.KeepAnchor)
            cursor.setCharFormat(fmt)

    @staticmethod
    def _data_uri_image(name: str) -> QImage | None:
        try:
            header, data = name.split(",", 1)
            if ";base64" in header:
                raw = base64.b64decode(data)
            else:
                raw = unquote(data).encode("latin-1", errors="replace")
        except Exception:
            return None
        image = QImage()
        if image.loadFromData(raw):
            return image
        return None

    @staticmethod
    def _clean_pasted_html(source: str) -> str:
        source = source.replace("\u00a0", " ")
        source = re.sub(r"(?is)<style.*?</style>", "", source)
        source = re.sub(r"(?is)<meta[^>]*>", "", source)
        source = re.sub(r"(?is)<link[^>]*>", "", source)

        keep = {"font-weight", "font-style", "text-decoration", "vertical-align", "font-variant"}

        def clean_style(match: re.Match) -> str:
            declarations = []
            for part in match.group(1).split(";"):
                if ":" not in part:
                    continue
                key, value = part.split(":", 1)
                key = key.strip().lower()
                if key in keep:
                    declarations.append(f"{key}:{value.strip()}")
            return f' style="{"; ".join(declarations)}"' if declarations else ""

        return re.sub(r'(?i)\sstyle="([^"]*)"', clean_style, source)

    def _insert_image(self, name: str, alt: str) -> None:
        cursor = self.textCursor()
        cursor.beginEditBlock()
        blocks.insert_image(cursor, name, alt, 80, max(320, self.viewport().width() - 100))
        cursor.endEditBlock()
        self.setTextCursor(cursor)

    def canInsertFromMimeData(self, source) -> bool:
        if source.hasImage() or source.hasUrls():
            return True
        return super().canInsertFromMimeData(source)

    def dropEvent(self, event) -> None:
        mime = event.mimeData()
        if self.image_handler is not None:
            if mime.hasImage():
                image = mime.imageData()
                if isinstance(image, QImage):
                    result = self.image_handler(image)
                    if result:
                        self._insert_image(result[0], result[1])
                        event.acceptProposedAction()
                        return
            if mime.hasUrls():
                local = [url for url in mime.urls() if url.isLocalFile()]
                if len(local) == 1:
                    path = Path(local[0].toLocalFile())
                    if path.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"):
                        result = self.image_handler(path)
                        if result:
                            self._insert_image(result[0], result[1])
                            event.acceptProposedAction()
                            return
        super().dropEvent(event)

    # -- small helpers ----------------------------------------------------
    def current_word_or_selection(self) -> str:
        cursor = self.textCursor()
        if cursor.hasSelection():
            return cursor.selectedText()
        return cursor.selectedText() or ""
