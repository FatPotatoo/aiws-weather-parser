# LLM-based AIWS extractor

Reads IMD All India Weather Summary (AIWS) `.docx` bulletins and returns
structured weather-system data using **Claude (`claude-opus-4-8`) structured
output**, instead of the brittle regex pipeline in [`../extract.py`](../extract.py).

It was built to fix the recall problem on the regex extractor: the old code only
recognized `WD` / `CYCIR` / `Trough`, only read one paragraph, and only detected
systems written at the start of a sentence — so monsoon-season Low Pressure Areas,
Depressions, and mid-sentence systems were silently dropped.

## What it reuses from the existing pipeline

The LLM does only the hard natural-language part (finding and attributing every
system). The deterministic parts stay in [`../extract.py`](../extract.py) and are
imported, not reimplemented:

- `read_docx_paragraphs`, bulletin-date parsing
- the official subdivision list (`load_form_subdivisions`, from `js/weather_form.js`)
- the height→pressure-level chart (`height_to_pressure_levels`)

The output CSV columns are identical to the old enriched CSV, so it flows into the
same database loader.

## Setup

```powershell
pip install -r llm_extractor/requirements.txt
$env:ANTHROPIC_API_KEY = "sk-ant-..."   # your Anthropic API key
$env:GEMINI_API_KEY = "AIza..."        # your Gemini API key for gemini_runner
```
## Run

`.doc` bulletins must be converted to `.docx` first (see the conversion note in the
project root). Then:

```powershell
# Test on 2 files first to sanity-check output and cost:
python -m llm_extractor.runner --folder AIWS2025 --out output_llm.csv --limit 2

# Full run:
python -m llm_extractor.runner --folder AIWS2025 --out output_llm.csv
```

Then load into the database (full refresh of `weather_system_entries`):

```powershell
python database/load_csv_to_entries.py output_llm.csv ^
    | & "C:/xampp/mysql/bin/mysql.exe" -u root weather_data_system
```

## How it works

- **One cached system prompt** ([prompt.py](prompt.py)) holds the extraction rules
  and the official subdivision list. It's marked with `cache_control`, so after the
  first bulletin every subsequent call reads it from cache (watch the `cache-read`
  number the runner prints).
- **Per bulletin** ([extractor.py](extractor.py)): the summary prose is gathered
  (all prose paragraphs, skipping numeric station tables), sent to Claude with
  adaptive thinking, and returned as a validated `BulletinExtraction`
  ([schema.py](schema.py)). Forecast-only systems are flagged and dropped.

## Notes / knobs

- `weather_system` labels: the three original types keep their DB codes
  (`WD` / `CYCIR` / `Trough`); new types use full names (`Low Pressure Area`,
  `Depression`, …). Change the mapping in [schema.py](schema.py) `DB_LABELS`.
- To benchmark against the old extractor, run both and diff `output_llm.csv`
  against `output_aiws_corrected_subdivisions_fixed.csv` (the current 338 rows).
