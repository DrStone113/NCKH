-- Add vocabulary needed by the separately versioned final research corpus.
-- This changes neither historical rows nor production RAG tables.
ALTER TABLE research_knowledge_chunks
    DROP CONSTRAINT IF EXISTS research_knowledge_chunks_category_check;

ALTER TABLE research_knowledge_chunks
    ADD CONSTRAINT research_knowledge_chunks_category_check
    CHECK (category IN (
        'food',
        'dish',
        'nutrition',
        'micronutrient',
        'exercise',
        'guideline',
        'physical_activity_guideline',
        'health',
        'health_safety',
        'body_metric',
        'weight_management',
        'other_approved'
    ));
