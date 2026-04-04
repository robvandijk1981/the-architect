"""
Calculation API routes — all /api/v1/calculate/* endpoints
Integrates the CalculationEngine with database and Monte Carlo.
"""

import json
import uuid
import structlog
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import verify_api_key
from app.models.calculation import (
    VacancyCostInput, VacancyCostOutput,
    TurnoverCostInput, TurnoverCostOutput,
    AbsenteeismCostInput, AbsenteeismCostOutput,
    CostOfInactionInput, CostOfInactionOutput,
    ReskillingRoiInput, ReskillingRoiOutput,
    AutomationRoiInput, AutomationRoiOutput,
    ScenarioCompareInput, ScenarioCompareOutput,
    BenchmarkScoreInput, BenchmarkScoreOutput,
    ConfidenceLevel, SectorEnum,
)
from app.calculation.engine import CalculationEngine
from app.statistical.monte_carlo import MonteCarloEngine
from app.core.database import fetch_one, execute

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/calculate", tags=["calculations"])


async def _get_sector_benchmarks(sector_id: str):
    """Fetch sector benchmarks from database."""
    return await fetch_one(
        "SELECT * FROM sector_benchmarks WHERE sector_id = $1 ORDER BY year DESC LIMIT 1",
        sector_id,
    )


async def _get_calculation_defaults(calc_type: str, sector_id: str):
    """Fetch calculation defaults for a sector."""
    defaults = await fetch_one(
        """SELECT parameter_name, default_value FROM calculation_defaults
           WHERE calculation_type = $1 AND (sector_id = $2 OR sector_id IS NULL)
           ORDER BY sector_id DESC""",
        calc_type,
        sector_id,
    )
    return defaults or {}


@router.post("/vacancy-cost", response_model=VacancyCostOutput)
async def calculate_vacancy_cost(
    input_data: VacancyCostInput,
    _: str = Depends(verify_api_key),
):
    """Calculate annual cost of open vacancies."""
    try:
        benchmarks = await _get_sector_benchmarks(input_data.sector.value)

        ttf = input_data.time_to_fill_days or (benchmarks or {}).get("time_to_fill_days") or 60
        cph = input_data.cost_per_hire or (benchmarks or {}).get("cost_per_hire") or 4000

        result = CalculationEngine.vacancy_cost(
            open_vacancies=input_data.open_vacancies,
            time_to_fill_days=float(ttf),
            cost_per_hire=float(cph),
        )

        mc_result = None
        if input_data.include_monte_carlo and benchmarks:
            distributions = MonteCarloEngine.default_distributions_for_sector(benchmarks)
            mc_params = {
                "open_vacancies": input_data.open_vacancies,
                "time_to_fill_days": float(ttf),
                "cost_per_hire": float(cph),
            }
            mc_result = MonteCarloEngine.simulate(
                CalculationEngine.vacancy_cost,
                mc_params,
                {k: v for k, v in distributions.items() if k in ["time_to_fill_days", "cost_per_hire"]},
                output_key="total_annual_cost",
            )

        # Log to database
        session_id = str(uuid.uuid4())
        await execute(
            """INSERT INTO calculation_results
               (calculation_type, sector_id, input_parameters, output_results,
                user_session_id, source_context, created_at)
               VALUES ($1, $2, $3, $4, $5, $6, NOW())""",
            "vacancy_cost",
            input_data.sector.value,
            json.dumps(input_data.model_dump()),
            json.dumps(result),
            session_id,
            "api",
        )

        breakdown_dicts = [
            {
                "component": b["category"],
                "amount": b["amount_eur"],
                "percentage": round((b["amount_eur"] / result["total_annual_cost"]) * 100, 1),
                "confidence": ConfidenceLevel.MEDIUM,
            }
            for b in result.get("breakdown", [])
        ]

        return VacancyCostOutput(
            total_annual_cost=result["total_annual_cost"],
            cost_per_vacancy=result["cost_per_vacancy"],
            breakdown=breakdown_dicts,
            benchmark_comparison=result.get("benchmark_comparison", {}),
            monte_carlo=mc_result,
            methodology=result.get("methodology", ""),
            assumptions=result.get("assumptions", {}),
            sources=result.get("sources", []),
            confidence_level=ConfidenceLevel.MEDIUM,
        )

    except Exception as e:
        logger.error("vacancy_cost_calculation_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/turnover-cost", response_model=TurnoverCostOutput)
