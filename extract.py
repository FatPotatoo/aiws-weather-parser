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
    r"became less marked": "became less marked",
    r"became less marked\b": "became less marked",
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
        r"(?<=\.)\s+(?=The\s+(?:upper air\s+)?cyclonic circulation|The\s+(?:north[- ]south\s+)?trough|"
        r"A\s+(?:north[- ]south\s+)?trough|The\s+western disturbance|An?\s+(?:upper air\s+)?cyclonic circulation|It\s+then\b)",
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


def clean_region_text(region: str) -> str:
    """Strip temporal/noise suffixes from region strings."""
    region = region.strip(" ,.;")
    region = re.sub(r"\s+of today morning\.?$", "", region, flags=re.I)
    region = re.sub(r"\s+also\.?$", "", region, flags=re.I)
    region = re.sub(r"\s+then persisted.*$", "", region, flags=re.I)
    return region.strip()


def normalize_region_key(region: str) -> str:
    return re.sub(r"\s+", " ", clean_region_text(region).lower())


def format_regions(regions: list[str]) -> str:
    cleaned = [clean_region_text(r) for r in regions if r and clean_region_text(r)]
    return " ; ".join(cleaned)


def is_continuation_sentence(sentence: str) -> bool:
    return bool(re.match(r"^\s*it\b", sentence.lower()))


def detect_primary_system(sentence: str) -> str | None:
    """Detect weather system from sentence subject, not embedded references."""
    s = sentence.lower().strip()
    if is_continuation_sentence(sentence):
        return None

    subject_patterns = [
        (r"^the\s+(?:fresh\s+)?western disturbance\b", "WD"),
        (r"^a\s+fresh\s+western disturbance\b", "WD"),
        (r"^the\s+western disturbance\b", "WD"),
        (r"^the\s+(?:north[- ]south\s+)?trough\b", "Trough"),
        (r"^a\s+(?:north[- ]south\s+)?trough\b", "Trough"),
        (r"^the\s+(?:upper air\s+)?cyclonic circulation\b", "CYCIR"),
        (r"^an?\s+(?:upper air\s+)?cyclonic circulation\b", "CYCIR"),
    ]
    for pattern, system in subject_patterns:
        if re.search(pattern, s):
            return system

    if re.search(r"\bwestern disturbance(s)?\s+(?:as a|seen as a)\b", s):
        return "WD"
    return None


def has_additional_trough(sentence: str) -> bool:
    return bool(re.search(r"\bwith a trough\b|\bassociated trough\b", sentence.lower()))


def extract_wd_region(sentence: str) -> str | None:
    s = sentence.lower()
    patterns = [
        r"western disturbance(?:s)?(?:\s+as a|\s+seen as a)?\s+(?:cyclonic circulation|trough)?\s+over\s+([^.;]+?)(?:\s+at|\s+between|\s+with|\s+persisted|\s+lay|\s+of today|\.)",
        r"western disturbance(?:s)?\s+over\s+([^.;]+?)(?:\s+at|\s+between|\s+with|\s+persisted|\.)",
    ]
    for pattern in patterns:
        match = re.search(pattern, s)
        if match:
            return clean_region_text(match.group(1))
    return None


