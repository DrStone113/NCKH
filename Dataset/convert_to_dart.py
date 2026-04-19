"""
Convert food_data.csv → Dart FoodItem list cho nutrition_provider.dart
"""
import csv
import re
import json

# Map category CSV → category hiển thị
CATEGORY_MAP = {
    "Ngũ cốc và sản phẩm chế biến từ chúng": "Ngũ cốc & Tinh bột",
    "Khoai củ và các sản phẩm chế biến từ chúng": "Khoai củ",
    "Hạt, quả giàu protein, chất béo và chế phẩm": "Hạt & Đậu",
    "THỊT VÀ SẢN PHẨM CHẾ BIẾN": "Thịt",
    "THỦY SẢN VÀ SẢN PHẨM CHẾ BIẾN": "Hải sản & Thủy sản",
    "TRỨNG VÀ SẢN PHẨM CHẾ BIẾN": "Trứng",
    "SỮA VÀ SẢN PHẨM CHẾ BIẾN": "Sữa & Chế phẩm",
    "ĐỒ HỘP": "Đồ hộp",
    "ĐỒ NGỌT (ĐƯỜNG, BÁNH, MỨT, KẸO)": "Bánh & Kẹo",
    "GIA VỊ, NƯỚC CHẤM": "Gia vị",
    "NƯỚC GIẢI KHÁT": "Đồ uống",
}

def parse_vn_float(s):
    """Parse số kiểu Việt Nam: '8,6' → 8.6"""
    if not s or s.strip() in ('', '0', '0,0', '0,00'):
        return 0.0
    s = s.strip().strip('"').replace(',', '.')
    # Bỏ ký tự lạ
    s = re.sub(r'[^\d.]', '', s)
    try:
        return round(float(s), 2)
    except:
        return 0.0

def escape_dart(s):
    return s.replace("'", "\\'").replace('"', '\\"')

items = []
seen_names = set()

with open('food_data.csv', encoding='utf-8-sig') as f:
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
        protein  = parse_vn_float(row[2])
        fat      = parse_vn_float(row[3])
        carbs    = parse_vn_float(row[4])
        fiber    = parse_vn_float(row[5])
        category_raw = row[-1].strip().strip('"') if len(row) > 15 else ''
        category = CATEGORY_MAP.get(category_raw, category_raw or 'Khác')

        # Bỏ qua món có calories = 0 và không có macro nào (gia vị thuần)
        if calories == 0 and protein == 0 and fat == 0 and carbs == 0:
            continue

        items.append({
            'id': f'vn{i+1:03d}',
            'name': name,
            'calories': calories,
            'protein': protein,
            'fat': fat,
            'carbs': carbs,
            'fiber': fiber,
            'category': category,
        })

print(f"✅ Parsed {len(items)} food items")

# Generate Dart code
lines = []
lines.append("  // === CƠ SỞ DỮ LIỆU THỰC PHẨM VIỆT NAM (Bảng thành phần thực phẩm VN) ===")
lines.append("  static final List<FoodItem> vietnameseFoodDatabase = [")

for item in items:
    name_escaped = escape_dart(item['name'])
    lines.append(
        f"    FoodItem(id: '{item['id']}', name: '{name_escaped}', "
        f"caloriesPer100g: {item['calories']}, "
        f"proteinPer100g: {item['protein']}, "
        f"fatPer100g: {item['fat']}, "
        f"carbsPer100g: {item['carbs']}, "
        f"category: '{item['category']}'),"
    )

lines.append("  ];")

dart_code = '\n'.join(lines)

with open('food_database.dart.txt', 'w', encoding='utf-8') as f:
    f.write(dart_code)

print(f"✅ Written to food_database.dart.txt")
print(f"   Categories: {set(i['category'] for i in items)}")
