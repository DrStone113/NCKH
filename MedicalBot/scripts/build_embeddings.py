"""
build_embeddings.py — Tính và lưu embeddings vào SQLite (GPU + Bulk Insert).

Tối ưu:
  - GPU acceleration (CUDA) cho SentenceTransformer
  - Batch size lớn (512+) để tận dụng VRAM
  - Bulk insert thay vì từng record
  - Progress bar với ETA

Sử dụng:
    python scripts/build_embeddings.py --db-path knowledge_base/health_kb.db
    python scripts/build_embeddings.py --db-path knowledge_base/health_kb.db --batch-size 1024
"""

import sys, os, argparse, logging, time
import numpy as np
import torch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "actions"))

from db_client import DBClient
from sentence_transformers import SentenceTransformer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _detect_device() -> str:
    if torch.cuda.is_available():
        name = torch.cuda.get_device_name(0)
        vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
        logger.info("🚀 GPU: %s (%.1f GB VRAM)", name, vram)
        return "cuda"
    logger.warning("⚠️  CUDA không khả dụng — dùng CPU (chậm hơn)")
    return "cpu"


def _auto_batch_size(device: str, requested: int) -> int:
    """Tự động chọn batch size tối ưu nếu không chỉ định."""
    if requested > 0:
        return requested
    if device == "cuda":
        vram_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
        # ~512 batch/GB VRAM cho all-MiniLM-L6-v2
        return min(int(vram_gb * 512), 2048)
    return 64  # CPU default


def _print_progress(done: int, total: int, elapsed: float, label: str = "") -> None:
    pct = done / total * 100
    bar_len = 45
    filled = int(bar_len * done / total)
    bar = "█" * filled + "░" * (bar_len - filled)
    rate = done / elapsed if elapsed > 0 else 0
    eta = (total - done) / rate if rate > 0 else 0
    print(
        f"\r  {label}[{bar}] {done:,}/{total:,} ({pct:.1f}%) "
        f"| {rate:.0f} rec/s | ETA {int(eta//60)}m{int(eta%60)}s   ",
        end="", flush=True
    )


def build_embeddings(db_path: str, model_name: str, batch_size: int, save_every: int) -> None:
    device = _detect_device()
    batch_size = _auto_batch_size(device, batch_size)
    logger.info("📦 Batch size: %d | Save every: %d batches", batch_size, save_every)

    # Load model lên GPU
    logger.info("Loading model: %s ...", model_name)
    model = SentenceTransformer(model_name, device=device)
    model.eval()
    logger.info("✅ Model loaded trên %s", device.upper())

    # Lấy records chưa có embedding
    db = DBClient(db_path)
    records = db.get_all_qa_without_embeddings()
    total = len(records)

    if total == 0:
        logger.info("✅ Tất cả bản ghi đã có embedding.")
        db.close()
        return

    logger.info("📊 Tổng bản ghi cần tính: %,d", total)
    logger.info("⚡ Bắt đầu encoding...\n")

    start_time = time.time()
    processed = 0
    pending_save: list[tuple] = []  # Buffer để bulk insert

    for batch_start in range(0, total, batch_size):
        batch = records[batch_start: batch_start + batch_size]
        texts = [r["instruction"] for r in batch]
        ids   = [r["id"]          for r in batch]

        # Encode batch trên GPU
        with torch.no_grad():
            vectors = model.encode(
                texts,
                batch_size=batch_size,
                convert_to_numpy=True,
                show_progress_bar=False,
                normalize_embeddings=True,  # Chuẩn hoá L2 — tốt cho cosine search
            )

        # Serialize và buffer
        for qa_id, vec in zip(ids, vectors):
            blob = vec.astype(np.float32).tobytes()
            pending_save.append((qa_id, blob))

        processed += len(batch)

        # Bulk insert mỗi save_every batches
        if len(pending_save) >= batch_size * save_every:
            db.batch_save_embeddings(pending_save, model_name)
            pending_save.clear()

        _print_progress(processed, total, time.time() - start_time, "Embedding ")

    # Lưu phần còn lại
    if pending_save:
        db.batch_save_embeddings(pending_save, model_name)

    elapsed = time.time() - start_time
    rate = processed / elapsed
    print()  # Xuống dòng sau progress bar
    logger.info("✅ Hoàn tất: %,d embeddings | %.1fs | %.0f rec/s", processed, elapsed, rate)
    db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Tính embeddings GPU + Bulk Insert")
    parser.add_argument("--db-path",    default="knowledge_base/health_kb.db")
    parser.add_argument("--model",      default="sentence-transformers/all-MiniLM-L6-v2")
    parser.add_argument("--batch-size", type=int, default=0,
                        help="0 = tự động theo VRAM (khuyến nghị)")
    parser.add_argument("--save-every", type=int, default=10,
                        help="Bulk insert mỗi N batches (mặc định: 10)")
    args = parser.parse_args()

    build_embeddings(
        db_path=args.db_path,
        model_name=args.model,
        batch_size=args.batch_size,
        save_every=args.save_every,
    )


if __name__ == "__main__":
    main()
