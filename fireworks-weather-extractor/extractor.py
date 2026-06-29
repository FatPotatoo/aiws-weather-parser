from __future__ import annotations

import copy
import json
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from pathlib import Path

import requests

from schema import BulletinExtraction

WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NAMESPACES = {"w": WORD_NAMESPACE}

FIREWORKS_API_URL = "https://api.fireworks.ai/inference/v1/chat/completions"
DEFAULT_MODEL = "accounts/fireworks/models/glm-5p2"
TIMEOUT = 120


def _parse_docx_paragraphs_from_zip(path: Path) -> list[str]:
    with zipfile.ZipFile(path, "r") as archive:
        with archive.open("word/document.xml") as document_xml:
            tree = ET.parse(document_xml)

    paragraphs = []
    for paragraph in tree.iterfind(".//w:p", namespaces=NAMESPACES):
        texts = [node.text for node in paragraph.iterfind(".//w:t", namespaces=NAMESPACES) if node.text]
        if texts:
            paragraphs.append("".join(texts))
    return paragraphs


def read_docx_paragraphs(path: Path) -> list[str]:
    """Read paragraphs from a .docx Word file using XML parsing."""
    if not path.exists():
        raise FileNotFoundError(f"Word file not found: {path}")
    if path.suffix.lower() != ".docx":
        raise ValueError("Only .docx Word files are supported.")

    try:
        return _parse_docx_paragraphs_from_zip(path)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"Invalid .docx file: {path}") from exc
    except PermissionError:
        # Word often locks open files; read from a temporary copy instead.
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            shutil.copy2(path, tmp_path)
            return _parse_docx_paragraphs_from_zip(tmp_path)
        except zipfile.BadZipFile as exc:
            raise ValueError(f"Invalid .docx file: {path}") from exc
        finally:
            tmp_path.unlink(missing_ok=True)


def parse_bulletin_date(paragraphs: list[str]) -> str | None:
    """Extract bulletin date from heading and return ISO date (YYYY-MM-DD)."""
    pattern = re.compile(
        r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s*,?\s*(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{4})\b",
        re.I,
    )
    for paragraph in paragraphs[:10]:
        match = pattern.search(paragraph)
        if not match:
            continue
        day, month_name, year = match.groups()
        clean = f"{int(day):02d} {month_name} {year}"
        try:
            return datetime.strptime(clean, "%d %B %Y").strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def parse_bulletin_date_from_filename(path: Path) -> str | None:
    """Extract bulletin date from filename like 'AIWS 20250608.docx'."""
    match = re.search(r"(20\d{2})(\d{2})(\d{2})", path.stem)
    if not match:
        return None
    year, month, day = match.groups()
    try:
        return datetime(int(year), int(month), int(day)).strftime("%Y-%m-%d")
    except ValueError:
        return None


def _bulletin_date(paragraphs: list[str], path: Path) -> str | None:
    return parse_bulletin_date(paragraphs) or parse_bulletin_date_from_filename(path)


def _digit_ratio(text: str) -> float:
    if not text:
        return 0.0
    return sum(ch.isdigit() for ch in text) / len(text)


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
    """Collect ONLY the synoptic-systems summary prose."""
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


_SURFACE_RE = re.compile(r"(mean sea level|sea level|at surface|\bsurface\b|m\.?\s*s\.?\s*l\.?)", re.I)


def keep_system(system) -> bool:
    """Apply the cross-check exclusion rules. Returns False to drop the system."""
    if system.is_forecast:
        return False
    if "less marked" in (system.status or "").lower():
        return False
    if (system.height_km_min or 0.0) > 0.0 or (system.height_km_max or 0.0) > 0.0:
        return True
    text = f"{system.region} {system.pressure_level} {system.status}".lower()
    return bool(_SURFACE_RE.search(text))


def is_coordinate_region(region: str) -> bool:
    return bool(re.search(r"\balong\s+long\.?", region.lower()))


def parse_coordinate_constraints(region: str) -> tuple[float | None, float | None]:
    """Parse longitude and minimum latitude (north-of) from coordinate region text."""
    text = region.lower()
    lon_match = re.search(r"long\.?\s*([0-9]+(?:\.[0-9]+)?)\s*°?", text)
    lat_match = re.search(r"lat\.?\s*([0-9]+(?:\.[0-9]+)?)\s*°?", text)
    longitude = float(lon_match.group(1)) if lon_match else None
    min_latitude = float(lat_match.group(1)) if lat_match else None
    return longitude, min_latitude


