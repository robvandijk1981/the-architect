"""
Pydantic models for calculation API request/response validation.
All calculation inputs, outputs, and database schemas.
"""

from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime

# Re-export the canonical SectorSlug from analysis.py as SectorEnum so all
# /calculate/* and /ai/* endpoints share the same 9-sector taxonomy as
# /chat, /analyze, /benchmark. Existing code that imports SectorEnum from
# this module continues to work unchanged.
from app.models.analysis import SectorSlug as SectorEnum


class ConfidenceLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ============ VACANCY COST ============

class VacancyCostInput(BaseModel):
    sector: SectorEnum
    open_vacancies: int = Field(..., ge=0, description="Number of open positions")
    time_to_fill_days: Optional[float] = Field(None, ge=0)
    cost_per_hire: Optional[float] = Field(None, ge=0)
    include_monte_carlo: bool = False


class CostBreakdown(BaseModel):
    component: str = Field(...)
    amount: float = Field(..., ge=0)
    percentage: float = Field(..., ge=0, le=100)
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM


class VacancyCostOutput(BaseModel):
    total_annual_cost: float
    cost_per_vacancy: float
    breakdown: List[CostBreakdown]
    benchmark_comparison: Dict[str, Any]
    monte_carlo: Optional[Dict[str, Any]] = None
    methodology: str
    assumptions: Any  # list[str] from engine, dict from API overrides
    sources: List[str]
    confidence_level: ConfidenceLevel


# ============ TURNOVER COST ============

class TurnoverCostInput(BaseModel):
    sector: SectorEnum
    fte_count: int = Field(..., ge=1)
    turnover_rate: Optional[float] = Field(None, ge=0, le=100)
    avg_salary: Optional[float] = Field(None, ge=0)
    include_monte_carlo: bool = False


class TurnoverCostOutput(BaseModel):
    total_annual_cost: float
    cost_per_exit: float
    estimated_exits_per_year: float
    breakdown: List[CostBreakdown]
    benchmark_comparison: Dict[str, Any]
    monte_carlo: Optional[Dict[str, Any]] = None
    methodology: str
    assumptions: Any  # list[str] from engine, dict from API overrides
    sources: List[str]
    confidence_level: ConfidenceLevel


# ============ ABSENTEEISM COST ============

class AbsenteeismCostInput(BaseModel):
    sector: SectorEnum
    fte_count: int = Field(..., ge=1)
    absenteeism_rate: Optional[float] = Field(None, ge=0)
    avg_salary: Optional[float] = Field(None, ge=0)
    burnout_prevalence: Optional[float] = Field(None, ge=0, le=100)
    include_monte_carlo: bool = False


class AbsenteeismCostOutput(BaseModel):
    total_annual_cost: float
    burnout_component: float
    short_term_component: float
    long_term_component: float
    breakdown: List[CostBreakdown]
    benchmark_comparison: Dict[str, Any]
    monte_carlo: Optional[Dict[str, Any]] = None
    methodology: str
    assumptions: Any  # list[str] from engine, dict from API overrides
    sources: List[str]
    confidence_level: ConfidenceLevel


# ============ COST OF INACTION ============

class ProjectionYear(BaseModel):
    year: int
    total_cost: float
    vacancy_costs: float
    turnover_costs: float
    absenteeism_costs: float


class CostOfInactionInput(BaseModel):
    sector: SectorEnum
    fte_count: int = Field(..., ge=1)
    open_vacancies: Optional[int] = Field(None, ge=0)
    turnover_rate: Optional[float] = Field(None, ge=0, le=100)
    absenteeism_rate: Optional[float] = Field(None, ge=0)
    avg_salary: Optional[float] = Field(None, ge=0)
    burnout_prevalence: Optional[float] = Field(None, ge=0, le=100)
    projection_years: int = Field(3, ge=1, le=10)
    include_societal_costs: bool = False
    include_monte_carlo: bool = False


class CostOfInactionOutput(BaseModel):
    total_annual_cost: float
    vacancy_costs: float
    turnover_costs: float
    absenteeism_costs: float
    societal_costs: float
    breakdown: List[CostBreakdown]
    projection: List[ProjectionYear]
    monte_carlo: Optional[Dict[str, Any]] = None
    benchmark_comparison: Dict[str, Any]
    top_3_interventions: List[Dict[str, Any]]
    methodology: str
    assumptions: Any  # list[str] from engine, dict from API overrides
    sources: List[str]
    confidence_level: ConfidenceLevel


