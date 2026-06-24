"""Batch-extract AIWS bulletins with Gemini and write CSV output.

    $env:GEMINI_API_KEY = "AIza..."
    python -m llm_extractor.gemini_runner --folder AIWS2025 --out output_gemini.csv
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import extract  # noqa: E402

from .gemini_extractor import extract_bulletin_gemini, extract_bulletins_gemini, DEFAULT_MODEL  # noqa: E402
from .prompt import build_system_prompt  # noqa: E402
from .runner import FIELDNAMES  # noqa: E402  (reuse same CSV column list)


def main() -> None:
    parser = argparse.ArgumentParser(description="Gemini extraction of AIWS bulletins")
    parser.add_argument("--folder", "-d", default=str(REPO_ROOT / "AIWS2025"))
    parser.add_argument("--glob", default="*.docx")
    parser.add_argument("--out", "-o", required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--api-key",
        default=None,
        help="Gemini API key; falls back to GEMINI_API_KEY or GOOGLE_API_KEY environment variables",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=10,
                        help="Number of bulletins to send in each Gemini call; 0 means all bulletins at once")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="Seconds to wait between requests")
    args = parser.parse_args()

    api_key = (
        args.api_key
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY", "")
    )
    if not api_key:
        raise SystemExit(
            "Gemini API key is not set. Provide --api-key or set GEMINI_API_KEY.\n"
            "In PowerShell:\n"
            '  $env:GEMINI_API_KEY = "AIza..."'
        )

    folder = Path(args.folder)
    files = extract.list_word_files(folder, args.glob)
    if args.limit:
        files = files[: args.limit]
    if not files:
        raise SystemExit(f"No bulletins matched {args.glob!r} in {folder}")

    batch_size = len(files) if args.batch_size == 0 else args.batch_size
    if batch_size < 1:
        raise SystemExit("--batch-size must be 0 or a positive integer")

    system_prompt = build_system_prompt()
    all_rows: list[dict] = []

    print(f"Extracting {len(files)} bulletin(s) with Gemini (preferred {args.model}) in batches of {batch_size}...\n")
    for start in range(0, len(files), batch_size):
        batch_paths = files[start : start + batch_size]
        batch_label = f"{start+1}-{start+len(batch_paths)}"
        model = args.model
        retry_count = 0
        while True:
            try:
                rows = extract_bulletins_gemini(api_key, batch_paths, system_prompt, model=model)
            except requests.HTTPError as exc:
                status_code = exc.response.status_code if exc.response is not None else None
                retry_after = _extract_retry_after(exc)

                if status_code == 503 and retry_count < 3:
                    retry_count += 1
                    wait = max(args.delay, retry_after or 0)
                    print(f"  ~ batch {batch_label}: 503 unavailable on {model}, retry {retry_count}/3 after {wait}s...")
                    time.sleep(wait)
                    continue
                if status_code == 503 and model.startswith("gemini-3.5"):
                    print(f"  ~ batch {batch_label}: switching to gemini-2.5-flash after 3 failures")
                    model = "gemini-2.5-flash"
                    retry_count = 0
                    continue

                if status_code == 429 and retry_count < 3:
                    retry_count += 1
                    wait = max(args.delay, retry_after or 10)
                    print(f"  ~ batch {batch_label}: 429 rate limit on {model}, retry {retry_count}/3 after {wait}s...")
                    time.sleep(wait)
                    continue
                if status_code == 429 and model.startswith("gemini-3.5"):
                    print(f"  ~ batch {batch_label}: switching to gemini-2.5-flash after repeated 429 on {model}")
                    model = "gemini-2.5-flash"
                    retry_count = 0
                    continue

                print(f"  ! batch {batch_label}: {type(exc).__name__}: {exc}")
                rows = []
            except Exception as exc:
                print(f"  ! batch {batch_label}: {type(exc).__name__}: {exc}")
                rows = []
            break

        if not rows and len(batch_paths) > 1:
            print(f"  ! batch {batch_label}: empty batch result, falling back to single-file extraction")
            fallback_rows: list[dict] = []
            for path in batch_paths:
                file_model = model
                file_retry = 0
                while True:
                    try:
                        file_rows = extract_bulletin_gemini(api_key, path, system_prompt, model=file_model)
                        break
                    except requests.HTTPError as exc:
                        status_code = exc.response.status_code if exc.response is not None else None
                        retry_after = _extract_retry_after(exc)

                        if status_code == 503 and file_retry < 3:
                            file_retry += 1
                            wait = max(args.delay, retry_after or 0)
                            print(f"    ~ {path.name}: 503 unavailable on {file_model}, retry {file_retry}/3 after {wait}s...")
                            time.sleep(wait)
                            continue
                        if status_code == 503 and file_model.startswith("gemini-3.5"):
                            print(f"    ~ {path.name}: switching to gemini-2.5-flash after 3 failures")
                            file_model = "gemini-2.5-flash"
                            file_retry = 0
                            continue

                        if status_code == 429 and file_retry < 3:
                            file_retry += 1
                            wait = max(args.delay, retry_after or 10)
                            print(f"    ~ {path.name}: 429 rate limit on {file_model}, retry {file_retry}/3 after {wait}s...")
                            time.sleep(wait)
                            continue
                        if status_code == 429 and file_model.startswith("gemini-3.5"):
                            print(f"    ~ {path.name}: switching to gemini-2.5-flash after repeated 429 on {file_model}")
                            file_model = "gemini-2.5-flash"
                            file_retry = 0
                            continue

                        print(f"    ! {path.name}: {type(exc).__name__}: {exc}")
                        file_rows = []
                        break
                    except Exception as exc:
                        print(f"    ! {path.name}: {type(exc).__name__}: {exc}")
                        file_rows = []
                        break
                for row in file_rows:
                    row["gemini_model"] = file_model
                fallback_rows.extend(file_rows)
                if args.delay:
                    time.sleep(args.delay)
            rows = fallback_rows

        if rows:
            if not any("gemini_model" in row for row in rows):
                for row in rows:
                    row["gemini_model"] = model
            models = {row.get("gemini_model", model) for row in rows}
            model_label = ",".join(sorted(models))
        else:
            model_label = model

        all_rows.extend(rows)
        print(f"  + batch {batch_label}: {len(batch_paths)} bulletins, {len(rows)} system(s) using {model_label}")
        if args.delay and start + args.batch_size < len(files):
            time.sleep(args.delay)

    out_path = Path(args.out)
    fieldnames = FIELDNAMES + ["gemini_model"]
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in all_rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})

    print(f"\nWrote {len(all_rows)} rows to {out_path}")


def _extract_retry_after(exc: requests.HTTPError) -> int | None:
    if exc.response is not None:
        header = exc.response.headers.get("Retry-After")
        if header:
            try:
                return int(header)
            except ValueError:
                m = re.search(r"(\d+)", header)
                if m:
                    return int(m.group(1))
    text = str(exc)
    m = re.search(r"retry in ([0-9.]+)s", text, re.I)
    if m:
        return int(float(m.group(1)))
    return None


if __name__ == "__main__":
    main()
