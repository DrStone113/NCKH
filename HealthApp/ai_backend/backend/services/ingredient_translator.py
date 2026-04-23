"""
Ingredient name translator - Dịch tên nguyên liệu sang tiếng Việt
"""

# Mapping tên tiếng Anh → tiếng Việt
INGREDIENT_NAMES_VN = {
    # Protein
    "chicken": "Thịt gà",
    "chicken breast": "Ức gà",
    "beef": "Thịt bò",
    "pork": "Thịt heo",
    "fish": "Cá",
    "salmon": "Cá hồi",
    "tuna": "Cá ngừ",
    "shrimp": "Tôm",
    "egg": "Trứng",
    "eggs": "Trứng",
    "tofu": "Đậu phụ",
    "tempeh": "Tempeh",
    "turkey": "Gà tây",
    
    # Carbs
    "rice": "Cơm",
    "white rice": "Cơm trắng",
    "brown rice": "Cơm gạo lứt",
    "bread": "Bánh mì",
    "pasta": "Mì ý",
    "noodle": "Mì",
    "noodles": "Mì",
    "potato": "Khoai tây",
    "potatoes": "Khoai tây",
    "sweet potato": "Khoai lang",
    "oat": "Yến mạch",
    "oats": "Yến mạch",
    "quinoa": "Quinoa",
    
    # Vegetables
    "broccoli": "Bông cải xanh",
    "spinach": "Rau bina",
    "lettuce": "Xà lách",
    "tomato": "Cà chua",
    "tomatoes": "Cà chua",
    "cucumber": "Dưa chuột",
    "carrot": "Cà rốt",
    "carrots": "Cà rốt",
    "cabbage": "Bắp cải",
    "kale": "Cải xoăn",
    "bell pepper": "Ớt chuông",
    "zucchini": "Bí ngòi",
    "cauliflower": "Súp lơ",
    "celery": "Cần tây",
    
    # Fat
    "oil": "Dầu ăn",
    "olive oil": "Dầu ô liu",
    "butter": "Bơ",
    "avocado": "Bơ (quả)",
    "almond": "Hạnh nhân",
    "almonds": "Hạnh nhân",
    "peanut": "Đậu phộng",
    "peanuts": "Đậu phộng",
    "walnut": "Óc chó",
    "walnuts": "Óc chó",
    "cashew": "Hạt điều",
    "cashews": "Hạt điều",
}


def translate_ingredient_name(english_name: str) -> str:
    """
    Dịch tên nguyên liệu sang tiếng Việt.
    Nếu không có trong dictionary, giữ nguyên tên tiếng Anh.
    """
    # Normalize
    name_lower = english_name.lower().strip()
    
    # Exact match
    if name_lower in INGREDIENT_NAMES_VN:
        return INGREDIENT_NAMES_VN[name_lower]
    
    # Partial match (chứa từ khóa)
    for en_key, vn_name in INGREDIENT_NAMES_VN.items():
        if en_key in name_lower:
            return vn_name
    
    # Fallback: capitalize first letter
    return english_name.title()


def format_ingredient_display(name: str, serving_grams: int, calories: float, 
                               protein: float, carbs: float, fat: float) -> str:
    """
    Format ingredient thành chuỗi hiển thị đẹp.
    
    Example:
        "Ức gà: 150g (248 kcal, P:37g, C:0g, F:10g)"
    """
    vn_name = translate_ingredient_name(name)
    return (
        f"{vn_name}: {serving_grams}g "
        f"({calories:.0f} kcal, P:{protein:.0f}g, C:{carbs:.0f}g, F:{fat:.0f}g)"
    )
