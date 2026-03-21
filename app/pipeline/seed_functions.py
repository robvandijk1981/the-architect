"""Seed function impact data from JSON research files into the database."""

import json
import structlog
from pathlib import Path

from app.core.database import execute, fetch_one, execute_many, get_connection

logger = structlog.get_logger()

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "function_impacts"


async def run_migration():
    """Run the function impacts migration SQL if tables don't exist."""
    migration_file = Path(__file__).parent.parent.parent / "migrations" / "003_function_impacts.sql"

    # Check if tables already exist
    exists = await fetch_one(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'function_profiles')"
    )
    if exists and exists.get("exists"):
        logger.info("function_impacts_tables_exist", status="skipping migration")
        return

    logger.info("function_impacts_running_migration")
    sql = migration_file.read_text()

    # Execute each statement separately (asyncpg doesn't support multi-statement)
    async with get_connection() as conn:
        # Split on semicolons but handle trigger/function bodies
        statements = []
        current = []
        in_function = False
        for line in sql.split('\n'):
            stripped = line.strip()
            if stripped.startswith('--') or not stripped:
                continue
            if 'LANGUAGE' in stripped and stripped.endswith(';'):
                current.append(line)
                statements.append('\n'.join(current))
                current = []
                in_function = False
                continue
            if '$$' in stripped:
                in_function = not in_function
            current.append(line)
            if stripped.endswith(';') and not in_function:
                statements.append('\n'.join(current))
                current = []
        if current:
            statements.append('\n'.join(current))

        for stmt in statements:
            stmt = stmt.strip()
            if stmt and not stmt.startswith('--'):
                try:
                    await conn.execute(stmt)
                except Exception as e:
                    # Skip errors for IF NOT EXISTS statements
                    if 'already exists' in str(e).lower():
                        continue
                    logger.warning("migration_statement_error", error=str(e), stmt=stmt[:100])

    # Drop CHECK constraints on function_tasks if they exist (data has free-form values)
    async with get_connection() as conn:
        try:
            await conn.execute("""
                DO $$ BEGIN
                    ALTER TABLE function_tasks DROP CONSTRAINT IF EXISTS function_tasks_type_check;
                    ALTER TABLE function_tasks DROP CONSTRAINT IF EXISTS function_tasks_technologie_check;
                EXCEPTION WHEN OTHERS THEN NULL;
                END $$;
            """)
        except Exception:
            pass  # Constraints may not exist

    logger.info("function_impacts_migration_complete")


async def seed_function_data():
    """Load function impact data from JSON files into the database."""

    # Check if all data is loaded (53 functions expected)
    count = await fetch_one("SELECT count(*) as cnt FROM function_profiles")
    current = count.get("cnt", 0) if count else 0
    if current >= 50:
        logger.info("function_data_already_seeded", count=current)
        return

    # Partial seed detected or first run — clean up and reseed
    if current > 0:
        logger.info("function_data_partial_seed_detected", count=current, action="reseed")
        async with get_connection() as conn:
            await conn.execute("DELETE FROM function_tasks")
            await conn.execute("DELETE FROM function_competencies")
            await conn.execute("DELETE FROM function_impacts")
            await conn.execute("DELETE FROM function_profiles")

    # Load both JSON files
    all_sectors = []
    for filename in ["research_data_part1.json", "research_data_part2.json"]:
        filepath = DATA_DIR / filename
        if not filepath.exists():
            logger.warning("function_data_file_missing", file=str(filepath))
            continue
        data = json.loads(filepath.read_text())
        all_sectors.extend(data.get("sectors", []))

    if not all_sectors:
        logger.warning("no_function_data_found")
        return

    logger.info("seeding_function_data", sectors=len(all_sectors))

    total_functions = 0
    total_impacts = 0
    total_tasks = 0
    total_competencies = 0

    async with get_connection() as conn:
        for sector in all_sectors:
            sector_name = sector["name"]

            for groep in sector.get("functiegroepen", []):
                groep_name = groep["name"]

                for functie in groep.get("functies", []):
                    functie_name = functie["name"]
                    dims = functie.get("impactDimensies", {})

                    # Insert function profile
                    row = await conn.fetchrow("""
                        INSERT INTO function_profiles (
                            sector, functiegroep, functie,
                            dim_fte_impact, dim_functie_invulling, dim_werving_arbeidsmarkt,
                            dim_competenties_scholing, dim_kennisbehoud, dim_werkbeleving_autonomie,
                            dim_productiviteit_kwaliteit, dim_fysieke_belasting, dim_samenwerking_locatie
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                        RETURNING id
                    """,
                        sector_name, groep_name, functie_name,
                        dims.get("fteImpact"), dims.get("functieInvulling"),
                        dims.get("wervingArbeidsmarkt"), dims.get("competentiesScholing"),
                        dims.get("kennisbehoud"), dims.get("werkbelevingAutonomie"),
                        dims.get("productiviteitKwaliteit"), dims.get("fysiekeBelasting"),
                        dims.get("samenwerkingLocatie"),
                    )
                    func_id = row["id"]
                    total_functions += 1

                    for period_data in functie.get("periods", []):
                        period = period_data["period"]

                        # Insert impact percentages
                        await conn.execute("""
                            INSERT INTO function_impacts (
                                function_id, period,
                                robotisering_ondersteuning, robotisering_augmentatie, robotisering_vervanging,
                                ai_ondersteuning, ai_augmentatie, ai_vervanging,
                                kennisoverdracht
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                        """,
                            func_id, period,
                            period_data.get("robotiseringOndersteuning", 0),
                            period_data.get("robotiseringAugmentatie", 0),
                            period_data.get("robotiseringVervanging", 0),
                            period_data.get("aiOndersteuning", 0),
                            period_data.get("aiAugmentatie", 0),
                            period_data.get("aiVervanging", 0),
                            period_data.get("kennisoverdracht"),
                        )
                        total_impacts += 1

                        # Insert task changes
                        for task in period_data.get("takenVerandering", []):
                            await conn.execute("""
                                INSERT INTO function_tasks (
                                    function_id, period, taak, type, technologie, beschrijving
                                ) VALUES ($1, $2, $3, $4, $5, $6)
                            """,
                                func_id, period,
                                task.get("taak", ""),
                                task.get("type", "ondersteuning"),
                                task.get("technologie", "AI"),
                                task.get("beschrijving"),
                            )
                            total_tasks += 1

                        # Insert competency changes
                        await conn.execute("""
                            INSERT INTO function_competencies (
                                function_id, period,
                                nieuwe_competenties, vervallen_competenties,
                                nieuwe_technische_vaardigheden, vervallen_technische_vaardigheden,
                                kennisoverdracht
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                        """,
                            func_id, period,
                            period_data.get("nieuweCompetencies", []),
                            period_data.get("vervallenCompetencies", []),
                            period_data.get("nieuweTechnischeVaardigheden", []),
                            period_data.get("vervallenTechnischeVaardigheden", []),
                            period_data.get("kennisoverdracht"),
                        )
                        total_competencies += 1

    logger.info(
        "function_data_seeded",
        functions=total_functions,
        impacts=total_impacts,
        tasks=total_tasks,
        competencies=total_competencies,
    )
