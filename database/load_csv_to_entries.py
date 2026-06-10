"""Load an enriched extraction CSV into the flat `weather_system_entries` table.

This is the table the PHP app reads. It TRUNCATEs the table and reloads it from
the CSV, mapping only the four columns the table stores:

    date         -> entry_date     (normalized to YYYY-MM-DD)
    weather_system
    pressure_level
    subdivisions

The CSV's region / height_km / status columns are intentionally ignored because
the flat table does not have them.

Emits SQL on stdout. Pipe it into the XAMPP MySQL client:

    python database/load_csv_to_entries.py output_aiws_corrected_subdivisions_fixed.csv ^
        | "C:/xampp/mysql/bin/mysql.exe" -u root weather_data_system
"""
from pathlib import Path
import csv
import sys
from datetime import datetime

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


def sql_str(value: str) -> str:
    """Quote/escape a string literal for MySQL, or NULL when empty."""
    value = (value or "").strip()
    if not value:
        return "NULL"
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def chunked(rows: list[str], size: int = 200):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def build_sql(csv_path: Path) -> str:
    with csv_path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    values: list[str] = []
    for r in rows:
        entry_date = normalize_date(r["date"])
        system = (r.get("weather_system") or "").strip()
        if not system:
            continue  # the flat table requires a weather_system (NOT NULL)
        pressure = r.get("pressure_level", "")
        subs = r.get("subdivisions", "")
        values.append(
            f"('{entry_date}', {sql_str(system)}, {sql_str(pressure)}, {sql_str(subs)})"
        )

    out: list[str] = []
    out.append(f"-- Loaded from {csv_path.name} ({len(values)} rows) into {TABLE}.")
    out.append("START TRANSACTION;")
    out.append(f"DELETE FROM {TABLE};")
    out.append(f"ALTER TABLE {TABLE} AUTO_INCREMENT = 1;")
    for batch in chunked(values):
        out.append(
            f"INSERT INTO {TABLE} (entry_date, weather_system, pressure_level, subdivisions) VALUES"
        )
        out.append(",\n".join(batch) + ";")
    out.append("COMMIT;")
    return "\n".join(out) + "\n"


def main() -> None:
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CSV
    if not csv_path.exists():
        raise SystemExit(f"CSV not found: {csv_path}")
    sys.stdout.write(build_sql(csv_path))


if __name__ == "__main__":
    main()
