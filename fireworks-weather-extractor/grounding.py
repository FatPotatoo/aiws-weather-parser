from __future__ import annotations

import re

from schema import WeatherSystem, WeatherSystemType

# System-type keyword table
SYSTEM_KEYWORDS: dict[WeatherSystemType, list[str]] = {
    # Cyclonic Circulations and Lows
    WeatherSystemType.cyclonic_circulation:             ["cyclonic circulation"],
    WeatherSystemType.low_pressure_with_associated_cycir: ["low pressure area", "low pressure", "associated cyclonic circulation", "associated upper air cyclonic circulation"],
    WeatherSystemType.well_marked_low_pressure_with_associated_cycir: ["well marked low pressure area", "well-marked low pressure area", "associated cyclonic circulation", "associated upper air cyclonic circulation"],
    WeatherSystemType.induced_cyclonic_circulation:     ["induced cyclonic circulation", "induced upper air cyclonic circulation"],
    WeatherSystemType.induced_low:                      ["induced low"],
    WeatherSystemType.low_level_cyclonic_circulation:   ["low level cyclonic circulation", "low-level cyclonic circulation"],
    WeatherSystemType.mid_level_cyclonic_circulation:   ["mid level cyclonic circulation", "mid-level cyclonic circulation"],
    WeatherSystemType.upper_level_cyclonic_circulation: ["upper level cyclonic circulation", "upper-level cyclonic circulation", "upper air cyclonic circulation"],

    # Western Disturbances & Storms
    WeatherSystemType.western_disturbances:             ["western disturbance", "western disturbances"],
    WeatherSystemType.western_depression:               ["western depression"],
    WeatherSystemType.depression:                       ["depression"],
    WeatherSystemType.deep_depression:                  ["deep depression"],
    WeatherSystemType.cyclonic_storm:                   ["cyclonic storm"],
    WeatherSystemType.severe_cyclonic_storm:            ["severe cyclonic storm"],
    WeatherSystemType.very_severe_cyclonic_storm:       ["very severe cyclonic storm"],
    WeatherSystemType.extremely_severe_cyclonic_storm:  ["extremely severe cyclonic storm"],
    WeatherSystemType.super_cyclonic_storm:             ["super cyclonic storm"],

    # Troughs
    WeatherSystemType.trough:                           ["trough"],
    WeatherSystemType.easterly_trough:                  ["easterly trough", "trough in easterlies", "trough in easterly"],
    WeatherSystemType.westerly_trough:                  ["westerly trough", "trough aloft in westerlies", "trough aloft in middle & upper tropospheric westerlies", "trough in westerlies", "trough in middle & upper tropospheric westerlies", "trough in middle and upper tropospheric westerlies", "trough aloft in middle & upper tropospheric levels", "trough aloft in middle and upper tropospheric levels", "trough aloft"],
    WeatherSystemType.offshore_trough:                  ["offshore trough", "off-shore trough"],
    WeatherSystemType.at_surface_trough:                ["at surface trough", "surface trough"],
    WeatherSystemType.mean_sea_level_trough:            ["mean sea level trough", "trough at mean sea level"],
    WeatherSystemType.monsoon_trough_with_extension_and_tilt: ["monsoon trough"],
}

# Words that carry no geographic specificity on their own.
_GEO_STOP: frozenset[str] = frozenset({
    "the", "a", "an", "of", "in", "at", "on", "to", "by", "for",
    "over", "near", "from", "and", "or", "with", "into", "through",
    "about", "under", "above", "below", "along", "across",
    "north", "south", "east", "west",
    "northern", "southern", "eastern", "western",
    "northeastern", "northwestern", "southeastern", "southwestern",
    "northeast", "northwest", "southeast", "southwest",
    "central", "interior", "coastal",
    "adjoining", "neighbourhood", "neighborhood", "vicinity",
    "india", "sea", "bay", "ocean", "gulf",
    "region", "area", "zone", "belt", "parts",
    "lat", "lon", "long", "latitude", "longitude",
    "level", "surface", "mean", "msl", "hrs", "ist", "today", "yesterday",
})

_MIN_TOKEN_LEN = 4


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _geo_tokens(region: str) -> list[str]:
    tokens: list[str] = []
    parts = re.split(
        r"[&,/]|\b(?:adjoining|neighbourhood|neighborhood|and|near|to|from|across)\b",
        region,
        flags=re.I,
    )
    for part in parts:
        part = part.strip(" .,()-")
        if not part:
            continue
        part_norm = _norm(part)
        if len(part_norm) >= _MIN_TOKEN_LEN:
            tokens.append(part_norm)
        for word in part.split():
            w = word.strip(".,()-").lower()
            if len(w) >= _MIN_TOKEN_LEN and w not in _GEO_STOP:
                tokens.append(w)
    return tokens


def _coordinates_grounded(region: str, bulletin_norm: str) -> bool:
    coords = re.findall(r"\d+\.?\d*\s*[NSEWnsew]", region)
    if not coords:
        return False
    bulletin_compact = bulletin_norm.replace(" ", "")
    return any(_norm(c).replace(" ", "") in bulletin_compact for c in coords)


def is_grounded(system: WeatherSystem, bulletin_text: str) -> bool:
    bn = _norm(bulletin_text)
    keywords = SYSTEM_KEYWORDS.get(
        system.weather_system,
        [_norm(system.weather_system.value)],
    )
    if not any(kw in bn for kw in keywords):
        return False
    if not system.region:
        return True
    region_norm = _norm(system.region)
    if region_norm in bn:
        return True
    if _coordinates_grounded(system.region, bn):
        return True
    for token in _geo_tokens(system.region):
        if token in bn:
            return True
    return False


def apply_grounding_filter(
    systems: list[WeatherSystem],
    bulletin_text: str,
    *,
    verbose: bool = False,
) -> tuple[list[WeatherSystem], list[WeatherSystem]]:
    kept: list[WeatherSystem] = []
    dropped: list[WeatherSystem] = []
    for sys in systems:
        if is_grounded(sys, bulletin_text):
            kept.append(sys)
        else:
            dropped.append(sys)
            if verbose:
                print(
                    f"    [grounding-drop] {sys.weather_system.value} "
                    f"over {sys.region!r} — no textual evidence"
                )
    return kept, dropped
