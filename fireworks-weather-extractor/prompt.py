from __future__ import annotations

import json

SUBDIVISIONS = [
    'Andaman & Nicobar Islands', 'Arunachal Pradesh', 'Assam & Meghalaya', 'Bihar', 'Chhattisgarh',
    'Coastal Andhra Pradesh', 'Coastal Karnataka', 'East Madhya Pradesh', 'East Rajasthan',
    'East Uttar Pradesh', 'Gangetic West Bengal', 'Gujarat Region', 'Haryana, Chandigarh & Delhi',
    'Himachal Pradesh', 'Jammu & Kashmir', 'Jharkhand', 'Kerala', 'Konkan & Goa', 'Lakshadweep',
    'Madhya Maharashtra', 'Marathwada', 'Nagaland, Manipur, Mizoram & Tripura', 'North Interior Karnataka',
    'Odisha', 'Punjab', 'Rayalaseema', 'Saurashtra & Kutch', 'Sikkim', 'South Interior Karnataka',
    'Sub-Himalayan West Bengal & Sikkim', 'Tamil Nadu & Puducherry', 'Telangana', 'Uttarakhand',
    'Vidarbha', 'West Madhya Pradesh', 'West Rajasthan', 'West Uttar Pradesh', 'NW Arabian Sea',
    'NE Arabian Sea', 'WC Arabian Sea', 'EC Arabian Sea', 'SW Arabian Sea', 'SE Arabian Sea',
    'NW Bay', 'NE Bay', 'WC Bay', 'EC Bay', 'SW Bay', 'SE Bay', 'N Andaman Sea', 'S Andaman Sea',
    'Central Pakistan', 'Pakistan', 'North pakistan', 'Bangladesh', 'Iran', 'Gulf of Mannar',
    'Comorin Area'
]

INSTRUCTIONS = """You extract structured data from India Meteorological Department (IMD) "All India Weather Summary" (AIWS) bulletins. You are given the synoptic-summary prose from one daily bulletin. Your task is to extract ONLY currently observed or forecast Depressions, Deep Depressions, and Cyclonic Storms (collectively referred to as "depression entries").

Do NOT extract Western Disturbances, general Cyclonic Circulations, Low Pressure Areas, or Troughs. Focus ONLY on Depressions, Deep Depressions, and Cyclonic Storms.

Weather system classification mapping (you must output one of these exact values for weather_system):
- For Depression, use: "Depression (D)"
- For Deep Depression, use: "Deep Depression (DD)"
- For Cyclonic Storms, map according to intensity/speed. If no wind speed is mentioned in the bulletin, map it to the lowest wind speed category: "Cyclonic Storm (CS) : 63 to 88 km/h". If wind speed is mentioned, choose the appropriate category:
  - "Cyclonic Storm (CS) : 63 to 88 km/h"
  - "Severe Cyclonic Storm (SCS) : 89 to 117 km/h"
  - "Very Severe Cyclonic Storm (VSCS) : 118 to 165 km/h"
  - "Extremely Severe Cyclonic Storm (ESCS) : 166 to 220 km/h"
  - "Super Cyclonic Storm (SuCS) : \u2265 221 km/h"

Extraction rules:
1. ONLY extract Depressions, Deep Depressions, and Cyclonic Storms. Do not extract other types of weather systems (like low pressure areas or troughs).
2. 08:30 OBSERVED LOCATION RULE: Depressions and Cyclonic Storms move throughout the day and the bulletin historical log lists positions at multiple times (e.g. 05:30 hrs IST of today, 17:30 hrs IST of yesterday). You MUST extract ONLY the position (region) and details corresponding to 08:30 hrs IST of 'today' (the bulletin date). Ignore positions at other times like 05:30 or 17:30.
3. Resolve coreference: "it", "the same region", "the system" refer to the most recently described system/region. Fill the resolved region.
4. region = the wording as written in the bulletin for the 08:30 position (state names, "& adjoining ...", "& neighbourhood", or a coordinate phrase like "along Long. 89E north of Lat. 22N"). Strip trailing timestamps ("at 0830 hrs IST of today").
5. subdivisions = map the region to one or more names from the ALLOWED LIST below. Use only exact names from that list. One region may map to several. If you cannot map it, return an empty list.
6. height_km_min and height_km_max = set both to 0.0 unless height is explicitly mentioned for the 08:30 depression position (which is rare). pressure_level = empty string unless explicitly stated.
7. status = the verb/state if present at 08:30 (persisted, continued, weakened, became less marked, merged, lay over, extended, ...); else empty.
8. is_forecast = true ONLY for outlook/forecast mentions ("likely to form", "is likely to affect", "expected to develop around ..."). Currently-observed systems are false. Still return forecast systems — they are filtered downstream — just flag them.
9. Do not invent systems. Do not include the "northern limit of monsoon" line or monsoon withdrawal line as a system.
10. LESS MARKED: when a system has become less marked / dissipated at 08:30, put that in status (e.g. "became less marked").

Return your answer using the structured output schema (a list of systems). If the text contains no weather systems, return an empty list.

ALLOWED SUBDIVISION LIST (use these exact strings for `subdivisions`):
"""

