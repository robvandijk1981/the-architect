"""API routes — all Architect endpoints."""

import json
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
import structlog

from app.api.deps import (
    verify_api_key,
    get_rag_service,
    get_risk_calculator,
    get_businesscase_calculator,
)
from app.core.database import fetch_all, fetch_one, fetch_val, execute, execute_returning
from app.models.analysis import (
    AnalysisRequest, AnalysisResponse, AnalysisStatus,
    ChatRequest, ChatResponse,
    ExpertOverrides, OrganizationProfile, SectorSlug,
)
from app.services.rag import RAGService
from app.services.risk_calculator import RiskCalculator
from app.services.businesscase import BusinessCaseCalculator

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1")


# ============================================
# Health Check (no auth)
# ============================================

@router.get("/health")
async def health_check():
    """Health check endpoint for Railway."""
    db_ok = False
    try:
        from app.core.database import get_pool
        pool = get_pool()
        db_ok = pool is not None and pool.get_size() > 0
    except Exception:
        pass

    return {
        "status": "healthy",
        "service": "the-architect",
        "version": "0.1.0",
        "database": "connected" if db_ok else "unavailable",
    }


@router.get("/stats")
async def knowledge_stats(_: str = Depends(verify_api_key)):
    """Get knowledge base statistics."""
    result = await fetch_one("SELECT * FROM knowledge_stats()")
    return result or {}


# ============================================
# POST /analyze — Full workforce analysis
# ============================================

@router.post("/analyze", response_model=AnalysisResponse)
async def start_analysis(
    request: AnalysisRequest,
    background_tasks: BackgroundTasks,
    _: str = Depends(verify_api_key),
    rag: RAGService = Depends(get_rag_service),
    risk_calc: RiskCalculator = Depends(get_risk_calculator),
    bc_calc: BusinessCaseCalculator = Depends(get_businesscase_calculator),
):
    """
    Start a full workforce analysis. Returns immediately with analysis_id.
    The analysis runs in the background.
    """
    analysis_id = str(uuid.uuid4())
    intake_json = json.dumps(request.organization_profile.model_dump(mode="json"))

    await execute(
        """INSERT INTO analyses (id, status, intake_data) VALUES ($1::uuid, 'pending', $2::jsonb)""",
        uuid.UUID(analysis_id), intake_json,
    )

    # Run analysis in background
    background_tasks.add_task(
        _run_analysis,
        analysis_id,
        request.organization_profile,
        request.sector,
        rag,
        risk_calc,
        bc_calc,
    )

    return AnalysisResponse(
        analysis_id=analysis_id,
        status=AnalysisStatus.PROCESSING,
    )


@router.get("/analyze/{analysis_id}", response_model=AnalysisResponse)
async def get_analysis(
    analysis_id: str,
    _: str = Depends(verify_api_key),
):
    """Poll for analysis status and results."""
    analysis = await fetch_one(
        "SELECT * FROM analyses WHERE id = $1::uuid", uuid.UUID(analysis_id)
    )

    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    results = analysis.get("results") or {}
    if isinstance(results, str):
        try:
            results = json.loads(results)
        except json.JSONDecodeError:
            results = {}

    return AnalysisResponse(
        analysis_id=str(analysis["id"]),
        status=AnalysisStatus(analysis["status"]),
        risk_matrix=analysis.get("risk_matrix"),
        business_case=analysis.get("business_case"),
        workforce_health_score=results.get("workforce_health_score") if results else None,
        arbeidsmarkt_analyse=results.get("arbeidsmarkt_analyse") if results else None,
        ai_impact_analyse=results.get("ai_impact_analyse") if results else None,
        skills_gap_analyse=results.get("skills_gap_analyse") if results else None,
        verloop_verzuim_diagnose=results.get("verloop_verzuim_diagnose") if results else None,
        actieplan=results.get("actieplan") if results else None,
        sources=analysis.get("sources_used") or [],
        processing_time_ms=analysis.get("processing_time_ms"),
    )


# ============================================
# POST /risk — Risk matrix calculation
# ============================================

@router.post("/risk")
async def calculate_risk(
    profile: OrganizationProfile,
    _: str = Depends(verify_api_key),
    risk_calc: RiskCalculator = Depends(get_risk_calculator),
):
    """Calculate the 6-risk workforce risk matrix."""
    start = time.time()
    matrix = await risk_calc.calculate(profile)
    elapsed = int((time.time() - start) * 1000)

    logger.info("risk_calculated", sector=profile.sector, elapsed_ms=elapsed)
    return {**matrix.model_dump(), "processing_time_ms": elapsed}


# ============================================
# POST /businesscase — Business case calculation
# ============================================

