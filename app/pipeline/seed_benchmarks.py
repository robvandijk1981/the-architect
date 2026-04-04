"""
Seed sector benchmark data into PostgreSQL.
Called during app startup to populate initial benchmark data.
"""

import structlog
from app.core.database import execute, fetch_one

logger = structlog.get_logger()


SECTOR_BENCHMARKS = {
    "healthcare": {
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


async def seed_sector_benchmarks():
    """Load all sector benchmarks into database if not already present."""
    logger.info("seeding_sector_benchmarks_start")

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
