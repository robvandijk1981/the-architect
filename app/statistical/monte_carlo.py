"""
MonteCarloEngine — uncertainty quantification via parametric simulation.
Runs calculation N times with randomly sampled input parameters.
"""

import numpy as np
from typing import Dict, Any, Callable, Optional
from scipy import stats


class MonteCarloEngine:
    """
    Monte Carlo simulation for workforce calculations.
    Samples parameter distributions and returns percentile confidence intervals.
    """
    
    @staticmethod
    def default_distributions_for_sector(sector_benchmarks: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create default parameter distributions (as dicts with 'type', 'mean', 'std') 
        based on sector benchmarks.
        """
        return {
            "time_to_fill_days": {
                "type": "lognormal",
                "mean": sector_benchmarks.get("time_to_fill_days", 60),
                "std": sector_benchmarks.get("time_to_fill_days", 60) * 0.3,  # 30% variation
            },
            "cost_per_hire": {
                "type": "normal",
                "mean": sector_benchmarks.get("cost_per_hire", 4000),
                "std": sector_benchmarks.get("cost_per_hire", 4000) * 0.25,
            },
            "cost_per_vacancy_month": {
                "type": "normal",
                "mean": sector_benchmarks.get("cost_per_vacancy_month", 5500),
                "std": sector_benchmarks.get("cost_per_vacancy_month", 5500) * 0.2,
            },
            "turnover_rate": {
                "type": "normal",
                "mean": sector_benchmarks.get("turnover_rate", 12),
                "std": sector_benchmarks.get("turnover_rate", 12) * 0.2,
            },
            "absenteeism_rate": {
                "type": "normal",
                "mean": sector_benchmarks.get("absenteeism_rate", 5),
                "std": sector_benchmarks.get("absenteeism_rate", 5) * 0.25,
            },
            "burnout_prevalence": {
                "type": "normal",
                "mean": sector_benchmarks.get("burnout_prevalence", 15),
                "std": sector_benchmarks.get("burnout_prevalence", 15) * 0.3,
            },
            "avg_labour_cost_fte": {
                "type": "normal",
                "mean": sector_benchmarks.get("avg_labour_cost_fte", 50000),
                "std": sector_benchmarks.get("avg_labour_cost_fte", 50000) * 0.15,
            },
        }
    
    @staticmethod
    def _sample_parameter(distribution: Dict[str, Any]) -> float:
        """Sample a single value from a distribution dict."""
        dist_type = distribution.get("type", "normal")
        mean = distribution.get("mean", 0)
        std = distribution.get("std", 0)
        
        if std <= 0:
            return mean
        
        if dist_type == "lognormal":
            # Lognormal: good for positive skewed data (times, costs)
            # Convert mean/std to lognormal parameters
            cv = std / mean if mean > 0 else 0.3  # Coefficient of variation
            sigma = np.sqrt(np.log(1 + cv**2))
            mu = np.log(mean) - sigma**2 / 2
            return np.random.lognormal(mu, sigma)
        elif dist_type == "normal":
            return np.random.normal(mean, std)
        else:
            return mean
    
    @staticmethod
    def simulate(
        calculation_func: Callable,
        base_params: Dict[str, Any],
        distributions: Dict[str, Dict[str, Any]],
        output_key: str = "total_annual_cost",
        iterations: int = 1000,
    ) -> Dict[str, Any]:
        """
        Run Monte Carlo simulation.
        
        Args:
            calculation_func: Function to call (e.g., CalculationEngine.vacancy_cost)
            base_params: Base parameters to pass to calculation_func
            distributions: Dict mapping param names to distribution specs
            output_key: Which output key to extract for percentile calculation
            iterations: Number of simulation runs
        
        Returns:
            Dict with mean, std, percentiles (5, 25, 50, 75, 95)
        """
        results = []
        
        for _ in range(iterations):
            # Sample parameters
            sampled_params = base_params.copy()
            for param_name, distribution in distributions.items():
                if param_name in sampled_params:
                    sampled_params[param_name] = MonteCarloEngine._sample_parameter(distribution)
            
            # Run calculation
            try:
                output = calculation_func(**sampled_params)
                if output_key in output:
                    results.append(output[output_key])
            except Exception:
                # Skip failed iterations
                continue
        
        if not results:
            return {
                "mean_estimate": 0,
                "std_deviation": 0,
                "percentile_5": 0,
                "percentile_25": 0,
                "percentile_50": 0,
                "percentile_75": 0,
                "percentile_95": 0,
                "iterations": 0,
            }
        
        results_array = np.array(results)
        
        return {
            "mean_estimate": float(np.mean(results_array)),
            "std_deviation": float(np.std(results_array)),
            "percentile_5": float(np.percentile(results_array, 5)),
            "percentile_25": float(np.percentile(results_array, 25)),
            "percentile_50": float(np.percentile(results_array, 50)),
            "percentile_75": float(np.percentile(results_array, 75)),
            "percentile_95": float(np.percentile(results_array, 95)),
            "iterations": len(results),
        }

