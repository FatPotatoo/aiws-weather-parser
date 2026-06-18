"""Evaluate the Ollama extractor against validationSet.xlsx.

Usage:
    python eval_validation.py

Runs the Ollama extractor on every bulletin in 'Validation Bulletins/' that
has a matching date row in validationSet.xlsx (2022 only), then prints a
per-bulletin breakdown + aggregate precision / recall / F1.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import ollama
import openpyxl

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from llm_extractor.ollama_extractor import extract_bulletin_ollama, DEFAULT_MODEL
from llm_extractor.prompt import build_system_prompt

VALIDATION_XLSX = REPO_ROOT / "validationSet.xlsx"
BULLETIN_FOLDER = REPO_ROOT / "Validation Bulletins"

# ── type normalisation ────────────────────────────────────────────────────────
# The validation Excel uses informal labels. Map everything to our DB labels.

_VAL_TYPE_MAP: dict[str, str] = {}  # built below

def _build_type_map() -> dict[str, str]:
    mapping = {}
    wd_variants = ["wd", "western disturbance"]
    cycir_variants = ["cycir", "cyclonic circulation", "cycir (upper air)",
                      "upper air cyclonic circulation"]
    trough_variants = [
        "trough", "troughs", "at surface trough", "east-west trough",
        "eastwest trough", "north-south trough", "northsouth trough",
        "offshore trough", "westerly trough", "easterly trough",
        "mean sea level trough", "monsoon trough",
    ]
    lpa_variants = ["lpa", "low pressure area", "low pressure"]
    wmlpa_variants = [
        "wmlpa", "well marked low pressure area",
        "well marked low pressure", "well marked lpa",
        "well marked low pressure with cycir",
        "well-marked low pressure area",
    ]
    dd_variants = ["deep depression", "dd"]
    dep_variants = ["depression", "dep", "d"]

    for v in wd_variants:    mapping[v] = "WD"
    for v in cycir_variants: mapping[v] = "CYCIR"
    for v in trough_variants: mapping[v] = "Trough"
    for v in lpa_variants:   mapping[v] = "Low Pressure Area"
    for v in wmlpa_variants: mapping[v] = "Well Marked Low Pressure Area"
    for v in dd_variants:    mapping[v] = "Deep Depression"
    for v in dep_variants:   mapping[v] = "Depression"
    return mapping

_VAL_TYPE_MAP = _build_type_map()


def normalise_val_type(raw: str) -> str:
    """Normalise a validation-set weather_system label to a DB label."""
    key = raw.strip().lower()
    # exact match first
    if key in _VAL_TYPE_MAP:
        return _VAL_TYPE_MAP[key]
    # prefix match for trough variants like "north-south trough (abc)"
    for pattern, label in _VAL_TYPE_MAP.items():
        if key.startswith(pattern):
            return label
    return raw.strip()  # unchanged if unknown


def normalise_ext_type(db_label: str) -> str:
    """Extractor DB labels are already normalised; just ensure consistent casing."""
    return db_label.strip()


# ── height normalisation ──────────────────────────────────────────────────────

def parse_height(raw) -> float:
    """Parse a validation height cell to a float (upper value of any range)."""
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip()
    # "1.5-3.1" or "1.5, 3.1" or "3.1-7.6"
    parts = re.split(r"[-,]", s)
    nums: list[float] = []
    for p in parts:
        try:
            nums.append(float(p.strip()))
        except ValueError:
            pass
    return max(nums) if nums else 0.0


# ── data structures ───────────────────────────────────────────────────────────

@dataclass
class ValEntry:
    date: str          # "YYYY-MM-DD"
    filename: str
    sys_type: str      # normalised
    height: float
    region: str


@dataclass
class ExtEntry:
    date: str
    sys_type: str      # normalised
    height: float
    region: str
    pressure_level: str


# ── load validation set ───────────────────────────────────────────────────────

def load_validation(path: Path, year_filter: int | None = None) -> list[ValEntry]:
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    entries: list[ValEntry] = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        date_cell, file_cell, sys_cell, height_cell, region_cell = row[:5]
        if date_cell is None:
            continue
        date_str = date_cell.strftime("%Y-%m-%d")
        if year_filter and date_cell.year != year_filter:
            continue
        entries.append(ValEntry(
            date=date_str,
            filename=str(file_cell or "").strip(),
            sys_type=normalise_val_type(str(sys_cell or "")),
            height=parse_height(height_cell),
            region=str(region_cell or "").strip(),
        ))
    return entries


# ── matching ──────────────────────────────────────────────────────────────────

HEIGHT_TOL = 0.15  # km — tolerance for height comparison


def _heights_match(h1: float, h2: float) -> bool:
    return abs(h1 - h2) <= HEIGHT_TOL


def match_entries(
    val_entries: list[ValEntry],
    ext_entries: list[ExtEntry],
) -> tuple[list[tuple[ValEntry, ExtEntry]], list[ValEntry], list[ExtEntry]]:
    """Greedy bipartite matching: (matched pairs, false negatives, false positives)."""
    remaining_val = list(val_entries)
    remaining_ext = list(ext_entries)
    matched: list[tuple[ValEntry, ExtEntry]] = []

    # Pass 1: exact date + type + height
    for v in list(remaining_val):
        for e in list(remaining_ext):
            if (v.date == e.date
                    and v.sys_type == e.sys_type
                    and _heights_match(v.height, e.height)):
                matched.append((v, e))
                remaining_val.remove(v)
                remaining_ext.remove(e)
                break

    # Pass 2: same date + type, wrong height (partial credit — shown separately)
    type_only_matched: list[tuple[ValEntry, ExtEntry]] = []
    for v in list(remaining_val):
        for e in list(remaining_ext):
            if v.date == e.date and v.sys_type == e.sys_type:
                type_only_matched.append((v, e))
                remaining_val.remove(v)
                remaining_ext.remove(e)
                break

    return matched, remaining_val, remaining_ext, type_only_matched  # type: ignore[return-value]


# ── report ────────────────────────────────────────────────────────────────────

def fmt(e: ValEntry | ExtEntry) -> str:
    h = f"{e.height:.1f}km" if e.height else "?km"
    region = e.region[:55] + "…" if len(e.region) > 55 else e.region
    return f"{e.sys_type:<30} {h:<8} {region}"


def run_evaluation(year_filter: int = 2022) -> None:
    # Load validation ground truth
    val_entries = load_validation(VALIDATION_XLSX, year_filter=year_filter)
    if not val_entries:
        print(f"No validation entries for year {year_filter}.")
        return

    # Group by date for per-bulletin display
    from collections import defaultdict
    val_by_date: dict[str, list[ValEntry]] = defaultdict(list)
    for v in val_entries:
        val_by_date[v.date].append(v)

    # Determine which bulletins to run (by filename pattern in the validation set)
    bulletin_paths: dict[str, Path] = {}
    for v in val_entries:
        fname = v.filename
        # Try exact, then strip .docx / add .docx
        candidates = [
            BULLETIN_FOLDER / fname,
            BULLETIN_FOLDER / (fname if fname.endswith(".docx") else fname + ".docx"),
        ]
        for c in candidates:
            if c.exists():
                bulletin_paths[v.date] = c
                break

    if not bulletin_paths:
        print(f"No bulletin files found in {BULLETIN_FOLDER}.")
        return

    # Run Ollama extractor
    client = ollama.Client()
    system_prompt = build_system_prompt()

    print(f"Running Ollama ({DEFAULT_MODEL}) on {len(bulletin_paths)} bulletin(s)…\n")

    all_ext: list[ExtEntry] = []
    date_to_ext: dict[str, list[ExtEntry]] = defaultdict(list)

    for date, path in sorted(bulletin_paths.items()):
        print(f"  Extracting {path.name}…", end=" ", flush=True)
        try:
            rows = extract_bulletin_ollama(client, path, system_prompt)
        except Exception as exc:
            print(f"ERROR: {exc}")
            rows = []
        print(f"{len(rows)} system(s)")
        for r in rows:
            e = ExtEntry(
                date=date,
                sys_type=normalise_ext_type(r["weather_system"]),
                height=float(r.get("height_km", 0) or 0),
                region=str(r.get("region", "")),
                pressure_level=str(r.get("pressure_level", "")),
            )
            all_ext.append(e)
            date_to_ext[date].append(e)

    print()

    # ── Per-bulletin comparison ──
    total_tp = total_fp = total_fn = 0
    total_type_partial = 0

    for date in sorted(val_by_date):
        vlist = val_by_date[date]
        elist = date_to_ext.get(date, [])

        matched, fn_list, fp_list, partial = match_entries(vlist, elist)
        tp = len(matched)
        fp = len(fp_list) + len(partial)  # wrong height counts as FP+FN
        fn = len(fn_list) + len(partial)
        total_tp += tp
        total_fp += fp
        total_fn += fn
        total_type_partial += len(partial)

        print(f"── {date} {'─'*50}")
        print(f"  Ground truth : {len(vlist)} entries  |  Extracted : {len(elist)} entries")

        if matched:
            print(f"  ✓ CORRECT ({len(matched)})")
            for v, e in matched:
                print(f"      {fmt(v)}")

        if partial:
            print(f"  ~ WRONG HEIGHT ({len(partial)})")
            for v, e in partial:
                print(f"      EXPECTED  {fmt(v)}")
                print(f"      GOT       {fmt(e)}")

        if fn_list:
            print(f"  ✗ MISSED / FALSE NEGATIVES ({len(fn_list)})")
            for v in fn_list:
                print(f"      {fmt(v)}")

        if fp_list:
            print(f"  + EXTRA / FALSE POSITIVES ({len(fp_list)})")
            for e in fp_list:
                print(f"      {fmt(e)}")

        print()

    # ── Aggregate stats ──
    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 0.0
    recall    = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 0.0
    f1        = (2 * precision * recall / (precision + recall)
                 if (precision + recall) else 0.0)

    print("═" * 65)
    print(f"  AGGREGATE  (year {year_filter}, 2022 bulletins only)")
    print(f"  Validation entries : {total_tp + total_fn}")
    print(f"  True Positives     : {total_tp}")
    print(f"  False Positives    : {total_fp}  (includes {total_type_partial} wrong-height)")
    print(f"  False Negatives    : {total_fn}  (includes {total_type_partial} wrong-height)")
    print(f"  Precision          : {precision:.1%}")
    print(f"  Recall             : {recall:.1%}")
    print(f"  F1                 : {f1:.1%}")
    print("═" * 65)


if __name__ == "__main__":
    run_evaluation(year_filter=2022)
