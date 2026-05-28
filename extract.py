from pathlib import Path
import argparse
import csv
import json
import re
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
    return sorted(folder.glob(pattern))


def read_docx_paragraphs(path: Path) -> list[str]:
    """Read paragraphs from a .docx Word file using the standard library."""
    if not path.exists():
        raise FileNotFoundError(f"Word file not found: {path}")
    if path.suffix.lower() != ".docx":
        raise ValueError("Only .docx Word files are supported by this script.")

    try:
        with zipfile.ZipFile(path, "r") as archive:
            with archive.open("word/document.xml") as document_xml:
                tree = ET.parse(document_xml)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"Invalid .docx file: {path}") from exc

    paragraphs = []
    for paragraph in tree.iterfind(".//w:p", namespaces=NAMESPACES):
        texts = [node.text for node in paragraph.iterfind(".//w:t", namespaces=NAMESPACES) if node.text]
        if texts:
            paragraphs.append("".join(texts))

    return paragraphs


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
    # Keep sentence-ending dot while normalizing m.s.l style abbreviations.
    text = re.sub(r"\bm\.\s*s\.\s*l\.", "msl.", text, flags=re.I)
    text = re.sub(r"\bm\.\s*s\.\s*l\b", "msl", text, flags=re.I)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    clean_sentences = [sentence.replace("<prd>", ".").strip() for sentence in sentences if sentence.strip()]
    return clean_sentences


def extract_weather_system(sentence: str) -> str | None:
    sentence_lower = sentence.lower().replace("-", " ")
    # Prioritize WD before representation words like trough/cyclonic circulation.
    if re.search(r"\bwestern disturbance(s)?\b", sentence_lower):
        return "WD"
    if re.search(r"\b(?:upper air\s+)?cyclonic circulation\b", sentence_lower):
        return "CYCIR"
    if re.search(r"\btrough\b", sentence_lower):
        return "Trough"
    return None


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
        r"(\d+(?:\.\d+)?)\s*km\s*(?:above\s+mean\s+sea\s+level|above\s+m\.s\.l\.|am\.sl\.|am\.sl|msl|mean sea level)",
        r"at\s+(\d+(?:\.\d+)?)\s*km\s*(?:above|height)",
        r"height\s+of\s+(\d+(?:\.\d+)?)\s*km",
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


def extract_from_docx(path: Path) -> list[dict]:
    paragraphs = read_docx_paragraphs(path)
    raw_text = get_summary_paragraph(paragraphs)
    bulletin_date = parse_bulletin_date(paragraphs) or parse_bulletin_date_from_filename(path)
    sentences = split_sentences(raw_text)
    parsed = [parse_sentence(sentence) for sentence in sentences if sentence]

    entities: list[dict] = []
    index_by_key: dict[tuple[str, str], int] = {}
    last_key_by_system: dict[str, tuple[str, str]] = {}

    for i, entry in enumerate(parsed):
        sentence = sentences[i].lower()
        system = entry.get("weather_system")
        region = entry.get("region")
        height = entry.get("height_km", 0.0) or 0.0
        pressure = entry.get("pressure_level")
        status = entry.get("status")

        if system not in SUPPORTED_SYSTEM_TYPES:
            # Coreference-only continuation sentence.
            if re.search(r"\bit\b|same region|same area|the same", sentence):
                system = next(iter(last_key_by_system.keys()), None)
            else:
                continue

        # Representation handling: "western disturbance as/seen as X" is only WD.
        if system != "WD" and re.search(r"\bwestern disturbance(s)?\b.*\b(as a|seen as)\b", sentence):
            system = "WD"

        # Coref region fallback.
        if not region and (re.search(r"same region|same area|the same", sentence) or re.search(r"\bit\b", sentence)):
            if system in last_key_by_system:
                region = last_key_by_system[system][1]

        if not region and system == "Trough":
            region = extract_coordinate_region_fallback(sentence)
            if not region:
                # Last resort: keep raw trough geographic phrase rather than blank.
                region = normalize_text(sentence)[:200]

        if not region:
            region = "unknown"

        key = (system, re.sub(r"\s+", " ", region.strip().lower()))

        if key in index_by_key:
            current = entities[index_by_key[key]]
            if (not current.get("height_km") or current.get("height_km") == 0.0) and height > 0.0:
                current["height_km"] = height
            if not current.get("pressure_level") and pressure:
                current["pressure_level"] = pressure
            if status:
                current["status"] = status
        else:
            entities.append(
                {
                    "date": bulletin_date,
                    "source_file": path.name,
                    "weather_system": system,
                    "region": region if region != "unknown" else "",
                    "height_km": height,
                    "pressure_level": pressure,
                    "status": status,
                }
            )
            index_by_key[key] = len(entities) - 1
            last_key_by_system[system] = key

    return entities


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
