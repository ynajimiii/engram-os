# engram/cli/learn_command.py
"""
`engram learn` — Manual learning cycle trigger and history view.

Usage:
  engram learn --module coding              # Trigger learning cycle
  engram learn --history                    # Show learning history
  engram learn --show-patches               # Show proposed patches
  engram learn --trigger                    # Force trigger (even if not at 10 tasks)
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
    """Build argument parser for learn command."""
    p = subparsers.add_parser(
        "learn",
        help="Trigger learning cycle or view learning history.",
    )
    
    # Action group (mutually exclusive)
    action_group = p.add_mutually_exclusive_group()
    
    action_group.add_argument(
        "--module", "-m",
        type=str,
        default=None,
        help="Module to run learning cycle for (e.g., coding, marketing)."
    )
    
    action_group.add_argument(
        "--history",
        action="store_true",
        help="Show learning history from cumulative_log.jsonl."
    )
    
    action_group.add_argument(
        "--show-patches",
        action="store_true",
        help="Show proposed prompt patches."
    )
    
    action_group.add_argument(
        "--trigger",
        action="store_true",
        help="Force trigger learning cycle (ignore 10-task threshold)."
    )
    
    # Options
    p.add_argument(
        "--project", "-p",
        type=str,
        default=".",
        help="Project root path."
    )
    
    p.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON."
    )
    
    p.set_defaults(func=run_learn_command)


def register(subparsers) -> None:
    """Register learn command with argument parser."""
    build_parser(subparsers)


def run_learn_command(args) -> int:
    """Main entry point for learn command."""
    project_root = Path(args.project).resolve()
    
    # Determine action
    if args.history:
        return _show_history(project_root, args.json)
    elif args.show_patches:
        return _show_patches(project_root, args.json)
    elif args.module or args.trigger:
        module_name = args.module or "coding"
        return _trigger_learning(module_name, project_root, args.trigger, args.json)
    else:
        # Default: show learning status
        return _show_status(project_root, args.json)


def _show_status(project_root: Path, as_json: bool = False) -> int:
    """Show current learning status."""
    from engram.core.embedder import embedding_info
    
    config = load_config()
    module_name = config.get("default_module", "coding")
    
    # Get cumulative log
    cum_log_path = project_root / "engram" / "sessions" / "cumulative_log.jsonl"
    
    task_count = 0
    if cum_log_path.exists():
        with open(cum_log_path, 'r', encoding='utf-8') as f:
            task_count = len([l for l in f.read().splitlines() if l.strip()])
    
    tasks_since = task_count % 10
    next_in = 10 - tasks_since if tasks_since < 10 else 0
    
    if as_json:
        output = {
            "module": module_name,
            "total_tasks": task_count,
            "tasks_since_learning": tasks_since,
            "next_learning_in": next_in,
            "ready": next_in == 0,
        }
        print(json.dumps(output, indent=2))
        return 0
    
    if not as_json:
        header("Learning Status")
    
    # Embedding info
    try:
        emb = embedding_info()
        ok(f"Embeddings: {emb['model']} ({emb['source']})")
    except Exception:
        info("Embeddings: local")
    
    # Task count
    ok(f"Cumulative tasks: {task_count}")
    
    # Next learning
    if next_in == 0:
        ok(f"Next learning: READY (trigger point reached)")
        info("Run: engram learn --module coding  to trigger")
    else:
        ok(f"Next learning: in {next_in} tasks")
    
    # Learning cycle config
    section("Configuration")
    print(f"    Trigger every:     10 tasks")
    print(f"    Tasks to analyze:  20")
    print(f"    Min improvement:   0.05")
    
    return 0


def _show_history(project_root: Path, as_json: bool = False) -> int:
    """Show learning history from cumulative log."""
    cum_log_path = project_root / "engram" / "sessions" / "cumulative_log.jsonl"
    
    if not cum_log_path.exists():
        fail("No learning history found", "Run some tasks first")
        return 1
    
    with open(cum_log_path, 'r', encoding='utf-8') as f:
        entries = [json.loads(l) for l in f.read().splitlines() if l.strip()]
    
    if not entries:
        warn("Learning history is empty")
        return 0
    
    # Filter to learning events (every 10 tasks)
    learning_events = [
        e for i, e in enumerate(entries)
        if (i + 1) % 10 == 0
    ]
    
    if as_json:
        print(json.dumps({
            "total_events": len(learning_events),
            "events": learning_events[-10:]  # Last 10
        }, indent=2, default=str))
        return 0
    
    header("Learning History")
    
    if not learning_events:
        info("No learning events yet (learning triggers every 10 tasks)")
        return 0
    
    section(f"Learning Events ({len(learning_events)} total)")
    
    for i, event in enumerate(learning_events[-10:], 1):
        ts = event.get("ts", "?")
        task = event.get("task", "?")[:50]
        score = event.get("quality_score", 0)
        
        print(f"\n{i}. [{ts}] Task: {task}...")
        print(f"   Quality: {score:.2f}")
    
    divider()
    info(f"Showing last {len(learning_events[-10:])} of {len(learning_events)} events")
    
    return 0


def _show_patches(project_root: Path, as_json: bool = False) -> int:
    """Show proposed prompt patches from learning history."""
    # Check for patch backup files
    modules_dir = project_root / "engram" / "modules"
    
    if not modules_dir.exists():
        fail("Modules directory not found")
        return 1
    
    # Find all .bak files (prompt backups from learning)
    bak_files = list(modules_dir.rglob("*.bak"))
    
    if not bak_files:
        warn("No prompt patches found", "Learning cycle hasn't proposed patches yet")
        return 0
    
    if as_json:
        patches = []
        for bak in bak_files:
            patches.append({
                "file": str(bak),
                "module": bak.parent.name,
                "created": datetime.fromtimestamp(bak.stat().st_mtime).isoformat(),
            })
        print(json.dumps({"patches": patches}, indent=2))
        return 0
    
    header("Prompt Patches")
    
    section(f"Backup Files ({len(bak_files)} found)")
    
    for bak in bak_files[-10:]:  # Show last 10
        module = bak.parent.name
        mtime = datetime.fromtimestamp(bak.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        size = bak.stat().st_size
        
        print(f"\n  Module: {module}")
        print(f"  File:   {bak.name}")
        print(f"  Date:   {mtime}")
        print(f"  Size:   {size} bytes")
        
        # Show first few lines
        try:
            with open(bak, 'r', encoding='utf-8') as f:
                first_lines = [f.readline().strip() for _ in range(3)]
            print(f"  First:  {' | '.join(first_lines)}")
        except Exception:
            pass
    
    divider()
    info("Patches are created when learning cycle improves prompts")
    info("Run: engram learn --module <name> --trigger  to manually trigger")
    
    return 0


def _trigger_learning(
    module_name: str,
    project_root: Path,
    force: bool = False,
    as_json: bool = False
) -> int:
    """Trigger learning cycle for a module."""
    from engram.core.learner import learning_cycle
    from engram.core.llm import BaseLLM, OllamaProvider
    
    config = load_config()
    
    # Check task count
    cum_log_path = project_root / "engram" / "sessions" / "cumulative_log.jsonl"
    task_count = 0
    
    if cum_log_path.exists():
        with open(cum_log_path, 'r', encoding='utf-8') as f:
            task_count = len([l for l in f.read().splitlines() if l.strip()])
    
    # Check if at trigger point
    if not force and task_count % 10 != 0:
        next_in = 10 - (task_count % 10)
        warn(
            f"Not at learning trigger point ({task_count} tasks, need multiple of 10)",
            f"Run: engram learn --trigger  to force"
        )
        if as_json:
            print(json.dumps({
                "status": "not_ready",
                "current_tasks": task_count,
                "next_trigger_in": next_in,
            }))
        return 1
    
    if not as_json:
        header(f"Learning Cycle — {module_name}")
        info(f"Analyzing {min(task_count, 20)} recent tasks...")
    
    # Load session log
    sessions_dir = project_root / "engram" / "sessions"
    sessions = sorted(sessions_dir.glob("*.yaml"), key=lambda f: f.stat().st_mtime, reverse=True)
    
    if not sessions:
        fail("No sessions found", "Run some tasks first")
        return 1
    
    # Load recent session log
    session_log = []
    with open(sessions[0], 'r', encoding='utf-8') as f:
        data = json.load(f)
        session_log = data.get("session_log", [])
    
    if len(session_log) < 3:
        fail("Not enough tasks for learning (need at least 3)")
        return 1
    
    # Create LLM for learning
    try:
        llm = BaseLLM(provider=OllamaProvider(
            model=config.get('model', 'qwen3:30b-a3b-q4_K_M'),
            base_url=config.get('ollama_url', 'http://localhost:11434')
        ))
        
        def llm_call(prompt, model=None):
            from engram.core.llm import Message, MessageRole
            response = llm.complete([
                Message(role=MessageRole.USER, content=prompt)
            ])
            return response.content if hasattr(response, 'content') else str(response)
        
    except Exception as e:
        fail(f"Failed to initialize LLM: {e}")
        return 1
    
    # Load current prompt
    modules_dir = project_root / "engram" / "modules"
    prompt_path = modules_dir / module_name / "agent_system_prompt.md"
    
    if not prompt_path.exists():
        fail(f"Module prompt not found: {prompt_path}")
        return 1
    
    with open(prompt_path, 'r', encoding='utf-8') as f:
        current_prompt = f.read()
    
    # Run learning cycle
    if not as_json:
        divider()
        info("Running learning cycle...")
    
    try:
        improved, patch = learning_cycle(
            module_name=module_name,
            session_log=session_log[-20:],  # Last 20 tasks
            current_prompt=current_prompt,
            llm_call=llm_call,
            n_recent=10,
            n_evaluate=3,
            min_improvement=0.05,
        )
        
        if improved and patch:
            if not as_json:
                ok(f"Learning cycle successful!")
                section("Patch Details")
                print(f"    Module:     {patch.module_name}")
                print(f"    Section:    {patch.section}")
                print(f"    Expected:   +{patch.expected_improvement:.2f} improvement")
                divider()
                info("Patch applied automatically to module prompt")
            else:
                print(json.dumps({
                    "status": "improved",
                    "module": patch.module_name,
                    "section": patch.section,
                    "expected_improvement": patch.expected_improvement,
                }, indent=2))
            return 0
        else:
            if not as_json:
                warn("No improvement found", "Current prompt is already optimal")
            else:
                print(json.dumps({
                    "status": "no_improvement",
                    "message": "Current prompt is already optimal",
                }, indent=2))
            return 0
            
    except Exception as e:
        fail(f"Learning cycle failed: {e}")
        if as_json:
            print(json.dumps({
                "status": "error",
                "error": str(e),
            }, indent=2))
        return 1
