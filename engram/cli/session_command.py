"""
ENGRAM OS CLI - Session Command

Manages multiple project sessions — list, resume, delete, export history.
Lets users switch between projects cleanly.

Usage:
    engram session list
    engram session resume my-auth-service
    engram session history my-auth-service
    engram session delete my-auth-service
    engram session export my-auth-service --format markdown
"""

import sys
import argparse
import yaml
from pathlib import Path
from datetime import datetime

from engram.cli._display import (
    ok, fail, warn, info, section, header, footer, divider
)
from engram.cli._config import load_config, SESSIONS_DIR


def _get_session_dirs():
    """Get all possible session directories."""
    dirs = [SESSIONS_DIR]  # Global ~/.engram/sessions
    
    # Also check local engram/sessions
    local_sessions = Path(__file__).parent.parent / "sessions"
    if local_sessions.exists():
        dirs.append(local_sessions)
    
    return dirs


def _find_sessions():
    """Find all session files from all directories."""
    sessions = []
    for session_dir in _get_session_dirs():
        if session_dir.exists():
            sessions.extend(session_dir.glob("*.yaml"))
    return sorted(sessions, key=lambda x: x.stat().st_mtime, reverse=True)


def session_list() -> int:
    """List all sessions."""
    sessions = _find_sessions()
    header("Sessions")
    if not sessions:
        warn("No sessions found", "Run: engram init")
        return 0

    # Show learning status
    try:
        from engram.core.embedder import embedding_info
        emb = embedding_info()
        section("Learning Status")
        ok(f"Embeddings: {emb['model']} ({emb['source']})")
        
        # Check cumulative log from first session
        if sessions:
            cum_log_path = sessions[0].parent / "cumulative_log.jsonl"
            if cum_log_path.exists():
                with open(cum_log_path) as f:
                    entries = [l for l in f.read().splitlines() if l.strip()]
                ok(f"Cumulative tasks: {len(entries)}")
                
                tasks_since = len(entries) % 10
                next_in = 10 - tasks_since if tasks_since < 10 else 0
                if next_in == 0:
                    ok(f"Next learning: READY (trigger point)")
                else:
                    ok(f"Next learning: in {next_in} tasks")
            else:
                info("Cumulative log: not yet created")
    except Exception:
        pass  # Silently skip if embedding check fails

    print()
    print(
        f"  {'NAME':<25} {'MODULE':<12}"
        f" {'TASKS':>6}  {'LAST ACTIVE'}"
    )
    divider()

    for i, sf in enumerate(sessions):
        try:
            with open(sf) as f:
                data = yaml.safe_load(f) or {}
            name   = data.get("project", {}).get("name", sf.stem)[:24]
            module = data.get("project", {}).get(
                "module",
                data.get("use_case", "?")
            )[:11]
            tasks  = len(data.get("session_log", []))
            mtime  = datetime.fromtimestamp(
                sf.stat().st_mtime
            ).strftime("%Y-%m-%d %H:%M")
            suffix = "  ← current" if i == 0 else ""
            print(
                f"  {name:<25} {module:<12}"
                f" {tasks:>6}  {mtime}{suffix}"
            )
        except Exception:
            info(f"  {sf.stem} (unreadable)")

    print()
    info(
        f"{len(sessions)} session(s) | "
        "Run: engram session resume <name>"
    )
    print()
    return 0


def session_resume(name: str) -> int:
    """Resume a session by name."""
    all_sessions = _find_sessions()
    matches = [s for s in all_sessions if s.stem.startswith(name)]
    if not matches:
        fail(f"No session matching: {name}")
        fail("Run: engram session list  to see all sessions")
        return 1
    sp = sorted(
        matches,
        key=lambda x: x.stat().st_mtime, reverse=True
    )[0]
    ok(f"Resuming session: {sp.name}")
    info(f"Run: engram run --session {sp}  to continue")
    return 0


