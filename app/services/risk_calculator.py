"""Deterministic risk matrix calculator — no AI, pure math + sector parameters."""

import structlog

from app.core.database import fetch_all
from app.models.analysis import (
    RiskCategory, RiskLevel, RiskScore, RiskMatrix, OrganizationProfile, SectorSlug,
)

logger = structlog.get_logger()

# Default thresholds when sector-specific data is not yet available
DEFAULT_THRESHOLDS = {
    RiskCategory.VERGRIJZING: {
        "gemiddelde_leeftijd": {"low": 38, "high": 48},
        "aandeel_55plus": {"low": 0.15, "high": 0.30},
    },
    RiskCategory.ARBEIDSMARKT: {
        "vacature_ratio": {"low": 0.02, "high": 0.06},
        "spanningsindicator": {"low": 1.5, "high": 3.5},
    },
    RiskCategory.AUTOMATISERING: {
        "ai_exposure_score": {"low": 0.20, "high": 0.50},
        "routinematig_werk_aandeel": {"low": 0.25, "high": 0.55},
    },
    RiskCategory.KENNISBEHOUD: {
        "kennisintensiteit": {"low": 0.30, "high": 0.60},
        "uitstroom_kritieke_functies": {"low": 0.05, "high": 0.15},
    },
    RiskCategory.VITALITEIT: {
        "verzuimpercentage": {"low": 4.0, "high": 7.0},
        "verlooppercentage": {"low": 8.0, "high": 18.0},
    },
    RiskCategory.INNOVATIE: {
        "digitale_volwassenheid": {"low": 2.0, "high": 3.5},  # 1-5 scale
        "opleidingsbudget_per_fte": {"low": 500, "high": 1500},
    },
}


