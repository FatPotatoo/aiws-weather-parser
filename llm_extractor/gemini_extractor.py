"""Gemini (Google AI) path — same schema/prompt/filters as the Claude and Ollama
paths, but calls the Gemini REST API directly via `requests` (no SDK needed).

Set GEMINI_API_KEY in your environment before running:
    $env:GEMINI_API_KEY = "AIza..."

Usage:
    python -m llm_extractor.gemini_runner --folder "Validation Bulletins" --out out.csv
"""
from __future__ import annotations

import copy
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

DEFAULT_MODEL = "gemini-3.5-flash"
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


def _build_batch_contents(system_prompt: str, bulletins: list[dict]) -> list[dict]:
    """Build Gemini contents for a batch of bulletins."""
    contents: list[dict] = []
    few_shot = few_shot_messages()

    batch_instructions = (
        "Process each bulletin below separately and return a JSON array of objects. "
        "Each object must include source_file, date, and systems. The systems field "
        "must follow the structured output schema defined by the system prompt."
    )

    first_user = few_shot[0]["content"] if few_shot else ""
    contents.append({
        "role": "user",
        "parts": [{"text": f"{system_prompt}\n\n{batch_instructions}\n\n---\n\n{first_user}"}],
    })

    for msg in few_shot[1:]:
        role = "model" if msg["role"] == "assistant" else "user"
        contents.append({
            "role": role,
            "parts": [{"text": msg["content"]}],
        })

    batch_parts: list[str] = []
    for bulletin in bulletins:
        batch_parts.append(
            f"Bulletin file: {bulletin['source_file']}\n"
            f"Bulletin date: {bulletin['date']}\n\n"
            f"Summary text:\n{bulletin['summary_text']}\n\n---\n"
        )

    batch_parts.append(
        "Return ONLY the JSON array described above. Do not include any "
        "explanatory text outside the JSON."
    )
    contents.append({"role": "user", "parts": [{"text": "\n".join(batch_parts)}]})
    return contents


def _inline_schema_refs(schema: dict) -> dict:
    schema = copy.deepcopy(schema)
    defs = schema.pop("$defs", {})

    def resolve(node):
        if isinstance(node, dict) and "$ref" in node:
            ref = node["$ref"]
            if ref.startswith("#/$defs/"):
                actual = defs.get(ref.split("#/$defs/", 1)[1])
                if actual is None:
                    raise ValueError(f"Unresolved $ref: {ref}")
                return resolve(actual)
            raise ValueError(f"Unsupported $ref: {ref}")

        if isinstance(node, dict):
            return {k: resolve(v) if isinstance(v, (dict, list)) else v for k, v in node.items()}
        if isinstance(node, list):
            return [resolve(v) if isinstance(v, (dict, list)) else v for v in node]
        return node

    return resolve(schema)


def _systems_schema() -> dict:
    """Return the JSON schema for the raw list under BulletinExtraction.systems."""
    extraction_schema = _inline_schema_refs(BulletinExtraction.model_json_schema())
    return extraction_schema["properties"]["systems"]


def _normalize_systems_payload(systems_payload) -> list:
    """Accept both the intended systems list and any nested Gemini wrapper.

    Gemini may return `systems` as a list or as an object containing a `systems`
    property, depending on how the schema was interpreted. Unwrap repeated
    wrappers until the actual list remains.
    """
    while isinstance(systems_payload, dict) and "systems" in systems_payload:
        systems_payload = systems_payload["systems"]
    if systems_payload is None:
        return []
    if isinstance(systems_payload, list):
        return systems_payload
    raise ValueError(f"Unexpected systems payload shape: {type(systems_payload).__name__}")


