from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

# Add current folder to sys.path to import local modules
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_DIR))

from extractor import extract_bulletin_fireworks, DEFAULT_MODEL
from prompt import build_system_prompt, few_shot_messages

def get_api_key() -> str:
    """Load API key from environment variable or config/fireworks.json."""
    # 1. Check environment variable
    api_key = os.environ.get("FIREWORKS_API_KEY", "")
    if api_key:
        return api_key

    # 2. Check local config file
    config_path = SCRIPT_DIR.parent / "config" / "fireworks.json"
    if config_path.exists():
        try:
            with config_path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
                return data.get("FIREWORKS_API_KEY", "")
        except Exception:
            pass
            
    return ""

def fetch_historical_data() -> list[dict]:
    """Fetch all entries from the MySQL database using the mysql.exe CLI."""
    mysql_path = "C:/xampp/mysql/bin/mysql.exe"
    if not Path(mysql_path).exists():
        mysql_path = "mysql"  # Fallback to PATH

    # Query to fetch all records
    query = "SELECT entry_date, weather_system, pressure_level, subdivisions FROM weather_system_entries ORDER BY entry_date DESC"
    
    cmd = [
        mysql_path,
        "-u", "root",
        "-D", "weather_data_system",
        "-e", query,
        "-B"  # Batch mode (tab-separated output)
    ]
    
    try:
        # Run command and capture output
        res = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding="utf-8")
        lines = res.stdout.strip().split("\n")
        if not lines or len(lines) <= 1:
            return []
            
        headers = lines[0].split("\t")
        records = []
        for line in lines[1:]:
            parts = line.split("\t")
            if len(parts) == len(headers):
                records.append(dict(zip(headers, parts)))
        return records
    except Exception as e:
        # Return empty list if MySQL command fails or is not running
        sys.stderr.write(f"Error querying database: {e}\n")
        return []

def clean_token(text: str) -> str:
    """Normalize text into a clean token format."""
    return re.sub(r"[^a-zA-Z0-9]", "_", text.lower().strip())

def build_profile_tokens(entries: list[dict]) -> list[str]:
    """Convert a list of weather system entries into feature tokens."""
    tokens = []
    for entry in entries:
        sys_type = entry.get("weather_system") or entry.get("weather system") or ""
        pressure = entry.get("pressure_level") or entry.get("heightAboveMSL") or ""
        subs = entry.get("subdivisions") or entry.get("Regions") or ""
        
        if sys_type:
            tokens.append(f"sys_{clean_token(sys_type)}")
        if pressure:
            tokens.append(f"pres_{clean_token(pressure)}")
        if subs:
            # Subdivisions can be semicolon- or comma-separated
            delimiter = ";" if ";" in subs else ","
            for sub in subs.split(delimiter):
                sub_clean = clean_token(sub)
                if sub_clean:
                    tokens.append(f"sub_{sub_clean}")
    return tokens

# --- Pure Python TF-IDF and Cosine Similarity Implementation ---

class PureTFIDF:
    """A lightweight, dependency-free TF-IDF and similarity calculator."""
    def __init__(self, corpus_tokens: list[list[str]]):
        self.num_docs = len(corpus_tokens)
        
        # 1. Compute Document Frequency (DF)
        self.df = {}
        for doc in corpus_tokens:
            unique_words = set(doc)
            for word in unique_words:
                self.df[word] = self.df.get(word, 0) + 1
                
        # 2. Compute IDF: log(N / df)
        self.idf = {}
        for word, count in self.df.items():
            self.idf[word] = math.log(self.num_docs / count)

    def vectorize(self, tokens: list[str]) -> dict[str, float]:
        """Compute the L2-normalized TF-IDF vector for a list of tokens."""
        # Compute Term Frequency (TF)
        tf = {}
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1
            
        # Compute TF-IDF
        vector = {}
        for token, count in tf.items():
            if token in self.idf:
                vector[token] = count * self.idf[token]
                
        # L2 Normalization
        square_sum = sum(val ** 2 for val in vector.values())
        if square_sum > 0:
            l2_norm = math.sqrt(square_sum)
            for token in vector:
                vector[token] /= l2_norm
                
        return vector

    @staticmethod
    def cosine_similarity(v1: dict[str, float], v2: dict[str, float]) -> float:
        """Compute the dot portion of two L2-normalized vectors."""
        similarity = 0.0
        for token, val in v1.items():
            if token in v2:
                similarity += val * v2[token]
        return similarity

