"""Main window: ribbon, page editor, generated-Markdown pane and file sync."""
from __future__ import annotations

import html
import os
import re
import shutil
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QDir, QModelIndex, QProcess, QProcessEnvironment, QSettings, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QFont,
    QIcon,
    QKeySequence,
    QPainter,
    QPixmap,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextDocumentFragment,
    QTextListFormat,
)
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QFileSystemModel,
    QFontComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTextBrowser,
    QToolBar,
    QToolButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from . import APP_NAME, __version__, external, icons, logbook, paths, theme
from .chat_panel import AIChatPanel
from .citations import CitationDialog
from .dialogs import (
    AboutDialog,
    ChunkDialog,
    FindReplaceDialog,
    ImageDialog,
    LinkDialog,
    SettingsDialog,
    SpacingDialog,
    TableDialog,
)
from .editor import MarkdownEditor
from .model import blocks
from .model.importer import import_rmd
from .model.markdown import SerializeOptions, SerializeResult, join_rmd, serialize_rmd, split_front_matter
from .model.style import (
    DEFAULT_COLOR,
    DEFAULT_FAMILY,
    DEFAULT_SIZE,
    HIGHLIGHT_COLOR,
    KIND_HEADING,
    KIND_QUOTE,
    PROP_BLOCK_LINE_SPACING,
    PROP_BLOCK_SPACE_AFTER,
    PROP_BLOCK_SPACE_BEFORE,
    PROP_TABLE_HEADER,
    Defaults,
    block_kind,
    default_char_format,
)
from .sync import ExternalConflict, FileSync, read_text


MODE_MARKDOWN = "markdown"
MODE_RMD = "rmd"
MODE_QUARTO = "quarto"

MODE_LABELS = {
    MODE_MARKDOWN: "Markdown",
    MODE_RMD: "R Markdown",
    MODE_QUARTO: "Quarto",
}
MODE_SUFFIX = {
    MODE_MARKDOWN: ".md",
    MODE_RMD: ".Rmd",
    MODE_QUARTO: ".qmd",
}


