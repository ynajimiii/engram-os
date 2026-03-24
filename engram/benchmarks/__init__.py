"""
ENGRAM OS Benchmarking Framework

A comprehensive benchmarking system for measuring ENGRAM OS performance
against naive baseline implementations.

This framework implements six essential metrics:
- Context Precision
- VRAM Efficiency
- Writeback Integrity
- Goal Coherence Decay Rate
- Session Resume Fidelity
- Experience Compound Rate

Usage:
    from engram.benchmarks import run_benchmark
    from engram.benchmarks.test_cases import TestContextPollution
    
    test = TestContextPollution()
    results = test.run()
"""

from .metrics import (
    context_precision,
    vram_efficiency,
    writeback_integrity,
    goal_coherence_decay,
    resume_fidelity,
    experience_compound_rate,
    BenchmarkMetrics,
)
from .baseline import (
    naive_run,
    BaselineComparison,
    compare_context_precision,
    compare_vram_efficiency,
    compare_writeback_integrity,
)
from .test_cases import (
    TestContextPollution,
    TestLongSessionDecay,
    TestSessionResume,
    TestDomainSwitch,
    TestAutonomousHorizon,
    BaseTestCase,
)
from .dashboard import (
    SummaryDashboard,
    BenchmarkResults,
    MetricComparison,
)

__version__ = "0.1.0"
__all__ = [
    # Metrics
    "context_precision",
    "vram_efficiency",
    "writeback_integrity",
    "goal_coherence_decay",
    "resume_fidelity",
    "experience_compound_rate",
    "BenchmarkMetrics",
    # Baseline
    "naive_run",
    "BaselineComparison",
    "compare_context_precision",
    "compare_vram_efficiency",
    "compare_writeback_integrity",
    # Test Cases
    "TestContextPollution",
    "TestLongSessionDecay",
    "TestSessionResume",
    "TestDomainSwitch",
    "TestAutonomousHorizon",
    "BaseTestCase",
    # Dashboard
    "SummaryDashboard",
    "BenchmarkResults",
    "MetricComparison",
]
