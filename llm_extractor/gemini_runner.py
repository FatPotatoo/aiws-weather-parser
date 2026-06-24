"""Batch-extract AIWS bulletins with Gemini and write CSV output.

    $env:GOOGLE_API_KEY = "AIza..."
    python -m llm_extractor.gemini_runner --folder AIWS2025 --out output_gemini.csv
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import extract  # noqa: E402

from .gemini_extractor import extract_bulletin_gemini, DEFAULT_MODEL  # noqa: E402
from .prompt import build_system_prompt  # noqa: E402
from .runner import FIELDNAMES  # noqa: E402  (reuse same CSV column list)


def main() -> None:
    parser = argparse.ArgumentParser(description="Gemini extraction of AIWS bulletins")
    parser.add_argument("--folder", "-d", default=str(REPO_ROOT / "AIWS2025"))
    parser.add_argument("--glob", default="*.docx")
    parser.add_argument("--out", "-o", required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    api_key = os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        raise SystemExit(
            "GOOGLE_API_KEY is not set. In PowerShell:\n"
            '  $env:GOOGLE_API_KEY = "AIza..."'
        )

    folder = Path(args.folder)
    files = extract.list_word_files(folder, args.glob)
    if args.limit:
        files = files[: args.limit]
    if not files:
        raise SystemExit(f"No bulletins matched {args.glob!r} in {folder}")

    system_prompt = build_system_prompt()
    all_rows: list[dict] = []

    print(f"Extracting {len(files)} bulletin(s) with Gemini ({args.model})...\n")
    for path in files:
        try:
            rows = extract_bulletin_gemini(api_key, path, system_prompt, model=args.model)
        except Exception as exc:
            print(f"  ! {path.name}: {type(exc).__name__}: {exc}")
            continue
        all_rows.extend(rows)
        print(f"  + {path.name}: {len(rows)} system(s)")

    out_path = Path(args.out)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for row in all_rows:
            writer.writerow({key: row.get(key, "") for key in FIELDNAMES})

    print(f"\nWrote {len(all_rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