def document_mode_for_path(path: Path | None) -> str:
    suffix = path.suffix.lower() if path is not None else ".md"
    if suffix == ".qmd":
        return MODE_QUARTO
    if suffix in (".rmd", ".rmarkdown"):
        return MODE_RMD
    return MODE_MARKDOWN


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings(str(paths.settings_path()), QSettings.Format.IniFormat)
        self.defaults = Defaults()
        self.path: Path | None = None
        self.project_root: Path | None = None
        self._mode = MODE_MARKDOWN
        self._loading = False
        self._generation = 0
        self._saved_generation = 0
        self._force_next_save = False
        self._last_saved_at: datetime | None = None
        self._last_result: SerializeResult | None = None
        self._syncing = False
        self._pandoc_warned = False
        self._knit_process: QProcess | None = None
        self._knit_progress: QProgressDialog | None = None
        self._knit_output: Path | None = None
        self._knit_canceled = False
        self._knit_started_at = 0.0
        self._latex_process: QProcess | None = None
        self._latex_progress: QProgressDialog | None = None
        self._latex_canceled = False
        self._recent_files = self._load_recent()
        self._preserve_visual = self._bool_setting("preserve_visual", False)
        self._autosave_enabled = self._bool_setting("autosave", True)
        self._autosave_ms = int(self.settings.value("autosave_ms", 800) or 800)
        self._last_warnings: list[str] = []
        self._word_timer = QTimer(self)
        self._word_timer.setSingleShot(True)
        self._word_timer.setInterval(180)
        self._word_timer.timeout.connect(self._update_word_count)
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(280)
        self._preview_timer.timeout.connect(self._refresh_preview)
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(650)
        self._render_timer.timeout.connect(self._refresh_rendered)
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.timeout.connect(lambda: self._write_to_path(silent=True))
        self._find_dialog: FindReplaceDialog | None = None

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icons.app_icon())
        self.setMinimumSize(980, 680)

        self.editor = MarkdownEditor(self.defaults, self)
        self.editor.image_handler = self._handle_image
        self.front_edit = QPlainTextEdit(self)
        self.front_edit.setObjectName("FrontMatter")
        self.front_edit.setPlaceholderText("title: \"Untitled\"\noutput: pdf_document")
        self.front_edit.setTabStopDistance(self.fontMetrics().horizontalAdvance("    "))
        self.preview = QPlainTextEdit(self)
        self.preview.setObjectName("Preview")
        self.preview.setReadOnly(True)
        self.preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.preview.setFont(QFont(theme.MONO_FONT, 9))
        self.sync = FileSync(self)
        self.sync.external_changed.connect(self._on_external_change)

        self._build_actions()
        self._build_menus()
        self._build_ui()
        self._build_status_bar()
        self._connect_document()
        self._restore_geometry()

        self._new_document(first=True)
        saved_root = self.settings.value("project_root", "", type=str) or ""
        if saved_root and Path(saved_root).is_dir():
            self._set_project_root(Path(saved_root), persist=False)
        self.side_tabs.setCurrentIndex(0)
        self.editor.setFocus()

    # ------------------------------------------------------------------
    # Settings helpers
    # ------------------------------------------------------------------
    def _bool_setting(self, key: str, default: bool) -> bool:
        value = self.settings.value(key, default)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "on")

    def _load_recent(self) -> list[str]:
        value = self.settings.value("recent_files", [])
        if isinstance(value, str):
            value = [value]
        return [str(item) for item in value or [] if item]

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _action(self, text: str, icon_name: str, shortcut: str | None = None,
                slot=None, checkable: bool = False) -> QAction:
        action = QAction(icons.icon(icon_name), text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        if slot is not None:
            action.triggered.connect(lambda _checked=False: slot())
        action.setCheckable(checkable)
        return action

    def _build_actions(self) -> None:
        self.action_new = self._action("New Markdown document", "new", "Ctrl+N", self.new_document)
        self.action_new_rmd = self._action("New R Markdown document", "new", None, self.new_rmd_document)
        self.action_new_quarto = self._action("New Quarto document", "new", "Ctrl+Alt+Q", self.new_quarto_document)
        self.action_open = self._action("Open document...", "open", "Ctrl+O", self.open_dialog)
        self.action_open_quarto = self._action("Open Quarto template...", "open", None, self.open_quarto_dialog)
        self.action_open_folder = self._action("Open project folder...", "open", "Ctrl+Shift+O", self.open_folder_dialog)
        self.action_save = self._action("Save", "save", "Ctrl+S", self._save_document)
        self.action_save_as = self._action("Save as...", "save_as", "Ctrl+Shift+S", self.save_as)
        self.action_knit = self._action("Knit to PDF", "knit", "Ctrl+Alt+K", self.knit)
        self.action_browser_preview = self._action("Rendered preview in browser", "external", None, self.preview_in_browser)
        self.action_settings = self._action("Settings...", "settings", "Ctrl+,", self.open_settings)
        self.action_exit = self._action("Exit", "close", "Ctrl+Q", self.close)

        self.action_undo = self._action("Undo", "undo", "Ctrl+Z", self.editor.undo)
        self.action_redo = self._action("Redo", "redo", "Ctrl+Y", self.editor.redo)
        self.action_cut = self._action("Cut", "cut", "Ctrl+X", self.editor.cut)
        self.action_copy = self._action("Copy", "copy", "Ctrl+C", self.editor.copy)
        self.action_paste = self._action("Paste", "paste", "Ctrl+V", self.editor.paste)
        self.action_paste_plain = self._action("Paste as plain text", "clear", "Ctrl+Shift+V", self._paste_plain)
        self.action_select_all = self._action("Select all", "word_count", "Ctrl+A", self.editor.selectAll)
        self.action_find = self._action("Find & replace", "find", "Ctrl+F", self.show_find)
        self.action_find_replace = self._action("Replace", "replace", "Ctrl+H", self.show_find)

        self.action_bold = self._action("Bold", "bold", "Ctrl+B", self.toggle_bold, checkable=True)
        self.action_italic = self._action("Italic", "italic", "Ctrl+I", self.toggle_italic, checkable=True)
        self.action_underline = self._action("Underline", "underline", "Ctrl+U", self.toggle_underline, checkable=True)
        self.action_strike = self._action("Strikethrough", "strike", "Ctrl+Shift+X", self.toggle_strike, checkable=True)
        self.action_superscript = self._action("Superscript", "superscript", "Ctrl+Shift+.", self.toggle_superscript, checkable=True)
        self.action_subscript = self._action("Subscript", "subscript", "Ctrl+Shift+,", self.toggle_subscript, checkable=True)
        self.action_clear_format = self._action("Clear formatting", "clear", "Ctrl+Shift+Space", self.clear_formatting)

        self.action_align_left = self._action("Align left", "align_left", "Ctrl+L", lambda: self.set_alignment(Qt.AlignmentFlag.AlignLeft), checkable=True)
        self.action_align_center = self._action("Align centre", "align_center", "Ctrl+E", lambda: self.set_alignment(Qt.AlignmentFlag.AlignHCenter), checkable=True)
        self.action_align_right = self._action("Align right", "align_right", "Ctrl+R", lambda: self.set_alignment(Qt.AlignmentFlag.AlignRight), checkable=True)
        self.action_align_justify = self._action("Justify", "align_justify", "Ctrl+J", lambda: self.set_alignment(Qt.AlignmentFlag.AlignJustify), checkable=True)
        self.align_group = QActionGroup(self)
        self.align_group.setExclusive(True)
        for action in (self.action_align_left, self.action_align_center, self.action_align_right, self.action_align_justify):
            self.align_group.addAction(action)

        self.action_bullets = self._action("Bullet list", "list_bullet", "Ctrl+Shift+8", lambda: self.toggle_list(False), checkable=True)
        self.action_numbers = self._action("Numbered list", "list_number", "Ctrl+Shift+7", lambda: self.toggle_list(True), checkable=True)
        self.action_indent = self._action("Increase indent", "indent", "Ctrl+]", lambda: self.change_indent(1))
        self.action_outdent = self._action("Decrease indent", "outdent", "Ctrl+[", lambda: self.change_indent(-1))
        self.action_paragraph_spacing = self._action("Paragraph spacing...", "spacing", None, self.open_spacing)
        self.action_text_color = self._action("Text colour...", "color", None, self.choose_text_color)
        self.action_highlight = self._action("Highlight colour...", "highlight", None, self.choose_highlight)
        self.action_remove_highlight = self._action("Remove highlight", "clear", None, lambda: self.apply_highlight(None))

        self.action_style_normal = self._action("Normal text", "paragraph", "Ctrl+Alt+0", lambda: self.apply_style("normal"))
        self.action_style_h1 = self._action("Heading 1", "paragraph", "Ctrl+Alt+1", lambda: self.apply_style("h1"))
        self.action_style_h2 = self._action("Heading 2", "paragraph", "Ctrl+Alt+2", lambda: self.apply_style("h2"))
        self.action_style_h3 = self._action("Heading 3", "paragraph", "Ctrl+Alt+3", lambda: self.apply_style("h3"))
        self.action_style_h4 = self._action("Heading 4", "paragraph", "Ctrl+Alt+4", lambda: self.apply_style("h4"))
        self.action_style_quote = self._action("Quote", "quote", "Ctrl+Shift+9", lambda: self.apply_style("quote"))

        self.action_link = self._action("Link...", "link", "Ctrl+K", self.insert_link)
        self.action_cite = self._action("Zotero citation...", "quote", "Ctrl+Alt+Z", self.insert_citation)
        self.action_image = self._action("Image...", "image", "Ctrl+Alt+I", self.insert_image)
        self.action_table = self._action("Table...", "table", "Ctrl+Alt+T", self.insert_table)
        self.action_hr = self._action("Horizontal rule", "rule", "Ctrl+Alt+H", self.insert_hr)
        self.action_inline_code = self._action("Inline code", "code", "Ctrl+Shift+`", self.toggle_inline_code, checkable=True)
        self.action_inline_r = self._action("Inline R expression", "inline_r", "Ctrl+Alt+R", self.insert_inline_r)
        self.action_chunk = self._action("R code chunk", "chunk", "Ctrl+Alt+C", self.insert_chunk)

        self.action_table_row_above = self._action("Insert row above", "plus", None, lambda: self.table_insert_row(False))
        self.action_table_row_below = self._action("Insert row below", "plus", None, lambda: self.table_insert_row(True))
        self.action_table_col_left = self._action("Insert column left", "plus", None, lambda: self.table_insert_column(False))
        self.action_table_col_right = self._action("Insert column right", "plus", None, lambda: self.table_insert_column(True))
        self.action_table_del_row = self._action("Delete row", "close", None, self.table_delete_row)
        self.action_table_del_col = self._action("Delete column", "close", None, self.table_delete_column)
        self.action_table_header = self._action("Toggle header row", "table", None, self.table_toggle_header)
        self.action_table_delete = self._action("Delete table", "close", None, self.table_delete)

        self.action_preview = self._action("Workspace panel", "preview", "Ctrl+Shift+P", None, checkable=True)
        self.action_preview.toggled.connect(self._toggle_preview)
        self.action_front = self._action("YAML front matter", "frontmatter", "Ctrl+Shift+M", None, checkable=True)
        self.action_front.toggled.connect(self._toggle_front)
        self.action_visual = self._action("Preserve fonts, colours and spacing (HTML)", "color", None, None, checkable=True)
        self.action_visual.setChecked(self._preserve_visual)
        self.action_visual.toggled.connect(self._set_visual_mode)

        self.action_about = self._action("About Rmd Studio", "info", None, self.show_about)
        self.action_guide = self._action("Quick guide", "info", "F1", self.show_guide)
        self.action_sample = self._action("Open Markdown sample", "new", None, self.open_demo)
        self.action_rmd_sample = self._action("Open R Markdown sample", "new", None, self.open_rmd_demo)
        self.action_quarto_sample = self._action("Open Quarto sample project", "new", None, self.open_quarto_demo)

    def _build_menus(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        file_menu.addAction(self.action_new)
        file_menu.addAction(self.action_new_rmd)
        file_menu.addAction(self.action_new_quarto)
        file_menu.addSeparator()
        file_menu.addAction(self.action_open)
        file_menu.addAction(self.action_open_quarto)
        file_menu.addAction(self.action_open_folder)
        self.recent_menu = file_menu.addMenu("Open recent")
        self._rebuild_recent_menu()
        file_menu.addSeparator()
        file_menu.addAction(self.action_save)
        file_menu.addAction(self.action_save_as)
        file_menu.addSeparator()
        file_menu.addAction(self.action_knit)
        file_menu.addAction(self.action_browser_preview)
        file_menu.addSeparator()
        file_menu.addAction(self.action_settings)
        file_menu.addAction(self.action_exit)

        edit_menu = bar.addMenu("&Edit")
        edit_menu.addAction(self.action_undo)
        edit_menu.addAction(self.action_redo)
        edit_menu.addSeparator()
        edit_menu.addAction(self.action_cut)
        edit_menu.addAction(self.action_copy)
        edit_menu.addAction(self.action_paste)
        edit_menu.addAction(self.action_paste_plain)
        edit_menu.addSeparator()
        edit_menu.addAction(self.action_select_all)
        edit_menu.addAction(self.action_find)
        edit_menu.addAction(self.action_find_replace)

        format_menu = bar.addMenu("F&ormat")
        format_menu.addAction(self.action_bold)
        format_menu.addAction(self.action_italic)
        format_menu.addAction(self.action_underline)
        format_menu.addAction(self.action_strike)
        format_menu.addAction(self.action_superscript)
        format_menu.addAction(self.action_subscript)
        format_menu.addSeparator()
        style_menu = format_menu.addMenu("Paragraph style")
        for action in (self.action_style_normal, self.action_style_h1, self.action_style_h2,
                       self.action_style_h3, self.action_style_h4, self.action_style_quote):
            style_menu.addAction(action)
        align_menu = format_menu.addMenu("Alignment")
        for action in (self.action_align_left, self.action_align_center, self.action_align_right, self.action_align_justify):
            align_menu.addAction(action)
        lists_menu = format_menu.addMenu("Lists & indent")
        lists_menu.addAction(self.action_bullets)
        lists_menu.addAction(self.action_numbers)
        lists_menu.addAction(self.action_indent)
        lists_menu.addAction(self.action_outdent)
        format_menu.addAction(self.action_paragraph_spacing)
        format_menu.addSeparator()
        format_menu.addAction(self.action_text_color)
        format_menu.addAction(self.action_highlight)
        format_menu.addAction(self.action_remove_highlight)
        format_menu.addSeparator()
        format_menu.addAction(self.action_clear_format)

        insert_menu = bar.addMenu("&Insert")
        insert_menu.addAction(self.action_link)
        insert_menu.addAction(self.action_cite)
        insert_menu.addAction(self.action_image)
        insert_menu.addAction(self.action_table)
        insert_menu.addAction(self.action_hr)
        insert_menu.addSeparator()
        insert_menu.addAction(self.action_inline_code)
        insert_menu.addAction(self.action_inline_r)
        insert_menu.addAction(self.action_chunk)

        table_menu = bar.addMenu("&Table")
        table_menu.addAction(self.action_table)
        table_menu.addSeparator()
        for action in (self.action_table_row_above, self.action_table_row_below,
                       self.action_table_col_left, self.action_table_col_right):
            table_menu.addAction(action)
        table_menu.addSeparator()
        table_menu.addAction(self.action_table_del_row)
        table_menu.addAction(self.action_table_del_col)
        table_menu.addSeparator()
        table_menu.addAction(self.action_table_header)
        table_menu.addAction(self.action_table_delete)
        self.table_menu = table_menu

        view_menu = bar.addMenu("&View")
        view_menu.addAction(self.action_preview)
        view_menu.addAction(self.action_front)
        view_menu.addSeparator()
        view_menu.addAction(self.action_visual)

        help_menu = bar.addMenu("&Help")
        help_menu.addAction(self.action_sample)
        help_menu.addAction(self.action_rmd_sample)
        help_menu.addAction(self.action_quarto_sample)
        help_menu.addSeparator()
        help_menu.addAction(self.action_guide)
        help_menu.addAction(self.action_about)

    def _build_ui(self) -> None:
        central = QWidget(self)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        ribbon = QFrame(central)
        ribbon.setObjectName("Ribbon")
        ribbon_layout = QVBoxLayout(ribbon)
        ribbon_layout.setContentsMargins(0, 0, 0, 0)
        ribbon_layout.setSpacing(0)

        top = QToolBar("Document", ribbon)
        top.setObjectName("TopBar")
        top.setMovable(False)
        top.setFloatable(False)
        top.setIconSize(QSize(19, 19))
        top.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        logo_label = QLabel(top)
        logo_label.setPixmap(icons.logo_pixmap(20))
        logo_label.setToolTip(APP_NAME)
        top.addWidget(logo_label)
        brand_label = QLabel(APP_NAME)
        brand_label.setObjectName("AppTitle")
        top.addWidget(brand_label)
        top.addSeparator()
        self.doc_title_label = QLabel("Untitled")
        self.doc_title_label.setObjectName("DocTitle")
        top.addWidget(self.doc_title_label)
        top.addSeparator()
        for action in (self.action_new, self.action_open, self.action_save):
            top.addAction(action)
        top.addSeparator()
        top.addAction(self.action_undo)
        top.addAction(self.action_redo)
        top.addSeparator()
        self.style_combo = QComboBox(top)
        for label, value in (("Normal text", "normal"), ("Heading 1", "h1"), ("Heading 2", "h2"),
                             ("Heading 3", "h3"), ("Heading 4", "h4"), ("Quote", "quote")):
            self.style_combo.addItem(label, value)
        self.style_combo.setFixedWidth(132)
        self.style_combo.setToolTip("Paragraph style")
        self.style_combo.activated.connect(lambda _index: self._style_combo_changed())
        top.addWidget(self.style_combo)
        self.font_combo = QFontComboBox(top)
        self.font_combo.setFixedWidth(142)
        self.font_combo.setToolTip("Font family (stored as an HTML style)")
        self.font_combo.currentFontChanged.connect(self._font_combo_changed)
        top.addWidget(self.font_combo)
        self.size_combo = QComboBox(top)
        self.size_combo.setEditable(True)
        self.size_combo.setFixedWidth(78)
        self.size_combo.setMinimumContentsLength(3)
        self.size_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.size_combo.setToolTip("Font size (stored as an HTML style)")
        for size in (8, 9, 10, 10.5, 11, 11.5, 12, 14, 16, 18, 20, 22, 24, 25, 28, 32, 36, 48):
            self.size_combo.addItem(f"{size:g}")
        if self.size_combo.lineEdit() is not None:
            self.size_combo.lineEdit().setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.size_combo.lineEdit().editingFinished.connect(self._size_combo_changed)
        self.size_combo.activated.connect(lambda _index: self._size_combo_changed())
        top.addWidget(self.size_combo)
        top.addSeparator()
        top.addAction(self.action_preview)
        top.addAction(self.action_front)
        spacer = QWidget(top)
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        top.addWidget(spacer)
        folder_button = QToolButton(top)
        folder_button.setDefaultAction(self.action_open_folder)
        folder_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        top.addWidget(folder_button)
        self.knit_button = QToolButton(top)
        self.knit_button.setDefaultAction(self.action_knit)
        self.knit_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        top.addWidget(self.knit_button)
        top.addAction(self.action_settings)
        ribbon_layout.addWidget(top)

        fmt = QToolBar("Formatting", ribbon)
        fmt.setObjectName("FormatBar")
        fmt.setMovable(False)
        fmt.setFloatable(False)
        fmt.setIconSize(QSize(18, 18))
        for action in (self.action_bold, self.action_italic, self.action_underline, self.action_strike,
                       self.action_superscript, self.action_subscript):
            fmt.addAction(action)
        fmt.addSeparator()
        self.color_button = self._make_color_button("color", self._text_color_menu(), "Text colour")
        fmt.addWidget(self.color_button)
        self.highlight_button = self._make_color_button("highlight", self._highlight_menu(), "Highlight colour")
        fmt.addWidget(self.highlight_button)
        fmt.addSeparator()
        for action in (self.action_align_left, self.action_align_center, self.action_align_right, self.action_align_justify):
            fmt.addAction(action)
        fmt.addSeparator()
        fmt.addAction(self.action_bullets)
        fmt.addAction(self.action_numbers)
        fmt.addAction(self.action_outdent)
        fmt.addAction(self.action_indent)
        fmt.addSeparator()
        self.line_combo = QComboBox(fmt)
        for label, value in (("Single", 1.0), ("1.15", 1.15), ("1.5", 1.5), ("Double", 2.0)):
            self.line_combo.addItem(label, value)
        self.line_combo.addItem("Custom...", None)
        self.line_combo.setFixedWidth(88)
        self.line_combo.setToolTip("Line spacing (HTML output)")
        self.line_combo.activated.connect(self._line_combo_changed)
        fmt.addWidget(self.line_combo)
        fmt.addAction(self.action_paragraph_spacing)
        fmt.addSeparator()
        fmt.addAction(self.action_link)
        fmt.addAction(self.action_cite)
        fmt.addAction(self.action_image)
        fmt.addAction(self.action_table)
        fmt.addAction(self.action_hr)
        fmt.addSeparator()
        fmt.addAction(self.action_inline_code)
        fmt.addAction(self.action_inline_r)
        fmt.addAction(self.action_chunk)
        fmt.addSeparator()
        fmt.addAction(self.action_find)
        ribbon_layout.addWidget(fmt)

        outer.addWidget(ribbon)

        self.front_panel = QFrame(central)
        self.front_panel.setObjectName("FrontMatterPanel")
        front_layout = QVBoxLayout(self.front_panel)
        front_layout.setContentsMargins(18, 10, 18, 12)
        front_layout.setSpacing(7)
        front_header = QHBoxLayout()
        label = QLabel("YAML FRONT MATTER")
        label.setObjectName("SectionLabel")
        front_header.addWidget(label)
        hint = QLabel("title, author, output, css")
        hint.setObjectName("Hint")
        front_header.addWidget(hint)
        front_header.addStretch(1)
        close_button = QToolButton(self.front_panel)
        close_button.setDefaultAction(self.action_front)
        front_header.addWidget(close_button)
        front_layout.addLayout(front_header)
        self.front_edit.setMaximumHeight(150)
        front_layout.addWidget(self.front_edit)
        self.front_panel.hide()
        outer.addWidget(self.front_panel)

        self.splitter = QSplitter(Qt.Orientation.Horizontal, central)
        self.splitter.setChildrenCollapsible(False)
        self.page = QFrame(self.splitter)
        self.page.setObjectName("PageFrame")
        page_layout = QHBoxLayout(self.page)
        page_layout.setContentsMargins(26, 18, 26, 18)
        page_layout.setSpacing(0)
        page_layout.addStretch(1)
        self.editor.setMaximumWidth(1020)
        self.editor.setMinimumWidth(420)
        shadow = QGraphicsDropShadowEffect(self.editor)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 90))
        self.editor.setGraphicsEffect(shadow)
        page_layout.addWidget(self.editor, 10)
        page_layout.addStretch(1)
        self.splitter.addWidget(self.page)

        self.preview_panel = QFrame(self.splitter)
        self.preview_panel.setObjectName("PreviewPanel")
        side_layout = QVBoxLayout(self.preview_panel)
        side_layout.setContentsMargins(12, 12, 12, 12)
        side_layout.setSpacing(8)
        side_header = QHBoxLayout()
        side_label = QLabel("WORKSPACE")
        side_label.setObjectName("SectionLabel")
        side_header.addWidget(side_label)
        side_header.addStretch(1)
        close_button = QToolButton(self.preview_panel)
        close_button.setDefaultAction(self.action_preview)
        side_header.addWidget(close_button)
        side_layout.addLayout(side_header)
        self.side_tabs = QTabWidget(self.preview_panel)
        self.side_tabs.setObjectName("WorkspaceTabs")
        self.side_tabs.addTab(self._build_files_tab(), "Files")
        self.side_tabs.addTab(self._build_log_tab(), "Work log")
        self.side_tabs.addTab(self._build_ai_tab(), "AI chat")
        self.side_tabs.addTab(self._build_preview_tab(), "Preview")
        side_layout.addWidget(self.side_tabs, 1)
        self.preview_panel.show()
        self.splitter.addWidget(self.preview_panel)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([840, 390])
        self.action_preview.blockSignals(True)
        self.action_preview.setChecked(True)
        self.action_preview.blockSignals(False)
        self.side_tabs.currentChanged.connect(self._side_tab_changed)
        outer.addWidget(self.splitter, 1)
        self.setCentralWidget(central)

    def _build_files_tab(self) -> QWidget:
        page = QWidget(self.preview_panel)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        header = QHBoxLayout()
        self.project_label = QLabel("No project folder open")
        self.project_label.setObjectName("Hint")
        self.project_label.setWordWrap(True)
        header.addWidget(self.project_label, 1)
        open_button = QToolButton(page)
        open_button.setIcon(icons.icon("open"))
        open_button.setToolTip("Open a project folder (Ctrl+Shift+O)")
        open_button.clicked.connect(self.open_folder_dialog)
        header.addWidget(open_button)
        refresh_button = QToolButton(page)
        refresh_button.setIcon(icons.icon("undo"))
        refresh_button.setToolTip("Refresh the folder tree")
        refresh_button.clicked.connect(self._refresh_file_tree)
        header.addWidget(refresh_button)
        layout.addLayout(header)
        self.file_tree = QTreeView(page)
        self.file_tree.setObjectName("FileTree")
        self.file_tree.setHeaderHidden(True)
        self.file_tree.setRootIsDecorated(True)
        self.file_tree.setUniformRowHeights(True)
        self.file_tree.setAnimated(True)
        self.file_tree.setSortingEnabled(True)
        self.file_tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.file_tree.setIndentation(14)
        self.file_model = QFileSystemModel(self)
        self.file_model.setFilter(QDir.Filter.AllEntries | QDir.Filter.NoDotAndDotDot)
        self.file_model.setRootPath("")
        self.file_tree.setModel(self.file_model)
        for column in range(1, 4):
            self.file_tree.hideColumn(column)
        self.file_tree.activated.connect(self._tree_activated)
        layout.addWidget(self.file_tree, 1)
        hint = QLabel("Double-click a .qmd, .Rmd or .md file to open it.")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return page

    def _detect_project_root(self, document: Path) -> Path:
        current = document.parent
        for _ in range(6):
            try:
                if any((current / marker).exists() for marker in ("_quarto.yml", "_quarto.yaml", ".git")):
                    return current
                if any(current.glob("*.Rproj")):
                    return current
            except OSError:
                pass
            if current.parent == current:
                break
            current = current.parent
        return document.parent

    def _set_project_root(self, folder: Path | None, persist: bool = True) -> None:
        if folder is None or not folder.is_dir():
            return
        folder = folder.resolve()
        self.project_root = folder
        self.project_label.setText(folder.name)
        self.project_label.setToolTip(str(folder))
        root_index = self.file_model.setRootPath(str(folder))
        self.file_tree.setRootIndex(root_index)
        if persist:
            self.settings.setValue("project_root", str(folder))
            self.settings.sync()
        self._select_current_in_files()
        QTimer.singleShot(180, self._select_current_in_files)
        if hasattr(self, "chat_panel"):
            self.chat_panel.refresh_settings()

    def _refresh_file_tree(self) -> None:
        if self.project_root is not None:
            self.file_model.setRootPath("")
            root_index = self.file_model.setRootPath(str(self.project_root))
            self.file_tree.setRootIndex(root_index)
            self._select_current_in_files()

    def _select_current_in_files(self) -> None:
        if self.path is None or self.project_root is None:
            return
        try:
            if not self.path.resolve().is_relative_to(self.project_root):
                return
            index = self.file_model.index(str(self.path))
            if not index.isValid():
                return
            parent = index.parent()
            while parent.isValid() and parent != self.file_tree.rootIndex():
                self.file_tree.expand(parent)
                parent = parent.parent()
            self.file_tree.setCurrentIndex(index)
            self.file_tree.scrollTo(index)
        except (OSError, ValueError):
            pass

    def _tree_activated(self, index: QModelIndex) -> None:
        path = Path(self.file_model.filePath(index))
        if path.is_dir():
            return
        suffix = path.suffix.lower()
        if suffix in (".qmd", ".rmd", ".md"):
            self.open_path(path)
        elif suffix in (".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp"):
            external.open_path(path)
        else:
            self.statusBar().showMessage(
                "The editor opens .qmd, .Rmd and .md files. Other files can stay in the tree for reference.",
                5000,
            )

    def open_folder_dialog(self) -> None:
        start = str(self.project_root or (self.path.parent if self.path else Path.home()))
        folder = QFileDialog.getExistingDirectory(self, "Open project folder", start)
        if folder:
            self._set_project_root(Path(folder))
            self.side_tabs.setCurrentIndex(0)
            self.statusBar().showMessage(f"Project folder: {folder}", 3500)

    def open_quarto_dialog(self) -> None:
        start = self.path.parent if self.path else (self.project_root or Path.home() / "Documents")
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open Quarto template", str(start),
            "Quarto documents (*.qmd);;All files (*)"
        )
        if filename:
            self.open_path(Path(filename))

    def _build_ai_tab(self) -> QWidget:
        self.chat_panel = AIChatPanel(
            self.settings,
            selection_provider=self._ai_selection,
            document_provider=lambda: self.editor.toPlainText(),
            document_path_provider=lambda: self.path,
            project_root_provider=lambda: self.project_root,
            insert_markdown=self._insert_ai_markdown,
        )
        self.chat_panel.configure_requested.connect(self.open_settings)
        return self.chat_panel

    def _ai_selection(self, _mode: str) -> str:
        text = self.editor.textCursor().selectedText()
        return text.replace("\u2029", "\n")

    def _insert_ai_markdown(self, markdown: str) -> None:
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            cursor.removeSelectedText()
        try:
            fragment = QTextDocumentFragment.fromMarkdown(markdown)
            cursor.insertFragment(fragment)
        except Exception:
            cursor.insertText(markdown)
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()

    def _build_preview_tab(self) -> QWidget:
        page = QWidget(self.preview_panel)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        header = QHBoxLayout()
        header.addStretch(1)
        copy_button = QToolButton(page)
        copy_button.setIcon(icons.icon("copy"))
        copy_button.setToolTip("Copy generated Markdown")
        copy_button.clicked.connect(self._copy_generated)
        header.addWidget(copy_button)
        layout.addLayout(header)
        self.preview_tabs = QTabWidget(page)
        self.preview_tabs.setObjectName("PreviewTabs")
        self.rendered_preview = QTextBrowser(self.preview_tabs)
        self.rendered_preview.setObjectName("RenderedPreview")
        self.rendered_preview.setOpenExternalLinks(True)
        self.rendered_preview.setOpenLinks(True)
        self.rendered_preview.setFont(QFont(theme.DOC_FONT, 11))
        self.rendered_preview.setStyleSheet(
            f"QTextBrowser {{ background: #121418; color: {theme.TEXT}; border: none; padding: 6px; }}"
        )
        self.preview_tabs.addTab(self.rendered_preview, "Rendered")
        self.preview_tabs.addTab(self.preview, "Markdown")
        layout.addWidget(self.preview_tabs, 1)
        self.preview_warning = QLabel("")
        self.preview_warning.setObjectName("Warning")
        self.preview_warning.setWordWrap(True)
        self.preview_warning.hide()
        layout.addWidget(self.preview_warning)
        preview_button = QPushButton("Open fully rendered preview")
        preview_button.clicked.connect(self.preview_in_browser)
        layout.addWidget(preview_button)
        return page

    def _build_log_tab(self) -> QWidget:
        page = QWidget(self.preview_panel)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        header = QHBoxLayout()
        self.log_path_label = QLabel("No log file selected")
        self.log_path_label.setObjectName("Hint")
        self.log_path_label.setWordWrap(True)
        header.addWidget(self.log_path_label, 1)
        choose = QToolButton(page)
        choose.setIcon(icons.icon("save"))
        choose.setToolTip("Choose the build log file")
        choose.clicked.connect(self._choose_log_path)
        header.addWidget(choose)
        reload_button = QToolButton(page)
        reload_button.setIcon(icons.icon("undo"))
        reload_button.setToolTip("Reload the log from disk")
        reload_button.clicked.connect(self._reload_log)
        header.addWidget(reload_button)
        layout.addLayout(header)
        self.log_view = QPlainTextEdit(page)
        self.log_view.setObjectName("LogView")
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("Log entries will appear here.")
        self.log_view.setFont(QFont(theme.MONO_FONT, 9))
        layout.addWidget(self.log_view, 1)
        self.log_input = QPlainTextEdit(page)
        self.log_input.setObjectName("LogInput")
        self.log_input.setPlaceholderText("Write a log entry, then click Add entry or press Ctrl+Enter.")
        self.log_input.setMaximumHeight(92)
        layout.addWidget(self.log_input)
        footer = QHBoxLayout()
        hint = QLabel("Ctrl+Enter adds entry")
        hint.setObjectName("Hint")
        footer.addWidget(hint)
        footer.addStretch(1)
        self.log_add_button = QPushButton("Add entry")
        self.log_add_button.setObjectName("Primary")
        self.log_add_button.clicked.connect(self._append_log_entry)
        footer.addWidget(self.log_add_button)
        layout.addLayout(footer)
        from PySide6.QtGui import QShortcut

        shortcut = QShortcut(QKeySequence("Ctrl+Return"), self.log_input)
        shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        shortcut.activated.connect(self._append_log_entry)
        return page

    def _side_tab_changed(self, index: int) -> None:
        if index == 3:
            self._refresh_preview()
            self._render_timer.start(0)
        else:
            self._render_timer.stop()

    def _current_log_path(self) -> Path | None:
        setting = self.settings.value("log_path", "", type=str) or ""
        return logbook.resolve_log_path(self.path, setting)

    def _update_log_path(self) -> None:
        path = self._current_log_path()
        if path is None:
            self.log_path_label.setText("Save the .Rmd or choose a log file to enable logging.")
            self.log_path_label.setToolTip("")
            self.log_input.setEnabled(False)
            self.log_add_button.setEnabled(False)
        else:
            shown = str(path)
            short = path.name
            if self.path is not None:
                try:
                    short = path.relative_to(self.path.parent).as_posix()
                except ValueError:
                    short = str(path)
                if len(short) > 46:
                    short = path.name
            self.log_path_label.setText(short)
            self.log_path_label.setToolTip(shown)
            self.log_input.setEnabled(True)
            self.log_add_button.setEnabled(True)
        self._reload_log()

    def _reload_log(self) -> None:
        path = self._current_log_path()
        text = logbook.read_log(path)
        self.log_view.setPlainText(text)
        bar = self.log_view.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _choose_log_path(self) -> None:
        current = self._current_log_path()
        start = current if current is not None else (
            (self.path.parent / "build-log.md") if self.path else paths.app_data_dir() / "build-log.md"
        )
        filename, _ = QFileDialog.getSaveFileName(
            self, "Choose the build log file", str(start),
            "Log or Markdown (*.log *.md *.txt);;All files (*)"
        )
        if not filename:
            return
        path = Path(filename)
        if not path.suffix:
            path = path.with_suffix(".md")
        self.settings.setValue("log_path", logbook.setting_value_for(path, self.path))
        self.settings.sync()
        self._update_log_path()
        self.statusBar().showMessage(f"Build log: {path}", 3500)

    def _append_log_entry(self) -> None:
        path = self._current_log_path()
        if path is None:
            QMessageBox.information(
                self, "Build log",
                "Save the .Rmd first, or choose a log file with the button in the Work log panel."
            )
            return
        text = self.log_input.toPlainText().strip()
        if not text:
            return
        try:
            logbook.append_entry(path, text)
        except OSError as exc:
            QMessageBox.critical(self, "Build log", f"Could not write the log file:\n{exc}")
            return
        self.log_input.clear()
        self._reload_log()
        self.log_input.setFocus()
        self.statusBar().showMessage(f"Logged to {path.name}", 2500)

        self.editor.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.editor.customContextMenuRequested.connect(self._show_editor_menu)

    def _build_status_bar(self) -> None:
        bar = QStatusBar(self)
        self.setStatusBar(bar)
        self.file_label = QLabel("Not saved")
        self.file_label.setMinimumWidth(160)
        bar.addWidget(self.file_label, 1)
        self.mode_label = QLabel(MODE_LABELS[MODE_MARKDOWN])
        self.mode_label.setToolTip("Document mode")
        self.mode_label.setStyleSheet(f"color: {theme.MUTED};")
        bar.addPermanentWidget(self.mode_label)
        self.sync_label = QLabel("")
        bar.addPermanentWidget(self.sync_label)
        self.word_label = QLabel("0 words")
        bar.addPermanentWidget(self.word_label)
        self.visual_label = QLabel("HTML styling" if self._preserve_visual else "PDF-clean source")
        self.visual_label.setToolTip("Presentational formatting is written as Pandoc HTML attributes")
        bar.addPermanentWidget(self.visual_label)
        self.visual_label.setStyleSheet(f"color: {theme.GOLD if self._preserve_visual else theme.MUTED};")
        bar.showMessage("Ready", 2500)

    def _connect_document(self) -> None:
        self.editor.document().contentsChanged.connect(self._on_modified)
        self.front_edit.textChanged.connect(self._on_modified)
        self.editor.contextChanged.connect(self._sync_toolbar)
        self.editor.undoAvailable.connect(self.action_undo.setEnabled)
        self.editor.redoAvailable.connect(self.action_redo.setEnabled)
        self.action_undo.setEnabled(False)
        self.action_redo.setEnabled(False)

    def _restore_geometry(self) -> None:
        geometry = self.settings.value("geometry")
        restored = False
        if geometry is not None:
            try:
                self.restoreGeometry(geometry)
                restored = True
            except Exception:
                pass
        if not restored:
            self.resize(1280, 840)
        splitter = self.settings.value("splitter")
        if splitter is not None:
            try:
                self.splitter.restoreState(splitter)
            except Exception:
                pass

    def _save_geometry(self) -> None:
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("splitter", self.splitter.saveState())
        self.settings.sync()

    # ------------------------------------------------------------------
    # Toolbar helpers
    # ------------------------------------------------------------------
    def _make_color_button(self, icon_name: str, menu: QMenu, tooltip: str) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName("ColorButton")
        button.setIcon(icons.icon(icon_name))
        button.setMenu(menu)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setToolTip(tooltip)
        return button

    def _swatch_icon(self, color: QColor) -> QIcon:
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QColor(theme.BORDER_STRONG))
        painter.setBrush(color)
        painter.drawRoundedRect(1, 1, 14, 14, 3, 3)
        painter.end()
        return QIcon(pixmap)

    def _text_color_menu(self) -> QMenu:
        menu = QMenu(self)
        colors = [
            ("Éclair", DEFAULT_COLOR),
            ("Caramel", theme.ACCENT),
            ("Blue", theme.BLUE),
            ("Rose", theme.RED),
            ("Sage", theme.GREEN),
            ("White", "#ffffff"),
            ("Ink", "#1b1d21"),
        ]
        for name, value in colors:
            action = QAction(self._swatch_icon(QColor(value)), name, self)
            action.triggered.connect(lambda _checked=False, v=value: self.apply_text_color(QColor(v)))
            menu.addAction(action)
        menu.addSeparator()
        custom = QAction("Custom colour...", self)
        custom.triggered.connect(self.choose_text_color)
        menu.addAction(custom)
        return menu

    def _highlight_menu(self) -> QMenu:
        menu = QMenu(self)
        none_action = QAction("No highlight", self)
        none_action.triggered.connect(lambda: self.apply_highlight(None))
        menu.addAction(none_action)
        menu.addSeparator()
        colors = [
            ("Gold", HIGHLIGHT_COLOR),
            ("Rose", "#623b3b"),
            ("Sage", "#355346"),
            ("Blue", "#344a63"),
            ("Violet", "#4b3a5d"),
        ]
        for name, value in colors:
            action = QAction(self._swatch_icon(QColor(value)), name, self)
            action.triggered.connect(lambda _checked=False, v=value: self.apply_highlight(QColor(v)))
            menu.addAction(action)
        menu.addSeparator()
        custom = QAction("Custom colour...", self)
        custom.triggered.connect(self.choose_highlight)
        menu.addAction(custom)
        return menu

    def _style_combo_changed(self) -> None:
        if self._syncing:
            return
        value = self.style_combo.currentData()
        if value:
            self.apply_style(str(value))

    def _font_combo_changed(self, font: QFont) -> None:
        if self._syncing:
            return
        self.apply_font_family(font.family())

    def _size_combo_changed(self) -> None:
        if self._syncing:
            return
        text = self.size_combo.currentText().strip().lower().replace("pt", "")
        try:
            size = float(text)
        except ValueError:
            return
        if 5 <= size <= 96:
            self.apply_font_size(size)

    def _line_combo_changed(self, index: int) -> None:
        if self._syncing:
            return
        value = self.line_combo.itemData(index)
        if value is None:
            self.open_spacing()
        else:
            cursor = self.editor.textCursor()
            blocks.set_line_spacing(cursor, float(value))
            self.editor.setFocus()
            self._sync_toolbar()

    def _paste_plain(self) -> None:
        self.editor.insertPlainText(QApplication.clipboard().text())
        self.editor.setFocus()

    def _sync_toolbar(self) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            cursor = self.editor.textCursor()
            fmt = cursor.charFormat()
            block = cursor.block()
            block_fmt = block.blockFormat()
            block_char = block.charFormat()
            families = fmt.fontFamilies() or block_char.fontFamilies() or []
            family = families[0] if families else self.defaults.family
            self.font_combo.setCurrentFont(QFont(family))
            size = fmt.fontPointSize() or block_char.fontPointSize() or self.defaults.size
            size_text = f"{size:g}"
            self.size_combo.setCurrentText(size_text)
            if self.size_combo.lineEdit() is not None:
                self.size_combo.lineEdit().setText(size_text)
            kind = block_kind(block)
            level = block_fmt.headingLevel()
            if kind == KIND_QUOTE:
                style = "quote"
            elif level:
                style = f"h{min(4, level)}"
            else:
                style = "normal"
            style_index = self.style_combo.findData(style)
            if style_index >= 0:
                self.style_combo.setCurrentIndex(style_index)
            self.action_bold.setChecked(fmt.fontWeight() >= QFont.Weight.DemiBold)
            self.action_italic.setChecked(fmt.fontItalic())
            self.action_underline.setChecked(fmt.fontUnderline())
            self.action_strike.setChecked(fmt.fontStrikeOut())
            vertical = fmt.verticalAlignment()
            self.action_superscript.setChecked(vertical == QTextCharFormat.VerticalAlignment.AlignSuperScript)
            self.action_subscript.setChecked(vertical == QTextCharFormat.VerticalAlignment.AlignSubScript)
            self.action_inline_code.setChecked(bool(fmt.property(blocks.PROP_INLINE_CODE)))
            alignment = block_fmt.alignment()
            self.action_align_left.setChecked(bool(alignment & Qt.AlignmentFlag.AlignLeft) and not (alignment & Qt.AlignmentFlag.AlignHCenter) and not (alignment & Qt.AlignmentFlag.AlignRight))
            self.action_align_center.setChecked(bool(alignment & Qt.AlignmentFlag.AlignHCenter))
            self.action_align_right.setChecked(bool(alignment & Qt.AlignmentFlag.AlignRight))
            self.action_align_justify.setChecked(bool(alignment & Qt.AlignmentFlag.AlignJustify))
            text_list = block.textList()
            self.action_bullets.setChecked(False)
            self.action_numbers.setChecked(False)
            if text_list is not None:
                list_style = text_list.format().style()
                if list_style in (QTextListFormat.Style.ListDecimal, QTextListFormat.Style.ListLowerAlpha,
                                  QTextListFormat.Style.ListUpperAlpha, QTextListFormat.Style.ListLowerRoman,
                                  QTextListFormat.Style.ListUpperRoman):
                    self.action_numbers.setChecked(True)
                else:
                    self.action_bullets.setChecked(True)
            line_value = block_fmt.property(PROP_BLOCK_LINE_SPACING)
            line = 1.0
            try:
                if line_value is not None:
                    line = float(line_value)
            except (TypeError, ValueError):
                pass
            line_index = -1
            for i in range(self.line_combo.count()):
                data = self.line_combo.itemData(i)
                if data is not None and abs(float(data) - line) < 0.001:
                    line_index = i
                    break
            if line_index < 0 and abs(line - 1.0) > 0.001:
                line_index = self.line_combo.count() - 1
            elif line_index < 0:
                line_index = 0
            self.line_combo.setCurrentIndex(line_index)
            color = fmt.foreground().color() if fmt.foreground().style() == Qt.BrushStyle.SolidPattern else QColor(self.defaults.color)
            self.color_button.setIcon(icons.icon("color", color=color.name()))
            background = fmt.background().color() if fmt.background().style() == Qt.BrushStyle.SolidPattern else None
            self.highlight_button.setIcon(icons.icon("highlight", accent=(background.name() if background and background.alpha() else theme.ACCENT)))
            self._update_table_actions()
            self.action_undo.setEnabled(self.editor.document().isUndoAvailable())
            self.action_redo.setEnabled(self.editor.document().isRedoAvailable())
        finally:
            self._syncing = False

    def _update_table_actions(self) -> None:
        in_table = self.editor.textCursor().currentTable() is not None
        for action in (self.action_table_row_above, self.action_table_row_below, self.action_table_col_left,
                       self.action_table_col_right, self.action_table_del_row, self.action_table_del_col,
                       self.action_table_header, self.action_table_delete):
            action.setEnabled(in_table)

    # ------------------------------------------------------------------
    # Formatting commands
    # ------------------------------------------------------------------
    def _with_cursor(self, function) -> None:
        cursor = self.editor.textCursor()
        function(cursor)
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()
        self._sync_toolbar()

    def toggle_bold(self) -> None:
        self._with_cursor(blocks.toggle_bold)

    def toggle_italic(self) -> None:
        self._with_cursor(blocks.toggle_italic)

    def toggle_underline(self) -> None:
        self._with_cursor(blocks.toggle_underline)

    def toggle_strike(self) -> None:
        self._with_cursor(blocks.toggle_strike)

    def toggle_superscript(self) -> None:
        self._with_cursor(blocks.toggle_superscript)

    def toggle_subscript(self) -> None:
        self._with_cursor(blocks.toggle_subscript)

    def toggle_inline_code(self) -> None:
        def apply(cursor: QTextCursor) -> None:
            if bool(cursor.charFormat().property(blocks.PROP_INLINE_CODE)):
                blocks.clear_inline_code(cursor, self.defaults)
            else:
                blocks.insert_inline_code(cursor, "", self.defaults)
        self._with_cursor(apply)

    def apply_font_family(self, family: str) -> None:
        self._with_cursor(lambda cursor: blocks.set_font_family(cursor, family))

    def apply_font_size(self, size: float) -> None:
        self._with_cursor(lambda cursor: blocks.set_font_size(cursor, size))

    def apply_style(self, style: str) -> None:
        self._with_cursor(lambda cursor: blocks.apply_paragraph_style(cursor, style, self.defaults))

    def set_alignment(self, alignment: Qt.AlignmentFlag) -> None:
        self._with_cursor(lambda cursor: blocks.set_alignment(cursor, alignment))

    def toggle_list(self, ordered: bool) -> None:
        self._with_cursor(lambda cursor: blocks.toggle_list(cursor, ordered))

    def change_indent(self, delta: int) -> None:
        self._with_cursor(lambda cursor: blocks.change_list_indent(cursor, delta))

    def apply_text_color(self, color: QColor) -> None:
        self._with_cursor(lambda cursor: blocks.set_text_color(cursor, color))

    def apply_highlight(self, color: QColor | None) -> None:
        self._with_cursor(lambda cursor: blocks.set_highlight(cursor, color))

    def choose_text_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.defaults.color), self, "Text colour")
        if color.isValid():
            self.apply_text_color(color)

    def choose_highlight(self) -> None:
        color = QColorDialog.getColor(QColor(HIGHLIGHT_COLOR), self, "Highlight colour")
        if color.isValid():
            self.apply_highlight(color)

    def clear_formatting(self) -> None:
        def apply(cursor: QTextCursor) -> None:
            blocks.reset_paragraph(cursor, self.defaults)
            fmt = default_char_format(self.defaults)
            fmt.setProperty(blocks.PROP_INLINE_CODE, False)
            fmt.setProperty(blocks.PROP_RAW_INLINE, False)
            fmt.setAnchor(False)
            fmt.setAnchorHref("")
            cursor.setCharFormat(fmt)
        self._with_cursor(apply)

    def open_spacing(self) -> None:
        cursor = self.editor.textCursor()
        fmt = cursor.block().blockFormat()
        line = fmt.property(PROP_BLOCK_LINE_SPACING)
        before = fmt.property(PROP_BLOCK_SPACE_BEFORE)
        after = fmt.property(PROP_BLOCK_SPACE_AFTER)
        dialog = SpacingDialog(self,
                               float(line) if line is not None else 1.0,
                               float(before) if before is not None else 0.0,
                               float(after) if after is not None else 0.0)
        if dialog.exec():
            line_value, before_value, after_value = dialog.values()
            cursor = self.editor.textCursor()
            cursor.beginEditBlock()
            blocks.set_line_spacing(cursor, line_value)
            blocks.set_paragraph_spacing(cursor, before_value, after_value)
            cursor.endEditBlock()
            self.editor.setFocus()
            self._sync_toolbar()

    # ------------------------------------------------------------------
    # Insert commands
    # ------------------------------------------------------------------
    def insert_link(self) -> None:
        cursor = self.editor.textCursor()
        selected = cursor.selectedText().replace("\u2029", " ")
        dialog = LinkDialog(self, selected, "")
        if not dialog.exec():
            return
        text, url = dialog.values()
        if not url:
            return
        cursor = self.editor.textCursor()
        if not cursor.hasSelection() and text:
            cursor.insertText(text)
            cursor.setPosition(cursor.position() - len(text), QTextCursor.MoveMode.KeepAnchor)
        elif not text:
            text = url
            cursor.insertText(text)
            cursor.setPosition(cursor.position() - len(text), QTextCursor.MoveMode.KeepAnchor)
        blocks.insert_link(cursor, text, url)
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()

    def _bibliography_path_from_yaml(self) -> Path | None:
        yaml = self.front_edit.toPlainText()
        match = re.search(r"^\s*bibliography:\s*(.+?)\s*$", yaml, re.MULTILINE)
        if not match:
            return None
        value = match.group(1).strip().strip("'\"")
        if not value or value.startswith("["):
            return None
        path = Path(value)
        if not path.is_absolute() and self.path is not None:
            path = self.path.parent / path
        return path

    def _default_bibliography(self) -> Path | None:
        yaml_path = self._bibliography_path_from_yaml()
        if yaml_path is not None and yaml_path.is_file():
            return yaml_path
        configured = self.settings.value("zotero_bib_path", "", type=str) or ""
        if configured and Path(configured).is_file():
            return Path(configured)
        bases = []
        if self.path is not None:
            bases.append(self.path.parent)
        if self.project_root is not None:
            bases.append(self.project_root)
        found: dict[str, Path] = {}
        for base in bases:
            for pattern in ("*.bib", "references/*.bib"):
                try:
                    for candidate in base.glob(pattern):
                        if candidate.is_file():
                            found[str(candidate.resolve())] = candidate
                except OSError:
                    pass
        return next(iter(found.values())) if len(found) == 1 else None

    def _set_bibliography_yaml(self, bibliography: Path, replace: bool) -> None:
        if self._mode == MODE_MARKDOWN:
            return
        yaml = self.front_edit.toPlainText()
        if self.path is not None:
            try:
                value = bibliography.resolve().relative_to(self.path.parent.resolve()).as_posix()
            except ValueError:
                value = bibliography.resolve().as_posix()
        else:
            value = bibliography.resolve().as_posix()
        line = f'bibliography: "{value}"'
        pattern = re.compile(r"^\s*bibliography:\s*.*$", re.MULTILINE)
        if pattern.search(yaml):
            if replace:
                yaml = pattern.sub(line, yaml, count=1)
            else:
                return
        else:
            yaml = (yaml.rstrip() + "\n" if yaml.strip() else "") + line
        self.front_edit.blockSignals(True)
        self.front_edit.setPlainText(yaml)
        self.front_edit.blockSignals(False)
        self._on_modified()

    def insert_citation(self) -> None:
        if self._mode == MODE_MARKDOWN:
            self.statusBar().showMessage("Zotero citations are available in R Markdown or Quarto mode", 3500)
            return
        if not self._ensure_saved():
            return
        bibliography = self._default_bibliography()
        dialog = CitationDialog(bibliography, self)
        if not dialog.exec():
            return
        selected = dialog.selected_citations()
        if not selected:
            QMessageBox.information(self, "Citation", "Select at least one bibliography entry.")
            return
        chosen = dialog.bibliography_path
        if chosen is not None:
            self.settings.setValue("zotero_bib_path", str(chosen))
            self.settings.sync()
            existing = self._bibliography_path_from_yaml()
            replace = existing is None or not existing.is_file()
            if existing is not None and existing.is_file():
                try:
                    same = existing.resolve() == chosen.resolve()
                except OSError:
                    same = False
                if not same:
                    answer = QMessageBox.question(
                        self, "Bibliography",
                        f"This document already links:\n{existing}\n\n"
                        f"Replace it with the selected bibliography?\n{chosen}",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No,
                    )
                    replace = answer == QMessageBox.StandardButton.Yes
            self._set_bibliography_yaml(chosen, replace=replace)
        keys = [citation.key for citation in selected]
        citation_text = f"[@{keys[0]}]" if len(keys) == 1 else "[@" + "; @".join(keys) + "]"
        cursor = self.editor.textCursor()
        cursor.insertText(citation_text)
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()
        self.statusBar().showMessage(f"Inserted citation: {citation_text}", 3500)

    def insert_image(self) -> None:
        if not self._ensure_saved():
            return
        dialog = ImageDialog(self)
        if not dialog.exec():
            return
        source, alt, width = dialog.values()
        if not source:
            return
        source_path = Path(source)
        if not source_path.is_file() or self.path is None:
            return
        try:
            relative = paths.copy_to_assets(source_path, self.path)
        except OSError as exc:
            QMessageBox.critical(self, "Image", f"Could not copy the image:\n{exc}")
            return
        cursor = self.editor.textCursor()
        cursor.beginEditBlock()
        blocks.insert_image(cursor, relative, alt or source_path.stem, float(width),
                            max(300, self.editor.viewport().width() - 100))
        cursor.endEditBlock()
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()

    def insert_table(self) -> None:
        dialog = TableDialog(self)
        if not dialog.exec():
            return
        rows, columns, header = dialog.values()
        cursor = self.editor.textCursor()
        cursor.beginEditBlock()
        blocks.create_table(cursor, rows, columns, header, self.defaults)
        cursor.endEditBlock()
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()

    def insert_hr(self) -> None:
        cursor = self.editor.textCursor()
        cursor.beginEditBlock()
        blocks.insert_hr(cursor, self.defaults)
        cursor.endEditBlock()
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()

    def insert_inline_r(self) -> None:
        if self._mode == MODE_MARKDOWN:
            self.statusBar().showMessage("Inline R is available in R Markdown or Quarto mode", 3000)
            return
        cursor = self.editor.textCursor()
        cursor.beginEditBlock()
        blocks.insert_inline_code(cursor, "r ", self.defaults)
        cursor.endEditBlock()
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()

    def insert_chunk(self) -> None:
        if self._mode == MODE_MARKDOWN:
            self.statusBar().showMessage("R code chunks are available in R Markdown or Quarto mode", 3000)
            return
        dialog = ChunkDialog(self)
        if not dialog.exec():
            return
        header, code = dialog.values()
        cursor = self.editor.textCursor()
        cursor.beginEditBlock()
        blocks.insert_chunk(cursor, header, code, self.defaults)
        cursor.endEditBlock()
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()

    # ------------------------------------------------------------------
    # Table commands
    # ------------------------------------------------------------------
    def _table_and_cell(self):
        cursor = self.editor.textCursor()
        table = cursor.currentTable()
        if table is None:
            return cursor, None, None
        return cursor, table, table.cellAt(cursor)

    def table_insert_row(self, below: bool) -> None:
        cursor, table, cell = self._table_and_cell()
        if table is None or cell is None:
            return
        index = cell.row() + (1 if below else 0)
        table.insertRows(index, 1)
        self.editor.setFocus()

    def table_insert_column(self, right: bool) -> None:
        cursor, table, cell = self._table_and_cell()
        if table is None or cell is None:
            return
        index = cell.column() + (1 if right else 0)
        table.insertColumns(index, 1)
        self.editor.setFocus()

    def table_delete_row(self) -> None:
        cursor, table, cell = self._table_and_cell()
        if table is None or cell is None:
            return
        if table.rows() <= 1:
            blocks.delete_table(cursor)
        else:
            table.removeRows(cell.row(), 1)
        self.editor.setFocus()

    def table_delete_column(self) -> None:
        cursor, table, cell = self._table_and_cell()
        if table is None or cell is None:
            return
        if table.columns() <= 1:
            blocks.delete_table(cursor)
        else:
            table.removeColumns(cell.column(), 1)
        self.editor.setFocus()

    def table_toggle_header(self) -> None:
        cursor = self.editor.textCursor()
        blocks.table_toggle_header(cursor)
        self.editor.setFocus()

    def table_delete(self) -> None:
        cursor = self.editor.textCursor()
        blocks.delete_table(cursor)
        self.editor.setFocus()

    # ------------------------------------------------------------------
    # Document lifecycle
    # ------------------------------------------------------------------
    def _default_yaml(self, title: str = "Untitled", quarto: bool = False) -> str:
        safe = title.replace('"', '\\"')
        if quarto:
            return f'title: "{safe}"\nformat: pdf'
        return f'title: "{safe}"\noutput: pdf_document'

    def _new_document(self, first: bool = False, mode: str = MODE_MARKDOWN) -> None:
        if not first and not self._maybe_save_changes():
            return
        if mode not in MODE_LABELS:
            mode = MODE_MARKDOWN
        self._mode = mode
        self._loading = True
        try:
            self.path = None
            self.editor.set_base_path(None)
            self.editor.reset_document()
            self.front_edit.setPlainText(
                "" if mode == MODE_MARKDOWN else self._default_yaml(quarto=mode == MODE_QUARTO)
            )
            self._generation = 0
            self._saved_generation = 0
            self._force_next_save = False
            self._last_saved_at = None
            self.sync.reset(None, "")
            self._autosave_timer.stop()
            self._last_result = None
            self._last_warnings = []
            self.preview.setPlainText("")
            self.preview_warning.hide()
        finally:
            self._loading = False
        self._update_title()
        self._update_file_label()
        self._update_word_count()
        self._update_sync_label()
        self._update_log_path()
        self._update_mode_ui()
        self._select_current_in_files()
        self.chat_panel.refresh_settings()
        self._refresh_preview()
        self.editor.setFocus()
        self.statusBar().showMessage(f"New {MODE_LABELS[mode]} document", 1800)

    def new_document(self) -> None:
        self._new_document(mode=MODE_MARKDOWN)

    def new_rmd_document(self) -> None:
        self._new_document(mode=MODE_RMD)

    def new_quarto_document(self) -> None:
        self._new_document(mode=MODE_QUARTO)

    def open_dialog(self) -> None:
        start = self.path.parent if self.path else Path.home() / "Documents"
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open document", str(start),
            "Markdown / Quarto / R Markdown (*.md *.markdown *.qmd *.Rmd *.rmd);;"
            "Markdown (*.md *.markdown);;Quarto (*.qmd);;R Markdown (*.Rmd *.rmd);;All files (*)"
        )
        if filename:
            self.open_path(Path(filename))

    def open_path(self, path: Path, silent: bool = False, check_save: bool = True) -> bool:
        path = Path(path)
        if self.path is not None and path.resolve() == self.path.resolve():
            return True
        if check_save and not self._maybe_save_changes():
            return False
        if not path.is_file():
            if not silent:
                QMessageBox.warning(self, "Open file", f"The file does not exist:\n{path}")
            return False
        try:
            text = read_text(path)
        except OSError as exc:
            if not silent:
                QMessageBox.critical(self, "Open file", f"Could not read the file:\n{exc}")
            return False
        self._load_text(path, text)
        if not silent:
            self._add_recent(path)
        return True

    def _load_text(self, path: Path | None, text: str) -> None:
        self._loading = True
        result = None
        try:
            self._autosave_timer.stop()
            self.path = path
            self._mode = document_mode_for_path(path)
            self.editor.set_base_path(path.parent if path else None)
            yaml_text, result = import_rmd(
                self.editor.document(), text, self.defaults,
                path.parent if path else None,
                self.settings.value("pandoc_path", "", type=str) or "",
            )
            self.front_edit.setPlainText(yaml_text)
            self._generation = 0
            self._saved_generation = 0
            self._force_next_save = False
            self._last_saved_at = None
            self._last_result = None
            self._last_warnings = result.warnings
            self.editor.document().clearUndoRedoStacks()
            self.editor.moveCursor(QTextCursor.MoveOperation.Start)
            self.sync.reset(path, text)
            if result.used_pandoc:
                self.statusBar().showMessage("Opened " + (path.name if path else "document"), 2200)
            else:
                self.statusBar().showMessage("Opened as raw Markdown (Pandoc not found)", 6000)
        finally:
            self._loading = False
        self._update_title()
        self._update_file_label()
        self._update_word_count()
        self._update_sync_label()
        self._update_log_path()
        self._update_mode_ui()
        if path is not None:
            try:
                inside = self.project_root is not None and path.resolve().is_relative_to(self.project_root)
            except (OSError, ValueError):
                inside = False
            if not inside:
                self._set_project_root(self._detect_project_root(path))
            self._select_current_in_files()
        self.chat_panel.refresh_settings()
        self._refresh_preview()
        self._sync_toolbar()
        self.editor.setFocus()
        if result is not None and not result.used_pandoc and not self._pandoc_warned:
            self._pandoc_warned = True
            QMessageBox.warning(
                self, "Pandoc not found",
                "Pandoc was not found, so this file is shown as raw Markdown blocks. "
                "Install Pandoc or set the Pandoc path in Settings (Ctrl+,) for visual editing."
            )

    def _maybe_save_changes(self) -> bool:
        if not self.dirty:
            return True
        box = QMessageBox(self)
        box.setWindowTitle("Unsaved changes")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText("Save changes to this document?")
        box.setInformativeText("If you close without saving, the generated document file will not be updated.")
        box.setStandardButtons(QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Save)
        choice = box.exec()
        if choice == QMessageBox.StandardButton.Save:
            saved = self._save_document()
            return saved or not self.dirty
        if choice == QMessageBox.StandardButton.Discard:
            return True
        return False

    @property
    def dirty(self) -> bool:
        return self._generation != self._saved_generation

    def _on_modified(self) -> None:
        if self._loading:
            return
        self._generation += 1
        self._update_title()
        self._update_sync_label()
        self._word_timer.start()
        self._preview_timer.start()
        if self.path is not None and self._autosave_enabled:
            self._autosave_timer.start(max(250, self._autosave_ms))

    def _serialize_current(self) -> SerializeResult:
        options = SerializeOptions(
            preserve_visual=self._preserve_visual and self._mode != MODE_MARKDOWN,
            defaults=self.defaults,
            document_dir=self.path.parent if self.path else None,
        )
        return serialize_rmd(self.editor.document(), self.front_edit.toPlainText(), options)

    def _write_to_path(self, force: bool = False, silent: bool = False) -> bool:
        if self.path is None:
            if silent:
                return False
            return self.save_as()
        generation = self._generation
        try:
            result = self._serialize_current()
        except Exception as exc:
            if not silent:
                QMessageBox.critical(self, "Serialise", f"Could not generate Markdown:\n{exc}")
            return False
        try:
            if self.sync.path != self.path:
                self.sync.reset(self.path, result.markdown)
            self.sync.save(result.markdown, force=force or self._force_next_save)
        except ExternalConflict:
            self._autosave_timer.stop()
            if silent:
                self._update_sync_label("External change — paused")
                QTimer.singleShot(0, self._on_external_change)
            else:
                self._show_conflict_dialog()
            return False
        except OSError as exc:
            if silent:
                self.statusBar().showMessage(f"Autosave failed: {exc}", 8000)
                self._update_sync_label("Autosave failed")
            else:
                QMessageBox.critical(self, "Save", f"Could not write the file:\n{exc}")
            return False
        self._saved_generation = generation
        self._force_next_save = False
        self._last_saved_at = datetime.now()
        self._last_result = result
        self._last_warnings = result.warnings
        self._refresh_preview(result)
        if self.dirty:
            if self._autosave_enabled:
                self._autosave_timer.start(max(250, self._autosave_ms))
        else:
            self._autosave_timer.stop()
        self._update_title()
        self._update_sync_label("Saved " + self._last_saved_at.strftime("%H:%M:%S"))
        if result.warnings:
            self.statusBar().showMessage(f"Saved with {len(result.warnings)} conversion note(s)", 4500)
        else:
            self.statusBar().showMessage("Saved", 2000)
        if not silent:
            self._add_recent(self.path)
        return True

    def _save_document(self) -> bool:
        if self.path is None:
            return self.save_as()
        return self._write_to_path(silent=False)

    def save_as(self) -> bool:
        start_dir = self.path.parent if self.path else Path.home() / "Documents"
        default_suffix = MODE_SUFFIX[self._mode]
        suggested = self.path.name if self.path else f"Untitled{default_suffix}"
        if self._mode == MODE_MARKDOWN:
            filters = "Markdown (*.md *.markdown);;All files (*)"
        elif self._mode == MODE_QUARTO:
            filters = "Quarto (*.qmd);;Markdown (*.md *.markdown);;R Markdown (*.Rmd *.rmd);;All files (*)"
        else:
            filters = "R Markdown (*.Rmd *.rmd);;Markdown (*.md *.markdown);;Quarto (*.qmd);;All files (*)"
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save document", str(start_dir / suggested), filters
        )
        if not filename:
            return False
        path = Path(filename)
        if not path.suffix:
            path = path.with_suffix(default_suffix)
        old_path = self.path
        if old_path is not None and old_path.parent.resolve() != path.parent.resolve():
            self._copy_assets(old_path, path)
        self.path = path
        self._mode = document_mode_for_path(path)
        self.editor.set_base_path(path.parent)
        yaml = self.front_edit.toPlainText()
        changed_yaml = False
        if self._mode != MODE_MARKDOWN:
            if re.search(r'^title:\s*"?Untitled"?\s*$', yaml, re.MULTILINE):
                title = path.stem.replace("_", " ")
                yaml = re.sub(r'^title:\s*"?Untitled"?\s*$', f'title: "{title}"', yaml, count=1, flags=re.MULTILINE)
                changed_yaml = True
            if self._mode == MODE_QUARTO and "format:" not in yaml:
                if "output: pdf_document" in yaml:
                    yaml = yaml.replace("output: pdf_document", "format: pdf")
                    changed_yaml = True
            elif self._mode == MODE_RMD and "format:" in yaml and "output:" not in yaml:
                yaml = yaml.replace("format: pdf", "output: pdf_document")
                changed_yaml = True
            if not yaml.strip():
                yaml = self._default_yaml(path.stem.replace("_", " "), quarto=self._mode == MODE_QUARTO)
                changed_yaml = True
        if changed_yaml:
            self.front_edit.blockSignals(True)
            self.front_edit.setPlainText(yaml)
            self.front_edit.blockSignals(False)
        self.sync.reset(path, yaml)
        self._force_next_save = True
        self._update_mode_ui()
        accepted = self._write_to_path(force=True, silent=False)
        if accepted:
            self._add_recent(path)
            self._update_file_label()
            self._update_log_path()
            self._update_mode_ui()
            try:
                inside = self.project_root is not None and path.resolve().is_relative_to(self.project_root)
            except (OSError, ValueError):
                inside = False
            if not inside:
                self._set_project_root(self._detect_project_root(path))
            self._select_current_in_files()
        return accepted

    def _copy_assets(self, old_path: Path, new_path: Path) -> None:
        source = old_path.parent / "assets"
        if not source.is_dir():
            return
        target = new_path.parent / "assets"
        try:
            shutil.copytree(source, target, dirs_exist_ok=True)
        except OSError:
            pass

    def _add_recent(self, path: Path | None) -> None:
        if path is None:
            return
        value = str(path.resolve())
        self._recent_files = [item for item in self._recent_files if item != value]
        self._recent_files.insert(0, value)
        self._recent_files = self._recent_files[:8]
        self.settings.setValue("recent_files", self._recent_files)
        self.settings.sync()
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self) -> None:
        if not hasattr(self, "recent_menu"):
            return
        self.recent_menu.clear()
        for item in self._recent_files:
            path = Path(item)
            action = QAction(path.name, self)
            action.setToolTip(item)
            action.triggered.connect(lambda _checked=False, p=path: self.open_path(p))
            self.recent_menu.addAction(action)
        if self._recent_files:
            self.recent_menu.addSeparator()
            clear = QAction("Clear recent files", self)
            clear.triggered.connect(self._clear_recent)
            self.recent_menu.addAction(clear)
        else:
            empty = QAction("No recent files", self)
            empty.setEnabled(False)
            self.recent_menu.addAction(empty)

    def _clear_recent(self) -> None:
        self._recent_files = []
        self.settings.setValue("recent_files", [])
        self._rebuild_recent_menu()

    def closeEvent(self, event) -> None:
        if not self._maybe_save_changes():
            event.ignore()
            return
        if self._knit_process is not None:
            self._knit_process.kill()
            self._knit_process.waitForFinished(1000)
        if self._latex_process is not None:
            self._latex_process.kill()
            self._latex_process.waitForFinished(1000)
        self.chat_panel.shutdown()
        self._save_geometry()
        event.accept()

    # ------------------------------------------------------------------
    # UI state
    # ------------------------------------------------------------------
    def _update_render_action(self) -> None:
        markdown = self._mode == MODE_MARKDOWN
        self.action_knit.setText("Render PDF" if self._mode == MODE_QUARTO else "Knit to PDF")
        self.action_knit.setVisible(not markdown)
        self.action_knit.setEnabled(not markdown)
        if hasattr(self, "knit_button"):
            self.knit_button.setVisible(not markdown)

    def _update_mode_ui(self) -> None:
        markdown = self._mode == MODE_MARKDOWN
        for action in (self.action_front, self.action_inline_r, self.action_chunk, self.action_cite, self.action_visual):
            action.setVisible(not markdown)
            action.setEnabled(not markdown)
        self.front_panel.setVisible((not markdown) and self.action_front.isChecked())
        self.mode_label.setText(MODE_LABELS[self._mode])
        self.mode_label.setToolTip(f"{MODE_LABELS[self._mode]} mode")
        if markdown:
            self.visual_label.setText("Markdown")
            self.visual_label.setToolTip("Plain Markdown source; visual font styling stays in the editor")
            self.visual_label.setStyleSheet(f"color: {theme.MUTED};")
        else:
            self.visual_label.setText("HTML styling" if self._preserve_visual else "PDF-clean source")
            self.visual_label.setToolTip("Presentational formatting is written as Pandoc HTML attributes")
            self.visual_label.setStyleSheet(
                f"color: {theme.GOLD if self._preserve_visual else theme.MUTED};"
            )
        self._update_render_action()

    def _update_title(self) -> None:
        name = self.path.name if self.path else f"Untitled{MODE_SUFFIX[self._mode]}"
        marker = " •" if self.dirty else ""
        self.setWindowTitle(f"{name}{marker} — {APP_NAME}")
        self.doc_title_label.setText(f"{name}{marker}")
        self.doc_title_label.setToolTip(str(self.path) if self.path else "Not saved yet")
        self._update_render_action()

    def _update_file_label(self) -> None:
        if self.path is None:
            self.file_label.setText("Not saved")
            self.file_label.setToolTip("Use Save to choose a file")
        else:
            try:
                shown = str(self.path.parent.name) + " / " + self.path.name
            except Exception:
                shown = str(self.path)
            self.file_label.setText(shown)
            self.file_label.setToolTip(str(self.path))

    def _update_word_count(self) -> None:
        text = self.editor.toPlainText()
        count = len(re.findall(r"[^\W_]+(?:['’\-][^\W_]+)*", text, flags=re.UNICODE))
        self.word_label.setText(f"{count:,} word{'s' if count != 1 else ''}")
        self.word_label.setToolTip(f"{len(text):,} characters")

    def _update_sync_label(self, text: str | None = None) -> None:
        if text is not None:
            self.sync_label.setText(text)
            paused = any(word in text for word in ("paused", "Conflict", "failed", "missing"))
            self.sync_label.setStyleSheet(f"color: {theme.GOLD if paused else theme.MUTED};")
            return
        if self.path is None:
            self.sync_label.setText("Not saved")
            self.sync_label.setStyleSheet(f"color: {theme.FAINT};")
        elif self.dirty:
            if self._autosave_enabled:
                self.sync_label.setText("Autosave pending")
            else:
                self.sync_label.setText("Unsaved changes")
            self.sync_label.setStyleSheet(f"color: {theme.GOLD};")
        else:
            if self._last_saved_at is not None:
                self.sync_label.setText("Saved " + self._last_saved_at.strftime("%H:%M"))
            else:
                self.sync_label.setText("Synced")
            self.sync_label.setStyleSheet(f"color: {theme.MUTED};")

    def _refresh_preview(self, result: SerializeResult | None = None) -> None:
        if result is None:
            try:
                result = self._serialize_current()
            except Exception as exc:
                self.preview.setPlainText(f"Could not generate Markdown:\n{exc}")
                return
        self._last_result = result
        self._last_warnings = result.warnings
        scroll = self.preview.verticalScrollBar().value()
        self.preview.setPlainText(result.markdown)
        self.preview.verticalScrollBar().setValue(scroll)
        if result.warnings:
            self.preview_warning.setText("\n".join("• " + item for item in result.warnings[:3]))
            self.preview_warning.show()
            self.preview_warning.setToolTip("\n".join(result.warnings))
            self.preview_warning.setVisible(self.preview_panel.isVisible())
            self.visual_label.setToolTip("\n".join(result.warnings))
        else:
            self.preview_warning.hide()
        if self.dirty:
            self._update_sync_label()
        if self.preview_panel.isVisible() and self.side_tabs.currentIndex() == 3:
            self._render_timer.start()

    def _refresh_rendered(self) -> None:
        if not self.preview_panel.isVisible() or self.side_tabs.currentIndex() != 3:
            return
        result = self._last_result
        if result is None:
            try:
                result = self._serialize_current()
            except Exception as exc:
                self.rendered_preview.setPlainText(f"Could not generate the preview:\n{exc}")
                return
        _yaml, body = split_front_matter(result.markdown)
        body = re.sub(r"```\{r[^}]*\}", "```r", body)
        fragment = external.pandoc_html(body, self.settings.value("pandoc_path", "", type=str) or "")
        if fragment is None:
            self.rendered_preview.setPlainText(
                "Pandoc is needed for the rendered preview.\n"
                "It is bundled with RStudio; set its path in Settings if it is not found."
            )
            return
        scroll = self.rendered_preview.verticalScrollBar().value()
        document = self.rendered_preview.document()
        document.setDefaultStyleSheet(_rendered_css())
        base_dir = self.path.parent if self.path else Path.cwd()
        document.setBaseUrl(QUrl.fromLocalFile(str(base_dir.resolve()) + "/"))
        self.rendered_preview.setHtml(fragment)
        document.setBaseUrl(QUrl.fromLocalFile(str(base_dir.resolve()) + "/"))
        self.rendered_preview.verticalScrollBar().setValue(scroll)

    def _copy_generated(self) -> None:
        result = self._last_result or self._serialize_current()
        QApplication.clipboard().setText(result.markdown)
        self.statusBar().showMessage("Generated Markdown copied", 1600)

    def _toggle_preview(self, checked: bool) -> None:
        self.preview_panel.setVisible(checked)
        if checked:
            self._refresh_preview()
            self._update_log_path()
            if self.side_tabs.currentIndex() == 3:
                self._render_timer.start(0)
            width = max(380, min(470, int(self.width() * 0.36)))
            total = max(800, self.splitter.width())
            self.splitter.setSizes([max(440, total - width), width])
        else:
            self.preview_warning.hide()
            self._render_timer.stop()

    def _toggle_front(self, checked: bool) -> None:
        if self._mode == MODE_MARKDOWN:
            self.front_panel.hide()
            if self.action_front.isChecked():
                self.action_front.blockSignals(True)
                self.action_front.setChecked(False)
                self.action_front.blockSignals(False)
            return
        self.front_panel.setVisible(checked)
        if checked:
            self.front_edit.setFocus()
            cursor = self.front_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.front_edit.setTextCursor(cursor)

    def _set_visual_mode(self, enabled: bool) -> None:
        if self._syncing or self._mode == MODE_MARKDOWN:
            return
        self._preserve_visual = enabled
        self.settings.setValue("preserve_visual", enabled)
        self.visual_label.setText("HTML styling" if enabled else "PDF-clean source")
        self.visual_label.setStyleSheet(f"color: {theme.GOLD if enabled else theme.MUTED};")
        self._generation += 1
        self._update_title()
        self._update_sync_label()
        self._preview_timer.start()
        if self.path is not None and self._autosave_enabled:
            self._autosave_timer.start(max(250, self._autosave_ms))
        self.statusBar().showMessage(
            "Presentational formatting will be written as Pandoc HTML styles; PDF ignores them."
            if enabled else "Source is PDF-clean: fonts, colours and spacing stay in the editor only.",
            3500,
        )

    # ------------------------------------------------------------------
    # External change handling
    # ------------------------------------------------------------------
    def _on_external_change(self, _path: str) -> None:
        if self.path is None or self._loading:
            return
        path = self.path
        if not path.exists():
            box = QMessageBox(self)
            box.setWindowTitle("File missing")
            box.setIcon(QMessageBox.Icon.Warning)
            box.setText("The .Rmd file was moved or deleted outside Rmd Studio.")
            box.setInformativeText("Save the document to a new location to keep working.")
            save_as = box.addButton("Save as...", QMessageBox.ButtonRole.AcceptRole)
            box.addButton(QMessageBox.StandardButton.Cancel)
            box.exec()
            if box.clickedButton() == save_as:
                self.save_as()
            else:
                self._autosave_timer.stop()
                self._update_sync_label("File missing — paused")
            return
        try:
            disk_text = read_text(path)
        except OSError:
            return
        if not self.dirty:
            self._reload_from_disk(disk_text)
            self.statusBar().showMessage("Reloaded changes from disk", 2600)
            return
        self._show_conflict_dialog()

    def _reload_from_disk(self, disk_text: str | None = None) -> None:
        if self.path is None:
            return
        if disk_text is None:
            try:
                disk_text = read_text(self.path)
            except OSError as exc:
                QMessageBox.critical(self, "Reload", f"Could not read the file:\n{exc}")
                return
        self._load_text(self.path, disk_text)
        self.statusBar().showMessage("Reloaded from disk", 2600)

    def _show_conflict_dialog(self) -> None:
        if self.path is None:
            return
        box = QMessageBox(self)
        box.setWindowTitle("File changed on disk")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText("This file changed in another editor or process while you had unsaved changes.")
        box.setInformativeText("How should the conflict be resolved?")
        reload_button = box.addButton("Reload from disk", QMessageBox.ButtonRole.DestructiveRole)
        keep_button = box.addButton("Keep my version", QMessageBox.ButtonRole.AcceptRole)
        copy_button = box.addButton("Save a copy...", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked == reload_button:
            self._reload_from_disk()
        elif clicked == keep_button:
            self._force_next_save = True
            self._write_to_path(force=True, silent=False)
        elif clicked == copy_button:
            self._save_copy_after_conflict()
        else:
            self._autosave_timer.stop()
            self._update_sync_label("Conflict — not saved")
            self.statusBar().showMessage("External change is unresolved; autosave is paused", 6000)

    def _save_copy_after_conflict(self) -> None:
        if self.path is None:
            return
        suggested = self.path.with_name(self.path.stem + " (copy)" + self.path.suffix)
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save a copy", str(suggested),
            "R Markdown (*.Rmd *.rmd);;Markdown (*.md);;All files (*)"
        )
        if not filename:
            return
        path = Path(filename)
        if not path.suffix:
            path = path.with_suffix(".Rmd")
        self._copy_assets(self.path, path)
        self.path = path
        self.editor.set_base_path(path.parent)
        self.sync.reset(path, "")
        self._force_next_save = True
        if self._write_to_path(force=True, silent=False):
            self._add_recent(path)
            self._update_file_label()
            self._update_log_path()

    # ------------------------------------------------------------------
    # Render and preview
    # ------------------------------------------------------------------
    def _ensure_saved(self) -> bool:
        if self.path is None:
            return self.save_as()
        return True

    def knit(self) -> None:
        if self._mode == MODE_MARKDOWN:
            QMessageBox.information(
                self, "Markdown mode",
                "PDF rendering is available for Quarto and R Markdown documents. "
                "Use File → New Quarto document or New R Markdown document to switch.",
            )
            return
        if not self._save_document():
            return
        if self.path is None:
            return
        latex_path = self.settings.value("pdflatex_path", "", type=str) or ""
        latex = external.find_pdflatex(latex_path)
        if not latex:
            self._offer_latex_install()
            return
        if self._knit_process is not None:
            return
        if self._mode == MODE_QUARTO:
            self._render_quarto(latex)
            return
        rscript = external.find_rscript(self.settings.value("rscript_path", "", type=str) or "")
        if not rscript:
            QMessageBox.warning(self, "Rscript not found", "Set the Rscript path in Settings (Ctrl+,).")
            return
        posix = self.path.as_posix().replace("'", "\\'")
        yaml = self.front_edit.toPlainText()
        if "pdf_document" in yaml:
            expression = f"rmarkdown::render('{posix}', quiet=TRUE, envir=new.env())"
        else:
            expression = (
                "rmarkdown::render("
                f"'{posix}', output_format='pdf_document', quiet=TRUE, envir=new.env())"
            )
        self._knit_output = self.path.with_suffix(".pdf")
        self._knit_canceled = False
        self._knit_started_at = time.time()
        process = QProcess(self)
        process.setProgram(rscript)
        process.setArguments(["-e", expression])
        process.setWorkingDirectory(str(self.path.parent))
        env = QProcessEnvironment.systemEnvironment()
        pandoc = external.find_pandoc(self.settings.value("pandoc_path", "", type=str) or "")
        if pandoc:
            env.insert("RSTUDIO_PANDOC", str(Path(pandoc).parent))
        env.insert("PATH", str(Path(latex).parent) + ";" + env.value("PATH"))
        try:
            rtemp = paths.app_data_dir() / "rtemp"
            rtemp.mkdir(parents=True, exist_ok=True)
            env.insert("TMPDIR", str(rtemp))
            env.insert("TMP", str(rtemp))
            env.insert("TEMP", str(rtemp))
        except OSError:
            pass
        process.setProcessEnvironment(env)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.finished.connect(self._knit_finished)
        process.errorOccurred.connect(self._knit_error)
        self._knit_process = process
        progress = QProgressDialog("Knitting the R Markdown document to PDF...", "Cancel", 0, 0, self)
        progress.setWindowTitle("Knit to PDF")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.canceled.connect(self._cancel_knit)
        self._knit_progress = progress
        progress.show()
        process.start()

    def _render_quarto(self, latex: str) -> None:
        quarto = external.find_quarto(self.settings.value("quarto_path", "", type=str) or "")
        if not quarto:
            QMessageBox.warning(
                self, "Quarto CLI not found",
                "Quarto is needed to render .qmd files. It is bundled with RStudio, "
                "or can be installed from quarto.org. Set the Quarto path in Settings. "
                "You do not need to open RStudio to use it."
            )
            return
        self._knit_output = self.path.with_suffix(".pdf")
        self._knit_canceled = False
        self._knit_started_at = time.time()
        process = QProcess(self)
        process.setProgram(quarto)
        render_path = paths.short_path(self.path) or self.path
        workdir = self.project_root if self.project_root is not None else self.path.parent
        workdir = paths.short_path(workdir) or workdir
        process.setArguments(["render", str(render_path), "--to", "pdf"])
        process.setWorkingDirectory(str(workdir))
        env = QProcessEnvironment.systemEnvironment()
        rscript = external.find_rscript(self.settings.value("rscript_path", "", type=str) or "")
        if rscript:
            env.insert("PATH", str(Path(rscript).parent) + ";" + env.value("PATH"))
        env.insert("PATH", str(Path(latex).parent) + ";" + env.value("PATH"))
        pandoc = external.find_pandoc(self.settings.value("pandoc_path", "", type=str) or "")
        if pandoc:
            env.insert("RSTUDIO_PANDOC", str(Path(pandoc).parent))
        try:
            cache_root = paths.quarto_cache_root()
            codepage_cache = cache_root / "quarto"
            codepage_cache.mkdir(parents=True, exist_ok=True)
            try:
                (codepage_cache / "codepage").write_text("65001", encoding="ascii")
            except OSError:
                pass
            env.insert("LOCALAPPDATA", str(cache_root))
            env.insert("QUARTO_WIN_CODEPAGE", "65001")
            rlib = paths.r_user_library()
            if rlib is not None:
                env.insert("R_LIBS_USER", str(rlib))
            temp = paths.runtime_temp_dir()
            env.insert("TMPDIR", str(temp))
            env.insert("TMP", str(temp))
            env.insert("TEMP", str(temp))
            tex_cache = paths.texmf_cache_dir()
            env.insert("TEXMFCACHE", str(tex_cache))
            env.insert("TEXMFVAR", str(tex_cache))
            env.insert("TEXMFCONFIG", str(tex_cache))
        except OSError:
            pass
        process.setProcessEnvironment(env)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.finished.connect(self._knit_finished)
        process.errorOccurred.connect(self._knit_error)
        self._knit_process = process
        progress = QProgressDialog("Rendering the Quarto document to PDF...", "Cancel", 0, 0, self)
        progress.setWindowTitle("Render PDF (Quarto)")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.canceled.connect(self._cancel_knit)
        self._knit_progress = progress
        progress.show()
        process.start()

    def _offer_latex_install(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("LaTeX is required for PDF")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText("No LaTeX engine was found.")
        box.setInformativeText(
            "rmarkdown needs LaTeX to produce a PDF. TinyTeX is a small LaTeX "
            "distribution and can be installed automatically (about 100 MB, internet required).\n\n"
            "You can also install MiKTeX or TeX Live and set the pdflatex path in Settings."
        )
        install_button = box.addButton("Install TinyTeX", QMessageBox.ButtonRole.AcceptRole)
        locate_button = box.addButton("Locate pdflatex...", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked == install_button:
            self._install_tinytex()
        elif clicked == locate_button:
            self.open_settings()

    def _install_tinytex(self) -> None:
        if self._latex_process is not None:
            return
        rscript = external.find_rscript(self.settings.value("rscript_path", "", type=str) or "")
        if not rscript:
            QMessageBox.warning(self, "TinyTeX", "Rscript was not found. Set its path in Settings.")
            return
        install_dir = paths.tinytex_dir()
        target = install_dir.as_posix().replace("'", "\\'")
        expression = (
            "if (!requireNamespace('tinytex', quietly=TRUE)) "
            "install.packages('tinytex', repos='https://cloud.r-project.org'); "
            f"tinytex::install_tinytex(dir='{target}', force=TRUE, "
            "add_path=FALSE, extra_packages='soul')"
        )
        process = QProcess(self)
        process.setProgram(rscript)
        process.setArguments(["-e", expression])
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        env = QProcessEnvironment.systemEnvironment()
        pandoc = external.find_pandoc(self.settings.value("pandoc_path", "", type=str) or "")
        if pandoc:
            env.insert("RSTUDIO_PANDOC", str(Path(pandoc).parent))
        try:
            rtemp = paths.app_data_dir() / "rtemp"
            rtemp.mkdir(parents=True, exist_ok=True)
            env.insert("TMPDIR", str(rtemp))
            env.insert("TMP", str(rtemp))
            env.insert("TEMP", str(rtemp))
        except OSError:
            pass
        process.setProcessEnvironment(env)
        process.finished.connect(self._latex_finished)
        process.errorOccurred.connect(self._latex_error)
        self._latex_process = process
        self._latex_canceled = False
        progress = QProgressDialog("Installing TinyTeX (this can take several minutes)...", "Cancel", 0, 0, self)
        progress.setWindowTitle("Install TinyTeX")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.canceled.connect(self._cancel_latex)
        self._latex_progress = progress
        progress.show()
        process.start()

    def _cancel_latex(self) -> None:
        self._latex_canceled = True
        if self._latex_process is not None:
            self._latex_process.kill()
            self._latex_process.waitForFinished(1000)
            self._latex_process = None
        self._close_progress("_latex_progress")
        self.statusBar().showMessage("TinyTeX installation cancelled", 3000)

    def _latex_finished(self, exit_code: int, _status) -> None:
        process = self._latex_process
        log = ""
        if process is not None:
            log = bytes(process.readAllStandardOutput()).decode("utf-8", "replace")
            self._latex_process = None
        self._close_progress("_latex_progress")
        if self._latex_canceled:
            self._latex_canceled = False
            return
        external.clear_cache()
        if exit_code == 0 and external.find_pdflatex():
            QMessageBox.information(self, "TinyTeX", "TinyTeX was installed. You can now Knit to PDF.")
        else:
            box = QMessageBox(self)
            box.setWindowTitle("TinyTeX installation failed")
            box.setIcon(QMessageBox.Icon.Critical)
            box.setText("TinyTeX could not be installed automatically.")
            box.setInformativeText("You can install MiKTeX or TinyTeX manually, then set the pdflatex path in Settings.")
            box.setDetailedText(log or "No output was captured.")
            box.exec()

    def _latex_error(self, _error) -> None:
        self._close_progress("_latex_progress")
        self._latex_process = None
        if self._latex_canceled:
            self._latex_canceled = False
            return
        QMessageBox.critical(self, "TinyTeX", "Rscript could not be started. Check the Rscript path in Settings.")

    def _close_progress(self, name: str) -> None:
        progress = getattr(self, name, None)
        setattr(self, name, None)
        if progress is not None:
            try:
                progress.blockSignals(True)
            except Exception:
                pass
            progress.close()
            progress.deleteLater()

    def _cancel_knit(self) -> None:
        self._knit_canceled = True
        if self._knit_process is not None:
            self._knit_process.kill()
            self._knit_process.waitForFinished(1000)
            self._knit_process = None
        self._close_progress("_knit_progress")
        self.statusBar().showMessage("Knit cancelled", 3000)

    def _rendered_pdf_path(self) -> Path | None:
        if self.path is None:
            return None
        expected = self.path.with_suffix(".pdf")
        if expected.is_file() and expected.stat().st_mtime >= self._knit_started_at - 1:
            return expected
        root = self.project_root if self.project_root is not None else self.path.parent
        try:
            candidates = [
                p for p in root.rglob(f"{self.path.stem}.pdf")
                if p.is_file() and p.stat().st_mtime >= self._knit_started_at - 1
            ]
        except OSError:
            candidates = []
        return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None

    def _knit_finished(self, exit_code: int, _status) -> None:
        process = self._knit_process
        log = ""
        if process is not None:
            log = bytes(process.readAllStandardOutput()).decode("utf-8", "replace")
            self._knit_process = None
        self._close_progress("_knit_progress")
        if self._knit_canceled:
            self._knit_canceled = False
            return
        if exit_code == 0:
            rendered = self._rendered_pdf_path()
            if rendered is not None:
                external.open_path(rendered)
                self.statusBar().showMessage(f"PDF complete — {rendered.name}", 4000)
            else:
                QMessageBox.information(
                    self, "PDF render",
                    "The render finished, but the expected PDF was not found.\n\n" + log
                )
        else:
            box = QMessageBox(self)
            box.setWindowTitle("PDF render failed")
            box.setIcon(QMessageBox.Icon.Critical)
            box.setText("The PDF render returned an error.")
            box.setInformativeText(
                "Check the render log, LaTeX installation, YAML format and project configuration."
            )
            box.setDetailedText(log or "No output was captured.")
            box.exec()

    def _knit_error(self, _error) -> None:
        self._close_progress("_knit_progress")
        self._knit_process = None
        if self._knit_canceled:
            self._knit_canceled = False
            return
        QMessageBox.critical(self, "Knit", "Rscript could not be started. Check the Rscript path in Settings.")

    def preview_in_browser(self) -> None:
        result = self._serialize_current()
        _yaml, body = split_front_matter(result.markdown)
        body = re.sub(r"```\{r[^}]*\}", "```r", body)
        pandoc = external.find_pandoc(self.settings.value("pandoc_path", "", type=str) or "")
        if not pandoc:
            QMessageBox.warning(
                self, "Pandoc not found",
                "Pandoc is needed for the rendered preview. It is bundled with RStudio; "
                "you can also set its path in Settings."
            )
            return
        fragment = external.pandoc_html(body, pandoc)
        if fragment is None:
            QMessageBox.warning(self, "Preview", "Pandoc could not render the document.")
            return
        title = self.path.stem if self.path else "Rmd Studio preview"
        base_dir = self.path.parent if self.path else Path.cwd()
        base_uri = base_dir.resolve().as_uri() + "/"
        page = _preview_html(title, fragment, base_uri)
        target = paths.preview_dir() / "preview.html"
        try:
            target.write_text(page, encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Preview", f"Could not write the preview:\n{exc}")
            return
        external.open_path(target)
        if result.warnings:
            self.statusBar().showMessage(f"Preview opened with {len(result.warnings)} conversion note(s)", 4000)

    # ------------------------------------------------------------------
    # Images
    # ------------------------------------------------------------------
    def _handle_image(self, image) -> tuple[str, str] | None:
        if not self._ensure_saved() or self.path is None:
            return None
        folder = self.path.parent / "assets"
        folder.mkdir(parents=True, exist_ok=True)
        if isinstance(image, Path):
            try:
                relative = paths.copy_to_assets(image, self.path)
            except OSError:
                return None
            return relative, image.stem.replace("_", " ")
        from PySide6.QtGui import QImage

        if isinstance(image, QImage):
            name = f"pasted-{datetime.now():%Y%m%d-%H%M%S}.png"
            target = folder / name
            if image.save(str(target), "PNG"):
                return f"assets/{name}", "Pasted image"
        return None

    # ------------------------------------------------------------------
    # Find, settings, help
    # ------------------------------------------------------------------
    def show_find(self) -> None:
        if self._find_dialog is None:
            self._find_dialog = FindReplaceDialog(self.editor, self)
        self._find_dialog.show()
        self._find_dialog.raise_()
        self._find_dialog.activateWindow()

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec():
            self._autosave_enabled = dialog.autosave_check.isChecked()
            self._autosave_ms = dialog.delay_spin.value()
            if not self._autosave_enabled:
                self._autosave_timer.stop()
            preserve = dialog.visual_check.isChecked()
            if preserve != self._preserve_visual:
                self._syncing = True
                self.action_visual.setChecked(preserve)
                self._syncing = False
                self._set_visual_mode(preserve)
            self.chat_panel.refresh_settings()
            self._refresh_preview()
            self.statusBar().showMessage("Settings saved", 2200)

    def show_about(self) -> None:
        AboutDialog(self, __version__).exec()

    def show_guide(self) -> None:
        QMessageBox.information(
            self, "Rmd Studio — quick guide",
            "<b>Markdown mode (default)</b><br>"
            "New documents are plain .md files with no YAML front matter. Bold, italic, "
            "headings, lists, tables, links and images are written as normal Markdown. "
            "PDF, R chunk and citation controls are hidden in this mode.<br><br>"
            "<b>R Markdown and Quarto</b><br>"
            "Use File → New R Markdown document or New Quarto document when you need YAML, "
            "R code chunks, citations or PDF rendering. Opening a .Rmd or .qmd file switches "
            "to that mode automatically.<br><br>"
            "<b>Project files</b><br>"
            "Open a project folder (Ctrl+Shift+O) to browse its tree in the Files tab. "
            "Double-click a .md, .qmd or .Rmd file to switch documents. The app saves the "
            "generated source after you pause typing.<br><br>"
            "<b>PDF and formatting</b><br>"
            "In R Markdown and Quarto mode, the generated source is PDF-clean by default: "
            "fonts, colours and line spacing stay in the editor. Use "
            "<i>View → Preserve visual formatting</i> only for HTML output. Quarto files "
            "render with Quarto; R Markdown files render with rmarkdown.<br><br>"
            "<b>Work log</b><br>"
            "Type in the Work log tab and press Ctrl+Enter to append a timestamped entry to the "
            "designated log file. The log file can be changed with the save button in that tab.<br><br>"
            "<b>AI chat</b><br>"
            "Configure an OpenAI-compatible endpoint in Settings, then ask a question. "
            "Every request, error and cancellation is appended to ai-usage.jsonl. "
            "Use Insert reply to place an answer at the cursor for review.<br><br>"
            "<b>Zotero</b><br>"
            "In R Markdown or Quarto mode, link a Better BibTeX .bib or CSL .json export in "
            "Settings, then use Ctrl+Alt+Z to insert citations. The bibliography is added to "
            "YAML on first use.<br><br>"
            "<b>Shortcuts</b><br>"
            "Ctrl+B / I / U — emphasis &nbsp;·&nbsp; Ctrl+K — link &nbsp;·&nbsp; "
            "Ctrl+Alt+1…4 — headings &nbsp;·&nbsp; Ctrl+Alt+C — R chunk &nbsp;·&nbsp; "
            "Ctrl+Alt+R — inline R &nbsp;·&nbsp; Ctrl+Shift+O — open folder &nbsp;·&nbsp; "
            "Ctrl+Shift+P — workspace panel &nbsp;·&nbsp; F1 — guide"
        )

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------
    def _show_editor_menu(self, position) -> None:
        menu = self.editor.createStandardContextMenu()
        menu.addSeparator()
        for action in (self.action_bold, self.action_italic, self.action_underline, self.action_strike):
            menu.addAction(action)
        menu.addSeparator()
        menu.addAction(self.action_link)
        if self.editor.textCursor().currentTable() is not None:
            table_menu = menu.addMenu("Table")
            table_menu.addAction(self.action_table_row_above)
            table_menu.addAction(self.action_table_row_below)
            table_menu.addAction(self.action_table_col_left)
            table_menu.addAction(self.action_table_col_right)
            table_menu.addSeparator()
            table_menu.addAction(self.action_table_del_row)
            table_menu.addAction(self.action_table_del_col)
            table_menu.addAction(self.action_table_delete)
        if self._mode != MODE_MARKDOWN:
            menu.addAction(self.action_chunk)
        menu.exec(self.editor.mapToGlobal(position))
        menu.deleteLater()

    # ------------------------------------------------------------------
    # Miscellaneous
    # ------------------------------------------------------------------
    def open_demo(self) -> None:
        sample = paths.sample_path()
        if sample is not None:
            self.open_path(sample)
            self.statusBar().showMessage("Markdown sample opened", 3000)

    def open_rmd_demo(self) -> None:
        sample = paths.rmd_sample_path()
        if sample is not None:
            self.open_path(sample)
            self.statusBar().showMessage("R Markdown sample opened", 3000)

    def open_quarto_demo(self) -> None:
        sample = paths.quarto_sample_path()
        if sample is not None:
            self.open_path(sample)
            self.side_tabs.setCurrentIndex(0)
            self._set_project_root(sample.parent)
            self.statusBar().showMessage("Quarto sample project opened", 3500)

    def selftest(self) -> bool:
        from tempfile import TemporaryDirectory

        def write_sample(path: Path) -> str:
            cursor = self.editor.textCursor()
            cursor.insertText("Hello ")
            fmt = QTextCharFormat(default_char_format(self.defaults))
            fmt.setFontWeight(QFont.Weight.Bold)
            cursor.insertText("world", fmt)
            cursor.insertBlock()
            blocks.insert_inline_code(cursor, "r 1 + 1", self.defaults)
            self.path = path
            self.editor.set_base_path(path.parent)
            self.sync.reset(path, "")
            self._force_next_save = True
            if not self._write_to_path(force=True, silent=True):
                raise RuntimeError("write failed")
            return path.read_text(encoding="utf-8")

        try:
            with TemporaryDirectory() as folder:
                self._new_document(first=True, mode=MODE_MARKDOWN)
                if self._mode != MODE_MARKDOWN or self.front_edit.toPlainText():
                    return False
                markdown = write_sample(Path(folder) / "selftest.md")
                if markdown.lstrip().startswith("---") or 'title: "Selftest"' in markdown:
                    return False
                if "**world**" not in markdown or "`r 1 + 1`" not in markdown:
                    return False

                self._new_document(first=True, mode=MODE_RMD)
                self.front_edit.setPlainText(self._default_yaml("Selftest"))
                rmd = write_sample(Path(folder) / "selftest.Rmd")
                return (
                    "**world**" in rmd
                    and 'title: "Selftest"' in rmd
                    and "`r 1 + 1`" in rmd
                )
        except Exception:
            return False


def _rendered_css() -> str:
    return """
    body { color: #f2ebdd; background-color: #121418; font-family: Georgia; font-size: 11pt; }
    p { margin-top: 3px; margin-bottom: 8px; }
    h1 { color: #f7efdf; font-size: 24pt; font-weight: bold; margin-top: 8px; margin-bottom: 8px; }
    h2 { color: #f7efdf; font-size: 19pt; font-weight: bold; margin-top: 14px; margin-bottom: 6px; }
    h3 { color: #f7efdf; font-size: 15pt; font-weight: bold; margin-top: 12px; margin-bottom: 5px; }
    h4 { color: #f7efdf; font-size: 13pt; font-weight: bold; }
    a { color: #7da7d9; text-decoration: underline; }
    code { font-family: Consolas; color: #e6cda3; background-color: #292c31; }
    pre { font-family: Consolas; color: #d8d0c2; background-color: #171a1e; }
    blockquote { color: #cfc7b8; background-color: #1b1e22; margin-left: 14px; }
    th { background-color: #262a30; color: #f7efdf; font-weight: bold; }
    th, td { border: 1px solid #343941; padding: 4px 7px; }
    table { border-collapse: collapse; }
    .underline { text-decoration: underline; }
    .mark { background-color: #6b5427; color: #fff7e6; }
    """


def _preview_html(title: str, fragment: str, base_uri: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<base href="{html.escape(base_uri, quote=True)}">
<style>
  :root {{ color-scheme: dark; }}
  body {{
    background: #111316; color: #f2ebdd;
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 17px; line-height: 1.68;
    max-width: 820px; margin: 0 auto; padding: 52px 28px 100px;
  }}
  h1, h2, h3, h4 {{ font-family: 'Segoe UI', sans-serif; color: #f7efdf; line-height: 1.22; margin-top: 1.6em; }}
  h1 {{ font-size: 2.1em; border-bottom: 1px solid #2a2e34; padding-bottom: .25em; }}
  h2 {{ font-size: 1.55em; }} h3 {{ font-size: 1.25em; }}
  a {{ color: #7da7d9; }}
  p {{ margin: 0 0 1em; }}
  strong {{ color: #fff7e6; }}
  code {{ font-family: Consolas, 'Cascadia Mono', monospace; font-size: .88em; background: #23262b; color: #e6cda3; padding: 2px 5px; border-radius: 4px; }}
  pre {{ background: #171a1e; border: 1px solid #2a2e34; border-radius: 9px; padding: 16px 18px; overflow: auto; line-height: 1.45; }}
  pre code {{ background: transparent; padding: 0; color: #d8d0c2; }}
  blockquote {{ margin: 1.4em 0; padding: 12px 18px; border-left: 3px solid #d3a35f; background: #1b1e22; color: #cfc7b8; }}
  blockquote p:last-child {{ margin-bottom: 0; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1.6em 0; font-family: 'Segoe UI', sans-serif; font-size: .92em; }}
  th, td {{ border: 1px solid #343941; padding: 8px 11px; text-align: left; }}
  th {{ background: #262a30; color: #f7efdf; }}
  tr:nth-child(even) td {{ background: #191c20; }}
  img {{ max-width: 100%; border-radius: 8px; }}
  hr {{ border: none; border-top: 1px solid #343941; margin: 2em 0; }}
  .underline {{ text-decoration: underline; }}
  .mark {{ background: #6b5427; color: #fff7e6; padding: 0 2px; }}
  .smallcaps {{ font-variant: small-caps; }}
  .math {{ font-family: 'Cambria Math', serif; }}
  .footnotes {{ font-size: .9em; color: #b7afa2; }}
</style>
</head>
<body>
{fragment}
</body>
</html>
"""
