"""Test dish_optimizer"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.dish_optimizer import dish_optimizer

print(f"✅ Loaded {len(dish_optimizer.dishes)} dishes")
print(f"✅ Loaded {len(dish_optimizer.foods_dict)} foods")

# Test một vài món
print("\n📋 Sample dishes:")
for dish in dish_optimizer.dishes[:5]:
    print(f"  - {dish.name}: {dish.total_calories:.0f} kcal ({len(dish.components)} nguyên liệu)")
