from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QSettings

from rmdstudio import ai_log, credentials
from rmdstudio.ai_client import chat_endpoint


def test_api_key_dpapi_roundtrip(tmp_path: Path):
    secret = "sk-test-not-a-real-key"
    encrypted = credentials.protect(secret)
    assert secret not in encrypted
    assert credentials.unprotect(encrypted) == secret
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    credentials.save_key(settings, secret)
    raw = str(settings.value("ai_api_key_dpapi", ""))
    assert secret not in raw
    assert credentials.load_key(settings) == secret
    credentials.clear_key(settings)
    assert credentials.load_key(settings) == ""


def test_ai_usage_log_is_jsonl(tmp_path: Path):
    path = tmp_path / "ai-usage.jsonl"
    ai_log.append_record(path, {"schema": 1, "status": "ok", "model": "mock"})
    ai_log.append_record(path, {"schema": 1, "status": "error", "error": "no key"})
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["status"] == "ok"
    assert json.loads(lines[1])["error"] == "no key"


def test_chat_endpoint():
    assert chat_endpoint("https://api.openai.com/v1") == "https://api.openai.com/v1/chat/completions"
    assert chat_endpoint("http://127.0.0.1:1234/v1/chat/completions") == (
        "http://127.0.0.1:1234/v1/chat/completions"
    )
