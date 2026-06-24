from pathlib import Path
import extract
import re

p = Path(r'C:/Users/ACER/Desktop/AIWS/2025/January/AIWS 20250101.docx')
print('stem:', p.stem)
print('parse filename:', extract.parse_bulletin_date_from_filename(p))
m = re.search(r'(20\d{2})(\d{2})(\d{2})', p.stem)
print('regex:', m.groups() if m else None)
