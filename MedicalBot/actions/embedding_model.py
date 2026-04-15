"""
embedding_model.py — Wrapper cho sentence-transformers EmbeddingModel.

Cung cấp encode, batch encode, serialize/deserialize numpy float32 vectors.
"""

import logging
import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class EmbeddingModel:
    """Wrapper cho sentence-transformers SentenceTransformer.

    Hỗ trợ encode đơn lẻ, batch encode, và serialize/deserialize
    numpy float32 array thành bytes để lưu vào SQLite BLOB.
    """

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        """Khởi tạo EmbeddingModel và nạp sentence-transformer model.

        Args:
            model_name: Tên model trên Hugging Face Hub hoặc đường dẫn cục bộ.
        """
        self._model_name = model_name
        logger.info("Loading embedding model: %s", model_name)
        self._model = SentenceTransformer(model_name)
        logger.info("Embedding model loaded successfully.")

    @property
    def model_name(self) -> str:
        """Tên model đang được sử dụng."""
        return self._model_name

    def encode(self, text: str) -> np.ndarray:
        """Tính embedding cho một chuỗi văn bản.

        Args:
            text: Chuỗi văn bản cần encode.

        Returns:
            numpy float32 array có shape (embedding_dim,).
        """
        vector = self._model.encode(text, convert_to_numpy=True)
        return vector.astype(np.float32)

    def encode_batch(self, texts: list[str]) -> np.ndarray:
        """Tính embedding cho một batch văn bản.

        Args:
            texts: Danh sách chuỗi văn bản cần encode.

        Returns:
            numpy float32 array có shape (len(texts), embedding_dim).
        """
        vectors = self._model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return vectors.astype(np.float32)

    def serialize(self, vector: np.ndarray) -> bytes:
        """Serialize numpy array thành bytes để lưu vào SQLite BLOB.

        Args:
            vector: numpy array cần serialize.

        Returns:
            bytes — raw bytes của float32 array.
        """
        return vector.astype(np.float32).tobytes()

    def deserialize(self, blob: bytes) -> np.ndarray:
        """Deserialize bytes từ SQLite BLOB thành numpy float32 array.

        Args:
            blob: bytes đã được serialize bằng serialize().

        Returns:
            numpy float32 array.
        """
        return np.frombuffer(blob, dtype=np.float32)
