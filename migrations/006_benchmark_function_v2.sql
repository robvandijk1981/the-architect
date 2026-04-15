-- ============================================
-- 006 — Benchmark function v2: aggregate over organizations
-- ============================================
-- The v1 function from 002_functions.sql reads from sector_intelligence,
-- which was never seeded with organization-level metrics, causing
-- /benchmark/{sector} to return empty arrays.
--
-- This v2 aggregates over the organizations table (60 organisations,
-- rich fields from migration 004) and produces statistical benchmarks
-- (median / min / max / p25 / p75) per key metric per sector.
--
-- Safe to re-run: CREATE OR REPLACE is idempotent.

CREATE OR REPLACE FUNCTION get_sector_benchmarks(p_sector_slug TEXT)
RETURNS TABLE (
    metric_name TEXT,
    median_value DECIMAL,
    min_value DECIMAL,
    max_value DECIMAL,
    p25 DECIMAL,
    p75 DECIMAL,
    sample_size INTEGER,
    unit TEXT
)
LANGUAGE sql
AS $$
    WITH sector_orgs AS (
        SELECT * FROM organizations WHERE sector_slug = p_sector_slug
    ),
    metrics AS (
        SELECT 'verzuim_pct'::TEXT AS metric, verzuim_pct::DECIMAL AS value, 'percentage'::TEXT AS unit
          FROM sector_orgs WHERE verzuim_pct IS NOT NULL
        UNION ALL
        SELECT 'vacatures', vacatures::DECIMAL, 'aantal'
          FROM sector_orgs WHERE vacatures IS NOT NULL
        UNION ALL
        SELECT 'gem_jaarsalaris', gem_jaarsalaris::DECIMAL, 'EUR'
          FROM sector_orgs WHERE gem_jaarsalaris IS NOT NULL
        UNION ALL
        SELECT 'personeelskosten_mln', personeelskosten_mln::DECIMAL, 'mln EUR'
          FROM sector_orgs WHERE personeelskosten_mln IS NOT NULL
        UNION ALL
        SELECT 'kosten_krapte_totaal_mln', kosten_krapte_totaal_mln::DECIMAL, 'mln EUR'
          FROM sector_orgs WHERE kosten_krapte_totaal_mln IS NOT NULL
        UNION ALL
        SELECT 'kosten_verzuim_mln', kosten_verzuim_mln::DECIMAL, 'mln EUR'
          FROM sector_orgs WHERE kosten_verzuim_mln IS NOT NULL
        UNION ALL
        SELECT 'kosten_werving_mln', kosten_werving_mln::DECIMAL, 'mln EUR'
          FROM sector_orgs WHERE kosten_werving_mln IS NOT NULL
        UNION ALL
        SELECT 'kosten_inhuur_mln', kosten_inhuur_mln::DECIMAL, 'mln EUR'
          FROM sector_orgs WHERE kosten_inhuur_mln IS NOT NULL
        UNION ALL
        SELECT 'ai_baten_25_mln', ai_baten_25_mln::DECIMAL, 'mln EUR'
          FROM sector_orgs WHERE ai_baten_25_mln IS NOT NULL
        UNION ALL
        SELECT 'ai_baten_50_mln', ai_baten_50_mln::DECIMAL, 'mln EUR'
          FROM sector_orgs WHERE ai_baten_50_mln IS NOT NULL
        UNION ALL
        SELECT 'ai_baten_75_mln', ai_baten_75_mln::DECIMAL, 'mln EUR'
          FROM sector_orgs WHERE ai_baten_75_mln IS NOT NULL
        UNION ALL
        SELECT 'fte_bespaard_50', fte_bespaard_50::DECIMAL, 'FTE'
          FROM sector_orgs WHERE fte_bespaard_50 IS NOT NULL
    )
    SELECT
        m.metric,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY m.value)::DECIMAL,
        MIN(m.value),
        MAX(m.value),
        PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY m.value)::DECIMAL,
        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY m.value)::DECIMAL,
        COUNT(*)::INTEGER,
        MAX(m.unit)
    FROM metrics m
    GROUP BY m.metric
    ORDER BY m.metric;
$$;

COMMENT ON FUNCTION get_sector_benchmarks(TEXT) IS
'Aggregated benchmarks (median/min/max/p25/p75) per key metric for a given sector, computed over the organizations table. Phase 5b of retrieval-infra roadmap, april 2026.';
