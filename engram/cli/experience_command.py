# engram/cli/experience_command.py
"""
`engram experience` — View and search distilled experiences.

Usage:
  engram experience list                         # List all experiences
  engram experience search "validation"          # Search experiences
  engram experience show <id>                    # Show specific experience
  engram experience stats                        # Show experience statistics
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

from engram.cli._display import (
    ok, fail, warn, info, section, header, footer, divider
)
from engram.cli._config import load_config, SESSIONS_DIR


def build_parser(subparsers) -> None:
    """Build argument parser for experience command."""
    p = subparsers.add_parser(
        "experience",
        help="View and search distilled experiences.",
    )
    
    # Subparsers for experience commands
    sub = p.add_subparsers(dest="action", metavar="<action>")
    
    # list
    list_p = sub.add_parser("list", help="List all experiences.")
    list_p.add_argument("--module", "-m", type=str, default=None,
                       help="Filter by module (coding, marketing, etc.).")
    list_p.add_argument("--limit", "-l", type=int, default=20,
                       help="Max experiences to show (default: 20).")
    list_p.set_defaults(func=_cmd_list)
    
    # search
    search_p = sub.add_parser("search", help="Search experiences.")
    search_p.add_argument("query", type=str, help="Search query.")
    search_p.add_argument("--module", "-m", type=str, default=None,
                         help="Filter by module.")
    search_p.set_defaults(func=_cmd_search)
    
    # show
    show_p = sub.add_parser("show", help="Show specific experience.")
    show_p.add_argument("id", type=str, help="Experience ID.")
    show_p.set_defaults(func=_cmd_show)
    
    # stats
    stats_p = sub.add_parser("stats", help="Show experience statistics.")
    stats_p.set_defaults(func=_cmd_stats)
    
    # Global options
    p.add_argument("--project", "-p", type=str, default=".",
                  help="Project root path.")
    p.add_argument("--json", action="store_true",
                  help="Output as JSON.")
    
    p.set_defaults(func=_cmd_list)  # Default to list


def register(subparsers) -> None:
    """Register experience command with argument parser."""
    build_parser(subparsers)


def _get_experiences_from_db(project_root: Path, module_name: str = None):
    """Load experiences from vector DB."""
    from engram.core.vector_db import VectorDB
    from engram.core.experience import Experience
    
    # Load vector DB
    db_path = project_root / "engram" / "sessions" / "vector_db.json"
    
    # For now, search session logs for experience entries
    sessions_dir = project_root / "engram" / "sessions"
    
    if not sessions_dir.exists():
        return []
    
    experiences = []
    
    # Search all session files for experience references
    for session_file in sessions_dir.glob("*.yaml"):
        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                import yaml
                data = yaml.safe_load(f) or {}
            
            # Check for experiences in session data
            # (In full implementation, would load from vector DB)
            
        except Exception:
            continue
    
    # For now, return empty list (experiences stored in vector DB)
    # This is a placeholder for the full implementation
    return experiences


def _cmd_list(args) -> int:
    """List all experiences."""
    project_root = Path(args.project).resolve()
    
    # Check for cumulative log to show task-based experiences
    cum_log_path = project_root / "engram" / "sessions" / "cumulative_log.jsonl"
    
    if args.json:
        # JSON output
        print(json.dumps({
            "experiences": [],
            "message": "Experience retrieval from vector DB not yet implemented",
        }, indent=2))
        return 0
    
    header("Distilled Experiences")
    
    if not cum_log_path.exists():
        fail("No cumulative log found", "Run some tasks first")
        return 1
    
    # Count tasks for experience estimation
    with open(cum_log_path, 'r', encoding='utf-8') as f:
        task_count = len([l for l in f.read().splitlines() if l.strip()])
    
    # Experiences distilled every 20 tasks
    expected_experiences = task_count // 20
    
    section("Status")
    ok(f"Cumulative tasks: {task_count}")
    ok(f"Expected experiences: ~{expected_experiences} (every 20 tasks)")
    
    if expected_experiences == 0:
        warn("No experiences distilled yet", "Need 20+ tasks for first experience")
        info("Experiences are distilled automatically every 20 tasks")
        return 0
    
    section("Note")
    info("Experience retrieval from vector DB is planned for future release")
    info("For now, experiences are stored internally and used automatically")
    divider()
    info(f"Run: engram session list  to see learning status")
    
    return 0


def _cmd_search(args) -> int:
    """Search experiences."""
    project_root = Path(args.project).resolve()
    query = args.query.lower()
    
    if args.json:
        print(json.dumps({
            "query": query,
            "results": [],
            "message": "Experience search not yet implemented",
        }, indent=2))
        return 0
    
    header(f"Search Experiences: '{query}'")
    
    # Placeholder for search implementation
    warn("Experience search is planned for future release")
    info("Experiences are currently used automatically during task execution")
    
    return 0


def _cmd_show(args) -> int:
    """Show specific experience."""
    project_root = Path(args.project).resolve()
    exp_id = args.id
    
    if args.json:
        print(json.dumps({
            "id": exp_id,
            "message": "Experience retrieval not yet implemented",
        }, indent=2))
        return 0
    
    header(f"Experience: {exp_id}")
    
    # Placeholder for show implementation
    fail("Experience not found", "Experience retrieval not yet implemented")
    
    return 1


def _cmd_stats(args) -> int:
    """Show experience statistics."""
    project_root = Path(args.project).resolve()
    
    # Check cumulative log
    cum_log_path = project_root / "engram" / "sessions" / "cumulative_log.jsonl"
    
    if not cum_log_path.exists():
        if args.json:
            print(json.dumps({
                "total_tasks": 0,
                "expected_experiences": 0,
            }, indent=2))
        else:
            fail("No cumulative log found", "Run some tasks first")
        return 1
    
    # Count tasks
    with open(cum_log_path, 'r', encoding='utf-8') as f:
        task_count = len([l for l in f.read().splitlines() if l.strip()])
    
    # Calculate stats
    expected_experiences = task_count // 20
    next_experience_in = 20 - (task_count % 20)
    
    if args.json:
        print(json.dumps({
            "total_tasks": task_count,
            "expected_experiences": expected_experiences,
            "next_experience_in": next_experience_in,
        }, indent=2))
        return 0
    
    header("Experience Statistics")
    
    section("Overview")
    ok(f"Total tasks:           {task_count}")
    ok(f"Expected experiences:  ~{expected_experiences}")
    ok(f"Next experience in:    {next_experience_in} tasks")
    
    section("Distillation Schedule")
    print("    Experiences are distilled every 20 tasks")
    print("    Each experience analyzes task patterns and extracts insights")
    print("    Insights are stored as vector embeddings for retrieval")
    
    section("Usage")
    info("Experiences are used automatically during task execution")
    info("Run: engram learn --history  to see learning events")
    
    return 0
