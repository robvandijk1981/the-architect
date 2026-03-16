-- ============================================
-- The Architect — Database Functions
-- ============================================
-- Run AFTER 001_initial_schema.sql

-- ============================================
-- 1. Vector Similarity Search
-- ============================================
-- Core RAG function: find relevant knowledge chunks
CREATE OR REPLACE FUNCTION match_knowledge_chunks(
    query_embedding vector(1024),
    match_count INTEGER DEFAULT 10,
    similarity_threshold FLOAT DEFAULT 0.7,
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
    SELECT
        ke.id,
        ke.document_id,
        ke.chunk_text,
        ke.chunk_index,
        1 - (ke.embedding <=> query_embedding) AS similarity,
        kd.source_name,
        kd.source_url,
        kd.source_type,
        kd.category,
        kd.layer,
        kd.sector,
        kd.source_date,
        ke.metadata
    FROM knowledge_embeddings ke
    JOIN knowledge_documents kd ON ke.document_id = kd.id
    WHERE kd.is_current = true
        AND (1 - (ke.embedding <=> query_embedding)) > similarity_threshold
        AND (filter_sector IS NULL OR filter_sector = ANY(kd.sector) OR kd.sector IS NULL)
        AND (filter_layer IS NULL OR kd.layer = filter_layer)
        AND (filter_category IS NULL OR kd.category = filter_category)
    ORDER BY ke.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- ============================================
-- 2. Sector Benchmarks
-- ============================================
-- Get all benchmarks for a sector
CREATE OR REPLACE FUNCTION get_sector_benchmarks(p_sector_slug TEXT)
RETURNS TABLE (
    metric_name TEXT,
    metric_value DECIMAL,
    metric_unit TEXT,
    metric_context TEXT,
    source TEXT,
    source_date DATE,
    confidence DECIMAL
)
LANGUAGE sql
AS $$
    SELECT
        si.metric_name,
        si.metric_value,
        si.metric_unit,
        si.metric_context,
        si.source,
        si.source_date,
        si.confidence
    FROM sector_intelligence si
    WHERE si.sector_slug = p_sector_slug
    ORDER BY si.metric_name;
$$;

-- ============================================
-- 3. Risk Parameters for Sector
-- ============================================
CREATE OR REPLACE FUNCTION get_risk_parameters(p_sector_slug TEXT)
RETURNS TABLE (
    risk_category TEXT,
    parameter_name TEXT,
    parameter_value DECIMAL,
    threshold_low DECIMAL,
    threshold_high DECIMAL,
    weight DECIMAL,
    source TEXT,
    source_date DATE
)
LANGUAGE sql
AS $$
    SELECT
        rp.risk_category,
        rp.parameter_name,
        rp.parameter_value,
        rp.threshold_low,
        rp.threshold_high,
        rp.weight,
        rp.source,
        rp.source_date
    FROM risk_parameters rp
    WHERE rp.sector_slug = p_sector_slug
    ORDER BY rp.risk_category, rp.parameter_name;
$$;

-- ============================================
-- 4. Business Case Parameters
-- ============================================
CREATE OR REPLACE FUNCTION get_businesscase_parameters(p_sector_slug TEXT)
RETURNS TABLE (
    category TEXT,
    parameter_name TEXT,
    parameter_value DECIMAL,
    parameter_unit TEXT,
    description TEXT,
    is_adjustable BOOLEAN,
    min_value DECIMAL,
    max_value DECIMAL
)
LANGUAGE sql
AS $$
    SELECT
        bp.category,
        bp.parameter_name,
        bp.parameter_value,
        bp.parameter_unit,
        bp.description,
        bp.is_adjustable,
        bp.min_value,
        bp.max_value
    FROM businesscase_parameters bp
    WHERE bp.sector_slug = p_sector_slug
    ORDER BY bp.category, bp.parameter_name;
$$;

-- ============================================
-- 5. Knowledge Base Stats
-- ============================================
CREATE OR REPLACE FUNCTION knowledge_stats()
RETURNS TABLE (
    total_documents BIGINT,
    current_documents BIGINT,
    total_chunks BIGINT,
    by_layer JSONB,
    by_category JSONB,
    oldest_source DATE,
    newest_source DATE,
    expired_count BIGINT
)
LANGUAGE sql
AS $$
    SELECT
        (SELECT count(*) FROM knowledge_documents) AS total_documents,
        (SELECT count(*) FROM knowledge_documents WHERE is_current = true) AS current_documents,
        (SELECT count(*) FROM knowledge_embeddings) AS total_chunks,
        (SELECT jsonb_object_agg(layer::text, cnt) FROM (
            SELECT layer, count(*) as cnt FROM knowledge_documents WHERE is_current = true GROUP BY layer
        ) t) AS by_layer,
        (SELECT jsonb_object_agg(category, cnt) FROM (
            SELECT category, count(*) as cnt FROM knowledge_documents WHERE is_current = true GROUP BY category
        ) t) AS by_category,
        (SELECT min(source_date) FROM knowledge_documents WHERE is_current = true) AS oldest_source,
        (SELECT max(source_date) FROM knowledge_documents WHERE is_current = true) AS newest_source,
        (SELECT count(*) FROM knowledge_documents WHERE expires_at < now() AND is_current = true) AS expired_count;
$$;

-- ============================================
-- 6. Marketplace: Match Providers to Risks
-- ============================================
CREATE OR REPLACE FUNCTION match_providers(
    p_risk_categories TEXT[],
    p_sector TEXT,
    p_limit INTEGER DEFAULT 5
)
RETURNS TABLE (
    provider_id UUID,
    provider_name TEXT,
    provider_slug TEXT,
    description TEXT,
    website TEXT,
    categories TEXT[],
    relevance_score INTEGER
)
LANGUAGE sql
AS $$
    SELECT
        sp.id AS provider_id,
        sp.name AS provider_name,
        sp.slug AS provider_slug,
        sp.description,
        sp.website,
        sp.categories,
        -- Score: how many risk categories this provider covers
        (SELECT count(*)::INTEGER FROM unnest(sp.categories) c WHERE c = ANY(p_risk_categories)) AS relevance_score
    FROM service_providers sp
    WHERE sp.subscription_status = 'active'
        AND (sp.sectors IS NULL OR p_sector = ANY(sp.sectors))
        AND sp.categories && p_risk_categories  -- array overlap
    ORDER BY relevance_score DESC, sp.name
    LIMIT p_limit;
$$;
