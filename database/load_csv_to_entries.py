"""Load enriched extraction CSV(s) into the flat `weather_system_entries` table.

This script generates and outputs SQL to stdout (which can be piped to MySQL),
or directly executes the SQL script via XAMPP's mysql client if --push is provided.

It supports both the original CSV columns and the new Fireworks extractor columns:
    date/entry_date     -> entry_date
    weather system/weather_system -> weather_system
    heightAboveMSL/pressure_level -> pressure_level
    Regions/subdivisions -> subdivisions

Usage:
    # 1. Output SQL to stdout:
    python database/load_csv_to_entries.py output_jan_2025.csv output_feb_2025.csv

    # 2. Push directly to XAMPP MySQL (local):
    python database/load_csv_to_entries.py output_jan_2025.csv output_feb_2025.csv --push
"""
from __future__ import annotations

import argparse
import csv
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_CSV = REPO / "output_aiws_corrected_subdivisions_fixed.csv"
TABLE = "weather_system_entries"


def normalize_date(value: str) -> str:
    """Accept ISO (2025-06-01) or DD-MM-YYYY (01-05-2026) and return YYYY-MM-DD."""
    value = (value or "").strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date format: {value!r}")


def normalize_pressure(value: str) -> str:
    """Normalize height/pressure level. If 0, MSL, or empty, translate to 'Surface'."""
    val = (value or "").strip()
    val_lower = val.lower()
    if val_lower in ("0.0 km", "0 km", "0", "0.0", "", "null", "mean sea level", "at mean sea level", "msl"):
        return "Surface"
    return val


def sql_str(value: str) -> str:
    """Quote/escape a string literal for MySQL, or NULL when empty."""
    value = (value or "").strip()
    if not value:
        return "NULL"
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def chunked(rows: list[str], size: int = 200):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def parse_csv_files(paths: list[Path]) -> list[tuple[str, str, str, str]]:
    """Parse multiple CSV files, automatically mapping headers, and return list of value rows."""
    parsed_rows: list[tuple[str, str, str, str]] = []
    
    for path in paths:
        if not path.exists():
            print(f"Warning: File not found: {path}", file=sys.stderr)
            continue
            
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for r in reader:
                # Resolve date key
                date_val = r.get("date") or r.get("entry_date")
                if not date_val:
                    continue
                    
                try:
                    entry_date = normalize_date(date_val)
                except ValueError as e:
                    print(f"Warning: Skipping row with invalid date: {e}", file=sys.stderr)
                    continue
                
                # Resolve weather system key
                system = (r.get("weather_system") or r.get("weather system") or "").strip()
                if not system:
                    continue  # flat table requires a weather_system (NOT NULL)
                
                # Resolve subdivisions/regions key
                subs = (r.get("subdivisions") or r.get("Regions") or "").strip()
                
                # Resolve pressure level/height key
                raw_pressure = (r.get("pressure_level") or r.get("heightAboveMSL") or "").strip()
                pressure = normalize_pressure(raw_pressure)
                
                parsed_rows.append((entry_date, system, pressure, subs))
                
    return parsed_rows


def build_sql(parsed_rows: list[tuple[str, str, str, str]], append: bool = False) -> str:
    """Generate MySQL commands for inserting all rows."""
    values: list[str] = []
    for entry_date, system, pressure, subs in parsed_rows:
        values.append(
            f"({sql_str(entry_date)}, {sql_str(system)}, {sql_str(pressure)}, {sql_str(subs)})"
        )

    out: list[str] = []
    out.append(f"-- Prepared {len(values)} rows to load into table `{TABLE}`.")
    out.append("START TRANSACTION;")
    if not append:
        out.append(f"DELETE FROM {TABLE};")
        out.append(f"ALTER TABLE {TABLE} AUTO_INCREMENT = 1;")
        
    for batch in chunked(values):
        out.append(
            f"INSERT INTO {TABLE} (entry_date, weather_system, height, subdivisions) VALUES"
        )
        out.append(",\n".join(batch) + ";")
    out.append("COMMIT;")
    return "\n".join(out) + "\n"


def load_db_config() -> dict[str, str]:
    """Return local database connection credentials."""
    return {
        "DB_HOST": "localhost",
        "DB_PORT": "3306",
        "DB_USER": "root",
        "DB_PASSWORD": "",
        "DB_NAME": "weather_data_system"
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SQL statements or directly load weather CSV data into database.")
    parser.add_argument("csv_files", nargs="*", help="One or more CSV files to read and load.")
    parser.add_argument("--push", action="store_true", help="Directly push SQL into MySQL database.")
    parser.add_argument("--append", action="store_true", help="Append entries to the table without truncating it first.")
    args = parser.parse_args()

    # Resolve input files
    paths: list[Path] = []
    if args.csv_files:
        for f in args.csv_files:
            paths.append(Path(f))
    else:
        paths.append(DEFAULT_CSV)

    parsed_rows = parse_csv_files(paths)
    if not parsed_rows:
        print("No valid rows found to load.", file=sys.stderr)
        sys.exit(1)

    sql_content = build_sql(parsed_rows, append=args.append)

    if args.push:
        db_config = load_db_config()
        mysql_path = "C:/xampp/mysql/bin/mysql.exe"
        if not Path(mysql_path).exists():
            mysql_path = shutil.which("mysql")
        if not mysql_path:
            print("Error: mysql.exe not found at C:/xampp/mysql/bin/mysql.exe or in system PATH.", file=sys.stderr)
            sys.exit(1)
            
        print(f"Connecting to database '{db_config['DB_NAME']}' on '{db_config['DB_HOST']}'...", file=sys.stderr)
        
        cmd = [
            mysql_path,
            "-h", db_config["DB_HOST"],
            "-P", db_config["DB_PORT"],
            "-u", db_config["DB_USER"]
        ]
        if db_config["DB_PASSWORD"]:
            cmd.append(f"-p{db_config['DB_PASSWORD']}")
        cmd.append(db_config["DB_NAME"])

        try:
            subprocess.run(
                cmd,
                input=sql_content,
                text=True,
                encoding="utf-8",
                check=True
            )
            print("Successfully loaded CSV data into the database!", file=sys.stderr)
        except Exception as e:
            print(f"Error running MySQL CLI: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        sys.stdout.write(sql_content)


if __name__ == "__main__":
    main()
