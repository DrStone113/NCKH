-- Extend only the research-store category vocabulary. Existing V1 rows remain
-- valid and are not rewritten; production RAG tables are not affected.
ALTER TABLE research_knowledge_chunks
    DROP CONSTRAINT IF EXISTS research_knowledge_chunks_category_check;

ALTER TABLE research_knowledge_chunks
    ADD CONSTRAINT research_knowledge_chunks_category_check
    CHECK (category IN ('food', 'exercise', 'guideline', 'health', 'nutrition', 'micronutrient'));
