"""
ingest.py — Load SQLite → ChromaDB (Đa luồng + GPU)

Sử dụng:
    python ingest.py                    # Mặc định
    python ingest.py --limit 50000      # Giới hạn records
    python ingest.py --workers 8        # Số luồng embed
"""

import argparse, sqlite3, os, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import numpy as np
from tqdm import tqdm
import torch
import chromadb
from sentence_transformers import SentenceTransformer

os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY"] = "False"

from config import SQLITE_PATH, CHROMA_DIR, CHROMA_COLLECTION, EMBED_MODEL

# ChromaDB giới hạn 166 per batch
CHROMA_BATCH = 100
# Số câu embed mỗi lần (tận dụng GPU)
EMBED_BATCH  = 512
# Số luồng song song
DEFAULT_WORKERS = 4

_insert_lock = Lock()


def load_sqlite(db_path: str, limit: int = None) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    q = """
        SELECT id, instruction, output FROM medical_qa
        WHERE instruction IS NOT NULL AND output IS NOT NULL
          AND LENGTH(instruction) > 10 AND LENGTH(output) > 10
    """
    if limit:
        q += f" LIMIT {limit}"
    rows = conn.execute(q).fetchall()

    # Thêm dữ liệu dinh dưỡng từ bảng nutrition
    try:
        nutrition = conn.execute("""
            SELECT 'nutrition_' || id,
                   'How many calories in ' || description || '? Nutrition of ' || description,
                   'Food: ' || description || ' (' || category || ').' ||
                   ' Calories: ' || COALESCE(kilocalories, 'unknown') || ' kcal.' ||
                   ' Protein: ' || COALESCE(protein_g, 'unknown') || 'g.' ||
                   ' Carbs: ' || COALESCE(carbohydrate_g, 'unknown') || 'g.' ||
                   ' Fat: ' || COALESCE(fat_total_g, 'unknown') || 'g.' ||
                   ' Fiber: ' || COALESCE(fiber_g, 'unknown') || 'g.'
            FROM nutrition
            WHERE description IS NOT NULL
        """).fetchall()
        rows += nutrition
        print(f"   + {len(nutrition):,} nutrition records")
    except Exception as e:
        print(f"   [WARN] nutrition: {e}")

    conn.close()
    return rows


def embed_chunk(args) -> tuple:
    """Worker: embed 1 chunk, trả về (ids, embeddings, metadatas, documents)."""
    chunk, model_name, device, embed_batch = args
    model = SentenceTransformer(model_name, device=device)
    model.eval()

    ids       = [str(r[0]) for r in chunk]
    documents = [r[1] for r in chunk]
    metadatas = [{"answer": r[2][:1000]} for r in chunk]

    with torch.no_grad():
        embeddings = model.encode(
            documents,
            batch_size=embed_batch,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).tolist()

    return ids, embeddings, metadatas, documents


def ingest(db_path: str, limit: int = None, workers: int = DEFAULT_WORKERS):
    start = time.time()

    # ── Detect device ──────────────────────────────────────────
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda":
        gpu = torch.cuda.get_device_name(0)
        vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
        print(f"🚀 GPU: {gpu} ({vram:.1f}GB VRAM)")
        workers = 1
        EMBED_BATCH_ACTUAL = 128  # Giảm xuống để tránh OOM
    else:
        print(f"⚙️  CPU mode — {workers} workers")
        EMBED_BATCH_ACTUAL = 64

    print(f"📂 SQLite : {db_path}")
    print(f"📦 Chroma : {CHROMA_DIR}")
    print(f"🤖 Model  : {EMBED_MODEL}\n")

    # ── Load data ──────────────────────────────────────────────
    rows = load_sqlite(db_path, limit)
    total = len(rows)
    print(f"✅ Loaded {total:,} records\n")

    # ── Setup ChromaDB ─────────────────────────────────────────
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    try:
        client.delete_collection(CHROMA_COLLECTION)
        print("🗑️  Đã xoá collection cũ")
    except Exception:
        pass
    collection = client.create_collection(
        name=CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"}
    )

    # Chia chunks nhỏ để tránh OOM — mỗi chunk ~5000 records
    chunk_size = 5000
    chunks = [rows[i:i+chunk_size] for i in range(0, total, chunk_size)]
    args_list = [(chunk, EMBED_MODEL, device, EMBED_BATCH_ACTUAL) for chunk in chunks]

    print(f"⚡ Embedding {total:,} records ({workers} worker(s) x {chunk_size} chunk)...\n")

    inserted = 0
    pbar = tqdm(total=total, desc="Ingesting", unit="rec")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(embed_chunk, a): a for a in args_list}

        for future in as_completed(futures):
            ids, embeddings, metadatas, documents = future.result()

            # Insert theo CHROMA_BATCH
            with _insert_lock:
                for i in range(0, len(ids), CHROMA_BATCH):
                    collection.add(
                        ids        = ids[i:i+CHROMA_BATCH],
                        embeddings = embeddings[i:i+CHROMA_BATCH],
                        metadatas  = metadatas[i:i+CHROMA_BATCH],
                        documents  = documents[i:i+CHROMA_BATCH],
                    )
                inserted += len(ids)
                pbar.update(len(ids))

    pbar.close()

    elapsed = time.time() - start
    rate = total / elapsed
    print(f"\n✅ Hoàn tất: {collection.count():,} records")
    print(f"⏱️  {elapsed:.1f}s | {rate:.0f} rec/s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite",  default=SQLITE_PATH)
    parser.add_argument("--limit",   type=int, default=None)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    args = parser.parse_args()
    ingest(args.sqlite, args.limit, args.workers)
