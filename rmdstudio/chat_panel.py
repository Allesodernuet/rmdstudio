"""AI chat tab with automatic append-only usage logging."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor, QTextDocumentFragment
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import ai_log, credentials, external, icons, paths, theme
from .ai_client import AIClient
from .ai_settings import DEFAULT_BASE, DEFAULT_MODEL, DEFAULT_SYSTEM

ContextProvider = Callable[[str], tuple[str, str]]
StringProvider = Callable[[], str]
PathProvider = Callable[[], Path | None]
InsertHandler = Callable[[str], None]


class AIChatPanel(QWidget):
    configure_requested = Signal()

    def __init__(
        self,
        settings,
        selection_provider: ContextProvider,
        document_provider: StringProvider,
        document_path_provider: PathProvider,
        project_root_provider: PathProvider,
        insert_markdown: InsertHandler,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.settings = settings
        self.selection_provider = selection_provider
        self.document_provider = document_provider
        self.document_path_provider = document_path_provider
        self.project_root_provider = project_root_provider
        self.insert_markdown = insert_markdown
        self.client = AIClient(self)
        self.client.finished.connect(self._on_finished)
        self.client.failed.connect(self._on_failed)
        self.messages: list[dict] = []
        self.last_response = ""
        self._pending: dict | None = None
        self._build_ui()
        self._show_welcome()
        self.refresh_settings()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)

        header = QHBoxLayout()
        label = QLabel("AI CHAT")
        label.setObjectName("SectionLabel")
        header.addWidget(label)
        self.model_label = QLabel("not configured")
        self.model_label.setObjectName("Hint")
        header.addWidget(self.model_label, 1)
        settings_button = QToolButton(self)
        settings_button.setIcon(icons.icon("settings"))
        settings_button.setToolTip("AI settings")
        settings_button.clicked.connect(self.configure_requested)
        header.addWidget(settings_button)
        clear_button = QToolButton(self)
        clear_button.setText("Clear")
        clear_button.setToolTip("Clear the conversation (the AI log is not deleted)")
        clear_button.clicked.connect(self.clear_chat)
        header.addWidget(clear_button)
        layout.addLayout(header)

        self.chat_view = QTextBrowser(self)
        self.chat_view.setObjectName("ChatView")
        self.chat_view.setOpenExternalLinks(True)
        self.chat_view.setOpenLinks(True)
        self.chat_view.document().setDefaultStyleSheet(
            """
            body { color: #f2ebdd; background-color: #121418; font-family: 'Segoe UI'; font-size: 10.5pt; }
            h1, h2, h3 { color: #f7efdf; }
            code { font-family: Consolas; background-color: #292c31; color: #e6cda3; }
            pre { font-family: Consolas; background-color: #171a1e; color: #d8d0c2; }
            blockquote { color: #cfc7b8; background-color: #1b1e22; }
            a { color: #7da7d9; }
            th { background-color: #262a30; color: #f7efdf; }
            th, td { border: 1px solid #343941; padding: 3px 6px; }
            """
        )
        layout.addWidget(self.chat_view, 1)

        reply_row = QHBoxLayout()
        self.copy_button = QPushButton("Copy reply")
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(self._copy_reply)
        self.insert_button = QPushButton("Insert reply")
        self.insert_button.setEnabled(False)
        self.insert_button.setToolTip("Insert the last answer at the editor cursor as formatted text")
        self.insert_button.clicked.connect(self._insert_reply)
        reply_row.addWidget(self.copy_button)
        reply_row.addWidget(self.insert_button)
        reply_row.addStretch(1)
        layout.addLayout(reply_row)

        context_row = QHBoxLayout()
        context_label = QLabel("Context")
        context_label.setObjectName("Hint")
        context_row.addWidget(context_label)
        self.context_combo = QComboBox(self)
        self.context_combo.addItem("None", "none")
        self.context_combo.addItem("Selection", "selection")
        self.context_combo.addItem("Whole document", "document")
        self.context_combo.setCurrentIndex(0)
        self.context_combo.setToolTip("Document text included with the next message")
        context_row.addWidget(self.context_combo, 1)
        layout.addLayout(context_row)

        self.input = QPlainTextEdit(self)
        self.input.setObjectName("ChatInput")
        self.input.setPlaceholderText("Ask about the document or just chat. Ctrl+Enter sends.")
        self.input.setMaximumHeight(100)
        layout.addWidget(self.input)

        from PySide6.QtGui import QShortcut, QKeySequence

        submit = QShortcut(QKeySequence("Ctrl+Return"), self.input)
        submit.setContext(Qt.ShortcutContext.WidgetShortcut)
        submit.activated.connect(self.send_message)

        bottom = QHBoxLayout()
        self.status_label = QLabel("")
        self.status_label.setObjectName("Hint")
        self.status_label.setWordWrap(True)
        bottom.addWidget(self.status_label, 1)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setVisible(False)
        self.stop_button.clicked.connect(self.cancel_request)
        bottom.addWidget(self.stop_button)
        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("Primary")
        self.send_button.clicked.connect(self.send_message)
        bottom.addWidget(self.send_button)
        layout.addLayout(bottom)

        log_row = QHBoxLayout()
        self.log_label = QLabel("")
        self.log_label.setObjectName("Hint")
        log_row.addWidget(self.log_label, 1)
        choose = QToolButton(self)
        choose.setIcon(icons.icon("save"))
        choose.setToolTip("Choose the AI usage log file")
        choose.clicked.connect(self._choose_log)
        log_row.addWidget(choose)
        open_log = QToolButton(self)
        open_log.setText("Open log")
        open_log.setToolTip("Open the append-only AI usage log")
        open_log.clicked.connect(self._open_log)
        log_row.addWidget(open_log)
        layout.addLayout(log_row)

    def _show_welcome(self) -> None:
        self.chat_view.clear()
        self._append_message(
            "Assistant",
            "Configure an OpenAI-compatible endpoint in Settings, then ask a question.\n\n"
            "Document context is opt-in. Every request will be appended to the AI usage log.",
            error=False,
        )

    # ------------------------------------------------------------------
    # Settings / log paths
    # ------------------------------------------------------------------
    def refresh_settings(self) -> None:
        base = self.settings.value("ai_base_url", DEFAULT_BASE, type=str) or DEFAULT_BASE
        model = self.settings.value("ai_model", DEFAULT_MODEL, type=str) or DEFAULT_MODEL
        host = urlparse(base).netloc or base
        self.model_label.setText(f"{model} · {host}")
        path = self._log_path()
        self.log_label.setText(path.name if path else "AI log unavailable")
        self.log_label.setToolTip(str(path) if path else "")
        if not credentials.load_key(self.settings) and not _is_local(base):
            self.status_label.setText("API key not configured — use the gear button.")
        else:
            self.status_label.setText("Every request is logged automatically.")

    def _log_path(self) -> Path | None:
        setting = self.settings.value("ai_log_path", "", type=str) or ""
        try:
            return ai_log.resolve_ai_log_path(
                self.document_path_provider(),
                self.project_root_provider(),
                setting,
            )
        except Exception:
            return None

    def _choose_log(self) -> None:
        current = self._log_path()
        start = current if current is not None else paths.app_data_dir() / "ai-usage.jsonl"
        filename, _ = QFileDialog.getSaveFileName(
            self, "Choose the AI usage log", str(start),
            "JSON Lines (*.jsonl);;Log files (*.log);;All files (*)"
        )
        if not filename:
            return
        path = Path(filename)
        if not path.suffix:
            path = path.with_suffix(".jsonl")
        self.settings.setValue(
            "ai_log_path",
            ai_log.setting_value_for(path, self.project_root_provider(), self.document_path_provider()),
        )
        self.settings.sync()
        self.refresh_settings()

    def _open_log(self) -> None:
        path = self._log_path()
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch(exist_ok=True)
        except OSError as exc:
            QMessageBox.critical(self, "AI log", f"Could not open the log file:\n{exc}")
            return
        external.open_path(path)

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------
    def _context(self) -> tuple[str, str]:
        mode = self.context_combo.currentData()
        if mode == "selection":
            text = self.selection_provider("selection")
            if text.strip():
                return f"[Document context: current selection]\n{text.strip()}", "selection"
            return "", "none"
        if mode == "document":
            text = self.document_provider()
            if text.strip():
                if len(text) > 16000:
                    text = text[:16000] + "\n\n[Document context truncated at 16,000 characters.]"
                return f"[Document context: current document]\n{text.strip()}", "document"
        return "", "none"

    def send_message(self) -> None:
        if self.client.busy:
            return
        text = self.input.toPlainText().strip()
        if not text:
            return
        base = self.settings.value("ai_base_url", DEFAULT_BASE, type=str) or DEFAULT_BASE
        model = self.settings.value("ai_model", DEFAULT_MODEL, type=str) or DEFAULT_MODEL
        key = credentials.load_key(self.settings)
        if not base.strip():
            self._append_message("System", "No AI base URL is configured. Open AI settings with the gear button.", error=True)
            self.configure_requested.emit()
            return
        if not _is_local(base) and not key:
            self._append_message("System", "No API key is configured. Open AI settings with the gear button.", error=True)
            self.configure_requested.emit()
            return
        if not model.strip():
            self._append_message("System", "No model is configured. Open AI settings with the gear button.", error=True)
            self.configure_requested.emit()
            return
        context_text, context_kind = self._context()
        user_content = (context_text + "\n\n" + text) if context_text else text
        self._append_message("You", text, error=False)
        self.messages.append({"role": "user", "content": user_content})
        self.input.clear()
        system = self.settings.value("ai_system_prompt", DEFAULT_SYSTEM, type=str) or DEFAULT_SYSTEM
        api_messages = [{"role": "system", "content": system}]
        api_messages.extend(self.messages[-12:])
        doc = self.document_path_provider()
        log_path = self._log_path()
        self._pending = {
            "start": time.time(),
            "base": base,
            "model": model,
            "context": context_kind,
            "messages": api_messages,
            "document": doc.name if doc is not None else "",
            "log_path": str(log_path) if log_path is not None else "",
        }
        self.send_button.setEnabled(False)
        self.stop_button.setVisible(True)
        self.status_label.setText("Waiting for the model…")
        request_id = self.client.complete(base, model, key, api_messages)
        self._pending["request_id"] = request_id

    def cancel_request(self) -> None:
        self.status_label.setText("Cancelling…")
        self.client.cancel()

    def _on_finished(self, content: str, usage: dict) -> None:
        if self._pending is None:
            return
        self.last_response = content
        self.messages.append({"role": "assistant", "content": content})
        self._append_message("Assistant", content or "(empty response)", error=False)
        self.copy_button.setEnabled(bool(content))
        self.insert_button.setEnabled(bool(content))
        logged = self._log("ok", content, "", usage)
        self._finish_ui()
        if logged:
            self.status_label.setText("Response received. Every request is logged.")

    def _on_failed(self, message: str, status: str) -> None:
        if self._pending is None:
            return
        self._append_message("System", message, error=True)
        logged = self._log(status, "", message, {})
        self._finish_ui()
        if logged:
            self.status_label.setText(
                "Request cancelled." if status == "cancelled" else "Request failed. See the message above."
            )

    def _finish_ui(self) -> None:
        self._pending = None
        self.send_button.setEnabled(True)
        self.stop_button.setVisible(False)

    def _log(self, status: str, response: str, error: str, usage: dict) -> bool:
        pending = self._pending
        if pending is None:
            return False
        path = Path(pending["log_path"]) if pending.get("log_path") else self._log_path()
        if path is None:
            self.status_label.setText("AI log path unavailable.")
            return False
        log_content = bool(self.settings.value("ai_log_content", True, type=bool))
        record = {
            "schema": 1,
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "kind": "chat",
            "request_id": pending.get("request_id", ""),
            "status": status,
            "base_url": pending.get("base", ""),
            "model": pending.get("model", ""),
            "context": pending.get("context", "none"),
            "latency_ms": round((time.time() - float(pending.get("start", time.time()))) * 1000),
            "document": pending.get("document", ""),
            "usage": usage if isinstance(usage, dict) else {},
        }
        if log_content:
            record["messages"] = pending.get("messages", [])
            record["response"] = response
        if error:
            record["error"] = error
        try:
            ai_log.append_record(path, record)
        except OSError as exc:
            self.status_label.setText(f"AI log write failed: {exc}")
            return False
        self.log_label.setText(path.name)
        self.log_label.setToolTip(str(path))
        return True

    # ------------------------------------------------------------------
    # Reply actions
    # ------------------------------------------------------------------
    def _copy_reply(self) -> None:
        if not self.last_response:
            return
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self.last_response)
        self.status_label.setText("Reply copied.")

    def _insert_reply(self) -> None:
        if not self.last_response:
            return
        self.insert_markdown(self.last_response)
        self.status_label.setText("Reply inserted at the editor cursor.")

    def clear_chat(self) -> None:
        if self.client.busy:
            self.client.cancel()
        self.messages = []
        self.last_response = ""
        self.copy_button.setEnabled(False)
        self.insert_button.setEnabled(False)
        self._show_welcome()
        self.status_label.setText("Conversation cleared. The AI log was not deleted.")

    def shutdown(self) -> None:
        if self.client.busy:
            self._log("cancelled", "", "Application closed during the request.", {})
            self._pending = None
            self.client.cancel()

    # ------------------------------------------------------------------
    # Transcript rendering
    # ------------------------------------------------------------------
    def _append_message(self, role: str, text: str, error: bool = False) -> None:
        cursor = QTextCursor(self.chat_view.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if not self.chat_view.document().isEmpty():
            cursor.insertBlock()
        fmt = QTextCharFormat()
        fmt.setFontWeight(700)
        fmt.setForeground(QColor(theme.RED if error else theme.ACCENT))
        cursor.insertText(role.upper() + "\n", fmt)
        if text:
            try:
                fragment = QTextDocumentFragment.fromMarkdown(text)
                cursor.insertFragment(fragment)
            except Exception:
                cursor.insertText(text)
        cursor.insertBlock()
        self.chat_view.setTextCursor(cursor)
        self.chat_view.verticalScrollBar().setValue(self.chat_view.verticalScrollBar().maximum())


def _is_local(base_url: str) -> bool:
    host = (urlparse(base_url).hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "::1")
