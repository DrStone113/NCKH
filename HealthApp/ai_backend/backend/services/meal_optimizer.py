"""
Meal Optimizer Service — Tối ưu bữa ăn bằng thuật toán.

Sử dụng Constraint Satisfaction + Greedy Algorithm để chọn nguyên liệu
đảm bảo:
- Đủ calories mục tiêu (±10%)
- Cân bằng macro (protein/carbs/fat)
- Đa dạng nhóm thực phẩm
- Không lặp lại nguyên liệu gần đây

Requirements: 1.2, 1.4, 1.5, 8.7
"""

import logging
import random
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class MacroTarget:
    """Mục tiêu macro cho 1 bữa ăn"""
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    tolerance: float = 0.15  # ±15% tolerance


@dataclass
class IngredientItem:
    """Nguyên liệu từ wger DB"""
    id: int
    name: str
    energy: float      # kcal/100g
    protein: float     # g/100g
    carbs: float       # g/100g
    fat: float         # g/100g
    category: str      # protein_source, carb_source, vegetable, fat_source


@dataclass
class MealComponent:
    """Thành phần bữa ăn đã tính khẩu phần"""
    ingredient: IngredientItem
    serving_grams: int
    calories: float
    protein: float
    carbs: float
    fat: float
    dish_name: str = ""  # Tên món ăn chứa nguyên liệu này


# Phân loại nguyên liệu theo nhóm
FOOD_CATEGORIES = {
    # Protein sources (>15g protein/100g)
    "protein_source": [
        # English
        "chicken", "beef", "pork", "fish", "egg", "tofu", "tempeh", "salmon",
        "tuna", "shrimp", "turkey", "duck", "lamb", "cod", "tilapia",
        # Vietnamese
        "gà", "bò", "heo", "cá", "trứng", "đậu phụ", "thịt", "tôm", "vịt",
        "lươn", "mực", "cua", "ghẹ", "ếch", "chả", "giò",
    ],
    # Carb sources (>50g carbs/100g)
    "carb_source": [
        # English
        "rice", "bread", "pasta", "noodle", "potato", "oat", "quinoa",
        "sweet potato", "brown rice", "white rice", "wheat", "corn",
        # Vietnamese
        "cơm", "gạo", "bánh", "bún", "phở", "khoai", "yến mạch", "mì",
        "miến", "bột", "sắn", "từ", "môn",
    ],
    # Vegetables (<10g carbs/100g, >2g fiber/100g)
    "vegetable": [
        # English
        "broccoli", "spinach", "lettuce", "tomato", "cucumber", "carrot",
        "cabbage", "kale", "bell pepper", "zucchini", "cauliflower", "celery",
        # Vietnamese
        "bông cải", "rau", "cà chua", "dưa", "cà rốt", "xà lách", "bắp cải",
    ],
    # Fat sources (>20g fat/100g)
    "fat_source": [
        # English
        "oil", "butter", "avocado", "nut", "seed", "olive", "almond",
        "peanut", "walnut", "cashew", "coconut",
        # Vietnamese
        "dầu", "bơ", "hạt", "óc chó", "đậu phộng", "điều", "mè", "dừa",
    ],
}

# Từ khóa để loại bỏ (sản phẩm chế biến sẵn, thương mại)
EXCLUDE_KEYWORDS = [
    # Thương hiệu / mã sản phẩm
    "gm,", "pf,", "oz,", "lb,", "#", "smkd", "dblsmk", "hkw", "pc",
    # Món ăn chế biến sẵn
    "pizza", "burger", "sandwich", "cake", "cookie", "pie", "muffin",
    "brownie", "donut", "croissant", "bagel", "pretzel", "cracker",
    # Đồ ăn nhanh
    "fried", "deep fried", "breaded", "battered", "crispy",
    # Đồ ngọt
    "candy", "chocolate bar", "ice cream", "gelato", "sorbet",
    "creme brulee", "pudding", "mousse", "tiramisu",
    # Đồ uống
    "soda", "juice", "smoothie", "shake", "latte", "cappuccino",
    # Đồ đóng gói
    "canned", "frozen meal", "tv dinner", "instant",
]


