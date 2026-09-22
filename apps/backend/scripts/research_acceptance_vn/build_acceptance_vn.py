"""Build a Vietnam-first acceptance candidate without changing older corpora."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
BACKEND = ROOT / "apps/backend"
DATA = BACKEND / "data/research_acceptance_vn"
PREVIOUS = BACKEND / "data/research_final/manifests/final_candidate_corpus.jsonl"
OUT = DATA / "manifests/acceptance_candidate.jsonl"
MANIFEST = DATA / "manifests/acceptance_candidate_manifest.json"
AUDIT = DATA / "manifests/acceptance_candidate_audit.json"
UTILITY_EXCLUSIONS = DATA / "manifests/utility_exclusions.jsonl"
REGISTRY = DATA / "source_registry.json"
NAMESPACE = uuid.UUID("d5581f39-1ac8-5cd4-ae6f-32fb2e4193cf")


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def norm(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def utility_gate(row: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    """Deterministic scope filter; authority never bypasses chatbot utility."""
    title = norm(str(row.get("title", "")))
    category, domain, jurisdiction = row["category"], row["domain"], row["jurisdiction"]
    source_authority = 3 if row["authority_level"] in {"VIETNAM_MINISTRY_OF_HEALTH", "VIETNAM_NATIONAL_INSTITUTE_OF_NUTRITION", "OPEN_DATASET", "FOREIGN_GOVERNMENT"} else 2
    intents: list[str] = []
    if domain in {"VN_FOOD", "FOREIGN_FOOD"}: intents = ["FOOD_NUTRITION_LOOKUP", "DIETARY_RECOMMENDATION"]
    elif domain == "VN_DISH": intents = ["FOOD_NUTRITION_LOOKUP", "DIETARY_RECOMMENDATION", "PERSONAL_HEALTH_PLAN_SUPPORT"]
    elif domain == "EXERCISE_CATALOG": intents = ["EXERCISE_RECOMMENDATION", "PHYSICAL_ACTIVITY_GUIDANCE"]
    elif domain in {"VN_NUTRIENT_REQUIREMENT", "VN_MICRONUTRIENT", "GLOBAL_MICRONUTRIENT"}: intents = ["MICRONUTRIENT_SUPPORT", "DIETARY_RECOMMENDATION"]
    elif domain in {"VN_NUTRITION_GUIDELINE", "VN_PHYSICAL_ACTIVITY", "INTERNATIONAL_SUPPLEMENTAL"}: intents = ["DIETARY_RECOMMENDATION", "PERSONAL_HEALTH_PLAN_SUPPORT"]
    elif domain == "VN_BODY_METRIC": intents = ["BODY_METRIC_SUPPORT", "PERSONAL_HEALTH_PLAN_SUPPORT"]
    elif domain == "GLOBAL_HEALTH":
        allowed = ("nutrition", "diet", "vitamin", "mineral", "anemia", "iron", "dehydration", "fatigue", "dizziness", "weakness", "appetite", "allergy", "intolerance", "constipation", "diarrhea", "nausea", "obesity", "overweight", "healthy weight", "exercise", "fitness", "muscle cramp", "sleep", "stress")
        forbidden = ("aplastic", "sickle", "thalassem", "cancer", "surgery", "genetic", "procedure", "imaging", "infection")
        if any(token in title for token in forbidden) or not any(token in title for token in allowed):
            intents = []
        else:
            intents = ["HEALTH_NUTRITION_CONTEXT"]
            if any(token in title for token in ("dehydration", "dizziness", "weakness", "muscle cramp")): intents.append("SAFETY_ESCALATION")
            if any(token in title for token in ("allergy", "intolerance")): intents.append("DIETARY_CONSTRAINT")
    relevance = 3 if category in {"food", "dish", "exercise", "nutrition", "micronutrient", "physical_activity_guideline", "body_metric", "weight_management"} and intents else (2 if intents else 1)
    vietnam = 2 if jurisdiction == "VN" else (1 if intents and category in {"food", "dish", "nutrition", "micronutrient"} else 0)
    actionability = 2 if category in {"food", "dish", "exercise", "nutrition", "micronutrient", "physical_activity_guideline", "body_metric", "weight_management"} else (1 if intents else 0)
    safety = 2 if "SAFETY_ESCALATION" in intents else (1 if category in {"health", "body_metric", "weight_management"} and intents else 0)
    total = relevance + vietnam + actionability + safety + source_authority
    approved_project = row["source_id"] == "PROJECT_CURATED_VN"
    included = bool(intents) and (approved_project or (relevance >= 2 and source_authority >= 2 and total >= 6))
    rationale = "approved canonical project dataset" if approved_project else "directly supports: " + ", ".join(intents) if included else "outside approved chatbot intents or insufficient direct utility"
    provenance = {"chatbot_intents": intents, "chatbot_relevance_score": relevance, "vietnam_relevance_score": vietnam, "actionability_score": actionability, "safety_value_score": safety, "source_authority_score": source_authority, "total_utility_score": total, "inclusion_reason": rationale if included else None, "exclusion_reason": None if included else rationale}
    return included, provenance


def source_template(source_id: str, publisher: str, url: str | None, *, jurisdiction: str, authority: str, license_name: str, reuse: str, language: str = "vi") -> dict[str, Any]:
    return {"source_id": source_id, "publisher": publisher, "title": source_id, "source_url": url, "download_url": None, "version": None, "publication_date": None, "accessed_at": "2026-09-22", "license": license_name, "license_url": None, "reuse_status": reuse, "attribution_required": True, "raw_artifact_path": None, "raw_sha256": None, "parser": "structured_acceptance_vn_builder", "parser_version": "1", "language": language, "jurisdiction": jurisdiction, "authority_level": authority, "record_count_raw": 0, "record_count_included": 0, "record_count_excluded": 0, "exclusion_reason": None}


def registry() -> dict[str, dict[str, Any]]:
    items = [
        source_template("VN_MOH_2030", "Bộ Y tế", "https://viendinhduong.vn/vi/proper-nutrition-and-health/muoi-loi-khuyen-dinh-duong", jurisdiction="VN", authority="VIETNAM_MINISTRY_OF_HEALTH", license_name="COPYRIGHT_LIMITED_FACTUAL_NORMALIZATION", reuse="LIMITED_FACTUAL_NORMALIZATION"),
        source_template("VN_NIN_RNI_2026", "Viện Dinh dưỡng", "https://viendinhduong.vn/vi/article/tin-tuc/6a70094d06fb0c475f0ac123", jurisdiction="VN", authority="VIETNAM_NATIONAL_INSTITUTE_OF_NUTRITION", license_name="COPYRIGHT_LIMITED_FACTUAL_NORMALIZATION", reuse="LIMITED_FACTUAL_NORMALIZATION"),
        source_template("VN_NIN_PYRAMID_2025", "Viện Dinh dưỡng", "https://viendinhduong.vn/vi/proper-nutrition-and-health/thap-dinh-duong-hop-ly", jurisdiction="VN", authority="VIETNAM_NATIONAL_INSTITUTE_OF_NUTRITION", license_name="COPYRIGHT_LIMITED_FACTUAL_NORMALIZATION", reuse="LIMITED_FACTUAL_NORMALIZATION"),
        source_template("VIETNAM_FCT_2007", "Viện Dinh dưỡng Quốc gia - Bộ Y tế", "https://chuyentrang.viendinhduong.vn/viewfilenew/vi/thu-vien-sach-chuyen-nganh/189/1.html", jurisdiction="VN", authority="VIETNAM_NATIONAL_INSTITUTE_OF_NUTRITION", license_name="REVIEW_REQUIRED_FOR_REDISTRIBUTION", reuse="LIMITED_INTERNAL_FACTUAL_PROJECTION"),
        source_template("PROJECT_CURATED_VN", "NCKH curated Vietnamese catalog", "local:apps/backend/data", jurisdiction="VN", authority="PROJECT_CURATED", license_name="PROJECT_CURATED", reuse="PROJECT_SCOPE"),
        source_template("USDA_FDC_FOUNDATION_2026", "USDA ARS", "https://fdc.nal.usda.gov/download-datasets.html", jurisdiction="US", authority="OPEN_DATASET", license_name="CC0-1.0", reuse="ALLOWED", language="en"),
        source_template("MEDLINEPLUS", "U.S. National Library of Medicine", "https://medlineplus.gov/xml.html", jurisdiction="US", authority="FOREIGN_GOVERNMENT", license_name="NLM_PUBLIC_DOMAIN_WITH_ATTRIBUTION", reuse="ALLOWED_WITH_ATTRIBUTION", language="en"),
        source_template("US_GUIDANCE", "U.S. public-health sources", "https://www.cdc.gov/physical-activity-basics/guidelines/adults.html", jurisdiction="US", authority="FOREIGN_GOVERNMENT", license_name="SUMMARY_ONLY_ATTRIBUTED", reuse="LIMITED_FACTUAL_NORMALIZATION", language="en"),
        source_template("WGER", "wger project", "https://wger.de/", jurisdiction="OTHER", authority="OPEN_DATASET", license_name="CC_BY_SA", reuse="ALLOWED_WITH_ATTRIBUTION", language="en"),
    ]
    return {item["source_id"]: item for item in items}


def record(*, source_id: str, source_record_id: str, title: str, content: str, category: str, domain: str, population: str, effective_date: str, authority: str, jurisdiction: str, publisher: str, url: str, **extra: Any) -> dict[str, Any]:
    return {"source_id": source_id, "source_record_id": source_record_id, "title": title, "content": content, "category": category, "domain": domain, "population": population, "effective_date": effective_date, "source_version": extra.pop("source_version", effective_date), "authority_level": authority, "jurisdiction": jurisdiction, "publisher": publisher, "source_url": url, "source_language": "vi", "normalization_method": "project-authored Vietnamese factual normalization; no source prose copied", "is_dynamic": False, **extra}


def vn_2030() -> list[dict[str, Any]]:
    facts = [
        ("01", "Ăn cân đối và đa dạng", "Khuyến nghị áp dụng bữa ăn đủ, cân đối và đa dạng; phối hợp thực phẩm nguồn động vật và thực vật.", "VN_NUTRITION_GUIDELINE", "vietnamese_general"),
        ("02", "Thực phẩm giàu vi chất", "Ưu tiên thực phẩm giàu vi chất và rau, củ, quả đa màu sắc; đọc thông tin dinh dưỡng trên nhãn trước khi chọn dùng.", "VN_MICRONUTRIENT", "vietnamese_general"),
        ("03", "Nguồn thực phẩm giàu đạm", "Lựa chọn thực phẩm giàu đạm hợp lý; ưu tiên cá, gia cầm và hạt, đồng thời dùng thịt đỏ có mức độ.", "VN_NUTRITION_GUIDELINE", "vietnamese_general"),
        ("04", "Uống đủ nước", "Duy trì lượng nước phù hợp hằng ngày; nhu cầu cụ thể còn phụ thuộc tuổi, cân nặng và hoạt động.", "VN_NUTRITION_GUIDELINE", "vietnamese_general"),
        ("05", "Thai kỳ và cho con bú", "Phụ nữ mang thai hoặc cho con bú cần khẩu phần hợp lý và vi chất theo hướng dẫn của cán bộ y tế phù hợp.", "VN_MICRONUTRIENT", "pregnant_lactating"),
        ("06", "Dinh dưỡng trẻ nhỏ", "Khuyến nghị nuôi con bằng sữa mẹ sớm, hoàn toàn trong 6 tháng đầu, sau đó ăn bổ sung phù hợp và tiếp tục bú mẹ khi thích hợp.", "VN_NUTRITION_GUIDELINE", "child"),
        ("07", "Hạn chế thực phẩm bất lợi", "Giảm thức ăn chiên rán, thức ăn nhanh nhiều dầu mỡ, thực phẩm nhiều muối hoặc đường, đồ uống có đường và đồ uống có cồn.", "VN_NUTRITION_GUIDELINE", "vietnamese_general"),
        ("08", "An toàn thực phẩm", "Lựa chọn, chế biến và bảo quản thực phẩm theo nguyên tắc an toàn thực phẩm.", "VN_NUTRITION_GUIDELINE", "vietnamese_general"),
        ("09", "Nề nếp bữa ăn", "Tổ chức bữa ăn gia đình, ăn các bữa chính phù hợp lứa tuổi, tránh bỏ bữa và tránh ăn quá mức.", "VN_NUTRITION_GUIDELINE", "vietnamese_general"),
        ("10", "Cân nặng và hoạt động thể lực", "Duy trì cân nặng phù hợp và tăng hoạt động thể lực phù hợp lứa tuổi, tình trạng sức khỏe; đây không phải hướng dẫn điều trị cá thể.", "VN_PHYSICAL_ACTIVITY", "vietnamese_general"),
    ]
    return [record(source_id="VN_MOH_2030", source_record_id=f"3594:{key}", title=f"Khuyến nghị dinh dưỡng Việt Nam 2030: {title}", content=content, category="nutrition" if domain != "VN_PHYSICAL_ACTIVITY" else "physical_activity_guideline", domain=domain, population=population, effective_date="2024-11-29", authority="VIETNAM_MINISTRY_OF_HEALTH", jurisdiction="VN", publisher="Bộ Y tế", url="https://viendinhduong.vn/vi/proper-nutrition-and-health/muoi-loi-khuyen-dinh-duong", source_version="3594/QĐ-BYT") for key, title, content, domain, population in facts]


def vn_rni() -> list[dict[str, Any]]:
    facts = [
        ("protein-adult", "Protein người trưởng thành", "Khuyến nghị protein cho người trưởng thành khỏe mạnh khoảng 0,93 g/kg cân nặng/ngày; không dùng thay thế đánh giá hoặc điều trị cá thể.", "VN_NUTRIENT_REQUIREMENT", "adult", "g/kg/ngày", 0.93),
        ("protein-long-term-upper", "Protein dùng dài hạn", "Không nên duy trì khẩu phần có lượng protein trên 2 g/kg cân nặng/ngày trong thời gian dài nếu không có đánh giá chuyên môn phù hợp.", "VN_NUTRIENT_REQUIREMENT", "adult", "g/kg/ngày", 2.0),
        ("lipid-adult", "Chất béo ở người trưởng thành", "Năng lượng từ lipid ở người trưởng thành được nêu trong khoảng 20–25% tổng năng lượng khẩu phần.", "VN_NUTRIENT_REQUIREMENT", "adult", "% năng lượng", "20–25"),
        ("omega3-adult", "EPA và DHA", "Tài liệu cập nhật nêu mức EPA và DHA tham khảo cho người trưởng thành là 250 mg/ngày.", "VN_MICRONUTRIENT", "adult", "mg/ngày", 250),
        ("free-sugar", "Đường tự do", "Đường tự do không nên vượt quá 10% tổng năng lượng; mức dưới 5% được nêu là có lợi hơn cho sức khỏe.", "VN_NUTRIENT_REQUIREMENT", "vietnamese_general", "% năng lượng", "<10; ưu tiên <5"),
        ("fiber-adult", "Chất xơ người trưởng thành", "Ví dụ được công bố: nam 18–49 tuổi trên 21 g/ngày và nữ cùng nhóm tuổi trên 18 g/ngày; các nhóm khác cần dùng bảng theo tuổi và giới.", "VN_NUTRIENT_REQUIREMENT", "adult", "g/ngày", "nam>21; nữ>18"),
        ("activity-level", "Nhu cầu năng lượng và mức hoạt động", "Khuyến nghị năng lượng phân theo mức hoạt động nhẹ, trung bình và nặng; hoạt động thể thao đặc thù cần xét thêm tiêu hao riêng.", "VN_NUTRIENT_REQUIREMENT", "adult", None, None),
        ("rni-limits", "Giới hạn sử dụng RNI", "Giá trị tham chiếu ghi nhãn không phải là nhu cầu điều trị hay chẩn đoán dinh dưỡng của một cá nhân.", "VN_BODY_METRIC", "vietnamese_general", None, None),
    ]
    return [record(source_id="VN_NIN_RNI_2026", source_record_id=f"rni2026:{key}", title=f"RNI Việt Nam 2026: {title}", content=content, category="micronutrient" if domain == "VN_MICRONUTRIENT" else ("body_metric" if domain == "VN_BODY_METRIC" else "nutrition"), domain=domain, population=population, effective_date="2026-08-03", authority="VIETNAM_NATIONAL_INSTITUTE_OF_NUTRITION", jurisdiction="VN", publisher="Viện Dinh dưỡng", url="https://viendinhduong.vn/vi/article/tin-tuc/6a70094d06fb0c475f0ac123", reference_type="VN_RNI_2026", unit=unit, value=value, source_version="RNI-2026") for key, title, content, domain, population, unit, value in facts]


def vn_pyramids() -> list[dict[str, Any]]:
    groups = [("3-5", "child_3_5"), ("6-11", "child_6_11"), ("12-14", "adolescent_12_14"), ("15-17", "adolescent_15_17"), ("người trưởng thành", "adult"), ("người cao tuổi", "elderly"), ("phụ nữ có thai và cho con bú", "pregnant_lactating")]
    return [record(source_id="VN_NIN_PYRAMID_2025", source_record_id=f"pyramid:{index}", title=f"Tháp dinh dưỡng Việt Nam 2025: {label}", content=f"Bộ tháp dinh dưỡng theo nhóm đối tượng có hướng dẫn riêng cho {label}; chọn tháp theo tuổi hoặc tình trạng sinh lý, phối hợp thực phẩm đa dạng, theo dõi cân nặng và vận động phù hợp.", category="nutrition", domain="VN_NUTRITION_GUIDELINE", population=population, effective_date="2025-05-26", authority="VIETNAM_NATIONAL_INSTITUTE_OF_NUTRITION", jurisdiction="VN", publisher="Viện Dinh dưỡng", url="https://viendinhduong.vn/vi/proper-nutrition-and-health/thap-dinh-duong-hop-ly", source_version="640/QĐ-VDD") for index, (label, population) in enumerate(groups, 1)]


def vn_foods() -> list[dict[str, Any]]:
    foods = json.loads((BACKEND / "data/vietnamese_foods.json").read_text(encoding="utf-8"))
    records = []
    for food in foods:
        name = str(food["name"]).strip(); code = str(food["ma_so"])
        facts = [f"năng lượng {food.get('energy_kcal')} kcal", f"protein {food.get('protein')} g", f"lipid {food.get('fat')} g", f"carbohydrat {food.get('carbohydrates')} g", f"canxi {food.get('calcium')} mg", f"sắt {food.get('iron')} mg"]
        records.append(record(source_id="VIETNAM_FCT_2007", source_record_id=f"vnfct:{code}", title=name, content="Thành phần dinh dưỡng quy chiếu theo dữ liệu Bảng thành phần thực phẩm Việt Nam trong dự án: " + "; ".join(facts) + ".", category="food", domain="VN_FOOD", population="vietnamese_general", effective_date="2007", authority="VIETNAM_NATIONAL_INSTITUTE_OF_NUTRITION", jurisdiction="VN", publisher="Viện Dinh dưỡng Quốc gia - Bộ Y tế", url="https://chuyentrang.viendinhduong.vn/viewfilenew/vi/thu-vien-sach-chuyen-nganh/189/1.html", source_version="VN_FCT_2007", preferred_for_vietnamese_user=True, reuse_status="LIMITED_INTERNAL_FACTUAL_PROJECTION"))
    return records


def reproject_previous() -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in PREVIOUS.read_text(encoding="utf-8").splitlines() if line]
    result=[]
    for row in rows:
        source = row["source_id"]
        if source == "USDA_FDC_FOUNDATION_2026" or (source == "V2_FROZEN_RESEARCH" and row.get("license") in {"CC0", "CC0-1.0"}): source_id, jurisdiction, authority = "USDA_FDC_FOUNDATION_2026", "US", "OPEN_DATASET"
        elif source.startswith("MEDLINEPLUS"): source_id, jurisdiction, authority = "MEDLINEPLUS", "US", "FOREIGN_GOVERNMENT"
        elif source in {"CDC_PHYSICAL_ACTIVITY_GUIDANCE", "DGA_2025_2030"} or (source == "V2_FROZEN_RESEARCH" and row.get("license") == "SUMMARY_ONLY_ATTRIBUTED"): source_id, jurisdiction, authority = "US_GUIDANCE", "US", "FOREIGN_GOVERNMENT"
        elif row.get("license", "").startswith("CC-BY-SA") or source == "V2_FROZEN_RESEARCH" and row.get("category") == "exercise": source_id, jurisdiction, authority = "WGER", "OTHER", "OPEN_DATASET"
        else: source_id, jurisdiction, authority = "PROJECT_CURATED_VN", "VN", "PROJECT_CURATED"
        category = row["category"]
        domain = {"food": "FOREIGN_FOOD" if jurisdiction != "VN" else "VN_DISH", "dish": "VN_DISH", "exercise": "EXERCISE_CATALOG", "micronutrient": "GLOBAL_MICRONUTRIENT", "health": "GLOBAL_HEALTH", "nutrition": "INTERNATIONAL_SUPPLEMENTAL", "physical_activity_guideline": "INTERNATIONAL_SUPPLEMENTAL", "health_safety": "GLOBAL_HEALTH", "body_metric": "INTERNATIONAL_SUPPLEMENTAL", "weight_management": "INTERNATIONAL_SUPPLEMENTAL"}.get(category, "INTERNATIONAL_SUPPLEMENTAL")
        item = dict(row); item.update({"source_id": source_id, "source_record_id": f"previous-final:{row['chunk_id']}", "domain": domain, "jurisdiction": jurisdiction, "authority_level": authority, "population": "general", "effective_date": row.get("source_dataset_version") or "historical", "source_version": row.get("source_dataset_version") or "historical", "normalization_method": "reprojection from offline-final-4419 pre-Vietnamization snapshot", "is_dynamic": False})
        result.append(item)
    return result


def main() -> int:
    if OUT.exists() or MANIFEST.exists(): raise RuntimeError("ACCEPTANCE_CANDIDATE_EXISTS_REFUSE_TO_OVERWRITE")
    DATA.joinpath("manifests").mkdir(parents=True, exist_ok=True)
    sources = registry(); incoming = reproject_previous() + vn_foods() + vn_2030() + vn_rni() + vn_pyramids()
    survivors: dict[str, dict[str, Any]] = {}; excluded=Counter()
    utility_exclusions: list[dict[str, Any]] = []
    priority = {"VN": 0, "GLOBAL": 1, "US": 2, "OTHER": 3}
    for row in sorted(incoming, key=lambda item: (priority.get(item["jurisdiction"], 9), item["source_id"], item["source_record_id"])):
        sources[row["source_id"]]["record_count_raw"] += 1
        required = ("title","content","source_id","source_record_id","source_url","jurisdiction","authority_level","population","effective_date")
        if any(not str(row.get(key,"")) for key in required): excluded["missing_provenance"] += 1; continue
        included, utility = utility_gate(row)
        if not included:
            excluded["low_chatbot_utility"] += 1
            sources[row["source_id"]]["record_count_excluded"] += 1
            utility_exclusions.append({"source_id": row["source_id"], "source_record_id": row["source_record_id"], "title": row["title"], **utility})
            continue
        row = dict(row); row.update(utility)
        key=norm(row["content"])
        if key in survivors:
            excluded["exact_duplicate"] += 1; sources[row["source_id"]]["record_count_excluded"] += 1; continue
        row["content_hash"]=digest(canonical({"title":row["title"],"content":row["content"],"source_id":row["source_id"],"source_record_id":row["source_record_id"]})); row["chunk_id"]=str(uuid.uuid5(NAMESPACE, f"{row['source_id']}:{row['source_record_id']}:{row['content_hash']}")); survivors[key]=row
    corpus=sorted(survivors.values(),key=lambda item:item["chunk_id"])
    for row in corpus: sources[row["source_id"]]["record_count_included"] += 1
    REGISTRY.write_text(json.dumps({"schema_version":"acceptance-vn-source-registry-1","registry_status":"CANDIDATE","sources":sorted(sources.values(),key=lambda item:item["source_id"])},ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    with OUT.open("w",encoding="utf-8",newline="\n") as handle:
        for row in corpus: handle.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+"\n")
    with UTILITY_EXCLUSIONS.open("w",encoding="utf-8",newline="\n") as handle:
        for row in utility_exclusions: handle.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+"\n")
    required_domains={"VN_FOOD","VN_NUTRITION_GUIDELINE","VN_NUTRIENT_REQUIREMENT","VN_MICRONUTRIENT","VN_PHYSICAL_ACTIVITY","VN_BODY_METRIC","VN_DISH"}
    domain_counts=Counter(row["domain"] for row in corpus); vn_count=sum(row["jurisdiction"]=="VN" for row in corpus); vn_relevant=sum(row["domain"].startswith("VN_") for row in corpus)
    intent_counts=Counter(intent for row in corpus for intent in row["chatbot_intents"])
    audit={"record_count":len(corpus),"empty_chunks":sum(not row["content"].strip() for row in corpus),"missing_provenance":0,"exact_duplicates":len(corpus)-len({norm(row["content"]) for row in corpus}),"domain_counts":dict(sorted(domain_counts.items())),"records_by_chatbot_intent":dict(sorted(intent_counts.items())),"excluded_low_chatbot_utility":len(utility_exclusions),"utility_exclusions_sha256":digest(UTILITY_EXCLUSIONS.read_bytes()),"source_counts":dict(sorted(Counter(row["source_id"] for row in corpus).items())),"vn_source_record_count":vn_count,"vn_source_record_percent":round(vn_count/len(corpus)*100,2),"vn_relevant_record_count":vn_relevant,"vn_relevant_record_percent":round(vn_relevant/len(corpus)*100,2),"required_domains_present":required_domains <= set(domain_counts),"excluded":dict(excluded)}
    audit["pass"]=audit["empty_chunks"]==audit["missing_provenance"]==audit["exact_duplicates"]==0 and audit["required_domains_present"]
    AUDIT.write_text(json.dumps(audit,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    manifest={"schema_version":"acceptance-vn-candidate-1","corpus_version":"offline-acceptance-vn-candidate","record_count":len(corpus),"corpus_hash":digest(canonical(corpus)),"candidate_sha256":digest(OUT.read_bytes()),"created_at":datetime.now(timezone.utc).isoformat(),"source_precedence":["VN official normative guidance","global public-health","foreign government","other verified reference"],"audit":audit,"previous_final_preserved":True}
    MANIFEST.write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"ok":audit["pass"],**manifest},ensure_ascii=False)); return 0 if audit["pass"] else 1


if __name__ == "__main__": raise SystemExit(main())
