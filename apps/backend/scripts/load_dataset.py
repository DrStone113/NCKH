"""Nạp dataset dinh dưỡng & bài tập vào knowledge_chunks + pgvector.

Chạy:
    python scripts/load_dataset.py            # nạp phần còn thiếu
    python scripts/load_dataset.py --rebuild  # xoá và nạp lại toàn bộ

Vì sao viết lại
---------------
Bản cũ chỉ nạp ``exercises.json`` (10 mục) và ``nutrition.json`` (11 mục) —
tổng cộng 21 chunk. Trong khi đó ``vietnamese_foods.json`` (526 thực phẩm từ
Bảng thành phần thực phẩm Việt Nam của Viện Dinh dưỡng, Bộ Y tế) và
``vietnamese_dishes.json`` (90 món ăn) nằm ngay cạnh mà không hề được dùng.
Kho RAG vì thế gần như rỗng, và đó là lý do chatbot hiếm khi tra được số liệu
dinh dưỡng Việt Nam.

Bản này nạp cả 4 nguồn (~637 chunk) và bổ sung ba thứ bản cũ thiếu:

1. **Idempotent.** ID sinh bằng UUID5 từ (category, title) nên chạy lại không
   nhân bản dữ liệu — bản cũ dùng ID ngẫu nhiên, chạy hai lần là kho RAG có
   hai bản của mọi thứ.
2. **Batch embedding.** Encode theo lô thay vì gọi model 637 lần; nhanh hơn
   khoảng một bậc độ lớn.
3. **Nhãn mô tả tự động.** Mỗi thực phẩm được gắn các nhãn như "giàu đạm",
   "giàu sắt", "ít béo" dựa trên ngưỡng dinh dưỡng thật. Không có nhãn này thì
   câu hỏi "món nào giàu sắt" không thể khớp được, vì bản thân con số
   "2.4 mg" trong text không mang ngữ nghĩa "giàu" đối với embedding.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import uuid
from pathlib import Path
from typing import Any, Iterable

# Add backend/ to path
sys.path.insert(0, str(Path(__file__).parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import asyncpg
from sentence_transformers import SentenceTransformer

from config import settings

DATA_DIR = Path(__file__).parent.parent / "data"

# Namespace cố định để sinh UUID5 ổn định giữa các lần chạy.
NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")

EMBED_BATCH_SIZE = 64

# Authoritative offline corpus definition shared with research mode. Raw and
# valid counts are explicit: one food row (stt=450, "Papaya jam") has no
# Vietnamese title and is therefore intentionally not chunked.
APPROVED_CORPUS_SOURCES: tuple[dict[str, Any], ...] = (
    {
        "dataset_file": "vietnamese_foods.json",
        "source_type": "official_food_composition_table",
        "source_name": "Vietnam Food Composition Table - National Institute of Nutrition",
        "expected_raw_count": 526,
        "expected_valid_count": 525,
    },
    {
        "dataset_file": "vietnamese_dishes.json",
        "source_type": "curated_offline_dataset",
        "source_name": "HealthApp Vietnamese dish catalog",
        "expected_raw_count": 90,
        "expected_valid_count": 90,
    },
    {
        "dataset_file": "nutrition.json",
        "source_type": "curated_offline_dataset",
        "source_name": "HealthApp nutrition catalog",
        "expected_raw_count": 11,
        "expected_valid_count": 11,
    },
    {
        "dataset_file": "exercises.json",
        "source_type": "curated_offline_dataset",
        "source_name": "HealthApp exercise catalog",
        "expected_raw_count": 10,
        "expected_valid_count": 10,
    },
)

APPROVED_CORPUS_RECORD_COUNT = sum(
    int(source["expected_valid_count"]) for source in APPROVED_CORPUS_SOURCES
)


# --------------------------------------------------------------------------- #
# Phân nhóm thực phẩm theo mã số của Viện Dinh dưỡng
# --------------------------------------------------------------------------- #

# Chữ số đầu của `ma_so` là mã nhóm trong Bảng thành phần thực phẩm Việt Nam.
FOOD_GROUPS: dict[str, str] = {
    "1": "Ngũ cốc và sản phẩm chế biến",
    "2": "Khoai củ và sản phẩm chế biến",
    "3": "Hạt và quả giàu đạm, giàu béo",
    "4": "Rau, củ, quả dùng làm rau",
    "5": "Quả chín",
    "6": "Dầu, mỡ, bơ",
    "7": "Thịt và sản phẩm chế biến",
    "8": "Thủy sản và sản phẩm chế biến",
    "9": "Trứng và sản phẩm chế biến",
}


def food_group(item: dict[str, Any]) -> str:
    return FOOD_GROUPS.get(str(item.get("ma_so", ""))[:1], "Thực phẩm khác")


# --------------------------------------------------------------------------- #
# Nhãn dinh dưỡng
# --------------------------------------------------------------------------- #

# CẢNH BÁO CHẤT LƯỢNG DỮ LIỆU
# ----------------------------
# Trong ``vietnamese_foods.json`` các cột khoáng chất từ `magnesium` trở đi bị
# LỆCH khi parse từ PDF gốc. Đối chiếu với số liệu đã biết:
#
#   Trứng gà — JSON: potassium=210, sodium=176, zinc=158
#              Thực tế: phospho=210, kali=176, natri=158
#
# tức là mỗi trường đang giữ giá trị của trường liền trước nó, và `magnesium`
# rỗng ở 525/526 dòng. Vì vậy các trường dưới đây KHÔNG được dùng cho tới khi
# parser PDF được chạy lại:
#
#   magnesium, manganese, phosphorus, potassium, sodium, zinc, copper
#
# Các trường đã đối chiếu và tin được: energy_kcal, protein, fat,
# carbohydrates, fiber, water, calcium, iron, vitamin_c, vitamin_a,
# beta_carotene, cholesterol, và nhóm acid amin.
#
# Thà thiếu thông tin còn hơn đưa cho người dùng con số natri sai nhãn là kẽm.
UNRELIABLE_FIELDS: frozenset[str] = frozenset({
    "magnesium", "manganese", "phosphorus", "potassium", "sodium",
    "zinc", "copper",
})

# (khóa, nhãn, ngưỡng, hướng) — tính trên 100g phần ăn được.
# Ngưỡng lấy theo tinh thần quy định ghi nhãn dinh dưỡng của EU/FDA, làm tròn
# cho dễ đọc. Mục đích không phải là tuyên bố pháp lý mà là giúp embedding bắt
# được truy vấn dạng "thực phẩm giàu X".
_LABEL_RULES: tuple[tuple[str, str, float, str], ...] = (
    ("protein", "giàu đạm", 15.0, "high"),
    ("protein", "ít đạm", 2.0, "low"),
    ("fiber", "giàu chất xơ", 3.0, "high"),
    ("fat", "ít béo", 3.0, "low"),
    ("fat", "nhiều béo", 20.0, "high"),
    ("energy_kcal", "ít calo", 80.0, "low"),
    ("energy_kcal", "nhiều calo", 300.0, "high"),
    ("calcium", "giàu canxi", 120.0, "high"),
    ("iron", "giàu sắt", 4.0, "high"),
    ("vitamin_c", "giàu vitamin C", 30.0, "high"),
    ("vitamin_a", "giàu vitamin A", 120.0, "high"),
    ("beta_carotene", "giàu beta-caroten", 600.0, "high"),
    ("cholesterol", "nhiều cholesterol", 100.0, "high"),
)

assert not (
    {rule[0] for rule in _LABEL_RULES} & UNRELIABLE_FIELDS
), "Một nhãn đang dùng trường dữ liệu bị lệch cột"


def _num(value: Any) -> float | None:
    """Ép về float, trả None cho ô trống / dấu '-' của bảng gốc."""
    if value is None or value == "" or value == "-":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def nutrition_labels(item: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    for key, label, threshold, direction in _LABEL_RULES:
        value = _num(item.get(key))
        if value is None:
            continue
        if direction == "high" and value >= threshold:
            labels.append(label)
        elif direction == "low" and value <= threshold:
            labels.append(label)
    return labels


# --------------------------------------------------------------------------- #
# Sinh text để embed
# --------------------------------------------------------------------------- #

def _fmt(value: Any, unit: str) -> str | None:
    number = _num(value)
    if number is None:
        return None
    text = f"{number:g}"
    return f"{text}{unit}"


def make_food_text(item: dict[str, Any]) -> str:
    """Text cho một thực phẩm trong bảng thành phần.

    Viết thành câu tiếng Việt tự nhiên chứ không phải bảng key–value: model
    embedding đa ngôn ngữ khớp câu tốt hơn nhiều so với khớp chuỗi tham số.
    """
    name = item.get("name", "")
    name_en = item.get("name_en", "")
    parts = [f"{name} ({name_en})." if name_en else f"{name}."]
    parts.append(f"Nhóm: {food_group(item)}.")

    macros = [
        ("Năng lượng", _fmt(item.get("energy_kcal"), " kcal")),
        ("chất đạm", _fmt(item.get("protein"), "g")),
        ("chất béo", _fmt(item.get("fat"), "g")),
        ("carbohydrate", _fmt(item.get("carbohydrates"), "g")),
        ("chất xơ", _fmt(item.get("fiber"), "g")),
    ]
    macro_text = ", ".join(f"{label} {value}" for label, value in macros if value)
    if macro_text:
        parts.append(f"Trong 100g phần ăn được: {macro_text}.")

    # Chỉ liệt kê các vi chất đã đối chiếu được — xem UNRELIABLE_FIELDS.
    micros = [
        ("canxi", _fmt(item.get("calcium"), "mg")),
        ("sắt", _fmt(item.get("iron"), "mg")),
        ("vitamin C", _fmt(item.get("vitamin_c"), "mg")),
        ("vitamin A", _fmt(item.get("vitamin_a"), " µg")),
        ("beta-caroten", _fmt(item.get("beta_carotene"), " µg")),
    ]
    micro_text = ", ".join(f"{label} {value}" for label, value in micros if value)
    if micro_text:
        parts.append(f"Vi chất: {micro_text}.")

    cholesterol = _fmt(item.get("cholesterol"), "mg")
    if cholesterol:
        parts.append(f"Cholesterol {cholesterol}.")

    waste = _num(item.get("thai_bo_pct"))
    if waste:
        parts.append(f"Tỷ lệ thải bỏ {waste:g}%.")

    labels = nutrition_labels(item)
    if labels:
        parts.append(f"Đặc điểm: {', '.join(labels)}.")

    parts.append("Nguồn: Bảng thành phần thực phẩm Việt Nam, Viện Dinh dưỡng - Bộ Y tế.")
    return " ".join(parts)


def make_dish_text(item: dict[str, Any]) -> str:
    """Text cho một món ăn Việt Nam (thành phần + calo ước tính)."""
    name = item.get("name", "")
    meal_types = item.get("meal_types") or []
    meal_vi = {
        "breakfast": "bữa sáng", "lunch": "bữa trưa",
        "dinner": "bữa tối", "snack": "bữa phụ",
    }
    meals = ", ".join(meal_vi.get(m, m) for m in meal_types)

    ingredients = item.get("ingredients") or []
    ing_text = ", ".join(
        f"{ing.get('name', '')} {ing.get('grams', 0)}g"
        for ing in ingredients if isinstance(ing, dict)
    )

    parts = [f"Món ăn Việt Nam: {name}."]
    if meals:
        parts.append(f"Thường ăn vào {meals}.")
    calories = _num(item.get("estimated_calories"))
    if calories:
        parts.append(f"Ước tính khoảng {calories:g} kcal cho một khẩu phần.")
    if ing_text:
        parts.append(f"Nguyên liệu: {ing_text}.")
    return " ".join(parts)


def make_exercise_text(item: dict[str, Any]) -> str:
    muscles = ", ".join(item.get("target_muscle", []))
    tags = ", ".join(item.get("tags", []))
    parts = [f"Bài tập: {item.get('name', '')}."]
    if muscles:
        parts.append(f"Nhóm cơ tác động: {muscles}.")
    if item.get("difficulty"):
        parts.append(f"Độ khó: {item['difficulty']}.")
    if item.get("equipment"):
        parts.append(f"Thiết bị: {item['equipment']}.")
    if item.get("instructions"):
        parts.append(f"Cách thực hiện: {item['instructions']}")
    if item.get("benefits"):
        parts.append(f"Lợi ích: {item['benefits']}")
    if tags:
        parts.append(f"Từ khóa: {tags}.")
    return " ".join(parts)


def make_nutrition_text(item: dict[str, Any]) -> str:
    ingredients = ", ".join(item.get("ingredients", []))
    tags = ", ".join(item.get("tags", []))
    parts = [f"{item.get('name', '')}."]
    if item.get("category"):
        parts.append(f"Loại: {item['category']}.")
    parts.append(
        f"Một khẩu phần ({item.get('serving_size', 'trung bình')}) cung cấp "
        f"khoảng {item.get('calories', 0)} kcal, "
        f"{item.get('protein', 0)}g đạm, "
        f"{item.get('carbs', 0)}g tinh bột, "
        f"{item.get('fat', 0)}g chất béo."
    )
    if ingredients:
        parts.append(f"Nguyên liệu: {ingredients}.")
    if tags:
        parts.append(f"Từ khóa: {tags}.")
    return " ".join(parts)


# --------------------------------------------------------------------------- #
# Thu thập chunk
# --------------------------------------------------------------------------- #

def _load_json(filename: str) -> list[dict[str, Any]]:
    path = DATA_DIR / filename
    if not path.is_file():
        print(f"  [bỏ qua] không tìm thấy {filename}")
        return []
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, list) else []


def _sha256_file(filename: str) -> str:
    digest = hashlib.sha256()
    with (DATA_DIR / filename).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_dataset_hashes() -> dict[str, str]:
    """Return SHA-256 for every approved source file."""

    return {
        str(source["dataset_file"]): _sha256_file(str(source["dataset_file"]))
        for source in APPROVED_CORPUS_SOURCES
    }


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _chunk_content_hash(
    category: str, title: str, content: str, metadata: dict[str, Any]
) -> str:
    return hashlib.sha256(
        _canonical_json(
            {
                "category": category,
                "title": title,
                "content": content,
                "metadata": metadata,
            }
        )
    ).hexdigest()


def _chunk_id(category: str, title: str) -> uuid.UUID:
    """UUID5 ổn định để chạy lại script không tạo bản trùng."""
    return uuid.uuid5(NAMESPACE, f"{category}::{title}")


def collect_chunks() -> list[dict[str, Any]]:
    """Trả về danh sách chunk từ mọi nguồn dữ liệu có sẵn."""
    chunks: list[dict[str, Any]] = []
    dataset_hashes = source_dataset_hashes()
    source_specs = {
        str(source["dataset_file"]): source for source in APPROVED_CORPUS_SOURCES
    }

    def add(
        category: str,
        title: str,
        content: str,
        metadata: dict[str, Any],
        *,
        dataset_file: str,
        source_record_id: str,
    ) -> None:
        title = str(title).strip()
        content = str(content).strip()
        if not title or not content:
            return
        source = source_specs[dataset_file]
        normalized_metadata = {
            **metadata,
            "source_type": source["source_type"],
            "source_name": source["source_name"],
            "source_url": None,
            "source_record_id": source_record_id,
            "dataset_file": dataset_file,
            "dataset_hash": dataset_hashes[dataset_file],
        }
        normalized_metadata["content_hash"] = _chunk_content_hash(
            category, title, content, normalized_metadata
        )
        chunks.append({
            "id": _chunk_id(category, title),
            "category": category,
            "title": title,
            "content": content,
            "metadata": normalized_metadata,
        })

    # 1. Bảng thành phần thực phẩm Việt Nam — nguồn lớn nhất và chuẩn nhất.
    foods = _load_json("vietnamese_foods.json")
    for item in foods:
        add("food", item.get("name", ""), make_food_text(item), {
            "ma_so": item.get("ma_so"),
            "name_en": item.get("name_en", ""),
            "nhom": food_group(item),
            "energy_kcal": _num(item.get("energy_kcal")),
            "protein": _num(item.get("protein")),
            "fat": _num(item.get("fat")),
            "carbohydrates": _num(item.get("carbohydrates")),
            "fiber": _num(item.get("fiber")),
            "nhan": nutrition_labels(item),
            "nguon": "Viện Dinh dưỡng - Bộ Y tế",
        }, dataset_file="vietnamese_foods.json", source_record_id=f"ma_so:{item.get('ma_so') or item.get('stt')}")
    print(f"  vietnamese_foods.json  -> {len(foods)} thực phẩm")

    # 2. Món ăn Việt Nam
    dishes = _load_json("vietnamese_dishes.json")
    for item in dishes:
        add("food", f"Món {item.get('name', '')}", make_dish_text(item), {
            "meal_types": item.get("meal_types", []),
            "estimated_calories": _num(item.get("estimated_calories")),
            "loai": "mon_an",
        }, dataset_file="vietnamese_dishes.json", source_record_id=f"id:{item.get('id')}")
    print(f"  vietnamese_dishes.json -> {len(dishes)} món ăn")

    # 3. Món ăn có sẵn macro chi tiết
    nutrition = _load_json("nutrition.json")
    for item in nutrition:
        add("food", item.get("name", ""), make_nutrition_text(item), {
            "calories": item.get("calories", 0),
            "protein": item.get("protein", 0),
            "carbs": item.get("carbs", 0),
            "fat": item.get("fat", 0),
            "serving_size": item.get("serving_size", ""),
        }, dataset_file="nutrition.json", source_record_id=f"id:{item.get('id')}")
    print(f"  nutrition.json         -> {len(nutrition)} món")

    # 4. Bài tập
    exercises = _load_json("exercises.json")
    for item in exercises:
        add("exercise", item.get("name", ""), make_exercise_text(item), {
            "difficulty": item.get("difficulty", ""),
            "equipment": item.get("equipment", ""),
            "target_muscle": item.get("target_muscle", []),
        }, dataset_file="exercises.json", source_record_id=f"id:{item.get('id')}")
    print(f"  exercises.json         -> {len(exercises)} bài tập")

    # Khử trùng theo id (cùng tên + cùng category thì giữ bản đầu tiên).
    unique: dict[uuid.UUID, dict[str, Any]] = {}
    for chunk in chunks:
        unique.setdefault(chunk["id"], chunk)
    dropped = len(chunks) - len(unique)
    if dropped:
        print(f"  (bỏ {dropped} mục trùng tên)")
    return list(unique.values())


# --------------------------------------------------------------------------- #
# Ghi vào DB
# --------------------------------------------------------------------------- #

def _batched(items: list[Any], size: int) -> Iterable[list[Any]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _get_asyncpg_dsn(database_url: str) -> str:
    """Chuyển SQLAlchemy URL sang asyncpg DSN."""
    return database_url.replace("postgresql+asyncpg://", "postgresql://")


async def load_data(rebuild: bool = False) -> None:
    print("Đang đọc dữ liệu...")
    chunks = collect_chunks()
    if not chunks:
        print("Không có dữ liệu nào để nạp.")
        return
    print(f"Tổng cộng {len(chunks)} chunk.\n")

    dsn = _get_asyncpg_dsn(settings.database_url)
    conn = await asyncpg.connect(dsn)

    try:
        if rebuild:
            # Chỉ xoá dữ liệu nạp từ file, giữ nguyên kiến thức bot tự học được
            # từ web (những row đó có source_url khác NULL).
            deleted = await conn.execute(
                "DELETE FROM knowledge_chunks WHERE source_url IS NULL"
            )
            print(f"--rebuild: đã xoá dữ liệu offline cũ ({deleted}).\n")

        existing = await conn.fetch("SELECT id FROM knowledge_chunks")
        existing_ids = {row["id"] for row in existing}
        todo = [c for c in chunks if c["id"] not in existing_ids]
        skipped = len(chunks) - len(todo)
        if skipped:
            print(f"Bỏ qua {skipped} chunk đã có trong DB.")
        if not todo:
            print("Kho kiến thức đã đầy đủ, không có gì để nạp.")
            return

        print(f"Khởi tạo embedding model: {settings.embedding_model} ...")
        model = SentenceTransformer(settings.embedding_model)
        print("Model sẵn sàng.\n")

        inserted = 0
        for batch in _batched(todo, EMBED_BATCH_SIZE):
            vectors = model.encode(
                [c["content"] for c in batch],
                batch_size=EMBED_BATCH_SIZE,
                show_progress_bar=False,
            )
            rows = []
            embed_rows = []
            for chunk, vector in zip(batch, vectors):
                rows.append((
                    chunk["id"],
                    chunk["category"],
                    chunk["title"][:500],
                    chunk["content"],
                    json.dumps(chunk["metadata"], ensure_ascii=False),
                ))
                embed_rows.append((
                    chunk["id"],
                    "[" + ",".join(str(v) for v in vector.tolist()) + "]",
                ))

            async with conn.transaction():
                await conn.executemany(
                    """
                    INSERT INTO knowledge_chunks (id, category, title, content, metadata)
                    VALUES ($1, $2, $3, $4, $5::jsonb)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    rows,
                )
                await conn.executemany(
                    """
                    INSERT INTO chunk_embeddings (chunk_id, embedding)
                    VALUES ($1, $2::vector)
                    ON CONFLICT (chunk_id) DO NOTHING
                    """,
                    embed_rows,
                )
            inserted += len(batch)
            print(f"  đã nạp {inserted}/{len(todo)}")

        total = await conn.fetchval("SELECT COUNT(*) FROM knowledge_chunks")
        embedded = await conn.fetchval("SELECT COUNT(*) FROM chunk_embeddings")
        print(f"\nXong. Nạp mới {inserted} chunk.")
        print(f"Kho kiến thức hiện có {total} chunk, {embedded} chunk đã có embedding.")

    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Nạp dataset vào knowledge base")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Xoá toàn bộ dữ liệu offline cũ rồi nạp lại (giữ kiến thức tự học từ web)",
    )
    args = parser.parse_args()
    asyncio.run(load_data(rebuild=args.rebuild))
