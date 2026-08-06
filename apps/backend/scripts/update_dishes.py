"""
Script để cập nhật vietnamese_dishes.json với tên nguyên liệu chính xác từ vietnamese_foods.json
"""
import json
from pathlib import Path

# Mapping tên nguyên liệu generic → tên chính xác trong vietnamese_foods.json
INGREDIENT_MAPPING = {
    # Gạo/Cơm
    "Gạo tẻ": "Gạo tẻ máy",
    "Gạo nếp": "Gạo nếp cái",
    "Gạo lức": "Gạo tẻ máy",  # Không có gạo lức trong DB, dùng gạo tẻ
    "Gạo tấm": "Gạo tẻ máy",  # Gạo tấm là gạo tẻ vụn
    "Cơm nguội": "Gạo tẻ máy",
    
    # Thịt gà
    "Thịt gà": "Thịt gà ta",
    "Đùi gà": "Thịt gà ta",
    "Ức gà": "Thịt gà ta",
    "Cánh gà": "Thịt gà ta",
    
    # Thịt heo/lợn
    "Thịt heo": "Thịt lợn nạc",
    "Thịt heo nạc": "Thịt lợn nạc",
    "Thịt heo nướng": "Thịt lợn nạc",
    "Thịt ba chỉ": "Thịt lợn nửa nạc, nửa mỡ",
    "Thịt bằm": "Thịt lợn nạc",
    "Sườn heo": "Sườn lợn",
    "Giò heo": "Giò thủ lợn",
    "Lòng heo": "Lòng lợn (ruột non)",
    "Chân giò lợn": "Chân giò lợn",
    
    # Thịt bò
    "Thịt bò": "Thịt bò loại I",
    
    # Cá
    "Cá": "Cá rô phi",
    "Cá lóc": "Cá rô phi",
    "Cá basa": "Cá rô phi",
    "Cá tuyết": "Cá rô phi",
    
    # Hải sản
    "Tôm": "Tôm biển",
    "Cua": "Cua bể",
    "Sò điệp": "Tôm biển",  # Không có sò điệp trong DB, dùng tôm thay thế
    
    # Trứng
    "Trứng gà": "Trứng gà",
    "Trứng vịt": "Trứng vịt",
    "Trứng": "Trứng gà",
    
    # Rau củ
    "Rau thơm": "Rau muống",
    "Rau sống": "Rau muống",
    "Rau xanh": "Rau muống",
    "Rau cải": "Cải xanh",
    "Rau muống": "Rau muống",
    "Cà chua": "Cà chua",
    "Cà rốt": "Cà rốt (củ đỏ, vàng)",
    "Củ cải": "Củ cải trắng",
    "Củ cải trắng": "Củ cải trắng",
    "Hành tây": "Hành tây",
    "Khoai tây": "Khoai tây",
    "Khoai mỡ": "Khoai lang",
    "Bông cải xanh": "Cải xanh",
    "Nấm": "Nấm rơm",
    "Gừng": "Gừng tươi",
    "Ớt": "ớt đỏ to",
    "Cải chua": "Cải bắp",
    
    # Đậu/Hạt
    "Đậu xanh": "Đậu xanh (đậu tắt)",
    "Đậu nành": "Đậu tương (đậu nành)",
    "Đậu phộng": "Lạc",
    "Đậu đũa": "Đậu đũa",
    "Đậu bắp": "Đậu đũa",
    "Hạt dẻ": "Hạt dẻ tươi",
    "Đậu đen": "Đậu đen (hạt)",
    
    # Bún/Mì/Phở
    "Bún": "Bún",
    "Bánh phở": "Bánh phở",
    "Mì": "Bún",  # Không có mì trong DB, dùng bún thay thế
    "Mì Quảng": "Bánh phở",
    "Mì cao lầu": "Bún",  # Không có mì trong DB, dùng bún thay thế
    "Hủ tiếu": "Bún",
    "Bánh cuốn": "Bánh phở",
    "Bánh mì": "Bánh mỳ",
    
    # Dầu/Mỡ
    "Dầu ăn": "Dầu thảo mộc (Lạc, vừng, cám...)",
    "Dầu mè": "Dầu thảo mộc (Lạc, vừng, cám...)",
    "Bơ": "Bơ thực vật",
    "Nước dừa": "Cùi dừa già",
    "Pate": "Thịt lợn nạc",
    
    # Khác
    "Bắp": "Ngô bắp tươi",
    "Ngô": "Ngô bắp tươi",
    "Yến mạch": "Yến mạch",
    "Lạp xưởng": "Thịt lợn nạc",
    "Bột chiên": "Bột mì",
}

def main():
    # Đường dẫn file
    base_dir = Path(__file__).parent.parent / 'data'
    foods_file = base_dir / 'vietnamese_foods.json'
    dishes_file = base_dir / 'vietnamese_dishes.json'
    
    # Load vietnamese_foods.json
    with open(foods_file, encoding='utf-8') as f:
        foods = json.load(f)
    
    # Tạo dict tên → food item
    foods_dict = {food['name']: food for food in foods}
    
    # Load vietnamese_dishes.json
    with open(dishes_file, encoding='utf-8') as f:
        dishes = json.load(f)
    
    # Cập nhật tên nguyên liệu
    updated_count = 0
    for dish in dishes:
        for ingredient in dish['ingredients']:
            old_name = ingredient['name']
            
            # Tìm tên mới từ mapping
            if old_name in INGREDIENT_MAPPING:
                new_name = INGREDIENT_MAPPING[old_name]
                
                # Kiểm tra tên mới có trong vietnamese_foods không
                if new_name in foods_dict:
                    ingredient['name'] = new_name
                    updated_count += 1
                    print(f"✓ {dish['name']}: {old_name} → {new_name}")
                else:
                    print(f"⚠ {dish['name']}: {old_name} → {new_name} (KHÔNG TÌM THẤY)")
            else:
                # Kiểm tra tên cũ có trong vietnamese_foods không
                if old_name not in foods_dict:
                    print(f"✗ {dish['name']}: {old_name} (KHÔNG CÓ MAPPING)")
    
    # Lưu lại file
    with open(dishes_file, 'w', encoding='utf-8') as f:
        json.dump(dishes, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Đã cập nhật {updated_count} nguyên liệu")
    print(f"📁 File đã lưu: {dishes_file}")

if __name__ == '__main__':
    main()
