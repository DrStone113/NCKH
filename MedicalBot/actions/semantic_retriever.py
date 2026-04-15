"""
semantic_retriever.py — SemanticRetriever dùng cosine similarity để tìm câu trả lời.

Tìm kiếm ngữ nghĩa trong Knowledge Base bằng cách so sánh embedding của query
với tất cả embeddings đã lưu trong bảng embeddings.
"""

import logging
import numpy as np

logger = logging.getLogger(__name__)


class SemanticRetriever:
    """Tìm kiếm ngữ nghĩa trong Knowledge Base bằng cosine similarity.

    Sử dụng numpy vectorized operations để đảm bảo hiệu năng,
    toàn bộ quá trình retrieve hoàn thành trong 3 giây.
    """

    def __init__(self, db_client, embed_model) -> None:
        """Khởi tạo SemanticRetriever.

        Args:
            db_client: Instance của DBClient để truy vấn SQLite.
            embed_model: Instance của EmbeddingModel để tính embedding.
        """
        self._db = db_client
        self._embed = embed_model

    def retrieve(self, query: str) -> dict:
        """Tìm câu trả lời phù hợp nhất với query trong Knowledge Base.

        Quy trình:
        1. Encode query thành vector.
        2. Load tất cả embeddings từ DB.
        3. Tính cosine similarity (vectorized, không dùng loop).
        4. Trả về câu trả lời có similarity cao nhất nếu >= 0.5.

        Args:
            query: Câu hỏi của người dùng.

        Returns:
            dict với các key:
                - answer (str | None): Câu trả lời hoặc None nếu không tìm thấy.
                - similarity_score (float): Cosine similarity cao nhất.
                - qa_id (int | None): ID của bản ghi trong medical_qa hoặc None.
        """
        # Bước 1: Encode query
        query_vector = self._embed.encode(query)

        # Bước 2: Load tất cả embeddings
        rows = self._db.get_all_embeddings()

        # Bước 3: Xử lý trường hợp DB rỗng
        if not rows:
            logger.warning("Knowledge Base không có embedding nào.")
            return {"answer": None, "similarity_score": 0.0, "qa_id": None}

        # Bước 4: Tính cosine similarity (vectorized)
        ids = [row[0] for row in rows]
        vectors = np.array(
            [self._embed.deserialize(row[1]) for row in rows],
            dtype=np.float32,
        )

        # Cosine similarity: (query · v) / (||query|| * ||v||)
        query_norm = query_vector / (np.linalg.norm(query_vector) + 1e-10)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-10
        vectors_norm = vectors / norms
        similarities = vectors_norm @ query_norm  # shape: (N,)

        # Bước 5: Tìm index có similarity cao nhất
        best_idx = int(np.argmax(similarities))
        max_similarity = float(similarities[best_idx])
        best_id = ids[best_idx]

        logger.debug(
            "Best match: qa_id=%d, similarity=%.4f", best_id, max_similarity
        )

        # Bước 6-7: Kiểm tra ngưỡng 0.5
        if max_similarity >= 0.5:
            answer = self._db.get_answer_by_id(best_id)
            return {
                "answer": answer,
                "similarity_score": max_similarity,
                "qa_id": best_id,
            }

        return {"answer": None, "similarity_score": max_similarity, "qa_id": None}
