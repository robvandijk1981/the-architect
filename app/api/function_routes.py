"""API routes for function impact data — structured, queryable workforce intelligence."""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

from app.api.deps import verify_api_key
from app.core.database import fetch_all, fetch_one, get_connection
from app.models.functions import (
    FunctionProfile, FunctionSummary, FunctionListResponse,
    ImpactPercentages, ImpactDimensions, TaskChange,
    CompetencyChange, PeriodDetail, TimelineResponse,
)

router = APIRouter(prefix="/api/v1")


def _build_dimensions(row: dict) -> ImpactDimensions:
    """Build ImpactDimensions from a database row."""
    return ImpactDimensions(
        fte_impact=row.get("dim_fte_impact"),
        functie_invulling=row.get("dim_functie_invulling"),
        werving_arbeidsmarkt=row.get("dim_werving_arbeidsmarkt"),
        competenties_scholing=row.get("dim_competenties_scholing"),
        kennisbehoud=row.get("dim_kennisbehoud"),
        werkbeleving_autonomie=row.get("dim_werkbeleving_autonomie"),
        productiviteit_kwaliteit=row.get("dim_productiviteit_kwaliteit"),
        fysieke_belasting=row.get("dim_fysieke_belasting"),
        samenwerking_locatie=row.get("dim_samenwerking_locatie"),
    )


async def _build_periods(function_id: str) -> list[PeriodDetail]:
    """Build full period details for a function."""
    # Get impact percentages
    impacts = await fetch_all(
        "SELECT * FROM function_impacts WHERE function_id = $1 ORDER BY period",
        function_id,
    )

    # Get tasks grouped by period
    tasks = await fetch_all(
        "SELECT * FROM function_tasks WHERE function_id = $1 ORDER BY period",
        function_id,
    )
    tasks_by_period = {}
    for t in tasks:
        p = t["period"]
        if p not in tasks_by_period:
            tasks_by_period[p] = []
        tasks_by_period[p].append(TaskChange(
            taak=t["taak"],
            type=t["type"],
            technologie=t["technologie"],
            beschrijving=t.get("beschrijving"),
        ))

    # Get competencies
    competencies = await fetch_all(
        "SELECT * FROM function_competencies WHERE function_id = $1 ORDER BY period",
        function_id,
    )
    comp_by_period = {}
    for c in competencies:
        comp_by_period[c["period"]] = CompetencyChange(
            period=c["period"],
            nieuwe_competenties=c.get("nieuwe_competenties") or [],
            vervallen_competenties=c.get("vervallen_competenties") or [],
            nieuwe_technische_vaardigheden=c.get("nieuwe_technische_vaardigheden") or [],
            vervallen_technische_vaardigheden=c.get("vervallen_technische_vaardigheden") or [],
            kennisoverdracht=c.get("kennisoverdracht"),
        )

    periods = []
    for imp in impacts:
        period = imp["period"]
        periods.append(PeriodDetail(
            period=period,
            impact=ImpactPercentages(
                period=period,
                robotisering_ondersteuning=float(imp.get("robotisering_ondersteuning") or 0),
                robotisering_augmentatie=float(imp.get("robotisering_augmentatie") or 0),
                robotisering_vervanging=float(imp.get("robotisering_vervanging") or 0),
                ai_ondersteuning=float(imp.get("ai_ondersteuning") or 0),
                ai_augmentatie=float(imp.get("ai_augmentatie") or 0),
                ai_vervanging=float(imp.get("ai_vervanging") or 0),
                kennisoverdracht=imp.get("kennisoverdracht"),
            ),
            tasks=tasks_by_period.get(period, []),
            competencies=comp_by_period.get(period),
        ))

    return periods


# ============================================
# Endpoints
# ============================================

