from pathlib import Path
import argparse
import csv
import json
import re
import shutil
import tempfile
import zipfile
from datetime import datetime
import xml.etree.ElementTree as ET

IMD_SUBDIVISIONS_PATH = Path(__file__).parent / "data" / "imd_subdivisions.json"
FORM_SUBDIVISIONS_GAZETTEER_PATH = Path(__file__).parent / "data" / "form_subdivisions_gazetteer.json"
WEATHER_FORM_JS_PATH = Path(__file__).parent / "js" / "weather_form.js"
IMD_SUBDIVISIONS: list[dict] = []
FORM_SUBDIVISIONS: list[str] = []
FORM_SUBDIVISION_GAZETTEER: list[dict] = []

WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NAMESPACES = {"w": WORD_NAMESPACE}

WEATHER_SYSTEM_PATTERNS = {
    r"super cyclonic storm": "Super Cyclonic Storm (SuCS)",
    r"extremely severe cyclonic storm": "Extremely Severe Cyclonic Storm (ESCS)",
    r"very severe cyclonic storm": "Very Severe Cyclonic Storm (VSCS)",
    r"severe cyclonic storm": "Severe Cyclonic Storm (SCS)",
    r"cyclonic storm": "Cyclonic Storm (CS)",
    r"deep depression": "Deep Depression (DD)",
    r"western depression": "Western Depression",
    r"depression": "Depression (D)",
    r"western disturbance": "Western Disturbances (WD)",
    r"western disturbances": "Western Disturbances (WD)",
    r"well marked low pressure area": "Well Marked Low Pressure Area (WML)",
    r"low pressure area": "Low Pressure Area",
    r"low pressure": "Low Pressure (L)",
    r"induced cyclonic circulation": "Induced Cyclonic Circulation",
    r"low-level cyclonic circulation": "Low-Level Cyclonic Circulation",
    r"mid-level cyclonic circulation": "Mid-Level Cyclonic Circulation",
    r"upper-level cyclonic circulation": "Upper-Level Cyclonic Circulation",
    r"cyclonic circulation": "Cyclonic Circulation (CYCIR)",
    r"monsoon trough with extension and tilt": "Monsoon Trough with Extension and Tilt",
    r"mean sea level trough": "Mean Sea Level Trough",
    r"at surface trough": "At Surface Trough",
    r"offshore trough": "Offshore Trough",
    r"westerly trough": "Westerly Trough",
    r"easterly trough": "Easterly Trough",
    r"trough": "Trough",
}

ASSOCIATED_SYSTEM_PATTERNS = {
    r"cyclonic circulation": "Cyclonic Circulation",
    r"western disturbance": "Western Disturbance",
    r"low pressure area": "Low Pressure Area",
    r"low pressure": "Low Pressure",
    r"easterly trough": "Easterly Trough",
    r"westerly trough": "Westerly Trough",
}

PRESSURE_LEVEL_PATTERNS = [
    "surface",
    "1000 hPa",
    "925 hPa",
    "850 hPa",
    "700 hPa",
    "500 hPa",
    "300 hPa",
]

# Height (km) -> pressure (hPa) from IMD conversion chart (+ user overrides).
PRESSURE_HEIGHT_CHART: list[tuple[int, float]] = [
    (925, 0.9),   # override: 0.9 km -> 925 hPa
    (925, 1.0),
    (850, 1.5),
    (700, 3.1),
    (600, 4.5),   # override: 4.5 km -> 600 hPa
    (500, 5.8),   # override: 5.8 km -> 500 hPa
    (400, 7.6),
    (300, 9.6),
    (250, 10.6),
    (200, 12.3),
    (150, 13.5),
    (100, 16.6),
]
HEIGHT_PRESSURE_TOLERANCE_KM = 0.05

REGION_KEYWORDS = ["over", "across", "along", "near", "off"]
SAME_REGION_PATTERNS = [
    r"same region",
    r"same area",
    r"same place",
    r"the same region",
    r"the same area",
    r"the same place",
]
STATUS_PATTERNS = {
    r"persisted": "persisted",
    r"continued": "continued",
    r"remained": "remained",
    r"(?:has\s+)?become(?:n)?\s+less\s+marked": "became less marked",
    r"became less marked": "became less marked",
    r"merged with": "merged",
    r"extended": "extended",
    r"weakened": "weakened",
    r"was marked": "was marked",
    r"is marked": "is marked",
    r"lay over": "lay over",
}

SUPPORTED_SYSTEM_TYPES = ("WD", "CYCIR", "Trough")


def list_word_files(folder: Path, pattern: str = "*.docx"):
    """Return all matching .docx files from the specified folder."""
    return sorted(
        path
        for path in folder.glob(pattern)
        if not path.name.startswith("~$") and "_copy" not in path.stem
    )


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
    """Read paragraphs from a .docx Word file using the standard library."""
    if not path.exists():
        raise FileNotFoundError(f"Word file not found: {path}")
    if path.suffix.lower() != ".docx":
        raise ValueError("Only .docx Word files are supported by this script.")

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


def read_docx_file(path: Path) -> str:
    """Read full text from a .docx Word file."""
    return "\n".join(read_docx_paragraphs(path))


def parse_bulletin_date(paragraphs: list[str]) -> str | None:
    """Extract bulletin date from heading and return ISO date (YYYY-MM-DD)."""
    # Common heading example: Sunday,08th June 2025 (...)
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


def get_summary_paragraph(paragraphs: list[str]) -> str:
    """Return first weather-summary paragraph; fallback to first non-empty paragraph."""
    for paragraph in paragraphs:
        if "summary of observations recorded" in paragraph.lower():
            return paragraph
    return next((p for p in paragraphs if p.strip()), "")


def normalize_text(text: str) -> str:
    """Normalize whitespace and lower-case the text for pattern matching."""
    text = text.replace("\u2013", "-")
    text = text.replace("\u2014", "-")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def split_sentences(text: str) -> list[str]:
    """Split raw text into sentences using punctuation boundaries."""
    text = text.replace("\n", " ")
    # Protect domain abbreviations from sentence splitting.
    text = re.sub(r"\bLong\.", "Long<prd>", text, flags=re.I)
    text = re.sub(r"\bLat\.", "Lat<prd>", text, flags=re.I)
    text = re.sub(r"\bm\.\s*s\.\s*l\.", "msl<prd>", text, flags=re.I)
    text = re.sub(r"\bm\.\s*s\.\s*l\b", "msl", text, flags=re.I)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    clean_sentences = [sentence.replace("<prd>", ".").strip() for sentence in sentences if sentence.strip()]
    return merge_sentence_fragments(clean_sentences)


