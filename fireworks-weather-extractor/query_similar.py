from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

# Add current folder to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent

def load_db_config() -> dict[str, str]:
    """Return local database connection credentials."""
    return {
        "DB_HOST": "localhost",
        "DB_PORT": "3306",
        "DB_USER": "root",
        "DB_PASSWORD": "",
        "DB_NAME": "weather_data_system"
    }

def fetch_historical_data() -> list[dict]:
    """Fetch all entries from the MySQL database using the mysql.exe CLI."""
    db_config = load_db_config()
    mysql_path = "C:/xampp/mysql/bin/mysql.exe"
    if not Path(mysql_path).exists():
        mysql_path = "mysql"  # Fallback to PATH

    # Query to fetch all records
    query = "SELECT entry_date, weather_system, height, subdivisions FROM weather_system_entries ORDER BY entry_date DESC"
    
    cmd = [
        mysql_path,
        "-h", db_config["DB_HOST"],
        "-P", db_config["DB_PORT"],
        "-u", db_config["DB_USER"]
    ]
    if db_config["DB_PASSWORD"]:
        cmd.append(f"-p{db_config['DB_PASSWORD']}")
    cmd.extend([
        "-D", db_config["DB_NAME"],
        "-e", query,
        "-B"  # Batch mode (tab-separated output)
    ])
    
    try:
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
        pressure = entry.get("height") or entry.get("pressure_level") or entry.get("heightAboveMSL") or ""
        subs = entry.get("subdivisions") or entry.get("Regions") or ""
        
        if sys_type:
            tokens.append(f"sys_{clean_token(sys_type)}")
        if pressure:
            tokens.append(f"pres_{clean_token(pressure)}")
        if subs:
            delimiter = ";" if ";" in subs else ","
            for sub in subs.split(delimiter):
                sub_clean = clean_token(sub)
                if sub_clean:
                    tokens.append(f"sub_{sub_clean}")
    return tokens

class PureTFIDF:
    """A lightweight, dependency-free TF-IDF and similarity calculator."""
    def __init__(self, corpus_tokens: list[list[str]]):
        self.num_docs = len(corpus_tokens)
        self.df = {}
        for doc in corpus_tokens:
            unique_words = set(doc)
            for word in unique_words:
                self.df[word] = self.df.get(word, 0) + 1
                
        self.idf = {}
        for word, count in self.df.items():
            self.idf[word] = math.log(self.num_docs / max(count, 1))

    def vectorize(self, tokens: list[str]) -> dict[str, float]:
        """Compute the L2-normalized TF-IDF vector for a list of tokens."""
        tf = {}
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1
            
        vector = {}
        for token, count in tf.items():
            if token in self.idf:
                vector[token] = count * self.idf[token]
                
        square_sum = sum(val ** 2 for val in vector.values())
        if square_sum > 0:
            l2_norm = math.sqrt(square_sum)
            for token in vector:
                vector[token] /= l2_norm
                
        return vector

    @staticmethod
    def cosine_similarity(v1: dict[str, float], v2: dict[str, float]) -> float:
        similarity = 0.0
        for token, val in v1.items():
            if token in v2:
                similarity += val * v2[token]
        return similarity

def main():
    parser = argparse.ArgumentParser(description="Find similar weather days in the database by date")
    parser.add_argument("--date", required=True, help="The target query date in YYYY-MM-DD format")
    args = parser.parse_args()
    
    query_date = args.date
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", query_date):
        print(json.dumps({"error": f"Invalid date format: {query_date}. Use YYYY-MM-DD."}))
        sys.exit(1)
        
    # 1. Fetch historical data from MySQL database
    historical_rows = fetch_historical_data()
    if not historical_rows:
        print(json.dumps({"error": "No weather systems found in the database. Please ensure the local MySQL database is populated."}))
        sys.exit(1)
        
    # 2. Group historical rows by date
    days_data: dict[str, list[dict]] = {}
    for row in historical_rows:
        date = row["entry_date"]
        if date not in days_data:
            days_data[date] = []
        days_data[date].append(row)
        
    # 3. Check if query date exists in database
    if query_date not in days_data:
        print(json.dumps({"error": f"Data for the day {query_date} is not available."}))
        sys.exit(1)
        
    # Extract query entries
    query_entries = days_data[query_date]
    
    # Exclude the query date from historical database corpus comparison
    del days_data[query_date]
    
    if not days_data:
        print(json.dumps({"error": "No other historical days left to compare in the database."}))
        sys.exit(1)
        
    # 4. Tokenize profiles
    query_tokens = build_profile_tokens(query_entries)
    
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
            pressure = entry.get("height") or entry.get("pressure_level") or ""
            subs = entry.get("subdivisions") or ""
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
                "system": r.get("weather_system") or "",
                "pressure": r.get("height") or r.get("pressure_level") or "",
                "subdivisions": [s.strip() for s in (r.get("subdivisions") or "").split(";") if s.strip()]
            }
            for r in query_entries
        ],
        "top_matches": top_5
    }
    
    print(json.dumps(output))

if __name__ == "__main__":
    main()
