"""
Convert Vietnamese food CSV to JSON for meal optimizer
"""
import csv
import json
import re
from pathlib import Path

def parse_vn_float(s):
    """Parse Vietnamese number format: '8,6' → 8.6"""
    if not s or s.strip() in ('', '0', '0,0', '0,00'):
        return 0.0
    s = s.strip().strip('"').replace(',', '.')
    s = re.sub(r'[^\d.]', '', s)
    try:
        return round(float(s), 2)
    except:
        return 0.0

# Paths
csv_path = Path(__file__).parent.parent.parent.parent.parent / 'Dataset' / 'food_data.csv'
json_path = Path(__file__).parent.parent / 'data' / 'vietnamese_foods.json'

items = []
seen_names = set()

with open(csv_path, encoding='utf-8-sig') as f:
    reader = csv.reader(f)
    next(reader)  # skip header
    
    for i, row in enumerate(reader):
        if len(row) < 16:
            continue
        
        name = row[0].strip()
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        
        calories = parse_vn_float(row[1])
        protein = parse_vn_float(row[2])
        fat = parse_vn_float(row[3])
        carbs = parse_vn_float(row[4])
        
        # Skip items with no nutritional value (pure seasonings)
        if calories == 0 and protein == 0 and fat == 0 and carbs == 0:
            continue
        
        items.append({
            'id': 10000 + i,  # Start from 10000 to avoid conflict with wger IDs
            'name': name,
            'energy': calories,
            'protein': protein,
            'fat': fat,
            'carbohydrates': carbs,
        })

# Write JSON
json_path.parent.mkdir(parents=True, exist_ok=True)
with open(json_path, 'w', encoding='utf-8') as f:
    json.dump(items, f, ensure_ascii=False, indent=2)

print(f'✅ Converted {len(items)} Vietnamese foods to {json_path}')
