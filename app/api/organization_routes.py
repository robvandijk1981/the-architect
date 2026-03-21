"""API routes for organization data and business case calculations."""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from decimal import Decimal

from app.api.deps import verify_api_key
from app.core.database import fetch_all, fetch_one

router = APIRouter(prefix="/api/v1")


def _decimal_to_float(d):
    """Convert Decimal to float for JSON serialization."""
    if isinstance(d, Decimal):
        return float(d)
    return d


def _org_to_dict(row: dict) -> dict:
    """Convert an organization database row to API response."""
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "sector": row["sector_slug"],
        "fte": row.get("employee_count"),
        "personeelskosten_mln": _decimal_to_float(row.get("personeelskosten_mln")),
        "omzet_budget_mln": _decimal_to_float(row.get("omzet_budget_mln")),
        "vacatures": row.get("vacatures"),
        "verzuim_pct": _decimal_to_float(row.get("verzuim_pct")),
        "gem_jaarsalaris": _decimal_to_float(row.get("gem_jaarsalaris")),
        "kritieke_functies": row.get("kritieke_functies"),
        "kosten_krapte": {
            "totaal_mln": _decimal_to_float(row.get("kosten_krapte_totaal_mln")),
            "werving_mln": _decimal_to_float(row.get("kosten_werving_mln")),
            "onvervuld_mln": _decimal_to_float(row.get("kosten_onvervuld_mln")),
            "inhuur_mln": _decimal_to_float(row.get("kosten_inhuur_mln")),
            "verzuim_mln": _decimal_to_float(row.get("kosten_verzuim_mln")),
            "burnout_mln": _decimal_to_float(row.get("kosten_burnout_mln")),
        },
        "ai_baten": {
            "scenario_25_mln": _decimal_to_float(row.get("ai_baten_25_mln")),
            "scenario_50_mln": _decimal_to_float(row.get("ai_baten_50_mln")),
            "scenario_75_mln": _decimal_to_float(row.get("ai_baten_75_mln")),
            "fte_bespaard_50": row.get("fte_bespaard_50"),
        },
        "ai_parameters": {
            "ondersteuning_pct": _decimal_to_float(row.get("ai_ondersteuning_pct")),
            "augmentatie_pct": _decimal_to_float(row.get("ai_augmentatie_pct")),
            "vervanging_pct": _decimal_to_float(row.get("ai_vervanging_pct")),
        },
        "ai_status": row.get("ai_status"),
    }


@router.get("/organizations")
async def list_organizations(
    sector: Optional[str] = Query(None, description="Filter by sector slug (e.g., 'zorg', 'overheid')"),
    _: str = Depends(verify_api_key),
) -> dict:
    """List all organizations, optionally filtered by sector."""
    if sector:
        rows = await fetch_all(
            "SELECT * FROM organizations WHERE sector_slug = $1 AND source = 'readiness_scan_2026' ORDER BY employee_count DESC",
            sector,
        )
    else:
        rows = await fetch_all(
            "SELECT * FROM organizations WHERE source = 'readiness_scan_2026' ORDER BY sector_slug, employee_count DESC"
        )

    return {
        "organizations": [_org_to_dict(r) for r in rows],
        "total": len(rows),
        "sector": sector,
    }


