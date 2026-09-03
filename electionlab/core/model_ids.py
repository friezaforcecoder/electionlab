from __future__ import annotations

OPENAI_DEFAULT_MODEL = "gpt-5.4-mini"


def normalize_openai_model(model: str | None, default: str = OPENAI_DEFAULT_MODEL) -> str:
    cleaned = str(model or "").strip()
    if not cleaned:
        cleaned = default
    return cleaned.lower()
