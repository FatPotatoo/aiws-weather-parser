---
name: fireworks-extractor
description: Extraction agent for India Meteorological Department (IMD) synoptic weather systems using the GLM 5.2 model of the Fireworks AI API.
---

# Fireworks GLM 5.2 Weather Extractor Agent

This agent extracts observed synoptic weather systems (Western Disturbances, Cyclonic Circulations, Troughs, Low Pressure Areas, Depressions, etc.) from India Meteorological Department (IMD) All India Weather Summary (AIWS) bulletins using the **GLM 5.2** model via the **Fireworks AI API**.

The extracted output is formatted into the specified structure:
```json
{
  "weather system": "<System Type>",
  "date": "<YYYY-MM-DD>",
  "heightAboveMSL": "<Height in km, Surface, or Not specified>",
  "Regions": "<Meteorological Subdivisions or region description>"
}
```

## Setup & Running

1. **Install Dependencies**:
   ```bash
   pip install -r c:/xampp/htdocs/fireworks-weather-extractor/requirements.txt
   ```

2. **Configure API Key**:
   Provide your Fireworks API Key as an environment variable:
   ```powershell
   $env:FIREWORKS_API_KEY = "your_fireworks_api_key_here"
   ```

3. **Run Extraction**:
   Run the extractor runner:
   ```bash
   python c:/xampp/htdocs/fireworks-weather-extractor/runner.py --folder c:/xampp/htdocs/aiws-weather-parser/AIWS2025 --out output_fireworks.csv --limit 2
   ```
