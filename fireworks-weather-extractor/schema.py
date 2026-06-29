from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class WeatherSystemType(str, Enum):
    """Canonical IMD synoptic-system types matched to dropdown selection options."""
    # Cyclonic Circulations and Lows
    cyclonic_circulation = "Cyclonic Circulation (CYCIR)"
    low_pressure_with_associated_cycir = "Low Pressure (L) with associated CYCIR"
    well_marked_low_pressure_with_associated_cycir = "Well Marked Low Pressure Area (WML) with associated CYCIR"
    induced_cyclonic_circulation = "Induced Cyclonic Circulation"
    induced_low = "Induced Low"
    low_level_cyclonic_circulation = "Low-Level Cyclonic Circulation"
    mid_level_cyclonic_circulation = "Mid-Level Cyclonic Circulation"
    upper_level_cyclonic_circulation = "Upper-Level Cyclonic Circulation"

    # Western Disturbances & Storms
    western_disturbances = "Western Disturbances (WD)"
    western_depression = "Western Depression"
    depression = "Depression (D)"
    deep_depression = "Deep Depression (DD)"
    cyclonic_storm = "Cyclonic Storm (CS) : 63 to 88 km/h"
    severe_cyclonic_storm = "Severe Cyclonic Storm (SCS) : 89 to 117 km/h"
    very_severe_cyclonic_storm = "Very Severe Cyclonic Storm (VSCS) : 118 to 165 km/h"
    extremely_severe_cyclonic_storm = "Extremely Severe Cyclonic Storm (ESCS) : 166 to 220 km/h"
    super_cyclonic_storm = "Super Cyclonic Storm (SuCS) : \u2265 221 km/h"

    # Troughs
    trough = "Trough"
    easterly_trough = "Easterly Trough"
    westerly_trough = "Westerly Trough"
    offshore_trough = "Offshore Trough"
    at_surface_trough = "At Surface Trough"
    mean_sea_level_trough = "Mean Sea Level Trough"
    monsoon_trough_with_extension_and_tilt = "Monsoon Trough with Extension and Tilt"


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
    height_km_min: float = Field(
        description=(
            "Minimum height in km above mean sea level if a range is stated. "
            "If a single height is stated, put it here. 0 if not stated."
        )
    )
    height_km_max: float = Field(
        description=(
            "Maximum height in km above mean sea level if a range is stated. "
            "0 if a single height or no height is stated."
        )
    )
    pressure_level: str = Field(
        description=(
            "Explicit pressure level if the bulletin gives one (e.g. '850 hPa', 'Surface'). "
            "Empty string if not stated."
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