# ----------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Find similar weather days in the database")
    parser.add_argument("file_path", help="Path to the query .docx bulletin")
    args = parser.parse_args()
    
    file_path = Path(args.file_path)
    if not file_path.exists():
        print(json.dumps({"error": f"Uploaded file does not exist: {file_path}"}))
        sys.exit(1)
        
    api_key = get_api_key()
    if not api_key:
        print(json.dumps({"error": "Fireworks API Key is not configured. Please set FIREWORKS_API_KEY environment variable or save it in config/fireworks.json."}))
        sys.exit(1)
        
    # 1. Extract weather systems from the query document
    try:
        sys_prompt = build_system_prompt()
        few_shot = few_shot_messages()
        extracted_rows = extract_bulletin_fireworks(api_key, file_path, sys_prompt, few_shot, model=DEFAULT_MODEL)
    except Exception as e:
        print(json.dumps({"error": f"Failed to extract weather data from file: {str(e)}"}))
        sys.exit(1)
        
    if not extracted_rows:
        print(json.dumps({"error": "No weather systems could be extracted from the uploaded document."}))
        sys.exit(1)
        
    # The date extracted from the first row of the query document
    query_date = extracted_rows[0].get("date", "Uploaded Document")

    # 2. Fetch historical data from MySQL database
    historical_rows = fetch_historical_data()
    if not historical_rows:
        print(json.dumps({"error": "No historical weather systems found in the database. Please load data first."}))
        sys.exit(1)
        
    # 3. Group historical rows by date
    days_data: dict[str, list[dict]] = {}
    for row in historical_rows:
        date = row["entry_date"]
        if date not in days_data:
            days_data[date] = []
        days_data[date].append(row)
        
    # Exclude the query date if it already exists in the database
    if query_date in days_data:
        del days_data[query_date]
        
    if not days_data:
        print(json.dumps({"error": "No other historical days left to compare in the database."}))
        sys.exit(1)
        
    # 4. Tokenize profiles
    query_tokens = build_profile_tokens(extracted_rows)
    
    corpus_tokens = [query_tokens]
    dates_list = []
    for date, entries in days_data.items():
        dates_list.append(date)
        corpus_tokens.append(build_profile_tokens(entries))
        
    # 5. Calculate TF-IDF Vectors
    tfidf = PureTFIDF(corpus_tokens)
    query_vector = tfidf.vectorize(query_tokens)
    
    # 6. Compare similarity for each date
    matches = []
    for idx, date in enumerate(dates_list):
        doc_tokens = corpus_tokens[idx + 1]
        doc_vector = tfidf.vectorize(doc_tokens)
        score = tfidf.cosine_similarity(query_vector, doc_vector)
        
        # Build summary of what was observed on that historical day for presentation
        day_entries = days_data[date]
        systems_summary = []
        for entry in day_entries:
            sys_type = entry.get("weather_system") or ""
            pressure = entry.get("pressure_level") or ""
            subs = entry.get("subdivisions") or ""
            # Format nicely
            systems_summary.append({
                "system": sys_type,
                "pressure": pressure,
                "subdivisions": [s.strip() for s in subs.split(";") if s.strip()]
            })
            
        matches.append({
            "date": date,
            "score": round(score * 100, 1),
            "systems": systems_summary
        })
        
    # Sort by score descending
    matches.sort(key=lambda x: x["score"], reverse=True)
    
    # Take top 5
    top_5 = matches[:5]
    
    # Output the result
    output = {
        "query_date": query_date,
        "query_extracted": [
            {
                "system": r.get("weather system") or r.get("weather_system") or "",
                "pressure": r.get("heightAboveMSL") or r.get("pressure_level") or "",
                "subdivisions": [s.strip() for s in (r.get("Regions") or r.get("subdivisions") or "").split(";") if s.strip()]
            }
            for r in extracted_rows
        ],
        "top_matches": top_5
    }
    
    print(json.dumps(output))

if __name__ == "__main__":
    main()
