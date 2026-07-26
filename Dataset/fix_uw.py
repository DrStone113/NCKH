"""
Fix lỗi chữ Ư/ư trong vietnamese_foods_Unicode.json
Pattern: '-' thay cho 'ư' do lỗi font TCVN3
"""
import json
import re
import sys
sys.stdout.reconfigure(encoding='utf-8')

INPUT  = 'Dataset/vietnamese_foods_Unicode.json'
OUTPUT = 'HealthApp/ai_backend/backend/data/vietnamese_foods.json'

def fix_uw(name: str) -> str:
    """Fix tất cả pattern '-' + dấu → ư + dấu"""
    # Thứ tự: dài trước, ngắn sau để tránh conflict
    replacements = [
        # ươ + dấu (6 dấu)
        ('-ường', 'ường'), ('-ướng', 'ướng'), ('-ưởng', 'ưởng'),
        ('-ượng', 'ượng'), ('-ưỡng', 'ưỡng'),
        ('-ờng', 'ường'), ('-ớng', 'ướng'), ('-ởng', 'ưởng'),
        ('-ợng', 'ượng'), ('-ỡng', 'ưỡng'),
        # ươi
        ('-ươi', 'ươi'), ('-ời', 'ười'), ('-ới', 'ưới'),
        # ươu
        ('-ươu', 'ươu'),
        # ươn
        ('-ươn', 'ươn'), ('-ờn', 'ườn'), ('-ớn', 'ướn'),
        # ươc
        ('-ước', 'ước'), ('-ợc', 'ược'),
        # ươt
        ('-ướt', 'ướt'), ('-ợt', 'ượt'),
        # ươm
        ('-ươm', 'ươm'), ('-ờm', 'ườm'),
        # ươp
        ('-ướp', 'ướp'), ('-ợp', 'ượp'),
        # ươ không dấu
        ('-ơi', 'ươi'), ('-ơu', 'ươu'), ('-ơn', 'ươn'),
        ('-ơng', 'ương'), ('-ơc', 'ươc'), ('-ơm', 'ươm'),
        ('-ơt', 'ươt'), ('-ơp', 'ươp'), ('-ơ ', 'ươ '),
        ('-ơ,', 'ươ,'), ('-ơ)', 'ươ)'), ('-ơ\n', 'ươ\n'),
        # ư + dấu (standalone)
        ('-ừ', 'ừ'), ('-ứ', 'ứ'), ('-ử', 'ử'), ('-ữ', 'ữ'), ('-ự', 'ự'),
        # ư không dấu trước phụ âm
        ('-ưa', 'ưa'), ('-ưc', 'ưc'), ('-ưng', 'ưng'),
        ('-ưt', 'ưt'), ('-ưm', 'ưm'), ('-ưp', 'ưp'),
        # ươ cuối từ
        ('-ơ', 'ươ'),
        # Lưng (l-ng)
        ('L-ng', 'Lưng'), ('l-ng', 'lưng'),
        # Dưa (D-a)
        ('D-a', 'Dưa'), ('d-a', 'dưa'),
        # Mướp (M-ớp)
        ('M-ớp', 'Mướp'), ('m-ớp', 'mướp'),
        # Xương (X-ơng)
        ('X-ơng', 'Xương'), ('x-ơng', 'xương'),
        # Hương (H-ơng)
        ('H-ơng', 'Hương'), ('h-ơng', 'hương'),
        # Nước (n-ớc)
        ('N-ớc', 'Nước'), ('n-ớc', 'nước'),
        # Nướng
        ('n-ớng', 'nướng'), ('N-ớng', 'Nướng'),
        # Tươi (t-ơi)
        ('T-ơi', 'Tươi'), ('t-ơi', 'tươi'),
        # Tương (t-ơng)
        ('T-ơng', 'Tương'), ('t-ơng', 'tương'),
        # Thường (th-ờng)
        ('Th-ờng', 'Thường'), ('th-ờng', 'thường'),
        # Rượu
        ('r-ợu', 'rượu'), ('R-ợu', 'Rượu'),
    ]
    
    for old, new in replacements:
        name = name.replace(old, new)
    
    # Regex fallback: còn '-' trước ơ/ờ/ớ/ở/ỡ/ợ → thêm ư
    name = re.sub(r'-([ờớởỡợ])', r'ư\1', name)
    name = re.sub(r'-([ừứửữự])', r'\1', name)
    name = re.sub(r'-ơ', 'ươ', name)
    
    return name

# Load
with open(INPUT, encoding='utf-8') as f:
    foods = json.load(f)

# Fix
fixed_count = 0
for food in foods:
    original = food.get('name', '')
    fixed = fix_uw(original)
    if fixed != original:
        food['name'] = fixed
        fixed_count += 1

print(f'Fixed {fixed_count} names')

# Verify - còn lỗi không?
remaining = []
for food in foods:
    name = food.get('name', '')
    if re.search(r'[a-zA-Z]-[a-zA-ZÀ-ỹ]', name):
        remaining.append((food['stt'], name))

if remaining:
    print(f'\n⚠️  Still {len(remaining)} names with potential issues:')
    for stt, name in remaining:
        print(f'  [{stt}] {name}')
else:
    print('✅ All names fixed!')

# Sample
print('\nSample fixed names:')
for food in foods[1:10]:
    print(f'  [{food["stt"]}] {food["name"]}')

# Save
import os
os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
with open(OUTPUT, 'w', encoding='utf-8') as f:
    json.dump(foods, f, ensure_ascii=False, indent=2)

print(f'\n✅ Saved {len(foods)} foods → {OUTPUT}')