@router.post("/businesscase")
async def calculate_businesscase(
    profile: OrganizationProfile,
    overrides: ExpertOverrides | None = None,
    _: str = Depends(verify_api_key),
    bc_calc: BusinessCaseCalculator = Depends(get_businesscase_calculator),
):
    """
    Calculate the 5-category business case.
    Accepts optional expert overrides for live recalculation.
    Target: < 2 sec response time (deterministic).
    """
    start = time.time()
    bc = await bc_calc.calculate(profile, overrides)
    elapsed = int((time.time() - start) * 1000)

    logger.info("businesscase_calculated", sector=profile.sector, elapsed_ms=elapsed)
    return {**bc.model_dump(), "processing_time_ms": elapsed}


# ============================================
# POST /chat — Conversational interface
# ============================================

@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    _: str = Depends(verify_api_key),
    rag: RAGService = Depends(get_rag_service),
):
    """Chat with the workforce specialist agent."""
    sector = request.context.get("sector")
    org_context = request.context.get("organization")

    answer, citations = await rag.query(
        question=request.message,
        sector=sector,
        organization_context=org_context,
    )

    return ChatResponse(
        response=answer,
        sources=[c.model_dump() for c in citations],
        suggested_actions=[],  # TODO: extract from answer
    )


# ============================================
# GET /benchmark/{sector} — Sector benchmarks
# ============================================

@router.get("/benchmark/{sector}")
async def get_benchmark(
    sector: str,
    _: str = Depends(verify_api_key),
):
    """Get sector benchmarks (cacheable by portal via ISR)."""
    benchmarks = await fetch_all(
        "SELECT * FROM get_sector_benchmarks($1)", sector
    )

    org_count = await fetch_val(
        "SELECT count(*) FROM organizations WHERE sector_slug = $1", sector
    )

    return {
        "sector": sector,
        "benchmarks": benchmarks,
        "organizations_count": org_count or 0,
    }


# ============================================
# GET /sector/{slug} — Sector profile
# ============================================

@router.get("/sector/{slug}")
async def get_sector(
    slug: str,
    _: str = Depends(verify_api_key),
):
    """Get full sector profile with dimensions and trends."""
    intel = await fetch_all(
        "SELECT * FROM sector_intelligence WHERE sector_slug = $1", slug
    )

    risk_params = await fetch_all(
        "SELECT * FROM get_risk_parameters($1)", slug
    )

    recent = await fetch_all(
        "SELECT * FROM knowledge_changelog ORDER BY created_at DESC LIMIT 10"
    )

    return {
        "sector": slug,
        "intelligence": intel,
        "risk_parameters": risk_params,
        "recent_changes": recent,
    }


# ============================================
# Background Task: Full Analysis
# ============================================

async def _run_analysis(
    analysis_id: str,
    profile: OrganizationProfile,
    sector: SectorSlug,
    rag: RAGService,
    risk_calc: RiskCalculator,
    bc_calc: BusinessCaseCalculator,
):
    """Run the full analysis pipeline in the background."""
    start = time.time()
    aid = uuid.UUID(analysis_id)

    try:
        # Update status
        await execute(
            "UPDATE analyses SET status = 'processing' WHERE id = $1::uuid", aid
        )

        # Step 1: Risk matrix (deterministic)
        risk_matrix = await risk_calc.calculate(profile)

        # Step 2: Business case (deterministic)
        business_case = await bc_calc.calculate(profile)

        # Step 3: AI analysis (RAG-powered)
        ai_results = await rag.analyze_organization(
            profile=profile.model_dump(),
            sector=sector.value,
        )

        elapsed = int((time.time() - start) * 1000)

        # Store results
        citations = [c.model_dump(mode="json") for c in ai_results.get("citations", [])]
        await execute(
            """UPDATE analyses SET
                status = 'completed',
                risk_matrix = $2::jsonb,
                business_case = $3::jsonb,
                results = $4::jsonb,
                sources_used = $5::jsonb,
                processing_time_ms = $6,
                completed_at = now()
               WHERE id = $1::uuid""",
            aid,
            json.dumps(risk_matrix.model_dump(mode="json")),
            json.dumps(business_case.model_dump(mode="json")),
            json.dumps(ai_results.get("raw_analysis")),
            json.dumps(citations),
            elapsed,
        )

        logger.info("analysis_completed", analysis_id=analysis_id, elapsed_ms=elapsed)

    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        logger.error("analysis_failed", analysis_id=analysis_id, error=str(e))
        await execute(
            """UPDATE analyses SET status = 'failed', error_message = $2, processing_time_ms = $3
               WHERE id = $1::uuid""",
            aid, str(e), elapsed,
        )
