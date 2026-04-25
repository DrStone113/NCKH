"""
Dish Optimizer Service — Tối ưu bữa ăn bằng cách chọn món ăn Việt Nam thực tế.

Thay vì chọn nguyên liệu riêng lẻ, service này chọn món ăn hoàn chỉnh
từ database vietnamese_dishes.json và tính toán khẩu phần phù hợp.

Requirements: 1.2, 1.4, 1.5, 8.7
"""

import logging
import random
import json
from dataclasses import dataclass
from pathlib import Path
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
class DishComponent:
    """Thành phần món ăn (nguyên liệu) với khẩu phần đã tính"""
    name: str  # Tên nguyên liệu
    serving_grams: int  # Khẩu phần (gram)
    calories: float  # Calories thực tế
    protein: float  # Protein (g)
    carbs: float  # Carbs (g)
    fat: float  # Fat (g)
    energy_per_100g: float  # Calories/100g (để tính toán)


@dataclass
class Dish:
    """Món ăn hoàn chỉnh"""
    id: int
    name: str
    meal_types: list[str]
    components: list[DishComponent]
    total_calories: float
    total_protein: float
    total_carbs: float
    total_fat: float


class DishOptimizer:
    """
    Tối ưu bữa ăn bằng cách chọn món ăn Việt Nam thực tế.
    
    Algorithm:
    1. Load món ăn từ vietnamese_dishes.json
    2. Load thông tin dinh dưỡng từ vietnamese_foods.json
    3. Lọc món phù hợp với meal_type
    4. Chọn món có calories gần với target nhất
    5. Scale khẩu phần để đạt target chính xác
    """

    def __init__(self):
        self.dishes = []
        self.foods_dict = {}
        self._load_data()

    def _load_data(self):
        """Load dữ liệu món ăn và thực phẩm"""
        base_dir = Path(__file__).parent.parent / 'data'
        
        # Load vietnamese_foods.json
        foods_file = base_dir / 'vietnamese_foods.json'
        try:
            with open(foods_file, encoding='utf-8') as f:
                foods = json.load(f)
                self.foods_dict = {food['name']: food for food in foods}
            logger.info(f"📦 Loaded {len(self.foods_dict)} foods from vietnamese_foods.json")
        except Exception as e:
            logger.error(f"❌ Failed to load vietnamese_foods.json: {e}")
            return
        
        # Load vietnamese_dishes.json
        dishes_file = base_dir / 'vietnamese_dishes.json'
        try:
            with open(dishes_file, encoding='utf-8') as f:
                dishes_data = json.load(f)
                
                # Parse dishes và tính toán thông tin dinh dưỡng
                for dish_data in dishes_data:
                    dish = self._parse_dish(dish_data)
                    if dish:
                        self.dishes.append(dish)
                
            logger.info(f"📦 Loaded {len(self.dishes)} dishes from vietnamese_dishes.json")
        except Exception as e:
            logger.error(f"❌ Failed to load vietnamese_dishes.json: {e}")

    def _parse_dish(self, dish_data: dict) -> Optional[Dish]:
        """Parse món ăn từ JSON và tính toán thông tin dinh dưỡng"""
        try:
            components = []
            total_cal = 0
            total_protein = 0
            total_carbs = 0
            total_fat = 0
            
            for ingredient in dish_data['ingredients']:
                ingredient_name = ingredient['name']
                serving_grams = ingredient['grams']
                
                # Tìm thông tin dinh dưỡng từ vietnamese_foods
                if ingredient_name not in self.foods_dict:
                    logger.warning(f"⚠️  Ingredient not found: {ingredient_name} in dish {dish_data['name']}")
                    continue
                
                food = self.foods_dict[ingredient_name]
                
                # Tính toán dinh dưỡng cho khẩu phần
                ratio = serving_grams / 100.0
                calories = float(food.get('energy_kcal', 0)) * ratio
                protein = float(food.get('protein', 0)) * ratio
                carbs = float(food.get('carbohydrates', 0)) * ratio
                fat = float(food.get('fat', 0)) * ratio
                
                component = DishComponent(
                    name=ingredient_name,
                    serving_grams=serving_grams,
                    calories=calories,
                    protein=protein,
                    carbs=carbs,
                    fat=fat,
                    energy_per_100g=float(food.get('energy_kcal', 0))
                )
                
                components.append(component)
                total_cal += calories
                total_protein += protein
                total_carbs += carbs
                total_fat += fat
            
            if not components:
                return None
            
            return Dish(
                id=dish_data['id'],
                name=dish_data['name'],
                meal_types=dish_data['meal_types'],
                components=components,
                total_calories=total_cal,
                total_protein=total_protein,
                total_carbs=total_carbs,
                total_fat=total_fat
            )
        except Exception as e:
            logger.error(f"❌ Failed to parse dish {dish_data.get('name', 'unknown')}: {e}")
            return None

    async def optimize_meal(
        self,
        db: AsyncSession,
        target: MacroTarget,
        meal_type: str,
        recent_dish_ids: list[int] = None,
        dietary_restrictions: list[str] = None,
    ) -> Optional[Dish]:
        """
        Tối ưu 1 bữa ăn bằng cách chọn món ăn phù hợp với sự đa dạng cao.
        
        Args:
            db: Database session (không dùng nhưng giữ để tương thích)
            target: Mục tiêu macro
            meal_type: breakfast/lunch/dinner/snack
            recent_dish_ids: Danh sách ID món đã dùng gần đây (để tránh lặp)
            dietary_restrictions: ["vegetarian", "low_carb", "high_protein"]
        
        Returns:
            Món ăn đã được scale khẩu phần phù hợp với target
        """
        recent_dish_ids = recent_dish_ids or []
        dietary_restrictions = dietary_restrictions or []

        # 1. Lọc món phù hợp với meal_type
        suitable_dishes = [
            dish for dish in self.dishes
            if meal_type in dish.meal_types
        ]
        
        if not suitable_dishes:
            logger.warning(f"⚠️  No dishes found for meal_type: {meal_type}")
            return None
        
        logger.info(f"📊 Found {len(suitable_dishes)} dishes for {meal_type}")

        # 2. Lọc theo dietary restrictions
        if "vegetarian" in dietary_restrictions:
            suitable_dishes = [
                dish for dish in suitable_dishes
                if not any(
                    any(kw in comp.name.lower() for kw in ["thịt", "gà", "bò", "heo", "lợn", "cá", "tôm"])
                    for comp in dish.components
                )
            ]

        # 3. Phân loại món theo loại tinh bột và protein để tăng đa dạng
        def get_carb_type(dish: Dish) -> str:
            """Xác định loại tinh bột chính của món"""
            for comp in dish.components:
                name_lower = comp.name.lower()
                if "cơm" in name_lower or "gạo" in name_lower:
                    return "cơm"
                elif "phở" in name_lower or "bánh phở" in name_lower:
                    return "phở"
                elif "bún" in name_lower:
                    return "bún"
                elif "miến" in name_lower:
                    return "miến"
                elif "mì" in name_lower:
                    return "mì"
                elif "cháo" in name_lower:
                    return "cháo"
                elif "xôi" in name_lower or "nếp" in name_lower:
                    return "xôi"
            return "khác"
        
        def get_protein_type(dish: Dish) -> str:
            """Xác định loại protein chính của món"""
            for comp in dish.components:
                name_lower = comp.name.lower()
                if "gà" in name_lower:
                    return "gà"
                elif "bò" in name_lower:
                    return "bò"
                elif "heo" in name_lower or "lợn" in name_lower or "sườn" in name_lower:
                    return "heo"
                elif "cá" in name_lower:
                    return "cá"
                elif "tôm" in name_lower:
                    return "tôm"
                elif "mực" in name_lower:
                    return "mực"
                elif "trứng" in name_lower:
                    return "trứng"
                elif "xúc xích" in name_lower or "giò" in name_lower or "chả" in name_lower:
                    return "chế biến"
            return "khác"

        # 4. Loại bỏ món đã dùng gần đây và ưu tiên món có loại tinh bột/protein khác
        if recent_dish_ids:
            # Lấy thông tin về các món đã ăn gần đây
            recent_dishes = [d for d in self.dishes if d.id in recent_dish_ids]
            recent_carb_types = set(get_carb_type(d) for d in recent_dishes)
            recent_protein_types = set(get_protein_type(d) for d in recent_dishes)
            
            # Ưu tiên món có loại tinh bột và protein khác với các bữa gần đây
            diverse_dishes = [
                dish for dish in suitable_dishes
                if dish.id not in recent_dish_ids
                and (get_carb_type(dish) not in recent_carb_types
                     or get_protein_type(dish) not in recent_protein_types)
            ]
            
            # Nếu có món đa dạng, dùng chúng; không thì dùng tất cả trừ món đã ăn
            if diverse_dishes:
                suitable_dishes = diverse_dishes
                logger.info(f"🎲 Prioritizing diverse dishes: {len(diverse_dishes)}")
            else:
                suitable_dishes = [
                    dish for dish in suitable_dishes
                    if dish.id not in recent_dish_ids
                ]
        
        if not suitable_dishes:
            logger.warning(f"⚠️  No dishes left after filtering")
            # Fallback: bỏ qua recent_dish_ids
            suitable_dishes = [
                dish for dish in self.dishes
                if meal_type in dish.meal_types
            ]

        # 5. Chọn món có calories gần với target nhất
        # Sắp xếp theo độ chênh lệch calories
        suitable_dishes.sort(
            key=lambda d: abs(d.total_calories - target.calories)
        )
        
        # Random trong top 8 để đa dạng hơn (tăng từ 5 lên 8)
        top_dishes = suitable_dishes[:8]
        selected_dish = random.choice(top_dishes)
        
        carb_type = get_carb_type(selected_dish)
        protein_type = get_protein_type(selected_dish)
        logger.info(
            f"🍽 Selected dish: {selected_dish.name} ({carb_type} + {protein_type}) "
            f"(base: {selected_dish.total_calories:.0f} kcal, target: {target.calories:.0f} kcal)"
        )

        # 6. Scale khẩu phần để đạt target
        scaled_dish = self._scale_dish(selected_dish, target)
        
        return scaled_dish

    def _scale_dish(self, dish: Dish, target: MacroTarget) -> Dish:
        """
        Scale khẩu phần của món ăn để đạt target calories.
        
        Strategy:
        - Tính tỷ lệ scale = target_calories / dish_calories
        - Giới hạn scale trong khoảng [0.7, 1.5] để không quá lệch
        - Scale tất cả nguyên liệu theo tỷ lệ
        """
        # Tính tỷ lệ scale
        scale_ratio = target.calories / dish.total_calories
        
        # Giới hạn scale
        scale_ratio = max(0.7, min(1.5, scale_ratio))
        
        # Scale components
        scaled_components = []
        for comp in dish.components:
            scaled_comp = DishComponent(
                name=comp.name,
                serving_grams=int(comp.serving_grams * scale_ratio),
                calories=comp.calories * scale_ratio,
                protein=comp.protein * scale_ratio,
                carbs=comp.carbs * scale_ratio,
                fat=comp.fat * scale_ratio,
                energy_per_100g=comp.energy_per_100g
            )
            scaled_components.append(scaled_comp)
        
        # Tạo dish mới với components đã scale
        scaled_dish = Dish(
            id=dish.id,
            name=dish.name,
            meal_types=dish.meal_types,
            components=scaled_components,
            total_calories=dish.total_calories * scale_ratio,
            total_protein=dish.total_protein * scale_ratio,
            total_carbs=dish.total_carbs * scale_ratio,
            total_fat=dish.total_fat * scale_ratio
        )
        
        logger.info(
            f"✅ Scaled dish: {scaled_dish.name} "
            f"({scaled_dish.total_calories:.0f} kcal, scale={scale_ratio:.2f})"
        )
        
        return scaled_dish


# Singleton
dish_optimizer = DishOptimizer()