def merge_sentence_fragments(sentences: list[str]) -> list[str]:
    """Merge fragments produced by abbreviation splits (e.g. msl. with a trough aloft)."""
    if not sentences:
        return sentences

    merged: list[str] = []
    buffer = sentences[0]
    fragment_starts = (
        r"^with a trough\b",
        r"^roughly along\b",
        r"^in middle\b",
        r"^in upper\b",
    )

    for sentence in sentences[1:]:
        if any(re.match(pattern, sentence, re.I) for pattern in fragment_starts):
            buffer = f"{buffer} {sentence}"
        else:
            merged.append(buffer)
            buffer = sentence

    merged.append(buffer)
    return split_weather_clauses(merged)


def split_weather_clauses(sentences: list[str]) -> list[str]:
    """Split combined clauses that share one sentence after m.s.l. protection."""
    clause_boundary = re.compile(
        r"(?<=\.)\s+(?=The\s+(?:induced\s+)?(?:upper air\s+)?cyclonic circulation|The\s+(?:north[- ]south\s+)?trough|"
        r"A\s+(?:north[- ]south\s+)?trough|A\s+fresh\s+western disturbance|The\s+western disturbance|Another\s+western disturbance|"
        r"An?\s+(?:induced\s+)?(?:upper air\s+)?cyclonic circulation|It\s+(?:then\s+)?\b)",
        re.I,
    )
    result: list[str] = []
    for sentence in sentences:
        parts = clause_boundary.split(sentence)
        for part in parts:
            cleaned = re.sub(r"^Summary of observations recorded[^:]*:\s*", "", part, flags=re.I).strip()
            if cleaned:
                result.append(cleaned)
    return result


def load_imd_subdivisions() -> list[dict]:
    global IMD_SUBDIVISIONS
    if IMD_SUBDIVISIONS:
        return IMD_SUBDIVISIONS
    if IMD_SUBDIVISIONS_PATH.exists():
        IMD_SUBDIVISIONS = json.loads(IMD_SUBDIVISIONS_PATH.read_text(encoding="utf-8"))
    return IMD_SUBDIVISIONS


def load_form_subdivisions() -> list[str]:
    """Load allowed meteorological subdivisions from weather_form.js."""
    global FORM_SUBDIVISIONS
    if FORM_SUBDIVISIONS:
        return FORM_SUBDIVISIONS

    if WEATHER_FORM_JS_PATH.exists():
        js_text = WEATHER_FORM_JS_PATH.read_text(encoding="utf-8")
        block_match = re.search(r"const subdivisions\s*=\s*\[(.*?)\];", js_text, re.S)
        if block_match:
            FORM_SUBDIVISIONS = re.findall(r'"([^"]+)"', block_match.group(1))

    if not FORM_SUBDIVISIONS and FORM_SUBDIVISIONS_GAZETTEER_PATH.exists():
        gazetteer = json.loads(FORM_SUBDIVISIONS_GAZETTEER_PATH.read_text(encoding="utf-8"))
        FORM_SUBDIVISIONS = [item["name"] for item in gazetteer]

    return FORM_SUBDIVISIONS


def load_form_subdivisions_gazetteer() -> list[dict]:
    global FORM_SUBDIVISION_GAZETTEER
    if FORM_SUBDIVISION_GAZETTEER:
        return FORM_SUBDIVISION_GAZETTEER
    if FORM_SUBDIVISIONS_GAZETTEER_PATH.exists():
        FORM_SUBDIVISION_GAZETTEER = json.loads(FORM_SUBDIVISIONS_GAZETTEER_PATH.read_text(encoding="utf-8"))
    return FORM_SUBDIVISION_GAZETTEER


def normalize_subdivision_key(text: str) -> str:
    text = text.lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# Bulletin phrase aliases -> official form subdivisions (weather_form.js list only).
REGION_ALIAS_TO_SUBDIVISIONS: dict[str, list[str]] = {
    "haryana": ["Haryana, Chandigarh & Delhi"],
    "chandigarh": ["Haryana, Chandigarh & Delhi"],
    "delhi": ["Haryana, Chandigarh & Delhi"],
    "ladakh": ["Jammu & Kashmir"],
    "kashmir": ["Jammu & Kashmir"],
    "jammu": ["Jammu & Kashmir"],
    "punjab": ["Punjab"],
    "himachal pradesh": ["Himachal Pradesh"],
    "uttarakhand": ["Uttarakhand"],
    "uttar pradesh": ["West Uttar Pradesh", "East Uttar Pradesh"],
    "west uttar pradesh": ["West Uttar Pradesh"],
    "east uttar pradesh": ["East Uttar Pradesh"],
    "bihar": ["Bihar"],
    "jharkhand": ["Jharkhand"],
    "odisha": ["Odisha"],
    "west bengal": ["Gangetic West Bengal", "Sub-Himalayan West Bengal & Sikkim"],
    "gangetic west bengal": ["Gangetic West Bengal"],
    "sub himalayan west bengal": ["Sub-Himalayan West Bengal & Sikkim"],
    "sub-himalayan west bengal": ["Sub-Himalayan West Bengal & Sikkim"],
    "sikkim": ["Sikkim", "Sub-Himalayan West Bengal & Sikkim"],
    "assam": ["Assam & Meghalaya"],
    "meghalaya": ["Assam & Meghalaya"],
    "arunachal pradesh": ["Arunachal Pradesh"],
    "nagaland": ["Nagaland, Manipur, Mizoram & Tripura"],
    "manipur": ["Nagaland, Manipur, Mizoram & Tripura"],
    "mizoram": ["Nagaland, Manipur, Mizoram & Tripura"],
    "tripura": ["Nagaland, Manipur, Mizoram & Tripura"],
    "rajasthan": ["West Rajasthan", "East Rajasthan"],
    "west rajasthan": ["West Rajasthan"],
    "east rajasthan": ["East Rajasthan"],
    "north rajasthan": ["West Rajasthan"],
    "south rajasthan": ["West Rajasthan"],
    "gujarat": ["Gujarat Region"],
    "saurashtra": ["Saurashtra & Kutch"],
    "kutch": ["Saurashtra & Kutch"],
    "konkan": ["Konkan & Goa"],
    "goa": ["Konkan & Goa"],
    "maharashtra": ["Madhya Maharashtra", "Marathwada", "Konkan & Goa"],
    "madhya maharashtra": ["Madhya Maharashtra"],
    "marathwada": ["Marathwada"],
    "vidarbha": ["Vidarbha"],
    "madhya pradesh": ["West Madhya Pradesh", "East Madhya Pradesh"],
    "west madhya pradesh": ["West Madhya Pradesh"],
    "east madhya pradesh": ["East Madhya Pradesh"],
    "chhattisgarh": ["Chhattisgarh"],
    "andhra pradesh": ["Coastal Andhra Pradesh", "Rayalaseema"],
    "coastal andhra pradesh": ["Coastal Andhra Pradesh"],
    "north coastal andhra pradesh": ["Coastal Andhra Pradesh"],
    "south coastal andhra pradesh": ["Coastal Andhra Pradesh"],
    "telangana": ["Telangana"],
    "rayalaseema": ["Rayalaseema"],
    "karnataka": ["Coastal Karnataka", "North Interior Karnataka", "South Interior Karnataka"],
    "coastal karnataka": ["Coastal Karnataka"],
    "north interior karnataka": ["North Interior Karnataka"],
    "south interior karnataka": ["South Interior Karnataka"],
    "interior karnataka": ["North Interior Karnataka", "South Interior Karnataka"],
    "tamil nadu": ["Tamil Nadu & Puducherry"],
    "puducherry": ["Tamil Nadu & Puducherry"],
    "kerala": ["Kerala"],
    "lakshadweep": ["Lakshadweep"],
    "andaman": ["Andaman & Nicobar Islands", "N Andaman Sea", "S Andaman Sea"],
    "nicobar": ["Andaman & Nicobar Islands"],
    "northwest bay of bengal": ["NW Bay"],
    "northeast bay of bengal": ["NE Bay"],
    "north bay of bengal": ["NW Bay", "NE Bay"],
    "westcentral bay of bengal": ["WC Bay"],
    "eastcentral bay of bengal": ["EC Bay"],
    "bay of bengal": ["NW Bay", "NE Bay", "WC Bay", "EC Bay", "SW Bay", "SE Bay"],
    "arabian sea": ["NW Arabian Sea", "NE Arabian Sea", "WC Arabian Sea", "EC Arabian Sea"],
    "pakistan": ["Pakistan"],
    "north pakistan": ["North pakistan"],
    "north pakistan & neighbourhood": ["North pakistan"],
    "north pakistan & adjoining jammu": ["North pakistan", "Jammu & Kashmir", "Punjab"],
    "north pakistan & adjoining jammu and north punjab": ["North pakistan", "Jammu & Kashmir", "Punjab"],
    "jammu": ["Jammu & Kashmir"],
    "north punjab": ["Punjab"],
    "punjab": ["Punjab"],
    "punjab & neighbourhood": ["Punjab"],
    "central pakistan": ["Central Pakistan"],
    "bangladesh": ["Bangladesh"],
    "iran": ["Iran"],
    "west rajasthan": ["West Rajasthan"],
    "north rajasthan": ["West Rajasthan"],
    "south rajasthan": ["West Rajasthan"],
    "northeast assam": ["Assam & Meghalaya"],
    "northeast bay": ["NE Bay"],
    "northwest bay": ["NW Bay"],
    "westcentral bay": ["WC Bay"],
    "eastcentral bay": ["EC Bay"],
    "southwest bay": ["SW Bay"],
    "southeast bay": ["SE Bay"],
}

