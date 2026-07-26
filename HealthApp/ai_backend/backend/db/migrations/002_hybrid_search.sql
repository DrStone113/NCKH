-- 002_hybrid_search.sql
--
-- Bổ sung hạ tầng cho hybrid retrieval (vector + từ khóa) trong RAGService.
--
-- Vì sao cần: pgvector một mình bỏ sót các truy vấn có danh từ riêng — tên món
-- ("bún bò Huế"), tên bài tập ("deadlift"), tên vi chất ("vitamin B12").
-- Embedding đa ngôn ngữ làm nhòe những token hiếm này, trong khi so khớp từ
-- khóa lại bắt chúng chính xác. Kết hợp hai nguồn rồi hợp nhất bằng Reciprocal
-- Rank Fusion cho recall tốt hơn hẳn so với từng cách riêng lẻ.
--
-- Dùng cấu hình text search 'simple' chứ không phải 'english': tiếng Việt
-- không có bộ stemmer trong Postgres, và 'english' sẽ cắt sai gốc từ. 'simple'
-- chỉ hạ chữ thường và tách theo khoảng trắng — đúng thứ ta cần cho tiếng Việt
-- vốn đã tách âm tiết sẵn.

-- pg_trgm dùng cho fuzzy match tên món viết sai chính tả / thiếu dấu.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Cột tsvector sinh tự động: title được nhân trọng số A (cao nhất), content
-- trọng số B. Là cột GENERATED nên không cần trigger đồng bộ.
ALTER TABLE knowledge_chunks
    ADD COLUMN IF NOT EXISTS search_vector tsvector
    GENERATED ALWAYS AS (
        setweight(to_tsvector('simple', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce(content, '')), 'B')
    ) STORED;

CREATE INDEX IF NOT EXISTS knowledge_chunks_search_vector_idx
    ON knowledge_chunks USING GIN (search_vector);

-- Trigram index trên title cho truy vấn sai chính tả / không dấu.
CREATE INDEX IF NOT EXISTS knowledge_chunks_title_trgm_idx
    ON knowledge_chunks USING GIN (title gin_trgm_ops);

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO health;
