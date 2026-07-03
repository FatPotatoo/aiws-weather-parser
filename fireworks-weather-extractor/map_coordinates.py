"""
Coordinate mapping script for output_jan_mar_2024.csv.

Reads the CSV and maps region entries that contain lat/lon coordinates (or
foreign country names) to official IMD meteorological subdivision names,
then writes a new CSV with an added `subdivisions` column.
"""
import csv
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
GAZETTEER_PATH = ROOT / "data" / "form_subdivisions_gazetteer.json"
DEFAULT_INPUT = Path(__file__).parent / "output_jan_mar_2024.csv"

# ── Gazetteer ────────────────────────────────────────────────────────────────

def load_gazetteer() -> list[dict]:
    return json.loads(GAZETTEER_PATH.read_text(encoding="utf-8"))


MARINE_SUBDIVISIONS = {
    "NW Arabian Sea", "NE Arabian Sea", "WC Arabian Sea", "EC Arabian Sea",
    "SW Arabian Sea", "SE Arabian Sea",
    "NW Bay", "NE Bay", "WC Bay", "EC Bay", "SW Bay", "SE Bay",
    "N Andaman Sea", "S Andaman Sea",
    "Comorin Area", "Gulf of Mannar",
    # Lakshadweep excluded: it's an island group, not an open-sea region, so
    # equatorial ocean CYCIRs should map to actual sea subdivisions instead.
}

# ── Distance helpers ──────────────────────────────────────────────────────────

