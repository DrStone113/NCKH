"""
Parse dinhduongvietnam.txt → vietnamese_foods_full.json
Xử lý lỗi font TCVN3/ABC → Unicode UTF-8
"""
import json
import re
from pathlib import Path

input_path  = Path(__file__).resolve().parent.parent / 'raw' / 'dinhduongvietnam.txt'
output_path = Path(__file__).resolve().parent.parent / 'raw' / 'vietnamese_foods_full.json'

# ── Bảng decode font TCVN3 (ABC) → Unicode ──────────────────────────────────
# Các ký tự Latin bị dùng thay cho chữ Việt trong font cũ
TCVN3_MAP = {
    # a
    'µ': 'à', '¸': 'á', 'Ç': 'ả', 'Ã': 'ã', 'Ạ': 'ạ',
    'Ç': 'ả', '¶': 'â', '©': 'ầ', 'Ê': 'ấ', 'È': 'ẩ',
    'Ê': 'ấ', 'Ë': 'ẫ', 'Ậ': 'ậ', 'ă': 'ă', '»': 'ằ',
    '¾': 'ắ', '¼': 'ẳ', '½': 'ẵ', 'Æ': 'ặ',
    # e
    'Ì': 'è', 'Ð': 'é', 'Î': 'ẻ', 'Ï': 'ẽ', 'Ñ': 'ẹ',
    'Ò': 'ê', 'Ó': 'ề', 'Ô': 'ế', 'Õ': 'ể', 'Ö': 'ễ', '×': 'ệ',
    # i
    'Ø': 'ì', 'Ý': 'í', 'Ú': 'ỉ', 'Û': 'ĩ', 'Ü': 'ị',
    # o
    'ß': 'ò', 'ã': 'ó', 'á': 'ỏ', 'â': 'õ', 'ä': 'ọ',
    'å': 'ô', 'ç': 'ồ', 'è': 'ố', 'é': 'ổ', 'ê': 'ỗ', 'ë': 'ộ',
    'ì': 'ơ', 'î': 'ờ', 'ï': 'ớ', 'í': 'ở', 'ð': 'ỡ', 'ñ': 'ợ',
    # u
    'ò': 'ù', 'ó': 'ú', 'ô': 'ủ', 'õ': 'ũ', 'ö': 'ụ',
    '÷': 'ư', 'ù': 'ừ', 'ú': 'ứ', 'û': 'ử', 'ü': 'ữ', 'ý': 'ự',
    # y
    'þ': 'ỳ', 'ÿ': 'ý', '\x80': 'ỷ', '\x81': 'ỹ', '\x82': 'ỵ',
    # d
    '®': 'đ',
    # Uppercase
    '¡': 'À', '¢': 'Á', '£': 'Ả', '¤': 'Ã', '¥': 'Ạ',
    '¦': 'Â', '\x87': 'Ầ', '\x88': 'Ấ', '\x89': 'Ẩ', '\x8a': 'Ẫ', '\x8b': 'Ậ',
    '\x8c': 'Ă', '\x8d': 'Ằ', '\x8e': 'Ắ', '\x8f': 'Ẳ', '\x90': 'Ẵ', '\x91': 'Ặ',
    '\x92': 'È', '\x93': 'É', '\x94': 'Ẻ', '\x95': 'Ẽ', '\x96': 'Ẹ',
    '\x97': 'Ê', '\x98': 'Ề', '\x99': 'Ế', '\x9a': 'Ể', '\x9b': 'Ễ', '\x9c': 'Ệ',
    '\x9d': 'Ì', '\x9e': 'Í', '\x9f': 'Ỉ', '\xa0': 'Ĩ', '\xa1': 'Ị',
    '§': 'Ò', '¨': 'Ó', '\xa4': 'Ỏ', '\xa5': 'Õ', '\xa6': 'Ọ',
    '\xa7': 'Ô', '\xa8': 'Ồ', '\xa9': 'Ố', '\xaa': 'Ổ', '\xab': 'Ỗ', '\xac': 'Ộ',
    '\xad': 'Ơ', '\xae': 'Ờ', '\xaf': 'Ớ', '\xb0': 'Ở', '\xb1': 'Ỡ', '\xb2': 'Ợ',
    '\xb3': 'Ù', '\xb4': 'Ú', '\xb5': 'Ủ', '\xb6': 'Ũ', '\xb7': 'Ụ',
    '\xb8': 'Ư', '\xb9': 'Ừ', '\xba': 'Ứ', '\xbb': 'Ử', '\xbc': 'Ữ', '\xbd': 'Ự',
    '\xbe': 'Ỳ', '\xbf': 'Ý', '\xc0': 'Ỷ', '\xc1': 'Ỹ', '\xc2': 'Ỵ',
    '\xc3': 'Đ',
    # Common wrong chars seen in output
    'ª': 'ấ', '«': 'ầ', '¬': 'ẩ',
    'Ð': 'Đ', '×': 'ệ',
    # Specific patterns seen
    'G¹o': 'Gạo', 'nÕp': 'nếp', 'c¸i': 'cái',
    'tÎ': 'tẻ', 'løt': 'lứt',
    'B¸nh': 'Bánh', 'phë': 'phở', 'bao': 'bao',
    'Bón': 'Bún', 'mú': 'mì',
}