NORMALIZED_REGION_ALIASES: dict[str, list[str]] = {
    normalize_subdivision_key(key): value for key, value in REGION_ALIAS_TO_SUBDIVISIONS.items()
}

COORDINATE_PHRASE_RE = re.compile(
    r"along\s+long\.?\s*[0-9]+(?:\.[0-9]+)?\s*°?\s*[ew]?"
    r"(?:\s+to\s+the\s+north\s+of\s+lat\.?\s*[0-9]+(?:\.[0-9]+)?\s*°?\s*[ns]?)?",
    re.I,
)


def _official_subdivisions_sorted() -> list[str]:
    return sorted(load_form_subdivisions(), key=len, reverse=True)


def resolve_coordinate_to_form_subdivisions(region: str, lon_tolerance: float = 2.5) -> list[str]:
    """Map coordinate text to allowed subdivisions using the form gazetteer."""
    longitude, min_latitude = parse_coordinate_constraints(region)
    if longitude is None or min_latitude is None:
        return []

    allowed = set(load_form_subdivisions())
    matches: list[tuple[float, str]] = []
    for item in load_form_subdivisions_gazetteer():
        name = item["name"]
        if name not in allowed:
            continue
        lat = float(item["lat"])
        lon = float(item["lon"])
        if abs(lon - longitude) > lon_tolerance:
            continue
        if min_latitude is not None and lat < min_latitude - 0.5:
            continue
        distance = abs(lon - longitude) + (max(0.0, (min_latitude or 0) - lat) if min_latitude else 0.0)
        matches.append((distance, name))

    matches.sort(key=lambda pair: pair[0])
    return [name for _, name in matches[:5]]


def _match_fragment_to_subdivisions(fragment: str) -> list[str]:
    fragment = clean_region_text(fragment)
    if not fragment:
        return []

    if is_coordinate_region(fragment):
        return resolve_coordinate_to_form_subdivisions(fragment)

    fragment_key = normalize_subdivision_key(fragment)
    if not fragment_key:
        return []

    if fragment_key in NORMALIZED_REGION_ALIASES:
        return list(NORMALIZED_REGION_ALIASES[fragment_key])

    matched: list[str] = []
    allowed = set(load_form_subdivisions())

    for official in _official_subdivisions_sorted():
        official_key = normalize_subdivision_key(official)
        if official_key and (official_key in fragment_key or fragment_key in official_key):
            if official not in matched:
                matched.append(official)

    if matched:
        return matched

    fragment_tokens = set(fragment_key.split())
    for official in load_form_subdivisions():
        official_key = normalize_subdivision_key(official)
        alias_hits = NORMALIZED_REGION_ALIASES.get(official_key, [])
        if alias_hits:
            alias_keys = {normalize_subdivision_key(x) for x in alias_hits}
            if fragment_key in alias_keys or any(a in fragment_key for a in alias_keys):
                for sub in alias_hits:
                    if sub not in matched:
                        matched.append(sub)
            continue

        core_tokens = [
            token
            for token in official_key.split()
            if len(token) > 2 and token not in {"and", "the", "sea", "bay", "north", "south", "east", "west"}
        ]
        if core_tokens and all(token in fragment_tokens for token in core_tokens):
            if official not in matched:
                matched.append(official)

    return matched


def split_region_fragments(region_text: str) -> list[str]:
    """Split semicolon-separated region lists (extraction already normalized paths)."""
    fragments: list[str] = []
    for part in re.split(r"\s*;\s*", region_text):
        part = clean_region_text(part)
        if not part:
            continue
        if part.lower() in {"the", "cyclonic circulation", "upper air cyclonic circulation"}:
            continue
        fragments.append(part)
    return fragments


def extract_coordinate_phrases(region_text: str) -> tuple[str, list[str]]:
    """Pull coordinate phrases out so they are not split or token-matched incorrectly."""
    phrases: list[str] = []
    remaining = region_text
    for match in COORDINATE_PHRASE_RE.finditer(region_text):
        phrases.append(match.group(0).strip())
    if phrases:
        remaining = COORDINATE_PHRASE_RE.sub(" ", remaining)
    return remaining, phrases


