"""
Seed sector benchmark data into PostgreSQL.
Called during app startup to populate initial benchmark data.
"""

import structlog
from app.core.database import execute, fetch_one

logger = structlog.get_logger()


SECTOR_BENCHMARKS = {
    "zorg": {
        "year": 2026,
        "time_to_fill_days": 65,
        "cost_per_hire": 4200,
        "turnover_rate": 14.2,
        "absenteeism_rate": 6.1,
        "burnout_prevalence": 22.0,
        "avg_labour_cost_fte": 52000,
        "cost_per_sick_day": 185,
        "long_term_absence_pct": 28,
        "burnout_cost_per_case": 145000,
        "data_source": "CBS Labour Statistics 2026",
        "confidence": "high",
    },
    "overheid": {
        "year": 2026,
        "time_to_fill_days": 85,
        "cost_per_hire": 5800,
        "turnover_rate": 8.5,
        "absenteeism_rate": 5.2,
        "burnout_prevalence": 16.0,
        "avg_labour_cost_fte": 58000,
        "cost_per_sick_day": 210,
        "long_term_absence_pct": 24,
        "burnout_cost_per_case": 133000,
        "data_source": "CBS + NPK Government Survey",
        "confidence": "high",
    },
    "bouw": {
        "year": 2026,
        "time_to_fill_days": 45,
        "cost_per_hire": 3200,
        "turnover_rate": 18.5,
        "absenteeism_rate": 5.9,
        "burnout_prevalence": 18.0,
        "avg_labour_cost_fte": 45000,
        "cost_per_sick_day": 165,
        "long_term_absence_pct": 22,
        "burnout_cost_per_case": 125000,
        "data_source": "CBS + FENIT Construction",
        "confidence": "medium",
    },
    "energie": {
        "year": 2026,
        "time_to_fill_days": 72,
        "cost_per_hire": 6500,
        "turnover_rate": 7.2,
        "absenteeism_rate": 4.8,
        "burnout_prevalence": 12.0,
        "avg_labour_cost_fte": 62000,
        "cost_per_sick_day": 225,
        "long_term_absence_pct": 20,
        "burnout_cost_per_case": 140000,
        "data_source": "CBS + Energie Veilig",
        "confidence": "high",
    },
    "onderwijs": {
        "year": 2026,
        "time_to_fill_days": 58,
        "cost_per_hire": 3800,
        "turnover_rate": 9.1,
        "absenteeism_rate": 5.4,
        "burnout_prevalence": 19.0,
        "avg_labour_cost_fte": 48000,
        "cost_per_sick_day": 175,
        "long_term_absence_pct": 26,
        "burnout_cost_per_case": 128000,
        "data_source": "CBS + PO-Raad Education",
        "confidence": "high",
    },
    "transport": {
        "year": 2026,
        "time_to_fill_days": 52,
        "cost_per_hire": 2900,
        "turnover_rate": 17.8,
        "absenteeism_rate": 6.2,
        "burnout_prevalence": 15.0,
        "avg_labour_cost_fte": 42000,
        "cost_per_sick_day": 155,
        "long_term_absence_pct": 21,
        "burnout_cost_per_case": 118000,
        "data_source": "CBS + TLV Transport",
        "confidence": "medium",
    },
}


