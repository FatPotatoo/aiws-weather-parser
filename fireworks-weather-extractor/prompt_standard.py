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

INSTRUCTIONS = """You extract structured data from India Meteorological Department (IMD) "All India Weather Summary" (AIWS) bulletins. You are given the synoptic-summary prose from one daily bulletin. Return every distinct weather system that is CURRENTLY OBSERVED in it.

Why this matters: this feeds a meteorological database. The previous rule-based extractor missed many systems — especially monsoon-season Low Pressure Areas and Depressions, and any system not written at the start of its sentence. Your job is high recall with correct attribution.

Weather system classification mapping (you must output one of these exact values for weather_system):
- If the system is a Western Disturbance, use: "Western Disturbances (WD)" (e.g. "western disturbance as a cyclonic circulation / trough").
- For a general cyclonic circulation without specific qualifiers, use: "Cyclonic Circulation (CYCIR)"
- If the text mentions "induced cyclonic circulation" / "induced upper air cyclonic circulation", use: "Induced Cyclonic Circulation"
- If the text mentions "low-level cyclonic circulation", use: "Low-Level Cyclonic Circulation"
- If the text mentions "mid-level cyclonic circulation", use: "Mid-Level Cyclonic Circulation"
- If the text mentions "upper-level cyclonic circulation" / "upper air cyclonic circulation" (explicitly called upper-level or upper air), use: "Upper-Level Cyclonic Circulation"
- If it is a low pressure area, use: "Low Pressure (L) with associated CYCIR"
- If it is a well marked low pressure area, use: "Well Marked Low Pressure Area (WML) with associated CYCIR"
- If it is an induced low, use: "Induced Low"
- For Western Depression, use: "Western Depression"
- For Depression, use: "Depression (D)"
- For Deep Depression, use: "Deep Depression (DD)"
- For Cyclonic Storms, map according to intensity/speed:
  - "Cyclonic Storm (CS) : 63 to 88 km/h"
  - "Severe Cyclonic Storm (SCS) : 89 to 117 km/h"
  - "Very Severe Cyclonic Storm (VSCS) : 118 to 165 km/h"
  - "Extremely Severe Cyclonic Storm (ESCS) : 166 to 220 km/h"
  - "Super Cyclonic Storm (SuCS) : \u2265 221 km/h"
- For Troughs, map according to specific type:
  - If a general trough without qualifiers, use: "Trough"
  - If "trough aloft in westerlies" / "trough in middle & upper tropospheric westerlies" / "trough aloft in middle & upper tropospheric levels" or similar westerly trough, use: "Westerly Trough"
  - If "trough in easterlies", use: "Easterly Trough"
  - If "offshore trough" / "off-shore trough", use: "Offshore Trough"
  - If "at surface trough" / "trough at surface", use: "At Surface Trough"
  - If "mean sea level trough" / "trough at mean sea level", use: "Mean Sea Level Trough"
  - If "monsoon trough with extension and tilt", use: "Monsoon Trough with Extension and Tilt"

Extraction rules:
1. Extract EVERY distinct system, even when it is introduced mid-sentence — after "Under the influence of ...", "The associated ...", "However, ...", "Yet another ...", or as a second clause ("..., a low pressure area formed over ..."). A single sentence can yield two or more systems; do not collapse them.
2. Resolve coreference: "it", "the same region", "the system" refer to the most recently described system/region. Fill the resolved region.
3. region = the wording as written in the bulletin (state names, "& adjoining ...", "& neighbourhood", or a coordinate phrase like "along Long. 89E north of Lat. 22N"). Strip trailing timestamps ("at 0530 hrs IST of today").
4. subdivisions = map the region to one or more names from the ALLOWED LIST below. Use only exact names from that list. One region may map to several (e.g. "Maharashtra" -> Madhya Maharashtra; Marathwada; Konkan & Goa). If you cannot map it, return an empty list.
5. height_km_min and height_km_max = if a range is stated, extract both points. For example, "between 1.5 and 3.1 km" -> height_km_min = 1.5, height_km_max = 3.1. If a single height is given (e.g., "at 1.5 km"), set height_km_min = 1.5, height_km_max = 0.0. If no height is stated, set both to 0.0. pressure_level = an explicit hPa level if the bulletin gives one; otherwise leave it empty.
6. status = the verb/state if present (persisted, continued, weakened, became less marked, merged, lay over, extended, ...); else empty.
7. is_forecast = true ONLY for outlook/forecast mentions ("likely to form", "is likely to affect", "expected to develop around ..."). Currently-observed systems are false. Still return forecast systems — they are filtered downstream — just flag them.
8. Do not invent systems. Do not include the "northern limit of monsoon" line or monsoon withdrawal line as a system.
9. SAME-SYSTEM TRACKING (coreference): the same physical system is often described across several sentences as it moves or evolves ("The low pressure area over X lay over Y at 0530 hrs of yesterday. It then persisted ..."). Emit each physical system ONCE, using its MOST RECENT region and status — do NOT create a separate entry for each mention of the same system. A sentence beginning "It"/"The said system" refers to the immediately preceding system, not a new one.
10. LESS MARKED: when a system has become less marked / dissipated, put that in status (e.g. "became less marked"). These entries are excluded downstream — but still report the system with that status so the filter can drop it.
11. HEIGHT / LEVEL: report height_km_min and height_km_max as the km values above mean sea level when the bulletin gives a range (e.g. between 1.5 and 3.1 km -> height_km_min = 1.5, height_km_max = 3.1). If a single height is given (e.g. at 1.5 km), set height_km_min = 1.5, height_km_max = 0.0. Use height_km_min = 0.0, height_km_max = 0.0 when the system is explicitly "at surface" / "at mean sea level" / "at sea level" — that IS a stated level (surface), and you MUST keep that wording in the region. If a system has NO height and NO level mention at all, still report height_km_min = 0.0, height_km_max = 0.0, but it will be dropped downstream — do not invent a height.
12. BE EXHAUSTIVE: a bulletin usually describes SEVERAL distinct systems over DIFFERENT regions. Extract EACH "cyclonic circulation over <region>", EACH trough, and EACH disturbance / low pressure area / depression as its own entry — work through the text sentence by sentence and skip none. Two cyclonic circulations over two different regions are TWO systems, not one. Only merge a sentence into a prior system when it literally continues it (It / the said system / over the same region).
13. WESTERN DISTURBANCE FORM: The phrase "the western disturbance as a cyclonic circulation over X" (or "as a trough in westerlies ...") identifies a WESTERN DISTURBANCE — not a Cyclonic Circulation or Trough. The "as a" describes how the WD currently manifests. weather_system MUST be Western Disturbances (WD) whenever the sentence says "the western disturbance as a ...". Never classify it as Cyclonic Circulation or Trough.
14. "LAY OVER" = MOVED: "The cyclonic circulation over X lay over Y" means the system MOVED and is NOW at Y. Use Y as the region, not the original X. For troughs described twice ("ran from A to B ... ran from C to D"), use the SECOND (current) description C to D.
15. SYSTEM EVOLUTION: "The low pressure area over X lay as a well marked low pressure area over Y" is ONE physical system that intensified. Extract it ONCE as the CURRENT type (Well Marked Low Pressure Area (WML) with associated CYCIR) at the CURRENT location Y. Do not create a separate LPA entry for the earlier stage.
16. FORECAST TRAJECTORY vs. NEW SYSTEM: "It is likely to intensify / concentrate into a [type]" about an EXISTING observed system is NOT a new entry — it describes that system's future state, not a new system forming. Only set is_forecast=true when an ENTIRELY NEW system is predicted to form at a new location ("a low pressure area is likely to form over X during the next 24 hours").
17. EMBEDDED SYSTEMS: Do not miss systems mentioned in subordinate clauses, nested descriptions, or parenthetical phrases (e.g. "...with the trough aloft in middle & upper tropospheric westerlies..." or "...with the trough aloft in middle & upper tropospheric levels..."). Extract them as distinct separate systems (e.g. Westerly Trough).

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
    "systems": [
        {"weather_system": "Upper-Level Cyclonic Circulation", "region": "south Gujarat",
         "subdivisions": ["Gujarat Region"], "height_km_min": 1.5, "height_km_max": 0.0, "pressure_level": "",
         "status": "persisted", "is_forecast": False},
        {"weather_system": "Upper-Level Cyclonic Circulation", "region": "east Bihar",
         "subdivisions": ["Bihar"], "height_km_min": 0.9, "height_km_max": 0.0, "pressure_level": "",
         "status": "persisted", "is_forecast": False},
        {"weather_system": "Mean Sea Level Trough",
         "region": "at mean sea level from south Gujarat to east Bihar across Madhya Pradesh",
         "subdivisions": ["Gujarat Region", "Bihar", "West Madhya Pradesh"],
         "height_km_min": 0.0, "height_km_max": 0.0, "pressure_level": "", "status": "", "is_forecast": False},
    ]
}

_FEWSHOT_USER_2 = (
    "Bulletin date: 2022-01-24\n\nSummary text:\n"
    "The western disturbance as a cyclonic circulation over Punjab and neighbourhood "
    "between 1.5 and 3.1 km above m.s.l. persisted. However, the trough aloft in mid "
    "and upper tropospheric westerlies with its axis at 5.8 km above m. s. l. ran "
    "roughly along Long.75°E to the north of Lat.32°N. A cyclonic circulation "
    "lay over Jharkhand and neighbourhood which extended upto 1.5 km above m. s. l. "
    "A trough ran from the cyclonic circulation over Punjab to the cyclonic circulation "
    "over Jharkhand and neighbourhood at 1.5 km above m. s. l. A cyclonic circulation "
    "lay over north interior Karnataka and neighbourhood and extended upto 1.5 km above "
    "m. s. l. The associated cyclonic circulation over Haryana and neighbourhood became "
    "less marked."
)
_FEWSHOT_SYSTEMS_2 = {
    "systems": [
        {"weather_system": "Western Disturbances (WD)",
         "region": "Punjab and neighbourhood",
         "subdivisions": ["Punjab"],
         "height_km_min": 1.5, "height_km_max": 3.1, "pressure_level": "",
         "status": "persisted", "is_forecast": False},
        {"weather_system": "Westerly Trough",
         "region": "along Long.75°E to the north of Lat.32°N",
         "subdivisions": [],
         "height_km_min": 5.8, "height_km_max": 0.0, "pressure_level": "",
         "status": "", "is_forecast": False},
        {"weather_system": "Cyclonic Circulation (CYCIR)",
         "region": "Jharkhand and neighbourhood",
         "subdivisions": ["Jharkhand"],
         "height_km_min": 1.5, "height_km_max": 0.0, "pressure_level": "",
         "status": "lay over", "is_forecast": False},
        {"weather_system": "Trough",
         "region": "from Punjab to Jharkhand and neighbourhood",
         "subdivisions": ["Punjab", "Jharkhand"],
         "height_km_min": 1.5, "height_km_max": 0.0, "pressure_level": "",
         "status": "", "is_forecast": False},
        {"weather_system": "Cyclonic Circulation (CYCIR)",
         "region": "north interior Karnataka and neighbourhood",
         "subdivisions": ["North Interior Karnataka"],
         "height_km_min": 1.5, "height_km_max": 0.0, "pressure_level": "",
         "status": "lay over", "is_forecast": False},
        {"weather_system": "Cyclonic Circulation (CYCIR)",
         "region": "Haryana and neighbourhood",
         "subdivisions": ["Haryana, Chandigarh & Delhi"],
         "height_km_min": 0.0, "height_km_max": 0.0, "pressure_level": "",
         "status": "became less marked", "is_forecast": False},
    ]
}

_FEWSHOT_USER_3 = (
    "Bulletin date: 2022-10-11\n\nSummary text:\n"
    "The cyclonic circulation over south Haryana and neighbourhood lay over Punjab and "
    "adjoining Haryana which extended upto 3.1 km above m. s. l. The cyclonic circulation "
    "over north Tamil Nadu and neighbourhood lay over Kerala and neighbourhood which "
    "extended upto 1.5 km above m. s. l. A cyclonic circulation lay over north Andaman "
    "sea and neighbourhood which extended upto 3.1 km above m. s. l. The trough from "
    "cyclonic circulation over north Tamil Nadu and neighbourhood to northeast Rajasthan "
    "ran from the cyclonic circulation over Kerala and neighbourhood to southwest Madhya "
    "Pradesh across interior Karnataka, Marathwada and Vidarbha which extended upto "
    "1.5 km above m. s. l."
)
_FEWSHOT_SYSTEMS_3 = {
    "systems": [
        {"weather_system": "Cyclonic Circulation (CYCIR)",
         "region": "Punjab and adjoining Haryana",
         "subdivisions": ["Punjab", "Haryana, Chandigarh & Delhi"],
         "height_km_min": 3.1, "height_km_max": 0.0, "pressure_level": "",
         "status": "lay over", "is_forecast": False},
        {"weather_system": "Cyclonic Circulation (CYCIR)",
         "region": "Kerala and neighbourhood",
         "subdivisions": ["Kerala"],
         "height_km_min": 1.5, "height_km_max": 0.0, "pressure_level": "",
         "status": "lay over", "is_forecast": False},
        {"weather_system": "Cyclonic Circulation (CYCIR)",
         "region": "north Andaman sea and neighbourhood",
         "subdivisions": ["N Andaman Sea"],
         "height_km_min": 3.1, "height_km_max": 0.0, "pressure_level": "",
         "status": "lay over", "is_forecast": False},
        {"weather_system": "Trough",
         "region": "from Kerala and neighbourhood to southwest Madhya Pradesh across "
                   "interior Karnataka, Marathwada and Vidarbha",
         "subdivisions": ["Kerala", "South Interior Karnataka", "North Interior Karnataka",
                            "Marathwada", "Vidarbha", "West Madhya Pradesh"],
         "height_km_min": 1.5, "height_km_max": 0.0, "pressure_level": "",
         "status": "", "is_forecast": False},
    ]
}

_FEWSHOT_USER_4 = (
    "Bulletin date: 2022-11-19\n\nSummary text:\n"
    "The low pressure area over southeast Bay of Bengal and neighbourhood lay as a well "
    "marked low pressure area over central parts of south Bay of Bengal today morning. "
    "It then persisted over the same region with the associated cyclonic circulation "
    "extended upto 7.6 km above m. s. l. It is likely to move west-northwestward and "
    "gradually concentrate into a Depression over southwest and adjoining westcentral "
    "Bay of Bengal during next 24 hours. The western disturbance as a trough in lower "
    "and mid tropospheric westerlies with its axis at 5.8 km above m. s. l. ran roughly "
    "along Long. 66°E to the north of Lat. 32°N."
)
_FEWSHOT_SYSTEMS_4 = {
    "systems": [
        {"weather_system": "Well Marked Low Pressure Area (WML) with associated CYCIR",
         "region": "central parts of south Bay of Bengal",
         "subdivisions": ["SW Bay", "SE Bay"],
         "height_km_min": 7.6, "height_km_max": 0.0, "pressure_level": "",
         "status": "persisted", "is_forecast": False},
        {"weather_system": "Western Disturbances (WD)",
         "region": "along Long. 66°E to the north of Lat. 32°N",
         "subdivisions": [],
         "height_km_min": 5.8, "height_km_max": 0.0, "pressure_level": "",
         "status": "", "is_forecast": False},
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
