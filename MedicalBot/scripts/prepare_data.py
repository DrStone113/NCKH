"""
prepare_data.py — DatasetProcessor entry point cho Health Advice Chatbot.

Xử lý toàn bộ data pipeline:
  1. Đọc dataset y tế (Parquet + JSON) → insert vào medical_qa
  2. Xuất data/nlu.yml (Rasa 3.x)
  3. Đọc food.csv / food1.csv → insert vào nutrition
  4. Đọc Gym Exercises Dataset.xlsx → insert vào exercises

Cách dùng:
    python scripts/prepare_data.py \
        --dataset-dir dataset/ \
        --db-path knowledge_base/health_kb.db \
        --output-dir data/

Tham số tùy chọn:
    --lang vi          Dịch instruction/output sang tiếng Việt
    --max-records N    Giới hạn số bản ghi (dùng khi test)
"""

import argparse
import glob
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import yaml

# Cho phép import db_client từ actions/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "actions"))
from db_client import DBClient  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("prepare_data")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _translate_text(text: str, target_lang: str = "vi") -> str:
    """Dịch văn bản sang ngôn ngữ đích bằng deep_translator.

    Nếu dịch thất bại (exception hoặc chuỗi rỗng), trả về bản gốc và log WARNING.
    """
    try:
        from deep_translator import GoogleTranslator  # type: ignore

        result = GoogleTranslator(source="auto", target=target_lang).translate(text)
        if not result or not result.strip():
            logger.warning("Translation returned empty string, keeping original: %.60s", text)
            return text
        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("Translation failed (%s), keeping original: %.60s", exc, text)
        return text


def _is_valid_record(record: dict) -> bool:
    """Kiểm tra bản ghi có instruction và output không rỗng/null."""
    instruction = record.get("instruction")
    output = record.get("output")
    return bool(instruction and str(instruction).strip() and output and str(output).strip())


# ---------------------------------------------------------------------------
# Load medical QA data
# ---------------------------------------------------------------------------

def load_parquet_records(dataset_dir: str, max_records: Optional[int] = None) -> list[dict]:
    """Đọc 2 file Parquet cục bộ. Fallback sang HuggingFace nếu không tồn tại."""
    import pandas as pd  # noqa: PLC0415

    pattern = os.path.join(dataset_dir, "train-*.parquet")
    parquet_files = sorted(glob.glob(pattern))

    if parquet_files:
        logger.info("Found %d local Parquet file(s): %s", len(parquet_files), parquet_files)
        dfs = [pd.read_parquet(f) for f in parquet_files]
        df = pd.concat(dfs, ignore_index=True)
    else:
        logger.warning(
            "No local Parquet files found in '%s'. Falling back to HuggingFace Hub...",
            dataset_dir,
        )
        from datasets import load_dataset  # type: ignore  # noqa: PLC0415

        ds = load_dataset("knowrohit07/know_medical_dialogue_v2", split="train")
        df = ds.to_pandas()

    if max_records is not None:
        df = df.head(max_records)

    records = df.to_dict("records")
    logger.info("Loaded %d records from Parquet/HuggingFace", len(records))
    return records


def load_json_records(dataset_dir: str, max_records: Optional[int] = None) -> list[dict]:
    """Đọc và merge know_med_v4.json."""
    json_path = os.path.join(dataset_dir, "know_med_v4.json")
    if not os.path.exists(json_path):
        logger.warning("JSON file not found: %s — skipping", json_path)
        return []

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        # Có thể là {"train": [...], "test": [...]} hoặc {"data": [...]}
        records = []
        for v in data.values():
            if isinstance(v, list):
                records.extend(v)
    elif isinstance(data, list):
        records = data
    else:
        logger.warning("Unexpected JSON structure in %s — skipping", json_path)
        return []

    if max_records is not None:
        records = records[:max_records]

    logger.info("Loaded %d records from %s", len(records), json_path)
    return records


# ---------------------------------------------------------------------------
# Process and insert medical QA
# ---------------------------------------------------------------------------

def process_medical_source(
    records: list[dict],
    source: str,
    db: DBClient,
    lang: str = "en",
) -> tuple[int, int]:
    """Validate, optionally translate, và insert batch vào medical_qa.

    Returns:
        (processed_count, skipped_count)
    """
    valid_records: list[dict] = []
    skipped = 0

    for rec in records:
        if not _is_valid_record(rec):
            logger.warning(
                "Skipping invalid record from '%s' (missing instruction/output): %s",
                source,
                str(rec)[:120],
            )
            skipped += 1
            continue

        instruction = str(rec["instruction"]).strip()
        output = str(rec["output"]).strip()
        inp = str(rec.get("input", "")).strip()

        if lang == "vi":
            instruction = _translate_text(instruction, target_lang="vi")
            output = _translate_text(output, target_lang="vi")

        valid_records.append(
            {
                "instruction": instruction,
                "input": inp,
                "output": output,
                "source": source,
                "language": lang,
            }
        )

    if valid_records:
        db.batch_insert_medical_qa(valid_records)

    processed = len(valid_records)
    logger.info(
        "[%s] processed=%d  skipped=%d",
        source,
        processed,
        skipped,
    )
    return processed, skipped


