#!/usr/bin/env python3
"""
ENGRAM OS Benchmark Runner

Main runner script for executing all benchmarks and generating reports.

Usage:
    python -m engram.benchmarks.run_benchmarks
    python -m engram.benchmarks.run_benchmarks --test ContextPollution
    python -m engram.benchmarks.run_benchmarks --output-dir ./results
    python -m engram.benchmarks.run_benchmarks --format json
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from engram.benchmarks.metrics import BenchmarkMetrics
from engram.benchmarks.test_cases import (
    TestContextPollution,
    TestLongSessionDecay,
    TestSessionResume,
    TestDomainSwitch,
    TestAutonomousHorizon,
    BaseTestCase,
    TestResult,
    run_all_tests,
    get_test_summary,
)
from engram.benchmarks.dashboard import SummaryDashboard, BenchmarkResults


# Available test cases
AVAILABLE_TESTS = {
    "ContextPollution": TestContextPollution,
    "LongSessionDecay": TestLongSessionDecay,
    "SessionResume": TestSessionResume,
    "DomainSwitch": TestDomainSwitch,
    "AutonomousHorizon": TestAutonomousHorizon,
}


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="ENGRAM OS Benchmark Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all benchmarks
  python -m engram.benchmarks.run_benchmarks

  # Run specific test
  python -m engram.benchmarks.run_benchmarks --test ContextPollution

  # Run multiple tests
  python -m engram.benchmarks.run_benchmarks --test ContextPollution --test SessionResume

  # Specify output directory
  python -m engram.benchmarks.run_benchmarks --output-dir ./my_results

  # Output as JSON
  python -m engram.benchmarks.run_benchmarks --format json

  # Quiet mode (only show summary)
  python -m engram.benchmarks.run_benchmarks --quiet
        """,
    )
    
    parser.add_argument(
        "--test", "-t",
        action="append",
        choices=list(AVAILABLE_TESTS.keys()),
        help="Run specific test(s). Can be specified multiple times.",
    )
    
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default=None,
        help="Output directory for results (default: engram/benchmarks/results)",
    )
    
    parser.add_argument(
        "--format", "-f",
        type=str,
        choices=["text", "json", "yaml", "markdown"],
        default="text",
        help="Output format (default: text)",
    )
    
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Quiet mode - only show summary",
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose mode - show detailed output",
    )
    
    parser.add_argument(
        "--list-tests",
        action="store_true",
        help="List available tests and exit",
    )
    
    return parser.parse_args()


def list_tests() -> None:
    """List all available tests."""
    print("\nAvailable Benchmark Tests")
    print("=" * 60)
    
    tests = [
        ("ContextPollution", "Tests semantic eviction loads only what's needed"),
        ("LongSessionDecay", "Tests goal coherence holds over 10+ tasks"),
        ("SessionResume", "Tests scratch note enables true project continuity"),
        ("DomainSwitch", "Tests multi-agent isolation prevents context bleed"),
        ("AutonomousHorizon", "Tests long-horizon loop runs from goal to completion"),
    ]
    
    for name, description in tests:
        print(f"\n{name}")
        print(f"  {description}")
    
    print("\n" + "=" * 60)
    print("Run with: python -m engram.benchmarks.run_benchmarks --test <NAME>")


def run_specific_tests(test_names: List[str], verbose: bool = False) -> List[TestResult]:
    """
    Run specific tests by name.
    
    Args:
        test_names: List of test names to run
        verbose: Show detailed output
        
    Returns:
        List of test results
    """
    results = []
    
    for name in test_names:
        if name not in AVAILABLE_TESTS:
            print(f"Unknown test: {name}")
            continue
        
        test_class = AVAILABLE_TESTS[name]
        test = test_class()
        
        if not verbose:
            print(f"Running: {test.name}...", end=" ", flush=True)
        
        try:
            result = test.run()
            results.append(result)
            
            status = "PASS" if result.passed else "FAIL"
            if verbose:
                print(f"\n{test.name}: {status}")
                print(f"  {result.metrics.summary()}")
                if result.details:
                    print(f"  Details: {result.details}")
            else:
                print(status)
                
        except Exception as e:
            if verbose:
                print(f"\n{test.name}: ERROR - {e}")
            else:
                print(f"ERROR: {e}")
            
            results.append(TestResult(
                test_name=test.name,
                passed=False,
                metrics=BenchmarkMetrics(),
                details={"error": str(e)},
            ))
    
    return results


def output_results(results: List[TestResult], format_type: str,
                   output_dir: Optional[str] = None) -> str:
    """
    Output results in specified format.
    
    Args:
        results: List of test results
        format_type: Output format (text, json, yaml, markdown)
        output_dir: Optional output directory
        
    Returns:
        Output string or file path
    """
    dashboard = SummaryDashboard(results_dir=output_dir)
    dashboard.load_results(results)
    
    if format_type == "json":
        from .dashboard import convert_numpy_types
        output = json.dumps(convert_numpy_types(dashboard.current_results.to_dict()), indent=2)
        if output_dir:
            filepath = Path(output_dir) / f"benchmark_{dashboard.current_results.run_id}.json"
            with open(filepath, 'w') as f:
                f.write(output)
            return str(filepath)
        return output
    
    elif format_type == "yaml":
        filepath = dashboard.log_to_yaml()
        return filepath
    
    elif format_type == "markdown":
        filepath = dashboard.generate_report()
        return filepath
    
    else:  # text
        return dashboard.display_comparison_table()


def print_summary(results: List[TestResult]) -> None:
    """Print summary of results."""
    print("\n" + get_test_summary(results))


def main() -> int:
    """Main entry point."""
    args = parse_args()
    
    # List tests if requested
    if args.list_tests:
        list_tests()
        return 0
    
    # Determine which tests to run
    if args.test:
        test_names = args.test
    else:
        test_names = list(AVAILABLE_TESTS.keys())
    
    if not args.quiet:
        print("\n" + "=" * 60)
        print("ENGRAM OS Benchmark Suite")
        print("=" * 60)
        print(f"Running {len(test_names)} test(s)...")
        print("-" * 60)
    
    # Run tests
    results = run_specific_tests(test_names, verbose=args.verbose)
    
    if not args.quiet:
        print("-" * 60)
    
    # Print summary
    print_summary(results)
    
    # Output results
    if args.format != "text" or args.output_dir:
        output_path = output_results(
            results,
            args.format,
            args.output_dir,
        )
        if not args.quiet:
            print(f"\nResults saved to: {output_path}")
    
    # Return exit code based on results
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    
    if passed == total:
        print("\n✓ All tests passed!")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