def map_text_to_form_subdivisions(region_text: str) -> list[str]:
    """Map free-text region field to allowed subdivisions from weather_form.js."""
    if not region_text.strip():
        return []

    subdivisions: list[str] = []
    remaining, coordinate_phrases = extract_coordinate_phrases(region_text)

    for phrase in coordinate_phrases:
        for sub in resolve_coordinate_to_form_subdivisions(phrase):
            if sub not in subdivisions:
                subdivisions.append(sub)

    alias_keys_sorted = sorted(NORMALIZED_REGION_ALIASES, key=len, reverse=True)

    for fragment in split_region_fragments(remaining):
        fragment_key = normalize_subdivision_key(fragment)
        alias_match = NORMALIZED_REGION_ALIASES.get(fragment_key)
        if alias_match is None:
            for alias_key in alias_keys_sorted:
                if alias_key in fragment_key or fragment_key in alias_key:
                    alias_match = NORMALIZED_REGION_ALIASES[alias_key]
                    break
        if alias_match is not None:
            for sub in alias_match:
                if sub not in subdivisions:
                    subdivisions.append(sub)
            continue

        for sub in _match_fragment_to_subdivisions(fragment):
            if sub not in subdivisions:
                subdivisions.append(sub)
    return subdivisions


def assign_form_subdivisions(entity: dict) -> None:
    """Assign official subdivisions to an entity (multiple allowed)."""
    region_text = str(entity.get("region", "") or "").strip()
    original_text = str(entity.get("region_original", "") or "").strip()
    combined = " ; ".join(part for part in [region_text, original_text] if part)
    entity["subdivisions"] = format_regions(map_text_to_form_subdivisions(combined))


def apply_form_subdivisions(entities: list[dict]) -> list[dict]:
    for entity in entities:
        assign_form_subdivisions(entity)
    return entities


def clean_region_text(region: str) -> str:
    """Strip temporal/noise suffixes from region strings."""
    region = region.strip(" ,.;")
    region = re.sub(r"\s+of today morning\.?$", "", region, flags=re.I)
    region = re.sub(r"\s+also\.?$", "", region, flags=re.I)
    region = re.sub(r"\s+then persisted.*$", "", region, flags=re.I)
    region = re.sub(r"\s+(?:has\s+)?become(?:n)?\s+less\s+marked.*$", "", region, flags=re.I)
    region = re.sub(r"\s+became\s+less\s+marked.*$", "", region, flags=re.I)
    return region.strip()


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

    subdivisions = load_imd_subdivisions()
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

    matches.sort(key=lambda pair: pair[0])
    return [name for _, name in matches[:5]]


def resolve_region_parts(region_text: str) -> tuple[str, str]:
    """
    Resolve region field; return (resolved_region, region_original).
    region_original is set only when coordinate text was converted.
    """
    if not region_text:
        return "", ""

    parts = [part.strip() for part in region_text.split(";") if part.strip()]
    resolved_parts: list[str] = []
    coordinate_originals: list[str] = []

    for part in parts:
        if is_coordinate_region(part):
            mapped = resolve_coordinate_to_subdivisions(part)
            if mapped:
                coordinate_originals.append(part)
                resolved_parts.extend(mapped)
            else:
                resolved_parts.append(part)
        else:
            resolved_parts.append(clean_region_text(part))

    unique_resolved: list[str] = []
    for name in resolved_parts:
        if name and name not in unique_resolved:
            unique_resolved.append(name)

    resolved_text = format_regions(unique_resolved)
    original_text = format_regions(coordinate_originals) if coordinate_originals else ""
    return resolved_text, original_text


def is_less_marked_status(status: str | None) -> bool:
    return bool(status and "less marked" in status.lower())


def height_to_pressure_levels(min_km: float, max_km: float | None = None) -> list[int]:
    """Map height (or inclusive range) to pressure level(s) using the conversion chart."""
    if min_km <= 0 and (max_km is None or max_km <= 0):
        return []

    if max_km is not None and max_km > 0 and max_km != min_km:
        low, high = (min_km, max_km) if min_km <= max_km else (max_km, min_km)
        levels: list[int] = []
        for pressure, chart_height in sorted(PRESSURE_HEIGHT_CHART, key=lambda item: item[1]):
            if low - HEIGHT_PRESSURE_TOLERANCE_KM <= chart_height <= high + HEIGHT_PRESSURE_TOLERANCE_KM:
                if pressure not in levels:
                    levels.append(pressure)
        return levels

    target = max_km if max_km and max_km > 0 else min_km
    for pressure, chart_height in PRESSURE_HEIGHT_CHART:
        if abs(chart_height - target) <= HEIGHT_PRESSURE_TOLERANCE_KM:
            return [pressure]

    closest_pressure, _ = min(PRESSURE_HEIGHT_CHART, key=lambda item: abs(item[1] - target))
    return [closest_pressure]


def format_pressure_levels(levels: list[int]) -> str:
    return " ; ".join(f"{level} hPa" for level in levels)


def format_height_km(min_km: float, max_km: float | None = None) -> str | float:
    if max_km is not None and max_km > 0 and abs(max_km - min_km) > HEIGHT_PRESSURE_TOLERANCE_KM:
        low, high = (min_km, max_km) if min_km <= max_km else (max_km, min_km)
        return f"{low}-{high}"
    if min_km > 0:
        return min_km
    if max_km and max_km > 0:
        return max_km
    return 0.0


def apply_pressure_from_height(entity: dict) -> None:
    min_km = float(entity.get("height_km_min", 0) or 0)
    max_km = entity.get("height_km_max")
    max_km = float(max_km) if max_km not in (None, "") else None

    if min_km <= 0 and not max_km:
        if isinstance(entity.get("height_km"), str) and "-" in str(entity.get("height_km")):
            parts = str(entity["height_km"]).split("-", 1)
            try:
                min_km = float(parts[0])
                max_km = float(parts[1])
            except ValueError:
                pass

    levels = height_to_pressure_levels(min_km, max_km)
    if levels:
        entity["pressure_level"] = format_pressure_levels(levels)

    entity["height_km"] = format_height_km(min_km, max_km)
    entity.pop("height_km_min", None)
    entity.pop("height_km_max", None)


def postprocess_entities(entities: list[dict]) -> list[dict]:
    """Drop less-marked rows, resolve coordinates, and assign pressure levels from height."""
    processed: list[dict] = []
    for entity in entities:
        if is_less_marked_status(entity.get("status")):
            continue

        region = str(entity.get("region", "")).strip()
        resolved, original = resolve_region_parts(region)
        entity["region"] = resolved
        if original:
            entity["region_original"] = original
        elif "region_original" in entity:
            entity.pop("region_original", None)

        apply_pressure_from_height(entity)
        processed.append(entity)
    return processed


def normalize_region_key(region: str) -> str:
    return re.sub(r"\s+", " ", clean_region_text(region).lower())


def format_regions(regions: list[str]) -> str:
    cleaned = [clean_region_text(r) for r in regions if r and clean_region_text(r)]
    return " ; ".join(cleaned)


def is_continuation_sentence(sentence: str) -> bool:
    return bool(re.match(r"^\s*it\b", sentence.lower()))


def is_forecast_sentence(sentence: str) -> bool:
    """Skip forecast-only mentions (not current observed systems)."""
    return bool(re.search(r"\b(?:is\s+)?likely\s+to\s+affect\b", sentence.lower()))


