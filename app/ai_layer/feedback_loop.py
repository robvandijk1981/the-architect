"""
FASE 5.2: Feedback Loop & Continuous Learning
Logs interactions, updates benchmarks, detects anomalies, and tracks sector trends.
"""

import json
import structlog
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

from app.core.database import fetch_all, fetch_one, execute, get_connection
from app.statistical.bayesian import BayesianBenchmarkUpdater

logger = structlog.get_logger()


# Mapping: Dutch KPI slugs (used in chat / portal / RAG) → English column
# names in the sector_benchmarks table. Keeps the public API consistent
# (Dutch everywhere) while the legacy DB schema stays English.
KPI_NAME_MAPPING = {
    # Dutch slug → English column
    "verzuim_pct": "absenteeism_rate",
    "verzuimpercentage": "absenteeism_rate",
    "ziekteverzuim": "absenteeism_rate",
    "verloop_pct": "turnover_rate",
    "verlooppercentage": "turnover_rate",
    "vacaturegraad": "vacancy_rate",
    "vacatures_pct": "vacancy_rate",
    "tijd_tot_invulling": "time_to_fill_days",
    "ttv_dagen": "time_to_fill_days",
    "kosten_per_hire": "cost_per_hire",
    "wervingskosten": "cost_per_hire",
    "burnout_pct": "burnout_prevalence",
    "burnoutprevalentie": "burnout_prevalence",
    "gem_loonkosten_fte": "avg_labour_cost_fte",
    "gem_jaarsalaris": "avg_labour_cost_fte",
}


def _normalize_kpi_name(kpi_name: str) -> str:
    """
    Translate a KPI slug to the canonical English column name used in
    sector_benchmarks. If the input is already English (or unknown),
    return it unchanged.
    """
    return KPI_NAME_MAPPING.get(kpi_name.lower(), kpi_name)


