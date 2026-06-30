from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Batch process weather summaries monthwise using Fireworks GLM 5.2")
    parser.add_argument(
        "--months",
        default="January,February,March",
        help="Comma-separated list of months to process (e.g. 'January,February,March' or 'April,May,June')"
    )
    parser.add_argument(
        "--year",
        default="2025",
        help="Year folder to look under (default: 2025)"
    )
    parser.add_argument(
        "--base-dir",
        default="C:/Users/ACER/Desktop/AIWS",
        help="Base directory containing the year folders (default: C:/Users/ACER/Desktop/AIWS)"
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output CSV file path. If specified, all months will append to this single file."
    )
    args = parser.parse_args()

    api_key = os.environ.get("FIREWORKS_API_KEY")
    if not api_key:
        print("Error: FIREWORKS_API_KEY environment variable is not set.")
        print("Please set it before running, for example:")
        print("  $env:FIREWORKS_API_KEY = 'your_key'")
        sys.exit(1)

    base_dir = Path(args.base_dir) / args.year
    months_to_run = [m.strip() for m in args.months.split(",") if m.strip()]
    
    print(f"Starting Fireworks GLM 5.2 weather system extraction for: {', '.join(months_to_run)} ({args.year})...\n")
    
    for month_name in months_to_run:
        folder_path = base_dir / month_name / "AIWS"
        out_file = args.out if args.out else f"output_{month_name.lower()[:3]}_{args.year}.csv"
        
        if not folder_path.exists():
            print(f"Skipping {month_name}: folder {folder_path} does not exist.")
            continue
            
        print(f"==========================================")
        print(f"Processing: {month_name}")
        print(f"Folder: {folder_path}")
        print(f"Output: {out_file}")
        print(f"==========================================")
        
        cmd = [
            sys.executable,
            str(Path(__file__).parent / "runner.py"),
            "--folder", str(folder_path),
            "--out", out_file,
            "--delay", "1.5"
        ]
        
        try:
            subprocess.run(cmd, check=True)
            print(f"Completed {month_name} successfully.\n")
        except subprocess.CalledProcessError as exc:
            print(f"Error occurred while processing {month_name}: {exc}")
            print("Stopping batch run.")
            sys.exit(1)

    print("Batch extraction finished.")

if __name__ == "__main__":
    main()