# ---------------------------------------------------------------------------
# Export NLU YAML
# ---------------------------------------------------------------------------

def export_nlu_yaml(db: DBClient, output_dir: str) -> None:
    """Xuất data/nlu.yml hợp lệ Rasa 3.x với intent ask_health_advice.

    Rasa 3.x yêu cầu trường 'examples' là literal block scalar (|).
    Viết thủ công để đảm bảo đúng định dạng thay vì dùng yaml.dump.
    """
    # Lấy tất cả instruction từ medical_qa
    conn = db._get_connection()
    rows = conn.execute("SELECT instruction FROM medical_qa").fetchall()
    db._release_connection(conn)

    instructions = [row[0] for row in rows if row[0] and row[0].strip()]

    if not instructions:
        logger.warning("No instructions found in medical_qa — NLU YAML will be empty")

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "nlu.yml")

    # Viết thủ công để đảm bảo literal block scalar (|) đúng cú pháp Rasa 3.x
    with open(output_path, "w", encoding="utf-8") as f:
        f.write('version: "3.1"\n')
        f.write("nlu:\n")
        f.write("- intent: ask_health_advice\n")
        f.write("  examples: |\n")
        for instr in instructions:
            # Escape dấu gạch đầu dòng trong nội dung để tránh nhầm với YAML list
            line = instr.strip().replace("\n", " ")
            f.write(f"    - {line}\n")

    # Validate: đảm bảo file có thể parse được
    with open(output_path, encoding="utf-8") as f:
        parsed = yaml.safe_load(f)
    assert "nlu" in parsed, "NLU YAML thiếu key 'nlu'"

    logger.info("Exported NLU YAML to %s (%d examples)", output_path, len(instructions))


# ---------------------------------------------------------------------------
# Load nutrition data
# ---------------------------------------------------------------------------

def load_nutrition(dataset_dir: str, db: DBClient) -> tuple[int, int]:
    """Đọc food.csv (fallback food1.csv), insert vào nutrition.

    Returns:
        (processed_count, skipped_count)
    """
    import pandas as pd  # noqa: PLC0415

    food_path = os.path.join(dataset_dir, "food.csv")
    if not os.path.exists(food_path):
        food_path = os.path.join(dataset_dir, "food1.csv")
        if not os.path.exists(food_path):
            logger.warning("Neither food.csv nor food1.csv found in '%s' — skipping", dataset_dir)
            return 0, 0

    logger.info("Reading nutrition data from %s", food_path)
    df = pd.read_csv(food_path)

    # Column mapping
    col_map = {
        "Category": "category",
        "Description": "description",
        "Data.Kilocalories": "kilocalories",
        "Data.Protein": "protein_g",
        "Data.Carbohydrate": "carbohydrate_g",
        "Data.Fat.Total Lipid": "fat_total_g",
        "Data.Fiber": "fiber_g",
    }

    # Chỉ giữ các cột tồn tại trong file
    available_cols = {k: v for k, v in col_map.items() if k in df.columns}
    df_mapped = df[list(available_cols.keys())].rename(columns=available_cols)

    records = []
    skipped = 0
    for _, row in df_mapped.iterrows():
        desc = row.get("description")
        if not desc or (isinstance(desc, float)):
            skipped += 1
            continue
        rec = {"description": str(desc).strip(), "source": "usda"}
        for field in ("category", "kilocalories", "protein_g", "carbohydrate_g", "fat_total_g", "fiber_g"):
            val = row.get(field)
            if val is not None and not (isinstance(val, float) and __import__("math").isnan(val)):
                rec[field] = val
        records.append(rec)

    if records:
        db.batch_insert_nutrition(records)

    logger.info("[nutrition] processed=%d  skipped=%d", len(records), skipped)
    return len(records), skipped


# ---------------------------------------------------------------------------
# Load exercises data
# ---------------------------------------------------------------------------

