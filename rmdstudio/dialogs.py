"""Small dialogs used by the main window."""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QRegularExpression, QSettings, Qt
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from . import external, icons, theme


class BaseDialog(QDialog):
    def __init__(self, title: str, parent: QWidget | None = None, width: int = 440):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(width)
        self.setModal(True)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(20, 18, 20, 16)
        self._layout.setSpacing(12)
        title_label = QLabel(title)
        title_label.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {theme.TEXT};")
        self._layout.addWidget(title_label)
        self.form = QFormLayout()
        self.form.setContentsMargins(0, 4, 0, 4)
        self.form.setSpacing(10)
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._layout.addLayout(self.form)

    def add_buttons(self, ok_text: str = "OK", cancel_text: str = "Cancel") -> QDialogButtonBox:
        box = QDialogButtonBox()
        ok = box.addButton(ok_text, QDialogButtonBox.ButtonRole.AcceptRole)
        ok.setObjectName("Primary")
        if cancel_text:
            box.addButton(cancel_text, QDialogButtonBox.ButtonRole.RejectRole)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        self._layout.addWidget(box)
        self._buttons = box
        return box


class LinkDialog(BaseDialog):
    def __init__(self, parent: QWidget | None = None, text: str = "", url: str = ""):
        super().__init__("Insert link", parent)
        self.text_edit = QLineEdit(text)
        self.text_edit.setPlaceholderText("Visible text (optional)")
        self.url_edit = QLineEdit(url)
        self.url_edit.setPlaceholderText("https://example.com")
        self.form.addRow("Text", self.text_edit)
        self.form.addRow("Address", self.url_edit)
        self.add_buttons("Insert link")

    def values(self) -> tuple[str, str]:
        return self.text_edit.text().strip(), self.url_edit.text().strip()


class ImageDialog(BaseDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__("Insert image", parent, 520)
        path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("PNG, JPG, GIF, SVG...")
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse)
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse)
        wrapper = QWidget()
        wrapper.setLayout(path_row)
        self.form.addRow("File", wrapper)
        self.alt_edit = QLineEdit()
        self.alt_edit.setPlaceholderText("Describe the image for accessibility")
        self.form.addRow("Alt text", self.alt_edit)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(0, 100)
        self.width_spin.setValue(80)
        self.width_spin.setSuffix(" %")
        self.width_spin.setSpecialValueText("Natural size")
        self.form.addRow("Width", self.width_spin)
        hint = QLabel("Images are copied into an assets/ folder beside the .Rmd file.")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        self._layout.addWidget(hint)
        self.add_buttons("Insert image")

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose an image", "", "Images (*.png *.jpg *.jpeg *.gif *.webp *.svg);;All files (*)"
        )
        if path:
            self.path_edit.setText(path)
            if not self.alt_edit.text():
                self.alt_edit.setText(Path(path).stem.replace("_", " "))

    def values(self) -> tuple[str, str, int]:
        return self.path_edit.text().strip(), self.alt_edit.text().strip(), self.width_spin.value()


