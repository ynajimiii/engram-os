# engram/cli/rubric_command.py
"""
`engram rubric` — View and compare scoring rubrics.

Usage:
  engram rubric show coding                     # Show current rubric
  engram rubric history coding                  # Show evolution history
  engram rubric compare coding v1 v2            # Compare versions
  engram rubric stats coding                    # Show calibration stats
"""

import sys
import json
import argparse
import re
from pathlib import Path
from datetime import datetime

from engram.cli._display import (
    ok, fail, warn, info, section, header, footer, divider
)
from engram.cli._config import load_config


def build_parser(subparsers) -> None:
    """Build argument parser for rubric command."""
    p = subparsers.add_parser(
        "rubric",
        help="View and compare scoring rubrics.",
    )
    
    # Subparsers for rubric commands
    sub = p.add_subparsers(dest="action", metavar="<action>")
    
    # show
    show_p = sub.add_parser("show", help="Show current rubric.")
    show_p.add_argument("module", type=str, help="Module name (coding, marketing, etc.).")
    show_p.set_defaults(func=_cmd_show)
    
    # history
    history_p = sub.add_parser("history", help="Show rubric evolution history.")
    history_p.add_argument("module", type=str, help="Module name.")
    history_p.set_defaults(func=_cmd_history)
    
    # compare
    compare_p = sub.add_parser("compare", help="Compare rubric versions.")
    compare_p.add_argument("module", type=str, help="Module name.")
    compare_p.add_argument("v1", type=str, help="First version (e.g., v1).")
    compare_p.add_argument("v2", type=str, help="Second version (e.g., v2).")
    compare_p.set_defaults(func=_cmd_compare)
    
    # stats
    stats_p = sub.add_parser("stats", help="Show rubric calibration stats.")
    stats_p.add_argument("module", type=str, help="Module name.")
    stats_p.set_defaults(func=_cmd_stats)
    
    # Global options
    p.add_argument("--project", "-p", type=str, default=".",
                  help="Project root path.")
    p.add_argument("--json", action="store_true",
                  help="Output as JSON.")
    
    p.set_defaults(func=_cmd_show)  # Default to show


def register(subparsers) -> None:
    """Register rubric command with argument parser."""
    build_parser(subparsers)


def _get_rubric_path(project_root: Path, module_name: str) -> Path:
    """Get path to module rubric file."""
    return project_root / "engram" / "modules" / module_name / "scorer_rubric.md"


def _get_rubric_backups(project_root: Path, module_name: str) -> list:
    """Get list of rubric backup files."""
    modules_dir = project_root / "engram" / "modules" / module_name
    
    if not modules_dir.exists():
        return []
    
    backups = list(modules_dir.glob("scorer_rubric.v*.bak"))
    return sorted(backups, key=lambda f: f.stat().st_mtime)


def _parse_rubric_version(content: str) -> str:
    """Extract version from rubric content."""
    match = re.search(r'# v(\d+)', content)
    return f"v{match.group(1)}" if match else "unknown"