async def calculate_turnover_cost(
    input_data: TurnoverCostInput,
    _: str = Depends(verify_api_key),
):
    """Calculate annual cost of staff turnover."""
    try:
        benchmarks = await _get_sector_benchmarks(input_data.sector.value)

        tr = input_data.turnover_rate or (benchmarks or {}).get("turnover_rate") or 12.0
        salary = input_data.avg_salary or (benchmarks or {}).get("avg_labour_cost_fte") or 50000

        result = CalculationEngine.turnover_cost(
            fte_count=input_data.fte_count,
            turnover_rate=float(tr),
            avg_salary=float(salary),
        )

        mc_result = None
        if input_data.include_monte_carlo and benchmarks:
            distributions = MonteCarloEngine.default_distributions_for_sector(benchmarks)
            mc_params = {
                "fte_count": input_data.fte_count,
                "turnover_rate": float(tr),
                "avg_salary": float(salary),
                "cost_pct_junior": 50,
                "cost_pct_mid": 100,
                "cost_pct_senior": 200,
            }
            mc_result = MonteCarloEngine.simulate(
                CalculationEngine.turnover_cost,
                mc_params,
                {k: v for k, v in distributions.items() if k in ["turnover_rate"]},
                output_key="total_annual_cost",
            )

        # Log to database
        session_id = str(uuid.uuid4())
        await execute(
            """INSERT INTO calculation_results
               (calculation_type, sector_id, input_parameters, output_results,
                user_session_id, source_context, created_at)
               VALUES ($1, $2, $3, $4, $5, $6, NOW())""",
            "turnover_cost",
            input_data.sector.value,
            json.dumps(input_data.model_dump()),
            json.dumps(result),
            session_id,
            "api",
        )

        breakdown_dicts = [
            {
                "component": b["category"],
                "amount": b["amount_eur"],
                "percentage": round((b["amount_eur"] / result["total_annual_cost"]) * 100, 1),
                "confidence": ConfidenceLevel.MEDIUM,
            }
            for b in result.get("breakdown", [])
        ]

        return TurnoverCostOutput(
            total_annual_cost=result["total_annual_cost"],
            cost_per_exit=result["cost_per_exit"],
            estimated_exits_per_year=result["estimated_exits_per_year"],
            breakdown=breakdown_dicts,
            benchmark_comparison=result.get("benchmark_comparison", {}),
            monte_carlo=mc_result,
            methodology=result.get("methodology", ""),
            assumptions=result.get("assumptions", {}),
            sources=result.get("sources", []),
            confidence_level=ConfidenceLevel.MEDIUM,
        )

    except Exception as e:
        logger.error("turnover_cost_calculation_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/absenteeism-cost", response_model=AbsenteeismCostOutput)
async def calculate_absenteeism_cost(
    input_data: AbsenteeismCostInput,
    _: str = Depends(verify_api_key),
):
    """Calculate annual cost of absenteeism and burnout."""
    try:
        benchmarks = await _get_sector_benchmarks(input_data.sector.value)

        absence = input_data.absenteeism_rate or (benchmarks or {}).get("absenteeism_rate") or 5.0
        burnout = input_data.burnout_prevalence or (benchmarks or {}).get("burnout_prevalence") or 15.0
        salary = input_data.avg_salary or (benchmarks or {}).get("avg_labour_cost_fte") or 50000

        result = CalculationEngine.absenteeism_cost(
            fte_count=input_data.fte_count,
            absenteeism_rate=float(absence),
            avg_salary=float(salary),
            burnout_prevalence=float(burnout),
        )

        mc_result = None
        if input_data.include_monte_carlo and benchmarks:
            distributions = MonteCarloEngine.default_distributions_for_sector(benchmarks)
            mc_params = {
                "fte_count": input_data.fte_count,
                "absenteeism_rate": float(absence),
                "avg_salary": float(salary),
                "burnout_prevalence": float(burnout),
            }
            mc_result = MonteCarloEngine.simulate(
                CalculationEngine.absenteeism_cost,
                mc_params,
                {k: v for k, v in distributions.items() if k in ["absenteeism_rate", "burnout_prevalence"]},
                output_key="total_annual_cost",
            )

        # Log to database
        session_id = str(uuid.uuid4())
        await execute(
            """INSERT INTO calculation_results
               (calculation_type, sector_id, input_parameters, output_results,
                user_session_id, source_context, created_at)
               VALUES ($1, $2, $3, $4, $5, $6, NOW())""",
            "absenteeism_cost",
            input_data.sector.value,
            json.dumps(input_data.model_dump()),
            json.dumps(result),
            session_id,
            "api",
        )

        breakdown_dicts = [
            {
                "component": b["category"],
                "amount": b["amount_eur"],
                "percentage": round((b["amount_eur"] / result["total_annual_cost"]) * 100, 1),
                "confidence": ConfidenceLevel.MEDIUM,
            }
            for b in result.get("breakdown", [])
        ]

        return AbsenteeismCostOutput(
            total_annual_cost=result["total_annual_cost"],
            burnout_component=result.get("burnout_component", 0),
            short_term_component=result.get("short_term_component", 0),
            long_term_component=result.get("long_term_component", 0),
            breakdown=breakdown_dicts,
            benchmark_comparison=result.get("benchmark_comparison", {}),
            monte_carlo=mc_result,
            methodology=result.get("methodology", ""),
            assumptions=result.get("assumptions", {}),
            sources=result.get("sources", []),
            confidence_level=ConfidenceLevel.MEDIUM,
        )

    except Exception as e:
        logger.error("absenteeism_cost_calculation_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cost-of-inaction", response_model=CostOfInactionOutput)