def detect_primary_system(sentence: str) -> str | None:
    """Detect weather system from sentence subject, not embedded references."""
    s = sentence.lower().strip()
    if is_continuation_sentence(sentence):
        return None

    subject_patterns = [
        (r"^the\s+(?:fresh\s+)?western disturbance\b", "WD"),
        (r"^a\s+fresh\s+western disturbance\b", "WD"),
        (r"^another\s+western disturbance\b", "WD"),
        (r"^the\s+western disturbance\b", "WD"),
        (r"^the\s+(?:north[- ]south\s+)?trough\b", "Trough"),
        (r"^a\s+(?:north[- ]south\s+)?trough\b", "Trough"),
        (r"^the\s+(?:induced\s+)?(?:upper air\s+)?cyclonic circulation\b", "CYCIR"),
        (r"^an?\s+(?:induced\s+)?(?:upper air\s+)?cyclonic circulation\b", "CYCIR"),
    ]
    for pattern, system in subject_patterns:
        if re.search(pattern, s):
            return system

    if re.search(r"\bwestern disturbance(s)?\s+(?:as a|seen as a)\b", s):
        return "WD"
    return None


def has_additional_trough(sentence: str) -> bool:
    return bool(re.search(r"\bwith (?:a|the) trough\b|\bassociated trough\b", sentence.lower()))


def extract_wd_regions(sentence: str) -> list[str]:
    """Extract all named or coordinate regions associated with a Western Disturbance."""
    s = sentence.lower()
    if "western disturbance" not in s:
        return []

    wd_match = re.search(r"\bwestern disturbance", s)
    chunk = s[wd_match.start() :]

    regions: list[str] = []
    for match in re.finditer(
        r"(?:lay\s+)?(?:as\s+a\s+(?:cyclonic\s+circulation|trough)\s+)?over\s+([^.;]+?)(?=\s+lay\s+over|\s+lay\s+as|\s+between|\s+at|\s+with\s+a\s+trough|\s+persisted|\s+roughly\s+along|\s+ran\s+roughly|\.)",
        chunk,
    ):
        region = clean_region_text(match.group(1))
        if region and region not in regions:
            regions.append(region)

    if not regions:
        coord = extract_coordinate_region_fallback(sentence)
        if coord:
            coord = re.sub(r"\s+at\s+\d{4}\s+hours.*$", "", coord, flags=re.I)
            coord = clean_region_text(coord)
            if coord:
                regions.append(coord)

    return regions


def extract_wd_region(sentence: str) -> str | None:
    regions = extract_wd_regions(sentence)
    return format_regions(regions) if regions else None


def extract_cycir_region(sentence: str) -> str | None:
    s = sentence.lower()
    patterns = [
        r"(?:induced\s+)?(?:upper air\s+)?cyclonic circulation\s+over\s+([^.;]+?)(?:\s+which|\s+persisted|\s+lay|\s+became|\s+between|\s+at|\s+of today|\s+and\b|\.)",
        r"(?:induced\s+)?(?:upper air\s+)?cyclonic circulation\s+lay\s+over\s+([^.;]+?)(?:\s+of today|\s+between|\s+at|\s+persisted|\s+which|\.)",
    ]
    for pattern in patterns:
        match = re.search(pattern, s)
        if match:
            return clean_region_text(match.group(1))
    return None


def extract_trough_path_regions(sentence: str) -> list[str]:
    """Extract regions from trough paths like 'from X to Y across Z'."""
    s = sentence.lower()
    patterns = [
        r"\btrough\b.*?\bfrom\s+(.+?)\s+to\s+(?:cyclonic circulation over\s+)?(.+?)(?:\s+across\s+(.+?))?(?:\s+of today|\s+also|\s+became|\s+at|\s+persisted|\.)",
        r"\bfrom\s+(.+?)\s+to\s+(?:cyclonic circulation over\s+)?(.+?)(?:\s+across\s+(.+?))?(?:\s+of today|\s+also|\s+became|\s+at|\s+persisted|\.)",
    ]
    for pattern in patterns:
        match = re.search(pattern, s)
        if not match:
            continue
        regions = [clean_region_text(match.group(i)) for i in range(1, 4) if match.group(i)]
        if regions:
            return regions
    return []


def extract_trough_aloft_info(sentence: str) -> tuple[list[str], float]:
    """Extract separate trough introduced by 'with a trough aloft'."""
    s = sentence.lower()
    if not has_additional_trough(sentence):
        return [], 0.0

    height = 0.0
    height_match = re.search(
        r"with (?:a|the) trough aloft[^.]*?at\s+(\d+(?:\.\d+)?)\s*km",
        s,
    )
    if height_match:
        height = float(height_match.group(1))

    regions: list[str] = []
    if "along long" in s:
        coord = extract_coordinate_region_fallback(sentence)
        if coord:
            regions = [clean_region_text(coord)]
    return regions, height


def extract_weather_system(sentence: str) -> str | None:
    return detect_primary_system(sentence)


def extract_associated_system(sentence: str) -> str | None:
    sentence_lower = sentence.lower()
    for pattern, label in ASSOCIATED_SYSTEM_PATTERNS.items():
        if re.search(rf"\b{pattern}\b", sentence_lower):
            return label
    return None


def extract_region(sentence: str) -> str | None:
    sentence_lower = sentence.lower()

    coords = extract_coordinates(sentence_lower)

    # Coordinate-first handling for cases like:
    # "ran roughly along Long. 89°E to the north of Lat. 22°N"
    if "along long" in sentence_lower:
        start = sentence_lower.find("along long")
        coord_text = sentence_lower[start:]
        coord_text = re.split(r"\s+(?:at\s+\d|persisted|became|continued|remained)\b", coord_text, maxsplit=1)[0]
        coord_text = coord_text.strip(" ,.;")
        if len(coord_text) > 10:
            return coord_text[:200]
        if coords:
            lon = coords.get("longitude", "")
            lat = coords.get("latitude", "")
            if lon and lat:
                return f"along long. {lon} to the north of lat. {lat}".lower()
            if lon:
                return f"along long. {lon}".lower()

    if "along lat" in sentence_lower:
        start = sentence_lower.find("along lat")
        coord_text = sentence_lower[start:]
        coord_text = re.split(r"\s+(?:at\s+\d|persisted|became|continued|remained)\b", coord_text, maxsplit=1)[0]
        coord_text = coord_text.strip(" ,.;")
        if len(coord_text) > 10:
            return coord_text[:200]
        if coords and coords.get("latitude"):
            return f"along lat. {coords['latitude']}".lower()

    for keyword in REGION_KEYWORDS:
        regex = rf"\b{keyword}\s+([a-z0-9&.,°:/\-\s]+?)(?:\s+(?:persisted|was|became|at|with|which|who|where|and|,|;|\)|\()|$)"
        match = re.search(regex, sentence_lower)
        if match:
            region = match.group(1).strip()[:200]
            if region in {"long.", "long", "lat.", "lat"}:
                continue
            if any(re.search(pattern, region) for pattern in SAME_REGION_PATTERNS):
                return None
            return region

    # For troughs written as "from X to Y across Z"
    from_to_match = re.search(
        r"\bfrom\s+([a-z0-9&.,°/\-\s]+?)\s+to\s+([a-z0-9&.,°/\-\s]+?)(?:\s+across\s+([a-z0-9&.,°/\-\s]+?))?(?:\s+(?:at|persisted|became|$)|[.;])",
        sentence_lower,
    )
    if from_to_match:
        parts = [p.strip() for p in from_to_match.groups() if p and p.strip()]
        return " ; ".join(parts)[:200]
    return None


