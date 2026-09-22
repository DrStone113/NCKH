"""Create deterministic, structured V2 records from approved raw sources."""

from __future__ import annotations

import hashlib
import html
import json
import re
import zipfile
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "apps/backend/data/research_v2"
NORMALIZED = DATA / "normalized"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


def _food_content(food: dict[str, Any]) -> str:
    values: list[tuple[int, str]] = []
    for item in food.get("foodNutrients", []):
        nutrient = item.get("nutrient") or {}
        amount = item.get("amount")
        if amount is None or not nutrient.get("name"):
            continue
        values.append((int(nutrient.get("rank") or 999999), f"{nutrient['name']}: {amount} {nutrient.get('unitName', '')}".strip()))
    values.sort()
    return "USDA FoodData Central SR Legacy nutrient profile (per 100 g where supplied): " + "; ".join(value for _, value in values[:20])


def usda_rows() -> list[dict[str, Any]]:
    raw = DATA / "raw/FoodData_Central_sr_legacy_food_json_2018-04.zip"
    with zipfile.ZipFile(raw) as archive:
        name = next(item for item in archive.namelist() if item.endswith(".json"))
        foods = json.loads(archive.read(name))["SRLegacyFoods"]
    rows = []
    for food in sorted(foods, key=lambda item: int(item["fdcId"]))[:3000]:
        fdc_id = str(food["fdcId"])
        title = str(food["description"]).strip()
        if not title:
            continue
        rows.append({
            "record_id": f"usda-sr-{fdc_id}", "category": "food", "domain": "food", "title": title,
            "content": _food_content(food), "source_id": "USDA_FDC_SR_LEGACY_2018", "source_type": "dataset",
            "publisher": "U.S. Department of Agriculture, Agricultural Research Service",
            "source_url": f"https://fdc.nal.usda.gov/food-details/{fdc_id}/nutrients",
            "source_record_id": f"fdcId:{fdc_id}", "source_dataset_version": "2018-04",
            "language": "en", "normalization_method": "structured_field_projection_v1", "license": "CC0-1.0",
        })
    return rows


def _plain(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def wger_rows() -> list[dict[str, Any]]:
    raw = ROOT / "apps/backend/data/wger_exercises_raw.json"
    records = json.loads(raw.read_text(encoding="utf-8"))
    rows = []
    for exercise in sorted(records, key=lambda item: int(item["id"])):
        translations = exercise.get("translations") or []
        translation = next((item for item in translations if item.get("language") == 2 and item.get("name")), None)
        translation = translation or next((item for item in translations if item.get("name")), None)
        if translation is None:
            continue
        exercise_id = str(exercise["id"])
        equipment = ", ".join(item.get("name", "") for item in exercise.get("equipment", []) if item.get("name")) or "Not specified"
        muscles = ", ".join(item.get("name", "") for item in exercise.get("muscles", []) if item.get("name")) or "Not specified"
        secondary = ", ".join(item.get("name", "") for item in exercise.get("muscles_secondary", []) if item.get("name")) or "Not specified"
        description = _plain(str(translation.get("description") or "")) or "Instructions not supplied in selected translation."
        license_info = exercise.get("license") or {}
        content = f"Exercise: {translation['name']}. Category: {(exercise.get('category') or {}).get('name', 'Not specified')}. Primary muscles: {muscles}. Secondary muscles: {secondary}. Equipment: {equipment}. Instructions: {description}"
        rows.append({
            "record_id": f"wger-{exercise_id}", "category": "exercise", "domain": "exercise", "title": str(translation["name"]).strip(),
            "content": content, "source_id": "WGER_LOCAL_SNAPSHOT", "source_type": "dataset_snapshot",
            "publisher": "wger project and record authors", "source_url": f"https://wger.de/api/v2/exerciseinfo/{exercise_id}/",
            "source_record_id": f"exercise_id:{exercise_id}", "source_dataset_version": str(exercise.get("last_update_global") or "local-snapshot"),
            "language": "en" if translation.get("language") == 2 else "und", "normalization_method": "structured_field_projection_v1",
            "license": license_info.get("short_name", "UNKNOWN"), "license_url": license_info.get("url"),
            "license_author": translation.get("license_author") or exercise.get("license_author"),
        })
    return rows


def guidance_rows() -> list[dict[str, Any]]:
    facts = [
        ("adults-aerobic", "Người lớn: hoạt động aerobic", "Hướng dẫn nêu mốc 150–300 phút hoạt động aerobic cường độ vừa mỗi tuần; đây là hướng dẫn sức khỏe cộng đồng, không phải đơn kê đơn cá nhân."),
        ("adults-strength", "Người lớn: tăng cường cơ", "Hướng dẫn nêu hoạt động tăng cường cơ ít nhất 2 ngày mỗi tuần cho người lớn."),
        ("youth", "Trẻ 6–17 tuổi", "Hướng dẫn nêu tối thiểu 60 phút hoạt động thể lực mức vừa đến mạnh mỗi ngày cho nhóm 6–17 tuổi."),
        ("preschool", "Trẻ 3–5 tuổi", "Hướng dẫn nêu trẻ mầm non nên hoạt động trong ngày; mốc tham khảo là khoảng 3 giờ hoạt động mỗi ngày."),
        ("inactivity", "Thông điệp tránh bất động", "Hướng dẫn khuyến khích vận động nhiều hơn và ngồi ít hơn; mức cường độ cần phù hợp khả năng và hoàn cảnh cá nhân."),
        ("older-adults", "Người lớn tuổi", "Hướng dẫn đề cập lợi ích hoạt động thể lực và nguy cơ té ngã; người có vấn đề sức khỏe cần trao đổi với chuyên gia phù hợp trước khi thay đổi chương trình."),
    ]
    return [{
        "record_id": f"hhs-pag-{key}", "category": "guideline", "domain": "guideline", "title": title, "content": content,
        "source_id": "HHS_PHYSICAL_ACTIVITY_GUIDELINES_2018", "source_type": "government_guideline_summary",
        "publisher": "U.S. Department of Health and Human Services, Office of Disease Prevention and Health Promotion",
        "source_url": "https://odphp.health.gov/our-work/nutrition-physical-activity/physical-activity-guidelines/current-guidelines",
        "source_record_id": key, "source_dataset_version": "2018", "language": "vi", "original_language": "en",
        "normalization_method": "author_created_concise_vietnamese_factual_summary_v1", "license": "SUMMARY_ONLY_ATTRIBUTED",
    } for key, title, content in facts]


def main() -> int:
    usda = usda_rows(); wger = wger_rows(); guidance = guidance_rows()
    counts = {
        "usda_sr_legacy_foods.jsonl": write_jsonl(NORMALIZED / "usda_sr_legacy_foods.jsonl", usda),
        "wger_exercises.jsonl": write_jsonl(NORMALIZED / "wger_exercises.jsonl", wger),
        "hhs_physical_activity_guidance.jsonl": write_jsonl(NORMALIZED / "hhs_physical_activity_guidance.jsonl", guidance),
    }
    manifest = {"normalizer_version": "research-v2-normalizer-1", "counts": counts, "inputs": {"usda_zip_sha256": sha256(DATA / "raw/FoodData_Central_sr_legacy_food_json_2018-04.zip"), "wger_snapshot_sha256": sha256(ROOT / "apps/backend/data/wger_exercises_raw.json")}}
    path = DATA / "manifests/normalization_manifest.json"; path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