def _extract_json_array(text: str) -> list:
    try:
        return json.loads(text)
    except ValueError:
        start = text.find("[")
        if start == -1:
            raise
        depth = 0
        for index, char in enumerate(text[start:], start):
            if char == "[":
                depth += 1
            elif char == "]":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : index + 1])
                    except ValueError:
                        break
        raise


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

    # Gemini 2.5 does not accept JSON Schema references like $ref/$defs.
    # Inline all referenced definitions before sending the request.
    schema = _inline_schema_refs(schema)

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
    if not resp.ok:
        error_body = resp.text
        try:
            error_body = json.dumps(resp.json(), indent=2)
        except ValueError:
            pass
        raise requests.HTTPError(
            f"Gemini request failed {resp.status_code} {resp.reason}: {error_body}", response=resp
        )

    data = resp.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        extraction = BulletinExtraction.model_validate_json(text)
    except (KeyError, IndexError, ValueError) as exc:
        print(f"    [gemini] parse error: {exc}")
        print(f"    [gemini] raw response: {json.dumps(data, indent=2)[:2000]}")
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


def extract_bulletins_gemini(
    api_key: str,
    paths: list[Path],
    system_prompt: str,
    model: str = DEFAULT_MODEL,
) -> list[dict]:
    """Extract a batch of bulletins in one Gemini call."""
    bulletins: list[dict] = []
    for path in paths:
        paragraphs = extract.read_docx_paragraphs(path)
        summary_text = gather_summary_text(paragraphs)
        if not summary_text.strip():
            continue
        date = _bulletin_date(paragraphs, path)
        bulletins.append({
            "source_file": path.name,
            "date": date or "unknown",
            "summary_text": summary_text,
        })

    if not bulletins:
        return []

    contents = _build_batch_contents(system_prompt, bulletins)
    systems_schema = _systems_schema()

    batch_schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "source_file": {"type": "string"},
                "date": {"type": "string"},
                "systems": systems_schema,
            },
            "required": ["source_file", "systems"],
        },
    }

    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": 0.0,
            "responseMimeType": "application/json",
            "responseSchema": batch_schema,
        },
    }

    url = f"{GEMINI_API_BASE}/{model}:generateContent?key={api_key}"
    resp = requests.post(url, json=payload, timeout=TIMEOUT)
    if not resp.ok:
        error_body = resp.text
        try:
            error_body = json.dumps(resp.json(), indent=2)
        except ValueError:
            pass
        raise requests.HTTPError(
            f"Gemini request failed {resp.status_code} {resp.reason}: {error_body}", response=resp
        )

    data = resp.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        try:
            extraction = json.loads(text)
        except ValueError:
            extraction = _extract_json_array(text)
    except (KeyError, IndexError, ValueError) as exc:
        print(f"    [gemini] parse error: {exc}")
        print(f"    [gemini] raw response: {json.dumps(data, indent=2)[:2000]}")
        return []

    rows: list[dict] = []
    if not isinstance(extraction, list):
        print("    [gemini] parse error: expected JSON array for batched bulletins")
        return []

    summary_by_source = {bulletin["source_file"]: bulletin["summary_text"] for bulletin in bulletins}
    date_by_source = {bulletin["source_file"]: bulletin["date"] for bulletin in bulletins}

    for item in extraction:
        if not isinstance(item, dict):
            continue
        source_file = item.get("source_file", "")
        date = item.get("date", "") or date_by_source.get(source_file, "")
        systems = _normalize_systems_payload(item.get("systems", []))
        summary_text = summary_by_source.get(source_file, "")
        try:
            bulletin_extraction = BulletinExtraction.model_validate({"systems": systems})
        except Exception as exc:
            print(f"    [gemini] bulletin validation failed for {source_file}: {exc}")
            continue

        grounded, ungrounded = apply_grounding_filter(bulletin_extraction.systems, summary_text)
        if ungrounded:
            names = ", ".join(f"{s.weather_system.value}/{s.region or '?'}" for s in ungrounded)
            print(f"    [grounding] dropped {len(ungrounded)}: {names}")

        rows.extend(
            system_to_row(system, date, source_file)
            for system in grounded
            if keep_system(system)
        )

    return rows