class FeedbackLoop:
    """
    Manages the continuous learning cycle:
    1. Log every calculation and user interaction
    2. Update benchmarks with new observations
    3. Detect anomalies in submitted data
    4. Track sector trends over time
    """

    # Standard deviations from mean to flag as anomaly. 2.0σ is industry
    # standard for "moderate anomaly worth attention". 2.5σ was too strict
    # — only caught extreme outliers, missed obviously-high values like
    # verzuim 9.5% (sector mean 6.1%, std ~0.92% → 3.7σ but routinely
    # missed because of KPI name mismatches in the legacy implementation).
    ANOMALY_THRESHOLD_SIGMA = 2.0

    @classmethod
    async def log_interaction(
        cls,
        session_id: str,
        calculation_type: str,
        input_data: Dict[str, Any],
        output_data: Dict[str, Any],
        sector: str,
        user_feedback: Optional[str] = None,
        validation_status: str = "pending",
    ) -> str:
        """
        Log a calculation interaction for audit trail and learning.

        Args:
            session_id: Unique session ID
            calculation_type: Type of calculation
            input_data: User input parameters
            output_data: Calculation output
            sector: Sector ID
            user_feedback: Optional feedback from user
            validation_status: Whether results were validated (pending/accepted/rejected)

        Returns:
            Interaction ID for reference
        """
        interaction_id = f"interaction_{int(datetime.now().timestamp())}"

        try:
            await execute("""
                INSERT INTO calculation_results
                (calculation_type, sector_id, input_parameters, output_results,
                 user_session_id, source_context, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
                calculation_type,
                sector,
                json.dumps(input_data, default=str),
                json.dumps(output_data, default=str),
                session_id,
                validation_status,
                datetime.utcnow()
            )

            logger.info("logged_interaction", interaction_id=interaction_id, sector=sector)
            return interaction_id

        except Exception as e:
            logger.error("error_logging_interaction", error=str(e))
            raise

    @classmethod
    async def update_benchmarks_from_results(
        cls,
        sector: str,
        calculation_results: Dict[str, Any],
        validation_status: str = "accepted",
        observation_reliability: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Update sector benchmarks using Bayesian updating with new observation.

        Args:
            sector: Sector ID
            calculation_results: Calculation result to incorporate
            validation_status: Whether data was validated (affects weighting)
            observation_reliability: Weight of this observation (0.3-1.0)

        Returns:
            Update summary with prior -> posterior shift
        """
        if validation_status != "accepted":
            logger.info("skipping_benchmark_update", reason="data_not_validated")
            return {"status": "skipped", "reason": "data not validated"}

        try:
            # Get current benchmarks
            current_benchmarks = await fetch_one(
                "SELECT * FROM sector_benchmarks WHERE sector_id = $1 ORDER BY year DESC LIMIT 1",
                sector,
            )
            if not current_benchmarks:
                logger.warning("no_benchmarks_found", sector=sector)
                return {"status": "skipped", "reason": "no benchmarks"}

            updates = {}

            # Extract KPI values from calculation results
            kpi_values = cls._extract_kpis_from_results(calculation_results)

            # Update each KPI that has a prior benchmark
            for kpi_name, observed_value in kpi_values.items():
                if kpi_name not in current_benchmarks:
                    continue

                benchmark_val = current_benchmarks[kpi_name]
                if isinstance(benchmark_val, dict):
                    benchmark_mean = benchmark_val.get("mean", benchmark_val.get("value"))
                else:
                    benchmark_mean = benchmark_val

                # Create prior from current benchmark
                prior = BayesianBenchmarkUpdater.create_prior(
                    mean=float(benchmark_mean) if benchmark_mean else 0,
                    std=float(benchmark_val.get("std", abs(float(benchmark_mean) * 0.15))) if isinstance(benchmark_val, dict) and benchmark_mean else 0,
                    n_observations=50,
                )

                # Update with new observation
                posterior = BayesianBenchmarkUpdater.update(
                    prior=prior,
                    new_observations=[float(observed_value)],
                    observation_reliability=observation_reliability,
                )

                updates[kpi_name] = {
                    "prior_mean": prior["mean"],
                    "posterior_mean": posterior["mean"],
                    "shift": posterior.get("shift", 0),
                    "uncertainty_reduction_pct": posterior.get("uncertainty_reduction_pct", 0),
                    "n_observations": posterior["n_observations"],
                }

            logger.info("updated_benchmarks", sector=sector, kpi_count=len(updates))
            return {
                "status": "success",
                "sector": sector,
                "updates": updates,
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error("error_updating_benchmarks", error=str(e))
            return {"status": "error", "message": str(e)}

    @classmethod
    async def detect_anomalies(
        cls,
        sector: str,
        new_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Detect anomalies by comparing new data to sector benchmarks.

        Accepts both flat dict ({kpi: value}) and wrapped dict
        ({"kpis": {kpi: value}}). Translates Dutch KPI slugs to the
        English column names used in sector_benchmarks.

        Args:
            sector: Sector ID
            new_data: New KPI data to analyze

        Returns:
            {
                "has_anomalies": bool,
                "anomalies": [
                    {"kpi": str, "value": float, "z_score": float, "message": str},
                    ...
                ]
            }
        """
        # Auto-unwrap if caller used the {"kpis": {...}} shape from docs/API.md
        if isinstance(new_data, dict) and "kpis" in new_data and isinstance(new_data["kpis"], dict):
            kpi_data = new_data["kpis"]
        else:
            kpi_data = new_data

        try:
            benchmarks = await fetch_one(
                "SELECT * FROM sector_benchmarks WHERE sector_id = $1 ORDER BY year DESC LIMIT 1",
                sector,
            )
            if not benchmarks:
                logger.warning("anomalies_no_benchmarks", sector=sector)
                return {"has_anomalies": False, "anomaly_count": 0, "anomalies": [], "action": "No benchmarks for this sector"}

            anomalies = []
            checked_kpis = []

            for raw_kpi_name, observed_value in kpi_data.items():
                # Translate Dutch KPI slug → English column name (or keep as-is if already English)
                kpi_name = _normalize_kpi_name(str(raw_kpi_name))

                if kpi_name not in benchmarks:
                    logger.debug("anomalies_kpi_not_found", raw=raw_kpi_name, normalized=kpi_name)
                    continue

                checked_kpis.append(raw_kpi_name)

                benchmark = benchmarks[kpi_name]
                if isinstance(benchmark, dict):
                    benchmark_mean = benchmark.get("mean", benchmark.get("value"))
                    benchmark_std = benchmark.get("std", abs(benchmark_mean * 0.15) if benchmark_mean else 1)
                else:
                    benchmark_mean = benchmark
                    benchmark_std = abs(benchmark * 0.15) if benchmark else 1

                # Calculate z-score
                if benchmark_std == 0 or benchmark_mean is None:
                    z_score = 0
                else:
                    z_score = (float(observed_value) - float(benchmark_mean)) / float(benchmark_std)

                # Flag if anomalous
                if abs(z_score) > cls.ANOMALY_THRESHOLD_SIGMA:
                    severity = "HIGH" if abs(z_score) > 4 else "MEDIUM"
                    direction = "above" if z_score > 0 else "below"
                    anomalies.append({
                        "kpi": raw_kpi_name,  # report back the user's original slug
                        "value": float(observed_value),
                        "benchmark_mean": float(benchmark_mean) if benchmark_mean else 0,
                        "z_score": round(z_score, 2),
                        "severity": severity,
                        "message": f"{raw_kpi_name}: {severity} anomaly — {abs(z_score):.1f}σ {direction} sector benchmark ({benchmark_mean})",
                    })

            logger.info(
                "anomaly_check_completed",
                sector=sector,
                checked=len(checked_kpis),
                found=len(anomalies),
            )

            return {
                "has_anomalies": len(anomalies) > 0,
                "anomaly_count": len(anomalies),
                "anomalies": anomalies,
                "action": "Review data quality and underlying causes" if anomalies else "Data within normal range",
            }

        except Exception as e:
            logger.error("error_detecting_anomalies", error=str(e))
            return {"has_anomalies": False, "anomaly_count": 0, "anomalies": [], "error": str(e)}

    @classmethod
    async def get_sector_trend(
        cls,
        sector: str,
        kpi_name: str,
        lookback_months: int = 12,
    ) -> Dict[str, Any]:
        """
        Get historical trend for a KPI in a sector.

        Args:
            sector: Sector ID
            kpi_name: KPI name (e.g., "turnover_rate")
            lookback_months: How far back to look

        Returns:
            Trend information
        """
        try:
            since = datetime.utcnow() - timedelta(days=lookback_months * 30)

            rows = await fetch_all("""
                SELECT created_at, output_results
                FROM calculation_results
                WHERE sector_id = $1 AND created_at >= $2
                ORDER BY created_at ASC
            """, sector, since)

            if not rows:
                return {
                    "kpi": kpi_name,
                    "sector": sector,
                    "data_points": [],
                    "trend": "insufficient_data",
                    "message": "Not enough historical data",
                }

            # Extract values over time
            data_points = []
            for row in rows:
                try:
                    output = json.loads(row["output_results"]) if isinstance(row["output_results"], str) else row["output_results"]
                    if kpi_name in output:
                        data_points.append({
                            "timestamp": row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else str(row["created_at"]),
                            "value": float(output[kpi_name]),
                        })
                except (json.JSONDecodeError, TypeError, KeyError, ValueError):
                    continue

            if len(data_points) < 2:
                return {
                    "kpi": kpi_name,
                    "sector": sector,
                    "data_points": data_points,
                    "trend": "insufficient_data",
                }

            # Calculate trend
            values = [d["value"] for d in data_points]
            if len(values) > 1:
                # Simple linear trend
                first_half = sum(values[:len(values)//2]) / max(1, len(values)//2)
                second_half = sum(values[len(values)//2:]) / max(1, len(values) - len(values)//2)

                if second_half > first_half * 1.05:
                    trend = "increasing"
                    trend_strength = ((second_half - first_half) / first_half) * 100 if first_half else 0
                elif second_half < first_half * 0.95:
                    trend = "decreasing"
                    trend_strength = ((first_half - second_half) / first_half) * 100 if first_half else 0
                else:
                    trend = "stable"
                    trend_strength = 0
            else:
                trend = "insufficient_data"
                trend_strength = 0

            return {
                "kpi": kpi_name,
                "sector": sector,
                "data_points": data_points,
                "trend": trend,
                "trend_strength_pct": round(trend_strength, 1),
                "latest_value": values[-1] if values else None,
                "forecast_comment": f"Current trend is {trend}. Continue monitoring for confirmation.",
            }

        except Exception as e:
            logger.error("error_getting_sector_trend", error=str(e))
            return {"kpi": kpi_name, "sector": sector, "error": str(e)}

    # ============ PRIVATE HELPERS ============

    @classmethod
    def _extract_kpis_from_results(cls, results: Dict[str, Any]) -> Dict[str, float]:
        """
        Extract KPI values from calculation results for benchmark updating.
        """
        kpis = {}

        # Common KPI patterns in results
        kpi_keys = [
            "turnover_rate",
            "absenteeism_rate",
            "vacancy_rate",
            "time_to_fill_days",
            "cost_per_hire",
            "burnout_prevalence",
            "total_annual_cost",
            "cost_per_exit",
            "total_cost_per_fte",
        ]

        for key in kpi_keys:
            if key in results and isinstance(results[key], (int, float)):
                kpis[key] = float(results[key])

        return kpis
