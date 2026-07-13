import os
import sys
import csv
import time
import re
from pathlib import Path
import requests

# Add current folder to path
sys.path.append(str(Path(__file__).parent))

from extractor_standard import extract_bulletin_fireworks, DEFAULT_MODEL
from prompt_standard import build_system_prompt, few_shot_messages

base_dir = Path(r"C:\Users\suyas\Downloads\AIWS\2021")
extractor_dir = Path(r"c:\xampp\htdocs\aiws-weather-parser\fireworks-weather-extractor")

quarter_files = {
    1: extractor_dir / "output_q1_2021.csv",
    2: extractor_dir / "output_q2_2021.csv",
    3: extractor_dir / "output_q3_2021.csv",
    4: extractor_dir / "output_q4_2021.csv",
}

resume_file = extractor_dir / ".run_2021_quarters.resume"

def get_file_quarter(path: Path) -> int | None:
    # Match 8 digits representing the date, e.g. "AIWS 20210314.docx"
    match = re.search(r"2021(\d{2})\d{2}", path.name)
    if not match:
        return None
    month = int(match.group(1))
    if 1 <= month <= 12:
        return (month - 1) // 3 + 1
    return None

def main():
    api_key = os.environ.get("FIREWORKS_API_KEY")
    if not api_key:
        print("Error: FIREWORKS_API_KEY environment variable is not set.")
        return

    print("Scanning 2021 folder recursively for .docx files...")
    all_files = []
    for root_dir, dirs, files in os.walk(base_dir):
        for file in files:
            if file.lower().endswith(".docx") and not file.startswith("~$") and "_copy" not in file:
                all_files.append(Path(root_dir) / file)

    # Sort files chronologically by filename date
    all_files.sort(key=lambda x: x.name)
    print(f"Found {len(all_files)} bulletins in 2021 to process.")

    system_prompt = build_system_prompt()
    few_shot = few_shot_messages()

    fieldnames = ["weather system", "date", "heightAboveMSL", "Regions"]

    # Load checkpoint/resume state
    done_files = set()
    if resume_file.exists():
        done_files = set(resume_file.read_text(encoding="utf-8").splitlines())
        print(f"Resuming: {len(done_files)} files already processed.")

    # Initialize CSV files (headers) if they don't exist
    writers = {}
    file_handles = {}
    for q, path in quarter_files.items():
        new_file = not path.exists() or path.stat().st_size == 0
        fh = path.open("a", newline="", encoding="utf-8")
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        if new_file:
            writer.writeheader()
            fh.flush()
        writers[q] = writer
        file_handles[q] = fh

    pending_files = [f for f in all_files if f.name not in done_files]
    print(f"Processing {len(pending_files)} pending bulletins...")

    try:
        for idx, path in enumerate(pending_files, 1):
            q = get_file_quarter(path)
            if q is None:
                print(f"[{idx}/{len(pending_files)}] Warning: Could not determine quarter for {path.name}. Skipping.")
                continue

            print(f"[{idx}/{len(pending_files)}] 2021 - Q{q} - Extracting from: {path.name}...")
            
            retry_count = 0
            success = False
            rows = []
            while retry_count < 3:
                try:
                    rows = extract_bulletin_fireworks(api_key, path, system_prompt, few_shot)
                    success = True
                    break
                except (requests.HTTPError, requests.exceptions.Timeout) as exc:
                    is_timeout = isinstance(exc, requests.exceptions.Timeout)
                    status_code = exc.response.status_code if (not is_timeout and exc.response is not None) else None
                    retry_count += 1
                    wait = 10.0
                    err_desc = "Timeout" if is_timeout else f"{status_code} error"
                    print(f"  ~ Warning: {err_desc}, retry {retry_count}/3 after {wait}s...", flush=True)
                    time.sleep(wait)
                except Exception as e:
                    print(f"  ~ Unexpected error: {e}. Skipping file.", flush=True)
                    break
            
            if success:
                if rows:
                    print(f"  -> Extracted {len(rows)} entries.")
                    for row in rows:
                        writers[q].writerow(row)
                    file_handles[q].flush()
                else:
                    print("  -> No weather systems observed.")
                
                # Mark done
                with resume_file.open("a", encoding="utf-8") as rf:
                    rf.write(path.name + "\n")
                
                # API rate limit delay
                time.sleep(1.5)
            else:
                print(f"  -> Failed to extract from {path.name}.")

    finally:
        for fh in file_handles.values():
            fh.close()
        print("Finished processing.")

if __name__ == "__main__":
    main()
