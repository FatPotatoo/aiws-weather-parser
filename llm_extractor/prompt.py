"""Builds the fixed system prompt (extraction instructions + official
subdivision list). It's stable across every bulletin, so the caller marks it
with cache_control to get prompt-cache reads after the first request.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import extract  # noqa: E402  (repo-root module: read_docx, subdivision loaders, height chart)


INSTRUCTIONS = """\
You extract structured data from India Meteorological Department (IMD) "All India \
Weather Summary" (AIWS) bulletins. You are given the synoptic-summary prose from \
one daily bulletin. Return every distinct weather system that is CURRENTLY OBSERVED \
in it.

Why this matters: this feeds a meteorological database. The previous rule-based \
extractor missed many systems — especially monsoon-season Low Pressure Areas and \
Depressions, and any system not written at the start of its sentence. Your job is \
high recall with correct attribution.

What counts as a system to extract:
- Western Disturbance
- Cyclonic Circulation (any qualifier: upper air, low level, mid level, induced, associated)
- Trough (any qualifier: east-west, north-south, off-shore, at sea level, aloft)
- Low Pressure Area
- Well Marked Low Pressure Area
- Depression, Deep Depression
- Cyclonic Storm and its intensities (Severe / Very Severe / Extremely Severe / Super)

Extraction rules:
1. Extract EVERY distinct system, even when it is introduced mid-sentence — after \
"Under the influence of ...", "The associated ...", "However, ...", "Yet another ...", \
or as a second clause ("..., a low pressure area formed over ..."). A single sentence \
can yield two or more systems; do not collapse them.
2. Resolve coreference: "it", "the same region", "the system" refer to the most \
recently described system/region. Fill the resolved region.
3. region = the wording as written in the bulletin (state names, "& adjoining ...", \
"& neighbourhood", or a coordinate phrase like "along Long. 89E north of Lat. 22N"). \
Strip trailing timestamps ("at 0530 hrs IST of today").
4. subdivisions = map the region to one or more names from the ALLOWED LIST below. \
Use only exact names from that list. One region may map to several (e.g. "Maharashtra" \
-> Madhya Maharashtra; Marathwada; Konkan & Goa). If you cannot map it, return an \
empty list.
5. height_km = top height in km above mean sea level if stated (upper value of a \
range); else 0. pressure_level = an explicit hPa level if the bulletin gives one; \
otherwise leave it empty (height is converted to pressure downstream).
6. status = the verb/state if present (persisted, continued, weakened, became less \
marked, merged, lay over, extended, ...); else empty.
7. is_forecast = true ONLY for outlook/forecast mentions ("likely to form", "is \
likely to affect", "expected to develop around ..."). Currently-observed systems are \
false. Still return forecast systems — they are filtered downstream — just flag them.
8. Do not invent systems. Do not include the "northern limit of monsoon" line or \
monsoon withdrawal line as a system.
9. SAME-SYSTEM TRACKING (coreference): the same physical system is often described \
across several sentences as it moves or evolves ("The low pressure area over X lay \
over Y at 0530 hrs of yesterday. It then persisted ..."). Emit each physical system \
ONCE, using its MOST RECENT region and status — do NOT create a separate entry for \
each mention of the same system. A sentence beginning "It"/"The said system" refers \
to the immediately preceding system, not a new one.
10. LESS MARKED: when a system has become less marked / dissipated, put that in \
status (e.g. "became less marked"). These entries are excluded downstream — but still \
report the system with that status so the filter can drop it.
11. HEIGHT / LEVEL: report height_km as the km value above mean sea level when the \
bulletin gives one (upper value of a range). Use height_km = 0 when the system is \
explicitly "at surface" / "at mean sea level" / "at sea level" — that IS a stated \
level (surface), and you MUST keep that wording in the region. If a system has NO \
height and NO level mention at all, still report height_km = 0, but it will be \
dropped downstream — do not invent a height.
12. BE EXHAUSTIVE: a bulletin usually describes SEVERAL distinct systems over \
DIFFERENT regions. Extract EACH "cyclonic circulation over <region>", EACH trough, \
and EACH disturbance / low pressure area / depression as its own entry — work through \
the text sentence by sentence and skip none. Two cyclonic circulations over two \
different regions are TWO systems, not one. Only merge a sentence into a prior system \
when it literally continues it (It / the said system / over the same region).
13. WESTERN DISTURBANCE FORM: The phrase "the western disturbance as a cyclonic \
circulation over X" (or "as a trough in westerlies ...") identifies a WESTERN \
DISTURBANCE — not a Cyclonic Circulation or Trough. The "as a" describes how the WD \
currently manifests. weather_system MUST be Western Disturbance whenever the sentence \
says "the western disturbance as a ...". Never classify it as Cyclonic Circulation or \
Trough.
14. "LAY OVER" = MOVED: "The cyclonic circulation over X lay over Y" means the system \
MOVED and is NOW at Y. Use Y as the region, not the original X. For troughs described \
twice ("ran from A to B ... ran from C to D"), use the SECOND (current) description C to D.
15. SYSTEM EVOLUTION: "The low pressure area over X lay as a well marked low pressure \
area over Y" is ONE physical system that intensified. Extract it ONCE as the CURRENT \
type (Well Marked Low Pressure Area) at the CURRENT location Y. Do not create a \
separate LPA entry for the earlier stage.
16. FORECAST TRAJECTORY vs. NEW SYSTEM: "It is likely to intensify / concentrate into \
a [type]" about an EXISTING observed system is NOT a new entry — it describes that \
system's future state, not a new system forming. Only set is_forecast=true when an \
ENTIRELY NEW system is predicted to form at a new location ("a low pressure area is \
likely to form over X during the next 24 hours").

