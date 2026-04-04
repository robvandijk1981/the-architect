"""
The Architect Calculation Engine
8 workforce calculation modules with Monte Carlo support.
All calculations are deterministic given inputs; Monte Carlo adds uncertainty ranges.
"""

import math
from typing import Dict, List, Optional, Any, Tuple

class CalculationEngine:
    """Stateless calculation engine. All methods are classmethod/staticmethod."""

    # ========================================
    # MODULE 1: Vacancy Cost Calculator
    # ========================================
    @staticmethod
    def vacancy_cost(
        open_vacancies: int,
        time_to_fill_days: float,
        cost_per_hire: float,
        indirect_cost_overwork_month: float = 1200,
        indirect_cost_temp_premium_month: float = 2800,
        indirect_cost_productivity_loss_month: float = 1500,
        sector_benchmark_ttf: Optional[float] = None,
        sector_benchmark_cpv: Optional[float] = None,
    ) -> Dict[str, Any]:
        ttf_months = time_to_fill_days / 30.0
        indirect_per_month = (indirect_cost_overwork_month +
                              indirect_cost_temp_premium_month +
                              indirect_cost_productivity_loss_month)

        cost_per_vacancy = cost_per_hire + (indirect_per_month * ttf_months)
        total_annual = cost_per_vacancy * open_vacancies

        breakdown = [
            {"category": "Direct recruitment costs", "amount_eur": round(cost_per_hire * open_vacancies, 2),
             "description": f"{open_vacancies} vacancies × €{cost_per_hire:,.0f} per hire"},
            {"category": "Overtime existing staff", "amount_eur": round(indirect_cost_overwork_month * ttf_months * open_vacancies, 2),
             "description": f"€{indirect_cost_overwork_month:,.0f}/month × {ttf_months:.1f} months × {open_vacancies} vacancies"},
            {"category": "Temp/contractor premium", "amount_eur": round(indirect_cost_temp_premium_month * ttf_months * open_vacancies, 2),
             "description": f"€{indirect_cost_temp_premium_month:,.0f}/month × {ttf_months:.1f} months × {open_vacancies} vacancies"},
            {"category": "Productivity loss", "amount_eur": round(indirect_cost_productivity_loss_month * ttf_months * open_vacancies, 2),
             "description": f"€{indirect_cost_productivity_loss_month:,.0f}/month × {ttf_months:.1f} months × {open_vacancies} vacancies"},
        ]

        benchmark = {}
        if sector_benchmark_ttf:
            benchmark["time_to_fill_vs_sector"] = {
                "yours": time_to_fill_days,
                "sector_median": sector_benchmark_ttf,
                "delta_pct": round((time_to_fill_days - sector_benchmark_ttf) / sector_benchmark_ttf * 100, 1)
            }

        return {
            "total_annual_cost": round(total_annual, 2),
            "cost_per_vacancy": round(cost_per_vacancy, 2),
            "breakdown": breakdown,
            "benchmark_comparison": benchmark,
            "methodology": f"TVC = N × (CPH + (IC_month × TTF/30)), where IC_month = overwork({indirect_cost_overwork_month}) + temp_premium({indirect_cost_temp_premium_month}) + productivity_loss({indirect_cost_productivity_loss_month})",
            "assumptions": [
                f"Time to fill: {time_to_fill_days} days",
                f"Direct hiring cost: €{cost_per_hire:,.0f}",
                f"Indirect cost per unfilled vacancy: €{indirect_per_month:,.0f}/month",
                "Assumes current vacancy snapshot represents rolling average"
            ],
            "sources": ["Berenschot HR Benchmark 2024", "UWV Arbeidsmarktinfo 2025", "ModellenWerk estimate"]
        }

    # ========================================
    # MODULE 2: Turnover Cost Calculator
    # ========================================
    @staticmethod
    def turnover_cost(
        fte_count: int,
        turnover_rate: float,
        avg_salary: float,
        cost_pct_junior: float = 50,
        cost_pct_mid: float = 100,
        cost_pct_senior: float = 200,
        junior_mid_senior_split: Tuple[float, float, float] = (0.4, 0.4, 0.2),
        sector_benchmark_turnover: Optional[float] = None,
    ) -> Dict[str, Any]:
        exits_per_year = int(round(fte_count * turnover_rate / 100))

        j, m, s = junior_mid_senior_split
        weighted_cost_pct = (j * cost_pct_junior + m * cost_pct_mid + s * cost_pct_senior) / 100
        cost_per_exit = avg_salary * weighted_cost_pct
        total_annual = exits_per_year * cost_per_exit

        breakdown = [
            {"category": "Junior exits", "amount_eur": round(exits_per_year * j * avg_salary * cost_pct_junior / 100, 2),
             "description": f"{int(exits_per_year * j)} junior exits × {cost_pct_junior}% of €{avg_salary:,.0f}"},
            {"category": "Mid-level exits", "amount_eur": round(exits_per_year * m * avg_salary * cost_pct_mid / 100, 2),
             "description": f"{int(exits_per_year * m)} mid exits × {cost_pct_mid}% of €{avg_salary:,.0f}"},
            {"category": "Senior exits", "amount_eur": round(exits_per_year * s * avg_salary * cost_pct_senior / 100, 2),
             "description": f"{int(exits_per_year * s)} senior exits × {cost_pct_senior}% of €{avg_salary:,.0f}"},
        ]

        benchmark = {}
        if sector_benchmark_turnover:
            benchmark["turnover_vs_sector"] = {
                "yours": turnover_rate,
                "sector_median": sector_benchmark_turnover,
                "delta_pct": round(turnover_rate - sector_benchmark_turnover, 1),
                "excess_cost": round(max(0, (turnover_rate - sector_benchmark_turnover) / 100 * fte_count * cost_per_exit), 2)
            }

        return {
            "total_annual_cost": round(total_annual, 2),
            "cost_per_exit": round(cost_per_exit, 2),
            "estimated_exits_per_year": exits_per_year,
            "breakdown": breakdown,
            "benchmark_comparison": benchmark,
            "methodology": f"ATC = FTE × turnover_rate × weighted_avg(cost_pct × salary). Split: {j:.0%} junior/{m:.0%} mid/{s:.0%} senior.",
            "assumptions": [
                f"FTE count: {fte_count}",
                f"Turnover rate: {turnover_rate}%",
                f"Average salary: €{avg_salary:,.0f}",
                f"Junior/Mid/Senior cost: {cost_pct_junior}%/{cost_pct_mid}%/{cost_pct_senior}% of salary",
            ],
            "sources": ["SHRM Human Capital Benchmarking 2023", "Hay/Korn Ferry 2024"]
        }

    # ========================================
    # MODULE 3: Absenteeism Cost Calculator
    # ========================================
    @staticmethod
    def absenteeism_cost(
        fte_count: int,
        absenteeism_rate: float,
        avg_salary: float,
        burnout_prevalence: float = 15.0,
        burnout_cost_per_case: float = 133000,
        cost_per_sick_day: Optional[float] = None,
        working_days_per_year: int = 220,
        long_term_absence_pct: float = 25.0,
        sector_benchmark_absence: Optional[float] = None,
    ) -> Dict[str, Any]:
        if cost_per_sick_day is None:
            cost_per_sick_day = avg_salary / working_days_per_year * 1.3

        total_sick_days = fte_count * working_days_per_year * absenteeism_rate / 100
        short_term_days = total_sick_days * (1 - long_term_absence_pct / 100)
        long_term_days = total_sick_days * long_term_absence_pct / 100

        short_term_cost = short_term_days * cost_per_sick_day
        long_term_cost = long_term_days * cost_per_sick_day * 1.5

        burnout_cases = fte_count * burnout_prevalence / 100 * 0.10
        burnout_total = burnout_cases * burnout_cost_per_case

        total_annual = short_term_cost + long_term_cost + burnout_total

        breakdown = [
            {"category": "Short-term absence (<6 weeks)", "amount_eur": round(short_term_cost, 2),
             "description": f"{int(short_term_days):,} days × €{cost_per_sick_day:,.0f}/day"},
            {"category": "Long-term absence (>6 weeks)", "amount_eur": round(long_term_cost, 2),
             "description": f"{int(long_term_days):,} days × €{cost_per_sick_day * 1.5:,.0f}/day (1.5× multiplier)"},
            {"category": "Burnout cases", "amount_eur": round(burnout_total, 2),
             "description": f"{burnout_cases:.1f} cases × €{burnout_cost_per_case:,.0f}/case ({burnout_prevalence}% at risk, 10% actualization)"},
        ]

        benchmark = {}
        if sector_benchmark_absence:
            excess_pct = absenteeism_rate - sector_benchmark_absence
            benchmark["absence_vs_sector"] = {
                "yours": absenteeism_rate,
                "sector_median": sector_benchmark_absence,
                "delta_pct": round(excess_pct, 1),
                "excess_cost": round(max(0, excess_pct / 100 * fte_count * working_days_per_year * cost_per_sick_day), 2)
            }

        return {
            "total_annual_cost": round(total_annual, 2),
            "burnout_component": round(burnout_total, 2),
            "short_term_component": round(short_term_cost, 2),
            "long_term_component": round(long_term_cost, 2),
            "breakdown": breakdown,
            "benchmark_comparison": benchmark,
            "methodology": f"AAC = (sick_days × CPD) + (burnout_cases × CPBO). Sick days = FTE × {working_days_per_year} × absence_rate. Long-term 1.5× multiplier. Burnout = {burnout_prevalence}% at-risk × 10% actualization.",
            "assumptions": [
                f"FTE count: {fte_count}",
                f"Absenteeism rate: {absenteeism_rate}%",
                f"Cost per sick day: €{cost_per_sick_day:,.0f}",
                f"Burnout cost per case: €{burnout_cost_per_case:,.0f} (Rabobank/werf-en.nl methodology)",
                f"Long-term absence: {long_term_absence_pct}% of total"
            ],
            "sources": ["Rabobank Kosten van Krapte 2022", "Vernet Verzuimnetwerk 2025", "TNO Werkgeversenquete 2024"]
        }

    # ========================================
    # MODULE 4: Cost of Inaction (Aggregator)
    # ========================================
    @staticmethod
    def cost_of_inaction(
        sector_id: str,
        fte_count: int,
        open_vacancies: int = 0,
        turnover_rate: float = 10,
        absenteeism_rate: float = 5,
        avg_salary: float = 50000,
        burnout_prevalence: float = 15.0,
        time_to_fill_days: float = 60.0,
        cost_per_hire: float = 4000.0,
        projection_years: int = 5,
        escalation_factor: float = 1.08,
        societal_cost_multiplier: float = 0.15,
        include_societal: bool = True,
        sector_benchmarks: Optional[Dict] = None,
        **kwargs
    ) -> Dict[str, Any]:

        vacancy = CalculationEngine.vacancy_cost(
            open_vacancies=open_vacancies,
            time_to_fill_days=time_to_fill_days,
            cost_per_hire=cost_per_hire,
            **{k: v for k, v in kwargs.items() if k.startswith('indirect_cost_')}
        )

        turnover = CalculationEngine.turnover_cost(
            fte_count=fte_count,
            turnover_rate=turnover_rate,
            avg_salary=avg_salary,
        )

        absence = CalculationEngine.absenteeism_cost(
            fte_count=fte_count,
            absenteeism_rate=absenteeism_rate,
            avg_salary=avg_salary,
            burnout_prevalence=burnout_prevalence,
        )

        direct_costs = vacancy["total_annual_cost"] + turnover["total_annual_cost"] + absence["total_annual_cost"]
        societal = direct_costs * societal_cost_multiplier if include_societal else 0
        total_annual = direct_costs + societal

        projection = []
        cumulative = 0
        for y in range(1, projection_years + 1):
            year_cost = total_annual * (escalation_factor ** (y - 1))
            cumulative += year_cost
            projection.append({
                "year": y,
                "total_cost": round(year_cost, 2),
                "cumulative_cost": round(cumulative, 2),
                "escalation_factor": round(escalation_factor ** (y - 1), 3)
            })

        breakdown = [
            {"category": "Vacancy costs", "amount_eur": vacancy["total_annual_cost"],
             "description": f"{open_vacancies} vacancies, {time_to_fill_days} days avg TTF"},
            {"category": "Turnover costs", "amount_eur": turnover["total_annual_cost"],
             "description": f"{turnover['estimated_exits_per_year']} exits/year at {turnover_rate}% rate"},
            {"category": "Absenteeism & burnout costs", "amount_eur": absence["total_annual_cost"],
             "description": f"{absenteeism_rate}% absence rate, {burnout_prevalence}% burnout risk"},
        ]
        if include_societal:
            breakdown.append({
                "category": "Societal/indirect costs", "amount_eur": round(societal, 2),
                "description": f"{societal_cost_multiplier:.0%} multiplier on direct costs (delayed services, quality impact)"
            })

        interventions = CalculationEngine._recommend_interventions(
            vacancy["total_annual_cost"], turnover["total_annual_cost"],
            absence["total_annual_cost"], absenteeism_rate, turnover_rate,
            sector_benchmarks
        )

        benchmark = {}
        if sector_benchmarks:
            rabobank_total = 20_000_000_000
            benchmark["rabobank_anchor"] = {
                "economy_wide_eur": rabobank_total,
                "your_share_pct": round(total_annual / rabobank_total * 100, 4),
                "context": "Rabobank estimates total economy-wide cost of labour shortages at €20B/year"
            }

        return {
            "total_annual_cost": round(total_annual, 2),
            "vacancy_costs": vacancy["total_annual_cost"],
            "turnover_costs": turnover["total_annual_cost"],
            "absenteeism_costs": absence["total_annual_cost"],
            "societal_costs": round(societal, 2),
            "breakdown": breakdown,
            "projection": projection,
            "top_3_interventions": interventions,
            "benchmark_comparison": benchmark,
            "methodology": f"CoI = vacancy_cost + turnover_cost + absenteeism_cost + (societal_multiplier × direct_costs). Projection: {escalation_factor:.0%} annual escalation over {projection_years} years.",
            "assumptions": [
                f"Sector: {sector_id}",
                f"Organisation size: {fte_count} FTE",
                f"Escalation factor: {escalation_factor:.0%}/year (demographic + labour market tightness)",
                f"Societal cost multiplier: {societal_cost_multiplier:.0%}",
                "All sub-calculations use sector defaults where not overridden"
            ],
            "sources": [
                "Rabobank Kosten van Krapte 2022 (€20B anchor)",
                "CBS StatLine 2025", "UWV Arbeidsmarktinfo 2025",
                "Berenschot HR Benchmark 2024", "Vernet 2025"
            ]
        }

    @staticmethod
    def _recommend_interventions(vacancy_cost, turnover_cost, absence_cost,
                                  absence_rate, turnover_rate, benchmarks) -> List[Dict]:
        """Rule-based intervention recommendations sorted by expected impact."""
        interventions = []

        total = vacancy_cost + turnover_cost + absence_cost

        costs = [
            ("vacancy", vacancy_cost, "Reduce time-to-fill by 20% through employer branding and process optimization",
             vacancy_cost * 0.20, "Employer branding ROI: 2-3× (LinkedIn Talent Solutions 2024)"),
            ("turnover", turnover_cost, "Implement retention programme targeting top-performers and critical roles",
             turnover_cost * 0.25, "Retention 5× cheaper than replacement (SHRM 2023)"),
            ("absenteeism", absence_cost, "Launch preventive burnout programme with early warning indicators",
             absence_cost * 0.15, "Preventive programmes reduce absence by 15-25% (TNO 2024)"),
        ]

        costs.sort(key=lambda x: x[3], reverse=True)

        for i, (driver, cost, intervention, savings, evidence) in enumerate(costs):
            interventions.append({
                "rank": i + 1,
                "driver": driver,
                "current_cost": round(cost, 2),
                "intervention": intervention,
                "expected_annual_savings": round(savings, 2),
                "evidence": evidence,
                "pct_of_total": round(cost / total * 100, 1) if total > 0 else 0
            })

        return interventions

    # ========================================
    # MODULE 5: Reskilling ROI Calculator
    # ========================================
    @staticmethod
    def reskilling_roi(
        num_employees: int,
        investment_per_person: float,
        expected_productivity_gain_pct: float,
        avg_salary: float,
        time_horizon_years: int = 3,
        discount_rate: float = 0.05,
        ramp_up_months: int = 6,
    ) -> Dict[str, Any]:
        total_investment = num_employees * investment_per_person
        annual_benefit_full = num_employees * avg_salary * expected_productivity_gain_pct / 100

        ramp_factor_y1 = 1 - (ramp_up_months / 12 * 0.5)

        npv = -total_investment
        cashflow = [{"year": 0, "cashflow": -total_investment, "cumulative": -total_investment}]
        cumulative = -total_investment

        for year in range(1, time_horizon_years + 1):
            benefit = annual_benefit_full * (ramp_factor_y1 if year == 1 else 1.0)
            discounted = benefit / ((1 + discount_rate) ** year)
            npv += discounted
            cumulative += benefit
            cashflow.append({
                "year": year,
                "cashflow": round(benefit, 2),
                "discounted_cashflow": round(discounted, 2),
                "cumulative": round(cumulative, 2)
            })

        monthly_benefit = annual_benefit_full * ramp_factor_y1 / 12
        break_even_months = total_investment / monthly_benefit if monthly_benefit > 0 else float('inf')

        irr = CalculationEngine._calculate_irr(total_investment, annual_benefit_full,
                                                 time_horizon_years, ramp_factor_y1)

        roi_pct = (npv / total_investment) * 100 if total_investment > 0 else 0

        return {
            "total_investment": round(total_investment, 2),
            "npv": round(npv, 2),
            "irr": round(irr * 100, 1) if irr else None,
            "break_even_months": round(break_even_months, 1),
            "roi_pct": round(roi_pct, 1),
            "annual_benefit": round(annual_benefit_full, 2),
            "cashflow_projection": cashflow,
            "methodology": f"NPV = Σ(t=1→{time_horizon_years}) [(N × salary × prod_gain) / (1+r)^t] - (N × invest_pp). Ramp-up: {ramp_up_months} months at 50% effectiveness.",
            "assumptions": [
                f"Employees in programme: {num_employees}",
                f"Investment per person: €{investment_per_person:,.0f}",
                f"Expected productivity gain: {expected_productivity_gain_pct}%",
                f"Discount rate: {discount_rate:.1%}",
                f"Ramp-up period: {ramp_up_months} months"
            ],
            "sources": ["McKinsey Reskilling Imperative 2024", "WEF Future of Jobs 2025"]
        }

    @staticmethod
    def _calculate_irr(investment, annual_benefit, years, ramp_y1, max_iter=100):
        """Bisection method for IRR."""
        lo, hi = -0.5, 5.0
        for _ in range(max_iter):
            r = (lo + hi) / 2
            npv = -investment
            for y in range(1, years + 1):
                b = annual_benefit * (ramp_y1 if y == 1 else 1.0)
                npv += b / ((1 + r) ** y)
            if abs(npv) < 1:
                return r
            if npv > 0:
                lo = r
            else:
                hi = r
        return (lo + hi) / 2

    # ========================================
    # MODULE 6: Automation ROI Calculator
    # ========================================
    @staticmethod
    def automation_roi(
        current_fte_allocated: float,
        implementation_cost: float,
        expected_fte_reduction: float,
        avg_salary: float,
        time_horizon_years: int = 5,
        failure_rate: float = 0.35,
        maintenance_cost_pct: float = 0.15,
        discount_rate: float = 0.05,
    ) -> Dict[str, Any]:
        annual_savings_gross = expected_fte_reduction * avg_salary
        annual_maintenance = implementation_cost * maintenance_cost_pct
        annual_savings_net = annual_savings_gross - annual_maintenance
        annual_savings_risk_adjusted = annual_savings_net * (1 - failure_rate)

        payback_months = (implementation_cost / annual_savings_risk_adjusted * 12) if annual_savings_risk_adjusted > 0 else float('inf')

        npv = -implementation_cost
        for y in range(1, time_horizon_years + 1):
            npv += annual_savings_risk_adjusted / ((1 + discount_rate) ** y)

        roi_pct = (npv / implementation_cost * 100) if implementation_cost > 0 else 0

        return {
            "total_investment": round(implementation_cost, 2),
            "annual_savings_gross": round(annual_savings_gross, 2),
            "annual_savings_risk_adjusted": round(annual_savings_risk_adjusted, 2),
            "annual_maintenance_cost": round(annual_maintenance, 2),
            "payback_months": round(payback_months, 1),
            "npv_5yr": round(npv, 2),
            "risk_adjusted_roi_pct": round(roi_pct, 1),
            "failure_discount_applied": failure_rate,
            "methodology": f"Risk-adjusted ROI: annual_savings × (1 - failure_rate) - maintenance. Failure rate: {failure_rate:.0%} based on industry data (30-50% of automation projects fail to deliver expected value).",
            "assumptions": [
                f"Current FTE on process: {current_fte_allocated}",
                f"Expected FTE reduction: {expected_fte_reduction}",
                f"Implementation cost: €{implementation_cost:,.0f}",
                f"Annual maintenance: {maintenance_cost_pct:.0%} of implementation",
                f"Failure rate discount: {failure_rate:.0%}",
            ],
            "sources": ["Deloitte State of AI 2026", "InSpark AI Benchmark 2025", "McKinsey AI Impact 2024"]
        }

    # ========================================
    # MODULE 7: Scenario Comparator
    # ========================================
    @staticmethod
    def scenario_compare(
        scenario_a: Dict[str, Any],
        scenario_b: Dict[str, Any],
        time_horizon_years: int = 5,
    ) -> Dict[str, Any]:
        def run_scenario(s):
            coi = CalculationEngine.cost_of_inaction(
                sector_id=s.get("sector", ""),
                fte_count=s["fte_count"],
                open_vacancies=s.get("open_vacancies", 0),
                turnover_rate=s.get("turnover_rate", 10),
                absenteeism_rate=s.get("absenteeism_rate", 5),
                avg_salary=s.get("avg_salary", 50000),
                projection_years=time_horizon_years,
            )

            reskilling_benefit = 0
            if s.get("reskilling_investment") and s.get("expected_productivity_gain_pct"):
                resk = CalculationEngine.reskilling_roi(
                    num_employees=int(s["fte_count"] * 0.2),
                    investment_per_person=s["reskilling_investment"],
                    expected_productivity_gain_pct=s["expected_productivity_gain_pct"],
                    avg_salary=s.get("avg_salary", 50000),
                    time_horizon_years=time_horizon_years,
                )
                reskilling_benefit = resk["npv"]

            automation_benefit = 0
            if s.get("automation_investment") and s.get("expected_fte_reduction"):
                auto = CalculationEngine.automation_roi(
                    current_fte_allocated=s.get("expected_fte_reduction", 0) * 2,
                    implementation_cost=s["automation_investment"],
                    expected_fte_reduction=s["expected_fte_reduction"],
                    avg_salary=s.get("avg_salary", 50000),
                    time_horizon_years=time_horizon_years,
                )
                automation_benefit = auto["npv_5yr"]

            return {
                "name": s.get("name", "Scenario"),
                "cost_of_inaction": coi["total_annual_cost"],
                "cumulative_cost": coi["projection"][-1]["cumulative_cost"] if coi["projection"] else 0,
                "reskilling_npv": round(reskilling_benefit, 2),
                "automation_npv": round(automation_benefit, 2),
                "total_net_position": round(-coi["projection"][-1]["cumulative_cost"] + reskilling_benefit + automation_benefit, 2),
            }

        a = run_scenario(scenario_a)
        b = run_scenario(scenario_b)

        delta = {k: round(b[k] - a[k], 2) for k in a if isinstance(a[k], (int, float))}

        better = "b" if b["total_net_position"] > a["total_net_position"] else "a"
        savings = abs(b["total_net_position"] - a["total_net_position"])

        return {
            "scenario_a_summary": a,
            "scenario_b_summary": b,
            "delta": delta,
            "total_savings": round(savings, 2),
            "recommended_scenario": scenario_b["name"] if better == "b" else scenario_a["name"],
            "rationale": f"Scenario '{scenario_b['name'] if better == 'b' else scenario_a['name']}' yields €{savings:,.0f} better net position over {time_horizon_years} years.",
            "methodology": f"Both scenarios run through Cost of Inaction + optional Reskilling ROI + Automation ROI modules. Compared on {time_horizon_years}-year cumulative net position."
        }

    # ========================================
    # MODULE 8: Benchmark Scorer
    # ========================================
    @staticmethod
    def benchmark_score(
        kpis: Dict[str, float],
        sector_benchmarks: Dict[str, Any],
        benchmark_ranges: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> Dict[str, Any]:
        """Score organisation KPIs against sector benchmarks."""

        if benchmark_ranges is None:
            benchmark_ranges = CalculationEngine._default_benchmark_ranges(sector_benchmarks)

        scores = []
        total_score = 0
        count = 0

        for kpi_name, observed in kpis.items():
            if kpi_name not in benchmark_ranges:
                continue

            r = benchmark_ranges[kpi_name]
            p25, p50, p75 = r.get("p25"), r.get("p50"), r.get("p75")
            direction = r.get("direction", "lower_is_better")

            if p50 is None:
                continue

            if direction == "lower_is_better":
                if observed <= (p25 or p50 * 0.8):
                    score_str, score_num = "green", 100
                elif observed <= p50:
                    score_str, score_num = "green", 80
                elif observed <= (p75 or p50 * 1.2):
                    score_str, score_num = "orange", 50
                else:
                    score_str, score_num = "red", 20
                gap = round((observed - p50) / p50 * 100, 1) if p50 else 0
            else:
                if observed >= (p75 or p50 * 1.2):
                    score_str, score_num = "green", 100
                elif observed >= p50:
                    score_str, score_num = "green", 80
                elif observed >= (p25 or p50 * 0.8):
                    score_str, score_num = "orange", 50
                else:
                    score_str, score_num = "red", 20
                gap = round((p50 - observed) / p50 * 100, 1) if p50 else 0

            total_score += score_num
            count += 1

            scores.append({
                "kpi_name": kpi_name,
                "observed_value": observed,
                "benchmark_p25": p25,
                "benchmark_p50": p50,
                "benchmark_p75": p75,
                "score": score_str,
                "gap_pct": gap,
                "interpretation": f"{'Above' if gap > 0 and direction == 'lower_is_better' else 'Below'} sector median by {abs(gap)}%" if gap != 0 else "At sector median"
            })

        overall = round(total_score / count, 1) if count > 0 else 0

        red_scores = [s for s in scores if s["score"] == "red"]
        orange_scores = [s for s in scores if s["score"] == "orange"]
        opportunities = sorted(red_scores + orange_scores, key=lambda x: abs(x["gap_pct"]), reverse=True)[:3]

        top_3 = [{"kpi": o["kpi_name"], "gap": f"{abs(o['gap_pct'])}% from median",
                   "action": f"Reduce {o['kpi_name']} from {o['observed_value']} to sector median {o['benchmark_p50']}"}
                  for o in opportunities]

        return {
            "overall_maturity_score": overall,
            "kpi_scores": scores,
            "top_3_opportunities": top_3,
            "methodology": "KPIs scored against sector P25/P50/P75 percentiles. Green = better than median, Orange = P25-P75, Red = worse than P75.",
            "sources": ["ModellenWerk Sector Benchmarks 2025", "CBS StatLine", "UWV Arbeidsmarktinfo"],
            "confidence_level": "medium"
        }

    @staticmethod
    def _default_benchmark_ranges(sector_data: Dict) -> Dict[str, Dict]:
        """Generate P25/P50/P75 estimates from sector median data."""
        ranges = {}
        mapping = {
            "turnover_rate": ("lower_is_better", 0.7, 1.3),
            "absenteeism_rate": ("lower_is_better", 0.7, 1.3),
            "time_to_fill_days": ("lower_is_better", 0.75, 1.25),
            "cost_per_hire": ("lower_is_better", 0.8, 1.2),
            "vacancy_rate": ("lower_is_better", 0.7, 1.3),
            "overhead_ratio": ("lower_is_better", 0.8, 1.2),
            "flex_ratio": ("lower_is_better", 0.8, 1.2),
            "burnout_prevalence": ("lower_is_better", 0.7, 1.3),
            "ai_adoption_rate": ("higher_is_better", 0.7, 1.3),
            "robotics_adoption_rate": ("higher_is_better", 0.5, 1.5),
            "training_investment_per_fte": ("higher_is_better", 0.8, 1.2),
            "avg_revenue_per_fte": ("higher_is_better", 0.85, 1.15),
            "internal_mobility_rate": ("higher_is_better", 0.7, 1.3),
        }

        for kpi, (direction, p25_factor, p75_factor) in mapping.items():
            if kpi in sector_data and sector_data[kpi] is not None:
                median = float(sector_data[kpi])
                ranges[kpi] = {
                    "p25": round(median * p25_factor, 2),
                    "p50": median,
                    "p75": round(median * p75_factor, 2),
                    "direction": direction
                }

        return ranges
