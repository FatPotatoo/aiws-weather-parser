"""Batch-extract AIWS .docx bulletins with Claude and write the enriched CSV.

The output CSV columns match the existing extraction CSV, so it pipes straight
into the database loader:

    python -m llm_extractor.runner --folder AIWS2025 --out output_llm.csv
    python database/load_csv_to_entries.py output_llm.csv ^
        | "C:/xampp/mysql/bin/mysql.exe" -u root weather_data_system

Requires the ANTHROPIC_API_KEY environment variable.
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

from .extractor import extract_bulletin  # noqa: E402
from .prompt import system_blocks  # noqa: E402

FIELDNAMES = [
    "date",
    "source_file",
    "weather_system",
    "subdivisions",
    "region",
    "region_original",
    "height_km",
    "pressure_level",
    "status",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM extraction of AIWS .docx bulletins")
    parser.add_argument("--folder", "-d", default=str(REPO_ROOT / "AIWS2025"),
                        help="Folder of .docx bulletins")
    parser.add_argument("--glob", default="*.docx", help="Glob pattern for bulletins")
    parser.add_argument("--out", "-o", required=True, help="Output CSV path")
    parser.add_argument("--limit", type=int, default=0,
                        help="Process at most N files (0 = all). Useful for a test run.")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit(
            "ANTHROPIC_API_KEY is not set. Set it first, e.g. in PowerShell:\n"
            '  $env:ANTHROPIC_API_KEY = "sk-ant-..."'
        )

    try:
        import anthropic
    except ImportError:
        raise SystemExit("The 'anthropic' package is missing. Run: pip install -r llm_extractor/requirements.txt")

    folder = Path(args.folder)
    files = extract.list_word_files(folder, args.glob)
    if args.limit:
        files = files[: args.limit]
    if not files:
        raise SystemExit(f"No bulletins matched {args.glob!r} in {folder}")

    client = anthropic.Anthropic()
    blocks = system_blocks()

    all_rows: list[dict] = []
    total_in = total_out = total_cache_read = 0

    print(f"Extracting {len(files)} bulletin(s) with Claude...\n")
    for path in files:
        try:
            rows, usage = extract_bulletin(client, path, blocks)
        except Exception as exc:  # keep going on a single-file failure
            print(f"  ! {path.name}: {type(exc).__name__}: {exc}")
            continue
        all_rows.extend(rows)
        if usage is not None:
            total_in += usage.input_tokens
            total_out += usage.output_tokens
            total_cache_read += getattr(usage, "cache_read_input_tokens", 0) or 0
        print(f"  + {path.name}: {len(rows)} system(s)")

    out_path = Path(args.out)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for row in all_rows:
            writer.writerow({key: row.get(key, "") for key in FIELDNAMES})

    print(
        f"\nWrote {len(all_rows)} rows to {out_path}\n"
        f"Tokens — input: {total_in:,}  output: {total_out:,}  "
        f"cache-read: {total_cache_read:,}"
    )


if __name__ == "__main__":
    main()