def _cmd_show(args) -> int:
    """Show current rubric."""
    project_root = Path(args.project).resolve()
    module_name = args.module
    
    rubric_path = _get_rubric_path(project_root, module_name)
    
    if not rubric_path.exists():
        fail(f"Rubric not found for module: {module_name}")
        info(f"Expected: {rubric_path}")
        return 1
    
    with open(rubric_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    version = _parse_rubric_version(content)
    
    if args.json:
        print(json.dumps({
            "module": module_name,
            "version": version,
            "content": content,
        }, indent=2))
        return 0
    
    header(f"Scoring Rubric — {module_name}")
    
    info(f"Version: {version}")
    info(f"File: {rubric_path.relative_to(project_root)}")
    
    section("Content")
    print(content)
    
    return 0


def _cmd_history(args) -> int:
    """Show rubric evolution history."""
    project_root = Path(args.project).resolve()
    module_name = args.module
    
    backups = _get_rubric_backups(project_root, module_name)
    current_path = _get_rubric_path(project_root, module_name)
    
    if args.json:
        history = []
        
        # Current version
        if current_path.exists():
            with open(current_path, 'r', encoding='utf-8') as f:
                content = f.read()
            history.append({
                "version": _parse_rubric_version(content),
                "file": str(current_path),
                "date": datetime.fromtimestamp(current_path.stat().st_mtime).isoformat(),
                "current": True,
            })
        
        # Backup versions
        for bak in backups:
            with open(bak, 'r', encoding='utf-8') as f:
                content = f.read()
            history.append({
                "version": _parse_rubric_version(content),
                "file": str(bak),
                "date": datetime.fromtimestamp(bak.stat().st_mtime).isoformat(),
                "current": False,
            })
        
        print(json.dumps({
            "module": module_name,
            "versions": history,
        }, indent=2))
        return 0
    
    header(f"Rubric Evolution — {module_name}")
    
    if not backups and not current_path.exists():
        fail("No rubric versions found")
        return 1
    
    section("Versions")
    
    # Show current version
    if current_path.exists():
        with open(current_path, 'r', encoding='utf-8') as f:
            content = f.read()
        version = _parse_rubric_version(content)
        mtime = datetime.fromtimestamp(current_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        
        print(f"\n  {version} (current)")
        print(f"    Date: {mtime}")
        print(f"    File: {current_path.name}")
        
        # Show first comment line
        first_line = content.split('\n')[0]
        if first_line.startswith('#'):
            print(f"    Note: {first_line[1:].strip()}")
    
    # Show backup versions
    if backups:
        print(f"\n  Backups ({len(backups)}):")
        
        for bak in backups[-5:]:  # Show last 5 backups
            with open(bak, 'r', encoding='utf-8') as f:
                content = f.read()
            version = _parse_rubric_version(content)
            mtime = datetime.fromtimestamp(bak.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            
            print(f"\n    {version}")
            print(f"      Date: {mtime}")
            print(f"      File: {bak.name}")
    
    divider()
    info("Rubrics evolve every 50 tasks based on calibration data")
    info("Run: engram rubric compare <module> v1 v2  to compare versions")
    
    return 0


def _cmd_compare(args) -> int:
    """Compare two rubric versions."""
    project_root = Path(args.project).resolve()
    module_name = args.module
    v1_name = args.v1
    v2_name = args.v2
    
    # Find the backup files
    backups = _get_rubric_backups(project_root, module_name)
    
    v1_content = None
    v2_content = None
    
    # Search for versions
    for bak in backups:
        with open(bak, 'r', encoding='utf-8') as f:
            content = f.read()
        version = _parse_rubric_version(content)
        
        if version == v1_name:
            v1_content = content
        if version == v2_name:
            v2_content = content
    
    # Check current version
    current_path = _get_rubric_path(project_root, module_name)
    if current_path.exists():
        with open(current_path, 'r', encoding='utf-8') as f:
            content = f.read()
        version = _parse_rubric_version(content)
        
        if version == v1_name:
            v1_content = content
        if version == v2_name:
            v2_content = content
    
    if not v1_content or not v2_content:
        fail("Could not find specified versions")
        info(f"Available: Run 'engram rubric history {module_name}'")
        return 1
    
    if args.json:
        print(json.dumps({
            "module": module_name,
            "v1": {"version": v1_name, "content": v1_content},
            "v2": {"version": v2_name, "content": v2_content},
        }, indent=2))
        return 0
    
    header(f"Rubric Comparison — {module_name}")
    
    print(f"\nComparing {v1_name} vs {v2_name}\n")
    
    # Simple diff (line by line)
    v1_lines = v1_content.split('\n')
    v2_lines = v2_content.split('\n')
    
    section(f"{v1_name}")
    for i, line in enumerate(v1_lines[:20]):  # Show first 20 lines
        print(f"  {i+1:3d}. {line[:70]}")
    
    print("\n" + "="*70 + "\n")
    
    section(f"{v2_name}")
    for i, line in enumerate(v2_lines[:20]):
        print(f"  {i+1:3d}. {line[:70]}")
    
    # Show differences
    section("Differences")
    
    added = 0
    removed = 0
    
    for line in v2_lines:
        if line not in v1_content:
            added += 1
    
    for line in v1_lines:
        if line not in v2_content:
            removed += 1
    
    print(f"    Lines added:   +{added}")
    print(f"    Lines removed: -{removed}")
    
    divider()
    info("Rubric evolution occurs every 50 tasks based on calibration data")
    
    return 0


def _cmd_stats(args) -> int:
    """Show rubric calibration stats."""
    project_root = Path(args.project).resolve()
    module_name = args.module
    
    # Load calibration log
    cal_log_path = project_root / "engram" / "sessions" / f"scorer_calibration_{module_name}.jsonl"
    
    if not cal_log_path.exists():
        fail(f"No calibration data for module: {module_name}")
        info("Calibration log created after first scored task")
        return 1
    
    # Load and analyze
    from engram.core.scorer_calibration import calibration_stats
    
    stats = calibration_stats(str(cal_log_path), module_name)
    
    if args.json:
        print(json.dumps(stats, indent=2))
        return 0
    
    header(f"Calibration Stats — {module_name}")
    
    section("Overview")
    ok(f"Total entries:        {stats['total_entries']}")
    ok(f"With ground truth:    {stats['with_ground_truth']}")
    ok(f"Human corrections:    {stats['human_corrections']}")
    
    section("Bias Analysis")
    print(f"    Mean error:         {stats['mean_error']:+.4f}")
    print(f"    Mean absolute err:  {stats['mean_abs_error']:.4f}")
    print(f"    Bias direction:     {stats['bias_direction']}")
    
    if stats['bias_direction'] == 'pessimistic':
        info("LLM judge scores too low — rubric may need relaxation")
    elif stats['bias_direction'] == 'optimistic':
        info("LLM judge scores too high — rubric may need tightening")
    else:
        ok("Calibration looks good")
    
    if stats['task_type_errors']:
        section("Per Task-Type Errors")
        for task_type, error in sorted(stats['task_type_errors'].items(), key=lambda x: abs(x[1]), reverse=True):
            direction = "pessimistic" if error > 0 else "optimistic"
            print(f"    {task_type:20s}: {error:+.3f} ({direction})")
    
    divider()
    info("Rubric evolves every 50 tasks to correct for observed bias")
    
    return 0
