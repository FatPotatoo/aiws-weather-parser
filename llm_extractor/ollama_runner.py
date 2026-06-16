"""Batch-extract AIWS .docx bulletins with a LOCAL Ollama model -> CSV.

Same output columns as the regex extractor and the Claude path, so it can be
compared directly. No API key needed — just a running Ollama server with the
model pulled.

    ollama pull qwen2.5:7b-instruct
    python -u -m llm_extractor.ollama_runner --folder AIWS2025 --out output_ollama.csv

Resilience (added after a sleep-induced hang lost a whole run):
  - Each bulletin's rows are written and flushed immediately (no end-of-run-only write).
  - Re-running with the same --out RESUMES: bulletins already in the CSV are skipped.
  - A per-request timeout means a stalled model call is skipped, not hung forever.

Applies the cross-check rules: excludes 'less marked' systems, excludes systems
with no stated height above MSL, and asks the model to merge same-system
references (coreference) into one entry.
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import extract  # noqa: E402

from .ollama_extractor import extract_bulletin_ollama, DEFAULT_MODEL  # noqa: E402
from .prompt import build_system_prompt  # noqa: E402

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

# Per-request ceiling (seconds). A bulletin taking longer than this is treated as
# stalled and skipped, instead of blocking the whole run forever.
REQUEST_TIMEOUT = 600


def _already_done(out_path: Path) -> set[str]:
    """Source filenames already present in the output CSV (for resume)."""
    if not out_path.exists() or out_path.stat().st_size == 0:
        return set()
    with out_path.open(newline="", encoding="utf-8") as fh:
        return {row["source_file"] for row in csv.DictReader(fh) if row.get("source_file")}


def main() -> None:
    parser = argparse.ArgumentParser(description="Local Ollama extraction of AIWS .docx bulletins")
    parser.add_argument("--folder", "-d", default=str(REPO_ROOT / "AIWS2025"))
    parser.add_argument("--glob", default="*.docx")
    parser.add_argument("--out", "-o", required=True, help="Output CSV path (resumes if it exists)")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--limit", type=int, default=0, help="Process at most N pending files (0 = all)")
    args = parser.parse_args()

    try:
        import ollama
    except ImportError:
        raise SystemExit("The 'ollama' package is missing. Run: pip install ollama")

    client = ollama.Client(timeout=REQUEST_TIMEOUT)
    try:
        tags = client.list()
        available = {m.get("model") or m.get("name") for m in tags.get("models", [])}
    except Exception as exc:
        raise SystemExit(f"Cannot reach Ollama at localhost:11434 ({exc}). Is the server running?")
    if args.model not in available and f"{args.model}:latest" not in available:
        print(f"Warning: '{args.model}' not in installed models {sorted(available)}. "
              f"Pull it with: ollama pull {args.model}", flush=True)

    folder = Path(args.folder)
    all_files = extract.list_word_files(folder, args.glob)
    if not all_files:
        raise SystemExit(f"No bulletins matched {args.glob!r} in {folder}")

    out_path = Path(args.out)
    done = _already_done(out_path)
    pending = [p for p in all_files if p.name not in done]
    if args.limit:
        pending = pending[: args.limit]

    if done:
        print(f"Resuming: {len(done)} bulletin(s) already in {out_path.name}, "
              f"{len(pending)} to go.\n", flush=True)
    if not pending:
        print("Nothing to do — all bulletins already extracted.", flush=True)
        return

    system_prompt = build_system_prompt()

    # Append mode; write the header only when starting a fresh file.
    new_file = not out_path.exists() or out_path.stat().st_size == 0
    fh = out_path.open("a", newline="", encoding="utf-8")
    writer = csv.DictWriter(fh, fieldnames=FIELDNAMES, extrasaction="ignore")
    if new_file:
        writer.writeheader()
        fh.flush()

    total_rows = 0
    run_start = time.monotonic()
    print(f"Extracting {len(pending)} bulletin(s) with Ollama model '{args.model}'...\n", flush=True)
    try:
        for i, path in enumerate(pending, 1):
            t0 = time.monotonic()
            try:
                rows = extract_bulletin_ollama(client, path, system_prompt, args.model)
            except Exception as exc:
                print(f"  ! [{i}/{len(pending)}] {path.name}: {type(exc).__name__}: {exc}", flush=True)
                continue
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in FIELDNAMES})
            fh.flush()  # persist immediately — survives interruptions
            total_rows += len(rows)
            print(f"  + [{i}/{len(pending)}] {path.name}: {len(rows)} system(s)  "
                  f"({time.monotonic()-t0:.0f}s)", flush=True)
    finally:
        fh.close()

    print(f"\nWrote {total_rows} new rows to {out_path} in "
          f"{(time.monotonic()-run_start)/60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
