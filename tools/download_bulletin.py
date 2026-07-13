#!/usr/bin/env python
"""
Scrapes the Daily Weather Summary bulletin PDF from the India Meteorological Department (IMD) Pune website,
extracts and verifies the date of the bulletin, and saves it locally.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
import requests

try:
    from pypdf import PdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False


WEBSITE_URL = "https://imdpune.gov.in/weatherservice.php"
STATIC_PDF_URL = "https://imdpune.gov.in/ws/aiws.pdf"
DATE_PATTERN = re.compile(
    r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s*,?\s*(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{4})\b",
    re.I
)


def get_bulletin_url() -> str:
    """
    Fetches the weather service page and looks for the 'Daily Weather Summary Reports (new)' link.
    Falls back to the static PDF URL if parsing fails or if the link is not found.
    """
    print(f"Connecting to {WEBSITE_URL} to locate the Daily Weather Summary PDF link...")
    try:
        resp = requests.get(WEBSITE_URL, timeout=15)
        resp.raise_for_status()
        html = resp.text

        # Look for the link matching the pattern for Daily Weather Summary Reports
        # Example in markdown format from our read was:
        # [Daily Weather Summary Reports (new)](https://imdpune.gov.in/ws/aiws.pdf)
        # In HTML it might look like: <a href="ws/aiws.pdf">Daily Weather Summary Reports (new)</a>
        # Let's find any href next to the text "Daily Weather Summary Reports"
        match = re.search(r'href=["\']([^"\']+\.pdf)["\'][^>]*>.*?Daily Weather Summary Reports', html, re.I)
        if not match:
            # Try matching text first then href
            match = re.search(r'Daily Weather Summary Reports.*?href=["\']([^"\']+\.pdf)["\']', html, re.I)
        
        if match:
            href = match.group(1)
            # Resolve relative URLs
            if not href.startswith("http"):
                # URL might be relative to the root or current page
                if href.startswith("/"):
                    href = "https://imdpune.gov.in" + href
                else:
                    href = "https://imdpune.gov.in/ws/" + href.split("/")[-1]
            print(f"Located dynamic PDF URL: {href}")
            return href
        else:
            print("Could not find dynamic link in HTML page. Falling back to static URL.")
    except Exception as e:
        print(f"Warning: Failed to fetch webpage or parse link: {e}. Falling back to static URL.")
    
    return STATIC_PDF_URL


def extract_date_from_pdf(pdf_path: Path) -> str | None:
    """
    Extracts text from the first page of the PDF and uses regex to find the bulletin date.
    Returns the date as YYYY-MM-DD, or None if extraction or parsing fails.
    """
    if not PYPDF_AVAILABLE:
        print("Warning: pypdf is not installed. Cannot verify the date inside the PDF file.")
        return None

    try:
        reader = PdfReader(pdf_path)
        if not reader.pages:
            print("Error: The downloaded PDF has no pages.")
            return None
        
        # Check first page text
        first_page_text = reader.pages[0].extract_text()
        if not first_page_text:
            print("Warning: No text could be extracted from the first page of the PDF.")
            return None
        
        # Search for date pattern
        match = DATE_PATTERN.search(first_page_text)
        if match:
            day, month_name, year = match.groups()
            clean_date_str = f"{int(day):02d} {month_name} {year}"
            try:
                dt = datetime.strptime(clean_date_str, "%d %B %Y")
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                print(f"Warning: Match found '{clean_date_str}' but could not parse it as date.")
                return None
    except Exception as e:
        print(f"Error reading PDF content: {e}")
        
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Download the Daily Weather Summary report from IMD Pune.")
    parser.add_argument("--output-dir", "-o", default="bulletins", help="Directory where the PDF should be saved.")
    parser.add_argument("--date", "-d", default="yesterday", help="Target date YYYY-MM-DD to download/verify. Defaults to 'yesterday'.")
    parser.add_argument("--force", "-f", action="store_true", help="Skip date verification and save whatever is downloaded.")
    args = parser.parse_args()

    # Determine target date
    if args.date.lower() == "yesterday":
        target_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        try:
            # Validate date format
            datetime.strptime(args.date, "%Y-%m-%d")
            target_date = args.date
        except ValueError:
            print(f"Error: Invalid date format for --date. Use YYYY-MM-DD or 'yesterday'. Got: {args.date}")
            sys.exit(1)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_url = get_bulletin_url()
    print(f"Downloading PDF from: {pdf_url}")

    # Download to a temporary file first
    try:
        resp = requests.get(pdf_url, stream=True, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"Error downloading the PDF file: {e}")
        sys.exit(1)

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    
    try:
        with open(tmp_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        # Verify size
        if tmp_path.stat().st_size < 1000:
            print("Error: The downloaded file is too small to be a valid PDF.")
            sys.exit(1)

        # Check PDF date
        pdf_date = extract_date_from_pdf(tmp_path)
        if pdf_date:
            print(f"Extracted date from PDF: {pdf_date}")
        else:
            print("Could not extract date from PDF content.")

        # Validation logic
        if args.force:
            save_date = pdf_date or datetime.now().strftime("%Y-%m-%d")
            dest_filename = f"AIWS_{save_date.replace('-', '')}.pdf"
            dest_path = output_dir / dest_filename
            import shutil
            shutil.copy2(tmp_path, dest_path)
            print(f"Force saved bulletin (unverified) to: {dest_path}")
        else:
            if not pdf_date:
                if not PYPDF_AVAILABLE:
                    # If pypdf is not available, we can look at the Last-Modified header
                    last_mod = resp.headers.get("Last-Modified")
                    if last_mod:
                        try:
                            # e.g., "Tue, 07 Jul 2026 10:04:10 GMT"
                            lm_dt = datetime.strptime(last_mod, "%a, %d %b %Y %H:%M:%S %Z")
                            pdf_date = lm_dt.strftime("%Y-%m-%d")
                            print(f"Extracted date from Last-Modified header: {pdf_date}")
                        except ValueError:
                            pass
                
                if not pdf_date:
                    print("Error: Date verification failed because no date could be extracted.")
                    print("Run with --force to save the file without verification, or install pypdf.")
                    sys.exit(1)

            if pdf_date == target_date:
                dest_filename = f"AIWS_{pdf_date.replace('-', '')}.pdf"
                dest_path = output_dir / dest_filename
                import shutil
                shutil.copy2(tmp_path, dest_path)
                print(f"Success! Downloaded and verified bulletin for {pdf_date}. Saved to: {dest_path}")
            else:
                print(f"Error: Bulletin date '{pdf_date}' does not match the target date '{target_date}'.")
                print("If you still want to keep this bulletin, run with --force.")
                sys.exit(1)

    finally:
        # Clean up temp file
        if tmp_path.exists():
            tmp_path.unlink()


if __name__ == "__main__":
    main()
