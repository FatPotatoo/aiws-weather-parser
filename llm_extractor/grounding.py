"""Textual grounding: enforce precision=1 by verifying each LLM-extracted
weather system has verbatim evidence in the source bulletin text.

For a system to pass grounding, BOTH conditions must hold:
  (a) The system-type keyword appears in the bulletin text (case-insensitive).
  (b) At least one meaningful geographic token from the region field appears
      in the bulletin text (case-insensitive).

Any system that fails either condition is dropped — it has no textual backing
and is therefore a potential hallucination.

The check is intentionally conservative on (b): it accepts a partial geographic
word match so that "south Gujarat" passes if "Gujarat" is in the text, while
still rejecting completely invented place names.
"""
from __future__ import annotations

import re

from .schema import WeatherSystem, WeatherSystemType


# ---------------------------------------------------------------------------
# System-type keyword table
# Longer/more-specific types listed before shorter ones so that e.g. "deep
# depression" is checked before "depression" when building debug output.
# The is_grounded() check does substring search, so ordering does not affect
# correctness — it only matters for readability of the table.
# ---------------------------------------------------------------------------
SYSTEM_KEYWORDS: dict[WeatherSystemType, list[str]] = {
    WeatherSystemType.super_cyclonic_storm:             ["super cyclonic storm"],
    WeatherSystemType.extremely_severe_cyclonic_storm:  ["extremely severe cyclonic storm"],
    WeatherSystemType.very_severe_cyclonic_storm:       ["very severe cyclonic storm"],
    WeatherSystemType.severe_cyclonic_storm:            ["severe cyclonic storm"],
    WeatherSystemType.cyclonic_storm:                   ["cyclonic storm"],
    WeatherSystemType.deep_depression:                  ["deep depression"],
    WeatherSystemType.depression:                       ["depression"],
    WeatherSystemType.well_marked_low_pressure_area:    [
        "well marked low pressure area",
        "well-marked low pressure area",
    ],
    WeatherSystemType.low_pressure_area:                ["low pressure area"],
    WeatherSystemType.western_disturbance:              ["western disturbance"],
    WeatherSystemType.cyclonic_circulation:             ["cyclonic circulation"],
    WeatherSystemType.trough:                           ["trough"],
}

# Words that carry no geographic specificity on their own.
# Tokens from the region field that match these are skipped; they cannot
# distinguish one bulletin location from another.
_GEO_STOP: frozenset[str] = frozenset({
    # Articles / prepositions
    "the", "a", "an", "of", "in", "at", "on", "to", "by", "for",
    "over", "near", "from", "and", "or", "with", "into", "through",
    "about", "under", "above", "below", "along", "across",
    # Generic directional qualifiers (alone they are meaningless)
    "north", "south", "east", "west",
    "northern", "southern", "eastern", "western",
    "northeastern", "northwestern", "southeastern", "southwestern",
    "northeast", "northwest", "southeast", "southwest",
    "central", "interior", "coastal",
    # Adjacency / proximity qualifiers
    "adjoining", "neighbourhood", "neighborhood", "vicinity",
    # Overly generic geographic nouns
    "india", "sea", "bay", "ocean", "gulf",
    "region", "area", "zone", "belt", "parts",
    # Coordinate labels
    "lat", "lon", "long", "latitude", "longitude",
    # Height / level / time qualifiers that bleed into region strings
    "level", "surface", "mean", "msl", "hrs", "ist", "today", "yesterday",
})

# Minimum character length for a token to be considered meaningful.
# Filters out two-letter abbreviations and single characters.
_MIN_TOKEN_LEN = 4


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _norm(text: str) -> str:
    """Lowercase and collapse internal whitespace."""
    return re.sub(r"\s+", " ", text.lower()).strip()


def _geo_tokens(region: str) -> list[str]:
    """Extract geographic tokens from a region description.

    Returns:
      - Each individual word that is ≥ _MIN_TOKEN_LEN characters and not in
        _GEO_STOP, normalised to lowercase.
      - The full cleaned sub-phrase for each segment (after splitting on
        delimiters), also normalised, so a multi-word phrase can match as a
        unit if the individual words are all stop-words.

    Example:
      "south Gujarat & adjoining Saurashtra" ->
        ["gujarat", "saurashtra",
         "south gujarat", "adjoining saurashtra"]
    """
    tokens: list[str] = []

    # Split on common delimiters that separate distinct sub-regions
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
        # Add the full phrase
        if len(part_norm) >= _MIN_TOKEN_LEN:
            tokens.append(part_norm)

        # Add each significant individual word
        for word in part.split():
            w = word.strip(".,()-").lower()
            if len(w) >= _MIN_TOKEN_LEN and w not in _GEO_STOP:
                tokens.append(w)

    return tokens


def _coordinates_grounded(region: str, bulletin_norm: str) -> bool:
    """True if any coordinate token (e.g. '89E', '22N') in region appears in bulletin.

    Handles formats like '89E', '89.5E', '22 N', 'Lat. 22N', 'Long. 89E'.
    Matching is done without spaces so '22 N' matches '22n' in the text.
    """
    coords = re.findall(r"\d+\.?\d*\s*[NSEWnsew]", region)
    if not coords:
        return False
    bulletin_compact = bulletin_norm.replace(" ", "")
    return any(_norm(c).replace(" ", "") in bulletin_compact for c in coords)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_grounded(system: WeatherSystem, bulletin_text: str) -> bool:
    """Return True iff the system has textual evidence in the bulletin.

    Precision=1 guarantee: a system without textual evidence is dropped as
    a potential hallucination regardless of how confident the model seemed.
    """
    bn = _norm(bulletin_text)

    # -- (a) System-type keyword --
    keywords = SYSTEM_KEYWORDS.get(
        system.weather_system,
        [_norm(system.weather_system.value)],
    )
    if not any(kw in bn for kw in keywords):
        return False

    # -- (b) Region --
    if not system.region:
        # No region asserted — type keyword alone is sufficient evidence.
        return True

    region_norm = _norm(system.region)

    # Full region phrase verbatim match (fastest, most common path)
    if region_norm in bn:
        return True

    # Coordinate-based match for systems described by lat/lon
    if _coordinates_grounded(system.region, bn):
        return True

    # At least one meaningful geographic token match
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
    """Split systems into (grounded, ungrounded) based on textual evidence.

    The caller MUST drop the ungrounded list to maintain precision=1.

    Args:
        systems:       Candidates from the LLM.
        bulletin_text: The synoptic summary text the LLM saw.
        verbose:       If True, print a line for every dropped system.

    Returns:
        (kept, dropped) — both are lists of WeatherSystem.
    """
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
