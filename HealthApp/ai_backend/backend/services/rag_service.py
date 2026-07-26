from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import logging

from models.schemas import KnowledgeChunk
from config import settings

logger = logging.getLogger(__name__)


class RAGService:
    def __init__(self):
        self._model = None  # lazy load — không block startup

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Init local embedding model: {settings.embedding_model}")
            self._model = SentenceTransformer(settings.embedding_model)
        return self._model

    def embed(self, text_input: str) -> list[float]:
        """Encode text thành embedding vector, trả về list[float]."""
        model = self._get_model()
        embedding = model.encode(text_input).tolist()
        return embedding

    async def retrieve(
        self,
        query: str,
        db: AsyncSession,
        top_k: int = None,
    ) -> list[KnowledgeChunk]:
        """
        Tìm kiếm top-K knowledge chunks gần nhất với query.

        1. Embed query thành vector
        2. Dùng pgvector cosine distance (<=> operator) để tìm chunks gần nhất
        3. Lọc bỏ chunks có similarity < settings.rag_similarity_threshold
        4. Trả về list[KnowledgeChunk]

        Validates: Requirements 3.1, 3.2, 3.5, 3.6
        """
        if top_k is None:
            top_k = settings.rag_top_k

        # 1. Embed query
        query_vec = self.embed(query)

        # pgvector expects embedding as string '[0.1, 0.2, ...]'
        query_vec_str = "[" + ",".join(str(v) for v in query_vec) + "]"

        # 2. Cosine similarity query via pgvector <=> (cosine distance)
        #    similarity = 1 - cosine_distance
        sql = text("""
            SELECT kc.id, kc.category, kc.title, kc.content, kc.metadata,
                   1 - (ce.embedding <=> CAST(:query_vec AS vector)) AS similarity
            FROM chunk_embeddings ce
            JOIN knowledge_chunks kc ON kc.id = ce.chunk_id
            ORDER BY ce.embedding <=> CAST(:query_vec AS vector)
            LIMIT :top_k
        """)

        result = await db.execute(sql, {"query_vec": query_vec_str, "top_k": top_k})
        rows = result.fetchall()

        # 3. Filter rows where similarity < threshold
        chunks = []
        for row in rows:
            similarity = float(row.similarity)
            if similarity >= settings.rag_similarity_threshold:
                chunks.append(
                    KnowledgeChunk(
                        id=str(row.id),
                        category=row.category,
                        title=row.title,
                        content=row.content,
                        metadata=row.metadata or {},
                        similarity=similarity,
                    )
                )

        return chunks


# Singleton instance
rag_service = RAGService()
