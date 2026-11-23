"""Minimal OpenAI-compatible chat client using QtNetwork."""
from __future__ import annotations

import json
import uuid
from typing import Any

from PySide6.QtCore import QByteArray, QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest


def chat_endpoint(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return ""
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


class AIClient(QObject):
    finished = Signal(str, dict)
    failed = Signal(str, str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.manager = QNetworkAccessManager(self)
        self._reply: QNetworkReply | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)
        self._cancelled = False
        self._timed_out = False
        self._done = False
        self.request_id = ""

    @property
    def busy(self) -> bool:
        return self._reply is not None

    def complete(
        self,
        base_url: str,
        model: str,
        api_key: str,
        messages: list[dict[str, Any]],
        timeout_ms: int = 180000,
    ) -> str:
        if self._reply is not None:
            self.cancel()
        self._cancelled = False
        self._timed_out = False
        self._done = False
        self.request_id = uuid.uuid4().hex
        endpoint = chat_endpoint(base_url)
        if not endpoint:
            self._fail("No AI base URL is configured.", "error")
            return self.request_id
        if not model.strip():
            self._fail("No AI model is configured.", "error")
            return self.request_id
        request = QNetworkRequest(QUrl(endpoint))
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        request.setRawHeader(b"Accept", b"application/json")
        request.setRawHeader(b"User-Agent", b"Rmd-Studio/0.3")
        if api_key:
            request.setRawHeader(b"Authorization", ("Bearer " + api_key).encode("utf-8"))
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        reply = self.manager.post(request, QByteArray(json.dumps(payload, ensure_ascii=False).encode("utf-8")))
        self._reply = reply
        self._timer.start(timeout_ms)
        reply.finished.connect(self._on_finished)
        return self.request_id

    def cancel(self) -> None:
        if self._reply is None:
            return
        self._cancelled = True
        self._timer.stop()
        self._reply.abort()

    def _on_timeout(self) -> None:
        if self._reply is not None:
            self._timed_out = True
            self._timer.stop()
            self._cancelled = True
            self._reply.abort()

    def _on_finished(self) -> None:
        if self._done:
            return
        self._done = True
        self._timer.stop()
        reply = self._reply
        self._reply = None
        if reply is None:
            return
        try:
            data = bytes(reply.readAll())
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            network_error = reply.error()
            error_text = reply.errorString()
        finally:
            reply.deleteLater()
        if self._cancelled:
            if self._timed_out:
                self.failed.emit("The AI request timed out.", "error")
            else:
                self.failed.emit("Request cancelled.", "cancelled")
            return
        text = data.decode("utf-8", "replace")
        if network_error != QNetworkReply.NetworkError.NoError and not data:
            self.failed.emit(error_text or "Network request failed.", "error")
            return
        try:
            payload = json.loads(text) if text else {}
        except ValueError:
            self.failed.emit(text[:1000] or "The AI endpoint returned an invalid response.", "error")
            return
        if status is not None and int(status) >= 400:
            message = _error_message(payload, text)
            self.failed.emit(f"HTTP {int(status)}: {message}", "error")
            return
        content = _content_from_payload(payload)
        if not content:
            message = _error_message(payload, text)
            self.failed.emit(message or "The AI endpoint returned an empty response.", "error")
            return
        usage = payload.get("usage") if isinstance(payload, dict) else {}
        if not isinstance(usage, dict):
            usage = {}
        self.finished.emit(content.strip(), usage)

    def _fail(self, message: str, status: str) -> None:
        if self._cancelled:
            status = "cancelled"
        self.failed.emit(message, status)


def _content_from_payload(payload: dict) -> str:
    if not isinstance(payload, dict):
        return ""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message") if isinstance(first, dict) else None
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    if isinstance(item.get("text"), str):
                        parts.append(item["text"])
                    elif isinstance(item.get("content"), str):
                        parts.append(item["content"])
            return "".join(parts)
    text = first.get("text")
    return text if isinstance(text, str) else ""


def _error_message(payload: Any, fallback: str) -> str:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
        if isinstance(payload.get("message"), str):
            return payload["message"].strip()
    return (fallback or "The AI endpoint returned an error.").strip()[:1000]
