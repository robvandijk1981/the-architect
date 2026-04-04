"""
Workforce forecasting module.
Uses exponential smoothing and linear projection (no heavy ML dependencies for v1).
Prophet and ARIMA can be added when historical data is available.
"""

import math
from typing import List, Dict, Any, Optional

class WorkforceForecaster:
    """Lightweight forecasting without requiring statsmodels/prophet.
    Uses Holt's linear trend method (double exponential smoothing).
    """

    @staticmethod
    def holt_linear_forecast(
        historical_values: List[float],
        periods_ahead: int = 5,
        alpha: float = 0.3,
        beta: float = 0.1,
    ) -> Dict[str, Any]:
        """
        Holt's linear trend method (double exponential smoothing).
        Good for data with trend but no seasonality.
        """
        if len(historical_values) < 2:
            return {"error": "Need at least 2 historical values"}

        level = historical_values[0]
        trend = historical_values[1] - historical_values[0]

        fitted = [level]

        for i in range(1, len(historical_values)):
            new_level = alpha * historical_values[i] + (1 - alpha) * (level + trend)
            new_trend = beta * (new_level - level) + (1 - beta) * trend
            level = new_level
            trend = new_trend
            fitted.append(level)

        forecast = []
        for h in range(1, periods_ahead + 1):
            forecast.append(round(level + h * trend, 2))

        residuals = [historical_values[i] - fitted[i] for i in range(len(historical_values))]
        rmse = math.sqrt(sum(r**2 for r in residuals) / len(residuals))

        forecast_with_ci = []
        for h in range(1, periods_ahead + 1):
            point = level + h * trend
            ci_width = 1.645 * rmse * math.sqrt(h)
            forecast_with_ci.append({
                "period": h,
                "forecast": round(point, 2),
                "ci_lower_90": round(point - ci_width, 2),
                "ci_upper_90": round(point + ci_width, 2),
            })

        return {
            "method": "Holt's Linear Trend (Double Exponential Smoothing)",
            "parameters": {"alpha": alpha, "beta": beta},
            "fitted_values": [round(f, 2) for f in fitted],
            "forecast": forecast_with_ci,
            "rmse": round(rmse, 2),
            "trend_direction": "increasing" if trend > 0 else "decreasing",
            "trend_per_period": round(trend, 2),
        }

    @staticmethod
    def cohort_retirement_forecast(
        age_distribution: Dict[str, int],
        retirement_age: int = 67,
        forecast_years: int = 10,
        annual_early_retirement_pct: float = 2.0,
    ) -> Dict[str, Any]:
        """
        Forecast retirements based on age cohorts.
        """
        cohorts = {}
        for age_range, count in age_distribution.items():
            parts = age_range.replace("+", "").split("-")
            mid_age = int(parts[0]) if len(parts) == 1 else (int(parts[0]) + int(parts[1])) / 2
            cohorts[age_range] = {"count": count, "mid_age": mid_age}

        yearly_retirements = []
        remaining = sum(c["count"] for c in cohorts.values())

        for year in range(1, forecast_years + 1):
            retirements_this_year = 0

            for age_range, data in cohorts.items():
                current_age = data["mid_age"] + year

                if current_age >= retirement_age:
                    retirements_this_year += data["count"]
                    data["count"] = 0
                else:
                    early = int(data["count"] * annual_early_retirement_pct / 100)
                    retirements_this_year += early
                    data["count"] -= early

            remaining -= retirements_this_year
            yearly_retirements.append({
                "year": year,
                "retirements": retirements_this_year,
                "remaining": max(0, remaining),
                "cumulative_loss_pct": round((1 - remaining / sum(c["count"] for c in {k: {"count": v} for k, v in age_distribution.items()}.values())) * 100, 1) if sum(age_distribution.values()) > 0 else 0
            })

        total_at_risk = sum(
            count for age_range, count in age_distribution.items()
            if int(age_range.replace("+", "").split("-")[0]) >= (retirement_age - forecast_years)
        )

        return {
            "method": "Cohort-based retirement forecast",
            "retirement_age": retirement_age,
            "early_retirement_rate": annual_early_retirement_pct,
            "total_current_workforce": sum(age_distribution.values()),
            "at_risk_within_period": total_at_risk,
            "yearly_forecast": yearly_retirements,
            "total_expected_retirements": sum(y["retirements"] for y in yearly_retirements),
            "replacement_demand": f"{sum(y['retirements'] for y in yearly_retirements)} replacements needed over {forecast_years} years",
        }

    @staticmethod
    def linear_projection(
        current_value: float,
        annual_growth_rate: float,
        years: int = 5,
        uncertainty_band_pct: float = 20.0,
    ) -> List[Dict[str, Any]]:
        """Simple compound growth projection with uncertainty band."""
        projection = []
        for y in range(1, years + 1):
            projected = current_value * ((1 + annual_growth_rate / 100) ** y)
            band = projected * uncertainty_band_pct / 100
            projection.append({
                "year": y,
                "projected": round(projected, 2),
                "lower": round(projected - band, 2),
                "upper": round(projected + band, 2),
            })
        return projection
