"""Windows DPAPI storage for the AI API key.

The key is encrypted for the current Windows user and stored base64-encoded in
QSettings. It is never written to the AI usage log or any other file in plain
text.
"""
from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


_CRYPTPROTECT_UI_FORBIDDEN = 0x01


def _make_blob(data: bytes):
    buffer = ctypes.create_string_buffer(data)
    blob = _DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    return blob, buffer


def protect(text: str) -> str:
    if not text:
        return ""
    if not hasattr(ctypes, "windll"):
        raise RuntimeError("Secure credential storage is only available on Windows.")
    data = text.encode("utf-8")
    in_blob, _keep_in = _make_blob(data)
    out_blob = _DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    result = crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    )
    if not result:
        raise OSError("Windows DPAPI could not encrypt the API key.")
    try:
        encrypted = ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)
    return base64.b64encode(encrypted).decode("ascii")


def unprotect(encoded: str) -> str:
    if not encoded:
        return ""
    if not hasattr(ctypes, "windll"):
        raise RuntimeError("Secure credential storage is only available on Windows.")
    try:
        data = base64.b64decode(encoded)
    except ValueError:
        return ""
    in_blob, _keep_in = _make_blob(data)
    out_blob = _DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    result = crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    )
    if not result:
        return ""
    try:
        plain = ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)
    return plain.decode("utf-8", "replace")


def save_key(settings, key: str) -> None:
    if key:
        settings.setValue("ai_api_key_dpapi", protect(key))
    else:
        settings.remove("ai_api_key_dpapi")


def load_key(settings) -> str:
    try:
        return unprotect(str(settings.value("ai_api_key_dpapi", "") or ""))
    except Exception:
        return ""


def clear_key(settings) -> None:
    settings.remove("ai_api_key_dpapi")
