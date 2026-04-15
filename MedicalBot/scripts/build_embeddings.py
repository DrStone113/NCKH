"""
build_embeddings.py — Script tính và lưu embeddings vào SQLite Knowledge Base.

Sử dụng:
    python scripts/build_embeddings.py \
        --db-path knowledge_base/health_kb.db \
        --model sentence-transformers/all-MiniLM-L6-v2 \
        --batch-size 64
"""

import sys
import os
import argparse
import logging

# Cho phép import từ thư mục actions/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "actions"))

from db_client import DBClient
from embedding_model import EmbeddingModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def build_embeddings(db_path: str, model_name: str, batch_size: int) -> None:
    """Tính và lưu embeddings cho tất cả bản ghi medical_qa chưa có embedding.

    Args:
        db_path: Đường dẫn đến file SQLite.
        model_name: Tên sentence-transformer model.
        batch_size: Số bản ghi xử lý mỗi batch.
    """
    db = DBClient(db_path)
    embed_model = EmbeddingModel(model_name)

    records = db.get_all_qa_without_embeddings()
    total = len(records)

    if total == 0:
        logger.info("Không có bản ghi nào cần tính embedding.")
        return

    logger.info("Tổng số bản ghi cần tính embedding: %d", total)
    processed = 0

    for batch_start in range(0, total, batch_size):
        batch = records[batch_start: batch_start + batch_size]
        texts = [r["instruction"] for r in batch]
        ids = [r["id"] for r in batch]

        vectors = embed_model.encode_batch(texts)

        for qa_id, vector in zip(ids, vectors):
            blob = embed_model.serialize(vector)
            db.save_embedding(qa_id, blob, model_name)

        processed += len(batch)

        if processed % 100 == 0 or processed == total:
            logger.info("Tiến độ: %d / %d bản ghi đã xử lý.", processed, total)

    logger.info("Hoàn tất: %d embeddings đã được lưu vào %s", processed, db_path)
    db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tính và lưu embeddings vào SQLite Knowledge Base."
    )
    parser.add_argument(
        "--db-path",
        default="knowledge_base/health_kb.db",
        help="Đường dẫn đến file SQLite (mặc định: knowledge_base/health_kb.db)",
    )
    parser.add_argument(
        "--model",
        default="sentence-transformers/all-MiniLM-L6-v2",
        help="Tên sentence-transformer model (mặc định: all-MiniLM-L6-v2)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="Số bản ghi xử lý mỗi batch (mặc định: 64)",
    )
    args = parser.parse_args()

    build_embeddings(
        db_path=args.db_path,
        model_name=args.model,
        batch_size=args.batch_size,
    )


if __name__ == "__main__":
    main()