@router.get("/functions")
async def list_functions(
    sector: Optional[str] = Query(None, description="Filter by sector (e.g., 'Zorg', 'Overheid')"),
    functiegroep: Optional[str] = Query(None, description="Filter by functiegroep"),
    period: Optional[str] = Query(None, description="Filter by period (e.g., '2028-2030')"),
    _: str = Depends(verify_api_key),
) -> FunctionListResponse:
    """
    List all functions with summary data.
    Optionally filter by sector, functiegroep, or period.
    """
    conditions = ["1=1"]
    params = []
    param_idx = 1

    if sector:
        conditions.append(f"fp.sector = ${param_idx}")
        params.append(sector)
        param_idx += 1
    if functiegroep:
        conditions.append(f"fp.functiegroep = ${param_idx}")
        params.append(functiegroep)
        param_idx += 1

    where = " AND ".join(conditions)

    query = f"""
        SELECT fp.*,
            fi_latest.ai_ondersteuning + fi_latest.ai_augmentatie + fi_latest.ai_vervanging as ai_total_latest,
            fi_latest.robotisering_ondersteuning + fi_latest.robotisering_augmentatie + fi_latest.robotisering_vervanging as robot_total_latest
        FROM function_profiles fp
        LEFT JOIN LATERAL (
            SELECT * FROM function_impacts
            WHERE function_id = fp.id
            ORDER BY period DESC LIMIT 1
        ) fi_latest ON true
        WHERE {where}
        ORDER BY fp.sector, fp.functiegroep, fp.functie
    """

    rows = await fetch_all(query, *params)

    functions = []
    for row in rows:
        functions.append(FunctionSummary(
            id=str(row["id"]),
            sector=row["sector"],
            functiegroep=row["functiegroep"],
            functie=row["functie"],
            dimensions=_build_dimensions(row),
            ai_total_2037=float(row.get("ai_total_latest") or 0),
            robot_total_2037=float(row.get("robot_total_latest") or 0),
        ))

    return FunctionListResponse(
        functions=functions,
        total=len(functions),
        sector=sector,
        period=period,
    )