async def _ensure_calculation_tables():
    """Create calculation tables if they don't exist yet."""
    migration_sql = """
    CREATE TABLE IF NOT EXISTS sector_benchmarks (
        id SERIAL PRIMARY KEY,
        sector_id VARCHAR(50) NOT NULL,
        sector_name VARCHAR(100) NOT NULL,
        subsector VARCHAR(100),
        year INTEGER NOT NULL,
        quarter INTEGER,
        total_workforce_fte INTEGER,
        avg_labour_cost_fte NUMERIC(10,2),
        labour_cost_ratio NUMERIC(5,2),
        avg_revenue_per_fte NUMERIC(12,2),
        sector_total_revenue_eur NUMERIC(15,2),
        vacancy_rate NUMERIC(5,2),
        open_vacancies INTEGER,
        time_to_fill_days NUMERIC(6,1),
        cost_per_hire NUMERIC(10,2),
        cost_per_vacancy_month NUMERIC(10,2),
        turnover_rate NUMERIC(5,2),
        turnover_cost_per_exit NUMERIC(10,2),
        turnover_cost_pct_salary NUMERIC(5,2),
        absenteeism_rate NUMERIC(5,2),
        cost_per_sick_day NUMERIC(8,2),
        burnout_prevalence NUMERIC(5,2),
        burnout_cost_per_case NUMERIC(10,2),
        long_term_absence_pct NUMERIC(5,2),
        productivity_index NUMERIC(8,2),
        overhead_ratio NUMERIC(5,2),
        span_of_control NUMERIC(4,1),
        ai_adoption_rate NUMERIC(5,2),
        robotics_adoption_rate NUMERIC(5,2),
        automation_roi_typical NUMERIC(5,2),
        automation_payback_months NUMERIC(5,1),
        digital_invest_per_fte NUMERIC(10,2),
        training_investment_per_fte NUMERIC(10,2),
        internal_mobility_rate NUMERIC(5,2),
        flex_ratio NUMERIC(5,2),
        source VARCHAR(500),
        confidence_level VARCHAR(20) DEFAULT 'medium',
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(sector_id, subsector, year, quarter)
    );

    CREATE TABLE IF NOT EXISTS calculation_defaults (
        id SERIAL PRIMARY KEY,
        calculation_type VARCHAR(50) NOT NULL,
        parameter_name VARCHAR(100) NOT NULL,
        sector_id VARCHAR(50),
        default_value NUMERIC(15,4) NOT NULL,
        unit VARCHAR(30),
        min_value NUMERIC(15,4),
        max_value NUMERIC(15,4),
        description TEXT,
        source VARCHAR(500),
        year INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(calculation_type, parameter_name, sector_id)
    );

    CREATE TABLE IF NOT EXISTS calculation_results (
        id SERIAL PRIMARY KEY,
        calculation_type VARCHAR(50) NOT NULL,
        sector_id VARCHAR(50),
        input_parameters JSONB NOT NULL,
        output_results JSONB NOT NULL,
        methodology TEXT,
        confidence_level VARCHAR(20),
        user_session_id VARCHAR(100),
        source_context VARCHAR(200),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    await execute(migration_sql)

    # Create indexes (IF NOT EXISTS not supported for all PG versions, so wrap in try)
    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS idx_benchmarks_sector_year ON sector_benchmarks(sector_id, year)",
        "CREATE INDEX IF NOT EXISTS idx_defaults_calc_sector ON calculation_defaults(calculation_type, sector_id)",
        "CREATE INDEX IF NOT EXISTS idx_results_type ON calculation_results(calculation_type, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_results_session ON calculation_results(user_session_id)",
    ]:
        try:
            await execute(idx_sql)
        except Exception:
            pass  # Index already exists

    logger.info("calculation_tables_ensured")


async def _cleanup_legacy_healthcare_row():
    """
    Delete the legacy sector_id='healthcare' row if it exists.

    Before phase 5a the SectorEnum used 'healthcare' as the zorg slug.
    Post-5a all endpoints use 'zorg'. The old row is dead data —
    clean it up for hygiene. Idempotent: no-op if absent.
    """
    try:
        result = await execute(
            "DELETE FROM sector_benchmarks WHERE sector_id = $1",
            "healthcare",
        )
        logger.info("legacy_healthcare_row_cleanup_attempted")
    except Exception as e:
        logger.warning("legacy_healthcare_cleanup_failed", error=str(e))


async def seed_sector_benchmarks():
    """Create tables (if needed) and load sector benchmarks."""
    logger.info("seeding_sector_benchmarks_start")

    # Ensure tables exist before seeding
    await _ensure_calculation_tables()

    # Clean up legacy 'healthcare' row from pre-5a days
    await _cleanup_legacy_healthcare_row()

    for sector_id, benchmark_data in SECTOR_BENCHMARKS.items():
        try:
            # Check if benchmark exists
            existing = await fetch_one(
                "SELECT id FROM sector_benchmarks WHERE sector_id = $1 AND year = $2",
                sector_id,
                benchmark_data["year"],
            )

            if existing:
                logger.info("benchmark_already_exists", sector=sector_id)
                continue

            # Insert new benchmark
            await execute(
                """INSERT INTO sector_benchmarks
                   (sector_id, sector_name, year,
                    time_to_fill_days, cost_per_hire, turnover_rate,
                    absenteeism_rate, burnout_prevalence, avg_labour_cost_fte,
                    cost_per_sick_day, long_term_absence_pct, burnout_cost_per_case,
                    source, confidence_level)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)""",
                sector_id,
                sector_id.capitalize(),
                benchmark_data["year"],
                benchmark_data["time_to_fill_days"],
                benchmark_data["cost_per_hire"],
                benchmark_data["turnover_rate"],
                benchmark_data["absenteeism_rate"],
                benchmark_data["burnout_prevalence"],
                benchmark_data["avg_labour_cost_fte"],
                benchmark_data["cost_per_sick_day"],
                benchmark_data["long_term_absence_pct"],
                benchmark_data["burnout_cost_per_case"],
                benchmark_data["data_source"],
                benchmark_data["confidence"],
            )

            logger.info("benchmark_seeded", sector=sector_id)

        except Exception as e:
            logger.error("benchmark_seed_error", sector=sector_id, error=str(e))

    logger.info("seeding_sector_benchmarks_complete")
