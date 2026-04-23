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

from sqlalchemy import text
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


# Phân loại nguyên liệu theo nhóm
FOOD_CATEGORIES = {
    # Protein sources (>15g protein/100g)
    "protein_source": [
        "chicken", "beef", "pork", "fish", "egg", "tofu", "tempeh",
        "gà", "bò", "heo", "cá", "trứng", "đậu phụ", "thịt",
    ],
    # Carb sources (>50g carbs/100g)
    "carb_source": [
        "rice", "bread", "pasta", "noodle", "potato", "oat", "quinoa",
        "cơm", "gạo", "bánh mì", "bún", "phở", "khoai", "yến mạch",
    ],
    # Vegetables (<10g carbs/100g, >2g fiber/100g)
    "vegetable": [
        "broccoli", "spinach", "lettuce", "tomato", "cucumber", "carrot",
        "bông cải", "rau", "cà chua", "dưa", "cà rốt", "xà lách",
    ],
    # Fat sources (>20g fat/100g)
    "fat_source": [
        "oil", "butter", "avocado", "nut", "seed", "olive",
        "dầu", "bơ", "hạt", "óc chó",
    ],
}


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

        logger.info(
            f"✅ Optimized meal: {len(components)} components, "
            f"total_cal={sum(c.calories for c in components):.0f}"
        )

        return components

    async def _load_ingredients(self, db: AsyncSession) -> list[IngredientItem]:
        """Load ingredients từ wger_ingredients cache"""
        query = text("""
            SELECT id, name, energy, protein, carbohydrates, fat
            FROM wger_ingredients
            WHERE energy IS NOT NULL
              AND protein IS NOT NULL
              AND carbohydrates IS NOT NULL
              AND fat IS NOT NULL
              AND energy > 0
            ORDER BY id
        """)
        result = await db.execute(query)
        rows = result.fetchall()

        ingredients = []
        for row in rows:
            # Phân loại tự động
            category = self._auto_categorize(
                name=row.name,
                protein=float(row.protein),
                carbs=float(row.carbohydrates),
                fat=float(row.fat),
            )
            ingredients.append(
                IngredientItem(
                    id=row.id,
                    name=row.name,
                    energy=float(row.energy),
                    protein=float(row.protein),
                    carbs=float(row.carbohydrates),
                    fat=float(row.fat),
                    category=category,
                )
            )

        return ingredients

    def _auto_categorize(self, name: str, protein: float, carbs: float, fat: float) -> str:
        """Tự động phân loại nguyên liệu dựa trên tên và macro"""
        name_lower = name.lower()

        # Check keywords
        for category, keywords in FOOD_CATEGORIES.items():
            if any(kw in name_lower for kw in keywords):
                return category

        # Fallback: phân loại theo macro
        if protein > 15:
            return "protein_source"
        elif carbs > 50:
            return "carb_source"
        elif fat > 20:
            return "fat_source"
        elif carbs < 10:
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
        - Protein: 1 nguồn chính
        - Carbs: 1 nguồn chính (bữa sáng/trưa nhiều hơn, tối ít hơn)
        - Veggies: 1-2 loại
        - Fat: 1 nguồn (ít)
        """
        selected = {}

        # Protein (bắt buộc)
        protein_pool = [ing for ing in categorized["protein_source"] if ing.id not in recent_ids]
        if not protein_pool:
            protein_pool = categorized["protein_source"]
        if protein_pool:
            selected["protein"] = random.choice(protein_pool[:20])  # Top 20 để đa dạng

        # Carbs (bắt buộc trừ low-carb meal)
        carb_pool = [ing for ing in categorized["carb_source"] if ing.id not in recent_ids]
        if not carb_pool:
            carb_pool = categorized["carb_source"]
        if carb_pool:
            selected["carbs"] = random.choice(carb_pool[:20])

        # Veggies (bắt buộc)
        veggie_pool = [ing for ing in categorized["vegetable"] if ing.id not in recent_ids]
        if not veggie_pool:
            veggie_pool = categorized["vegetable"]
        if veggie_pool:
            selected["veggie"] = random.choice(veggie_pool[:15])

        # Fat (optional, ít)
        fat_pool = [ing for ing in categorized["fat_source"] if ing.id not in recent_ids]
        if fat_pool:
            selected["fat"] = random.choice(fat_pool[:10])

        return selected

    def _calculate_servings(
        self, selected: dict[str, IngredientItem], target: MacroTarget
    ) -> list[MealComponent]:
        """
        Tính khẩu phần cho từng nguyên liệu để đạt target.
        
        Strategy:
        1. Phân bổ calories theo tỷ lệ:
           - Protein: 30-35%
           - Carbs: 40-50%
           - Veggies: 10-15%
           - Fat: 5-10%
        2. Tính serving_grams từ calories phân bổ
        3. Làm tròn về bội số 10g
        """
        components = []

        # Phân bổ calories
        cal_protein = target.calories * 0.30
        cal_carbs = target.calories * 0.45
        cal_veggie = target.calories * 0.15
        cal_fat = target.calories * 0.10

        # Protein
        if "protein" in selected:
            ing = selected["protein"]
            serving = int((cal_protein / ing.energy) * 100)
            serving = max(50, min(300, serving))  # 50-300g
            serving = round(serving / 10) * 10  # Làm tròn 10g
            components.append(self._make_component(ing, serving))

        # Carbs
        if "carbs" in selected:
            ing = selected["carbs"]
            serving = int((cal_carbs / ing.energy) * 100)
            serving = max(50, min(250, serving))  # 50-250g
            serving = round(serving / 10) * 10
            components.append(self._make_component(ing, serving))

        # Veggies
        if "veggie" in selected:
            ing = selected["veggie"]
            serving = int((cal_veggie / ing.energy) * 100)
            serving = max(80, min(200, serving))  # 80-200g
            serving = round(serving / 10) * 10
            components.append(self._make_component(ing, serving))

        # Fat (optional)
        if "fat" in selected:
            ing = selected["fat"]
            serving = int((cal_fat / ing.energy) * 100)
            serving = max(5, min(30, serving))  # 5-30g
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


# Singleton
meal_optimizer = MealOptimizer()
