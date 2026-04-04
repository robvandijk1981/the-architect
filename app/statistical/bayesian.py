"""
Bayesian updating for benchmark parameters.
Starts with priors from Manus research (CBS/UWV data),
updates with each new observation from clients.
"""

import math
from typing import Dict, Tuple, Optional, List, Any

class BayesianBenchmarkUpdater:
    """
    Normal-Normal conjugate model for continuous KPIs.
    Prior: N(mu_0, sigma_0^2)
    Likelihood: N(mu, sigma^2)
    Posterior: N(mu_n, sigma_n^2) where:
        mu_n = (mu_0/sigma_0^2 + n*x_bar/sigma^2) / (1/sigma_0^2 + n/sigma^2)
        sigma_n^2 = 1 / (1/sigma_0^2 + n/sigma^2)
    """

    @staticmethod
    def create_prior(mean: float, std: float, n_observations: int = 0) -> Dict[str, float]:
        """Create a prior distribution from benchmark data."""
        return {
            "mean": mean,
            "std": std,
            "variance": std ** 2,
            "precision": 1 / (std ** 2) if std > 0 else 0,
            "n_observations": n_observations,
            "type": "normal"
        }

    @staticmethod
    def update(
        prior: Dict[str, float],
        new_observations: List[float],
        observation_reliability: float = 1.0,
        known_variance: Optional[float] = None,
    ) -> Dict[str, float]:
        """
        Update prior with new observations.

        observation_reliability:
        - 1.0 = validated consultancy data (full weight)
        - 0.7 = Deep Dive self-reported (good but unverified)
        - 0.3 = Quick Scan self-reported (rough estimate)
        """
        if not new_observations:
            return prior

        n = len(new_observations) * observation_reliability
        x_bar = sum(new_observations) / len(new_observations)

        if known_variance is None:
            if len(new_observations) > 1:
                obs_var = sum((x - x_bar) ** 2 for x in new_observations) / (len(new_observations) - 1)
            else:
                obs_var = prior["variance"]
        else:
            obs_var = known_variance

        prior_precision = prior["precision"]
        obs_precision = n / obs_var if obs_var > 0 else 0

        posterior_precision = prior_precision + obs_precision
        posterior_variance = 1 / posterior_precision if posterior_precision > 0 else prior["variance"]
        posterior_mean = (prior["mean"] * prior_precision + x_bar * obs_precision) / posterior_precision if posterior_precision > 0 else prior["mean"]
        posterior_std = math.sqrt(posterior_variance)

        return {
            "mean": round(posterior_mean, 4),
            "std": round(posterior_std, 4),
            "variance": round(posterior_variance, 4),
            "precision": round(posterior_precision, 4),
            "n_observations": prior["n_observations"] + len(new_observations),
            "type": "normal",
            "prior_mean": prior["mean"],
            "prior_std": prior["std"],
            "shift": round(posterior_mean - prior["mean"], 4),
            "uncertainty_reduction_pct": round((1 - posterior_std / prior["std"]) * 100, 1) if prior["std"] > 0 else 0,
        }

    @staticmethod
    def credible_interval(posterior: Dict[str, float], level: float = 0.80) -> Tuple[float, float]:
        """Calculate credible interval from posterior."""
        try:
            from scipy import stats as scipy_stats
            alpha = (1 - level) / 2
            z = scipy_stats.norm.ppf(1 - alpha)
        except ImportError:
            z = 1.282 if level == 0.80 else 1.96
        lower = posterior["mean"] - z * posterior["std"]
        upper = posterior["mean"] + z * posterior["std"]
        return (round(lower, 2), round(upper, 2))

    @staticmethod
    def detect_anomaly(value: float, posterior: Dict[str, float], threshold_std: float = 2.0) -> Dict[str, Any]:
        """Flag if an observed value is anomalous relative to the current posterior."""
        z_score = (value - posterior["mean"]) / posterior["std"] if posterior["std"] > 0 else 0
        is_anomaly = abs(z_score) > threshold_std

        return {
            "value": value,
            "expected_mean": posterior["mean"],
            "expected_std": posterior["std"],
            "z_score": round(z_score, 2),
            "is_anomaly": is_anomaly,
            "direction": "above" if z_score > 0 else "below",
            "message": f"Value {value} is {abs(z_score):.1f} standard deviations {'above' if z_score > 0 else 'below'} expected mean of {posterior['mean']:.1f}. {'VERIFY DATA.' if is_anomaly else 'Within normal range.'}"
        }
