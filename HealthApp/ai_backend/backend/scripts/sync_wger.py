"""
Script đồng bộ dữ liệu wger vào pgvector.

Chạy: python scripts/sync_wger.py
Hoặc dry-run: python scripts/sync_wger.py --dry-run

Tối ưu:
- Batch embedding (encode cả list cùng lúc, nhanh hơn 10-20x)
- Parallel upsert với asyncio.gather theo batch
- asyncpg connection pool
- Fetch exercises + ingredients song song

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 8.5, 8.6
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncpg
from sentence_transformers import SentenceTransformer

from config import settings
from models.schemas import WgerExerciseData, WgerIngredientData
from services.wger_service import wger_service
from db.database import AsyncSessionLocal

# Số items xử lý song song khi upsert vào DB
UPSERT_CONCURRENCY = 20
# Batch size cho embedding (encode nhiều text cùng lúc)
EMBED_BATCH_SIZE = 64


def build_exercise_text(exercise: WgerExerciseData) -> str:
    """Requirements: 2.2"""
    muscle_names = [m.name_en for m in exercise.muscles]
    muscles_text = ", ".join(muscle_names) if muscle_names else "No specific muscles"
    equipment_names = [e.name for e in exercise.equipment]
    equipment_text = ", ".join(equipment_names) if equipment_names else "No equipment"
    return (
        f"{exercise.name}. "
        f"Category: {exercise.category_name}. "
        f"Muscles: {muscles_text}. "
        f"Equipment: {equipment_text}. "
        f"{exercise.description}"
    )


def build_ingredient_text(ingredient: WgerIngredientData) -> str:
    """Requirements: 2.3"""
    energy_str = f"{ingredient.energy:.1f}" if ingredient.energy is not None else "N/A"
    protein_str = f"{ingredient.protein:.1f}" if ingredient.protein is not None else "N/A"
    carbs_str = f"{ingredient.carbohydrates:.1f}" if ingredient.carbohydrates is not None else "N/A"
    fat_str = f"{ingredient.fat:.1f}" if ingredient.fat is not None else "N/A"
    return (
        f"{ingredient.name}. "
        f"Energy: {energy_str} kcal/100g. "
        f"Protein: {protein_str}g/100g. "
        f"Carbohydrates: {carbs_str}g/100g. "
        f"Fat: {fat_str}g/100g."
    )


async def upsert_chunk(
    pool: asyncpg.Pool,
    category: str,
    title: str,
    content: str,
    metadata: dict,
    embedding: list[float],
) -> None:
    """Upsert một chunk + embedding. Dùng pool để parallel-safe. Requirements: 2.4, 2.5"""
    metadata_json = json.dumps(metadata, ensure_ascii=False)
    embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

    async with pool.acquire() as conn:
        # Upsert chunk
        existing_id = await conn.fetchval(
            "SELECT id FROM knowledge_chunks WHERE category = $1 AND metadata->>'wger_id' = $2",
            category,
            str(metadata["wger_id"]),
        )
        if existing_id:
            await conn.execute(
                "UPDATE knowledge_chunks SET title=$1, content=$2, metadata=$3::jsonb WHERE id=$4",
                title, content, metadata_json, existing_id,
            )
            chunk_id = existing_id
        else:
            chunk_id = await conn.fetchval(
                "INSERT INTO knowledge_chunks (category, title, content, metadata) VALUES ($1,$2,$3,$4::jsonb) RETURNING id",
                category, title, content, metadata_json,
            )
        # Upsert embedding
        await conn.execute(
            "INSERT INTO chunk_embeddings (chunk_id, embedding) VALUES ($1,$2::vector) ON CONFLICT (chunk_id) DO UPDATE SET embedding=EXCLUDED.embedding",
            chunk_id, embedding_str,
        )


async def upsert_batch(
    pool: asyncpg.Pool,
    batch: list[dict],
) -> None:
    """Upsert một batch items song song với asyncio.gather."""
    tasks = [
        upsert_chunk(pool, **item)
        for item in batch
    ]
    await asyncio.gather(*tasks)


def embed_batch(model: SentenceTransformer, texts: list[str]) -> list[list[float]]:
    """Encode cả batch cùng lúc — nhanh hơn nhiều so với từng cái."""
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        batch_size=EMBED_BATCH_SIZE,
        show_progress_bar=False,
    )
    return embeddings.tolist()


async def sync_items(
    items: list,
    build_text_fn,
    build_metadata_fn,
    category: str,
    label: str,
    model: SentenceTransformer,
    pool: asyncpg.Pool,
) -> int:
    """
    Generic sync: build texts → batch embed → parallel upsert.
    Dùng chung cho cả exercises và ingredients.
    """
    total = len(items)
    count = 0
    t0 = time.time()

    # Xử lý theo batch để không quá tải memory
    for batch_start in range(0, total, EMBED_BATCH_SIZE):
        batch_items = items[batch_start: batch_start + EMBED_BATCH_SIZE]

        # 1. Build texts cho cả batch
        texts = [build_text_fn(item) for item in batch_items]

        # 2. Embed cả batch cùng lúc (nhanh hơn nhiều)
        embeddings = await asyncio.get_event_loop().run_in_executor(
            None, embed_batch, model, texts
        )

        # 3. Chuẩn bị upsert data
        upsert_data = [
            {
                "category": category,
                "title": item.name,
                "content": text,
                "metadata": build_metadata_fn(item),
                "embedding": emb,
            }
            for item, text, emb in zip(batch_items, texts, embeddings)
        ]

        # 4. Upsert song song theo batch nhỏ hơn (tránh quá tải DB)
        for i in range(0, len(upsert_data), UPSERT_CONCURRENCY):
            sub_batch = upsert_data[i: i + UPSERT_CONCURRENCY]
            await upsert_batch(pool, sub_batch)

        count += len(batch_items)
        elapsed = time.time() - t0
        rate = count / elapsed if elapsed > 0 else 0
        eta = (total - count) / rate if rate > 0 else 0
        print(
            f"  {label}: {count}/{total} "
            f"({rate:.1f} items/s, ETA: {eta:.0f}s)",
            end="\r",
        )

    print(f"  {label}: {count}/{total} - DONE ({time.time()-t0:.1f}s)          ")
    return count


async def sync_exercises(model: SentenceTransformer, pool: asyncpg.Pool, dry_run: bool = False) -> int:
    """Requirements: 2.1, 2.2, 2.4, 2.5, 2.6"""
    async with AsyncSessionLocal() as db:
        exercises = await wger_service.fetch_all_exercises(db)

    if not exercises:
        print("  No exercises fetched from wger API")
        return 0

    print(f"  Fetched {len(exercises)} exercises")

    if dry_run:
        for ex in exercises[:5]:
            print(f"    - {ex.name} (ID: {ex.id})")
        if len(exercises) > 5:
            print(f"    ... and {len(exercises) - 5} more")
        return len(exercises)

    def build_metadata(ex: WgerExerciseData) -> dict:
        return {
            "wger_id": ex.id,
            "category_id": ex.category_id,
            "category_name": ex.category_name,
            "image_url": ex.image_url,
        }

    return await sync_items(
        exercises, build_exercise_text, build_metadata,
        "wger_exercise", "Exercises", model, pool,
    )


async def sync_ingredients(model: SentenceTransformer, pool: asyncpg.Pool, dry_run: bool = False) -> int:
    """Requirements: 2.1, 2.3, 2.4, 2.5, 2.6"""
    async with AsyncSessionLocal() as db:
        ingredients = await wger_service.fetch_all_ingredients(db)

    if not ingredients:
        print("  No ingredients fetched from wger API")
        return 0

    print(f"  Fetched {len(ingredients)} ingredients")

    if dry_run:
        for ing in ingredients[:5]:
            print(f"    - {ing.name} (ID: {ing.id})")
        if len(ingredients) > 5:
            print(f"    ... and {len(ingredients) - 5} more")
        return len(ingredients)

    def build_metadata(ing: WgerIngredientData) -> dict:
        return {
            "wger_id": ing.id,
            "energy": ing.energy,
            "protein": ing.protein,
            "carbohydrates": ing.carbohydrates,
            "fat": ing.fat,
        }

    return await sync_items(
        ingredients, build_ingredient_text, build_metadata,
        "wger_ingredient", "Ingredients", model, pool,
    )


async def main():
    """Requirements: 2.6, 8.5, 8.6"""
    parser = argparse.ArgumentParser(description="Sync wger data to pgvector")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be synced without writing to DB")
    parser.add_argument("--exercises-only", action="store_true",
                        help="Chi dong bo exercises")
    parser.add_argument("--ingredients-only", action="store_true",
                        help="Chi dong bo ingredients")
    args = parser.parse_args()

    print("=" * 60)
    print("Wger Data Sync Script")
    print("=" * 60)
    if args.dry_run:
        print("DRY RUN mode - khong ghi vao DB\n")

    t_total = time.time()

    # Load model một lần dùng chung
    model = None
    pool = None

    if not args.dry_run:
        print(f"Loading embedding model: {settings.embedding_model} ...")
        model = SentenceTransformer(settings.embedding_model)
        print("Model loaded.\n")

        dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        pool = await asyncpg.create_pool(dsn, min_size=5, max_size=UPSERT_CONCURRENCY)

    exercise_count = 0
    ingredient_count = 0

    do_exercises = not args.ingredients_only
    do_ingredients = not args.exercises_only

    if do_exercises and do_ingredients and not args.dry_run:
        # Fetch cả hai song song
        print("[1/2] Fetching + syncing exercises...")
        print("[2/2] Fetching ingredients (song song)...")
        exercise_count, ingredient_count = await asyncio.gather(
            sync_exercises(model, pool, dry_run=False),
            sync_ingredients(model, pool, dry_run=False),
        )
    else:
        if do_exercises:
            print("[1/2] Syncing exercises...")
            exercise_count = await sync_exercises(model, pool, dry_run=args.dry_run)
        if do_ingredients:
            print("[2/2] Syncing ingredients...")
            ingredient_count = await sync_ingredients(model, pool, dry_run=args.dry_run)

    if pool:
        await pool.close()

    elapsed = time.time() - t_total
    print("\n" + "=" * 60)
    print("Sync Summary")
    print("=" * 60)
    print(f"Exercises  : {exercise_count}")
    print(f"Ingredients: {ingredient_count}")
    print(f"Total      : {exercise_count + ingredient_count}")
    print(f"Time       : {elapsed:.1f}s")
    if args.dry_run:
        print("\n[DRY RUN] Khong co du lieu nao duoc ghi")
    else:
        print("\nSync completed!")


if __name__ == "__main__":
    asyncio.run(main())
