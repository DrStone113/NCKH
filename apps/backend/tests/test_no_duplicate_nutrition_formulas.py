from __future__ import annotations

from pathlib import Path

from scripts.check_duplicate_nutrition_formulas import (
    find_duplicate_formulas,
    production_files,
)


def test_repository_has_no_duplicate_approved_nutrition_formulas() -> None:
    assert find_duplicate_formulas(production_files()) == []


def test_detector_catches_intentionally_introduced_bmi_copy(tmp_path: Path) -> None:
    copied_caller = tmp_path / "copied_prompt.py"
    copied_caller.write_text(
        'prompt = "underweight" if bmi < 18.5 else "ordinary"\n',
        encoding="utf-8",
    )
    findings = find_duplicate_formulas([copied_caller])
    assert [(item.path, item.rule) for item in findings] == [
        (copied_caller, "BMI_THRESHOLD_COPY")
    ]


def test_detector_ignores_unrelated_product_numbers(tmp_path: Path) -> None:
    unrelated = tmp_path / "layout.dart"
    unrelated.write_text(
        "const spacing = 25.0; const timeoutSeconds = 30.0; "
        "const caloriesPer100g = 23.0;\n",
        encoding="utf-8",
    )
    assert find_duplicate_formulas([unrelated]) == []
