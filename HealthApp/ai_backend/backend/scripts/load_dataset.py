"""
Script nạp Dataset_VN vào pgvector.
Chạy: docker compose --profile init up data_loader
Hoặc local: python scripts/load_dataset.py
"""
import asyncio
import json
import sys
import uuid
from pathlib import Path

# Add backend/ to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sentence_transformers import SentenceTransformer
import asyncpg
from config import settings

DATA_DIR = Path(__file__).parent.parent / "data"


def make_exercise_text(item: dict) -> str:
    """Tạo text representation để embed cho bài tập."""
    muscles = ", ".join(item.get("target_muscle", []))
    tags = ", ".join(item.get("tags", []))
    return (
        f"{item['name']}. "
        f"Nhóm cơ: {muscles}. "
        f"Độ khó: {item.get('difficulty', '')}. "
        f"Thiết bị: {item.get('equipment', '')}. "
        f"Hướng dẫn: {item.get('instructions', '')}. "
        f"Tags: {tags}."
    )


def make_nutrition_text(item: dict) -> str:
    """Tạo text representation để embed cho món ăn."""
    ingredients = ", ".join(item.get("ingredients", []))
    tags = ", ".join(item.get("tags", []))
    return (
        f"{item['name']}. "
        f"Loại: {item.get('category', '')}. "
        f"Calo: {item.get('calories', 0)} kcal. "
        f"Protein: {item.get('protein', 0)}g, Carbs: {item.get('carbs', 0)}g, Fat: {item.get('fat', 0)}g. "
        f"Khẩu phần: {item.get('serving_size', '')}. "
        f"Nguyên liệu: {ingredients}. "
        f"Tags: {tags}."
    )


def _get_asyncpg_dsn(database_url: str) -> str:
    """Chuyển đổi SQLAlchemy URL sang asyncpg DSN."""
    return database_url.replace("postgresql+asyncpg://", "postgresql://")


async def load_data():
    # 1. Load JSON files
    exercises_path = DATA_DIR / "exercises.json"
    nutrition_path = DATA_DIR / "nutrition.json"

    with open(exercises_path, encoding="utf-8") as f:
        exercises = json.load(f)

    with open(nutrition_path, encoding="utf-8") as f:
        nutrition_items = json.load(f)

    print(f"Loaded {len(exercises)} exercises and {len(nutrition_items)} nutrition items from JSON.")

    # 2. Init SentenceTransformer
    print(f"Loading embedding model: {settings.embedding_model} ...")
    model = SentenceTransformer(settings.embedding_model)
    print("Embedding model ready.")

    # 3. Connect asyncpg
    dsn = _get_asyncpg_dsn(settings.database_url)
    conn = await asyncpg.connect(dsn)

    try:
        exercise_count = 0
        nutrition_count = 0

        # 4a. Insert exercises
        for item in exercises:
            text = make_exercise_text(item)
            embedding = model.encode(text).tolist()

            metadata = {
                "difficulty": item.get("difficulty", ""),
                "equipment": item.get("equipment", ""),
                "target_muscle": item.get("target_muscle", []),
            }

            # Insert knowledge_chunk
            chunk_id = await conn.fetchval(
                """
                INSERT INTO knowledge_chunks (category, title, content, metadata)
                VALUES ($1, $2, $3, $4::jsonb)
                RETURNING id
                """,
                "exercise",
                item["name"],
                text,
                json.dumps(metadata, ensure_ascii=False),
            )

            # Insert embedding — pgvector expects "[x,y,z,...]" string format
            embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
            await conn.execute(
                """
                INSERT INTO chunk_embeddings (chunk_id, embedding)
                VALUES ($1, $2::vector)
                ON CONFLICT (chunk_id) DO NOTHING
                """,
                chunk_id,
                embedding_str,
            )

            exercise_count += 1
            print(f"[exercise] Loaded: {item['name']}")

        # 4b. Insert nutrition items
        for item in nutrition_items:
            text = make_nutrition_text(item)
            embedding = model.encode(text).tolist()

            metadata = {
                "calories": item.get("calories", 0),
                "protein": item.get("protein", 0),
                "carbs": item.get("carbs", 0),
                "fat": item.get("fat", 0),
                "serving_size": item.get("serving_size", ""),
            }

            # Insert knowledge_chunk
            chunk_id = await conn.fetchval(
                """
                INSERT INTO knowledge_chunks (category, title, content, metadata)
                VALUES ($1, $2, $3, $4::jsonb)
                RETURNING id
                """,
                "food",
                item["name"],
                text,
                json.dumps(metadata, ensure_ascii=False),
            )

            # Insert embedding — pgvector expects "[x,y,z,...]" string format
            embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
            await conn.execute(
                """
                INSERT INTO chunk_embeddings (chunk_id, embedding)
                VALUES ($1, $2::vector)
                ON CONFLICT (chunk_id) DO NOTHING
                """,
                chunk_id,
                embedding_str,
            )

            nutrition_count += 1
            print(f"[nutrition] Loaded: {item['name']}")

        # 5. Summary
        print(f"\nLoaded {exercise_count} exercises, {nutrition_count} nutrition items")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(load_data())