# ============ RESKILLING ROI ============

class ReskillingRoiInput(BaseModel):
    sector: SectorEnum
    num_employees: int = Field(..., ge=1)
    investment_per_person: float = Field(..., ge=0)
    expected_productivity_gain_pct: float = Field(..., ge=0, le=100)
    avg_salary: Optional[float] = Field(None, ge=0)
    time_horizon_years: int = Field(3, ge=1, le=10)
    discount_rate: float = Field(0.08, ge=0, le=0.25)


class ReskillingRoiOutput(BaseModel):
    total_investment: float
    annual_productivity_gain: float
    net_present_value: float
    roi_percentage: float
    payback_period_years: float
    breakeven_year: int
    methodology: str
    assumptions: Any  # list[str] from engine, dict from API overrides
    confidence_level: ConfidenceLevel


# ============ AUTOMATION ROI ============

class AutomationRoiInput(BaseModel):
    sector: SectorEnum
    current_fte_allocated: float = Field(..., ge=0)
    implementation_cost: float = Field(..., ge=0)
    expected_fte_reduction: float = Field(..., ge=0)
    avg_salary: Optional[float] = Field(None, ge=0)
    time_horizon_years: int = Field(3, ge=1, le=10)
    failure_rate_adjustment: float = Field(1.0, ge=0.5, le=2.0)


class AutomationRoiOutput(BaseModel):
    total_implementation_cost: float
    annual_salary_savings: float
    annual_maintenance_cost: float
    net_annual_benefit: float
    roi_percentage: float
    payback_period_years: float
    methodology: str
    assumptions: Any  # list[str] from engine, dict from API overrides
    confidence_level: ConfidenceLevel


# ============ SCENARIO COMPARISON ============

class ScenarioInput(BaseModel):
    name: str
    fte_count: int
    open_vacancies: int
    turnover_rate: float
    absenteeism_rate: float
    avg_salary: float


class ScenarioCompareInput(BaseModel):
    scenario_a: ScenarioInput
    scenario_b: ScenarioInput
    time_horizon_years: int = Field(3, ge=1, le=10)


class ScenarioCompareOutput(BaseModel):
    scenario_a_cost: float
    scenario_b_cost: float
    cost_difference: float
    recommendation: str
    methodology: str


# ============ BENCHMARK SCORING ============

class KpiScore(BaseModel):
    kpi_name: str
    your_value: float
    sector_benchmark: float
    percentile: float
    rating: str
    interpretation: str


class BenchmarkScoreInput(BaseModel):
    sector: SectorEnum
    organisation_name: str
    kpis: Dict[str, float]


class BenchmarkScoreOutput(BaseModel):
    organisation_name: str
    sector: str
    overall_maturity_score: float
    kpi_scores: List[KpiScore]
    top_3_opportunities: List[str]
    methodology: str
    sources: List[str]
    confidence_level: ConfidenceLevel


# ============ MONTE CARLO RESULT ============

class MonteCarloResult(BaseModel):
    mean_estimate: float
    std_deviation: float
    percentile_5: float
    percentile_25: float
    percentile_50: float
    percentile_75: float
    percentile_95: float
    iterations: int


# ============ REPORT GENERATION ============

class ReportRequest(BaseModel):
    calculation_type: str
    calculation_id: str
    output_format: str = "pdf"
    include_monte_carlo: bool = False


# ============ ADMIN / BENCHMARK DATA ============

class SectorBenchmarkCreate(BaseModel):
    sector: str
    subsector: Optional[str] = None
    year: int
    time_to_fill_days: Optional[float] = None
    cost_per_hire: Optional[float] = None
    turnover_rate: Optional[float] = None
    absenteeism_rate: Optional[float] = None
    burnout_prevalence: Optional[float] = None
    avg_labour_cost_fte: Optional[float] = None
    cost_per_sick_day: Optional[float] = None
    long_term_absence_pct: Optional[float] = None
    burnout_cost_per_case: Optional[float] = None
    open_vacancies: Optional[int] = None
    data_source: Optional[str] = None
    confidence: Optional[str] = None