class MealOptimizer:
    """
    Tối ưu bữa ăn bằng thuật toán Greedy + Constraint Satisfaction.
    
    Algorithm:
    1. Lọc nguyên liệu hợp lệ từ wger DB
    2. Phân loại theo nhóm (protein/carbs/veggies/fat)
    3. Chọn 1 nguyên liệu chính từ mỗi nhóm
    4. Tính khẩu phần tối ưu để đạt macro target
    5. Điều chỉnh để đảm bảo tolerance
    """

    async def optimize_meal(
        self,
        db: AsyncSession,
        target: MacroTarget,
        meal_type: str,
        recent_ingredient_ids: list[int] = None,
        dietary_restrictions: list[str] = None,
    ) -> list[MealComponent]:
        """
        Tối ưu 1 bữa ăn.
        
        Args:
            db: Database session
            target: Mục tiêu macro
            meal_type: breakfast/lunch/dinner/snack
            recent_ingredient_ids: Danh sách ID nguyên liệu đã dùng gần đây (để tránh lặp)
            dietary_restrictions: ["vegetarian", "low_carb", "high_protein"]
        
        Returns:
            Danh sách MealComponent đã tối ưu
        """
        recent_ingredient_ids = recent_ingredient_ids or []
        dietary_restrictions = dietary_restrictions or []

        # 1. Load ingredients từ DB
        ingredients = await self._load_ingredients(db)
        logger.info(f"📦 Loaded {len(ingredients)} ingredients from wger cache")

        # 2. Lọc theo dietary restrictions
        ingredients = self._filter_by_diet(ingredients, dietary_restrictions)

        # 3. Phân loại theo nhóm
        categorized = self._categorize_ingredients(ingredients)
        logger.info(
            f"📊 Categorized: protein={len(categorized['protein_source'])}, "
            f"carbs={len(categorized['carb_source'])}, "
            f"veggies={len(categorized['vegetable'])}, "
            f"fat={len(categorized['fat_source'])}"
        )

        # 4. Chọn nguyên liệu chính từ mỗi nhóm (tránh lặp)
        selected = self._select_diverse_ingredients(
            categorized, recent_ingredient_ids, meal_type
        )

        # 5. Tính khẩu phần tối ưu
        components = self._calculate_servings(selected, target)

        # 6. Validate và điều chỉnh
        components = self._adjust_to_target(components, target)

        # 7. Đặt tên món cho từng component
        components = self._assign_dish_names(components, meal_type)

        logger.info(
            f"✅ Optimized meal: {len(components)} components, "
            f"total_cal={sum(c.calories for c in components):.0f}"
        )

        return components

    async def _load_ingredients(self, db: AsyncSession) -> list[IngredientItem]:
        """
        Load ingredients từ Vietnamese database + wger API.
        Ưu tiên Vietnamese foods trước.
        """
        ingredients = []
        food_id_counter = 90000  # fallback ID counter
        
        # 1. Load Vietnamese foods từ local JSON
        import json
        from pathlib import Path
        
        vn_foods_path = Path(__file__).parent.parent / 'data' / 'vietnamese_foods.json'
        try:
            with open(vn_foods_path, encoding='utf-8') as f:
                vn_foods = json.load(f)
            
            for food in vn_foods:
                # Tên: ưu tiên name tiếng Việt, fallback sang name_en
                name = food.get('name') or food.get('name_en', '')
                if not name:
                    continue
                
                # Lọc bỏ đồ ngọt, đồ hộp, gia vị
                if self._should_exclude_vn(name):
                    continue
                
                energy = float(food.get('energy_kcal') or food.get('energy') or 0)
                protein = float(food.get('protein') or 0)
                carbs = float(food.get('carbohydrates') or 0)
                fat = float(food.get('fat') or 0)
                
                if energy <= 0:
                    continue
                
                # Phân loại
                category = self._auto_categorize(
                    name=name,
                    protein=protein,
                    carbs=carbs,
                    fat=fat,
                )
                
                if category != "other":
                    food_id = food.get('stt') or food.get('id') or food_id_counter
                    food_id_counter += 1
                    ingredients.append(
                        IngredientItem(
                            id=food_id,
                            name=name,
                            energy=energy,
                            protein=protein,
                            carbs=carbs,
                            fat=fat,
                            category=category,
                        )
                    )
            
            logger.info(f"📦 Loaded {len(ingredients)} Vietnamese foods")
        except Exception as e:
            logger.warning(f"⚠️  Failed to load Vietnamese foods: {e}")
        
        # 2. Load wger ingredients (nếu cần thêm)
        # Chỉ load nếu Vietnamese foods không đủ
        if len(ingredients) < 50:
            from services.wger_service import wger_service
            
            wger_ingredients = await wger_service.fetch_all_ingredients(db)
            
            for wger_ing in wger_ingredients:
                if not all([
                    wger_ing.energy is not None,
                    wger_ing.protein is not None,
                    wger_ing.carbohydrates is not None,
                    wger_ing.fat is not None,
                    wger_ing.energy > 0,
                ]):
                    continue
                
                if self._should_exclude(wger_ing.name):
                    continue
                
                category = self._auto_categorize(
                    name=wger_ing.name,
                    protein=float(wger_ing.protein),
                    carbs=float(wger_ing.carbohydrates),
                    fat=float(wger_ing.fat),
                )
                
                if category == "other":
                    continue
                
                ingredients.append(
                    IngredientItem(
                        id=wger_ing.id,
                        name=wger_ing.name,
                        energy=float(wger_ing.energy),
                        protein=float(wger_ing.protein),
                        carbs=float(wger_ing.carbohydrates),
                        fat=float(wger_ing.fat),
                        category=category,
                    )
                )
            
            logger.info(f"📦 Added {len(ingredients)} total ingredients (VN + wger)")
        
        return ingredients
    
    def _should_exclude_vn(self, name: str) -> bool:
        """Lọc bỏ món không phù hợp cho meal planning"""
        name_lower = name.lower()
        
        # Đồ ngọt
        if any(kw in name_lower for kw in [
            'kẹo', 'mứt', 'đường', 'candy', 'sugar', 'sweet', 'cake',
            'cookie', 'chocolate', 'jam', 'jelly', 'syrup',
            'bánh in', 'bánh sôcôla', 'bánh thỏi', 'bánh men', 'bánh mì khô',
        ]):
            return True
        
        # Đồ hộp không phải thực phẩm chính
        if ('hộp' in name_lower or 'canned' in name_lower) and \
           not any(kw in name_lower for kw in ['cá', 'thịt', 'fish', 'meat', 'tuna', 'sardine']):
            return True
        
        # Gia vị thuần
        if any(kw in name_lower for kw in [
            'muối', 'nước mắm', 'xì dầu', 'tương', 'mắm tôm', 'cari bột',
            'salt', 'fish sauce', 'soy sauce', 'curry powder',
        ]):
            return True
        
        # Đồ uống
        if any(kw in name_lower for kw in [
            'bia', 'rượu', 'coca', 'beer', 'wine', 'alcohol', 'spirit',
            'soft drink', 'juice', 'nước giải khát',
        ]):
            return True
        
        # Nội tạng ít dùng
        if any(kw in name_lower for kw in [
            'óc', 'não', 'lưỡi', 'tai', 'mề', 'phèo', 'huyết', 'bao tử',
            'brain', 'tongue', 'ear', 'blood', 'tripe',
        ]):
            return True
        
        return False
    
    def _should_exclude(self, name: str) -> bool:
        """Kiểm tra xem ingredient có nên bị loại bỏ không"""
        name_lower = name.lower()
        
        # Loại bỏ nếu chứa từ khóa exclude
        for keyword in EXCLUDE_KEYWORDS:
            if keyword in name_lower:
                return True
        
        # Loại bỏ nếu tên quá dài (thường là mã sản phẩm)
        if len(name) > 50:
            return True
        
        # Loại bỏ nếu có nhiều số (mã sản phẩm)
        digit_count = sum(c.isdigit() for c in name)
        if digit_count > 5:
            return True
        
        return False

    def _auto_categorize(self, name: str, protein: float, carbs: float, fat: float) -> str:
        """Tự động phân loại nguyên liệu dựa trên tên và macro"""
        name_lower = name.lower()

        # Check keywords (ưu tiên tên) - chỉ match chính xác
        for category, keywords in FOOD_CATEGORIES.items():
            for kw in keywords:
                # Match chính xác từ (không phải substring)
                if f' {kw} ' in f' {name_lower} ' or name_lower.startswith(kw) or name_lower.endswith(kw):
                    return category

        # Fallback: phân loại theo macro (chặt chẽ hơn)
        # Protein source: >18g protein/100g VÀ không phải carb cao
        if protein >= 18 and carbs < 30:
            return "protein_source"
        # Carb source: >60g carbs/100g VÀ protein < 12g
        elif carbs >= 60 and protein < 12:
            return "carb_source"
        # Fat source: >35g fat/100g
        elif fat >= 35:
            return "fat_source"
        # Vegetable: carbs < 12g, protein < 4g, fat < 3g
        elif carbs < 12 and protein < 4 and fat < 3:
            return "vegetable"
        else:
            return "other"

    def _filter_by_diet(
        self, ingredients: list[IngredientItem], restrictions: list[str]
    ) -> list[IngredientItem]:
        """Lọc theo dietary restrictions"""
        if not restrictions:
            return ingredients

        filtered = ingredients[:]

        if "vegetarian" in restrictions:
            # Loại bỏ thịt, cá
            meat_keywords = ["chicken", "beef", "pork", "fish", "gà", "bò", "heo", "cá", "thịt"]
            filtered = [
                ing for ing in filtered
                if not any(kw in ing.name.lower() for kw in meat_keywords)
            ]

        if "low_carb" in restrictions:
            # Chỉ giữ nguyên liệu có carbs < 30g/100g
            filtered = [ing for ing in filtered if ing.carbs < 30]

        if "high_protein" in restrictions:
            # Ưu tiên protein > 10g/100g
            filtered = [ing for ing in filtered if ing.protein > 10]

        return filtered

    def _categorize_ingredients(
        self, ingredients: list[IngredientItem]
    ) -> dict[str, list[IngredientItem]]:
        """Nhóm nguyên liệu theo category"""
        categorized = {
            "protein_source": [],
            "carb_source": [],
            "vegetable": [],
            "fat_source": [],
            "other": [],
        }

        for ing in ingredients:
            categorized[ing.category].append(ing)

        return categorized

    def _select_diverse_ingredients(
        self,
        categorized: dict[str, list[IngredientItem]],
        recent_ids: list[int],
        meal_type: str,
    ) -> dict[str, IngredientItem]:
        """
        Chọn 1 nguyên liệu từ mỗi nhóm, tránh lặp lại.
        
        Strategy:
        - Ưu tiên ingredients có tên ngắn gọn (nguyên liệu cơ bản)
        - Protein: 1 nguồn chính
        - Carbs: 1 nguồn chính (bữa sáng/trưa nhiều hơn, tối ít hơn)
        - Veggies: 1-2 loại (optional nếu không có)
        - Fat: 1 nguồn (ít, optional)
        """
        selected = {}

        # Helper: chọn ingredient tốt nhất từ pool
        def pick_best(pool: list[IngredientItem], avoid_ids: list[int], top_n: int = 30) -> IngredientItem:
            # Lọc bỏ recent
            filtered = [ing for ing in pool if ing.id not in avoid_ids]
            if not filtered:
                filtered = pool
            
            # Sắp xếp theo độ ưu tiên:
            # 1. Tên ngắn (nguyên liệu cơ bản)
            # 2. Macro cân bằng (không quá cao/thấp)
            def score(ing: IngredientItem) -> float:
                name_score = 1.0 / (len(ing.name) + 1)  # Tên ngắn = điểm cao
                # Ưu tiên energy trong khoảng hợp lý (100-300 kcal/100g)
                energy_score = 1.0 if 100 <= ing.energy <= 300 else 0.5
                return name_score * energy_score
            
            filtered.sort(key=score, reverse=True)
            
            # Random trong top N để đa dạng
            top = filtered[:top_n]
            return random.choice(top) if top else filtered[0]

        # Protein (bắt buộc)
        if categorized["protein_source"]:
            selected["protein"] = pick_best(categorized["protein_source"], recent_ids, top_n=20)

        # Carbs (bắt buộc)
        if categorized["carb_source"]:
            selected["carbs"] = pick_best(categorized["carb_source"], recent_ids, top_n=20)

        # Veggies (optional - dataset VN thiếu rau)
        if categorized["vegetable"]:
            selected["veggie"] = pick_best(categorized["vegetable"], recent_ids, top_n=15)

        # Fat (optional)
        if categorized["fat_source"]:
            selected["fat"] = pick_best(categorized["fat_source"], recent_ids, top_n=10)

        return selected

    def _calculate_servings(
        self, selected: dict[str, IngredientItem], target: MacroTarget
    ) -> list[MealComponent]:
        """
        Tính khẩu phần cho từng nguyên liệu để đạt target.
        
        Strategy:
        1. Phân bổ calories theo tỷ lệ:
           - Protein: 35-40%
           - Carbs: 45-50%
           - Veggies: 5-10% (optional)
           - Fat: 5-10% (optional)
        2. Tính serving_grams từ calories phân bổ
        3. Làm tròn về bội số 10g
        """
        components = []

        # Tính tỷ lệ dựa trên món có sẵn
        has_veggie = "veggie" in selected
        has_fat = "fat" in selected
        
        if has_veggie and has_fat:
            cal_protein = target.calories * 0.35
            cal_carbs = target.calories * 0.45
            cal_veggie = target.calories * 0.10
            cal_fat = target.calories * 0.10
        elif has_veggie:
            cal_protein = target.calories * 0.40
            cal_carbs = target.calories * 0.50
            cal_veggie = target.calories * 0.10
            cal_fat = 0
        elif has_fat:
            cal_protein = target.calories * 0.40
            cal_carbs = target.calories * 0.50
            cal_veggie = 0
            cal_fat = target.calories * 0.10
        else:
            cal_protein = target.calories * 0.45
            cal_carbs = target.calories * 0.55
            cal_veggie = 0
            cal_fat = 0

        # Protein
        if "protein" in selected:
            ing = selected["protein"]
            serving = int((cal_protein / ing.energy) * 100)
            serving = max(80, min(250, serving))  # 80-250g
            serving = round(serving / 10) * 10  # Làm tròn 10g
            components.append(self._make_component(ing, serving))

        # Carbs
        if "carbs" in selected:
            ing = selected["carbs"]
            serving = int((cal_carbs / ing.energy) * 100)
            serving = max(80, min(200, serving))  # 80-200g
            serving = round(serving / 10) * 10
            components.append(self._make_component(ing, serving))

        # Veggies (optional)
        if "veggie" in selected:
            ing = selected["veggie"]
            serving = int((cal_veggie / ing.energy) * 100)
            serving = max(50, min(150, serving))  # 50-150g
            serving = round(serving / 10) * 10
            components.append(self._make_component(ing, serving))

        # Fat (optional)
        if "fat" in selected:
            ing = selected["fat"]
            serving = int((cal_fat / ing.energy) * 100)
            serving = max(5, min(20, serving))  # 5-20g
            serving = round(serving / 5) * 5  # Làm tròn 5g
            components.append(self._make_component(ing, serving))

        return components

    def _make_component(self, ing: IngredientItem, serving_grams: int) -> MealComponent:
        """Tạo MealComponent từ ingredient và serving"""
        ratio = serving_grams / 100.0
        return MealComponent(
            ingredient=ing,
            serving_grams=serving_grams,
            calories=ing.energy * ratio,
            protein=ing.protein * ratio,
            carbs=ing.carbs * ratio,
            fat=ing.fat * ratio,
        )

    def _adjust_to_target(
        self, components: list[MealComponent], target: MacroTarget
    ) -> list[MealComponent]:
        """
        Điều chỉnh khẩu phần để đạt target trong tolerance.
        
        Strategy:
        - Nếu tổng calories < target → tăng carbs
        - Nếu tổng calories > target → giảm carbs
        - Giữ protein và veggies ổn định
        """
        total_cal = sum(c.calories for c in components)
        diff = target.calories - total_cal

        # Nếu sai số < 10% → OK
        if abs(diff) < target.calories * 0.10:
            return components

        # Điều chỉnh carbs component
        for comp in components:
            if comp.ingredient.category == "carb_source":
                # Tính serving mới
                adjustment_ratio = 1 + (diff / total_cal)
                new_serving = int(comp.serving_grams * adjustment_ratio)
                new_serving = max(50, min(300, new_serving))
                new_serving = round(new_serving / 10) * 10

                # Update component
                ratio = new_serving / 100.0
                comp.serving_grams = new_serving
                comp.calories = comp.ingredient.energy * ratio
                comp.protein = comp.ingredient.protein * ratio
                comp.carbs = comp.ingredient.carbs * ratio
                comp.fat = comp.ingredient.fat * ratio
                break

        return components


    def _assign_dish_names(
        self, components: list[MealComponent], meal_type: str
    ) -> list[MealComponent]:
        """
        Tự động đặt tên món cho từng component dựa trên món ăn Việt Nam thực tế.
        
        Strategy:
        - Load danh sách món ăn Việt Nam từ vietnamese_dishes.json
        - Tìm món phù hợp với nguyên liệu đã chọn
        - Nếu không tìm thấy → fallback về tên nguyên liệu
        """
        import json
        from pathlib import Path
        
        # Load món ăn Việt Nam
        dishes_path = Path(__file__).parent.parent / 'data' / 'vietnamese_dishes.json'
        try:
            with open(dishes_path, encoding='utf-8') as f:
                dishes = json.load(f)
        except Exception as e:
            logger.warning(f"⚠️  Failed to load Vietnamese dishes: {e}")
            # Fallback: dùng tên nguyên liệu
            for comp in components:
                comp.dish_name = comp.ingredient.name
            return components
        
        # Tìm protein và carbs chính
        protein_comp = next((c for c in components if c.ingredient.category == "protein_source"), None)
        carbs_comp = next((c for c in components if c.ingredient.category == "carb_source"), None)
        
        if not protein_comp or not carbs_comp:
            # Không đủ nguyên liệu → dùng tên nguyên liệu
            for comp in components:
                comp.dish_name = comp.ingredient.name
            return components
        
        # Tìm món phù hợp
        best_match = None
        best_score = 0
        
        for dish in dishes:
            # Kiểm tra meal_type
            if meal_type not in dish.get("meal_types", []):
                continue
            
            # Tính điểm match dựa trên nguyên liệu
            score = 0
            dish_ingredients = dish.get("ingredients", [])
            
            # Helper: kiểm tra 2 tên có match không (xử lý tiếng Việt)
            def ingredient_match(comp_name: str, dish_ing_name: str) -> bool:
                comp_lower = comp_name.lower().strip()
                dish_lower = dish_ing_name.lower().strip()
                
                # Exact match
                if comp_lower == dish_lower:
                    return True
                
                # Partial match (chứa nhau)
                if comp_lower in dish_lower or dish_lower in comp_lower:
                    return True
                
                # Synonym match (gà = thịt gà, bò = thịt bò)
                synonyms = {
                    "gà": ["thịt gà", "gà luộc", "gà rán"],
                    "bò": ["thịt bò", "bò luộc"],
                    "heo": ["thịt heo", "thịt lợn", "heo luộc"],
                    "cá": ["cá lóc", "cá rô", "cá diêu hồng"],
                    "gạo": ["cơm", "gạo tẻ", "gạo nếp"],
                    "trứng": ["trứng gà", "trứng vịt"],
                }
                
                for key, values in synonyms.items():
                    if key in comp_lower and any(v in dish_lower for v in values):
                        return True
                    if key in dish_lower and any(v in comp_lower for v in values):
                        return True
                
                return False
            
            # Check protein match
            protein_name = protein_comp.ingredient.name
            for dish_ing in dish_ingredients:
                if dish_ing["category"] == "protein" and ingredient_match(protein_name, dish_ing["name"]):
                    score += 3
                    break
            
            # Check carbs match
            carbs_name = carbs_comp.ingredient.name
            for dish_ing in dish_ingredients:
                if dish_ing["category"] == "carb" and ingredient_match(carbs_name, dish_ing["name"]):
                    score += 3
                    break
            
            # Bonus: check veggies/fat match
            for comp in components:
                if comp.ingredient.category in ["vegetable", "fat_source"]:
                    for dish_ing in dish_ingredients:
                        if ingredient_match(comp.ingredient.name, dish_ing["name"]):
                            score += 1
                            break
            
            if score > best_score:
                best_score = score
                best_match = dish
        
        # Đặt tên món
        if best_match and best_score >= 3:  # Cần ít nhất match protein HOẶC carbs
            dish_name = best_match["name"]
            logger.info(f"🍽 Matched dish: {dish_name} (score={best_score})")
            for comp in components:
                comp.dish_name = dish_name
        else:
            # Không tìm thấy món phù hợp → dùng tên mô tả đơn giản
            if "gạo" in carbs_comp.ingredient.name.lower() or "cơm" in carbs_comp.ingredient.name.lower():
                carbs_word = "Cơm"
            elif "bún" in carbs_comp.ingredient.name.lower():
                carbs_word = "Bún"
            elif "phở" in carbs_comp.ingredient.name.lower():
                carbs_word = "Phở"
            elif "mì" in carbs_comp.ingredient.name.lower():
                carbs_word = "Mì"
            else:
                carbs_word = carbs_comp.ingredient.name
            
            if "gà" in protein_comp.ingredient.name.lower():
                protein_word = "gà"
            elif "bò" in protein_comp.ingredient.name.lower():
                protein_word = "bò"
            elif "heo" in protein_comp.ingredient.name.lower() or "lợn" in protein_comp.ingredient.name.lower():
                protein_word = "heo"
            elif "cá" in protein_comp.ingredient.name.lower():
                protein_word = "cá"
            elif "trứng" in protein_comp.ingredient.name.lower():
                protein_word = "trứng"
            else:
                protein_word = protein_comp.ingredient.name
            
            dish_name = f"{carbs_word} {protein_word}"
            logger.info(f"🍽 No exact match, using generic: {dish_name}")
            for comp in components:
                comp.dish_name = dish_name
        
        return components


# Singleton
meal_optimizer = MealOptimizer()
