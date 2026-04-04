"""
AI Interpretation routes — all /api/v1/ai/* endpoints
Claude-powered insights from calculations.
"""

import uuid
import structlog
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import verify_api_key
from app.models.calculation import (
    InterpretRequest, InterpretResponse,
    NarrativeRequest, NarrativeResponse,
    WorkforceGapRequest, WorkforceGapResponse,
    CostTrajectoryRequest, CostTrajectoryResponse,
    AnomalyDetectionResponse,
)
from app.ai_layer.interpreter import ArchitectInterpreter
from app.ai_layer.predictive import PredictiveEngine
from app.ai_layer.feedback_loop import FeedbackLoop

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


@router.post("/interpret", response_model=InterpretResponse)
async def interpret_results(
    request: InterpretRequest,
    _: str = Depends(verify_api_key),
):
    """
    Transform calculation results into human-readable Dutch insights using Claude.
    """
    try:
        insights = await ArchitectInterpreter.interpret_results(
            calculation_type=request.calculation_type,
            results=request.results,
            sector=request.sector,
            confidence_level=request.confidence_level or "medium",
        )

        return InterpretResponse(
            executive_summary=insights.get("executive_summary", ""),
            key_findings=insights.get("key_findings", []),
            recommendations=insights.get("recommendations", []),
            risk_flags=insights.get("risk_flags", []),
            confidence_assessment=insights.get("confidence_assessment", ""),
            generated_at=insights.get("generated_at", ""),
        )

    except Exception as e:
        logger.error("interpret_results_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/narrative", response_model=NarrativeResponse)
async def generate_narrative(
    request: NarrativeRequest,
    _: str = Depends(verify_api_key),
):
    """
    Generate a narrative paragraph for board presentation.
    """
    try:
        narrative = await ArchitectInterpreter.generate_narrative(
            results=request.results,
            audience=request.audience,
        )

        return NarrativeResponse(
            narrative=narrative,
            audience=request.audience,
            generated_at="",
        )

    except Exception as e:
        logger.error("generate_narrative_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workforce-gap", response_model=WorkforceGapResponse)
async def predict_workforce_gap(
    request: WorkforceGapRequest,
    _: str = Depends(verify_api_key),
):
    """
    Predict future workforce gaps using demographic modeling.
    """
    try:
        result = await PredictiveEngine.predict_workforce_gap(
            sector=request.sector,
            current_fte=request.current_fte,
            growth_rate=request.growth_rate,
            retirement_rate=request.retirement_rate,
            attrition_rate=request.attrition_rate,
            years=request.years,
        )

        # Transform projection to response format
        from app.models.calculation import GapProjectionYear

        projection = [
            GapProjectionYear(
                year=p["year"],
                fte_demand=p["fte_demand"],
                fte_available=p["fte_available"],
                gap=p["gap"],
                gap_type=p["gap_type"],
            )
            for p in result.get("projection", [])
        ]

        return WorkforceGapResponse(
            sector=result.get("sector", ""),
            current_fte=result.get("current_fte", 0),
            assumptions=result.get("assumptions", {}),
            projection=projection,
            total_gap_person_years=result.get("total_gap_person_years", 0),
            max_gap_single_year=result.get("max_gap_single_year", 0),
            peak_gap_year=result.get("peak_gap_year", 0),
            recruitment_needed=result.get("recruitment_needed", 0),
            retention_critical=result.get("retention_critical", False),
            recommendations=result.get("recommendations", []),
        )

    except Exception as e:
        logger.error("predict_workforce_gap_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cost-trajectory", response_model=CostTrajectoryResponse)
async def predict_cost_trajectory(
    request: CostTrajectoryRequest,
    _: str = Depends(verify_api_key),
):
    """
    Project cost escalation over time.
    """
    try:
        result = await PredictiveEngine.predict_cost_trajectory(
            sector=request.sector,
            current_costs=request.current_costs,
            escalation_factor=request.escalation_factor,
            years=request.years,
        )

        # Transform projection to response format
        from app.models.calculation import CostTrajectoryYear

        projection = [
            CostTrajectoryYear(
                year=p["year"],
                total=p["total"],
                breakdown=p["breakdown"],
                increase_from_current_pct=p["increase_from_current_pct"],
            )
            for p in result.get("projection", [])
        ]

        return CostTrajectoryResponse(
            sector=result.get("sector", ""),
            current_total=result.get("current_total", 0),
            assumptions=result.get("assumptions", {}),
            projection=projection,
            total_cost_5yr=result.get("total_cost_5yr", 0),
            total_cost_5yr_vs_today=result.get("total_cost_5yr_vs_today", 0),
            cagr_pct=result.get("cagr_pct", 0),
            cost_control_priority=result.get("cost_control_priority", "MEDIUM"),
            recommendations=result.get("recommendations", []),
        )

    except Exception as e:
        logger.error("predict_cost_trajectory_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/detect-anomalies", response_model=AnomalyDetectionResponse)
async def detect_anomalies(
    sector: str,
    new_data: dict,
    _: str = Depends(verify_api_key),
):
    """
    Detect anomalies by comparing new data to sector benchmarks.
    """
    try:
        result = await FeedbackLoop.detect_anomalies(
            sector=sector,
            new_data=new_data,
        )

        # Transform anomalies to response format
        from app.models.calculation import AnomalyItem

        anomalies = [
            AnomalyItem(
                kpi=a["kpi"],
                value=a["value"],
                benchmark_mean=a["benchmark_mean"],
                z_score=a["z_score"],
                severity=a["severity"],
                message=a["message"],
            )
            for a in result.get("anomalies", [])
        ]

        return AnomalyDetectionResponse(
            has_anomalies=result.get("has_anomalies", False),
            anomaly_count=result.get("anomaly_count", 0),
            anomalies=anomalies,
            action=result.get("action", "Review data quality"),
        )

    except Exception as e:
        logger.error("detect_anomalies_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sector-trend/{sector}/{kpi_name}")
async def get_sector_trend(
    sector: str,
    kpi_name: str,
    lookback_months: int = 12,
    _: str = Depends(verify_api_key),
):
    """
    Get historical trend for a KPI in a sector.
    """
    try:
        result = await FeedbackLoop.get_sector_trend(
            sector=sector,
            kpi_name=kpi_name,
            lookback_months=lookback_months,
        )

        return result

    except Exception as e:
        logger.error("get_sector_trend_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