def session_history(name: str) -> int:
    """Show task history for a session."""
    all_sessions = _find_sessions()
    matches = [s for s in all_sessions if s.stem.startswith(name)]
    if not matches:
        fail(f"No session matching: {name}")
        return 1
    sp = matches[0]
    with open(sp) as f:
        data = yaml.safe_load(f) or {}
    log = data.get("session_log", [])

    header(f"Session History: {name}")
    
    # Show learning status
    try:
        from engram.core.embedder import embedding_info
        emb = embedding_info()
        section("Learning Status")
        ok(f"Embeddings: {emb['model']} ({emb['source']})")
        
        # Check cumulative log
        cum_log_path = sp.parent / "cumulative_log.jsonl"
        if cum_log_path.exists():
            with open(cum_log_path) as f:
                entries = [l for l in f.read().splitlines() if l.strip()]
            ok(f"Cumulative tasks: {len(entries)}")
            
            tasks_since = len(entries) % 10
            next_in = 10 - tasks_since if tasks_since < 10 else 0
            if next_in == 0:
                ok(f"Next learning: READY (trigger point)")
            else:
                ok(f"Next learning: in {next_in} tasks")
        else:
            info("Cumulative log: not yet created")
    except Exception:
        pass  # Silently skip if embedding check fails
    
    print()
    print(f"  {'#':>3}  {'TIMESTAMP':<20}  TASK")
    divider()

    for i, entry in enumerate(log, 1):
        ts_raw = entry.get("ts", "")
        try:
            ts = datetime.fromisoformat(ts_raw).strftime(
                "%Y-%m-%d %H:%M"
            )
        except Exception:
            ts = ts_raw[:16]
        task = str(
            entry.get("task") or entry.get("event") or ""
        )[:50]
        print(f"  {i:>3}  {ts:<20}  {task}")

    print()
    modules_touched = set(
        e.get("routing", {}).get("module", "")
        for e in log
        if isinstance(e.get("routing"), dict)
    )
    info(f"{len(log)} tasks | "
         f"{len(modules_touched)} modules touched")
    print()
    return 0


def session_delete(name: str) -> int:
    """Delete a session by name."""
    matches = list(SESSIONS_DIR.glob(f"{name}*.yaml"))
    if not matches:
        fail(f"No session matching: {name}")
        return 1
    sp = matches[0]
    confirm = input(
        f"  Delete {sp.name}? [y/N]: "
    ).strip().lower()
    if confirm == "y":
        sp.unlink()
        ok(f"Deleted: {sp.name}")
    else:
        info("Cancelled")
    return 0


def session_export(name: str, fmt: str = "markdown") -> int:
    """Export a session as a report."""
    all_sessions = _find_sessions()
    matches = [s for s in all_sessions if s.stem.startswith(name)]
    if not matches:
        fail(f"No session matching: {name}")
        return 1
    sp = matches[0]
    with open(sp) as f:
        data = yaml.safe_load(f) or {}

    project = data.get("project", {})
    log     = data.get("session_log", [])
    mods    = data.get("modules", {})
    convs   = data.get("conventions", {})

    # Get learning status
    learning_info = {}
    try:
        from engram.core.embedder import embedding_info
        emb = embedding_info()
        learning_info["embeddings"] = emb
        
        # Check cumulative log
        cum_log_path = sp.parent / "cumulative_log.jsonl"
        if cum_log_path.exists():
            with open(cum_log_path) as f:
                entries = [l for l in f.read().splitlines() if l.strip()]
            learning_info["cumulative_tasks"] = len(entries)
            
            tasks_since = len(entries) % 10
            next_in = 10 - tasks_since if tasks_since < 10 else 0
            learning_info["next_learning_in"] = next_in
        else:
            learning_info["cumulative_tasks"] = 0
            learning_info["next_learning_in"] = 0
    except Exception:
        pass  # Silently skip if embedding check fails

    if fmt == "markdown":
        out = _export_markdown(name, project, log, mods, convs, learning_info)
        out_path = Path.cwd() / f"engram_report_{name}.md"
        out_path.write_text(out, encoding="utf-8")
        ok(f"Exported: {out_path}")
    return 0