class TableDialog(BaseDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__("Insert table", parent)
        self.rows_spin = QSpinBox()
        self.rows_spin.setRange(1, 50)
        self.rows_spin.setValue(3)
        self.cols_spin = QSpinBox()
        self.cols_spin.setRange(1, 20)
        self.cols_spin.setValue(3)
        self.header_check = QCheckBox("Use the first row as a header")
        self.header_check.setChecked(True)
        self.form.addRow("Rows", self.rows_spin)
        self.form.addRow("Columns", self.cols_spin)
        self.form.addRow("", self.header_check)
        self.add_buttons("Insert table")

    def values(self) -> tuple[int, int, bool]:
        return self.rows_spin.value(), self.cols_spin.value(), self.header_check.isChecked()


class ChunkDialog(BaseDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__("Insert R code chunk", parent, 520)
        self.label_edit = QLineEdit("chunk")
        self.label_edit.setPlaceholderText("Optional chunk label")
        self.form.addRow("Label", self.label_edit)
        options_row = QHBoxLayout()
        self.echo_check = QCheckBox("echo")
        self.eval_check = QCheckBox("eval")
        self.warning_check = QCheckBox("warning")
        self.message_check = QCheckBox("message")
        for check in (self.echo_check, self.eval_check, self.warning_check, self.message_check):
            check.setChecked(True)
            options_row.addWidget(check)
        options_row.addStretch(1)
        wrapper = QWidget()
        wrapper.setLayout(options_row)
        self.form.addRow("Options", wrapper)
        self.code_edit = QPlainTextEdit()
        self.code_edit.setPlaceholderText("Code in the chunk")
        self.code_edit.setPlainText("# your code")
        self.code_edit.setMinimumHeight(110)
        self.form.addRow("Code", self.code_edit)
        self.preview = QLabel()
        self.preview.setObjectName("Chip")
        self._layout.addWidget(self.preview)
        self.label_edit.textChanged.connect(self._update_preview)
        for check in (self.echo_check, self.eval_check, self.warning_check, self.message_check):
            check.toggled.connect(self._update_preview)
        self._update_preview()
        self.add_buttons("Insert chunk")

    def _update_preview(self) -> None:
        self.preview.setText(self.header())

    def header(self) -> str:
        label = self.label_edit.text().strip().replace(" ", "-")
        options = []
        if not self.echo_check.isChecked():
            options.append("echo=FALSE")
        if not self.eval_check.isChecked():
            options.append("eval=FALSE")
        if not self.warning_check.isChecked():
            options.append("warning=FALSE")
        if not self.message_check.isChecked():
            options.append("message=FALSE")
        parts = [label] if label else []
        parts.extend(options)
        return "{r" + (", " + ", ".join(parts) if parts else "") + "}"

    def values(self) -> tuple[str, str]:
        return self.header(), self.code_edit.toPlainText()


class SpacingDialog(BaseDialog):
    def __init__(self, parent: QWidget | None = None, line: float = 1.0,
                 before: float = 0.0, after: float = 0.0):
        super().__init__("Paragraph spacing", parent)
        self.line_combo = QComboBox()
        for value in (1.0, 1.15, 1.5, 2.0):
            self.line_combo.addItem(f"{value:g}", value)
        self._select(self.line_combo, line)
        self.before_spin = QSpinBox()
        self.before_spin.setRange(0, 72)
        self.before_spin.setValue(int(round(before)))
        self.before_spin.setSuffix(" pt")
        self.after_spin = QSpinBox()
        self.after_spin.setRange(0, 72)
        self.after_spin.setValue(int(round(after)))
        self.after_spin.setSuffix(" pt")
        self.form.addRow("Line spacing", self.line_combo)
        self.form.addRow("Space before", self.before_spin)
        self.form.addRow("Space after", self.after_spin)
        hint = QLabel("Line and paragraph spacing are stored as Pandoc HTML styles. "
                      "They render in HTML output; PDF and Word output ignore them.")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        self._layout.addWidget(hint)
        self.add_buttons("Apply")

    @staticmethod
    def _select(combo: QComboBox, value: float) -> None:
        for index in range(combo.count()):
            if abs(float(combo.itemData(index)) - value) < 0.001:
                combo.setCurrentIndex(index)
                return

    def values(self) -> tuple[float, float, float]:
        return float(self.line_combo.currentData()), float(self.before_spin.value()), float(self.after_spin.value())


class FindReplaceDialog(QDialog):
    def __init__(self, editor: QTextEdit, parent: QWidget | None = None):
        super().__init__(parent)
        self.editor = editor
        self.setWindowTitle("Find & replace")
        self.setMinimumWidth(480)
        self.setModal(False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)
        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText("Find")
        self.replace_edit = QLineEdit()
        self.replace_edit.setPlaceholderText("Replace with")
        layout.addWidget(self.find_edit)
        layout.addWidget(self.replace_edit)
        options = QHBoxLayout()
        self.case_check = QCheckBox("Match case")
        self.word_check = QCheckBox("Whole words")
        self.back_check = QCheckBox("Search backwards")
        options.addWidget(self.case_check)
        options.addWidget(self.word_check)
        options.addWidget(self.back_check)
        options.addStretch(1)
        layout.addLayout(options)
        buttons = QHBoxLayout()
        prev_button = QPushButton("Previous")
        next_button = QPushButton("Next")
        replace_button = QPushButton("Replace")
        all_button = QPushButton("Replace all")
        close_button = QPushButton("Close")
        prev_button.clicked.connect(lambda: self.find(backward=True))
        next_button.clicked.connect(lambda: self.find(backward=False))
        replace_button.clicked.connect(self.replace)
        all_button.clicked.connect(self.replace_all)
        close_button.clicked.connect(self.close)
        for widget in (prev_button, next_button, replace_button, all_button):
            buttons.addWidget(widget)
        buttons.addStretch(1)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)
        self.status = QLabel("")
        self.status.setObjectName("Hint")
        layout.addWidget(self.status)
        self.find_edit.returnPressed.connect(lambda: self.find(backward=self.back_check.isChecked()))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        selected = self.editor.textCursor().selectedText()
        if selected and "\u2029" not in selected:
            self.find_edit.setText(selected)
        self.find_edit.setFocus()
        self.find_edit.selectAll()

    def _cursor_after_search(self, start: QTextCursor, backward: bool) -> QTextCursor:
        doc = self.editor.document()
        flags = QTextDocument.FindFlag(0)
        if self.case_check.isChecked():
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if backward:
            flags |= QTextDocument.FindFlag.FindBackward
        term = self.find_edit.text()
        if not term:
            return QTextCursor()
        if self.word_check.isChecked():
            pattern = r"\b" + re.escape(term) + r"\b"
            regex = QRegularExpression(pattern)
            if not self.case_check.isChecked():
                regex.setPatternOptions(QRegularExpression.PatternOption.CaseInsensitiveOption)
            return doc.find(regex, start, flags)
        return doc.find(term, start, flags)

    def find(self, backward: bool = False) -> bool:
        term = self.find_edit.text()
        if not term:
            self.status.setText("Type something to find.")
            return False
        cursor = self.editor.textCursor()
        found = self._cursor_after_search(cursor, backward)
        if found.isNull():
            wrap = QTextCursor(self.editor.document())
            wrap.movePosition(QTextCursor.MoveOperation.End if backward else QTextCursor.MoveOperation.Start)
            found = self._cursor_after_search(wrap, backward)
        if found.isNull():
            self.status.setText("No matches.")
            return False
        self.editor.setTextCursor(found)
        self.editor.setFocus()
        self.status.setText("")
        return True

    def replace(self) -> None:
        cursor = self.editor.textCursor()
        term = self.find_edit.text()
        selected = cursor.selectedText()
        matches = selected == term if self.case_check.isChecked() else selected.lower() == term.lower()
        if not cursor.hasSelection() or not matches:
            self.find(backward=False)
            return
        cursor.insertText(self.replace_edit.text())
        self.find(backward=False)

    def replace_all(self) -> None:
        term = self.find_edit.text()
        if not term:
            self.status.setText("Type something to find.")
            return
        replacement = self.replace_edit.text()
        cursor = QTextCursor(self.editor.document())
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        count = 0
        document = self.editor.document()
        document.beginEditBlock()
        try:
            while True:
                found = self._cursor_after_search(cursor, backward=False)
                if found.isNull():
                    break
                found.insertText(replacement)
                count += 1
                cursor = found
                if cursor.position() >= document.characterCount() - 1:
                    break
        finally:
            document.endEditBlock()
        self.status.setText(f"Replaced {count} occurrence{'s' if count != 1 else ''}.")


class SettingsDialog(BaseDialog):
    def __init__(self, settings: QSettings, parent: QWidget | None = None):
        super().__init__("Settings", parent, 620)
        self.settings = settings
        self.autosave_check = QCheckBox("Autosave to the .Rmd file while typing")
        self.autosave_check.setChecked(settings.value("autosave", True, type=bool))
        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(250, 5000)
        self.delay_spin.setSingleStep(250)
        self.delay_spin.setValue(settings.value("autosave_ms", 800, type=int))
        self.delay_spin.setSuffix(" ms")
        self.visual_check = QCheckBox("Preserve fonts, colours and spacing as Pandoc HTML styles")
        self.visual_check.setChecked(settings.value("preserve_visual", True, type=bool))
        self.form.addRow("", self.autosave_check)
        self.form.addRow("Autosave delay", self.delay_spin)
        self.form.addRow("", self.visual_check)

        self.pandoc_edit = self._path_row("Pandoc", settings.value("pandoc_path", "", type=str), external.find_pandoc())
        self.rstudio_edit = self._path_row("RStudio", settings.value("rstudio_path", "", type=str), external.find_rstudio())
        self.rscript_edit = self._path_row("Rscript", settings.value("rscript_path", "", type=str), external.find_rscript())
        hint = QLabel("RStudio and Rscript are only needed for the RStudio/Knit buttons. "
                      "Pandoc is used to import existing Markdown and render browser previews.")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        self._layout.addWidget(hint)
        self.add_buttons("Save settings")

    def _path_row(self, label: str, value: str, detected: str | None) -> QLineEdit:
        row = QHBoxLayout()
        edit = QLineEdit(value)
        edit.setPlaceholderText(detected or "Not found automatically")
        browse = QPushButton("Browse...")
        browse.clicked.connect(lambda: self._browse(edit))
        detect = QPushButton("Detect")
        detect.clicked.connect(lambda: edit.setText(detected or ""))
        row.addWidget(edit, 1)
        row.addWidget(detect)
        row.addWidget(browse)
        wrapper = QWidget()
        wrapper.setLayout(row)
        self.form.addRow(label, wrapper)
        return edit

    def _browse(self, edit: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose executable", "", "Executables (*.exe);;All files (*)")
        if path:
            edit.setText(path)

    def accept(self) -> None:
        self.settings.setValue("autosave", self.autosave_check.isChecked())
        self.settings.setValue("autosave_ms", self.delay_spin.value())
        self.settings.setValue("preserve_visual", self.visual_check.isChecked())
        self.settings.setValue("pandoc_path", self.pandoc_edit.text().strip())
        self.settings.setValue("rstudio_path", self.rstudio_edit.text().strip())
        self.settings.setValue("rscript_path", self.rscript_edit.text().strip())
        self.settings.sync()
        external.clear_cache()
        super().accept()


class AboutDialog(BaseDialog):
    def __init__(self, parent: QWidget | None = None, version: str = ""):
        super().__init__("About Rmd Studio", parent, 460)
        logo = QLabel()
        logo.setPixmap(icons.logo_pixmap(92))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.insertWidget(0, logo)
        body = QLabel(
            f"<b>Rmd Studio {version}</b><br><br>"
            "A graphite word-processor front end for R Markdown.<br><br>"
            "Write with Word-like controls and keep a clean <code>.Rmd</code> file "
            "updated in the background. Formatting that Markdown cannot express is "
            "written as Pandoc HTML attributes.<br><br>"
            "Everything runs locally. No accounts, telemetry or network calls."
        )
        body.setWordWrap(True)
        body.setTextFormat(Qt.TextFormat.RichText)
        body.setStyleSheet(f"color: {theme.MUTED}; font-size: 12px;")
        self._layout.addWidget(body)
        self.add_buttons("Close", "")
