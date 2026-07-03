import json
from pathlib import Path

GAZETTEER_PATH = Path(r"C:\xampp\htdocs\aiws-weather-parser\data\form_subdivisions_gazetteer.json")
gazetteer = json.loads(GAZETTEER_PATH.read_text(encoding="utf-8"))

for item in gazetteer:
    if "iran" in item["name"].lower():
        print(item)