def session_learning(module_name: str = None, show_trend: bool = False) -> int:
    """Show learning history and quality trends."""
    from engram.core.learning_history import LearningHistory, QualityTrend
    from engram.cli._config import SESSIONS_DIR
    
    header("Learning History & Trends")
    
    # Show learning history
    section("Patches Applied")
    try:
        history = LearningHistory(str(SESSIONS_DIR))
        summary = history.get_summary()
        
        ok(f"Total patches: {summary['total_patches']}")
        ok(f"Modules improved: {summary['modules_improved']}")
        
        if summary['average_expected_improvement'] > 0:
            ok(f"Avg expected improvement: {summary['average_expected_improvement']:.3f}")
        if summary['average_actual_improvement'] > 0:
            ok(f"Avg actual improvement: {summary['average_actual_improvement']:.3f}")
        
        # Show recent patches
        patches = history.get_all_patches()[-5:] if summary['total_patches'] > 0 else []
        if patches:
            print()
            print(f"  {'TIMESTAMP':<22} {'MODULE':<15} {'SECTION':<15} {'EXPECTED':>8}")
            divider()
            for patch in patches:
                if module_name and patch.module_name != module_name:
                    continue
                ts = patch.timestamp[:19].replace('T', ' ')
                print(f"  {ts:<22} {patch.module_name:<15} {patch.section:<15} {patch.expected_improvement:>8.3f}")
    except Exception as e:
        warn(f"Learning history unavailable: {e}")
    
    print()
    
    # Show quality trend if requested
    if show_trend:
        section("Quality Trend")
        try:
            trend = QualityTrend(str(SESSIONS_DIR))
            trend_data = trend.calculate_trend(window_size=10)
            summary = trend.get_summary()
            
            ok(f"Total snapshots: {summary['total_snapshots']}")
            ok(f"Overall average quality: {summary['average_quality']:.3f}")
            
            if trend_data['trend'] != 'insufficient_data':
                trend_icon = "📈" if trend_data['trend'] == 'improving' else "📉" if trend_data['trend'] == 'declining' else "➡️"
                ok(f"Trend: {trend_icon} {trend_data['trend'].upper()}")
                ok(f"Change: {trend_data['change']:+.4f} ({trend_data['percent_change']:+.2f}%)")
                ok(f"First avg: {trend_data['first_average']:.3f} → Last avg: {trend_data['last_average']:.3f}")
            else:
                info("Insufficient data for trend analysis (need 2+ snapshots)")
        except Exception as e:
            warn(f"Quality trend unavailable: {e}")
    
    print()
    info("Run: engram session learning --trend  to see quality trends")
    print()
    
    return 0


