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
8. Do not invent systems. Do not include the "northern limit of monsoon" line as a \
system.
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


# A worked example shown to the model (few-shot) to enforce exhaustive,
# one-per-region extraction and demonstrate the surface (height 0) case. Small
# local models miss systems badly without it.
_FEWSHOT_USER = (
    "Bulletin date: 2020-01-01\n\nSummary text:\n"
    "The upper air cyclonic circulation over south Gujarat persisted at 1.5 km above "
    "m. s. l. The upper air cyclonic circulation lay over east Bihar at 0.9 km above "
    "m. s. l. It then persisted over the same region. A trough at mean sea level ran "
    "from south Gujarat to east Bihar across Madhya Pradesh."
)
_FEWSHOT_SYSTEMS = {
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


def few_shot_messages() -> list[dict]:
    """User/assistant example pair demonstrating exhaustive extraction."""
    return [
        {"role": "user", "content": _FEWSHOT_USER},
        {"role": "assistant", "content": json.dumps(_FEWSHOT_SYSTEMS)},
    ]
