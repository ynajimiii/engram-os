"""
ENGRAM OS Benchmark Dashboard

Tracking dashboard for benchmark results:
- SummaryDashboard class
- Displays comparison table (Baseline vs ENGRAM)
- Logs metrics to YAML
- Generates reports
"""

import os
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .metrics import BenchmarkMetrics
from .baseline import BaselineComparison
from .test_cases import TestResult


def convert_numpy_types(obj: Any) -> Any:
    """
    Recursively convert numpy types to native Python types for YAML serialization.
    
    Args:
        obj: Object to convert
        
    Returns:
        Object with all numpy types converted to native Python types
    """
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    elif isinstance(obj, (np.bool_,)):
        return bool(obj)
    elif isinstance(obj, dict):
        return {k: convert_numpy_types(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [convert_numpy_types(item) for item in obj]
    return obj


@dataclass
class MetricComparison:
    """Comparison data for a single metric."""
    metric_name: str
    baseline: float
    engram: float
    delta: float
    target: float
    passed: bool
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "metric_name": self.metric_name,
            "baseline": self.baseline,
            "engram": self.engram,
            "delta": self.delta,
            "target": self.target,
            "passed": self.passed,
        }


@dataclass
class BenchmarkResults:
    """Container for all benchmark results."""
    run_id: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S"))
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    test_results: List[TestResult] = field(default_factory=list)
    metric_comparisons: List[MetricComparison] = field(default_factory=list)
    summary_stats: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "test_results": [r.to_dict() for r in self.test_results],
            "metric_comparisons": [c.to_dict() for c in self.metric_comparisons],
            "summary_stats": self.summary_stats,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BenchmarkResults":
        """Create from dictionary representation."""
        results = cls(
            run_id=data.get("run_id", ""),
            timestamp=data.get("timestamp", ""),
            summary_stats=data.get("summary_stats", {}),
        )
        
        for test_data in data.get("test_results", []):
            results.test_results.append(TestResult(
                test_name=test_data.get("test_name", ""),
                passed=test_data.get("passed", False),
                metrics=BenchmarkMetrics.from_dict(test_data.get("metrics", {})),
                details=test_data.get("details", {}),
                timestamp=test_data.get("timestamp", ""),
            ))
        
        for comp_data in data.get("metric_comparisons", []):
            results.metric_comparisons.append(MetricComparison(
                metric_name=comp_data.get("metric_name", ""),
                baseline=comp_data.get("baseline", 0.0),
                engram=comp_data.get("engram", 0.0),
                delta=comp_data.get("delta", 0.0),
                target=comp_data.get("target", 0.0),
                passed=comp_data.get("passed", False),
            ))
        
        return results


class SummaryDashboard:
    """
    Dashboard for displaying and tracking benchmark results.
    
    Features:
    - Comparison table (Baseline vs ENGRAM)
    - YAML logging
    - Report generation
    - Historical tracking
    """
    
    def __init__(self, results_dir: Optional[str] = None):
        """
        Initialize the dashboard.
        
        Args:
            results_dir: Directory to store results (default: engram/benchmarks/results)
        """
        if results_dir is None:
            # Get the directory where this module is located
            module_dir = Path(__file__).parent
            results_dir = str(module_dir / "results")
        
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        self.current_results: Optional[BenchmarkResults] = None
        self.historical_results: List[BenchmarkResults] = []
        
    def load_results(self, test_results: List[TestResult]) -> BenchmarkResults:
        """
        Load test results into the dashboard.
        
        Args:
            test_results: List of test results to display
            
        Returns:
            BenchmarkResults object
        """
        self.current_results = BenchmarkResults()
        self.current_results.test_results = test_results
        
        # Build metric comparisons from test results
        self._build_metric_comparisons()
        
        # Calculate summary statistics
        self._calculate_summary_stats()
        
        return self.current_results
    
    def _build_metric_comparisons(self) -> None:
        """Build metric comparisons from test results."""
        if self.current_results is None:
            return
        
        comparisons = []
        
        # Aggregate metrics from all tests
        metrics_map = {
            "Context Precision": [],
            "VRAM Efficiency": [],
            "Writeback Integrity": [],
            "Goal Coherence Decay": [],
            "Resume Fidelity": [],
            "Experience Compound Rate": [],
        }
        
        for result in self.current_results.test_results:
            metrics = result.metrics
            
            if metrics.context_precision > 0:
                metrics_map["Context Precision"].append(metrics.context_precision)
            if metrics.vram_efficiency > 0:
                metrics_map["VRAM Efficiency"].append(metrics.vram_efficiency)
            if metrics.writeback_integrity > 0:
                metrics_map["Writeback Integrity"].append(metrics.writeback_integrity)
            if metrics.goal_coherence_decay > 0:
                metrics_map["Goal Coherence Decay"].append(metrics.goal_coherence_decay)
            if metrics.resume_fidelity > 0:
                metrics_map["Resume Fidelity"].append(metrics.resume_fidelity)
            if metrics.experience_compound_rate > 0:
                metrics_map["Experience Compound Rate"].append(metrics.experience_compound_rate)
            
            # Also include comparisons from test results
            for comp in result.comparisons:
                comparisons.append(MetricComparison(
                    metric_name=comp.metric_name,
                    baseline=comp.baseline_score,
                    engram=comp.engram_score,
                    delta=comp.delta,
                    target=comp.target,
                    passed=comp.passed,
                ))
        
        # Create average comparisons for standard metrics
        targets = {
            "Context Precision": 0.80,
            "VRAM Efficiency": 0.80,
            "Writeback Integrity": 0.85,
            "Goal Coherence Decay": 0.50,
            "Resume Fidelity": 0.85,
            "Experience Compound Rate": 0.15,
        }
        
        baseline_defaults = {
            "Context Precision": 0.25,
            "VRAM Efficiency": 0.50,
            "Writeback Integrity": 0.40,
            "Goal Coherence Decay": 0.30,
            "Resume Fidelity": 0.00,
            "Experience Compound Rate": 0.00,
        }
        
        for metric_name, values in metrics_map.items():
            if values:
                avg_value = sum(values) / len(values)
                baseline = baseline_defaults.get(metric_name, 0.0)
                target = targets.get(metric_name, 0.5)
                
                comparisons.append(MetricComparison(
                    metric_name=metric_name,
                    baseline=baseline,
                    engram=avg_value,
                    delta=avg_value - baseline,
                    target=target,
                    passed=avg_value >= target,
                ))
        
        self.current_results.metric_comparisons = comparisons
    
    def _calculate_summary_stats(self) -> None:
        """Calculate summary statistics."""
        if self.current_results is None:
            return
        
        total_tests = len(self.current_results.test_results)
        passed_tests = sum(1 for r in self.current_results.test_results if r.passed)
        
        total_comparisons = len(self.current_results.metric_comparisons)
        passed_comparisons = sum(1 for c in self.current_results.metric_comparisons if c.passed)
        
        # Calculate average delta
        deltas = [c.delta for c in self.current_results.metric_comparisons]
        avg_delta = sum(deltas) / len(deltas) if deltas else 0.0
        
        self.current_results.summary_stats = {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "test_pass_rate": passed_tests / total_tests if total_tests > 0 else 0.0,
            "total_comparisons": total_comparisons,
            "passed_comparisons": passed_comparisons,
            "comparison_pass_rate": passed_comparisons / total_comparisons if total_comparisons > 0 else 0.0,
            "average_delta": avg_delta,
        }
    
    def display_comparison_table(self) -> str:
        """
        Display comparison table (Baseline vs ENGRAM).
        
        Returns:
            Formatted table string
        """
        if self.current_results is None:
            return "No results loaded. Run benchmarks first."
        
        lines = [
            "",
            "=" * 80,
            "ENGRAM OS Benchmark Results",
            "=" * 80,
            f"Run ID: {self.current_results.run_id}",
            f"Timestamp: {self.current_results.timestamp}",
            "",
            "METRIC COMPARISON TABLE",
            "-" * 80,
            f"{'METRIC':<25} {'BASELINE':>10} {'ENGRAM':>10} {'DELTA':>10} {'TARGET':>10} {'STATUS':>10}",
            "-" * 80,
        ]
        
        for comp in self.current_results.metric_comparisons:
            status = "PASS" if comp.passed else "FAIL"
            delta_str = f"+{comp.delta:.3f}" if comp.delta >= 0 else f"{comp.delta:.3f}"
            lines.append(
                f"{comp.metric_name:<25} {comp.baseline:>10.3f} {comp.engram:>10.3f} "
                f"{delta_str:>10} {comp.target:>10.2f} {status:>10}"
            )
        
        lines.append("-" * 80)
        
        # Add summary
        stats = self.current_results.summary_stats
        lines.append("")
        lines.append("SUMMARY")
        lines.append(f"  Tests Passed: {stats.get('passed_tests', 0)}/{stats.get('total_tests', 0)} "
                    f"({stats.get('test_pass_rate', 0):.1%})")
        lines.append(f"  Metrics Passed: {stats.get('passed_comparisons', 0)}/{stats.get('total_comparisons', 0)} "
                    f"({stats.get('comparison_pass_rate', 0):.1%})")
        lines.append(f"  Average Delta: +{stats.get('average_delta', 0):.3f}")
        lines.append("")
        
        # Add test results
        lines.append("TEST RESULTS")
        lines.append("-" * 80)
        for result in self.current_results.test_results:
            status = "[PASS]" if result.passed else "[FAIL]"
            lines.append(f"  {status} {result.test_name}")
        
        lines.append("")
        lines.append("=" * 80)
        
        return "\n".join(lines)
    
    def log_to_yaml(self, filename: Optional[str] = None) -> str:
        """
        Log results to YAML file.

        Args:
            filename: Optional filename (auto-generated if not provided)

        Returns:
            Path to the saved file
        """
        if self.current_results is None:
            raise ValueError("No results to log. Run benchmarks first.")

        if filename is None:
            filename = f"benchmark_{self.current_results.run_id}.yaml"

        filepath = self.results_dir / filename

        # Convert numpy types to native Python types before serialization
        data = convert_numpy_types(self.current_results.to_dict())

        with open(filepath, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        return str(filepath)
    
    def load_from_yaml(self, filepath: str) -> BenchmarkResults:
        """
        Load results from YAML file.
        
        Args:
            filepath: Path to YAML file
            
        Returns:
            BenchmarkResults object
        """
        with open(filepath, 'r') as f:
            data = yaml.safe_load(f)
        
        results = BenchmarkResults.from_dict(data)
        self.historical_results.append(results)
        
        return results
    
    def generate_report(self, output_path: Optional[str] = None) -> str:
        """
        Generate a comprehensive report.
        
        Args:
            output_path: Optional output path (auto-generated if not provided)
            
        Returns:
            Path to the saved report
        """
        if self.current_results is None:
            raise ValueError("No results to report. Run benchmarks first.")
        
        if output_path is None:
            output_path = self.results_dir / f"report_{self.current_results.run_id}.md"
        else:
            output_path = Path(output_path)
        
        lines = [
            "# ENGRAM OS Benchmark Report",
            "",
            f"**Run ID:** {self.current_results.run_id}",
            f"**Timestamp:** {self.current_results.timestamp}",
            "",
            "## Executive Summary",
            "",
        ]
        
        stats = self.current_results.summary_stats
        passed = stats.get('passed_tests', 0)
        total = stats.get('total_tests', 0)
        
        if passed == total:
            lines.append("**All tests passed!** ENGRAM OS meets all benchmark targets.")
        elif passed > total / 2:
            lines.append(f"**{passed}/{total} tests passed.** Some improvements needed.")
        else:
            lines.append(f"**{passed}/{total} tests passed.** Significant improvements needed.")
        
        lines.append("")
        lines.append("## Metric Comparison")
        lines.append("")
        lines.append("| Metric | Baseline | ENGRAM | Delta | Target | Status |")
        lines.append("|--------|----------|--------|-------|--------|--------|")
        
        for comp in self.current_results.metric_comparisons:
            status = "PASS" if comp.passed else "FAIL"
            delta_str = f"+{comp.delta:.3f}" if comp.delta >= 0 else f"{comp.delta:.3f}"
            lines.append(
                f"| {comp.metric_name} | {comp.baseline:.3f} | {comp.engram:.3f} | "
                f"{delta_str} | {comp.target:.2f} | {status} |"
            )
        
        lines.append("")
        lines.append("## Test Details")
        lines.append("")
        
        for result in self.current_results.test_results:
            status = "PASS" if result.passed else "FAIL"
            lines.append(f"### {result.test_name} - {status}")
            lines.append("")
            lines.append(f"**Timestamp:** {result.timestamp}")
            lines.append("")
            
            # Metrics
            lines.append("**Metrics:**")
            lines.append("")
            metrics = result.metrics
            if metrics.context_precision > 0:
                lines.append(f"- Context Precision: {metrics.context_precision:.3f}")
            if metrics.vram_efficiency > 0:
                lines.append(f"- VRAM Efficiency: {metrics.vram_efficiency:.3f}")
            if metrics.writeback_integrity > 0:
                lines.append(f"- Writeback Integrity: {metrics.writeback_integrity:.3f}")
            if metrics.goal_coherence_decay > 0:
                lines.append(f"- Goal Coherence Decay: {metrics.goal_coherence_decay:.3f}")
            if metrics.resume_fidelity > 0:
                lines.append(f"- Resume Fidelity: {metrics.resume_fidelity:.3f}")
            if metrics.experience_compound_rate > 0:
                lines.append(f"- Experience Compound Rate: {metrics.experience_compound_rate:.3f}")
            
            lines.append("")
            
            # Details
            if result.details:
                lines.append("**Details:**")
                lines.append("")
                for key, value in result.details.items():
                    if isinstance(value, list):
                        lines.append(f"- {key}: {value}")
                    else:
                        lines.append(f"- {key}: {value}")
            
            lines.append("")
        
        lines.append("## Summary Statistics")
        lines.append("")
        lines.append(f"- **Test Pass Rate:** {stats.get('test_pass_rate', 0):.1%}")
        lines.append(f"- **Metric Pass Rate:** {stats.get('comparison_pass_rate', 0):.1%}")
        lines.append(f"- **Average Delta:** +{stats.get('average_delta', 0):.3f}")
        lines.append("")
        lines.append("---")
        lines.append("*Generated by ENGRAM OS Benchmark Framework*")
        
        # Write report with UTF-8 encoding
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))
        
        return str(output_path)
    
    def get_pass_fail_summary(self) -> Dict[str, Any]:
        """
        Get pass/fail summary for all metrics.
        
        Returns:
            Dictionary with pass/fail information
        """
        if self.current_results is None:
            return {}
        
        summary = {
            "run_id": self.current_results.run_id,
            "timestamp": self.current_results.timestamp,
            "metrics": {},
            "tests": {},
            "overall_pass": True,
        }
        
        for comp in self.current_results.metric_comparisons:
            summary["metrics"][comp.metric_name] = {
                "baseline": comp.baseline,
                "engram": comp.engram,
                "delta": comp.delta,
                "target": comp.target,
                "passed": comp.passed,
            }
            if not comp.passed:
                summary["overall_pass"] = False
        
        for result in self.current_results.test_results:
            summary["tests"][result.test_name] = {
                "passed": result.passed,
                "details": result.details,
            }
            if not result.passed:
                summary["overall_pass"] = False
        
        return summary
    
    def list_historical_runs(self) -> List[str]:
        """
        List all historical result files.
        
        Returns:
            List of filenames
        """
        if not self.results_dir.exists():
            return []
        
        return sorted([f.name for f in self.results_dir.glob("benchmark_*.yaml")])
    
    def compare_runs(self, run_ids: List[str]) -> str:
        """
        Compare multiple historical runs.
        
        Args:
            run_ids: List of run IDs to compare
            
        Returns:
            Comparison table string
        """
        if len(run_ids) < 2:
            return "Need at least 2 runs to compare."
        
        lines = [
            "",
            "=" * 80,
            "Historical Run Comparison",
            "=" * 80,
            "",
        ]
        
        # Load all runs
        runs = []
        for run_id in run_ids:
            filepath = self.results_dir / f"benchmark_{run_id}.yaml"
            if filepath.exists():
                results = self.load_from_yaml(str(filepath))
                runs.append((run_id, results))
        
        if len(runs) < 2:
            return "Could not load enough runs for comparison."
        
        # Build comparison table
        lines.append(f"{'METRIC':<25} " + " ".join([f"{r[0]:>15}" for r in runs]))
        lines.append("-" * 80)
        
        # Get all metric names
        all_metrics = set()
        for _, results in runs:
            for comp in results.metric_comparisons:
                all_metrics.add(comp.metric_name)
        
        for metric in sorted(all_metrics):
            values = []
            for _, results in runs:
                found = False
                for comp in results.metric_comparisons:
                    if comp.metric_name == metric:
                        values.append(f"{comp.engram:>15.3f}")
                        found = True
                        break
                if not found:
                    values.append(" " * 15)
            
            lines.append(f"{metric:<25} " + " ".join(values))
        
        lines.append("")
        lines.append("=" * 80)
        
        return "\n".join(lines)
