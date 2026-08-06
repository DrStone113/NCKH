"""
Extract toàn bộ dữ liệu dinh dưỡng từ VTN_FCT_2007.pdf
526 thực phẩm × 84 chất dinh dưỡng
"""
import json
import re
import sys
from pathlib import Path

import pdfplumber

sys.stdout.reconfigure(encoding='utf-8')

PDF_PATH = Path(__file__).resolve().parent.parent / 'raw' / 'VTN_FCT_2007.pdf'
OUT_PATH = Path(__file__).resolve().parent.parent / 'raw' / 'vietnamese_foods_full.json'

# ── Nutrient name → key ──────────────────────────────────────────────────────
NUTRIENT_MAP = {
    'nước': 'water',
    'năng lượng': 'energy_kcal', 'energy': 'energy_kcal',
    'kcal': 'energy_kcal',
    'kj': 'energy_kj',
    'protein': 'protein',
    'lipid': 'fat', 'fat': 'fat',
    'glucid': 'carbohydrates', 'carbohydrate': 'carbohydrates',
    'celluloza': 'fiber', 'fiber': 'fiber',
    'tro': 'ash', 'ash': 'ash',
    'đường tổng số': 'sugar_total', 'sugar': 'sugar_total',
    'galactoza': 'galactose',
    'maltoza': 'maltose',
    'lactoza': 'lactose',
    'fructoza': 'fructose',
    'glucoza': 'glucose',
    'sacaroza': 'sucrose',
    'calci': 'calcium', 'calcium': 'calcium',
    'sắt': 'iron', 'iron': 'iron',
    'magiê': 'magnesium', 'magnesium': 'magnesium',
    'mangan': 'manganese', 'manganese': 'manganese',
    'phospho': 'phosphorus', 'phosphorous': 'phosphorus',
    'kali': 'potassium', 'potassium': 'potassium',
    'natri': 'sodium', 'sodium': 'sodium',
    'kẽm': 'zinc', 'zinc': 'zinc',
    'đồng': 'copper', 'copper': 'copper',
    'selen': 'selenium', 'selenium': 'selenium',
    'vitamin c': 'vitamin_c', 'ascorbic': 'vitamin_c',
    'vitamin b1': 'vitamin_b1', 'thiamine': 'vitamin_b1',
    'vitamin b2': 'vitamin_b2', 'riboflavin': 'vitamin_b2',
    'vitamin pp': 'niacin', 'niacin': 'niacin',
    'vitamin b5': 'vitamin_b5', 'pantothenic': 'vitamin_b5',
    'vitamin b6': 'vitamin_b6', 'pyridoxine': 'vitamin_b6',
    'folat': 'folate', 'folate': 'folate',
    'vitamin b9': 'folic_acid', 'folic acid': 'folic_acid',
    'vitamin h': 'biotin', 'biotin': 'biotin',
    'vitamin b12': 'vitamin_b12', 'cyanocobalamine': 'vitamin_b12',
    'vitamin a': 'vitamin_a', 'retinol': 'vitamin_a',
    'vitamin d': 'vitamin_d', 'calciferol': 'vitamin_d',
    'vitamin e': 'vitamin_e', 'alpha-tocopherol': 'vitamin_e',
    'vitamin k': 'vitamin_k', 'phylloquinone': 'vitamin_k',
    'beta-caroten': 'beta_carotene',
    'alpha-caroten': 'alpha_carotene',
    'beta-cryptoxanthin': 'beta_cryptoxanthin',
    'lycopen': 'lycopene', 'lycopene': 'lycopene',
    'lutein + zeaxanthin': 'lutein_zeaxanthin', 'lutein': 'lutein_zeaxanthin',
    'purin': 'purin',
    'tổng số isoflavon': 'isoflavone_total', 'total isoflavone': 'isoflavone_total',
    'daidzein': 'daidzein',
    'genistein': 'genistein',
    'glycetin': 'glycetin',
    'tổng số acid béo no': 'sfa_total', 'total saturated': 'sfa_total',
    'palmitic': 'palmitic',
    'margaric': 'margaric',
    'stearic': 'stearic',
    'arachidic': 'arachidic',
    'behenic': 'behenic',
    'lignoceric': 'lignoceric',
    'ts acid béo không no 1': 'mufa_total', 'monounsaturated': 'mufa_total',
    'myristoleic': 'myristoleic',
    'palmitoleic': 'palmitoleic',
    'oleic': 'oleic',
    'ts acid béo không no nhiều': 'pufa_total', 'polyunsaturated': 'pufa_total',
    'linoleic': 'linoleic',
    'linolenic': 'linolenic',
    'arachidonic': 'arachidonic',
    'eicosapentaenoic': 'epa',
    'docosahexaenoic': 'dha',
    'ts acid béo trans': 'trans_fat', 'trans fatty': 'trans_fat',
    'cholesterol': 'cholesterol',
    'phytosterol': 'phytosterol',
    'lysin': 'lysine',
    'methionin': 'methionine',
    'tryptophan': 'tryptophan',
    'phenylalanin': 'phenylalanine',
    'threonin': 'threonine',
    'valin': 'valine',
    'leucin': 'leucine',
    'isoleucin': 'isoleucine',
    'arginin': 'arginine',
    'histidin': 'histidine',
    'cystin': 'cystine',
    'tyrosin': 'tyrosine',
    'alanin': 'alanine',
    'acid aspartic': 'aspartic_acid',
    'acid glutamic': 'glutamic_acid',
    'glycin': 'glycine',
    'prolin': 'proline',
    'serin': 'serine',
}