@router.get("/organization/{name}")
async def get_organization(
    name: str,
    _: str = Depends(verify_api_key),
) -> dict:
    """Get detailed organization profile by name (case-insensitive partial match)."""
    row = await fetch_one(
        "SELECT * FROM organizations WHERE lower(name) LIKE '%' || lower($1) || '%' AND source = 'readiness_scan_2026' LIMIT 1",
        name,
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Organisatie '{name}' niet gevonden")

    org = _org_to_dict(row)

    # Add sector benchmark for comparison
    sector_row = await fetch_one(
        "SELECT * FROM sector_profiles WHERE sector_slug = $1",
        row["sector_slug"],
    )
    if sector_row:
        org["sector_benchmark"] = {
            "sector": sector_row["sector_slug"],
            "gem_fte": sector_row.get("fte"),
            "gem_verzuim_pct": _decimal_to_float(sector_row.get("gem_verzuim_pct")),
            "totaal_kosten_krapte_mln": _decimal_to_float(sector_row.get("kosten_krapte_mln")),
            "ai_baten_50_mln": _decimal_to_float(sector_row.get("ai_baten_50_mln")),
        }

    return org


@router.get("/sector-profiles")
async def list_sector_profiles(
    _: str = Depends(verify_api_key),
) -> dict:
    """Get all sector profiles with aggregated benchmarks."""
    rows = await fetch_all("SELECT * FROM sector_profiles ORDER BY kosten_krapte_mln DESC")

    return {
        "sectors": [
            {
                "sector": r["sector_slug"],
                "fte": r.get("fte"),
                "personeelskosten_mln": _decimal_to_float(r.get("personeelskosten_mln")),
                "omzet_budget_mln": _decimal_to_float(r.get("omzet_budget_mln")),
                "vacatures": r.get("vacatures"),
                "gem_verzuim_pct": _decimal_to_float(r.get("gem_verzuim_pct")),
                "kosten_krapte_mln": _decimal_to_float(r.get("kosten_krapte_mln")),
                "ai_parameters": {
                    "ondersteuning_pct": _decimal_to_float(r.get("ai_ondersteuning_pct")),
                    "augmentatie_pct": _decimal_to_float(r.get("ai_augmentatie_pct")),
                    "vervanging_pct": _decimal_to_float(r.get("ai_vervanging_pct")),
                },
                "ai_baten": {
                    "scenario_25_mln": _decimal_to_float(r.get("ai_baten_25_mln")),
                    "scenario_50_mln": _decimal_to_float(r.get("ai_baten_50_mln")),
                    "scenario_75_mln": _decimal_to_float(r.get("ai_baten_75_mln")),
                    "fte_bespaard_50": r.get("fte_bespaard_50"),
                },
                "kritieke_functies": r.get("kritieke_functies"),
            }
            for r in rows
        ],
        "total": len(rows),
    }


@router.post("/organization/simulate")
async def simulate_organization(
    fte: int = Query(..., description="Aantal FTE"),
    sector: str = Query(..., description="Sector slug (zorg, overheid, etc.)"),
    verzuim_pct: Optional[float] = Query(None, description="Verzuimpercentage (default: sectorgemiddelde)"),
    vacature_ratio: Optional[float] = Query(None, description="Vacatures als % van FTE (default: sectorgemiddelde)"),
    adoptie_pct: float = Query(50, description="AI-adoptiescenario: 25, 50, of 75%"),
    _: str = Depends(verify_api_key),
) -> dict:
    """
    Simulate a custom organization business case.
    Uses sector benchmarks with optional overrides.
    """
    # Get sector profile for defaults
    sector_row = await fetch_one(
        "SELECT * FROM sector_profiles WHERE sector_slug = $1", sector
    )
    if not sector_row:
        raise HTTPException(status_code=404, detail=f"Sector '{sector}' niet gevonden")

    # Apply defaults from sector
    actual_verzuim = verzuim_pct or float(sector_row.get("gem_verzuim_pct") or 5.5)
    sector_vac_ratio = (sector_row.get("vacatures") or 0) / max(sector_row.get("fte") or 1, 1)
    actual_vac_ratio = vacature_ratio or sector_vac_ratio
    vacatures = int(fte * actual_vac_ratio)

    # Estimate average salary from sector (personeelskosten / fte)
    sector_fte = sector_row.get("fte") or 1
    sector_pk = float(sector_row.get("personeelskosten_mln") or 0)
    gem_salaris = (sector_pk * 1_000_000) / sector_fte
    personeelskosten = fte * gem_salaris

    # Cost model (same as Readiness Scan methodology)
    kosten_werving = vacatures * gem_salaris * 0.21
    kosten_onvervuld = vacatures * gem_salaris * 0.65 * 0.4
    kosten_inhuur = vacatures * gem_salaris * 0.40 * 1.35
    kosten_verzuim = fte * (actual_verzuim / 100) * gem_salaris * 0.75
    kosten_burnout = fte * 0.008 * 133000  # 0.8% burnout rate × €133K per case
    kosten_totaal = kosten_werving + kosten_onvervuld + kosten_inhuur + kosten_verzuim + kosten_burnout

    # AI benefits (sector parameters)
    ai_o = float(sector_row.get("ai_ondersteuning_pct") or 0) / 100
    ai_a = float(sector_row.get("ai_augmentatie_pct") or 0) / 100
    ai_v = float(sector_row.get("ai_vervanging_pct") or 0) / 100
    adoptie = adoptie_pct / 100

    bruto_ondersteuning = personeelskosten * ai_o * adoptie * 0.15  # 15% productiviteitswinst
    bruto_augmentatie = personeelskosten * ai_a * adoptie * 0.25  # 25% waardecreatie
    bruto_vervanging = personeelskosten * ai_v * adoptie * 0.80  # 80% kostenreductie
    bruto_totaal = bruto_ondersteuning + bruto_augmentatie + bruto_vervanging
    investering = bruto_totaal * 0.20  # 20% implementatiekosten
    netto_baten = bruto_totaal - investering
    fte_bespaard = int(netto_baten / gem_salaris) if gem_salaris > 0 else 0

    return {
        "simulatie": {
            "fte": fte,
            "sector": sector,
            "verzuim_pct": actual_verzuim,
            "vacatures": vacatures,
            "adoptie_pct": adoptie_pct,
            "gem_jaarsalaris": round(gem_salaris),
            "personeelskosten_mln": round(personeelskosten / 1_000_000, 1),
        },
        "kosten_krapte": {
            "totaal_mln": round(kosten_totaal / 1_000_000, 1),
            "werving_mln": round(kosten_werving / 1_000_000, 1),
            "onvervuld_mln": round(kosten_onvervuld / 1_000_000, 1),
            "inhuur_mln": round(kosten_inhuur / 1_000_000, 1),
            "verzuim_mln": round(kosten_verzuim / 1_000_000, 1),
            "burnout_mln": round(kosten_burnout / 1_000_000, 1),
        },
        "ai_baten": {
            "ondersteuning_mln": round(bruto_ondersteuning / 1_000_000, 1),
            "augmentatie_mln": round(bruto_augmentatie / 1_000_000, 1),
            "vervanging_mln": round(bruto_vervanging / 1_000_000, 1),
            "bruto_totaal_mln": round(bruto_totaal / 1_000_000, 1),
            "investering_mln": round(investering / 1_000_000, 1),
            "netto_baten_mln": round(netto_baten / 1_000_000, 1),
            "fte_equivalent_bespaard": fte_bespaard,
        },
        "ratio_baten_vs_kosten": round(netto_baten / max(kosten_totaal, 1), 2),
        "sector_benchmark": {
            "kosten_krapte_sector_mln": _decimal_to_float(sector_row.get("kosten_krapte_mln")),
            "ai_baten_50_sector_mln": _decimal_to_float(sector_row.get("ai_baten_50_mln")),
        },
    }