def extract_height(sentence: str) -> float | None:
    min_km, max_km = extract_height_range(sentence)
    if max_km is not None:
        return max_km if max_km > 0 else min_km
    return min_km if min_km > 0 else 0.0


def extract_height_range(sentence: str) -> tuple[float, float | None]:
    """Return (min_km, max_km). max_km is set when bulletin gives an inclusive height range."""
    sentence_lower = sentence.lower()

    between_match = re.search(
        r"between\s+(\d+(?:\.\d+)?)\s*(?:km\s*)?(?:&|and)\s*(\d+(?:\.\d+)?)\s*(?:km\b)?",
        sentence_lower,
    )
    if between_match:
        return float(between_match.group(1)), float(between_match.group(2))

    patterns = [
        r"(\d+(?:\.\d+)?)\s*km\s*(?:above\s+mean\s+sea\s+level|above\s+m\.s\.l\.|above\s+msl|am\.sl\.|am\.sl|msl|mean sea level)",
        r"at\s+(\d+(?:\.\d+)?)\s*km\s*(?:above|height)",
        r"height\s+of\s+(\d+(?:\.\d+)?)\s*km",
        r"upto\s+(\d+(?:\.\d+)?)\s*km",
        r"extended\s+upto\s+(\d+(?:\.\d+)?)\s*km",
    ]
    for pattern in patterns:
        match = re.search(pattern, sentence_lower)
        if match:
            try:
                value = float(match.group(1))
                return value, None
            except ValueError:
                continue
    return 0.0, None


def extract_status(sentence: str) -> str | None:
    sentence_lower = sentence.lower()
    for pattern, label in STATUS_PATTERNS.items():
        if re.search(pattern, sentence_lower):
            return label
    return None


def extract_pressure_level(sentence: str) -> str | None:
    sentence_lower = sentence.lower()
    for level in PRESSURE_LEVEL_PATTERNS:
        if level in sentence_lower:
            return level
    match = re.search(r"(\d{3,4})\s*hpa", sentence_lower)
    if match:
        return f"{match.group(1)} hPa"
    return None


def extract_coordinates(sentence: str) -> dict | None:
    lat_match = re.search(r"lat(?:itude)?\.?\s*[:\s]*([0-9]+(?:\.[0-9]+)?)°?\s*([NS])", sentence, re.I)
    lon_match = re.search(r"lon(?:gitude)?\.?\s*[:\s]*([0-9]+(?:\.[0-9]+)?)°?\s*([EW])", sentence, re.I)
    if lat_match or lon_match:
        coords = {}
        if lat_match:
            coords["latitude"] = f"{lat_match.group(1)}°{lat_match.group(2).upper()}"
        if lon_match:
            coords["longitude"] = f"{lon_match.group(1)}°{lon_match.group(2).upper()}"
        return coords
    return None


def extract_coordinate_region_fallback(sentence: str) -> str | None:
    sentence_lower = sentence.lower()
    if "along" not in sentence_lower or ("long" not in sentence_lower and "lat" not in sentence_lower):
        return None
    start = sentence_lower.find("along")
    coord_text = sentence_lower[start:]
    coord_text = re.split(r"\s+(?:at\s+\d|persisted|became|continued|remained)\b", coord_text, maxsplit=1)[0]
    coord_text = coord_text.strip(" ,.;")
    return coord_text[:200] if len(coord_text) > 10 else None


def parse_sentence(sentence: str) -> dict:
    """Parse a single sentence into structured weather data."""
    normalized = normalize_text(sentence)
    return {
        "weather_system": extract_weather_system(normalized),
        "region": extract_region(normalized),
        "height_km": extract_height(normalized),
        "pressure_level": extract_pressure_level(normalized),
        "status": extract_status(normalized),
    }


def resolve_context(parsed: list[dict], sentences: list[str]) -> list[dict]:
    context = {
        "last_weather_system": None,
        "last_region": None,
        "last_height": 0.0,
        "last_pressure_level": None,
    }

    for index, entry in enumerate(parsed):
        sentence = sentences[index].lower()

        if entry.get("weather_system"):
            context["last_weather_system"] = entry["weather_system"]
            if entry.get("region"):
                context["last_region"] = entry["region"]
            if entry.get("height_km", 0.0) > 0.0:
                context["last_height"] = entry["height_km"]
            if entry.get("pressure_level"):
                context["last_pressure_level"] = entry["pressure_level"]

        if not entry.get("region") and re.search(r"same region|same area|same place", sentence):
            entry["region"] = context["last_region"]

        if not entry.get("region") and re.search(r"over the same|across the same", sentence):
            entry["region"] = context["last_region"]

        if not entry.get("weather_system") and re.search(r"\bit\b|this system|the system|it persisted|it remained|it continued", sentence):
            entry["weather_system"] = context["last_weather_system"]

        if entry.get("weather_system") and entry.get("height_km", 0.0) == 0.0 and index + 1 < len(parsed):
            next_entry = parsed[index + 1]
            if not next_entry.get("weather_system") and next_entry.get("height_km", 0.0) > 0.0:
                entry["height_km"] = next_entry["height_km"]

    return parsed