def _export_markdown(
    name, project, log, modules, conventions, learning_info=None
) -> str:
    """Export session to markdown format."""
    lines = [
        f"# ENGRAM Session Report — {name}",
        f"",
        f"**Generated:** {datetime.utcnow().isoformat()}Z",
        f"**Module:** {project.get('module', '?')}",
        f"**Path:** {project.get('path', '?')}",
        f"",
    ]
    
    # Add learning status section
    if learning_info and learning_info.get("embeddings"):
        emb = learning_info["embeddings"]
        lines += [
            f"## Learning Status",
            f"",
            f"- **Embeddings:** {emb.get('model', 'N/A')} ({emb.get('source', 'N/A')})",
            f"- **Dimension:** {emb.get('dimension', 'N/A')}",
        ]
        
        if learning_info.get("cumulative_tasks") is not None:
            lines += [
                f"- **Cumulative tasks:** {learning_info['cumulative_tasks']}",
            ]
            next_in = learning_info.get("next_learning_in", 0)
            if next_in == 0:
                lines.append(f"- **Next learning:** READY (trigger point)")
            else:
                lines.append(f"- **Next learning:** in {next_in} tasks")
        lines += [""]
    
    # Add learning history summary if available
    try:
        from engram.core.learning_history import LearningHistory, QualityTrend
        from engram.cli._config import SESSIONS_DIR
        
        history = LearningHistory(str(SESSIONS_DIR))
        hist_summary = history.get_summary()
        
        if hist_summary['total_patches'] > 0:
            lines += [
                f"## Learning History",
                f"",
                f"- **Total patches applied:** {hist_summary['total_patches']}",
                f"- **Modules improved:** {hist_summary['modules_improved']}",
                f"- **Avg expected improvement:** {hist_summary['average_expected_improvement']:.3f}",
            ]
            if hist_summary['average_actual_improvement'] > 0:
                lines.append(f"- **Avg actual improvement:** {hist_summary['average_actual_improvement']:.3f}")
            lines += [""]
        
        # Add quality trend
        trend = QualityTrend(str(SESSIONS_DIR))
        trend_summary = trend.get_summary()
        
        if trend_summary['total_snapshots'] > 0:
            lines += [
                f"## Quality Trend",
                f"",
                f"- **Overall average quality:** {trend_summary['average_quality']:.3f}",
                f"- **Quality range:** {trend_summary['min_quality']:.3f} - {trend_summary['max_quality']:.3f}",
            ]
            if trend_summary.get('trend'):
                lines.append(f"- **Trend:** {trend_summary['trend']}")
            if trend_summary.get('trend_change'):
                lines.append(f"- **Change:** {trend_summary['trend_change']:+.4f}")
            lines += [""]
    except Exception:
        pass  # Silently skip if learning history unavailable
    
    lines += [
        f"## Module Status",
        f"",
    ]
    for mod_name, mod_data in modules.items():
        if isinstance(mod_data, dict):
            status = mod_data.get("status", "?")
            lines.append(f"- **{mod_name}**: {status}")
    lines += ["", "## Conventions Learned", ""]
    for key, val in conventions.items():
        if val:
            lines.append(f"- **{key}**: {val}")
    lines += ["", "## Task History", ""]
    for i, entry in enumerate(log, 1):
        ts = entry.get("ts", "")[:16]
        task = entry.get("task") or entry.get("event", "")
        lines.append(f"{i}. `{ts}` — {task}")
    return "\n".join(lines)


def register(subparsers) -> None:
    """Register session command with argument parser."""
    p = subparsers.add_parser(
        "session",
        help="Manage ENGRAM sessions"
    )
    sub = p.add_subparsers(dest="session_cmd")

    sub.add_parser("list", help="List all sessions")
    r = sub.add_parser("resume", help="Resume a session")
    r.add_argument("name")
    h = sub.add_parser("history", help="Show task history")
    h.add_argument("name")
    d = sub.add_parser("delete", help="Delete a session")
    d.add_argument("name")
    e = sub.add_parser("export", help="Export session as report")
    e.add_argument("name")
    e.add_argument("--format", default="markdown",
                   choices=["markdown"])
    
    # Add learning subcommand
    learn = sub.add_parser("learning", help="Show learning history and trends")
    learn.add_argument("--module", help="Filter by module name")
    learn.add_argument("--trend", action="store_true",
                       help="Show quality trend analysis")

    def dispatch(args):
        cmd = args.session_cmd
        if cmd == "list":    return session_list()
        if cmd == "resume":  return session_resume(args.name)
        if cmd == "history": return session_history(args.name)
        if cmd == "delete":  return session_delete(args.name)
        if cmd == "export":
            return session_export(args.name, args.format)
        if cmd == "learning":
            return session_learning(getattr(args, 'module', None), 
                                   getattr(args, 'trend', False))
        p.print_help()
        return 1

    p.set_defaults(func=lambda args: sys.exit(dispatch(args)))