def extract_cycir_region(sentence: str) -> str | None:
    s = sentence.lower()
    patterns = [
        r"(?:upper air\s+)?cyclonic circulation\s+over\s+([^.;]+?)(?:\s+which|\s+persisted|\s+lay|\s+became|\s+at|\s+of today|\s+and|\.)",
        r"(?:upper air\s+)?cyclonic circulation\s+lay\s+over\s+([^.;]+?)(?:\s+of today|\s+at|\s+persisted|\s+which|\.)",
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
        r"with a trough aloft[^.]*?at\s+(\d+(?:\.\d+)?)\s*km",
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
    patterns = [
        r"(\d+(?:\.\d+)?)\s*km\s*(?:above\s+mean\s+sea\s+level|above\s+m\.s\.l\.|above\s+msl|am\.sl\.|am\.sl|msl|mean sea level)",
        r"at\s+(\d+(?:\.\d+)?)\s*km\s*(?:above|height)",
        r"height\s+of\s+(\d+(?:\.\d+)?)\s*km",
        r"upto\s+(\d+(?:\.\d+)?)\s*km",
        r"extended\s+upto\s+(\d+(?:\.\d+)?)\s*km",
    ]
    sentence_lower = sentence.lower()
    for pattern in patterns:
        match = re.search(pattern, sentence_lower)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                continue
    return 0.0


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

    def _merge_fields(self, idx: int, height: float, status: str | None, pressure: str | None) -> None:
        entity = self.entities[idx]
        if height > 0.0 and float(entity.get("height_km", 0.0) or 0.0) == 0.0:
            entity["height_km"] = height
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
    ) -> int:
        key = self._entity_key(system, regions)
        region_str = format_regions(regions)

        if key in self.index:
            idx = self.index[key]
            self._merge_fields(idx, height, status, pressure)
        else:
            entity = {
                "date": self.date,
                "source_file": self.source_file,
                "weather_system": system,
                "region": region_str,
                "height_km": height or 0.0,
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

    def update_last(self, height: float = 0.0, status: str | None = None, pressure: str | None = None) -> None:
        if self.last_idx is None:
            return
        self._merge_fields(self.last_idx, height, status, pressure)

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

        height = extract_height(normalized) or 0.0
        status = extract_status(normalized)
        pressure = extract_pressure_level(normalized)

        # Rule 2: "It then persisted..." refers to the last mentioned entity.
        if is_continuation_sentence(normalized):
            tracker.update_last(height=height, status=status or "persisted", pressure=pressure)

            # Rule 4: "with a trough aloft" introduces an additional trough system.
            aloft_regions, aloft_height = extract_trough_aloft_info(normalized)
            if aloft_regions or aloft_height > 0.0:
                tracker.upsert("Trough", aloft_regions, aloft_height, None, pressure)
            continue

        # Standalone trough-aloft fragment (after sentence merge).
        if re.match(r"^\s*with a trough\b", normalized, re.I):
            aloft_regions, aloft_height = extract_trough_aloft_info(normalized)
            if aloft_regions or aloft_height > 0.0:
                tracker.upsert("Trough", aloft_regions, aloft_height, None, pressure)
            continue

        primary = detect_primary_system(normalized)
        if not primary and re.search(r"\b(?:north[- ]south\s+)?trough\b.*\b(?:ran|run|extends?|extended)\b", sentence_lower):
            primary = "Trough"
        if not primary:
            continue

        if primary == "WD":
            region = extract_wd_region(normalized)
            tracker.upsert("WD", [region] if region else [], height, status, pressure)

            aloft_regions, aloft_height = extract_trough_aloft_info(normalized)
            if aloft_regions or aloft_height > 0.0:
                tracker.upsert("Trough", aloft_regions, aloft_height, None, pressure)
            continue

        if primary == "CYCIR":
            region = extract_cycir_region(normalized)
            if not region:
                continue

            # Status-only mention of an existing CYCIR — do not create duplicate.
            if status == "became less marked" and tracker.update_status_by_region("CYCIR", region, status, height):
                continue

            tracker.upsert("CYCIR", [region], height, status, pressure)
            continue

        if primary == "Trough":
            path_regions = extract_trough_path_regions(normalized)
            if path_regions:
                tracker.upsert("Trough", path_regions, height, status, pressure)
                continue

            region = extract_trough_region(normalized)
            if status == "became less marked" and region and tracker.update_status_by_region("Trough", region, status, height):
                continue

            tracker.upsert("Trough", [region] if region else [], height, status, pressure)


def extract_from_docx(path: Path) -> list[dict]:
    paragraphs = read_docx_paragraphs(path)
    raw_text = get_summary_paragraph(paragraphs)
    bulletin_date = parse_bulletin_date(paragraphs) or parse_bulletin_date_from_filename(path)
    sentences = split_sentences(raw_text)

    tracker = EntityTracker(bulletin_date, path.name)
    process_summary_sentences(sentences, tracker)
    return tracker.entities


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
            if float(existing.get("height_km", 0.0) or 0.0) == 0.0 and float(row.get("height_km", 0.0) or 0.0) > 0.0:
                existing["height_km"] = row.get("height_km", 0.0)
            if not existing.get("pressure_level") and row.get("pressure_level"):
                existing["pressure_level"] = row.get("pressure_level")
            if row.get("status"):
                existing["status"] = row.get("status")
            continue
        seen.add(dedup_key)
        unique.append(row)
    return unique


def write_csv(data: list[dict], path: Path) -> None:
    fieldnames = ["date", "source_file", "weather_system", "region", "height_km", "pressure_level", "status"]
    with path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in data:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def main(
    folder: Path,
    filename: str | None = None,
    json_output: bool = False,
    csv_output: str | None = None,
    pattern: str = "*.docx",
) -> None:
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

    if json_output:
        print(json.dumps(parsed, indent=2))
    elif not csv_output:
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
        "--glob",
        help="Glob pattern for selecting .docx files when --file is not provided",
        default="*.docx",
    )
    args = parser.parse_args()
    main(Path(args.folder), args.file, args.json, args.csv, args.glob)