class EntityTracker:
    """Track weather entities with coreference resolution."""

    def __init__(self, date: str | None, source_file: str):
        self.entities: list[dict] = []
        self.index: dict[tuple[str, str], int] = {}
        self.cycir_by_region: dict[str, int] = {}
        self.last_idx: int | None = None
        self.last_by_type: dict[str, int] = {}
        self.date = date
        self.source_file = source_file

    def _entity_key(self, system: str, regions: list[str]) -> tuple[str, str]:
        if len(regions) > 1:
            region_key = "|".join(sorted(normalize_region_key(r) for r in regions))
        elif regions:
            region_key = normalize_region_key(regions[0])
        else:
            region_key = ""
        return (system, region_key)

    def _merge_fields(
        self,
        idx: int,
        height: float,
        status: str | None,
        pressure: str | None,
        height_max: float | None = None,
    ) -> None:
        entity = self.entities[idx]
        if height > 0.0:
            if float(entity.get("height_km_min", 0) or 0) == 0.0:
                entity["height_km_min"] = height
            else:
                entity["height_km_min"] = min(float(entity["height_km_min"]), height)
        if height_max and height_max > 0.0:
            entity["height_km_max"] = height_max
        elif height > 0.0 and not entity.get("height_km_max"):
            entity["height_km_min"] = height
        if status:
            entity["status"] = status
        if pressure and not entity.get("pressure_level"):
            entity["pressure_level"] = pressure

    def _register_cycir(self, idx: int, regions: list[str]) -> None:
        for region in regions:
            self.cycir_by_region[normalize_region_key(region)] = idx

    def find_cycir(self, region_hint: str) -> int | None:
        key = normalize_region_key(region_hint)
        if key in self.cycir_by_region:
            return self.cycir_by_region[key]
        for region_key, idx in self.cycir_by_region.items():
            if key in region_key or region_key in key:
                return idx
        return None

    def upsert(
        self,
        system: str,
        regions: list[str],
        height: float = 0.0,
        status: str | None = None,
        pressure: str | None = None,
        height_max: float | None = None,
    ) -> int:
        key = self._entity_key(system, regions)
        region_str = format_regions(regions)

        if key in self.index:
            idx = self.index[key]
            self._merge_fields(idx, height, status, pressure, height_max)
        else:
            entity = {
                "date": self.date,
                "source_file": self.source_file,
                "weather_system": system,
                "region": region_str,
                "height_km_min": height or 0.0,
                "height_km_max": height_max,
                "pressure_level": pressure,
                "status": status,
            }
            self.entities.append(entity)
            idx = len(self.entities) - 1
            self.index[key] = idx
            if system == "CYCIR":
                self._register_cycir(idx, regions)

        self.last_idx = idx
        self.last_by_type[system] = idx
        return idx

    def update_last(
        self,
        height: float = 0.0,
        status: str | None = None,
        pressure: str | None = None,
        height_max: float | None = None,
    ) -> None:
        if self.last_idx is None:
            return
        self._merge_fields(self.last_idx, height, status, pressure, height_max)

    def update_status_by_region(self, system: str, region: str, status: str | None, height: float = 0.0) -> bool:
        if system != "CYCIR":
            key = self._entity_key(system, [region])
            if key in self.index:
                self.last_idx = self.index[key]
                self._merge_fields(self.last_idx, height, status, None)
                return True
            return False

        idx = self.find_cycir(region)
        if idx is None:
            return False
        self.last_idx = idx
        self._merge_fields(idx, height, status, None)
        return True

    def update_status_by_regions(self, system: str, regions: list[str], status: str | None, height: float = 0.0) -> bool:
        key = self._entity_key(system, regions)
        if key in self.index:
            self.last_idx = self.index[key]
            self._merge_fields(self.last_idx, height, status, None)
            return True
        if len(regions) == 1:
            return self.update_status_by_region(system, regions[0], status, height)
        return False


def extract_trough_region(sentence: str) -> str | None:
    """Extract single-region trough description (coordinates or along phrases)."""
    path_regions = extract_trough_path_regions(sentence)
    if path_regions:
        return format_regions(path_regions)

    coord = extract_coordinate_region_fallback(sentence)
    if coord:
        return clean_region_text(coord)

    sentence_lower = sentence.lower()
    for keyword in REGION_KEYWORDS:
        regex = rf"\b{keyword}\s+([a-z0-9&.,°:/\-\s]+?)(?:\s+(?:persisted|was|became|at|with|which|who|where|and|,|;|\)|\()|$)"
        match = re.search(regex, sentence_lower)
        if match:
            region = clean_region_text(match.group(1))
            if region and region not in {"long.", "long", "lat.", "lat"}:
                return region
    return None


def process_summary_sentences(sentences: list[str], tracker: EntityTracker) -> None:
    """Process summary sentences with entity tracking and coreference resolution."""
    for sentence in sentences:
        normalized = normalize_text(sentence)
        sentence_lower = normalized.lower()

        if "northern limit of monsoon" in sentence_lower:
            continue

        if is_forecast_sentence(normalized):
            continue

        height_min, height_max = extract_height_range(normalized)
        status = extract_status(normalized)

        if is_less_marked_status(status):
            # A continuation such as "It became less marked" retires the
            # entity introduced immediately before it.
            if is_continuation_sentence(normalized) or re.match(r"^\s*(?:has\s+)?become(?:n)?\s+less\s+marked\b", sentence_lower):
                tracker.update_last(status=status)
                continue

            primary = detect_primary_system(normalized)
            if not primary and re.search(r"\b(?:north[- ]south\s+)?trough\b", sentence_lower):
                primary = "Trough"

            regions: list[str] = []
            if primary == "WD":
                regions = extract_wd_regions(normalized)
            elif primary == "CYCIR":
                region = extract_cycir_region(normalized)
                regions = [region] if region else []
            elif primary == "Trough":
                regions = extract_trough_path_regions(normalized)
                if not regions:
                    region = extract_trough_region(normalized)
                    regions = [region] if region else []

            if primary and regions:
                tracker.update_status_by_regions(primary, regions, status, height_min)
            continue

        # Rule 2: "It then persisted..." refers to the last mentioned entity.
        if is_continuation_sentence(normalized):
            tracker.update_last(
                height=height_min,
                status=status or "persisted",
                height_max=height_max,
            )

            # Rule 4: "with a trough aloft" introduces an additional trough system.
            aloft_regions, aloft_height = extract_trough_aloft_info(normalized)
            if aloft_regions or aloft_height > 0.0:
                tracker.upsert("Trough", aloft_regions, aloft_height, None, height_max=None)
            continue

        # Standalone trough-aloft fragment (after sentence merge).
        if re.match(r"^\s*with a trough\b", normalized, re.I):
            aloft_regions, aloft_height = extract_trough_aloft_info(normalized)
            if aloft_regions or aloft_height > 0.0:
                tracker.upsert("Trough", aloft_regions, aloft_height, None, height_max=None)
            continue

        primary = detect_primary_system(normalized)
        if not primary and re.search(r"\b(?:north[- ]south\s+)?trough\b.*\b(?:ran|run|extends?|extended)\b", sentence_lower):
            primary = "Trough"
        if not primary:
            continue

        if primary == "WD":
            wd_regions = extract_wd_regions(normalized)
            tracker.upsert("WD", wd_regions, height_min, status, height_max=height_max)

            aloft_regions, aloft_height = extract_trough_aloft_info(normalized)
            if aloft_regions or aloft_height > 0.0:
                tracker.upsert("Trough", aloft_regions, aloft_height, None, height_max=None)
            continue

        if primary == "CYCIR":
            region = extract_cycir_region(normalized)
            if not region:
                continue

            tracker.upsert("CYCIR", [region], height_min, status, height_max=height_max)

            aloft_regions, aloft_height = extract_trough_aloft_info(normalized)
            if aloft_regions or aloft_height > 0.0:
                tracker.upsert("Trough", aloft_regions, aloft_height, None, height_max=None)
            continue

        if primary == "Trough":
            path_regions = extract_trough_path_regions(normalized)
            if path_regions:
                tracker.upsert("Trough", path_regions, height_min, status, height_max=height_max)
                continue

            region = extract_trough_region(normalized)
            tracker.upsert("Trough", [region] if region else [], height_min, status, height_max=height_max)


