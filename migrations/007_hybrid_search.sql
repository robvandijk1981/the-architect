-- ============================================
-- 007 — Hybrid search infrastructure
-- ============================================
-- Adds Dutch full-text search (BM25-via-ts_rank) alongside the existing
-- pgvector dense-search, plus a function combining both into a single
-- hybrid score.
--
-- Rationale: pure dense vector search misses exact-term matches on jargon
-- (SPO, DBV, ZSM, vacaturegraad). BM25 catches those. Combined with
-- alpha-weighted scoring (default 0.7 dense + 0.3 BM25) the retrieval
-- handles both semantic similarity and lexical precision.
--
-- Idempotent — safe to re-run.

-- Step 1: Add a generated tsvector column on knowledge_embeddings.
-- GENERATED ALWAYS AS ... STORED auto-updates on every INSERT/UPDATE
-- without needing a trigger. Requires PostgreSQL 12+.
ALTER TABLE knowledge_embeddings
    ADD COLUMN IF NOT EXISTS search_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('dutch', coalesce(chunk_text, ''))) STORED;

-- Step 2: GIN index for fast full-text search.
CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_search_tsv
    ON knowledge_embeddings USING GIN (search_tsv);

-- Step 3: Hybrid search function.
-- Combines dense cosine similarity with BM25-style ts_rank into a single
-- ranked result set.
DROP FUNCTION IF EXISTS hybrid_search_chunks(TEXT, vector, INTEGER, FLOAT, FLOAT, TEXT, INTEGER, TEXT);

CREATE OR REPLACE FUNCTION hybrid_search_chunks(
    query_text TEXT,
    query_embedding vector(1024),
    match_count INTEGER DEFAULT 10,
    similarity_threshold FLOAT DEFAULT 0.30,
    alpha FLOAT DEFAULT 0.7,
    filter_sector TEXT DEFAULT NULL,
    filter_layer INTEGER DEFAULT NULL,
    filter_category TEXT DEFAULT NULL
)
RETURNS TABLE (
    id UUID,
    document_id UUID,
    chunk_text TEXT,
    chunk_index INTEGER,
    similarity FLOAT,
    bm25_score FLOAT,
    hybrid_score FLOAT,
    source_name TEXT,
    source_url TEXT,
    source_type TEXT,
    category TEXT,
    layer INTEGER,
    sector TEXT[],
    source_date DATE,
    metadata JSONB
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH scored AS (
        SELECT
            ke.id,
            ke.document_id,
            ke.chunk_text,
            ke.chunk_index,
            (1.0 - (ke.embedding <=> query_embedding))::FLOAT AS dense_sim,
            -- ts_rank values typically range 0.0 - ~1.0 for short queries.
            -- Cap at 1.0 to prevent extreme outliers from dominating the blend.
            LEAST(
                ts_rank(ke.search_tsv, plainto_tsquery('dutch', query_text))::FLOAT,
                1.0
            ) AS bm25,
            kd.source_name,
            kd.source_url,
            kd.source_type,
            kd.category,
            kd.layer,
            kd.sector,
            kd.source_date,
            kd.metadata
        FROM knowledge_embeddings ke
        JOIN knowledge_documents kd ON kd.id = ke.document_id
        WHERE kd.is_current = TRUE
          AND (1.0 - (ke.embedding <=> query_embedding)) >= similarity_threshold
          AND (filter_sector IS NULL OR filter_sector = ANY(kd.sector))
          AND (filter_layer IS NULL OR kd.layer = filter_layer)
          AND (filter_category IS NULL OR kd.category = filter_category)
    )
    SELECT
        scored.id,
        scored.document_id,
        scored.chunk_text,
        scored.chunk_index,
        scored.dense_sim AS similarity,
        scored.bm25 AS bm25_score,
        (alpha * scored.dense_sim + (1.0 - alpha) * scored.bm25)::FLOAT AS hybrid_score,
        scored.source_name,
        scored.source_url,
        scored.source_type,
        scored.category,
        scored.layer,
        scored.sector,
        scored.source_date,
        scored.metadata
    FROM scored
    ORDER BY (alpha * scored.dense_sim + (1.0 - alpha) * scored.bm25) DESC
    LIMIT match_count;
END;
$$;

COMMENT ON FUNCTION hybrid_search_chunks(TEXT, vector, INTEGER, FLOAT, FLOAT, TEXT, INTEGER, TEXT) IS
'Hybrid search: combines pgvector cosine similarity (weighted alpha) with PostgreSQL ts_rank BM25 (weighted 1-alpha). Phase 4c of retrieval-infra roadmap, april 2026.';
