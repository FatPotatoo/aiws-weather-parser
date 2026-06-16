import random
import csv
import sys
from pathlib import Path

repo = Path(__file__).resolve().parent
sys.path.insert(0, str(repo))

import extract
from llm_extractor.ollama_extractor import extract_bulletin_ollama, DEFAULT_MODEL
from llm_extractor.prompt import build_system_prompt
import ollama

folder = repo / 'AIWS2025'
files = [p for p in extract.list_word_files(folder) if not p.name.startswith('~$')]
if len(files) < 5:
    raise SystemExit(f'Not enough .docx files: {len(files)}')
selected = random.sample(files, 5)
print('Selected files:')
for f in selected:
    print('  ', f.name)

client = ollama.Client(timeout=600)
available_models = [m.get('model') or m.get('name') for m in client.list().get('models', [])]
print('Available models:', available_models)
if DEFAULT_MODEL not in available_models and f'{DEFAULT_MODEL}:latest' not in available_models:
    raise SystemExit(f'Model {DEFAULT_MODEL} not installed or unavailable')

output_path = repo / 'output_ollama_random5.csv'
fieldnames = ['date', 'source_file', 'weather_system', 'subdivisions', 'region', 'region_original', 'height_km', 'pressure_level', 'status']
all_rows = []
for path in selected:
    print('Extracting', path.name)
    rows = extract_bulletin_ollama(client, path, build_system_prompt(), DEFAULT_MODEL)
    print('  rows:', len(rows))
    for row in rows:
        row['source_file'] = path.name
    all_rows.extend(rows)

with output_path.open('w', newline='', encoding='utf-8') as fh:
    writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    for row in all_rows:
        writer.writerow({key: row.get(key, '') for key in fieldnames})

print('Wrote', len(all_rows), 'rows to', output_path)
print('Unique source_file count:', len({r['source_file'] for r in all_rows}))
print('Output file path:', output_path)
