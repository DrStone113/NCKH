-- 003_web_knowledge.sql
--
-- Cho phép lưu kiến thức lấy từ internet vào chính knowledge_chunks, để lần
-- sau hỏi câu tương tự thì RAG nội bộ trả lời được mà không cần ra mạng.
--
-- Hai thay đổi:
--
-- 1. Nới CHECK constraint trên `category`. Constraint cũ chỉ cho 4 giá trị
--    ('food', 'exercise', 'wger_exercise', 'wger_ingredient') nên mọi INSERT
--    từ web search đều bị chặn.
--
-- 2. Thêm cột provenance. Kiến thức tự học BẮT BUỘC phải truy vết được nguồn:
--    một con số dinh dưỡng không có nguồn thì không dùng được trong báo cáo
--    NCKH, và không có `fetched_at` thì không biết khi nào cần làm mới.
--    `source_url` là UNIQUE để cùng một trang không bị nạp trùng nhiều lần.

ALTER TABLE knowledge_chunks DROP CONSTRAINT IF EXISTS knowledge_chunks_category_check;
ALTER TABLE knowledge_chunks ADD CONSTRAINT knowledge_chunks_category_check
    CHECK (category IN (
        'food', 'exercise', 'wger_exercise', 'wger_ingredient',
        'medical_literature',   -- PubMed
        'web_health'            -- WHO, Bộ Y tế, Vinmec, ...
    ));

ALTER TABLE knowledge_chunks
    ADD COLUMN IF NOT EXISTS source_url  TEXT,
    ADD COLUMN IF NOT EXISTS source_tier SMALLINT,
    ADD COLUMN IF NOT EXISTS fetched_at  TIMESTAMPTZ;

-- Partial unique index: chỉ áp dụng cho row có source_url, nên toàn bộ dữ liệu
-- offline sẵn có (source_url IS NULL) không bị ảnh hưởng.
CREATE UNIQUE INDEX IF NOT EXISTS knowledge_chunks_source_url_key
    ON knowledge_chunks (source_url)
    WHERE source_url IS NOT NULL;

CREATE INDEX IF NOT EXISTS knowledge_chunks_fetched_at_idx
    ON knowledge_chunks (fetched_at)
    WHERE fetched_at IS NOT NULL;

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO health;
