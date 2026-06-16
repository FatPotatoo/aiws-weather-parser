"""Core extraction: bulletin .docx -> Claude structured output -> CSV rows.

Reuses the existing repo helpers for the deterministic parts:
  - extract.read_docx_paragraphs / date parsing
  - extract.height_to_pressure_levels / format_pressure_levels (height -> hPa)
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import extract  # noqa: E402

from .schema import BulletinExtraction, WeatherSystem, db_label

MODEL = "claude-opus-4-8"
MAX_TOKENS = 16000


def _digit_ratio(text: str) -> float:
    if not text:
        return 0.0
    return sum(ch.isdigit() for ch in text) / len(text)


def gather_summary_text(paragraphs: list[str], max_chars: int = 12000) -> str:
    """Collect the synoptic-summary prose, skipping numeric station/rainfall rows.

    Unlike the old extractor (which read only ONE paragraph), this keeps every
    prose paragraph from the summary heading onward, so multi-paragraph
    summaries survive. Digit-heavy lines (station tables) are dropped.
    """
    start = next(
        (i for i, p in enumerate(paragraphs)
         if "summary of observations recorded" in p.lower()),
        0,
    )
    collected: list[str] = []
    total = 0
    for paragraph in paragraphs[start:]:
        text = paragraph.strip()
        if not text:
            continue
        # Station / rainfall table rows are mostly digits — skip, don't stop.
        if len(text) > 15 and _digit_ratio(text) > 0.4:
            continue
        collected.append(text)
        total += len(text)
        if total >= max_chars:
            break
    return "\n".join(collected)


def _resolve_pressure(system: WeatherSystem) -> str:
    """Use the bulletin's explicit pressure level, else derive it from height."""
    if system.pressure_level.strip():
        return system.pressure_level.strip()
    levels = extract.height_to_pressure_levels(system.height_km or 0.0)
    return extract.format_pressure_levels(levels)  # "Surface" when no levels


def _bulletin_date(paragraphs: list[str], path: Path) -> str | None:
    return extract.parse_bulletin_date(paragraphs) or extract.parse_bulletin_date_from_filename(path)


def keep_system(system: WeatherSystem) -> bool:
    """Apply the cross-check exclusion rules. Returns False to drop the system."""
    if system.is_forecast:
        return False
    if "less marked" in (system.status or "").lower():
        return False
    if (system.height_km or 0.0) <= 0.0:  # exclude systems with no height above MSL
        return False
    return True


def system_to_row(system: WeatherSystem, date: str | None, source_file: str) -> dict:
    return {
        "date": date or "",
        "source_file": source_file,
        "weather_system": db_label(system.weather_system),
        "subdivisions": " ; ".join(system.subdivisions),
        "region": system.region,
        "region_original": "",
        "height_km": system.height_km or 0.0,
        "pressure_level": _resolve_pressure(system),
        "status": system.status,
    }


def extract_bulletin(client, path: Path, system_blocks: list[dict]) -> tuple[list[dict], object | None]:
    """Extract one bulletin. Returns (rows, usage); forecast-only systems dropped."""
    paragraphs = extract.read_docx_paragraphs(path)
    summary_text = gather_summary_text(paragraphs)
    if not summary_text.strip():
        return [], None

    date = _bulletin_date(paragraphs, path)

    response = client.messages.parse(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system_blocks,
        messages=[{
            "role": "user",
            "content": f"Bulletin date: {date or 'unknown'}\n\nSummary text:\n{summary_text}",
        }],
        output_format=BulletinExtraction,
        thinking={"type": "adaptive"},
    )

    extraction = response.parsed_output
    if extraction is None:  # refusal or truncated output
        return [], response.usage

    rows = [
        system_to_row(system, date, path.name)
        for system in extraction.systems
        if keep_system(system)
    ]
    return rows, response.usage