def load_exercises(dataset_dir: str, db: DBClient) -> tuple[int, int]:
    """Đọc Gym Exercises Dataset.xlsx, insert vào exercises.

    Returns:
        (processed_count, skipped_count)
    """
    import pandas as pd  # noqa: PLC0415

    xlsx_path = os.path.join(dataset_dir, "Gym Exercises Dataset.xlsx")
    if not os.path.exists(xlsx_path):
        logger.warning("Gym Exercises Dataset.xlsx not found in '%s' — skipping", dataset_dir)
        return 0, 0

    logger.info("Reading exercises data from %s", xlsx_path)
    df = pd.read_excel(xlsx_path, engine="openpyxl")

    logger.info("Exercises columns: %s", list(df.columns))

    # Mapping linh hoạt — dùng tên cột thực tế (case-insensitive)
    col_lower = {c.lower(): c for c in df.columns}

    def _get_col(candidates: list[str]) -> Optional[str]:
        for c in candidates:
            if c.lower() in col_lower:
                return col_lower[c.lower()]
        return None

    name_col = _get_col(["name", "exercise name", "exercise", "title"])
    category_col = _get_col(["category", "type", "exercise type"])
    muscle_col = _get_col(["muscle group", "muscle", "primary muscle", "muscles", "body part"])
    equipment_col = _get_col(["equipment", "equipment needed"])
    difficulty_col = _get_col(["difficulty", "level", "experience level"])
    desc_col = _get_col(["description", "desc"])
    instructions_col = _get_col(["instructions", "steps", "how to"])

    if name_col is None:
        logger.warning("Could not find 'name' column in exercises XLSX — skipping")
        return 0, 0

    records = []
    skipped = 0
    for _, row in df.iterrows():
        name_val = row.get(name_col)
        if not name_val or (isinstance(name_val, float)):
            skipped += 1
            continue

        rec: dict = {"name": str(name_val).strip()}
        if category_col:
            rec["category"] = str(row[category_col]).strip() if row[category_col] else None
        if muscle_col:
            rec["muscle_group"] = str(row[muscle_col]).strip() if row[muscle_col] else None
        if equipment_col:
            rec["equipment"] = str(row[equipment_col]).strip() if row[equipment_col] else None
        if difficulty_col:
            rec["difficulty"] = str(row[difficulty_col]).strip() if row[difficulty_col] else None
        if desc_col:
            rec["description"] = str(row[desc_col]).strip() if row[desc_col] else None
        if instructions_col:
            rec["instructions"] = str(row[instructions_col]).strip() if row[instructions_col] else None

        records.append(rec)

    if records:
        db.batch_insert_exercises(records)

    logger.info("[exercises] processed=%d  skipped=%d", len(records), skipped)
    return len(records), skipped


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DatasetProcessor — chuẩn bị dữ liệu cho Health Advice Chatbot"
    )
    parser.add_argument(
        "--db-path",
        default="knowledge_base/health_kb.db",
        help="Đường dẫn đến file SQLite (default: knowledge_base/health_kb.db)",
    )
    parser.add_argument(
        "--dataset-dir",
        default="dataset/",
        help="Thư mục chứa các file dataset (default: dataset/)",
    )
    parser.add_argument(
        "--output-dir",
        default="data/",
        help="Thư mục xuất file nlu.yml (default: data/)",
    )
    parser.add_argument(
        "--lang",
        default="en",
        choices=["en", "vi"],
        help="Ngôn ngữ lưu vào DB: 'en' (default) hoặc 'vi' (dịch sang tiếng Việt)",
    )
    parser.add_argument(
        "--max-records",
        type=int,
        default=None,
        help="Giới hạn số bản ghi mỗi nguồn (dùng khi test)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    logger.info("=== DatasetProcessor bắt đầu ===")
    logger.info("  db-path    : %s", args.db_path)
    logger.info("  dataset-dir: %s", args.dataset_dir)
    logger.info("  output-dir : %s", args.output_dir)
    logger.info("  lang       : %s", args.lang)
    logger.info("  max-records: %s", args.max_records)

    # Khởi tạo DB
    os.makedirs(os.path.dirname(args.db_path) or ".", exist_ok=True)
    db = DBClient(args.db_path)
    db.init_db()

    total_processed = 0
    total_skipped = 0

    # --- 1. Parquet ---
    try:
        parquet_records = load_parquet_records(args.dataset_dir, args.max_records)
        p, s = process_medical_source(parquet_records, source="parquet", db=db, lang=args.lang)
        total_processed += p
        total_skipped += s
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to process Parquet data: %s", exc)

    # --- 2. JSON ---
    try:
        json_records = load_json_records(args.dataset_dir, args.max_records)
        p, s = process_medical_source(json_records, source="json", db=db, lang=args.lang)
        total_processed += p
        total_skipped += s
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to process JSON data: %s", exc)

    logger.info("=== Medical QA tổng kết: processed=%d  skipped=%d ===", total_processed, total_skipped)

    # --- 3. NLU YAML ---
    try:
        export_nlu_yaml(db, args.output_dir)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to export NLU YAML: %s", exc)

    # --- 4. Nutrition ---
    try:
        load_nutrition(args.dataset_dir, db)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to process nutrition data: %s", exc)

    # --- 5. Exercises ---
    try:
        load_exercises(args.dataset_dir, db)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to process exercises data: %s", exc)

    db.close()
    logger.info("=== DatasetProcessor hoàn tất ===")


if __name__ == "__main__":
    main()
