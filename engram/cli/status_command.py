"""
ENGRAM OS CLI - Status Command

Shows live state of the current session — what ENGRAM knows,
what's in memory, recent tasks, conventions learned.

Usage:
    engram status
    engram status --session ./sessions/proj.yaml
    engram status --json
"""

import sys
import json as json_lib
import argparse
import yaml
from pathlib import Path
from datetime import datetime

from engram.cli._display import (
    ok, fail, warn, info, section, header, footer, divider
)
from engram.cli._config import load_config, SESSIONS_DIR


STATUS_ICONS = {
    "done":        "✓",
    "in_progress": "●",
    "pending":     "○",
    "blocked":     "✗",
}


def status(
    session_path: str | None = None,
    as_json: bool = False
) -> int:
    """
    Show current session state and memory.

    Args:
        session_path: Path to session YAML file
        as_json: Output as JSON

    Returns:
        Exit code (0 on success, 1 on failure)
    """
    config = load_config()

    if session_path:
        sp = Path(session_path)
    else:
        sessions = sorted(
            SESSIONS_DIR.glob("*.yaml"),
            key=lambda x: x.stat().st_mtime, reverse=True
        )
        if not sessions:
            fail("No sessions found", "Run: engram init")
            return 1
        sp = sessions[0]

    if not sp.exists():
        fail(f"Session not found: {sp}")
        return 1

    # Load session YAML directly
    with open(sp) as f:
        data = yaml.safe_load(f) or {}

    if as_json:
        print(json_lib.dumps(data, indent=2, default=str))
        return 0

    header("Session Status")

    # PROJECT INFO
    project = data.get("project", {})
    ok(f"Project:  {project.get('name', sp.stem)}")
    ok(f"Module:   {project.get('module', data.get('use_case', '?'))}")
    ok(f"Session:  {sp.name}")
    if project.get("path"):
        ok(f"Path:     {project['path']}")

    # MEMORY INFO
    section("Memory (last boot)")
    # Note: We can't access DB here without booting, so show session info
    session_log = data.get("session_log", [])
    ok(f"Tasks logged: {len(session_log)}")

    # ACTIVE TASK
    active = data.get("active_task", {})
    if active and active.get("objective"):
        section("Active Task")
        ok(f"Module:    {active.get('module', '?')}")
        ok(f"Objective: {active.get('objective', '?')}")
        if active.get("constraints"):
            for c in active["constraints"]:
                info(f"  constraint: {c}")

    # MODULES STATUS
    modules = data.get("modules", {})
    if modules:
        section("Modules")
        for mod_name, mod_data in modules.items():
            if not isinstance(mod_data, dict):
                continue
            status_val = mod_data.get("status", "pending")
            icon = STATUS_ICONS.get(status_val, "○")
            blocked = ""
            if status_val == "blocked" and mod_data.get("blocked_by"):
                blocked = f" (depends: {', '.join(mod_data['blocked_by'])})"
            print(
                f"    {icon} {mod_name:<22}"
                f" {status_val}{blocked}"
            )

    # CONVENTIONS
    conventions = data.get("conventions", {})
    if conventions:
        section("Conventions Learned")
        for key, val in conventions.items():
            if val and key != "learned":
                ok(f"{key}: {str(val)[:60]}")
        if conventions.get("learned"):
            ok(f"learned: {str(conventions['learned'])[:60]}")

    # LEARNING STATUS
    section("Learning Status")
    try:
        from engram.core.embedder import embedding_info
        emb_info = embedding_info()
        ok(f"Embeddings: {emb_info['model']} ({emb_info['source']})")
        
        # Check cumulative log
        cum_log_path = sp.parent / "cumulative_log.jsonl"
        if cum_log_path.exists():
            with open(cum_log_path) as f:
                entries = [l for l in f.read().splitlines() if l.strip()]
            ok(f"Cumulative tasks: {len(entries)}")
            
            # Calculate learning progress
            tasks_since_learning = len(entries) % 10
            next_learning = 10 - tasks_since_learning if tasks_since_learning < 10 else 0
            ok(f"Next learning: in {next_learning} tasks")
        else:
            warn("Cumulative log: not found")
    except Exception:
        warn("Learning status: unavailable")

    # SESSION LOG — last 5 entries
    if session_log:
        section("Recent Tasks (last 5)")
        for entry in session_log[-5:]:
            ts_raw = entry.get("ts", "")
            try:
                ts = datetime.fromisoformat(
                    ts_raw
                ).strftime("%Y-%m-%d %H:%M")
            except Exception:
                ts = ts_raw[:16]
            task = str(entry.get("task", ""))[:45]
            ev = entry.get("event", "")
            if ev:
                info(f"  {ev:<45} {ts}")
            else:
                info(f"  ✓ {task:<43} {ts}")

    print()
    divider()
    info(f"Total tasks logged: {len(session_log)}")
    print()
    return 0


def register(subparsers) -> None:
    """Register status command with argument parser."""
    p = subparsers.add_parser(
        "status",
        help="Show current session state and memory"
    )
    p.add_argument("--session", help="Path to session YAML")
    p.add_argument("--json", action="store_true",
                   help="Output as JSON")
    p.set_defaults(func=lambda args: sys.exit(status(
        session_path=args.session,
        as_json=args.json
    )))
