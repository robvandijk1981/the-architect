"""
Install or upgrade the get_sector_benchmarks SQL function.

Phase 5b of the retrieval-infra roadmap. Replaces the v1 function (which
read from the empty sector_intelligence table) with one that aggregates
live statistics over the organizations table.

Idempotent — safe to run multiple times. Explicitly DROPs the old
function first because PostgreSQL forbids changing a set-returning
function's return-type columns via CREATE OR REPLACE.
"""

import structlog

from app.core.database import execute

logger = structlog.get_logger()


# Drop v1 first — its RETURNS TABLE(...) columns differ from v2, and
# PostgreSQL rejects CREATE OR REPLACE when the row-type changes.
BENCHMARK_FUNCTION_V2_SQL = """
DROP FUNCTION IF EXISTS get_sector_benchmarks(TEXT);

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
"""


async def install_benchmark_function_v2() -> dict:
    """
    Install or replace the v2 get_sector_benchmarks SQL function.

    Drops the v1 function first (its return-type columns differ) then
    creates the v2. Idempotent — safe to run multiple times.
    """
    await execute(BENCHMARK_FUNCTION_V2_SQL)
    logger.info("benchmark_function_v2_installed")
    return {
        "status": "ok",
        "function": "get_sector_benchmarks",
        "version": "v2",
        "aggregation_source": "organizations table",
        "metrics": [
            "verzuim_pct", "vacatures", "gem_jaarsalaris", "personeelskosten_mln",
            "kosten_krapte_totaal_mln", "kosten_verzuim_mln", "kosten_werving_mln",
            "kosten_inhuur_mln", "ai_baten_25_mln", "ai_baten_50_mln",
            "ai_baten_75_mln", "fte_bespaard_50",
        ],
    }
