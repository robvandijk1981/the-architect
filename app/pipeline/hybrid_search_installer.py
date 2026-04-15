"""
Install hybrid search infrastructure.

Phase 4c of retrieval-infra roadmap. Adds:
- search_tsv generated tsvector column on knowledge_embeddings
- GIN index for fast full-text lookup
- hybrid_search_chunks() SQL function combining dense + BM25 scoring

Idempotent — safe to run multiple times. Uses ADD COLUMN IF NOT EXISTS,
CREATE INDEX IF NOT EXISTS, and DROP FUNCTION IF EXISTS before CREATE.
"""

import structlog

from app.core.database import execute

logger = structlog.get_logger()


HYBRID_SEARCH_SQL = """
ALTER TABLE knowledge_embeddings
    ADD COLUMN IF NOT EXISTS search_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('dutch', coalesce(chunk_text, ''))) STORED;

CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_search_tsv
    ON knowledge_embeddings USING GIN (search_tsv);

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
"""


async def install_hybrid_search() -> dict:
    """
    Install hybrid search: tsvector column + GIN index + hybrid_search_chunks function.
    Idempotent — safe to run multiple times.

    Note: ADD COLUMN with GENERATED ALWAYS AS ... STORED on a large table
    will rewrite all rows. For ~160k rows this typically takes 30-90 seconds
    on Neon Postgres. Run during low-traffic window.
    """
    await execute(HYBRID_SEARCH_SQL)
    logger.info("hybrid_search_installed")
    return {
        "status": "ok",
        "function": "hybrid_search_chunks",
        "components": [
            "search_tsv generated column on knowledge_embeddings",
            "GIN index idx_knowledge_embeddings_search_tsv",
            "hybrid_search_chunks(query_text, query_embedding, ...) function",
        ],
        "default_alpha": 0.7,
        "scoring": "alpha * cosine_similarity + (1-alpha) * ts_rank (BM25)",
        "note": "Add column on existing 160k chunks rewrites the table — may take 30-90s on first install.",
    }