def euclidean(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return math.sqrt((lat1 - lat2) ** 2 + (lon1 - lon2) ** 2)


def nearest_subdivisions(
    lat: float,
    lon: float,
    gazetteer: list[dict],
    n: int = 3,
    marine_only: bool = False,
) -> list[str]:
    """Return the n nearest gazetteer entries to (lat, lon)."""
    candidates = gazetteer
    if marine_only:
        candidates = [g for g in gazetteer if g["name"] in MARINE_SUBDIVISIONS]

    scored: list[tuple[float, str]] = []
    seen: set[str] = set()
    for entry in candidates:
        name = entry["name"]
        dist = euclidean(lat, lon, float(entry["lat"]), float(entry["lon"]))
        scored.append((dist, name))

    scored.sort()
    result: list[str] = []
    for _, name in scored:
        if name not in seen:
            seen.add(name)
            result.append(name)
        if len(result) >= n:
            break
    return result


# ── Coordinate parsers ────────────────────────────────────────────────────────

# "centered at Lat 2.8°N and Long 82.2°E"  (must NOT start with "between")
_POINT_RE = re.compile(
    r"(?<!between\s)"          # negative lookbehind guard — handled by range check first
    r"centered\s+at\s+"
    r"lat(?:itude)?\.?\s*([0-9]+(?:\.[0-9]+)?)[^0-9]{0,6}[Nn]"
    r".*?"
    r"long(?:itude)?\.?\s*([0-9]+(?:\.[0-9]+)?)[^0-9]{0,6}[Ee]",
    re.I | re.S,
)

# "between Lat. 30°N/Long. 82°E and Lat. 24°N/Long. 70°E"
# "between Long. 45°E/Lat. 28°N and Long. 68°E/Lat. 40°N"
_RANGE_RE = re.compile(
    r"between\s+"
    r"(?:lat\.?\s*([0-9]+(?:\.[0-9]+)?)\s*°?\s*[Nn]\s*/\s*long\.?\s*([0-9]+(?:\.[0-9]+)?)\s*°?\s*[Ee]"
    r"|long\.?\s*([0-9]+(?:\.[0-9]+)?)\s*°?\s*[Ee]\s*/\s*lat\.?\s*([0-9]+(?:\.[0-9]+)?)\s*°?\s*[Nn])"
    r"\s+and\s+"
    r"(?:lat\.?\s*([0-9]+(?:\.[0-9]+)?)\s*°?\s*[Nn]\s*/\s*long\.?\s*([0-9]+(?:\.[0-9]+)?)\s*°?\s*[Ee]"
    r"|long\.?\s*([0-9]+(?:\.[0-9]+)?)\s*°?\s*[Ee]\s*/\s*lat\.?\s*([0-9]+(?:\.[0-9]+)?)\s*°?\s*[Nn])",
    re.I,
)


def parse_point(text: str) -> tuple[float, float] | None:
    m = _POINT_RE.search(text)
    if m:
        return float(m.group(1)), float(m.group(2))
    return None


def parse_range(text: str) -> tuple[tuple[float, float], tuple[float, float]] | None:
    m = _RANGE_RE.search(text)
    if not m:
        return None
    g = m.groups()
    # First endpoint: (lat1, lon1)
    if g[0] is not None:
        lat1, lon1 = float(g[0]), float(g[1])
    else:
        lat1, lon1 = float(g[3]), float(g[2])
    # Second endpoint: (lat2, lon2)
    if g[4] is not None:
        lat2, lon2 = float(g[4]), float(g[5])
    else:
        lat2, lon2 = float(g[7]), float(g[6])
    return (lat1, lon1), (lat2, lon2)


# ── Country-name overrides ────────────────────────────────────────────────────

COUNTRY_OVERRIDES: dict[str, list[str]] = {
    # Afghanistan variants → Far West Pakistan (nearest IMD-recognised region)
    "afghanistan": ["Far West Pakistan"],
    "northwest afghanistan": ["Far West Pakistan"],
    "central afghanistan": ["Far West Pakistan"],
    "east afghanistan": ["Far West Pakistan"],
    "north afghanistan": ["Far West Pakistan"],
    "south afghanistan": ["Far West Pakistan"],
    "west afghanistan": ["Far West Pakistan"],
    "north afghanistan & adjoining pakistan": ["Far West Pakistan", "Pakistan"],
    "north afghanistan and adjoining pakistan": ["Far West Pakistan", "Pakistan"],
    # Iran variants
    "northwest iran": ["Iran"],
    "iran": ["Iran"],
    # Sri Lanka variants
    "sri lanka": ["SW Bay", "Comorin Area"],
    "south sri lanka": ["SW Bay", "Comorin Area"],
    "north sri lanka": ["SW Bay", "Comorin Area"],
}

# "Far West Pakistan" is in IMD bulletins but not in the form-subdivision allowed
# list; keep it here so the mapping is recognisable to downstream consumers.


def country_override(region: str) -> list[str] | None:
    key = region.strip().lower()
    # normalise & → and, strip trailing "and/& neighbourhood"
    key = key.replace(" & ", " and ")
    key_clean = re.sub(r"\s*and\s+neighbourhood$", "", key).strip()
    return COUNTRY_OVERRIDES.get(key_clean) or COUNTRY_OVERRIDES.get(key)


def is_coordinate_region(region: str) -> bool:
    return bool(re.search(r"\balong\s+long\.?", region.lower()))


def parse_coordinate_constraints(region: str) -> tuple[float | None, float | None]:
    """Parse longitude and minimum latitude (north-of) from coordinate region text."""
    text = region.lower()
    lon_match = re.search(r"long(?:itude)?\.?\s*([0-9]+(?:\.[0-9]+)?)\s*°?", text)
    lat_match = re.search(r"lat(?:itude)?\.?\s*([0-9]+(?:\.[0-9]+)?)\s*°?", text)
    longitude = float(lon_match.group(1)) if lon_match else None
    min_latitude = float(lat_match.group(1)) if lat_match else None
    return longitude, min_latitude


def resolve_coordinate_to_subdivisions(region: str, gazetteer: list[dict], lon_tolerance: float = 3.5) -> list[str]:
    """
    Map coordinate phrases (e.g. along Long. 89°E north of Lat. 22°N) to IMD subdivisions
    using centroid proximity and latitude constraints.
    """
    longitude, min_latitude = parse_coordinate_constraints(region)
    if longitude is None:
        return []

    # If the coordinate is far west (longitude < 68), we can widen the tolerance to match Pakistan/Iran
    actual_tolerance = lon_tolerance
    if longitude < 68.0:
        actual_tolerance = 15.0  # allow matching Pakistan or Iran subdivisions if far west

    matches: list[tuple[float, str]] = []
    for item in gazetteer:
        lat = float(item["lat"])
        lon = float(item["lon"])
        if abs(lon - longitude) > actual_tolerance:
            continue
        if min_latitude is not None and lat < min_latitude - 0.5:
            continue
        distance = abs(lon - longitude) + (max(0.0, min_latitude - lat) if min_latitude else 0.0)
        matches.append((distance, item["name"]))

    matches.sort(key=lambda pair: pair[0])
    unique_names = []
    for _, name in matches:
        if name not in unique_names:
            unique_names.append(name)
        if len(unique_names) >= 5:
            break
    return unique_names


# ── Main mapping ──────────────────────────────────────────────────────────────

def map_region(region: str, gazetteer: list[dict]) -> list[str]:
    """Map a single region string to official subdivision names."""
    region = region.strip()
    if not region:
        return []

    # 1. Coordinate range checked FIRST to avoid false point matches.
    # "between Lat X1°N/Long Y1°E and Lat X2°N/Long Y2°E"
    rng = parse_range(region)
    if rng:
        (lat1, lon1), (lat2, lon2) = rng
        max_lon = max(lon1, lon2)
        min_lon = min(lon1, lon2)
        # If the entire range is west of 68°E it's over the Middle East — use all gazetteer
        # entries (which include Iran); if it crosses into India, use land+sea but not
        # strictly marine-only.
        marine_only = max_lon < 60  # only pure open-sea ranges get marine filter

        # Sample 7 points along the axis
        subs: list[str] = []
        seen: set[str] = set()
        for i in range(7):
            t = i / 6.0
            lat = lat1 + t * (lat2 - lat1)
            lon = lon1 + t * (lon2 - lon1)
            for s in nearest_subdivisions(lat, lon, gazetteer, n=1, marine_only=marine_only):
                if s not in seen:
                    seen.add(s)
                    subs.append(s)
        return subs

    # 2. Point coordinate: "east Equatorial Indian Ocean centered at Lat X°N and Long Y°E"
    point = parse_point(region)
    if point:
        lat, lon = point
        # These are open-ocean equatorial locations — use marine subdivisions only
        marine = nearest_subdivisions(lat, lon, gazetteer, n=2, marine_only=True)
        if marine:
            return marine
        return nearest_subdivisions(lat, lon, gazetteer, n=2)

    # 3. Coordinate line (e.g. along Longitude 80°E to the north of Latitude 30°N)
    if is_coordinate_region(region):
        mapped = resolve_coordinate_to_subdivisions(region, gazetteer)
        if mapped:
            return mapped

    # 4. Country-name override
    override = country_override(region)
    if override:
        return override

    # 5. Already a named subdivision (semicolon-separated) — pass through as-is
    parts = [p.strip() for p in region.split(";") if p.strip()]
    return parts


def format_subdivisions(subs: list[str]) -> str:
    return " ; ".join(subs)


# ── CSV processing ────────────────────────────────────────────────────────────

def main() -> None:
    input_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_INPUT
    stem = input_path.stem
    output_path = input_path.parent / f"{stem}_mapped.csv"

    gazetteer = load_gazetteer()

    with open(input_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # Identify which rows need coordinate/country mapping
    needs_mapping: list[int] = []
    for i, row in enumerate(rows):
        region = row.get("Regions", "")
        if parse_point(region) or parse_range(region) or country_override(region):
            needs_mapping.append(i)

    print(f"Input:  {input_path}")
    print(f"Rows needing coordinate/country mapping: {len(needs_mapping)}")
    for i in needs_mapping:
        row = rows[i]
        region = row["Regions"]
        mapped = map_region(region, gazetteer)
        print(f"  Line {i+2}: {region!r}")
        print(f"         -> {mapped}")

    # Write output CSV
    fieldnames = list(rows[0].keys()) + ["subdivisions"]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            region = row.get("Regions", "")
            mapped = map_region(region, gazetteer)
            row["subdivisions"] = format_subdivisions(mapped)
            writer.writerow(row)

    print(f"\nOutput written to: {output_path}")


if __name__ == "__main__":
    main()