def find_key(text: str):
    if not text:
        return None
    t = text.lower().strip()
    # Bỏ phần trong ngoặc đơn
    t_clean = re.sub(r'\(.*?\)', '', t).strip()
    # Exact match
    for k, v in NUTRIENT_MAP.items():
        if t_clean == k or t == k:
            return v
    # Starts with
    for k, v in NUTRIENT_MAP.items():
        if t_clean.startswith(k) or t.startswith(k):
            return v
    return None

def parse_val(s: str):
    """Parse số, trả về None nếu '-' hoặc không hợp lệ"""
    if not s:
        return None
    s = str(s).strip()
    if s in ('-', '', 'None', 'null'):
        return None
    # Xử lý số bị double do lỗi PDF: "1177" khi thực ra là "17"
    # Detect bằng cách kiểm tra nếu chuỗi số là palindrome double
    s_clean = re.sub(r'[^\d.]', '', s.replace(',', '.'))
    if not s_clean:
        return None
    # Fix double-digit bug: "00.220000" → "0.2200", "1177" → "17"
    # Nếu chuỗi số có dạng XXYY (lặp đôi), lấy nửa đầu
    if len(s_clean) >= 4 and '.' not in s_clean:
        half = len(s_clean) // 2
        if s_clean[:half] == s_clean[half:]:
            s_clean = s_clean[:half]
    try:
        v = float(s_clean)
        return round(v, 4) if v != 0 else 0.0
    except:
        return None

def parse_cell_pair(name_cell: str, unit_cell: str, value_cell: str) -> dict:
    """
    Parse 1 cặp cell (nutrient names | units | values) → dict
    Align theo units vì Energy có 2 units (KCal + KJ)
    """
    result = {}
    if not name_cell or not value_cell:
        return result

    names  = [n.strip() for n in str(name_cell).split('\n') if n.strip()]
    units  = [u.strip() for u in str(unit_cell or '').split('\n') if u.strip()]
    values = [v.strip() for v in str(value_cell).split('\n') if v.strip()]

    # Lọc bỏ dòng không phải nutrient name
    valid_names = []
    for name in names:
        if name.startswith('(') or len(name) < 2:
            continue
        if re.search(r'(.)\1{3,}', name):  # double chars bug
            continue
        valid_names.append(name)

    # Align: dùng units để map value → nutrient
    # Mỗi unit tương ứng 1 value; Energy có 2 units (KCal, KJ)
    # Tạo list (nutrient_key, value) theo thứ tự units
    name_idx = 0
    current_key = None

    for u_idx, unit in enumerate(units):
        if u_idx >= len(values):
            break
        val = parse_val(values[u_idx])

        # KJ là unit thứ 2 của Energy → lưu vào energy_kj
        if unit == 'KJ':
            if val is not None:
                result['energy_kj'] = val
            continue

        # Advance name_idx để lấy nutrient name tiếp theo
        while name_idx < len(valid_names):
            key = find_key(valid_names[name_idx])
            name_idx += 1
            if key:
                current_key = key
                break

        if current_key and val is not None and current_key not in result:
            result[current_key] = val

    return result