def build_system_prompt() -> str:
    listing = "\n".join(f"- {name}" for name in SUBDIVISIONS)
    return INSTRUCTIONS + listing

# Few-shot examples
_FEWSHOT_USER_1 = (
    "Bulletin date: 2020-01-01\n\nSummary text:\n"
    "The upper air cyclonic circulation over south Gujarat persisted at 1.5 km above "
    "m. s. l. The upper air cyclonic circulation lay over east Bihar at 0.9 km above "
    "m. s. l. It then persisted over the same region. A trough at mean sea level ran "
    "from south Gujarat to east Bihar across Madhya Pradesh."
)
_FEWSHOT_SYSTEMS_1 = {
    "systems": []
}

_FEWSHOT_USER_2 = (
    "Bulletin date: 2025-09-28\n\nSummary text:\n"
    "The Depression over south coastal Odisha moved westwards and lay centred at 1130 hrs IST "
    "of yesterday over south interior Odisha. It moved west-northwestwards and lay centred at 0530 "
    "hrs IST of today over south Chhattisgarh. It then lay centred at 0830 hrs IST of today over "
    "west Vidarbha and neighbourhood."
)
_FEWSHOT_SYSTEMS_2 = {
    "systems": [
        {
            "weather_system": "Depression (D)",
            "region": "west Vidarbha and neighbourhood",
            "subdivisions": ["Vidarbha"],
            "height_km_min": 0.0, "height_km_max": 0.0, "pressure_level": "",
            "status": "lay over", "is_forecast": False
        }
    ]
}

_FEWSHOT_USER_3 = (
    "Bulletin date: 2025-12-01\n\nSummary text:\n"
    "The Cyclonic Storm Ditwah over southwest Bay of Bengal moved northwards and lay centered "
    "at 0830 hrs IST of today over southwest Bay of Bengal and adjoining areas of westcentral "
    "Bay of Bengal, North Tamil Nadu-Puducherry & South Andhra Pradesh coasts."
)
_FEWSHOT_SYSTEMS_3 = {
    "systems": [
        {
            "weather_system": "Cyclonic Storm (CS) : 63 to 88 km/h",
            "region": "southwest Bay of Bengal and adjoining areas of westcentral Bay of Bengal, North Tamil Nadu-Puducherry & South Andhra Pradesh coasts",
            "subdivisions": ["SW Bay", "WC Bay", "Tamil Nadu & Puducherry", "Coastal Andhra Pradesh"],
            "height_km_min": 0.0, "height_km_max": 0.0, "pressure_level": "",
            "status": "lay over", "is_forecast": False
        }
    ]
}

_FEWSHOT_USER_4 = (
    "Bulletin date: 2025-11-19\n\nSummary text:\n"
    "A Low-Pressure area is likely to form over Southeast Bay of Bengal around 22nd November 2025. "
    "Thereafter, it is very likely to move west-northwestwards and intensify into Depression "
    "over central parts of south Bay of Bengal around 24th November 2025."
)
_FEWSHOT_SYSTEMS_4 = {
    "systems": [
        {
            "weather_system": "Depression (D)",
            "region": "central parts of south Bay of Bengal",
            "subdivisions": ["SW Bay", "SE Bay"],
            "height_km_min": 0.0, "height_km_max": 0.0, "pressure_level": "",
            "status": "", "is_forecast": True
        }
    ]
}

def few_shot_messages() -> list[dict]:
    pairs = [
        (_FEWSHOT_USER_1, _FEWSHOT_SYSTEMS_1),
        (_FEWSHOT_USER_2, _FEWSHOT_SYSTEMS_2),
        (_FEWSHOT_USER_3, _FEWSHOT_SYSTEMS_3),
        (_FEWSHOT_USER_4, _FEWSHOT_SYSTEMS_4),
    ]
    msgs: list[dict] = []
    for user, assistant in pairs:
        msgs.append({"role": "user", "content": user})
        msgs.append({"role": "assistant", "content": json.dumps(assistant)})
    return msgs
