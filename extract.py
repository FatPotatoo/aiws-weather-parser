from pathlib import Path
import argparse
import csv
import json
import re
import zipfile
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


def list_word_files(folder: Path):
    """Return all .docx files from the specified folder."""
    return sorted(folder.glob("*.docx"))


def read_docx_file(path: Path) -> str:
    """Read text from a .docx Word file using the standard library."""
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

    return "\n".join(paragraphs)


def normalize_text(text: str) -> str:
    """Normalize whitespace and lower-case the text for pattern matching."""
    text = text.replace("\u2013", "-")
    text = text.replace("\u2014", "-")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def split_sentences(text: str) -> list[str]:
    """Split raw text into sentences using punctuation boundaries."""
    text = text.replace("\n", " ")
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def extract_weather_system(sentence: str) -> str | None:
    sentence_lower = sentence.lower()
    for pattern, label in WEATHER_SYSTEM_PATTERNS.items():
        if re.search(rf"\b{pattern}\b", sentence_lower):
            return label
    return None


def extract_associated_system(sentence: str) -> str | None:
    sentence_lower = sentence.lower()
    for pattern, label in ASSOCIATED_SYSTEM_PATTERNS.items():
        if re.search(rf"\b{pattern}\b", sentence_lower):
            return label
    return None


def extract_region(sentence: str) -> str | None:
    sentence_lower = sentence.lower()
    for keyword in REGION_KEYWORDS:
        regex = rf"\b{keyword}\s+([a-z0-9&.,\-\s]+?)(?:\s+(?:persisted|was|became|at|with|and|,|\.|;|\)|\()|$)"
        match = re.search(regex, sentence_lower)
        if match:
            region = match.group(1).strip()[:200]
            if any(re.search(pattern, region) for pattern in SAME_REGION_PATTERNS):
                return None
            return region
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
    raw_text = read_docx_file(path)
    sentences = split_sentences(raw_text)
    parsed = [parse_sentence(sentence) for sentence in sentences if sentence]
    parsed = resolve_context(parsed, sentences)
    return [entry for entry in parsed if entry.get("weather_system") is not None]


def write_csv(data: list[dict], path: Path) -> None:
    fieldnames = ["weather_system", "region", "height_km", "pressure_level", "status"]
    with path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in data:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def main(folder: Path, filename: str | None = None, json_output: bool = False, csv_output: str | None = None) -> None:
    aiws_folder = Path(folder)
    if not aiws_folder.exists() or not aiws_folder.is_dir():
        raise FileNotFoundError(f"Folder not found: {aiws_folder}")

    if filename:
        file_path = aiws_folder / filename
        parsed = extract_from_docx(file_path)
    else:
        files = list_word_files(aiws_folder)
        if not files:
            print(f"No .docx Word files were found in {aiws_folder}")
            return
        print(f"Found {len(files)} .docx files in {aiws_folder}")
        print(f"Parsing first file: {files[0].name}\n")
        parsed = extract_from_docx(files[0])

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
    args = parser.parse_args()
    main(Path(args.folder), args.file, args.json, args.csv)