def parse_page(page) -> dict | None:
    """Parse 1 trang PDF → food dict"""
    text = page.extract_text() or ''
    lines = [l.strip() for l in text.split('\n')]

    # Header info
    vn_name = ''
    en_name = ''
    stt = None
    ma_so = None
    thai_bo = None

    for line in lines[:12]:
        if 'Vietnamese):' in line:
            rest = line.split('Vietnamese):')[-1].strip()
            rest = re.sub(r'\s+STT:.*$', '', rest).strip()
            vn_name = rest
        if 'English):' in line:
            rest = line.split('English):')[-1].strip()
            rest = re.sub(r'\s+M·.*$', '', rest).strip()
            en_name = rest
        m = re.search(r'STT:\s*(\d+)', line)
        if m:
            stt = int(m.group(1))
        m = re.search(r'M·\s*sè:\s*(\d+)', line)
        if m:
            ma_so = int(m.group(1))
        m = re.search(r'Th¶i\s*bá\s*\(%\):\s*([\d.]+)', line)
        if m:
            thai_bo = float(m.group(1))

    if not en_name and not vn_name:
        return None

    # Parse bảng
    nutrients = {}
    tables = page.extract_tables()
    for table in tables:
        for row in table:
            if not row:
                continue
            # Cột trái: col 0 (names), col 1 (units), col 2 (values)
            if len(row) >= 3:
                left = parse_cell_pair(row[0], row[1], row[2])
                nutrients.update({k: v for k, v in left.items() if k not in nutrients})
            # Cột phải: col 4 (names), col 5 (units), col 6 (values)
            if len(row) >= 7:
                right = parse_cell_pair(row[4], row[5], row[6])
                nutrients.update({k: v for k, v in right.items() if k not in nutrients})

    # Phải có energy mới là trang data
    if 'energy_kcal' not in nutrients:
        return None

    return {
        'stt': stt,
        'ma_so': ma_so,
        'name': vn_name,
        'name_en': en_name,
        'thai_bo_pct': thai_bo,
        **nutrients,
    }

# ── Main ─────────────────────────────────────────────────────────────────────
print(f"Opening {PDF_PATH}...")
foods = []
errors = []

with pdfplumber.open(PDF_PATH) as pdf:
    total = len(pdf.pages)
    print(f"Total pages: {total}")

    for i, page in enumerate(pdf.pages):
        try:
            result = parse_page(page)
            if result:
                foods.append(result)
                if len(foods) % 50 == 0:
                    print(f"  [{i+1}/{total}] Parsed {len(foods)} foods...")
        except Exception as e:
            errors.append({'page': i+1, 'error': str(e)})

# Dedup theo stt
seen = set()
unique = []
for f in foods:
    key = f.get('stt') or f.get('name_en') or f.get('name')
    if key not in seen:
        seen.add(key)
        unique.append(f)

unique.sort(key=lambda x: x.get('stt') or 9999)

print(f"\n✅ Parsed {len(unique)} unique foods ({len(errors)} errors)")

# Verify sample
print("\nSample (10 foods):")
for f in unique[:10]:
    print(f"  [{f.get('stt')}] {f.get('name_en')}")
    print(f"       E:{f.get('energy_kcal')} kcal | P:{f.get('protein')}g | F:{f.get('fat')}g | C:{f.get('carbohydrates')}g | Fiber:{f.get('fiber')}g")

# Fields summary
all_keys = set()
for f in unique:
    all_keys.update(f.keys())
print(f"\nTotal fields: {len(all_keys)}")

# Save
with open(OUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(unique, f, ensure_ascii=False, indent=2)

print(f"\n✅ Saved {len(unique)} foods → {OUT_PATH}")
if errors:
    print(f"⚠️  {len(errors)} errors: {errors[:3]}")