def extract_from_docx(path: Path) -> list[dict]:
    paragraphs = read_docx_paragraphs(path)
    raw_text = get_summary_paragraph(paragraphs)
    bulletin_date = parse_bulletin_date(paragraphs) or parse_bulletin_date_from_filename(path)
    sentences = split_sentences(raw_text)

    tracker = EntityTracker(bulletin_date, path.name)
    process_summary_sentences(sentences, tracker)
    return postprocess_entities(tracker.entities)


def _parse_height_for_compare(height_value) -> float:
    if height_value in (None, ""):
        return 0.0
    if isinstance(height_value, str) and "-" in height_value:
        try:
            return float(height_value.split("-")[-1])
        except ValueError:
            return 0.0
    try:
        return float(height_value)
    except (TypeError, ValueError):
        return 0.0


def extract_from_folder(folder: Path, pattern: str = "*.docx") -> list[dict]:
    files = list_word_files(folder, pattern)
    if not files:
        return []
    all_entries: list[dict] = []
    for file_path in files:
        try:
            all_entries.extend(extract_from_docx(file_path))
        except (PermissionError, FileNotFoundError, ValueError) as exc:
            print(f"Skipping {file_path.name}: {exc}")
    # Final de-dup guard across all files.
    unique: list[dict] = []
    seen: set[tuple] = set()
    for row in all_entries:
        if is_less_marked_status(row.get("status")):
            continue
        dedup_key = (
            row.get("date"),
            row.get("source_file"),
            row.get("weather_system"),
            re.sub(r"\s+", " ", str(row.get("region", "")).strip().lower()),
        )
        if dedup_key in seen:
            # Merge into the existing row for same entity.
            idx = next(
                i
                for i, existing in enumerate(unique)
                if (
                    existing.get("date"),
                    existing.get("source_file"),
                    existing.get("weather_system"),
                    re.sub(r"\s+", " ", str(existing.get("region", "")).strip().lower()),
                )
                == dedup_key
            )
            existing = unique[idx]
            if _parse_height_for_compare(existing.get("height_km")) == 0.0 and _parse_height_for_compare(row.get("height_km")) > 0.0:
                existing["height_km"] = row.get("height_km", 0.0)
                existing["pressure_level"] = row.get("pressure_level", existing.get("pressure_level"))
            if not existing.get("pressure_level") and row.get("pressure_level"):
                existing["pressure_level"] = row.get("pressure_level")
            if row.get("status"):
                existing["status"] = row.get("status")
            continue
        seen.add(dedup_key)
        unique.append(row)
    return unique


def write_csv(data: list[dict], path: Path) -> None:
    fieldnames = [
        "date",
        "source_file",
        "weather_system",
        "region",
        "region_original",
        "height_km",
        "pressure_level",
        "status",
    ]
    with path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in data:
            if is_less_marked_status(row.get("status")):
                continue
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def write_subdivision_csv(data: list[dict], path: Path) -> None:
    """Write CSV with official weather_form.js subdivisions (semicolon-separated)."""
    fieldnames = [
        "date",
        "source_file",
        "weather_system",
        "subdivisions",
        "region",
        "region_original",
        "height_km",
        "pressure_level",
        "status",
    ]
    enriched = apply_form_subdivisions([dict(row) for row in data])
    with path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in enriched:
            if is_less_marked_status(row.get("status")):
                continue
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def enrich_csv_with_subdivisions(input_path: Path, output_path: Path) -> int:
    """Map regions in an existing extraction CSV to form subdivisions (new file)."""
    with input_path.open(newline="", encoding="utf-8") as csvfile:
        rows = list(csv.DictReader(csvfile))
    write_subdivision_csv(rows, output_path)
    return len(rows)


def main(
    folder: Path,
    filename: str | None = None,
    json_output: bool = False,
    csv_output: str | None = None,
    subdivision_csv_output: str | None = None,
    enrich_csv_input: str | None = None,
    pattern: str = "*.docx",
) -> None:
    if enrich_csv_input and subdivision_csv_output:
        input_path = Path(enrich_csv_input)
        output_path = Path(subdivision_csv_output)
        count = enrich_csv_with_subdivisions(input_path, output_path)
        print(f"Mapped {count} rows from {input_path} -> {output_path}")
        return

    aiws_folder = Path(folder)
    if not aiws_folder.exists() or not aiws_folder.is_dir():
        raise FileNotFoundError(f"Folder not found: {aiws_folder}")

    if filename:
        file_path = aiws_folder / filename
        parsed = extract_from_docx(file_path)
    else:
        files = list_word_files(aiws_folder, pattern)
        if not files:
            print(f"No matching .docx Word files were found in {aiws_folder} using pattern '{pattern}'")
            return
        print(f"Found {len(files)} .docx files in {aiws_folder} using pattern '{pattern}'")
        parsed = extract_from_folder(aiws_folder, pattern)
        print(f"Extracted {len(parsed)} weather system entries.\n")

    if csv_output:
        output_path = Path(csv_output)
        write_csv(parsed, output_path)
        print(f"CSV saved to {output_path}")

    if subdivision_csv_output:
        subdivision_path = Path(subdivision_csv_output)
        write_subdivision_csv(parsed, subdivision_path)
        print(f"Subdivision CSV saved to {subdivision_path}")

    if json_output:
        print(json.dumps(parsed, indent=2))
    elif not csv_output and not subdivision_csv_output:
        for entry in parsed:
            print(entry)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract structured weather data from AIWS .docx bulletins")
    parser.add_argument(
        "--file",
        "-f",
        help="Specific .docx file name inside the AIWS2025 folder",
        default=None,
    )
    parser.add_argument(
        "--folder",
        "-d",
        help="Path to the AIWS2025 folder",
        default=Path(__file__).parent / "AIWS2025",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print structured output as JSON",
    )
    parser.add_argument(
        "--csv",
        help="Write structured output to CSV file",
        default=None,
    )
    parser.add_argument(
        "--subdivision-csv",
        help="Write a new CSV with official subdivisions from weather_form.js (does not update --csv file)",
        default=None,
    )
    parser.add_argument(
        "--enrich-csv",
        help="Map subdivisions from an existing extraction CSV (use with --subdivision-csv, skips .docx parsing)",
        default=None,
    )
    parser.add_argument(
        "--glob",
        help="Glob pattern for selecting .docx files when --file is not provided",
        default="*.docx",
    )
    args = parser.parse_args()
    main(
        Path(args.folder),
        args.file,
        args.json,
        args.csv,
        args.subdivision_csv,
        args.enrich_csv,
        args.glob,
    )
