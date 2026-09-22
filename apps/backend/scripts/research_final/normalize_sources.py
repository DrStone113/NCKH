"""Normalize reviewed final-corpus sources into deterministic semantic records.

English source wording is retained only where necessary for traceability.
Vietnamese titles and controlled labels are written by this project and marked
as such; they are not represented as NIH/NLM/CDC-authored translations.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import zipfile
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "apps/backend/data/research_final"
RAW, NORMALIZED = DATA / "raw", DATA / "normalized"

NUTRIENTS = {
    "VitaminA": "Vitamin A", "Thiamin": "Vitamin B1 (thiamin)", "Riboflavin": "Vitamin B2 (riboflavin)",
    "Niacin": "Vitamin B3 (niacin)", "PantothenicAcid": "Vitamin B5 (pantothenic acid)", "VitaminB6": "Vitamin B6",
    "Biotin": "Biotin", "Folate": "Folate", "VitaminB12": "Vitamin B12", "VitaminC": "Vitamin C",
    "VitaminD": "Vitamin D", "VitaminE": "Vitamin E", "VitaminK": "Vitamin K", "Calcium": "Canxi",
    "Iron": "Sắt", "Magnesium": "Magiê", "Zinc": "Kẽm", "Iodine": "I-ốt", "Selenium": "Selen",
    "Copper": "Đồng", "Potassium": "Kali", "Choline": "Choline", "Omega3FattyAcids": "Axit béo omega-3",
}
RELEVANT_TERMS = (
    "nutrition", "healthy eating", "fitness", "exercise", "physical fitness", "dehydration", "fatigue", "dizziness",
    "anemia", "iron deficiency", "vitamin deficiency", "mineral deficiency", "food allergy", "food intolerance",
    "overweight", "obesity", "healthy weight", "digestive", "constipation", "diarrhea", "nausea", "muscle cramps",
    "sleep", "stress", "headache", "weakness", "loss of appetite",
)


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def plain(value: str) -> str:
    value = re.sub(r"<(script|style).*?</\\1>", " ", value, flags=re.I | re.S)
    return re.sub(r"\\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    materialized = sorted(rows, key=lambda row: row["record_id"])
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in materialized:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return len(materialized)


def record(*, record_id: str, category: str, title: str, content: str, source_id: str, source_url: str, source_record_id: str, publisher: str, language: str, license_name: str, method: str, **extra: Any) -> dict[str, Any]:
    return {
        "record_id": record_id, "category": category, "title": title.strip(), "content": content.strip(),
        "source_id": source_id, "source_url": source_url, "source_record_id": source_record_id,
        "publisher": publisher, "source_language": language, "license": license_name,
        "normalization_method": method, "is_dynamic": False, **extra,
    }


def ods_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for slug, vn_name in NUTRIENTS.items():
        path = RAW / "ods" / f"{slug}.html"
        if not path.exists():
            continue
        body = plain(path.read_text(encoding="utf-8", errors="replace"))
        # Consumer pages use headings followed by sections.  Keep compact, source-attributed excerpts.
        sections = re.split(r"(?=(?:What|How|Can|Does|Who) [A-Z][^?]{2,120}\\?)", body)
        usable = 0
        for section in sections:
            section = section.strip()
            match = re.match(r"((?:What|How|Can|Does|Who) [^?]{2,120}\\?)\\s*(.*)", section, flags=re.S)
            if not match:
                continue
            heading, content = match.group(1), re.sub(r"\\s+", " ", match.group(2)).strip()
            if len(content) < 60:
                continue
            content = content[:1200].rsplit(" ", 1)[0] + "." if len(content) > 1200 else content
            label = {"what": "tổng quan", "how": "lượng dùng hoặc nguồn thực phẩm", "can": "an toàn", "does": "tương tác", "who": "nhóm nguy cơ"}.get(heading.split()[0].lower(), "thông tin")
            rows.append(record(
                record_id=f"ods-{slug}-{usable:02d}", category="micronutrient", title=f"{vn_name}: {label}",
                content=f"Tóm tắt có dẫn nguồn NIH ODS. {heading} {content}", source_id="NIH_ODS_FACT_SHEETS",
                source_url=f"https://ods.od.nih.gov/factsheets/{slug}-Consumer/", source_record_id=f"{slug}:{usable}",
                publisher="National Institutes of Health, Office of Dietary Supplements", language="en",
                license_name="US_GOVERNMENT_PUBLIC_DOMAIN_UNLESS_NOTED", method="controlled_vietnamese_label_plus_structured_source_excerpt_en_v1",
                original_title=heading, normalization_language="vi+en", attribution="NIH Office of Dietary Supplements",
            ))
            usable += 1
            if usable >= 6:
                break
    return rows


def medline_definition_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted((RAW / "medlineplus_definitions").glob("*.xml")):
        root = ET.fromstring(path.read_bytes())
        page_url = root.attrib.get("page-url", "https://medlineplus.gov/xml.html")
        category = "micronutrient" if path.stem in {"vitamins", "minerals"} else "nutrition"
        for index, group in enumerate(root.findall("term-group")):
            term = plain(group.findtext("term") or "").lstrip(">")
            definition = plain(group.findtext("definition") or "").lstrip(">")
            if not term or len(definition) < 40:
                continue
            rows.append(record(
                record_id=f"medline-definition-{path.stem}-{index:03d}", category=category,
                title=f"{term}: định nghĩa", content=f"Định nghĩa MedlinePlus có dẫn nguồn: {definition}",
                source_id="MEDLINEPLUS_DEFINITIONS", source_url=page_url, source_record_id=f"{path.stem}:{index}",
                publisher="U.S. National Library of Medicine", language="en", license_name="NLM_PUBLIC_DOMAIN_WITH_ATTRIBUTION",
                method="controlled_vietnamese_label_plus_medlineplus_definition_v1", normalization_language="vi+en",
                attribution="MedlinePlus.gov, U.S. National Library of Medicine", referenced_publisher=group.attrib.get("reference"),
            ))
    return rows


def medline_rows() -> list[dict[str, Any]]:
    with zipfile.ZipFile(RAW / "medlineplus_topics.zip") as archive:
        xml_name = next(name for name in archive.namelist() if name.endswith(".xml"))
        root = ET.fromstring(archive.read(xml_name))
    rows: list[dict[str, Any]] = []
    for topic in root.findall(".//health-topic"):
        title = (topic.attrib.get("title") or topic.findtext("title") or "").strip()
        summary = plain(topic.findtext("full-summary") or topic.findtext("summary") or "")
        url = (topic.attrib.get("url") or topic.findtext("url") or "https://medlineplus.gov/").strip()
        key = " ".join([title, *(item.text or "" for item in topic.findall("also-called"))]).casefold()
        if not title or len(summary) < 80 or not any(term in key for term in RELEVANT_TERMS):
            continue
        topic_id = (topic.attrib.get("id") or topic.findtext("id") or title).strip()
        text = summary[:1600].rsplit(" ", 1)[0] + "." if len(summary) > 1600 else summary
        rows.append(record(
            record_id=f"medlineplus-{hashlib.sha256(topic_id.encode()).hexdigest()[:16]}", category="health",
            title=f"Sức khỏe: {title}", content=f"Tóm tắt MedlinePlus (NLM), dành cho thông tin sức khỏe phổ thông: {text}",
            source_id="MEDLINEPLUS_HEALTH_TOPICS", source_url=url, source_record_id=topic_id,
            publisher="U.S. National Library of Medicine", language="en", license_name="NLM_PUBLIC_DOMAIN_WITH_ATTRIBUTION",
            method="controlled_vietnamese_label_plus_medlineplus_structured_summary_v1", normalization_language="vi+en",
            attribution="MedlinePlus.gov, U.S. National Library of Medicine",
        ))
    return rows


def foundation_rows(limit: int = 600) -> list[dict[str, Any]]:
    with zipfile.ZipFile(RAW / "usda_foundation_2026.zip") as archive:
        json_name = next(name for name in archive.namelist() if name.endswith(".json"))
        payload = json.loads(archive.read(json_name))
    foods = payload.get("FoundationFoods") or payload.get("foundationFoods") or []
    rows: list[dict[str, Any]] = []
    valid_foods = [item for item in foods if isinstance(item, dict)]
    for food in sorted(valid_foods, key=lambda item: int(item.get("fdcId", 0)))[:limit]:
        fdc_id, title = str(food.get("fdcId", "")), str(food.get("description", "")).strip()
        nutrients = []
        for item in food.get("foodNutrients", []):
            nutrient = item.get("nutrient") or {}
            amount, name = item.get("amount"), nutrient.get("name")
            if amount is not None and name:
                nutrients.append((int(nutrient.get("rank") or 999999), f"{name}: {amount} {nutrient.get('unitName', '')}".strip()))
        if not fdc_id or not title or not nutrients:
            continue
        profile = "; ".join(text for _, text in sorted(nutrients)[:18])
        rows.append(record(
            record_id=f"usda-foundation-{fdc_id}", category="food", title=title,
            content=f"USDA FoodData Central Foundation Foods nutrient profile (as supplied): {profile}",
            source_id="USDA_FDC_FOUNDATION_2026", source_url=f"https://fdc.nal.usda.gov/food-details/{fdc_id}/nutrients",
            source_record_id=f"fdcId:{fdc_id}", publisher="U.S. Department of Agriculture, Agricultural Research Service",
            language="en", license_name="CC0-1.0", method="structured_field_projection_v1", normalization_language="en",
        ))
    if not rows:
        raise RuntimeError("USDA_FOUNDATION_PARSE_EMPTY")
    return rows


def authored_guidance() -> list[dict[str, Any]]:
    facts = [
        ("cdc-adult-aerobic", "physical_activity_guideline", "Người lớn: hoạt động aerobic", "Hướng dẫn CDC nêu người lớn cần ít nhất 150 phút hoạt động aerobic cường độ vừa mỗi tuần, hoặc 75 phút cường độ mạnh, hay cách kết hợp tương đương."),
        ("cdc-adult-strength", "physical_activity_guideline", "Người lớn: tăng cường cơ", "Hướng dẫn CDC nêu hoạt động tăng cường cơ cho các nhóm cơ chính ít nhất 2 ngày mỗi tuần."),
        ("cdc-start-safely", "health_safety", "Bắt đầu vận động an toàn", "Khi mới vận động hoặc có bệnh mạn tính/triệu chứng đáng lo, nên tăng dần theo khả năng và trao đổi với chuyên gia phù hợp trước khi đổi mạnh chương trình."),
        ("dga-pattern", "nutrition", "Ăn uống lành mạnh: mô hình tổng thể", "Tóm tắt có dẫn nguồn DGA: ưu tiên mô hình ăn đa dạng với rau, quả, ngũ cốc nguyên hạt, thực phẩm giàu đạm và lựa chọn ít đường thêm, natri và chất béo bão hòa hơn."),
        ("dga-nutrient-density", "nutrition", "Mật độ dinh dưỡng", "Tóm tắt có dẫn nguồn DGA: lựa chọn giàu dinh dưỡng giúp đáp ứng nhu cầu vitamin, khoáng chất và chất xơ trong giới hạn năng lượng phù hợp."),
        ("dga-weight", "weight_management", "Quản lý cân nặng: nguyên tắc", "Tóm tắt có dẫn nguồn DGA: quản lý cân nặng cần xem xét mô hình ăn, hoạt động thể lực, giấc ngủ và bối cảnh cá nhân; không phải là đơn điều trị hay chẩn đoán."),
        ("cdc-bmi-screening", "body_metric", "BMI người lớn: chỉ số sàng lọc", "BMI là chỉ số sàng lọc dựa trên cân nặng và chiều cao, không tự nó chẩn đoán tình trạng sức khỏe hoặc thành phần cơ thể của từng cá nhân."),
    ]
    result = []
    for key, category, title, content in facts:
        source = "CDC_PHYSICAL_ACTIVITY_GUIDANCE" if key.startswith("cdc-") else "DGA_2025_2030"
        url = "https://www.cdc.gov/physical-activity-basics/guidelines/adults.html" if key.startswith("cdc-") else "https://odphp.health.gov/our-work/nutrition-physical-activity/dietary-guidelines"
        result.append(record(
            record_id=key, category=category, title=title, content=content, source_id=source, source_url=url,
            source_record_id=key, publisher="Centers for Disease Control and Prevention" if key.startswith("cdc-") else "U.S. Department of Health and Human Services and U.S. Department of Agriculture",
            language="vi", license_name="US_GOVERNMENT_PUBLIC_DOMAIN_UNLESS_NOTED", method="project_authored_concise_vietnamese_factual_normalization_v1",
            original_language="en", normalization_language="vi", attribution="CDC" if key.startswith("cdc-") else "Dietary Guidelines for Americans, 2025-2030",
        ))
    return result


def main() -> int:
    NORMALIZED.mkdir(parents=True, exist_ok=True)
    groups = {
        "nih_ods_micronutrients.jsonl": ods_rows(),
        "medlineplus_definitions.jsonl": medline_definition_rows(),
        "medlineplus_health_topics.jsonl": medline_rows(),
        "usda_foundation_foods.jsonl": foundation_rows(),
        "us_guidance.jsonl": authored_guidance(),
    }
    counts = {name: write_jsonl(NORMALIZED / name, rows) for name, rows in groups.items()}
    manifest = {"normalizer_version": "research-final-normalizer-1", "counts": counts, "input_hashes": {str(path.relative_to(ROOT)).replace("\\\\", "/"): sha256(path) for path in sorted(RAW.rglob("*")) if path.is_file()}}
    (DATA / "manifests").mkdir(exist_ok=True)
    (DATA / "manifests/normalization_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, **manifest}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
