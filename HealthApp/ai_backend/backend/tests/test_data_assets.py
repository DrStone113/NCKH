from pathlib import Path


def test_required_data_assets_exist():
    data_dir = Path(__file__).resolve().parent.parent / "data"
    for name in [
        "vietnamese_dishes.json",
        "vietnamese_foods.json",
        "wger_exercises_raw.json",
        "exercises.json",
        "nutrition.json",
    ]:
        assert (data_dir / name).exists()