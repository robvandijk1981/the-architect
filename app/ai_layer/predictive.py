"""
FASE 5.3: Predictive Engine
Forecasts workforce gaps, cost trajectories, and recommends intervention priorities.
"""

import structlog
from typing import Dict, Any, List, Optional

from app.statistical.forecasting import WorkforceForecaster
from app.calculation.engine import CalculationEngine
from app.core.database import fetch_all

logger = structlog.get_logger()


class PredictiveEngine:
    """
    Generates forward-looking predictions and recommendations.
    """

    @classmethod
    async def predict_workforce_gap(
        cls,
        sector: str,
        current_fte: int,
        growth_rate: float,
        retirement_rate: float,
        attrition_rate: float = 12.0,
        years: int = 5,
    ) -> Dict[str, Any]:
        """
        Predict future workforce gaps using demographic modeling.

        Args:
            sector: Sector ID
            current_fte: Current FTE count
            growth_rate: Expected business growth rate (% per year)
            retirement_rate: Expected retirement rate (% per year)
            attrition_rate: Voluntary attrition rate (% per year)
            years: Projection period

        Returns:
            {
                "current_fte": int,
                "projection": [
                    {"year": int, "fte_demand": int, "fte_available": int, "gap": int, "gap_type": str},
                    ...
                ],
                "total_gap_person_years": int,
                "peak_gap_year": int,
                "recruitment_needed": int,
                "retention_priority": float,
                "recommendations": [str, ...],
            }
        """
        try:
            # Get sector benchmarks from database
            benchmarks = await fetch_all(
                "SELECT * FROM sector_benchmarks WHERE sector_id = $1 ORDER BY year DESC LIMIT 1",
                sector,
            )

            projection = []
            available_fte = current_fte
            total_gap_person_years = 0
            max_gap = 0
            peak_gap_year = 0

            for year in range(1, years + 1):
                # Demand side: grow with business
                fte_demand = int(current_fte * ((1 + growth_rate / 100) ** year))

                # Supply side: lose to retirement and attrition
                losses = int(available_fte * ((retirement_rate + attrition_rate) / 100))
                available_fte = max(0, available_fte - losses)

                # Gap
                gap = fte_demand - available_fte
                gap_type = "surplus" if gap < 0 else "shortage"

                if gap > max_gap:
                    max_gap = gap
                    peak_gap_year = year

                if gap > 0:
                    total_gap_person_years += gap

                projection.append({
                    "year": year,
                    "fte_demand": fte_demand,
                    "fte_available": available_fte,
                    "gap": gap,
                    "gap_type": gap_type,
                })

            # Recommendations
            recommendations = cls._workforce_gap_recommendations(
                total_gap_person_years,
                projection,
                retention_rate=100 - attrition_rate,
            )

            return {
                "sector": sector,
                "current_fte": current_fte,
                "assumptions": {
                    "growth_rate_pct": growth_rate,
                    "retirement_rate_pct": retirement_rate,
                    "attrition_rate_pct": attrition_rate,
                    "projection_years": years,
                },
                "projection": projection,
                "total_gap_person_years": total_gap_person_years,
                "max_gap_single_year": max_gap,
                "peak_gap_year": peak_gap_year,
                "recruitment_needed": sum(p["gap"] for p in projection if p["gap"] > 0),
                "retention_critical": attrition_rate > 15,
                "recommendations": recommendations,
            }

        except Exception as e:
            logger.error("predict_workforce_gap_error", error=str(e))
            return {"error": str(e), "recommendations": ["Consult with HR planning team"]}

    @classmethod
    async def predict_cost_trajectory(
        cls,
        sector: str,
        current_costs: Dict[str, float],
        escalation_factor: float = 1.08,
        years: int = 5,
    ) -> Dict[str, Any]:
        """
        Project cost escalation over time.

        Args:
            sector: Sector ID
            current_costs: Current cost components {component: amount}
            escalation_factor: Annual escalation (1.08 = 8% increase)
            years: Projection period

        Returns:
            {
                "current_total": float,
                "projection": [
                    {"year": int, "total": float, "breakdown": {...}},
                    ...
                ],
                "total_cost_5yr": float,
                "cagr": float,
                "cost_control_needed": bool,
                "recommendations": [str, ...],
            }
        """
        try:
            projection = []
            current_total = sum(current_costs.values())
            cumulative = 0

            for year in range(1, years + 1):
                year_multiplier = escalation_factor ** year
                year_total = current_total * year_multiplier
                cumulative += year_total

                # Breakdown by component
                breakdown = {
                    component: round(amount * year_multiplier, 0)
                    for component, amount in current_costs.items()
                }

                projection.append({
                    "year": year,
                    "total": round(year_total, 0),
                    "breakdown": breakdown,
                    "increase_from_current_pct": round((year_multiplier - 1) * 100, 1),
                })

            # CAGR calculation
            final_total = current_total * (escalation_factor ** years)
            cagr = ((final_total / current_total) ** (1 / years) - 1) * 100

            # Recommendations
            recommendations = cls._cost_trajectory_recommendations(
                cagr,
                escalation_factor,
                cumulative,
                current_total,
            )

            return {
                "sector": sector,
                "current_total": round(current_total, 0),
                "assumptions": {
                    "annual_escalation_pct": round((escalation_factor - 1) * 100, 1),
                    "projection_years": years,
                },
                "projection": projection,
                "total_cost_5yr": round(cumulative, 0),
                "total_cost_5yr_vs_today": round(cumulative - (current_total * years), 0),
                "cagr_pct": round(cagr, 1),
                "cost_control_priority": "HIGH" if cagr > 6 else "MEDIUM" if cagr > 3 else "LOW",
                "recommendations": recommendations,
            }

        except Exception as e:
            logger.error("predict_cost_trajectory_error", error=str(e))
            return {"error": str(e), "recommendations": ["Review cost structure with Finance"]}

    @classmethod
    async def identify_intervention_priority(
        cls,
        benchmark_scores: Dict[str, float],
        sector: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Rank interventions by potential impact based on benchmark gaps.

        Args:
            benchmark_scores: KPI scores from benchmark calculation
            sector: Optional sector for context

        Returns:
            Sorted list of interventions
        """
        try:
            # Map benchmark gaps to interventions
            intervention_library = cls._get_intervention_library()

            # Calculate gap for each KPI and match to interventions
            scored_interventions = []

            for intervention in intervention_library:
                target_kpi = intervention["target_kpi"]
                if target_kpi not in benchmark_scores:
                    continue

                current_score = benchmark_scores[target_kpi]
                benchmark = intervention["benchmark_target"]
                gap = abs(current_score - benchmark)

                # Only include interventions with meaningful gaps
                if gap < 5:
                    continue

                # Estimate impact
                potential_impact = intervention["impact_per_point"] * gap
                roi_months = intervention["cost_to_implement"] / (potential_impact / 12) if potential_impact > 0 else 999

                scored_interventions.append({
                    "intervention": intervention["name"],
                    "target_kpi": target_kpi,
                    "current_score": round(current_score, 1),
                    "benchmark_score": benchmark,
                    "gap": round(gap, 1),
                    "potential_impact_eur": round(potential_impact, 0),
                    "effort_level": intervention["effort"],
                    "cost_to_implement": intervention["cost_to_implement"],
                    "roi_months": round(roi_months, 1),
                    "rationale": intervention["rationale"],
                })

            # Sort by impact/effort ratio (highest first)
            scored_interventions.sort(
                key=lambda x: (x["potential_impact_eur"] / max(x["cost_to_implement"], 1), -x["roi_months"]),
                reverse=True
            )

            # Add ranking
            for i, intervention in enumerate(scored_interventions, 1):
                intervention["rank"] = i

            return scored_interventions[:10]  # Return top 10

        except Exception as e:
            logger.error("identify_intervention_priority_error", error=str(e))
            return []

    @classmethod
    async def scenario_optimizer(
        cls,
        sector: str,
        budget: float,
        constraints: Dict[str, Any],
        current_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Suggest optimal allocation of workforce budget across interventions.

        Args:
            sector: Sector ID
            budget: Total budget available (EUR)
            constraints: {max_implementations: int, min_roi_months: float, ...}
            current_state: Current KPIs and costs

        Returns:
            Optimized allocation plan
        """
        try:
            max_implementations = constraints.get("max_implementations", 5)
            min_roi_months = constraints.get("min_roi_months", 24)

            # Get all possible interventions
            interventions = cls._get_intervention_library()

            # Filter by ROI threshold
            viable = [i for i in interventions if i.get("typical_roi_months", 999) <= min_roi_months]
            viable.sort(key=lambda x: x["impact_per_point"] / max(x["cost_to_implement"], 1), reverse=True)

            allocations = []
            remaining_budget = budget
            total_benefit = 0

            for i, intervention in enumerate(viable):
                if i >= max_implementations or remaining_budget < intervention["cost_to_implement"]:
                    break

                cost = intervention["cost_to_implement"]
                # Assume moderate gap of 10 points
                benefit = intervention["impact_per_point"] * 10

                allocations.append({
                    "rank": i + 1,
                    "intervention": intervention["name"],
                    "budget": cost,
                    "expected_benefit": round(benefit, 0),
                    "roi_months": intervention.get("typical_roi_months", 24),
                    "timeline_months": intervention.get("timeline_months", 6),
                })

                remaining_budget -= cost
                total_benefit += benefit

            overall_roi = (sum(a["roi_months"] for a in allocations) / len(allocations)) if allocations else 999

            recommendations = [
                f"Allocate {len(allocations)} interventions within budget constraints",
                f"Expected annual benefit: €{round(total_benefit, 0):,.0f}",
                f"Payback period: {round(overall_roi, 1)} months",
            ]

            return {
                "sector": sector,
                "budget_available": budget,
                "budget_allocated": round(budget - remaining_budget, 0),
                "budget_remaining": round(remaining_budget, 0),
                "allocations": allocations,
                "total_expected_benefit": round(total_benefit, 0),
                "overall_roi_months": round(overall_roi, 1),
                "implementation_count": len(allocations),
                "recommendations": recommendations,
            }

        except Exception as e:
            logger.error("scenario_optimizer_error", error=str(e))
            return {"error": str(e), "recommendations": ["Consult ModellenWerk for custom analysis"]}

    # ============ PRIVATE HELPERS ============

    @classmethod
    def _workforce_gap_recommendations(
        cls,
        total_gap: int,
        projection: List[Dict],
        retention_rate: float,
    ) -> List[str]:
        """Generate recommendations based on workforce gap analysis."""
        recommendations = []

        if total_gap > 0:
            recommendations.append(f"Recruit proactively: {total_gap} FTE shortage over {len(projection)} years")

        if retention_rate < 85:
            recommendations.append(f"High attrition risk: focus on retention programs")

        max_single_year = max((p["gap"] for p in projection if p["gap"] > 0), default=0)
        if max_single_year > 10:
            peak_year = next((p['year'] for p in projection if p['gap'] == max_single_year), 1)
            recommendations.append(f"Plan recruitment pipeline early: peak demand {max_single_year} FTE in year {peak_year}")

        if not recommendations:
            recommendations.append("Workforce outlook stable: maintain current headcount strategy")

        return recommendations

    @classmethod
    def _cost_trajectory_recommendations(
        cls,
        cagr: float,
        escalation_factor: float,
        cumulative_5yr: float,
        current_annual: float,
    ) -> List[str]:
        """Generate recommendations based on cost projection."""
        recommendations = []

        if cagr > 6:
            recommendations.append("URGENT: Cost growth exceeds business growth. Implement cost control measures.")
        elif cagr > 3:
            recommendations.append("Monitor cost escalation. Consider process optimization initiatives.")

        if escalation_factor > 1.10:
            recommendations.append(f"Annual escalation at {(escalation_factor - 1) * 100:.1f}% is aggressive. Negotiate contracts.")

        overspend_5yr = cumulative_5yr - (current_annual * 5)
        if overspend_5yr > 0:
            recommendations.append(f"5-year budget impact: €{overspend_5yr:,.0f} above baseline. Plan accordingly.")

        return recommendations

    @classmethod
    def _get_intervention_library(cls) -> List[Dict[str, Any]]:
        """
        Return a curated library of workforce interventions with expected impacts.
        """
        return [
            {
                "name": "Turnover Reduction Program",
                "target_kpi": "turnover_rate",
                "benchmark_target": 10.0,
                "impact_per_point": 50000,
                "cost_to_implement": 75000,
                "effort": "MEDIUM",
                "timeline_months": 6,
                "typical_roi_months": 18,
                "rationale": "Targeted retention program with manager training and career development",
            },
            {
                "name": "Recruitment & Onboarding Optimization",
                "target_kpi": "time_to_fill",
                "benchmark_target": 45,
                "impact_per_point": 15000,
                "cost_to_implement": 50000,
                "effort": "LOW",
                "timeline_months": 3,
                "typical_roi_months": 6,
                "rationale": "Process automation, employer branding, pipeline development",
            },
            {
                "name": "Health & Wellbeing Initiative",
                "target_kpi": "absenteeism_rate",
                "benchmark_target": 4.0,
                "impact_per_point": 120000,
                "cost_to_implement": 150000,
                "effort": "MEDIUM",
                "timeline_months": 9,
                "typical_roi_months": 15,
                "rationale": "Mental health support, ergonomics, stress management programs",
            },
            {
                "name": "Skills Development & Reskilling",
                "target_kpi": "productivity_index",
                "benchmark_target": 85,
                "impact_per_point": 80000,
                "cost_to_implement": 200000,
                "effort": "HIGH",
                "timeline_months": 12,
                "typical_roi_months": 24,
                "rationale": "Upskilling programs, digital transformation, future-proofing workforce",
            },
            {
                "name": "Flexible Work & Location Strategy",
                "target_kpi": "engagement_score",
                "benchmark_target": 75,
                "impact_per_point": 40000,
                "cost_to_implement": 50000,
                "effort": "LOW",
                "timeline_months": 3,
                "typical_roi_months": 9,
                "rationale": "Hybrid work policy, location flexibility, remote collaboration tools",
            },
            {
                "name": "Process Automation & Efficiency",
                "target_kpi": "cost_per_fte",
                "benchmark_target": 50000,
                "impact_per_point": 5000,
                "cost_to_implement": 300000,
                "effort": "HIGH",
                "timeline_months": 6,
                "typical_roi_months": 20,
                "rationale": "RPA, workflow optimization, AI-assisted tasks",
            },
        ]
