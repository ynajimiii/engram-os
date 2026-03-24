# engram/cli/score_command.py
"""
`engram score` — inject human quality corrections.

Usage:
  engram score --session abc123 --task 3 --correct 0.95
  engram score --session abc123 --task 7 --correct 0.40
  engram score --module coding --stats

Human corrections are weighted 3x in bias correction calculation.
They anchor the calibration curve toward ground truth.
"""

import sys
import logging
import argparse
from pathlib import Path


def build_parser(subparsers) -> None:
    p = subparsers.add_parser(
        "score",
        help="Inject human quality corrections or view calibration stats.",
    )
    p.add_argument("--session", "-s", type=str, default=None,
                   help="Session ID containing the task to correct.")
    p.add_argument("--task", "-t", type=int, default=None,
                   help="Task index within the session (1-based).")
    p.add_argument("--correct", "-c", type=float, default=None,
                   help="Your quality score for this task (0.0–1.0).")
    p.add_argument("--module", "-m", type=str, default="coding",
                   help="Module name for stats view.")
    p.add_argument("--stats", action="store_true",
                   help="Show calibration statistics for the module.")
    p.add_argument("--project", "-p", type=str, default=".",
                   help="Project root path.")
    p.set_defaults(func=run_score_command)


def register(subparsers) -> None:
    """Register score command with argument parser."""
    build_parser(subparsers)


def run_score_command(args) -> int:
    project_root = Path(args.project).resolve()

    # Stats mode
    if args.stats:
        return _show_stats(args.module, project_root)

    # Correction mode
    if not all([args.session, args.task is not None, args.correct is not None]):
        print(
            "error: --session, --task, and --correct are all required\n"
            "  example: engram score --session abc123 --task 3 --correct 0.95",
            file=sys.stderr,
        )
        return 1

    if not 0.0 <= args.correct <= 1.0:
        print(
            f"error: --correct must be between 0.0 and 1.0, got {args.correct}",
            file=sys.stderr,
        )
        return 1

    return _inject_correction(args, project_root)


def _inject_correction(args, project_root: Path) -> int:
    """Read the session, find the task, inject correction."""
    import yaml
    from engram.core.scorer_calibration import inject_human_correction

    # Load session YAML
    session_files = list(
        (project_root / "engram" / "sessions").glob(f"{args.session}*.yaml")
    )
    if not session_files:
        print(f"error: session not found: {args.session}", file=sys.stderr)
        return 1

    session_path = session_files[0]
    with open(session_path, encoding="utf-8") as f:
        session_data = yaml.safe_load(f) or {}

    session_log = session_data.get("session_log", [])
    task_index  = args.task - 1   # convert to 0-based

    if task_index < 0 or task_index >= len(session_log):
        print(
            f"error: task {args.task} not found. "
            f"Session has {len(session_log)} tasks.",
            file=sys.stderr,
        )
        return 1

    task_entry   = session_log[task_index]
    task_text    = task_entry.get("task", "unknown")
    llm_score    = task_entry.get("quality_score", 0.0)
    module_name  = session_data.get("module", "coding")
    task_id      = f"{args.session}:{args.task}"

    # Determine calibration log path
    cal_log_path = str(
        project_root / "engram" / "sessions"
        / f"scorer_calibration_{module_name}.jsonl"
    )

    # Inject correction
    inject_human_correction(
        log_path=cal_log_path,
        module_name=module_name,
        task_id=task_id,
        llm_judge_score=llm_score,
        human_score=args.correct,
    )

    print(f"[ENGRAM] Human correction recorded:")
    print(f"  Session:     {args.session}")
    print(f"  Task {args.task:3d}:    {task_text[:60]}")
    print(f"  LLM score:   {llm_score:.2f}")
    print(f"  Your score:  {args.correct:.2f}")
    print(f"  Difference:  {args.correct - llm_score:+.2f}")
    print(f"  Weight:      3x (high-value calibration signal)")
    print(f"  Module:      {module_name}")
    return 0


def _show_stats(module_name: str, project_root: Path) -> int:
    """Display calibration statistics for a module."""
    from engram.core.scorer_calibration import calibration_stats

    cal_log_path = str(
        project_root / "engram" / "sessions"
        / f"scorer_calibration_{module_name}.jsonl"
    )

    stats = calibration_stats(cal_log_path, module_name)

    print(f"\nCalibration Stats — {module_name} module")
    print("─" * 45)
    print(f"  Total entries:       {stats['total_entries']}")
    print(f"  With ground truth:   {stats['with_ground_truth']}")
    print(f"  Human corrections:   {stats['human_corrections']}")
    print(f"  Mean error:          {stats['mean_error']:+.4f}")
    print(f"  Mean absolute error: {stats['mean_abs_error']:.4f}")
    print(f"  Bias direction:      {stats['bias_direction']}")

    if stats['task_type_errors']:
        print(f"\n  Per task-type errors:")
        for tt, err in sorted(
            stats['task_type_errors'].items(),
            key=lambda x: abs(x[1]), reverse=True
        ):
            direction = "pessimistic" if err > 0 else "optimistic"
            print(f"    {tt:20s}: {err:+.3f} ({direction})")
    print()
    return 0