@router.get("/function/{sector}/{functie}")
async def get_function(
    sector: str,
    functie: str,
    _: str = Depends(verify_api_key),
) -> FunctionProfile:
    """
    Get full function profile with all periods, tasks, and competencies.
    Sector and functie are case-insensitive.
    """
    row = await fetch_one(
        "SELECT * FROM function_profiles WHERE lower(sector) = lower($1) AND lower(functie) = lower($2)",
        sector, functie,
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Functie '{functie}' niet gevonden in sector '{sector}'")

    func_id = str(row["id"])
    periods = await _build_periods(func_id)

    return FunctionProfile(
        id=func_id,
        sector=row["sector"],
        functiegroep=row["functiegroep"],
        functie=row["functie"],
        dimensions=_build_dimensions(row),
        periods=periods,
    )


@router.get("/timeline/{sector}/{functie}")
async def get_timeline(
    sector: str,
    functie: str,
    _: str = Depends(verify_api_key),
) -> TimelineResponse:
    """
    Get the complete 15-year transformation timeline for a function.
    Shows how the function evolves from 2025 to 2040.
    """
    row = await fetch_one(
        "SELECT * FROM function_profiles WHERE lower(sector) = lower($1) AND lower(functie) = lower($2)",
        sector, functie,
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Functie '{functie}' niet gevonden in sector '{sector}'")

    func_id = str(row["id"])
    periods = await _build_periods(func_id)

    return TimelineResponse(
        sector=row["sector"],
        functiegroep=row["functiegroep"],
        functie=row["functie"],
        dimensions=_build_dimensions(row),
        timeline=periods,
    )


@router.post("/admin/reseed-functions")
async def admin_reseed_functions(
    _: str = Depends(verify_api_key),
) -> dict:
    """Force reseed of function impact data. Clears existing data and reloads from JSON."""
    import traceback
    try:
        # Drop constraints first
        async with get_connection() as conn:
            await conn.execute("""
                DO $$ BEGIN
                    ALTER TABLE function_tasks DROP CONSTRAINT IF EXISTS function_tasks_type_check;
                    ALTER TABLE function_tasks DROP CONSTRAINT IF EXISTS function_tasks_technologie_check;
                EXCEPTION WHEN OTHERS THEN NULL;
                END $$;
            """)
            # Clear existing data
            await conn.execute("DELETE FROM function_tasks")
            await conn.execute("DELETE FROM function_competencies")
            await conn.execute("DELETE FROM function_impacts")
            await conn.execute("DELETE FROM function_profiles")

        # Re-run seed
        from app.pipeline.seed_functions import seed_function_data
        await seed_function_data()

        count = await fetch_one("SELECT count(*) as cnt FROM function_profiles")
        return {"status": "ok", "functions_seeded": count.get("cnt", 0) if count else 0}
    except Exception as e:
        return {"status": "error", "error": str(e), "traceback": traceback.format_exc()}


@router.post("/admin/reseed-organizations")
async def admin_reseed_organizations(
    _: str = Depends(verify_api_key),
) -> dict:
    """Force reseed of organization data. Runs migration + seed."""
    import traceback
    try:
        # Run migration inline (more reliable than file-based migration)
        async with get_connection() as conn:
            # Add columns to organizations table
            for col in [
                "personeelskosten_mln DECIMAL(10,2)", "omzet_budget_mln DECIMAL(12,2)",
                "vacatures INTEGER", "verzuim_pct DECIMAL(5,2)", "gem_jaarsalaris DECIMAL(10,0)",
                "kritieke_functies TEXT", "kosten_krapte_totaal_mln DECIMAL(10,2)",
                "kosten_werving_mln DECIMAL(10,2)", "kosten_onvervuld_mln DECIMAL(10,2)",
                "kosten_inhuur_mln DECIMAL(10,2)", "kosten_verzuim_mln DECIMAL(10,2)",
                "kosten_burnout_mln DECIMAL(10,2)", "ai_baten_25_mln DECIMAL(10,2)",
                "ai_baten_50_mln DECIMAL(10,2)", "ai_baten_75_mln DECIMAL(10,2)",
                "fte_bespaard_50 INTEGER", "ai_ondersteuning_pct DECIMAL(5,2)",
                "ai_augmentatie_pct DECIMAL(5,2)", "ai_vervanging_pct DECIMAL(5,2)",
                "ai_status TEXT",
            ]:
                try:
                    await conn.execute(f"ALTER TABLE organizations ADD COLUMN IF NOT EXISTS {col}")
                except Exception:
                    pass

            # Create sector_profiles table (TIMESTAMPTZ for tz-aware freshness checks)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS sector_profiles (
                    sector_slug TEXT PRIMARY KEY,
                    fte INTEGER NOT NULL,
                    personeelskosten_mln DECIMAL(10,2),
                    omzet_budget_mln DECIMAL(12,2),
                    vacatures INTEGER,
                    gem_verzuim_pct DECIMAL(5,2),
                    kosten_krapte_mln DECIMAL(10,2),
                    ai_ondersteuning_pct DECIMAL(5,2),
                    ai_augmentatie_pct DECIMAL(5,2),
                    ai_vervanging_pct DECIMAL(5,2),
                    ai_baten_25_mln DECIMAL(10,2),
                    ai_baten_50_mln DECIMAL(10,2),
                    ai_baten_75_mln DECIMAL(10,2),
                    fte_bespaard_50 INTEGER,
                    kritieke_functies TEXT,
                    created_at TIMESTAMPTZ DEFAULT now(),
                    updated_at TIMESTAMPTZ DEFAULT now()
                )
            """)

            # Migrate existing tables from TIMESTAMP to TIMESTAMPTZ (idempotent)
            for col in ("created_at", "updated_at"):
                try:
                    await conn.execute(
                        f"ALTER TABLE sector_profiles ALTER COLUMN {col} "
                        f"TYPE TIMESTAMPTZ USING {col} AT TIME ZONE 'UTC'"
                    )
                except Exception:
                    pass

        # Clean existing data before re-seed (force fresh created_at on all rows)
        from app.pipeline.seed_organizations import seed_organizations, seed_sector_profiles
        async with get_connection() as conn:
            await conn.execute("DELETE FROM organizations WHERE source = 'readiness_scan_2026'")
            await conn.execute("DELETE FROM sector_profiles")
        await seed_organizations()
        await seed_sector_profiles()

        count = await fetch_one("SELECT count(*) as cnt FROM organizations WHERE source = 'readiness_scan_2026'")
        sector_count = await fetch_one("SELECT count(*) as cnt FROM sector_profiles")
        return {
            "status": "ok",
            "organizations_seeded": count.get("cnt", 0) if count else 0,
            "sector_profiles_seeded": sector_count.get("cnt", 0) if sector_count else 0,
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "traceback": traceback.format_exc()}


@router.get("/data-freshness")
async def data_freshness(
    _: str = Depends(verify_api_key),
) -> dict:
    """
    Check data freshness across all layers and tables.
    Returns status per data source: green (<1 month), orange (1-3 months), red (>3 months).
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    layers = {}

    # Check knowledge documents per layer
    try:
        layer_stats = await fetch_all("""
            SELECT layer, category, count(*) as doc_count,
                max(created_at) as latest_update,
                min(created_at) as oldest_update
            FROM knowledge_documents
            WHERE is_current = true
            GROUP BY layer, category
            ORDER BY layer
        """)
        for row in layer_stats:
            latest = row.get("latest_update")
            if latest:
                if latest.tzinfo:
                    age_days = (now - latest).days
                else:
                    age_days = (now.replace(tzinfo=None) - latest).days
                if age_days < 30:
                    status = "green"
                elif age_days < 90:
                    status = "orange"
                else:
                    status = "red"
            else:
                age_days = None
                status = "unknown"

            key = f"layer_{row['layer']}_{row['category']}"
            layers[key] = {
                "layer": row["layer"],
                "category": row["category"],
                "documents": row["doc_count"],
                "latest_update": str(latest)[:10] if latest else None,
                "age_days": age_days,
                "status": status,
            }
    except Exception:
        pass

    # Check structured tables (use GREATEST of created/updated; handle naive timestamps)
    tables = {}
    for table, query in [
        ("function_profiles", "SELECT count(*) as cnt, max(GREATEST(created_at, COALESCE(updated_at, created_at))) as latest FROM function_profiles"),
        ("function_impacts", "SELECT count(*) as cnt, max(created_at) as latest FROM function_impacts"),
        ("organizations", "SELECT count(*) as cnt, max(GREATEST(created_at, COALESCE(updated_at, created_at))) as latest FROM organizations WHERE source = 'readiness_scan_2026'"),
        ("sector_profiles", "SELECT count(*) as cnt, max(GREATEST(created_at, COALESCE(updated_at, created_at))) as latest FROM sector_profiles"),
    ]:
        try:
            row = await fetch_one(query)
            if row:
                latest = row.get("latest")
                if latest:
                    if latest.tzinfo:
                        age_days = (now - latest).days
                    else:
                        age_days = (now.replace(tzinfo=None) - latest).days
                else:
                    age_days = None
                tables[table] = {
                    "records": row.get("cnt", 0),
                    "latest_update": str(latest)[:10] if latest else None,
                    "age_days": age_days,
                    "status": "green" if age_days is not None and age_days < 30 else ("orange" if age_days is not None and age_days < 90 else "red"),
                }
        except Exception:
            tables[table] = {"records": 0, "status": "missing"}

    return {
        "checked_at": str(now)[:19],
        "knowledge_layers": layers,
        "structured_tables": tables,
        "summary": {
            "total_knowledge_docs": sum(v["documents"] for v in layers.values()),
            "total_structured_records": sum(v.get("records", 0) for v in tables.values()),
            "red_flags": [k for k, v in {**layers, **tables}.items() if v.get("status") == "red"],
            "orange_flags": [k for k, v in {**layers, **tables}.items() if v.get("status") == "orange"],
        },
    }


@router.get("/sectors")
async def list_sectors(
    _: str = Depends(verify_api_key),
) -> dict:
    """
    List all sectors with function counts and aggregate impact stats.
    """
    rows = await fetch_all("""
        SELECT
            fp.sector,
            count(DISTINCT fp.id) as function_count,
            count(DISTINCT fp.functiegroep) as functiegroep_count,
            round(avg(fi.ai_ondersteuning + fi.ai_augmentatie + fi.ai_vervanging), 1) as avg_ai_total,
            round(avg(fi.robotisering_ondersteuning + fi.robotisering_augmentatie + fi.robotisering_vervanging), 1) as avg_robot_total
        FROM function_profiles fp
        LEFT JOIN function_impacts fi ON fi.function_id = fp.id AND fi.period = '2037-2040'
        GROUP BY fp.sector
        ORDER BY fp.sector
    """)

    return {
        "sectors": [
            {
                "sector": r["sector"],
                "function_count": r["function_count"],
                "functiegroep_count": r["functiegroep_count"],
                "avg_ai_impact_2040": float(r.get("avg_ai_total") or 0),
                "avg_robot_impact_2040": float(r.get("avg_robot_total") or 0),
            }
            for r in rows
        ],
        "total_sectors": len(rows),
        "total_functions": sum(r["function_count"] for r in rows),
    }


@router.get("/impact-comparison")
async def compare_impacts(
    functies: str = Query(..., description="Comma-separated function names"),
    period: str = Query("2028-2030", description="Period to compare"),
    _: str = Depends(verify_api_key),
) -> dict:
    """
    Compare AI/robotisation impact across multiple functions for a given period.
    Useful for: which functions in my organization are most affected?
    """
    functie_list = [f.strip() for f in functies.split(",")]

    rows = await fetch_all("""
        SELECT fp.sector, fp.functiegroep, fp.functie,
            fi.robotisering_ondersteuning, fi.robotisering_augmentatie, fi.robotisering_vervanging,
            fi.ai_ondersteuning, fi.ai_augmentatie, fi.ai_vervanging
        FROM function_profiles fp
        JOIN function_impacts fi ON fi.function_id = fp.id AND fi.period = $1
        WHERE lower(fp.functie) = ANY($2)
        ORDER BY (fi.ai_ondersteuning + fi.ai_augmentatie + fi.ai_vervanging) DESC
    """, period, [f.lower() for f in functie_list])

    return {
        "period": period,
        "comparison": [
            {
                "sector": r["sector"],
                "functiegroep": r["functiegroep"],
                "functie": r["functie"],
                "robotisering": {
                    "ondersteuning": float(r["robotisering_ondersteuning"] or 0),
                    "augmentatie": float(r["robotisering_augmentatie"] or 0),
                    "vervanging": float(r["robotisering_vervanging"] or 0),
                    "totaal": float((r["robotisering_ondersteuning"] or 0) + (r["robotisering_augmentatie"] or 0) + (r["robotisering_vervanging"] or 0)),
                },
                "ai": {
                    "ondersteuning": float(r["ai_ondersteuning"] or 0),
                    "augmentatie": float(r["ai_augmentatie"] or 0),
                    "vervanging": float(r["ai_vervanging"] or 0),
                    "totaal": float((r["ai_ondersteuning"] or 0) + (r["ai_augmentatie"] or 0) + (r["ai_vervanging"] or 0)),
                },
            }
            for r in rows
        ],
        "count": len(rows),
    }
