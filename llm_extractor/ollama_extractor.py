"""Ollama (local LLM) path — same schema/prompt/filters as the Claude path,
but calls a local model via the `ollama` package and its JSON-schema structured
output (`format=<json schema>`) instead of the Anthropic API.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import extract  # noqa: E402

from .schema import BulletinExtraction  # noqa: E402
from .extractor import (  # noqa: E402  (reuse the deterministic helpers + filter)
    gather_summary_text,
    system_to_row,
    keep_system,
    _bulletin_date,
)

DEFAULT_MODEL = "qwen2.5:7b-instruct"
# Context window must hold the system prompt (~1k tok) + bulletin (~3-4k tok) + output.
NUM_CTX = 8192


def _content(response) -> str:
    """Return the assistant text from an ollama ChatResponse (typed or dict)."""
    if isinstance(response, dict):
        return response["message"]["content"]
    return response.message.content


def extract_bulletin_ollama(client, path: Path, system_prompt: str, model: str = DEFAULT_MODEL) -> list[dict]:
    """Extract one bulletin via a local Ollama model. Returns filtered CSV rows."""
    paragraphs = extract.read_docx_paragraphs(path)
    summary_text = gather_summary_text(paragraphs)
    if not summary_text.strip():
        return []

    date = _bulletin_date(paragraphs, path)

    response = client.chat(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"Bulletin date: {date or 'unknown'}\n\nSummary text:\n{summary_text}",
            },
        ],
        format=BulletinExtraction.model_json_schema(),
        options={"temperature": 0, "num_ctx": NUM_CTX},
    )

    try:
        extraction = BulletinExtraction.model_validate_json(_content(response))
    except Exception:
        return []  # malformed JSON from the local model — skip this bulletin

    return [
        system_to_row(system, date, path.name)
        for system in extraction.systems
        if keep_system(system)
    ]
