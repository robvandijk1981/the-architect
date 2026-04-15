"""
Install hybrid search infrastructure.

Phase 4c of retrieval-infra roadmap. Adds:
- search_tsv generated tsvector column on knowledge_embeddings
- GIN index for fast full-text lookup
- hybrid_search_chunks() SQL function combining dense + BM25 scoring

Idempotent — safe to run multiple times. Uses ADD COLUMN IF NOT EXISTS,
CREATE INDEX IF NOT EXISTS, and DROP FUNCTION IF EXISTS before CREATE.

Split into 3 phases because the ALTER TABLE part rewrites the whole
knowledge_embeddings table (~160k rows, 30-90s on Neon) which exceeds
Railway's HTTP timeout. The API endpoint runs the full install as a
BackgroundTask; status can be polled via /admin/hybrid-search-status.
"""

import structlog

from app.core.database import execute, fetch_one

logger = structlog.get_logger()


# Phase 1: ALTER TABLE — slow (table rewrite ~30-90s for 160k rows)
TSV_COLUMN_SQL = """
ALTER TABLE knowledge_embeddings
    ADD COLUMN IF NOT EXISTS search_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('dutch', coalesce(chunk_text, ''))) STORED;
"""

# Phase 2: GIN index — fast (a few seconds)
GIN_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_search_tsv
    ON knowledge_embeddings USING GIN (search_tsv);
"""

# Phase 3: hybrid_search_chunks function — fast (ms)
HYBRID_FUNCTION_SQL = """
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


async def install_tsv_column() -> None:
    """Phase 1: ALTER TABLE — table rewrite, slow."""
    logger.info("hybrid_install_phase_1_tsv_column_start")
    await execute(TSV_COLUMN_SQL)
    logger.info("hybrid_install_phase_1_tsv_column_done")


async def install_gin_index() -> None:
    """Phase 2: GIN index on the new tsvector column."""
    logger.info("hybrid_install_phase_2_gin_index_start")
    await execute(GIN_INDEX_SQL)
    logger.info("hybrid_install_phase_2_gin_index_done")


async def install_hybrid_function() -> None:
    """Phase 3: CREATE FUNCTION."""
    logger.info("hybrid_install_phase_3_function_start")
    await execute(HYBRID_FUNCTION_SQL)
    logger.info("hybrid_install_phase_3_function_done")


async def install_hybrid_search() -> dict:
    """
    Run all three install phases sequentially.
    Idempotent — safe to run multiple times.

    Run as a BackgroundTask from the API to avoid HTTP timeout, since
    phase 1 takes 30-90s on the 160k-row knowledge_embeddings table.
    """
    try:
        await install_tsv_column()
        await install_gin_index()
        await install_hybrid_function()
        logger.info("hybrid_search_installed_full")
        return {
            "status": "ok",
            "phases": ["tsv_column", "gin_index", "hybrid_function"],
        }
    except Exception as e:
        logger.error("hybrid_install_failed", error=str(e))
        raise


async def check_hybrid_search_status() -> dict:
    """
    Inspect whether each component is in place. Read-only, fast (<100ms).
    """
    column_exists = await fetch_one(
        """SELECT 1 AS ok FROM information_schema.columns
           WHERE table_name = 'knowledge_embeddings'
             AND column_name = 'search_tsv'"""
    )
    index_exists = await fetch_one(
        """SELECT 1 AS ok FROM pg_indexes
           WHERE tablename = 'knowledge_embeddings'
             AND indexname = 'idx_knowledge_embeddings_search_tsv'"""
    )
    function_exists = await fetch_one(
        """SELECT 1 AS ok FROM pg_proc WHERE proname = 'hybrid_search_chunks'"""
    )

    components = {
        "tsv_column": bool(column_exists),
        "gin_index": bool(index_exists),
        "hybrid_function": bool(function_exists),
    }
    all_ready = all(components.values())

    return {
        "status": "ready" if all_ready else "in_progress_or_missing",
        "components": components,
        "next_step": (
            "Hybrid search ready — call /admin/test-hybrid-search to verify."
            if all_ready
            else "Some components missing. POST /admin/install-hybrid-search to install (background task)."
        ),
    }