def resolve_coordinate_to_subdivisions(region: str, lon_tolerance: float = 3.5) -> list[str]:
    """
    Map coordinate phrases (e.g. along Long. 89°E north of Lat. 22°N) to IMD subdivisions
    using centroid proximity and latitude constraints.
    """
    longitude, min_latitude = parse_coordinate_constraints(region)
    if longitude is None:
        return []

    subdivisions_path = Path("c:/xampp/htdocs/aiws-weather-parser/data/imd_subdivisions.json")
    if not subdivisions_path.exists():
        return []
    with subdivisions_path.open(encoding="utf-8") as fh:
        subdivisions = json.load(fh)

    # 1. Try with strict constraints
    matches: list[tuple[float, str]] = []
    for item in subdivisions:
        lat = float(item["lat"])
        lon = float(item["lon"])
        if abs(lon - longitude) > lon_tolerance:
            continue
        if min_latitude is not None and lat < min_latitude - 0.5:
            continue
        distance = abs(lon - longitude) + (max(0.0, (min_latitude or 0) - lat) if min_latitude else 0.0)
        matches.append((distance, item["name"]))

    # 2. Fallback: Try with relaxed constraints (up to 8.0 longitude and 3.0 latitude offset)
    if not matches:
        for item in subdivisions:
            lat = float(item["lat"])
            lon = float(item["lon"])
            if abs(lon - longitude) > 8.0:
                continue
            if min_latitude is not None and lat < min_latitude - 3.0:
                continue
            distance = abs(lon - longitude) + (max(0.0, (min_latitude or 0) - lat) if min_latitude else 0.0)
            matches.append((distance, item["name"]))

    # 3. Last resort: Match closest 3 subdivisions by pure distance
    if not matches:
        for item in subdivisions:
            lat = float(item["lat"])
            lon = float(item["lon"])
            distance = abs(lon - longitude) + (max(0.0, (min_latitude or 0) - lat) if min_latitude else 0.0)
            matches.append((distance, item["name"]))

    matches.sort(key=lambda pair: pair[0])
    return [name for _, name in matches[:5]]


def resolve_regions(region_text: str) -> str:
    if not region_text:
        return ""
    parts = [p.strip() for p in region_text.split(";") if p.strip()]
    resolved_parts: list[str] = []
    for part in parts:
        if is_coordinate_region(part):
            mapped = resolve_coordinate_to_subdivisions(part)
            if mapped:
                resolved_parts.extend(mapped)
            else:
                resolved_parts.append(part)
        else:
            resolved_parts.append(part)
            
    unique_resolved: list[str] = []
    for name in resolved_parts:
        if name and name not in unique_resolved:
            unique_resolved.append(name)
            
    return " ; ".join(unique_resolved)


def system_to_row(system, date: str | None) -> dict:
    """Map the structured Pydantic object to the requested final dictionary format."""
    # Determine heightAboveMSL
    if (system.height_km_min or 0.0) > 0.0 and (system.height_km_max or 0.0) > 0.0:
        height_above_msl = f"{system.height_km_min} km to {system.height_km_max} km"
    elif (system.height_km_min or 0.0) > 0.0:
        height_above_msl = f"{system.height_km_min} km"
    elif (system.height_km_max or 0.0) > 0.0:
        height_above_msl = f"{system.height_km_max} km"
    elif system.pressure_level.strip():
        height_above_msl = system.pressure_level.strip()
    else:
        text = f"{system.region} {system.status}".lower()
        if bool(_SURFACE_RE.search(text)):
            height_above_msl = "Surface"
        else:
            height_above_msl = "Not specified"

    # Determine Regions
    if system.subdivisions:
        regions = " ; ".join(system.subdivisions)
    else:
        regions = resolve_regions(system.region)

    return {
        "weather system": system.weather_system.value,
        "date": date or "",
        "heightAboveMSL": height_above_msl,
        "Regions": regions,
    }


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


def _build_messages(system_prompt: str, summary_text: str, date: str | None, few_shot: list[dict]) -> list[dict]:
    messages = [{"role": "system", "content": system_prompt}]
    for msg in few_shot:
        role = "assistant" if msg["role"] == "assistant" else "user"
        messages.append({"role": role, "content": msg["content"]})
    messages.append({
        "role": "user",
        "content": f"Bulletin date: {date or 'unknown'}\n\nSummary text:\n{summary_text}",
    })
    return messages


def extract_bulletin_fireworks(
    api_key: str,
    path: Path,
    system_prompt: str,
    few_shot: list[dict],
    model: str = DEFAULT_MODEL,
) -> list[dict]:
    """Extract one bulletin via Fireworks API and GLM 5.2 model."""
    paragraphs = read_docx_paragraphs(path)
    summary_text = gather_summary_text(paragraphs)
    if not summary_text.strip():
        return []

    date = _bulletin_date(paragraphs, path)
    messages = _build_messages(system_prompt, summary_text, date, few_shot)

    schema = BulletinExtraction.model_json_schema()
    schema = _inline_schema_refs(schema)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.0,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "BulletinExtraction",
                "schema": schema,
            }
        }
    }

    resp = requests.post(FIREWORKS_API_URL, headers=headers, json=payload, timeout=TIMEOUT)
    if not resp.ok:
        raise requests.HTTPError(
            f"Fireworks API request failed {resp.status_code} {resp.reason}: {resp.text}", response=resp
        )

    data = resp.json()
    try:
        text = data["choices"][0]["message"]["content"]
        extraction = BulletinExtraction.model_validate_json(text)
    except (KeyError, IndexError, ValueError) as exc:
        print(f"    [fireworks] parse error: {exc}")
        print(f"    [fireworks] raw response: {json.dumps(data, indent=2)[:2000]}")
        return []

    from grounding import apply_grounding_filter
    grounded, ungrounded = apply_grounding_filter(extraction.systems, summary_text)
    if ungrounded:
        names = ", ".join(f"{s.weather_system.value}/{s.region or '?'}" for s in ungrounded)
        print(f"    [grounding] dropped {len(ungrounded)}: {names}")

    return [
        system_to_row(system, date)
        for system in grounded
        if keep_system(system)
    ]
