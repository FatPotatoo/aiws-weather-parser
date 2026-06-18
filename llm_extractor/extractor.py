"""Core extraction: bulletin .docx -> Claude structured output -> CSV rows.

Reuses the existing repo helpers for the deterministic parts:
  - extract.read_docx_paragraphs / date parsing
  - extract.height_to_pressure_levels / format_pressure_levels (height -> hPa)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import extract  # noqa: E402

from .grounding import apply_grounding_filter
from .schema import BulletinExtraction, WeatherSystem, db_label

MODEL = "claude-opus-4-8"
MAX_TOKENS = 16000


def _digit_ratio(text: str) -> float:
    if not text:
        return 0.0
    return sum(ch.isdigit() for ch in text) / len(text)


# Markers that begin the NON-synoptic sections of a bulletin (temperatures,
# rainfall tables, forecast tables, signatures). Once any of these appears, the
# synoptic-systems summary is over — stop gathering, or the model drowns in noise.
STOP_MARKERS = (
    "day temperature",
    "temperatures were",
    "maximum temperature",
    "station reported rainfall",
    "total rainfall",
    "realised rainfall",
    "forecast / warning",
    "forecast/warning",
    "districtwise warning",
    "rainfall distribution",
    "weather forecasting division",
    "issued at",
    "fig.",
    "fig ",
    "scientist",
)


def gather_summary_text(paragraphs: list[str], max_chars: int = 8000) -> str:
    """Collect ONLY the synoptic-systems summary prose.

    Starts at the 'Summary of observations recorded' heading and stops at the
    first non-synoptic section (temperatures / rainfall / forecast tables), so
    the model sees the weather systems and nothing else. Multi-paragraph
    summaries are still supported (it keeps going until a STOP_MARKER), but the
    huge rainfall/temperature/forecast tables that follow are excluded.
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
        low = text.lower()
        if any(marker in low for marker in STOP_MARKERS):
            break  # reached the non-synoptic sections — stop
        if len(text) > 15 and _digit_ratio(text) > 0.4:
            continue  # stray numeric table row
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


# A system at height 0 is KEPT only if a level is explicitly stated (surface /
# mean sea level), not when height was simply never mentioned.
_SURFACE_RE = re.compile(r"(mean sea level|sea level|at surface|\bsurface\b|m\.?\s*s\.?\s*l\.?)", re.I)


def keep_system(system: WeatherSystem) -> bool:
    """Apply the cross-check exclusion rules. Returns False to drop the system."""
    if system.is_forecast:
        return False
    if "less marked" in (system.status or "").lower():
        return False
    if (system.height_km or 0.0) > 0.0:
        return True
    # height 0: keep only if explicitly at surface / mean sea level (stated level),
    # drop if the bulletin gave no height/level for it at all.
    text = f"{system.region} {system.pressure_level} {system.status}".lower()
    return bool(_SURFACE_RE.search(text))


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


def extract_bulletin(
    client,
    path: Path,
    system_blocks: list[dict],
    *,
    verbose: bool = False,
) -> tuple[list[dict], object | None]:
    """Extract one bulletin. Returns (rows, usage).

    Pipeline:
      1. LLM extracts all candidate systems (high recall).
      2. Grounding filter drops any system not evidenced in the text
         (precision = 1 guarantee).
      3. keep_system() drops forecast / dissipated systems.
    """
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

    # -- Grounding filter (precision = 1) --
    # Drop any system the LLM invented without textual evidence.
    grounded, ungrounded = apply_grounding_filter(
        extraction.systems, summary_text, verbose=verbose
    )
    if ungrounded:
        names = ", ".join(
            f"{s.weather_system.value}/{s.region or '?'}"
            for s in ungrounded
        )
        print(f"    [grounding] dropped {len(ungrounded)}: {names}")

    rows = [
        system_to_row(system, date, path.name)
        for system in grounded
        if keep_system(system)
    ]
    return rows, response.usage