def decode_tcvn3(text: str) -> str:
    """Thử decode font TCVN3 → Unicode"""
    # Thử decode từng ký tự
    result = []
    i = 0
    while i < len(text):
        c = text[i]
        if c in TCVN3_MAP:
            result.append(TCVN3_MAP[c])
        else:
            result.append(c)
        i += 1
    return ''.join(result)

# ── Đọc file ─────────────────────────────────────────────────────────────────
with open(input_path, encoding='utf-8') as f:
    lines = [l.rstrip('\n') for l in f.readlines()]

print(f"Total lines: {len(lines)}")

def parse_float(s):
    if not s or s.strip() in ('-', '', '0.0'):
        return 0.0
    s = s.strip().replace(',', '.')
    s = re.sub(r'[^\d.]', '', s)
    try:
        return round(float(s), 2)
    except:
        return 0.0

# ── Tìm tất cả food entries ──────────────────────────────────────────────────
entry_starts = []
for i, line in enumerate(lines):
    if 'Vietnamese):' in line:
        entry_starts.append(i)

print(f"Found {len(entry_starts)} entries")

# ── Parse từng entry ─────────────────────────────────────────────────────────
foods = []
food_id = 20000

for idx, start in enumerate(entry_starts):
    end = entry_starts[idx+1] if idx+1 < len(entry_starts) else min(start+200, len(lines))
    window = lines[start:end]

    # --- Tên tiếng Anh (không bị lỗi font) ---
    en_name = ''
    for j, wl in enumerate(window):
        if 'English):' in wl:
            # Tên ở dòng tiếp theo (bỏ qua dòng trắng)
            for k in range(j+1, min(j+5, len(window))):
                candidate = window[k].strip()
                if candidate and not candidate.startswith('M·') and not candidate.startswith('Th'):
                    en_name = candidate
                    break
            break

    # --- Tên tiếng Việt (thử decode) ---
    vn_name = ''
    # Tên ở dòng +2 sau "Vietnamese):"
    for k in range(1, 5):
        if k < len(window):
            candidate = window[k].strip()
            if candidate and not candidate.startswith('STT') \
               and not candidate.startswith('M·') \
               and not candidate.startswith('Tªn') \
               and not candidate.startswith('Th') \
               and len(candidate) > 1:
                vn_name = decode_tcvn3(candidate)
                break

    # Dùng tên tiếng Anh làm display (tên Việt bị lỗi font)
    display_name = en_name if en_name else vn_name
    if not display_name:
        continue

    # --- Energy ---
    energy = 0.0
    for j, wl in enumerate(window):
        if 'KCal' in wl or wl.strip() == 'KCal':
            # Số ở dòng tiếp theo
            for k in range(j+1, min(j+5, len(window))):
                v = parse_float(window[k])
                if v and 5 <= v <= 1000:
                    energy = v
                    break
            if energy:
                break

    # --- Protein ---
    protein = 0.0
    for j, wl in enumerate(window):
        if wl.strip() == 'Protein':
            for k in range(j+1, min(j+8, len(window))):
                if window[k].strip() == 'g':
                    for m in range(k+1, min(k+4, len(window))):
                        v = parse_float(window[m])
                        if v is not None and window[m].strip() not in ('', '-'):
                            protein = v
                            break
                    break
            break

    # --- Fat ---
    fat = 0.0
    for j, wl in enumerate(window):
        if 'Lipid (Fat)' in wl or wl.strip() == 'Lipid':
            for k in range(j+1, min(j+8, len(window))):
                if window[k].strip() == 'g':
                    for m in range(k+1, min(k+4, len(window))):
                        v = parse_float(window[m])
                        if v is not None and window[m].strip() not in ('', '-'):
                            fat = v
                            break
                    break
            break

    # --- Carbs ---
    carbs = 0.0
    for j, wl in enumerate(window):
        if 'Glucid' in wl:
            for k in range(j+1, min(j+8, len(window))):
                if window[k].strip() == 'g':
                    for m in range(k+1, min(k+4, len(window))):
                        v = parse_float(window[m])
                        if v is not None and window[m].strip() not in ('', '-'):
                            carbs = v
                            break
                    break
            break

    if energy > 0:
        foods.append({
            'id': food_id,
            'name': display_name,
            'name_en': en_name,
            'energy': energy,
            'protein': protein,
            'fat': fat,
            'carbohydrates': carbs,
        })
        food_id += 1

# Loại bỏ duplicate
seen = set()
unique = []
for f in foods:
    key = f['name_en'] or f['name']
    if key not in seen:
        seen.add(key)
        unique.append(f)

print(f'\n✅ Parsed {len(unique)} unique foods')
print('\nSample (first 20):')
for f in unique[:20]:
    print(f"  [{f['name']}] ({f['name_en']}): {f['energy']} kcal | P:{f['protein']}g F:{f['fat']}g C:{f['carbohydrates']}g")

with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(unique, f, ensure_ascii=False, indent=2)

print(f'\n✅ Saved to {output_path}')
