"""Deterministic business case calculator — pure math with sector parameters."""

import structlog

from app.core.database import fetch_all
from app.models.analysis import (
    BCCategory, BCLine, BusinessCase, ExpertOverrides, OrganizationProfile,
)

logger = structlog.get_logger()

# Default cost parameters when sector-specific data is not yet loaded
DEFAULT_COST_PARAMS = {
    "arbeidstekorten": {
        "kosten_per_vacature": 8000,             # EUR — gemiddeld NL
        "gemiddelde_doorlooptijd_vacature": 90,    # dagen
        "productiviteitsverlies_per_dag": 200,     # EUR per dag per openstaande vacature
    },
    "verloop": {
        "kosten_per_vertrek": 15000,              # EUR — werving + inwerk + productiviteitsverlies
        "inwerkperiode_maanden": 6,
        "productiviteit_nieuwe_medewerker": 0.65,  # eerste 6 maanden
    },
    "verzuim": {
        "verzuimkosten_per_dag": 350,             # EUR per dag per medewerker
        "gemiddeld_verzuimpercentage_sector": 5.5, # %
        "preventiekosten_per_fte": 250,           # EUR per jaar
        "preventie_effectiviteit": 0.20,          # 20% reductie haalbaar
    },
    "automatisering": {
        "gemiddeld_uurloon": 38,                  # EUR
        "uren_per_fte_per_jaar": 1720,
        "automatiseerbaar_aandeel": 0.15,         # 15% van taken
        "implementatiekosten_per_fte": 2000,      # EUR eenmalig
    },
    "kennisbehoud": {
        "kosten_kennisverlies_per_vertrek": 25000, # EUR — inclusief productiviteitsverlies
        "aandeel_kritieke_functies": 0.15,         # 15% van personeel
        "kennisborgingskosten_per_fte": 500,       # EUR per jaar
    },
}