class CalculationResult(BaseModel):
    id: str
    calculation_type: str
    sector: str
    created_at: datetime
    input_data: Dict[str, Any]
    output_data: Dict[str, Any]
    methodology: str
    confidence_level: str
    session_id: str
    source: str


# ============ AI INTERPRETATION & FEEDBACK ============

class InterpretRequest(BaseModel):
    calculation_type: str = Field(...)
    results: Dict[str, Any] = Field(...)
    sector: str = Field(...)
    confidence_level: Optional[str] = Field("medium")


class InterpretResponse(BaseModel):
    executive_summary: str
    key_findings: List[str]
    recommendations: List[str]
    risk_flags: List[str]
    confidence_assessment: str
    generated_at: str


class NarrativeRequest(BaseModel):
    results: Dict[str, Any] = Field(...)
    audience: str = Field("chro")


class NarrativeResponse(BaseModel):
    narrative: str
    audience: str
    generated_at: str


class WorkforceGapRequest(BaseModel):
    sector: str
    current_fte: int = Field(..., ge=1)
    growth_rate: float = Field(..., ge=0, le=100)
    retirement_rate: float = Field(..., ge=0, le=100)
    attrition_rate: float = Field(12.0, ge=0, le=100)
    years: int = Field(5, ge=1, le=20)


class GapProjectionYear(BaseModel):
    year: int
    fte_demand: int
    fte_available: int
    gap: int
    gap_type: str


class WorkforceGapResponse(BaseModel):
    sector: str
    current_fte: int
    assumptions: Any  # list[str] from engine, dict from API overrides
    projection: List[GapProjectionYear]
    total_gap_person_years: int
    max_gap_single_year: int
    peak_gap_year: int
    recruitment_needed: int
    retention_critical: bool
    recommendations: List[str]


class CostTrajectoryRequest(BaseModel):
    sector: str
    current_costs: Dict[str, float] = Field(...)
    escalation_factor: float = Field(1.08, ge=1.01, le=1.20)
    years: int = Field(5, ge=1, le=10)


class CostTrajectoryYear(BaseModel):
    year: int
    total: float
    breakdown: Dict[str, float]
    increase_from_current_pct: float


class CostTrajectoryResponse(BaseModel):
    sector: str
    current_total: float
    assumptions: Any  # list[str] from engine, dict from API overrides
    projection: List[CostTrajectoryYear]
    total_cost_5yr: float
    total_cost_5yr_vs_today: float
    cagr_pct: float
    cost_control_priority: str
    recommendations: List[str]


class InterventionPriorityItem(BaseModel):
    rank: int
    intervention: str
    target_kpi: str
    current_score: float
    benchmark_score: float
    gap: float
    potential_impact_eur: float
    effort_level: str
    roi_months: float
    rationale: str


class InterventionPriorityResponse(BaseModel):
    interventions: List[InterventionPriorityItem]
    top_recommendation: str


class BudgetAllocationItem(BaseModel):
    rank: int
    intervention: str
    budget: float
    expected_benefit: float
    roi_months: float
    timeline_months: int


class ScenarioOptimizerResponse(BaseModel):
    sector: str
    budget_available: float
    budget_allocated: float
    budget_remaining: float
    allocations: List[BudgetAllocationItem]
    total_expected_benefit: float
    overall_roi_months: float
    implementation_count: int
    recommendations: List[str]


class FeedbackRequest(BaseModel):
    session_id: str
    calculation_type: str
    sector: str
    input_data: Dict[str, Any]
    output_data: Dict[str, Any]
    user_feedback: Optional[str] = None
    validation_status: str = Field("pending")


class FeedbackResponse(BaseModel):
    interaction_id: str
    status: str
    message: str
    anomaly_detected: bool
    benchmark_update_status: Optional[str] = None


class AnomalyItem(BaseModel):
    kpi: str
    value: float
    benchmark_mean: float
    z_score: float
    severity: str
    message: str


class AnomalyDetectionResponse(BaseModel):
    has_anomalies: bool
    anomaly_count: int
    anomalies: List[AnomalyItem]
    action: str


class TrendDataPoint(BaseModel):
    month: str
    value: float


class TrendResponse(BaseModel):
    kpi: str
    sector: str
    data_points: List[TrendDataPoint]
    trend: str
    trend_strength: Optional[float] = None
    n_observations: Optional[int] = None
    mean: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
