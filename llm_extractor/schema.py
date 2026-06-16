"""Pydantic models for the structured output returned by Claude.

The model is forced to emit a `BulletinExtraction` (a list of `WeatherSystem`
objects). All fields are required — the model fills sentinels ("" / 0 / false)
rather than omitting, which keeps the JSON schema strict.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class WeatherSystemType(str, Enum):
    """Canonical IMD synoptic-system types we extract.

    The first three match the codes already in the database; the rest are the
    monsoon-season systems the old regex extractor dropped entirely.
    """

    western_disturbance = "Western Disturbance"
    cyclonic_circulation = "Cyclonic Circulation"
    trough = "Trough"
    low_pressure_area = "Low Pressure Area"
    well_marked_low_pressure_area = "Well Marked Low Pressure Area"
    depression = "Depression"
    deep_depression = "Deep Depression"
    cyclonic_storm = "Cyclonic Storm"
    severe_cyclonic_storm = "Severe Cyclonic Storm"
    very_severe_cyclonic_storm = "Very Severe Cyclonic Storm"
    extremely_severe_cyclonic_storm = "Extremely Severe Cyclonic Storm"
    super_cyclonic_storm = "Super Cyclonic Storm"


# How each canonical type is written into the `weather_system` column.
# The original 338 rows use WD / CYCIR / Trough, so we preserve those codes and
# use full names for the newly-captured types. Edit here to change the scheme.
DB_LABELS: dict[WeatherSystemType, str] = {
    WeatherSystemType.western_disturbance: "WD",
    WeatherSystemType.cyclonic_circulation: "CYCIR",
    WeatherSystemType.trough: "Trough",
}


def db_label(system: WeatherSystemType) -> str:
    return DB_LABELS.get(system, system.value)


class WeatherSystem(BaseModel):
    weather_system: WeatherSystemType = Field(
        description="The synoptic system type, as one of the allowed labels."
    )
    region: str = Field(
        description=(
            "The region exactly as described in the bulletin (e.g. 'northeast "
            "Jharkhand & adjoining Gangetic West Bengal', or a coordinate phrase "
            "like 'along Long. 89E north of Lat. 22N'). Resolve 'the same region' "
            "/ 'it' from earlier context. Empty string only if truly none."
        )
    )
    subdivisions: list[str] = Field(
        description=(
            "Official meteorological subdivisions this system lies over, chosen "
            "ONLY from the allowed list in the system prompt. Map the bulletin's "
            "wording (states, seas, coordinates) to one or more exact names. "
            "Empty list if none can be determined."
        )
    )
    height_km: float = Field(
        description=(
            "Top height in km above mean sea level if the bulletin states one "
            "(use the upper value of a range). 0 if not stated."
        )
    )
    pressure_level: str = Field(
        description=(
            "Explicit pressure level if the bulletin gives one (e.g. '850 hPa'). "
            "Empty string if not stated — it will be derived from height_km."
        )
    )
    status: str = Field(
        description=(
            "Free-text status/verb if present: e.g. 'persisted', 'continued', "
            "'weakened', 'became less marked', 'merged', 'lay over', 'extended'. "
            "Empty string if none."
        )
    )
    is_forecast: bool = Field(
        description=(
            "True if this system is only a forecast/outlook (phrases like "
            "'likely to form', 'is likely to affect', 'expected to develop'), "
            "rather than a currently-observed system. Observed systems are False."
        )
    )


class BulletinExtraction(BaseModel):
    systems: list[WeatherSystem] = Field(
        description="Every distinct weather system in the bulletin summary."
    )
