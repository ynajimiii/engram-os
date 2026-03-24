"""
ENGRAM OS CLI - Benchmark Command

Runs the ENGRAM benchmark suite against the current hardware
and produces a shareable result card.

Usage:
    engram benchmark
    engram benchmark --quick
    engram benchmark --share
"""

import sys
import argparse
from datetime import date

from engram.cli._display import (
    ok, fail, warn, info, section, header, footer,
    divider, ProgressBar
)
from engram.cli._config import load_config


def benchmark(quick: bool = False, share: bool = False) -> int:
    """
    Run the ENGRAM benchmark suite.

    Args:
        quick: Run 3 tests instead of 5
        share: Show shareable results

    Returns:
        Exit code (0 if all pass, 1 otherwise)
    """
    config = load_config()
    header("Benchmark Suite")

    # HARDWARE INFO
    try:
        import pynvml
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        gpu_name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(gpu_name, bytes):
            gpu_name = gpu_name.decode("utf-8")
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        vram_gb = mem.total // (1024**3)
    except Exception:
        gpu_name = "Unknown GPU"
        vram_gb  = 0

    model = config.get("model", "qwen2.5:14b")
    run_date = date.today().isoformat()

    ok(f"Model:  {model}")
    ok(f"GPU:    {gpu_name} ({vram_gb} GB)")
    ok(f"Date:   {run_date}")
    print()
    info(f"Running {'3' if quick else '5'} tests...")
    divider()

    # RUN BENCHMARKS
    try:
        from engram.benchmarks.benchmark_suite import (
            run_all_benchmarks
        )
        results = run_all_benchmarks(quick=quick)
    except ImportError:
        fail("Benchmark suite not found")
        fail("Expected: engram/benchmarks/benchmark_suite.py")
        return 1
    except Exception as e:
        fail(f"Benchmark failed: {e}")
        return 1

    # DISPLAY RESULTS
    METRIC_LABELS = {
        "context_precision":   ("Context Precision",  0.80),
        "goal_coherence":      ("Goal Coherence",     0.50),
        "resume_fidelity":     ("Resume Fidelity",    0.85),
        "domain_isolation":    ("Domain Isolation",   1.00),
        "experience_compound": ("Experience Rate",    0.15),
    }

    passed = 0
    total  = 0
    result_lines = []

    for key, (label, target) in METRIC_LABELS.items():
        if key not in results:
            continue
        total += 1
        score = results[key]
        passed_test = score >= target
        if passed_test:
            passed += 1
            ok(f"{label:<22} {score:.3f}  PASS")
        else:
            fail(f"{label:<22} {score:.3f}  FAIL (target: {target})")
        result_lines.append(
            f"{label}: {score:.3f} {'✓' if passed_test else '✗'}"
        )

    divider()
    pct = int(passed / max(1, total) * 100)
    if passed == total:
        ok(f"OVERALL: {passed}/{total} PASS ({pct}%)")
    else:
        fail(f"OVERALL: {passed}/{total} PASS ({pct}%)")

    if share or passed == total:
        print()
        divider()
        print(f"  ENGRAM OS Benchmark Results")
        print(f"  Model: {model} | "
              f"GPU: {gpu_name} | VRAM: {vram_gb}GB")
        for line in result_lines:
            print(f"  {line}")
        print(f"  Overall: {passed}/{total} PASS")
        print(f"  github.com/ynajimiii/engram-os")
        divider()

    return 0 if passed == total else 1


def register(subparsers) -> None:
    """Register benchmark command with argument parser."""
    p = subparsers.add_parser(
        "benchmark",
        help="Run the ENGRAM benchmark suite"
    )
    p.add_argument(
        "--quick", action="store_true",
        help="Run 3 tests instead of 5"
    )
    p.add_argument(
        "--share", action="store_true",
        help="Show shareable results even on partial pass"
    )
    p.set_defaults(func=lambda args: sys.exit(benchmark(
        quick=args.quick,
        share=args.share
    )))
