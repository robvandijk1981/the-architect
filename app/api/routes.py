"""API routes — all Architect endpoints."""

import json
import time
import uuid
from typing import Any


def _parse_jsonb(value: Any) -> dict | list | None:
    """Safely parse a JSONB value that asyncpg may return as raw JSON string."""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, (dict, list)):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
    return None

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, Form
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
    """
    Health check endpoint for Railway.

    Performs a real roundtrip `SELECT 1` to verify the database is reachable —
    more reliable than pool.get_size() which can be 0 immediately after
    startup while the pool is still lazy-initialising.
    """
    db_ok = False
    try:
        result = await fetch_val("SELECT 1")
        db_ok = result == 1
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

    # Resolve effective sector: top-level override wins, else fall back
    # to the profile's sector. See AnalysisRequest docstring.
    effective_sector = request.sector or request.organization_profile.sector

    # Run analysis in background
    background_tasks.add_task(
        _run_analysis,
        analysis_id,
        request.organization_profile,
        effective_sector,
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

    results = _parse_jsonb(analysis.get("results")) or {}

    return AnalysisResponse(
        analysis_id=str(analysis["id"]),
        status=AnalysisStatus(analysis["status"]),
        risk_matrix=_parse_jsonb(analysis.get("risk_matrix")),
        business_case=_parse_jsonb(analysis.get("business_case")),
        workforce_health_score=results.get("workforce_health_score") if results else None,
        arbeidsmarkt_analyse=results.get("arbeidsmarkt_analyse") if results else None,
        ai_impact_analyse=results.get("ai_impact_analyse") if results else None,
        skills_gap_analyse=results.get("skills_gap_analyse") if results else None,
        verloop_verzuim_diagnose=results.get("verloop_verzuim_diagnose") if results else None,
        actieplan=results.get("actieplan") if results else None,
        sources=_parse_jsonb(analysis.get("sources_used")) or [],
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

    try:
        answer, citations = await rag.query(
            question=request.message,
            sector=sector,
            organization_context=org_context,
        )
    except Exception as e:
        logger.error("chat_failed", error=str(e), error_type=type(e).__name__)
        raise HTTPException(
            status_code=500,
            detail=f"Chat pipeline failed: {type(e).__name__}: {str(e)[:500]}",
        )

    return ChatResponse(
        response=answer,
        sources=[c.model_dump() for c in citations],
        suggested_actions=[],  # TODO: extract from answer
    )


# ============================================
# GET /debug/chat — Diagnose chat pipeline step by step
# ============================================

@router.get("/debug/chat")
async def debug_chat(
    _: str = Depends(verify_api_key),
):
    """
    Step-by-step diagnostic of the chat pipeline.
    Tests: DB → Voyage AI embedding → Anthropic Claude.
    """
    results = {"db": None, "voyage_embed": None, "vector_search": None, "anthropic": None}

    # Step 1: Database
    try:
        stats = await fetch_one("SELECT * FROM knowledge_stats()")
        results["db"] = {"status": "ok", "stats": stats}
    except Exception as e:
        results["db"] = {"status": "error", "error": f"{type(e).__name__}: {e}"}
        return results

    # Step 2: Voyage AI embedding
    try:
        from app.services.embedder import EmbeddingService
        embedder = EmbeddingService()
        embedding = await embedder.embed_query("test query arbeidsmarkt")
        results["voyage_embed"] = {"status": "ok", "dimensions": len(embedding)}
    except Exception as e:
        results["voyage_embed"] = {"status": "error", "error": f"{type(e).__name__}: {e}"}
        return results

    # Step 3: Vector search
    try:
        from app.core.database import vector_search as db_vector_search
        chunks = await db_vector_search(
            query_embedding=embedding,
            match_count=3,
            similarity_threshold=0.25,
        )
        results["vector_search"] = {"status": "ok", "chunks_found": len(chunks)}
    except Exception as e:
        results["vector_search"] = {"status": "error", "error": f"{type(e).__name__}: {e}"}
        return results

    # Step 4: Anthropic Claude
    try:
        import anthropic
        from app.core.config import get_settings
        settings = get_settings()
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=50,
            messages=[{"role": "user", "content": "Zeg alleen: OK"}],
        )
        results["anthropic"] = {
            "status": "ok",
            "model": settings.claude_model,
            "response": response.content[0].text[:100],
        }
    except Exception as e:
        results["anthropic"] = {"status": "error", "error": f"{type(e).__name__}: {e}"}

    return results


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
# POST /admin/seed — Seed knowledge base
# ============================================

@router.post("/admin/seed")
async def admin_seed(
    _: str = Depends(verify_api_key),
):
    """Seed the knowledge base with ModellenWerk research files."""
    from app.pipeline.seed import seed_knowledge_base_online

    try:
        result = await seed_knowledge_base_online()
        return {"status": "seed_complete", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Seed failed: {type(e).__name__}: {e}")


# ============================================
# POST /admin/upload — Upload a document to the knowledge base
# ============================================

@router.post("/admin/upload")
async def admin_upload(
    file: UploadFile,
    title: str = Form(...),
    category: str = Form("sectorkennis"),
    layer: int = Form(2),
    source_type: str = Form("own_research"),
    sector: str = Form(None),
    _: str = Depends(verify_api_key),
):
    """
    Upload a document to the knowledge base.
    Supported: .md, .txt, .pdf (text extraction)
    The document is chunked, embedded, and stored immediately.
    """
    from app.services.embedder import EmbeddingService
    from app.models.knowledge import KnowledgeDocument, SourceType, KnowledgeCategory

    # Read file content
    raw = await file.read()
    filename = file.filename or "upload.md"

    if filename.endswith(".pdf"):
        # Extract text from PDF
        try:
            import pypdf
            import io
            reader = pypdf.PdfReader(io.BytesIO(raw))
            content = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as e:
            return {"status": "error", "error": f"PDF extraction failed: {e}"}
    else:
        content = raw.decode("utf-8")

    if len(content.strip()) < 50:
        return {"status": "error", "error": "Document too short or empty"}

    # Parse enums
    try:
        src_type = SourceType(source_type)
    except ValueError:
        src_type = SourceType.OWN_RESEARCH

    try:
        cat = KnowledgeCategory(category)
    except ValueError:
        cat = KnowledgeCategory.SECTORKENNIS

    sector_list = [s.strip() for s in sector.split(",")] if sector else None

    doc = KnowledgeDocument(
        source_name=f"Upload: {filename}",
        source_url=None,
        source_type=src_type,
        category=cat,
        layer=layer,
        sector=sector_list,
        title=title,
        content=content,
        metadata={
            "uploaded": True,
            "original_filename": filename,
        },
        source_date=__import__("datetime").date.today(),
    )

    embedder = EmbeddingService()
    try:
        doc_id, chunks = await embedder.process_document(doc)
        return {
            "status": "ok",
            "document_id": doc_id,
            "title": title,
            "chunks_created": len(chunks),
            "content_length": len(content),
            "category": cat.value,
            "layer": layer,
        }
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}


# ============================================
# GET /admin/documents — List all documents in the knowledge base
# ============================================

@router.get("/admin/documents")
async def admin_list_documents(
    layer: int | None = None,
    category: str | None = None,
    sector: str | None = None,
    source_type: str | None = None,
    limit: int = 500,
    offset: int = 0,
    _: str = Depends(verify_api_key),
):
    """
    List all documents in the RAG knowledge base with metadata and chunk counts.
    Supports filtering on layer, category, sector, source_type.
    """
    # Build query dynamically
    conditions = ["d.is_current = true"]
    params = []
    param_idx = 0

    if layer is not None:
        param_idx += 1
        conditions.append(f"d.layer = ${param_idx}")
        params.append(layer)
    if category is not None:
        param_idx += 1
        conditions.append(f"d.category = ${param_idx}")
        params.append(category)
    if sector is not None:
        param_idx += 1
        conditions.append(f"${param_idx} = ANY(d.sector)")
        params.append(sector)
    if source_type is not None:
        param_idx += 1
        conditions.append(f"d.source_type = ${param_idx}")
        params.append(source_type)

    where_clause = " AND ".join(conditions)

    # Count total (before pagination)
    count_query = f"SELECT COUNT(*) FROM knowledge_documents d WHERE {where_clause}"
    total = await fetch_val(count_query, *params)

    # Fetch documents with chunk count and first excerpt
    param_idx += 1
    limit_param = param_idx
    param_idx += 1
    offset_param = param_idx
    params.extend([limit, offset])

    docs_query = f"""
        SELECT
            d.id,
            d.title,
            d.source_name,
            d.source_type,
            d.category,
            d.layer,
            d.sector,
            d.source_date,
            d.created_at,
            d.metadata,
            (SELECT COUNT(*) FROM knowledge_embeddings e WHERE e.document_id = d.id) AS chunk_count,
            (SELECT LEFT(e2.chunk_text, 200) FROM knowledge_embeddings e2
             WHERE e2.document_id = d.id ORDER BY e2.chunk_index LIMIT 1) AS excerpt
        FROM knowledge_documents d
        WHERE {where_clause}
        ORDER BY d.created_at DESC
        LIMIT ${limit_param} OFFSET ${offset_param}
    """
    rows = await fetch_all(docs_query, *params)

    documents = []
    for row in rows:
        # Extract filename from metadata or source_name
        metadata = _parse_jsonb(row.get("metadata")) or {}
        filename = metadata.get("original_filename")
        if not filename and row.get("source_name"):
            # Strip "Upload: " prefix if present
            sn = row["source_name"]
            filename = sn.replace("Upload: ", "") if sn.startswith("Upload: ") else sn

        # Derive filetype
        filetype = None
        if filename and "." in filename:
            filetype = filename.rsplit(".", 1)[-1].lower()

        # Parse sector (stored as text[] in postgres)
        sector_val = row.get("sector")
        if isinstance(sector_val, list):
            sector_str = ",".join(sector_val) if sector_val else None
        else:
            sector_str = sector_val

        documents.append({
            "id": str(row["id"]),
            "title": row.get("title"),
            "filename": filename,
            "filetype": filetype,
            "category": row.get("category"),
            "layer": row.get("layer"),
            "source_type": row.get("source_type"),
            "sector": sector_str,
            "uploaded_at": str(row.get("source_date") or row.get("created_at", ""))[:10],
            "chunk_count": row.get("chunk_count", 0),
            "excerpt": row.get("excerpt"),
        })

    return {
        "total": total or 0,
        "documents": documents,
    }


# ============================================
# POST /admin/collect — Run data collectors
# ============================================

@router.post("/admin/collect")
async def admin_collect(
    background_tasks: BackgroundTasks,
    _: str = Depends(verify_api_key),
):
    """Run all data collectors (CBS, UWV, AZW)."""
    from app.pipeline.orchestrator import run_pipeline_online

    background_tasks.add_task(run_pipeline_online)
    return {"status": "collection_started", "message": "Collectors running in background. Check /api/v1/stats for progress."}


# ============================================
# POST /admin/install-benchmark-v2 — Upgrade benchmark SQL function
# ============================================

@router.post("/admin/install-benchmark-v2")
async def admin_install_benchmark_v2(_: str = Depends(verify_api_key)):
    """
    Install or re-apply the v2 get_sector_benchmarks SQL function.

    The v1 function (from 002_functions.sql) reads from the empty
    sector_intelligence table. The v2 aggregates live over the
    organizations table (median / min / max / p25 / p75 per metric).

    Idempotent — safe to call multiple times.
    """
    from app.pipeline.benchmark_function import install_benchmark_function_v2
    try:
        result = await install_benchmark_function_v2()
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to install benchmark function: {type(e).__name__}: {e}",
        )


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