class BusinessCaseCalculator:
    """Calculate the 5-category financial business case."""

    async def calculate(
        self,
        profile: OrganizationProfile,
        overrides: ExpertOverrides | None = None,
    ) -> BusinessCase:
        """
        Calculate full business case.
        Uses sector-specific parameters from DB, with optional expert overrides.
        """
        # Load sector parameters
        params = await self._load_sector_params(profile.sector.value)

        # Apply expert overrides
        if overrides:
            params = self._apply_overrides(params, overrides)

        n = profile.employee_count
        lines = [
            self._calc_arbeidstekorten(profile, params, n),
            self._calc_verloop(profile, params, n),
            self._calc_verzuim(profile, params, n),
            self._calc_automatisering(profile, params, n),
            self._calc_kennisbehoud(profile, params, n),
        ]

        total_cost = sum(l.current_cost_annual for l in lines)
        total_saving = sum(l.potential_saving_annual for l in lines)
        total_5yr = sum(l.saving_5yr for l in lines)

        roi = (total_saving / max(total_cost * 0.1, 1)) * 100  # ROI on 10% investment
        payback = int(12 / max(roi / 100, 0.01))  # months

        # Executive summary (3-line version)
        top_2 = sorted(lines, key=lambda l: l.saving_5yr, reverse=True)[:2]
        exec_summary = (
            f"Uw organisatie laat jaarlijks circa €{total_saving:,.0f} liggen aan workforce-gerelateerde kosten. "
            f"De grootste besparingsmogelijkheden liggen bij {top_2[0].category.value} "
            f"(€{top_2[0].potential_saving_annual:,.0f}/jaar) en {top_2[1].category.value} "
            f"(€{top_2[1].potential_saving_annual:,.0f}/jaar). "
            f"Over 5 jaar is de totale besparingspotentie €{total_5yr:,.0f}."
        )

        summary = (
            f"Business case voor {profile.name} ({n} medewerkers, sector {profile.sector.value}). "
            f"Totale jaarlijkse workforce-kosten: €{total_cost:,.0f}. "
            f"Besparingspotentie: €{total_saving:,.0f}/jaar (€{total_5yr:,.0f} over 5 jaar). "
            f"Geschatte ROI: {roi:.0f}%, terugverdientijd: {payback} maanden."
        )

        return BusinessCase(
            lines=lines,
            total_current_cost=total_cost,
            total_potential_saving_annual=total_saving,
            total_saving_5yr=total_5yr,
            roi_percentage=roi,
            payback_months=payback,
            summary=summary,
            executive_summary=exec_summary,
        )

    # ============================================
    # Category Calculations
    # ============================================

    def _calc_arbeidstekorten(self, profile: OrganizationProfile, params: dict, n: int) -> BCLine:
        p = params.get("arbeidstekorten", DEFAULT_COST_PARAMS["arbeidstekorten"])
        kosten_per_vacature = p.get("kosten_per_vacature", 8000)
        doorlooptijd = p.get("gemiddelde_doorlooptijd_vacature", 90)
        prod_verlies = p.get("productiviteitsverlies_per_dag", 200)

        # Estimate: ~8% vacature-ratio typical, varies by sector
        vacature_ratio = profile.extracted_data.get("vacature_ratio", 0.08)
        openstaande_vacatures = int(n * vacature_ratio)

        # Direct costs: werving
        wervingskosten = openstaande_vacatures * kosten_per_vacature
        # Indirect: productiviteitsverlies during vacancy
        productiviteitsverlies = openstaande_vacatures * doorlooptijd * prod_verlies / 365

        current_cost = wervingskosten + productiviteitsverlies
        # With better SPP: 30% shorter doorlooptijd + 20% fewer vacatures
        saving = current_cost * 0.25

        return BCLine(
            category=BCCategory.ARBEIDSTEKORTEN,
            description="Kosten gerelateerd aan openstaande vacatures en wervingsuitgaven",
            current_cost_annual=current_cost,
            potential_saving_annual=saving,
            saving_5yr=saving * 5,
            assumptions=[
                f"Vacatureratio: {vacature_ratio:.0%} ({openstaande_vacatures} vacatures)",
                f"Kosten per vacature: €{kosten_per_vacature:,.0f}",
                f"Gemiddelde doorlooptijd: {doorlooptijd} dagen",
                "Besparing door betere SPP: ~25% reductie in wervingskosten",
            ],
            parameters_used=p,
        )

    def _calc_verloop(self, profile: OrganizationProfile, params: dict, n: int) -> BCLine:
        p = params.get("verloop", DEFAULT_COST_PARAMS["verloop"])
        kosten_per_vertrek = p.get("kosten_per_vertrek", 15000)

        verloop = profile.turnover_rate or 12.0  # %
        vertrekkers = int(n * verloop / 100)

        current_cost = vertrekkers * kosten_per_vertrek
        # With better retention: 20% less unwanted turnover
        saving = current_cost * 0.20

        return BCLine(
            category=BCCategory.VERLOOP,
            description="Kosten van personeelsverloop: werving, inwerkperiode en productiviteitsverlies",
            current_cost_annual=current_cost,
            potential_saving_annual=saving,
            saving_5yr=saving * 5,
            assumptions=[
                f"Verlooppercentage: {verloop:.1f}% ({vertrekkers} vertrekkers/jaar)",
                f"Kosten per vertrek: €{kosten_per_vertrek:,.0f}",
                "Reductie door gerichte retentie-interventies: ~20%",
            ],
            parameters_used=p,
        )

    def _calc_verzuim(self, profile: OrganizationProfile, params: dict, n: int) -> BCLine:
        p = params.get("verzuim", DEFAULT_COST_PARAMS["verzuim"])
        kosten_per_dag = p.get("verzuimkosten_per_dag", 350)
        preventie_effect = p.get("preventie_effectiviteit", 0.20)

        verzuim = profile.absence_rate or p.get("gemiddeld_verzuimpercentage_sector", 5.5)
        verzuimdagen = n * 220 * verzuim / 100  # 220 werkdagen/jaar

        current_cost = verzuimdagen * kosten_per_dag
        saving = current_cost * preventie_effect

        return BCLine(
            category=BCCategory.VERZUIM,
            description="Kosten van ziekteverzuim en potentie door preventie en vroegsignalering",
            current_cost_annual=current_cost,
            potential_saving_annual=saving,
            saving_5yr=saving * 5,
            assumptions=[
                f"Verzuimpercentage: {verzuim:.1f}%",
                f"Verzuimdagen/jaar: {verzuimdagen:,.0f}",
                f"Kosten per verzuimdag: €{kosten_per_dag:,.0f}",
                f"Haalbare reductie door preventie: {preventie_effect:.0%}",
            ],
            parameters_used=p,
        )

    def _calc_automatisering(self, profile: OrganizationProfile, params: dict, n: int) -> BCLine:
        p = params.get("automatisering", DEFAULT_COST_PARAMS["automatisering"])
        uurloon = p.get("gemiddeld_uurloon", 38)
        uren_per_fte = p.get("uren_per_fte_per_jaar", 1720)
        auto_aandeel = p.get("automatiseerbaar_aandeel", 0.15)
        impl_kosten = p.get("implementatiekosten_per_fte", 2000)

        # Current cost of work that could be automated
        loonkosten_automatiseerbaar = n * uren_per_fte * uurloon * auto_aandeel

        # Net saving (minus implementation amortized over 3 years)
        impl_amortized = (n * impl_kosten * auto_aandeel) / 3
        saving = loonkosten_automatiseerbaar * 0.50 - impl_amortized  # 50% realiseerbaar

        if saving < 0:
            saving = 0

        return BCLine(
            category=BCCategory.AUTOMATISERING,
            description="Besparingspotentie door automatisering en AI van routinetaken",
            current_cost_annual=loonkosten_automatiseerbaar,
            potential_saving_annual=saving,
            saving_5yr=saving * 5,
            assumptions=[
                f"Gemiddeld uurloon: €{uurloon}",
                f"Automatiseerbaar aandeel taken: {auto_aandeel:.0%}",
                f"Implementatiekosten: €{impl_kosten}/FTE (afgeschreven over 3 jaar)",
                "Realisatie-graad: 50% van theoretisch potentieel",
            ],
            parameters_used=p,
        )

    def _calc_kennisbehoud(self, profile: OrganizationProfile, params: dict, n: int) -> BCLine:
        p = params.get("kennisbehoud", DEFAULT_COST_PARAMS["kennisbehoud"])
        kosten_verlies = p.get("kosten_kennisverlies_per_vertrek", 25000)
        aandeel_kritiek = p.get("aandeel_kritieke_functies", 0.15)

        # Assume verloop for critical roles = same as overall
        verloop = profile.turnover_rate or 12.0
        kritieke_vertrekkers = int(n * aandeel_kritiek * verloop / 100)

        current_cost = kritieke_vertrekkers * kosten_verlies
        # With knowledge management: 40% reduction in knowledge loss cost
        saving = current_cost * 0.40

        return BCLine(
            category=BCCategory.KENNISBEHOUD,
            description="Kosten van kennisverlies bij vertrek van medewerkers in kritieke functies",
            current_cost_annual=current_cost,
            potential_saving_annual=saving,
            saving_5yr=saving * 5,
            assumptions=[
                f"Aandeel kritieke functies: {aandeel_kritiek:.0%} ({int(n * aandeel_kritiek)} FTE)",
                f"Kosten kennisverlies per vertrek: €{kosten_verlies:,.0f}",
                f"Geschat verloop kritieke functies: {verloop:.1f}% ({kritieke_vertrekkers}/jaar)",
                "Reductie door kennismanagement: ~40%",
            ],
            parameters_used=p,
        )

    # ============================================
    # Helpers
    # ============================================

    async def _load_sector_params(self, sector_slug: str) -> dict:
        """Load sector-specific business case parameters."""
        try:
            rows = await fetch_all(
                "SELECT * FROM get_businesscase_parameters($1)", sector_slug
            )
            params = {}
            for row in rows:
                cat = row["category"]
                if cat not in params:
                    params[cat] = {}
                params[cat][row["parameter_name"]] = row["parameter_value"]
            return params
        except Exception as e:
            logger.warning("bc_params_load_failed", sector=sector_slug, error=str(e))
            return {}

    @staticmethod
    def _apply_overrides(params: dict, overrides: ExpertOverrides) -> dict:
        """Apply expert mode overrides to parameters."""
        for key, value in overrides.overrides.items():
            # Key format: "category.parameter_name" or just "parameter_name"
            if "." in key:
                cat, param = key.split(".", 1)
                if cat in params:
                    params[cat][param] = value
            else:
                # Search all categories
                for cat_params in params.values():
                    if isinstance(cat_params, dict) and key in cat_params:
                        cat_params[key] = value
        return params
