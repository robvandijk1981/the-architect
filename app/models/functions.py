"""Pydantic models for function impact data."""

from pydantic import BaseModel, Field


class ImpactPercentages(BaseModel):
    """AI and robotisation impact percentages for a single period."""
    period: str
    robotisering_ondersteuning: float = 0
    robotisering_augmentatie: float = 0
    robotisering_vervanging: float = 0
    ai_ondersteuning: float = 0
    ai_augmentatie: float = 0
    ai_vervanging: float = 0
    kennisoverdracht: str | None = None


class TaskChange(BaseModel):
    """A single task change within a period."""
    taak: str
    type: str  # ondersteuning, augmentatie, vervanging
    technologie: str  # AI, Robot, Beide
    beschrijving: str | None = None


class CompetencyChange(BaseModel):
    """Competency changes for a single period."""
    period: str
    nieuwe_competenties: list[str] = []
    vervallen_competenties: list[str] = []
    nieuwe_technische_vaardigheden: list[str] = []
    vervallen_technische_vaardigheden: list[str] = []
    kennisoverdracht: str | None = None


class ImpactDimensions(BaseModel):
    """AIAIAI Wat Nu 9-dimension impact scores."""
    fte_impact: str | None = None
    functie_invulling: str | None = None
    werving_arbeidsmarkt: str | None = None
    competenties_scholing: str | None = None
    kennisbehoud: str | None = None
    werkbeleving_autonomie: str | None = None
    productiviteit_kwaliteit: str | None = None
    fysieke_belasting: str | None = None
    samenwerking_locatie: str | None = None


class PeriodDetail(BaseModel):
    """Full detail for a single period: impact %, tasks, competencies."""
    period: str
    impact: ImpactPercentages
    tasks: list[TaskChange] = []
    competencies: CompetencyChange | None = None


class FunctionProfile(BaseModel):
    """Complete profile for a single function."""
    id: str
    sector: str
    functiegroep: str
    functie: str
    dimensions: ImpactDimensions
    periods: list[PeriodDetail] = []


class FunctionSummary(BaseModel):
    """Summary view of a function (for list endpoints)."""
    id: str
    sector: str
    functiegroep: str
    functie: str
    dimensions: ImpactDimensions
    # Aggregated: latest period AI total impact
    ai_total_2037: float | None = None
    robot_total_2037: float | None = None


class FunctionListResponse(BaseModel):
    """Response for function listing endpoints."""
    functions: list[FunctionSummary]
    total: int
    sector: str | None = None
    period: str | None = None


class TimelineResponse(BaseModel):
    """Timeline view for a single function across all periods."""
    sector: str
    functiegroep: str
    functie: str
    dimensions: ImpactDimensions
    timeline: list[PeriodDetail]
