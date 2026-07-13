import os
import sys
import csv
import time
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
import requests

# Add current folder to path
sys.path.append(str(Path(__file__).parent))

from extractor import extract_bulletin_fireworks, DEFAULT_MODEL
from prompt import build_system_prompt, few_shot_messages

base_dir = Path(r"C:\Users\suyas\Downloads\AIWS\2021")
out_csv = Path(r"c:\xampp\htdocs\aiws-weather-parser\fireworks-weather-extractor\output_depression_2025.csv")
resume_file = out_csv.parent / f".{out_csv.name}.resume"

def get_docx_paragraphs(path):
    try:
        with zipfile.ZipFile(path) as z:
            xml_content = z.read('word/document.xml')
            root = ET.fromstring(xml_content)
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            paragraphs = []
            for p in root.findall('.//w:p', ns):
                texts = [t.text for t in p.findall('.//w:t', ns) if t.text]
                if texts:
                    paragraphs.append("".join(texts))
            return paragraphs
    except Exception:
        return []

def main():
    api_key = os.environ.get("FIREWORKS_API_KEY")
    if not api_key:
        print("Error: FIREWORKS_API_KEY environment variable is not set.")
        return

    print("Scanning 2021 folders for bulletins referencing depression or cyclonic storms...")
    matching_files = []
    
    for root_dir, dirs, files in os.walk(base_dir):
        for file in files:
            # ONLY scan converted .docx files (exclude original .doc)
            if file.lower().endswith(".docx") and not file.startswith("~$"):
                file_path = Path(root_dir) / file
                paragraphs = get_docx_paragraphs(file_path)
                has_depression = False
                for p in paragraphs:
                    p_lower = p.lower()
                    if "depression" in p_lower or "cyclonic storm" in p_lower:
                        has_depression = True
                        break
                if has_depression:
                    matching_files.append(file_path)

    # Sort matching files chronologically
    matching_files.sort(key=lambda x: (x.parent.name.lower(), x.name))
    print(f"Found {len(matching_files)} bulletins with depression/cyclonic storm references in 2021.")

    system_prompt = build_system_prompt()
    few_shot = few_shot_messages()

    fieldnames = ["weather system", "date", "heightAboveMSL", "Regions"]
    
    # Check if resume is possible
    done_files = set()
    if resume_file.exists():
        done_files = set(resume_file.read_text(encoding="utf-8").splitlines())
        print(f"Resuming: {len(done_files)} files already processed.")

    # Open CSV in append mode
    new_file = not out_csv.exists() or out_csv.stat().st_size == 0
    fh = out_csv.open("a", newline="", encoding="utf-8")
    writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
    if new_file:
        writer.writeheader()
        fh.flush()

    pending_files = [f for f in matching_files if f.name not in done_files]
    print(f"Processing {len(pending_files)} pending bulletins for 2021...")

    for idx, path in enumerate(pending_files, 1):
        print(f"[{idx}/{len(pending_files)}] 2021 - Extracting from: {path.name}...")
        
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
                    writer.writerow(row)
                fh.flush()
            else:
                print("  -> No observed depression entries.")
            
            # Mark done
            with resume_file.open("a", encoding="utf-8") as rf:
                rf.write(path.name + "\n")
            
            # API rate limit delay
            time.sleep(1.5)
        else:
            print(f"  -> Failed to extract from {path.name}.")

    fh.close()
    print("Finished extracting 2021 depression entries.")

if __name__ == "__main__":
    main()
