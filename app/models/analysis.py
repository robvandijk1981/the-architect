"""Pydantic models for analysis requests and responses."""

from pydantic import BaseModel, Field
from datetime import date
from enum import Enum


# ============================================
# Intake & Organization
# ============================================

class SectorSlug(str, Enum):
    ZORG = "zorg"
    BOUW = "bouw"
    TECHNIEK = "techniek"
    ONDERWIJS = "onderwijs"
    OVERHEID = "overheid"
    FINANCIEEL = "financieel"
    RETAIL = "retail"
    TRANSPORT = "transport"


class IntakeData(BaseModel):
    """Intake questionnaire answers."""

    organization_name: str
    sector: SectorSlug
    employee_count: int = Field(ge=1)
    average_age: float | None = None
    turnover_rate: float | None = None  # percentage
    absence_rate: float | None = None  # percentage
    annual_report_extracted: dict | None = None  # from document extraction
    additional_answers: dict = Field(default_factory=dict)  # adaptive intake answers


class OrganizationProfile(BaseModel):
    """Aggregated organization profile for analysis."""

    name: str
    sector: SectorSlug
    employee_count: int
    average_age: float | None = None
    turnover_rate: float | None = None
    absence_rate: float | None = None
    revenue: float | None = None  # EUR
    fte_count: float | None = None
    function_groups: list[dict] | None = None
    strategic_priorities: list[str] | None = None
    extracted_data: dict = Field(default_factory=dict)


# ============================================
# Risk Matrix
# ============================================

class RiskLevel(str, Enum):
    LAAG = "laag"
    MIDDEN = "midden"
    HOOG = "hoog"


class RiskCategory(str, Enum):
    VERGRIJZING = "vergrijzing"
    ARBEIDSMARKT = "arbeidsmarktafhankelijkheid"
    AUTOMATISERING = "automatisering"
    KENNISBEHOUD = "kennisbehoud"
    VITALITEIT = "vitaliteit"
    INNOVATIE = "innovatie_adoptie"


class RiskScore(BaseModel):
    """Single risk assessment."""

    category: RiskCategory
    level: RiskLevel
    score: float = Field(ge=0, le=100)
    factors: list[str]  # what drives this risk
    benchmark_comparison: str | None = None  # vs sector average
    recommended_actions: list[str]


class RiskMatrix(BaseModel):
    """Complete 6-risk assessment."""

    risks: list[RiskScore] = Field(min_length=6, max_length=6)
    overall_profile: RiskLevel
    summary: str
    sources: list[dict] = Field(default_factory=list)


# ============================================
# Business Case
# ============================================

class BCCategory(str, Enum):
    ARBEIDSTEKORTEN = "arbeidstekorten"
    VERLOOP = "verloop"
    VERZUIM = "verzuim"
    AUTOMATISERING = "automatisering"
    KENNISBEHOUD = "kennisbehoud"


class BCLine(BaseModel):
    """Single business case line item."""

    category: BCCategory
    description: str
    current_cost_annual: float  # EUR per year
    potential_saving_annual: float  # EUR per year
    saving_5yr: float  # EUR over 5 years
    assumptions: list[str]
    parameters_used: dict = Field(default_factory=dict)


class ExpertOverrides(BaseModel):
    """Expert mode parameter overrides for live recalculation."""

    overrides: dict[str, float] = Field(default_factory=dict)
    # e.g. {"kosten_per_vacature": 15000, "verzuimpercentage": 6.5}


class BusinessCase(BaseModel):
    """Complete 5-category business case."""

    lines: list[BCLine]
    total_current_cost: float
    total_potential_saving_annual: float
    total_saving_5yr: float
    roi_percentage: float
    payback_months: int
    summary: str
    executive_summary: str  # 3-line version for dashboard
    sources: list[dict] = Field(default_factory=list)


# ============================================
# Full Analysis Response
# ============================================

class AnalysisStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AnalysisRequest(BaseModel):
    """
    Request to start a full analysis.

    `sector` is optional — if omitted, falls back to
    `organization_profile.sector`. Provide it only to override the
    profile's sector (rare: when analyzing a multi-sector org from a
    specific sector's perspective).
    """

    organization_profile: OrganizationProfile
    sector: SectorSlug | None = None
    documents: list[str] | None = None  # file references


class AnalysisResponse(BaseModel):
    """Full analysis result."""

    analysis_id: str
    status: AnalysisStatus
    risk_matrix: RiskMatrix | None = None
    business_case: BusinessCase | None = None
    workforce_health_score: float | None = None  # 0-100
    benchmark_comparison: dict | None = None
    arbeidsmarkt_analyse: dict | None = None
    ai_impact_analyse: dict | None = None
    skills_gap_analyse: dict | None = None
    verloop_verzuim_diagnose: dict | None = None
    actieplan: dict | None = None
    sources: list[dict] = Field(default_factory=list)
    processing_time_ms: int | None = None


class ChatRequest(BaseModel):
    """Chat with the workforce specialist."""

    message: str
    context: dict = Field(default_factory=dict)
    # context can include: sector, organization_id, analysis_id


class ChatResponse(BaseModel):
    """Chat response with sources."""

    response: str
    sources: list[dict] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)