async def calculate_cost_of_inaction(
    input_data: CostOfInactionInput,
    _: str = Depends(verify_api_key),
):
    """Calculate integrated cost across all three pillars."""
    try:
        benchmarks = await _get_sector_benchmarks(input_data.sector.value)

        vacancies = input_data.open_vacancies or (benchmarks or {}).get("open_vacancies") or 10
        tr = input_data.turnover_rate or (benchmarks or {}).get("turnover_rate") or 12.0
        absence = input_data.absenteeism_rate or (benchmarks or {}).get("absenteeism_rate") or 5.0
        burnout = input_data.burnout_prevalence or (benchmarks or {}).get("burnout_prevalence") or 15.0
        salary = input_data.avg_salary or (benchmarks or {}).get("avg_labour_cost_fte") or 50000

        result = CalculationEngine.cost_of_inaction(
            sector_id=input_data.sector.value,
            fte_count=input_data.fte_count,
            open_vacancies=int(vacancies),
            turnover_rate=float(tr),
            absenteeism_rate=float(absence),
            avg_salary=float(salary),
            burnout_prevalence=float(burnout),
            projection_years=input_data.projection_years,
            include_societal=input_data.include_societal_costs,
            sector_benchmarks=benchmarks,
        )

        # Log to database
        session_id = str(uuid.uuid4())
        await execute(
            """INSERT INTO calculation_results
               (calculation_type, sector_id, input_parameters, output_results,
                user_session_id, source_context, created_at)
               VALUES ($1, $2, $3, $4, $5, $6, NOW())""",
            "cost_of_inaction",
            input_data.sector.value,
            json.dumps(input_data.model_dump()),
            json.dumps(result),
            session_id,
            "api",
        )

        breakdown_dicts = [
            {
                "component": b["category"],
                "amount": b["amount_eur"],
                "percentage": round((b["amount_eur"] / result["total_annual_cost"]) * 100, 1),
                "confidence": ConfidenceLevel.MEDIUM,
            }
            for b in result.get("breakdown", [])
        ]

        projection_dicts = [
            {
                "year": p["year"],
                "total_cost": p["total_cost"],
                "vacancy_costs": 0,  # Could be extracted if available
                "turnover_costs": 0,
                "absenteeism_costs": 0,
            }
            for p in result.get("projection", [])
        ]

        return CostOfInactionOutput(
            total_annual_cost=result["total_annual_cost"],
            vacancy_costs=result.get("vacancy_costs", 0),
            turnover_costs=result.get("turnover_costs", 0),
            absenteeism_costs=result.get("absenteeism_costs", 0),
            societal_costs=result.get("societal_costs", 0),
            breakdown=breakdown_dicts,
            projection=projection_dicts,
            benchmark_comparison=result.get("benchmark_comparison", {}),
            top_3_interventions=result.get("top_3_interventions", []),
            methodology=result.get("methodology", ""),
            assumptions=result.get("assumptions", {}),
            sources=result.get("sources", []),
            confidence_level=ConfidenceLevel.MEDIUM,
        )

    except Exception as e:
        logger.error("cost_of_inaction_calculation_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reskilling-roi")
