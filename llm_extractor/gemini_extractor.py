"""Gemini (Google AI) path — same schema/prompt/filters as the Claude and Ollama
paths, but calls the Gemini REST API directly via `requests` (no SDK needed).

Set GOOGLE_API_KEY in your environment before running:
    $env:GOOGLE_API_KEY = "AIza..."

Usage:
    python -m llm_extractor.gemini_runner --folder "Validation Bulletins" --out out.csv
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import extract  # noqa: E402

from .schema import BulletinExtraction  # noqa: E402
from .prompt import build_system_prompt, few_shot_messages  # noqa: E402
from .grounding import apply_grounding_filter  # noqa: E402
from .extractor import (  # noqa: E402
    gather_summary_text,
    system_to_row,
    keep_system,
    _bulletin_date,
)

DEFAULT_MODEL = "gemini-2.0-flash"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
TIMEOUT = 120  # seconds per request


def _build_contents(system_prompt: str, summary_text: str, date: str | None) -> list[dict]:
    """Build the Gemini `contents` array from the system prompt + few-shot messages."""
    contents: list[dict] = []

    # Gemini doesn't have a system role in the standard chat API — prepend to first user turn.
    few_shot = few_shot_messages()  # [user, assistant, user, assistant, ...]

    # First user turn: system prompt + first few-shot user message
    first_user = few_shot[0]["content"] if few_shot else ""
    contents.append({
        "role": "user",
        "parts": [{"text": f"{system_prompt}\n\n---\n\n{first_user}"}],
    })

    # Remaining few-shot turns
    for msg in few_shot[1:]:
        role = "model" if msg["role"] == "assistant" else "user"
        contents.append({
            "role": role,
            "parts": [{"text": msg["content"]}],
        })

    # Actual bulletin
    contents.append({
        "role": "user",
        "parts": [{"text": f"Bulletin date: {date or 'unknown'}\n\nSummary text:\n{summary_text}"}],
    })

    return contents


def extract_bulletin_gemini(
    api_key: str,
    path: Path,
    system_prompt: str,
    model: str = DEFAULT_MODEL,
) -> list[dict]:
    """Extract one bulletin via the Gemini API. Returns filtered CSV rows."""
    paragraphs = extract.read_docx_paragraphs(path)
    summary_text = gather_summary_text(paragraphs)
    if not summary_text.strip():
        return []

    date = _bulletin_date(paragraphs, path)
    contents = _build_contents(system_prompt, summary_text, date)

    schema = BulletinExtraction.model_json_schema()

    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": 0.0,
            "responseMimeType": "application/json",
            "responseSchema": schema,
        },
    }

    url = f"{GEMINI_API_BASE}/{model}:generateContent?key={api_key}"
    resp = requests.post(url, json=payload, timeout=TIMEOUT)
    resp.raise_for_status()

    data = resp.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        extraction = BulletinExtraction.model_validate_json(text)
    except (KeyError, IndexError, ValueError) as exc:
        print(f"    [gemini] parse error: {exc}")
        return []

    grounded, ungrounded = apply_grounding_filter(extraction.systems, summary_text)
    if ungrounded:
        names = ", ".join(f"{s.weather_system.value}/{s.region or '?'}" for s in ungrounded)
        print(f"    [grounding] dropped {len(ungrounded)}: {names}")

    return [
        system_to_row(system, date, path.name)
        for system in grounded
        if keep_system(system)
    ]
