"""Defaults and presets for the optional AI chat."""
from __future__ import annotations

DEFAULT_BASE = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_SYSTEM = (
    "You are a precise writing and Quarto/R Markdown assistant embedded in a "
    "document editor. Answer concisely. Use Markdown when helpful. Do not claim "
    "to have changed the document; the user will review and insert text manually."
)

PRESETS: list[tuple[str, str, str]] = [
    ("OpenAI", "https://api.openai.com/v1", "gpt-4o-mini"),
    ("OpenRouter", "https://openrouter.ai/api/v1", "openai/gpt-4o-mini"),
    ("LM Studio (local)", "http://127.0.0.1:1234/v1", "local-model"),
    ("Custom", "", ""),
]