async def calculate_reskilling_roi(
    input_data: ReskillingRoiInput,
    _: str = Depends(verify_api_key),
):
    """Calculate ROI of reskilling/upskilling investment."""
    try:
        benchmarks = await _get_sector_benchmarks(input_data.sector.value)
        salary = input_data.avg_salary or (benchmarks or {}).get("avg_labour_cost_fte") or 50000

        result = CalculationEngine.reskilling_roi(
            num_employees=input_data.num_employees,
            investment_per_person=input_data.investment_per_person,
            expected_productivity_gain_pct=input_data.expected_productivity_gain_pct,
            avg_salary=float(salary),
            time_horizon_years=input_data.time_horizon_years,
            discount_rate=input_data.discount_rate,
        )

        session_id = str(uuid.uuid4())
        await execute(
            """INSERT INTO calculation_results
               (calculation_type, sector_id, input_parameters, output_results,
                user_session_id, source_context, created_at)
               VALUES ($1, $2, $3, $4, $5, $6, NOW())""",
            "reskilling_roi", input_data.sector.value,
            json.dumps(input_data.model_dump()), json.dumps(result, default=str),
            session_id, "api",
        )

        return result

    except Exception as e:
        logger.error("reskilling_roi_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/automation-roi")
async def calculate_automation_roi(
    input_data: AutomationRoiInput,
    _: str = Depends(verify_api_key),
):
    """Calculate risk-adjusted ROI of automation investment."""
    try:
        benchmarks = await _get_sector_benchmarks(input_data.sector.value)
        salary = input_data.avg_salary or (benchmarks or {}).get("avg_labour_cost_fte") or 50000

        result = CalculationEngine.automation_roi(
            current_fte_allocated=input_data.current_fte_allocated,
            implementation_cost=input_data.implementation_cost,
            expected_fte_reduction=input_data.expected_fte_reduction,
            avg_salary=float(salary),
            time_horizon_years=input_data.time_horizon_years,
            failure_rate=input_data.failure_rate_adjustment,
        )

        session_id = str(uuid.uuid4())
        await execute(
            """INSERT INTO calculation_results
               (calculation_type, sector_id, input_parameters, output_results,
                user_session_id, source_context, created_at)
               VALUES ($1, $2, $3, $4, $5, $6, NOW())""",
            "automation_roi", input_data.sector.value,
            json.dumps(input_data.model_dump()), json.dumps(result, default=str),
            session_id, "api",
        )

        return result

    except Exception as e:
        logger.error("automation_roi_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scenario-compare")
async def calculate_scenario_compare(
    input_data: ScenarioCompareInput,
    _: str = Depends(verify_api_key),
):
    """Compare two workforce scenarios."""
    try:
        result = CalculationEngine.scenario_compare(
            scenario_a=input_data.scenario_a.model_dump(),
            scenario_b=input_data.scenario_b.model_dump(),
            time_horizon_years=input_data.time_horizon_years,
        )

        session_id = str(uuid.uuid4())
        await execute(
            """INSERT INTO calculation_results
               (calculation_type, sector_id, input_parameters, output_results,
                user_session_id, source_context, created_at)
               VALUES ($1, $2, $3, $4, $5, $6, NOW())""",
            "scenario_compare", "cross-sector",
            json.dumps(input_data.model_dump()), json.dumps(result, default=str),
            session_id, "api",
        )

        return result

    except Exception as e:
        logger.error("scenario_compare_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/benchmark-score")
async def calculate_benchmark_score(
    input_data: BenchmarkScoreInput,
    _: str = Depends(verify_api_key),
):
    """Score organisation KPIs against sector benchmarks."""
    try:
        benchmarks = await _get_sector_benchmarks(input_data.sector.value)
        if not benchmarks:
            raise HTTPException(status_code=404, detail=f"No benchmarks for sector {input_data.sector.value}")

        sector_benchmarks = {
            "turnover_rate": float(benchmarks.get("turnover_rate") or 12),
            "absenteeism_rate": float(benchmarks.get("absenteeism_rate") or 5),
            "time_to_fill_days": float(benchmarks.get("time_to_fill_days") or 60),
            "burnout_prevalence": float(benchmarks.get("burnout_prevalence") or 15),
            "cost_per_hire": float(benchmarks.get("cost_per_hire") or 4000),
        }

        result = CalculationEngine.benchmark_score(
            kpis=input_data.kpis,
            sector_benchmarks=sector_benchmarks,
        )

        session_id = str(uuid.uuid4())
        await execute(
            """INSERT INTO calculation_results
               (calculation_type, sector_id, input_parameters, output_results,
                user_session_id, source_context, created_at)
               VALUES ($1, $2, $3, $4, $5, $6, NOW())""",
            "benchmark_score", input_data.sector.value,
            json.dumps(input_data.model_dump()), json.dumps(result, default=str),
            session_id, "api",
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("benchmark_score_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