class RiskCalculator:
    """Calculate the 6-risk workforce risk matrix."""

    async def calculate(
        self, profile: OrganizationProfile
    ) -> RiskMatrix:
        """
        Calculate all 6 risks for an organization.
        Uses sector-specific parameters from DB, falls back to defaults.
        """
        # Try to load sector-specific thresholds
        sector_params = await self._load_sector_params(profile.sector.value)

        risks = [
            self._calc_vergrijzing(profile, sector_params),
            self._calc_arbeidsmarkt(profile, sector_params),
            self._calc_automatisering(profile, sector_params),
            self._calc_kennisbehoud(profile, sector_params),
            self._calc_vitaliteit(profile, sector_params),
            self._calc_innovatie(profile, sector_params),
        ]

        # Overall profile based on weighted scores
        avg_score = sum(r.score for r in risks) / len(risks)
        if avg_score >= 65:
            overall = RiskLevel.HOOG
        elif avg_score >= 40:
            overall = RiskLevel.MIDDEN
        else:
            overall = RiskLevel.LAAG

        # Summary
        high_risks = [r for r in risks if r.level == RiskLevel.HOOG]
        if high_risks:
            risk_names = ", ".join(r.category.value for r in high_risks)
            summary = (
                f"De organisatie heeft {len(high_risks)} hoge risico's: {risk_names}. "
                f"Directe actie aanbevolen op deze gebieden."
            )
        else:
            summary = "De organisatie heeft geen direct hoge risico's, maar aandacht voor preventie blijft belangrijk."

        return RiskMatrix(
            risks=risks,
            overall_profile=overall,
            summary=summary,
        )

    # ============================================
    # Individual Risk Calculations
    # ============================================

    def _calc_vergrijzing(self, profile: OrganizationProfile, params: dict) -> RiskScore:
        """Calculate aging risk."""
        factors = []
        scores = []

        avg_age = profile.average_age or 42  # default assumption
        thresholds = self._get_thresholds(RiskCategory.VERGRIJZING, "gemiddelde_leeftijd", params)

        if avg_age >= thresholds["high"]:
            scores.append(80)
            factors.append(f"Gemiddelde leeftijd ({avg_age:.0f}) boven sectorgemiddelde")
        elif avg_age >= thresholds["low"]:
            scores.append(50)
            factors.append(f"Gemiddelde leeftijd ({avg_age:.0f}) rond sectorgemiddelde")
        else:
            scores.append(20)
            factors.append(f"Gemiddelde leeftijd ({avg_age:.0f}) onder sectorgemiddelde")

        # Additional factor from extracted data
        pct_55plus = profile.extracted_data.get("aandeel_55plus")
        if pct_55plus is not None:
            t55 = self._get_thresholds(RiskCategory.VERGRIJZING, "aandeel_55plus", params)
            if pct_55plus >= t55["high"]:
                scores.append(85)
                factors.append(f"Hoog aandeel 55+ medewerkers ({pct_55plus:.0%})")
            elif pct_55plus >= t55["low"]:
                scores.append(50)
                factors.append(f"Gemiddeld aandeel 55+ medewerkers ({pct_55plus:.0%})")
            else:
                scores.append(20)

        score = sum(scores) / len(scores) if scores else 50
        level = self._score_to_level(score)

        return RiskScore(
            category=RiskCategory.VERGRIJZING,
            level=level,
            score=score,
            factors=factors or ["Onvoldoende data voor gedetailleerde analyse"],
            recommended_actions=self._vergrijzing_actions(level),
        )

    def _calc_arbeidsmarkt(self, profile: OrganizationProfile, params: dict) -> RiskScore:
        factors = []
        scores = []

        # Use sector knowledge
        sector_data = profile.extracted_data.get("arbeidsmarktkrapte")
        if sector_data:
            krapte = sector_data if isinstance(sector_data, (int, float)) else 50
            scores.append(krapte)
            factors.append(f"Arbeidsmarktkrapte in sector: {'hoog' if krapte > 60 else 'gemiddeld' if krapte > 35 else 'laag'}")
        else:
            scores.append(50)  # neutral assumption
            factors.append("Arbeidsmarktkrapte: sectorgemiddelde aangenomen (onvoldoende data)")

        score = sum(scores) / len(scores) if scores else 50
        level = self._score_to_level(score)

        return RiskScore(
            category=RiskCategory.ARBEIDSMARKT,
            level=level,
            score=score,
            factors=factors,
            recommended_actions=self._arbeidsmarkt_actions(level),
        )

    def _calc_automatisering(self, profile: OrganizationProfile, params: dict) -> RiskScore:
        factors = []
        scores = []

        ai_exposure = profile.extracted_data.get("ai_exposure_score")
        if ai_exposure is not None:
            t = self._get_thresholds(RiskCategory.AUTOMATISERING, "ai_exposure_score", params)
            if ai_exposure >= t["high"]:
                scores.append(80)
                factors.append(f"Hoge AI-exposure ({ai_exposure:.0%} van taken automatiseerbaar)")
            elif ai_exposure >= t["low"]:
                scores.append(50)
                factors.append(f"Gemiddelde AI-exposure ({ai_exposure:.0%})")
            else:
                scores.append(25)
                factors.append(f"Lage AI-exposure ({ai_exposure:.0%})")
        else:
            scores.append(45)
            factors.append("AI-exposure: sectorgemiddelde aangenomen")

        score = sum(scores) / len(scores) if scores else 45
        level = self._score_to_level(score)

        return RiskScore(
            category=RiskCategory.AUTOMATISERING,
            level=level,
            score=score,
            factors=factors,
            recommended_actions=self._automatisering_actions(level),
        )

    def _calc_kennisbehoud(self, profile: OrganizationProfile, params: dict) -> RiskScore:
        factors = []
        scores = []

        # Cross-reference vergrijzing with turnover for knowledge risk
        avg_age = profile.average_age or 42
        turnover = profile.turnover_rate or 12

        if avg_age > 45 and turnover > 12:
            scores.append(80)
            factors.append("Combinatie van hoge leeftijd én hoog verloop vergroot kennisrisico")
        elif avg_age > 45 or turnover > 15:
            scores.append(55)
            factors.append("Leeftijdsopbouw of verloop vormt risico voor kennisbehoud")
        else:
            scores.append(30)
            factors.append("Kennisbehoud lijkt beheersbaar")

        score = sum(scores) / len(scores) if scores else 50
        level = self._score_to_level(score)

        return RiskScore(
            category=RiskCategory.KENNISBEHOUD,
            level=level,
            score=score,
            factors=factors,
            recommended_actions=self._kennisbehoud_actions(level),
        )

    def _calc_vitaliteit(self, profile: OrganizationProfile, params: dict) -> RiskScore:
        factors = []
        scores = []

        absence = profile.absence_rate
        if absence is not None:
            t = self._get_thresholds(RiskCategory.VITALITEIT, "verzuimpercentage", params)
            if absence >= t["high"]:
                scores.append(85)
                factors.append(f"Verzuimpercentage ({absence:.1f}%) boven sectorgemiddelde")
            elif absence >= t["low"]:
                scores.append(50)
                factors.append(f"Verzuimpercentage ({absence:.1f}%) rond sectorgemiddelde")
            else:
                scores.append(20)
                factors.append(f"Verzuimpercentage ({absence:.1f}%) onder sectorgemiddelde")
        else:
            scores.append(50)
            factors.append("Verzuimpercentage: niet opgegeven, sectorgemiddelde aangenomen")

        turnover = profile.turnover_rate
        if turnover is not None:
            t = self._get_thresholds(RiskCategory.VITALITEIT, "verlooppercentage", params)
            if turnover >= t["high"]:
                scores.append(80)
                factors.append(f"Verlooppercentage ({turnover:.1f}%) boven sectorgemiddelde")
            elif turnover >= t["low"]:
                scores.append(45)
                factors.append(f"Verlooppercentage ({turnover:.1f}%) rond sectorgemiddelde")
            else:
                scores.append(15)
                factors.append(f"Verlooppercentage ({turnover:.1f}%) onder sectorgemiddelde")

        score = sum(scores) / len(scores) if scores else 50
        level = self._score_to_level(score)

        return RiskScore(
            category=RiskCategory.VITALITEIT,
            level=level,
            score=score,
            factors=factors,
            recommended_actions=self._vitaliteit_actions(level),
        )

    def _calc_innovatie(self, profile: OrganizationProfile, params: dict) -> RiskScore:
        factors = []
        scores = []

        digital_maturity = profile.extracted_data.get("digitale_volwassenheid")
        if digital_maturity is not None:
            t = self._get_thresholds(RiskCategory.INNOVATIE, "digitale_volwassenheid", params)
            if digital_maturity <= t["low"]:
                scores.append(80)
                factors.append(f"Lage digitale volwassenheid (score {digital_maturity:.1f}/5)")
            elif digital_maturity <= t["high"]:
                scores.append(45)
                factors.append(f"Gemiddelde digitale volwassenheid (score {digital_maturity:.1f}/5)")
            else:
                scores.append(15)
                factors.append(f"Hoge digitale volwassenheid (score {digital_maturity:.1f}/5)")
        else:
            scores.append(50)
            factors.append("Digitale volwassenheid: niet gemeten")

        score = sum(scores) / len(scores) if scores else 50
        level = self._score_to_level(score)

        return RiskScore(
            category=RiskCategory.INNOVATIE,
            level=level,
            score=score,
            factors=factors,
            recommended_actions=self._innovatie_actions(level),
        )

    # ============================================
    # Action Recommendations (per risk level)
    # ============================================

    @staticmethod
    def _vergrijzing_actions(level: RiskLevel) -> list[str]:
        if level == RiskLevel.HOOG:
            return [
                "Start nu met kennisoverdracht-programma's voor kritieke functies",
                "Ontwikkel een strategisch wervingsplan gericht op jongere doelgroepen",
                "Implementeer gefaseerde pensioenplanning met duo-banen",
            ]
        elif level == RiskLevel.MIDDEN:
            return [
                "Monitor leeftijdsopbouw per afdeling/functiegroep",
                "Start met opvolgerplanning voor sleutelfuncties",
            ]
        return ["Onderhoud huidige leeftijdsspreiding", "Blijf investeren in medewerkersontwikkeling"]

    @staticmethod
    def _arbeidsmarkt_actions(level: RiskLevel) -> list[str]:
        if level == RiskLevel.HOOG:
            return [
                "Versterk employer branding en arbeidsmarktpositionering",
                "Diversifieer wervingskanalen (internationaal, zij-instromers)",
                "Investeer in retentie: verloop voorkomen is goedkoper dan werving",
            ]
        elif level == RiskLevel.MIDDEN:
            return [
                "Analyseer welke functies het moeilijkst vervulbaar zijn",
                "Verken samenwerkingen met opleidingsinstituten",
            ]
        return ["Behoud goede relatie met wervingspartners", "Monitor arbeidsmarkttrends"]

    @staticmethod
    def _automatisering_actions(level: RiskLevel) -> list[str]:
        if level == RiskLevel.HOOG:
            return [
                "Breng taak-level AI-impact in kaart per functiegroep",
                "Start reskilling programma's voor meest geraakte functies",
                "Ontwikkel een AI-adoptie roadmap met change management",
            ]
        elif level == RiskLevel.MIDDEN:
            return [
                "Experimenteer met AI-pilots in ondersteunende processen",
                "Inventariseer welke taken het eerst geautomatiseerd kunnen worden",
            ]
        return ["Volg AI-ontwikkelingen in de sector", "Investeer in digitale vaardigheden"]

    @staticmethod
    def _kennisbehoud_actions(level: RiskLevel) -> list[str]:
        if level == RiskLevel.HOOG:
            return [
                "Identificeer en documenteer kritieke kennis bij vertrekkende medewerkers",
                "Implementeer mentoring- en buddy-systemen",
                "Creëer kennisbanken en standaardprocessen voor cruciale werkzaamheden",
            ]
        elif level == RiskLevel.MIDDEN:
            return [
                "Start met kennismanagement voor top-10 sleutelfuncties",
                "Organiseer cross-training tussen afdelingen",
            ]
        return ["Onderhoud documentatie van kernprocessen", "Stimuleer kennisdeling"]

    @staticmethod
    def _vitaliteit_actions(level: RiskLevel) -> list[str]:
        if level == RiskLevel.HOOG:
            return [
                "Analyseer verzuimoorzaken per afdeling en functiegroep",
                "Investeer in preventieve gezondheidsinterventies",
                "Voer exit-interviews uit om structurele verloopoorzaken te achterhalen",
            ]
        elif level == RiskLevel.MIDDEN:
            return [
                "Monitor verzuimtrends en signaleer vroeg",
                "Versterk leiderschapskwaliteit (grootste verzuimfactor)",
            ]
        return ["Blijf investeren in werkgeluk en werkomgeving", "Monitor medewerkerstevredenheid"]

    @staticmethod
    def _innovatie_actions(level: RiskLevel) -> list[str]:
        if level == RiskLevel.HOOG:
            return [
                "Investeer in digitale vaardigheden op alle niveaus",
                "Start innovatiepilots met duidelijke KPI's en terugkoppeling",
                "Creëer een cultuur van experimenteren en leren",
            ]
        elif level == RiskLevel.MIDDEN:
            return [
                "Versteek digitale geletterdheid bij middenmanagement",
                "Benchmark innovatieaanpak met koplopers in de sector",
            ]
        return ["Onderhoud huidige innovatiecapaciteit", "Volg technologische ontwikkelingen"]

    # ============================================
    # Helpers
    # ============================================

    async def _load_sector_params(self, sector_slug: str) -> dict:
        """Load sector-specific risk parameters from database."""
        try:
            rows = await fetch_all(
                "SELECT * FROM get_risk_parameters($1)", sector_slug
            )
            params = {}
            for row in rows:
                cat = row["risk_category"]
                name = row["parameter_name"]
                if cat not in params:
                    params[cat] = {}
                params[cat][name] = {
                    "value": row["parameter_value"],
                    "low": row["threshold_low"],
                    "high": row["threshold_high"],
                    "weight": row["weight"],
                }
            return params
        except Exception as e:
            logger.warning("sector_params_load_failed", sector=sector_slug, error=str(e))
            return {}

    def _get_thresholds(self, category: RiskCategory, param_name: str, params: dict) -> dict:
        """Get thresholds from DB params, fall back to defaults."""
        cat_key = category.value
        if cat_key in params and param_name in params[cat_key]:
            p = params[cat_key][param_name]
            return {"low": p["low"], "high": p["high"]}
        # Fall back to defaults
        defaults = DEFAULT_THRESHOLDS.get(category, {}).get(param_name, {})
        return {"low": defaults.get("low", 35), "high": defaults.get("high", 65)}

    @staticmethod
    def _score_to_level(score: float) -> RiskLevel:
        if score >= 65:
            return RiskLevel.HOOG
        elif score >= 35:
            return RiskLevel.MIDDEN
        return RiskLevel.LAAG