Return your answer using the structured output schema (a list of systems). If the \
text contains no weather systems, return an empty list.

ALLOWED SUBDIVISION LIST (use these exact strings for `subdivisions`):
"""


def build_system_prompt() -> str:
    """Compose instructions + the official subdivision list from weather_form.js."""
    subdivisions = extract.load_form_subdivisions()
    listing = "\n".join(f"- {name}" for name in subdivisions)
    return INSTRUCTIONS + listing


def system_blocks() -> list[dict]:
    """System prompt as a cached content block (prefix reused across bulletins)."""
    return [
        {
            "type": "text",
            "text": build_system_prompt(),
            "cache_control": {"type": "ephemeral"},
        }
    ]


# ---------------------------------------------------------------------------
# Few-shot examples
# ---------------------------------------------------------------------------

# Example 1 — two CCs at height with coreference + surface trough
# Teaches: multiple distinct systems, "the same region" coreference, surface level.
_FEWSHOT_USER_1 = (
    "Bulletin date: 2020-01-01\n\nSummary text:\n"
    "The upper air cyclonic circulation over south Gujarat persisted at 1.5 km above "
    "m. s. l. The upper air cyclonic circulation lay over east Bihar at 0.9 km above "
    "m. s. l. It then persisted over the same region. A trough at mean sea level ran "
    "from south Gujarat to east Bihar across Madhya Pradesh."
)
_FEWSHOT_SYSTEMS_1 = {
    "systems": [
        {"weather_system": "Cyclonic Circulation", "region": "south Gujarat",
         "subdivisions": ["Gujarat Region"], "height_km": 1.5, "pressure_level": "",
         "status": "persisted", "is_forecast": False},
        {"weather_system": "Cyclonic Circulation", "region": "east Bihar",
         "subdivisions": ["Bihar"], "height_km": 0.9, "pressure_level": "",
         "status": "persisted", "is_forecast": False},
        {"weather_system": "Trough",
         "region": "at mean sea level from south Gujarat to east Bihar across Madhya Pradesh",
         "subdivisions": ["Gujarat Region", "Bihar", "West Madhya Pradesh"],
         "height_km": 0.0, "pressure_level": "", "status": "", "is_forecast": False},
    ]
}

# Example 2 — WD as cyclonic circulation, height range, trough between CCs, became less marked
# Teaches:
#  - "western disturbance AS a cyclonic circulation" → weather_system = Western Disturbance
#  - height range "between 1.5 and 3.1 km" → height_km = 3.1 (upper value)
#  - trough at coordinate region
#  - "became less marked" system still extracted with that status
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
        # WD manifests "as a cyclonic circulation" — type is Western Disturbance,
        # height range 1.5–3.1 km → take upper value 3.1
        {"weather_system": "Western Disturbance",
         "region": "Punjab and neighbourhood",
         "subdivisions": ["Punjab"],
         "height_km": 3.1, "pressure_level": "",
         "status": "persisted", "is_forecast": False},
        # The upper-tropospheric trough axis of the same WD — separate entry
        {"weather_system": "Trough",
         "region": "along Long.75°E to the north of Lat.32°N",
         "subdivisions": [],
         "height_km": 5.8, "pressure_level": "",
         "status": "", "is_forecast": False},
        {"weather_system": "Cyclonic Circulation",
         "region": "Jharkhand and neighbourhood",
         "subdivisions": ["Jharkhand"],
         "height_km": 1.5, "pressure_level": "",
         "status": "lay over", "is_forecast": False},
        {"weather_system": "Trough",
         "region": "from Punjab to Jharkhand and neighbourhood",
         "subdivisions": ["Punjab", "Jharkhand"],
         "height_km": 1.5, "pressure_level": "",
         "status": "", "is_forecast": False},
        {"weather_system": "Cyclonic Circulation",
         "region": "north interior Karnataka and neighbourhood",
         "subdivisions": ["North Interior Karnataka"],
         "height_km": 1.5, "pressure_level": "",
         "status": "lay over", "is_forecast": False},
        # "became less marked" — still extracted so the downstream filter can drop it
        {"weather_system": "Cyclonic Circulation",
         "region": "Haryana and neighbourhood",
         "subdivisions": ["Haryana, Chandigarh & Delhi"],
         "height_km": 0.0, "pressure_level": "",
         "status": "became less marked", "is_forecast": False},
    ]
}

# Example 3 — "lay over" = system moved, extract FINAL location; trough with coreference
# Teaches:
#  - "The CC over X lay over Y" → region = Y (current), not X (previous)
#  - Trough described twice (old position → new position); use the new position
#  - Multiple CCs each with their own final location
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
        # "lay over Punjab and adjoining Haryana" — current location is Punjab/Haryana
        {"weather_system": "Cyclonic Circulation",
         "region": "Punjab and adjoining Haryana",
         "subdivisions": ["Punjab", "Haryana, Chandigarh & Delhi"],
         "height_km": 3.1, "pressure_level": "",
         "status": "lay over", "is_forecast": False},
        # "lay over Kerala" — current location is Kerala
        {"weather_system": "Cyclonic Circulation",
         "region": "Kerala and neighbourhood",
         "subdivisions": ["Kerala"],
         "height_km": 1.5, "pressure_level": "",
         "status": "lay over", "is_forecast": False},
        {"weather_system": "Cyclonic Circulation",
         "region": "north Andaman sea and neighbourhood",
         "subdivisions": ["N Andaman Sea"],
         "height_km": 3.1, "pressure_level": "",
         "status": "lay over", "is_forecast": False},
        # Trough given in two descriptions — use the second (current) one:
        # "ran from ... over Kerala ... to southwest Madhya Pradesh across ..."
        {"weather_system": "Trough",
         "region": "from Kerala and neighbourhood to southwest Madhya Pradesh across "
                   "interior Karnataka, Marathwada and Vidarbha",
         "subdivisions": ["Kerala", "South Interior Karnataka", "North Interior Karnataka",
                          "Marathwada", "Vidarbha", "West Madhya Pradesh"],
         "height_km": 1.5, "pressure_level": "",
         "status": "", "is_forecast": False},
    ]
}

# Example 4 — LPA intensifies to WMLPA (one system, current type), WD as trough at coordinate
# Teaches:
#  - "LPA lay as a WMLPA over Y" → ONE entry as Well Marked Low Pressure Area at Y
#  - "with the associated CC extended upto 7.6 km" → height_km = 7.6
#  - "It is likely to concentrate into a Depression" → NOT a new entry; it's the
#    existing WMLPA's forecast trajectory, not a new system forming
#  - WD "as a trough in westerlies" → weather_system = Western Disturbance
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
        # LPA intensified to WMLPA — ONE system, current type = Well Marked Low Pressure Area,
        # current location = "central parts of south Bay of Bengal".
        # Associated CC reaches 7.6 km → height_km = 7.6.
        # "likely to concentrate into a Depression" is the WMLPA's forecast trajectory —
        # NOT a new system; do not create a Depression entry.
        {"weather_system": "Well Marked Low Pressure Area",
         "region": "central parts of south Bay of Bengal",
         "subdivisions": ["SW Bay", "SE Bay"],
         "height_km": 7.6, "pressure_level": "",
         "status": "persisted", "is_forecast": False},
        # WD "as a trough" → weather_system = Western Disturbance
        {"weather_system": "Western Disturbance",
         "region": "along Long. 66°E to the north of Lat. 32°N",
         "subdivisions": [],
         "height_km": 5.8, "pressure_level": "",
         "status": "", "is_forecast": False},
    ]
}


def few_shot_messages() -> list[dict]:
    """Four worked examples covering the main IMD extraction patterns.

    Example 1: two CCs + surface trough, coreference.
    Example 2: WD as CC, height range, became-less-marked.
    Example 3: 'lay over' movement, trough with old/new position.
    Example 4: LPA → WMLPA evolution, WD as trough at coordinate.
    """
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
