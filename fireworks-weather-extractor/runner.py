from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import time
from pathlib import Path

import requests

from extractor import extract_bulletin_fireworks, DEFAULT_MODEL
from prompt import build_system_prompt, few_shot_messages

FIELDNAMES = [
    "weather system",
    "date",
    "heightAboveMSL",
    "Regions",
]


def list_word_files(folder: Path, pattern: str = "*.docx") -> list[Path]:
    """Return all matching .docx files recursively from the specified folder."""
    return sorted(
        path
        for path in folder.rglob(pattern)
        if not path.name.startswith("~$") and "_copy" not in path.stem
    )


def _already_done(out_path: Path) -> set[str]:
    checkpoint_path = out_path.parent / f".{out_path.name}.resume"
    if not checkpoint_path.exists():
        return set()
    return set(checkpoint_path.read_text(encoding="utf-8").splitlines())


def _mark_done(out_path: Path, filename: str) -> None:
    checkpoint_path = out_path.parent / f".{out_path.name}.resume"
    with checkpoint_path.open("a", encoding="utf-8") as fh:
        fh.write(filename + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fireworks GLM 5.2 extraction of AIWS bulletins")
    parser.add_argument("--folder", "-d", default=None,
                        help="Folder of .docx bulletins (defaults to check locally or standard location)")
    parser.add_argument("--glob", default="*.docx")
    parser.add_argument("--out", "-o", required=True, help="Output CSV path")
    parser.add_argument("--model", default="accounts/fireworks/models/glm-5p2")
    parser.add_argument(
        "--api-key",
        default=None,
        help="Fireworks API key; falls back to FIREWORKS_API_KEY environment variable",
    )
    parser.add_argument("--limit", type=int, default=0, help="Process at most N pending files (0 = all)")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds to wait between requests")
    parser.add_argument("--mode", choices=["standard", "depression"], default="depression",
                        help="Extraction mode: standard (extract all systems) or depression (extract depression/cyclonic storms only)")
    args = parser.parse_args()

    # Import modules dynamically based on mode
    if args.mode == "standard":
        from extractor_standard import extract_bulletin_fireworks
        from prompt_standard import build_system_prompt, few_shot_messages
    else:
        from extractor import extract_bulletin_fireworks
        from prompt import build_system_prompt, few_shot_messages

    api_key = args.api_key or os.environ.get("FIREWORKS_API_KEY", "")
    if not api_key:
        raise SystemExit(
            "Fireworks API key is not set. Provide --api-key or set FIREWORKS_API_KEY.\n"
            "In PowerShell:\n"
            '  $env:FIREWORKS_API_KEY = "your_key"'
        )

    # Resolve folder path
    folder_path = None
    if args.folder:
        folder_path = Path(args.folder)
    else:
        # Check standard locations
        local_dir = Path("AIWS2025")
        sibling_dir = Path("../aiws-weather-parser/AIWS2025")
        if local_dir.exists() and local_dir.is_dir():
            folder_path = local_dir
        elif sibling_dir.exists() and sibling_dir.is_dir():
            folder_path = sibling_dir
        else:
            raise SystemExit("AIWS2025 directory not found. Please provide --folder argument.")

    files = list_word_files(folder_path, args.glob)
    if not files:
        raise SystemExit(f"No bulletins matched {args.glob!r} in {folder_path}")

    out_path = Path(args.out)
    done = _already_done(out_path)
    pending = [p for p in files if p.name not in done]
    if args.limit:
        pending = pending[: args.limit]

    if done:
        print(f"Resuming: {len(done)} bulletin(s) already done, {len(pending)} remaining.\n", flush=True)
    if not pending:
        print("Nothing to do — all bulletins already extracted.", flush=True)
        return

    system_prompt = build_system_prompt()
    few_shot = few_shot_messages()


    new_file = not out_path.exists() or out_path.stat().st_size == 0
    fh = out_path.open("a", newline="", encoding="utf-8")
    writer = csv.DictWriter(fh, fieldnames=FIELDNAMES, extrasaction="ignore")
    if new_file:
        writer.writeheader()
        fh.flush()

    total_rows = 0
    run_start = time.monotonic()
    print(f"Extracting {len(pending)} bulletin(s) with Fireworks GLM 5.2 model '{args.model}'...\n", flush=True)
    
    try:
        for i, path in enumerate(pending, 1):
            t0 = time.monotonic()
            retry_count = 0
            success = False
            while True:
                try:
                    rows = extract_bulletin_fireworks(api_key, path, system_prompt, few_shot, model=args.model)
                    success = True
                    break
                except (requests.HTTPError, requests.exceptions.Timeout) as exc:
                    is_timeout = isinstance(exc, requests.exceptions.Timeout)
                    status_code = exc.response.status_code if (not is_timeout and exc.response is not None) else None
                    if (is_timeout or status_code in (429, 503)) and retry_count < 3:
                        retry_count += 1
                        wait = max(args.delay * 2, 10.0)
                        err_desc = "Timeout" if is_timeout else f"{status_code} error"
                        print(f"  ~ [{i}/{len(pending)}] {path.name}: {err_desc}, retry {retry_count}/3 after {wait}s...", flush=True)
                        time.sleep(wait)
                        continue
                    print(f"  ! [{i}/{len(pending)}] {path.name}: {type(exc).__name__}: {exc}", flush=True)
                    break
                except Exception as exc:
                    print(f"  ! [{i}/{len(pending)}] {path.name}: {type(exc).__name__}: {exc}", flush=True)
                    break

            if success:
                for row in rows:
                    writer.writerow(row)
                fh.flush()
                _mark_done(out_path, path.name)
                total_rows += len(rows)
                print(f"  + [{i}/{len(pending)}] {path.name}: {len(rows)} system(s) ({time.monotonic()-t0:.1f}s)", flush=True)
            else:
                print(f"  ! [{i}/{len(pending)}] {path.name}: Extraction failed, will NOT mark as done", flush=True)
            
            if args.delay and i < len(pending):
                time.sleep(args.delay)
    finally:
        fh.close()

    print(f"\nWrote {total_rows} new rows to {out_path} in {(time.monotonic()-run_start)/60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
