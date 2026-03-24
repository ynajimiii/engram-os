"""
ENGRAM OS CLI - Run Command

Main goal execution entry point.
Auto-detects session for current directory, loads module,
and runs agent_turn() in a loop until goal is complete or user exits.

Usage:
    engram run --goal "implement JWT auth"
    engram run --goal "write launch copy" --module marketing
    engram run --session ./sessions/proj.yaml --goal "..."
    engram run --interactive   (REPL mode)
"""

import sys
import time
import argparse
import yaml
from pathlib import Path

from engram.cli._display import (
    ok, fail, warn, info, section, header, footer,
    divider, Spinner
)
from engram.cli._config import load_config, SESSIONS_DIR, _resolve_session


def run(
    goal: str | None = None,
    session_path: str | None = None,
    module_name: str | None = None,
    interactive: bool = False
) -> int:
    """
    Execute a goal using the ENGRAM agent.

    Args:
        goal: What to accomplish
        session_path: Path to session YAML file
        module_name: Module to use
        interactive: Start interactive REPL mode

    Returns:
        Exit code (0 on success, 1 on failure)
    """
    config = load_config()

    # AUTO-DETECT SESSION using _resolve_session()
    sp = _resolve_session(
        session_arg=session_path,
        module=module_name or config.get("default_module", "coding"),
    )
    
    # Track if session was auto-selected
    session_was_auto = session_path is None
    
    if sp is None:
        # No session found - try auto-init
        from engram.core.session import new_session
        from pathlib import Path as _P
        try:
            module_name = module_name or config.get("default_module", "coding")
            session_file, scratch = new_session(module_name, "auto-session")
            sp = _P(session_file)
            ok(f"Session created: {sp.stem}")
            session_was_auto = True
        except Exception as e:
            fail(
                "No session found",
                "Run: engram init  to create one"
            )
            return 1

    # Verify session file exists
    if not sp.exists():
        fail(f"Session not found: {session_path}")
        return 1

    # LOAD SESSION
    with open(sp) as f:
        scratch_data = yaml.safe_load(f) or {}
    
    # Create a simple scratch-like object for compatibility
    class ScratchProxy:
        def __init__(self, data):
            self._data = data
            self._session_log = []
        def get(self, *keys, default=None):
            d = self._data
            for k in keys:
                if isinstance(d, dict):
                    d = d.get(k, default)
                else:
                    return default
            return d if d is not None else default
        def set(self, value, *keys):
            d = self._data
            for k in keys[:-1]:
                d = d.setdefault(k, {})
            d[keys[-1]] = value
        def log(self, entry: dict):
            """Append an entry to the session log."""
            import logging
            try:
                self._session_log.append(entry)
                logging.debug(f"[ENGRAM] scratch.log: {entry.get('task', '?')[:50]}")
            except Exception as e:
                logging.warning(f"[ENGRAM] scratch.log failed: {e}")
        def save(self, path):
            """Save session data including session_log to disk."""
            import yaml
            from pathlib import Path
            try:
                path_obj = Path(path)
                # Load existing to merge
                if path_obj.exists():
                    with open(path_obj, 'r') as f:
                        existing = yaml.safe_load(f) or {}
                else:
                    existing = {}
                # Merge in-memory data
                existing.update(self._data)
                # Add session_log if we have entries
                if self._session_log:
                    if 'session_log' not in existing:
                        existing['session_log'] = []
                    existing['session_log'].extend(self._session_log)
                with open(path_obj, 'w') as f:
                    yaml.dump(existing, f, default_flow_style=False)
            except Exception as e:
                import logging
                logging.error(f"[ENGRAM] scratch.save failed: {e}")
                raise
    
    scratch = ScratchProxy(scratch_data)
    project_name = scratch.get("project", "name") or sp.stem
    active_module = (
        module_name
        or scratch.get("project", "module")
        or config.get("default_module", "coding")
    )

    # BOOT SYSTEM
    with Spinner("Booting ENGRAM..."):
        try:
            from engram.core.boot import boot_system
            contract, db = boot_system(
                weights_mb=config.get("weights_mb", 14000),
                n_ctx=config.get("n_ctx", 8192),
                scratch_mb=config.get("scratch_mb", 512)
            )
        except Exception as e:
            fail(f"Boot failed: {e}")
            return 1

    # LOAD MODULE - use simple prompt for now
    module_prompt = f"You are a helpful {active_module} assistant."
    stones = None

    # CONNECT MCP CLIENT
    try:
        from engram.core.mcp_client import MCPClient
        mcp = MCPClient()
        mcp.connect_from_config()
    except Exception as e:
        warn(f"MCP connection failed: {e}")
        mcp = None

    # RE-INGEST PROJECT IF DB IS EMPTY
    project_path = scratch.get("project", "path")
    if project_path and db and len(db.warm_chunks) == 0:
        with Spinner("Loading project context..."):
            from engram.core.ingestion import ingest_project
            ingest_project(
                root_path=project_path,
                db=db,
                module_name=active_module,
                verbose=False
            )

    # PRINT SESSION HEADER
    header("Running")
    session_label = f"{sp.stem} (auto)" if session_was_auto else sp.stem
    ok(f"Session:  {session_label}")
    ok(f"Module:   {active_module}")
    ok(f"Model:    {config.get('model', 'qwen2.5:14b')}")
    if db:
        from engram.core.probe import get_hardware_state
        hw = get_hardware_state()
        vram_used = hw["vram_total_mb"] - hw["vram_free_mb"]
        ok(f"VRAM:     {vram_used/1024:.1f} GB "
           f"/ {hw['vram_total_mb']/1024:.1f} GB")

    # SHOW LEARNING STATUS
    try:
        from engram.core.embedder import embedding_info
        emb = embedding_info()
        section("Learning")
        ok(f"Embeddings: {emb['model']} ({emb['source']})")
        
        # Check cumulative log
        cum_log_path = sp.parent / "cumulative_log.jsonl"
        if cum_log_path.exists():
            with open(cum_log_path) as f:
                entries = [l for l in f.read().splitlines() if l.strip()]
            ok(f"Cumulative: {len(entries)} tasks")
            
            # Calculate next learning
            tasks_since = len(entries) % 10
            next_in = 10 - tasks_since if tasks_since < 10 else 0
            if next_in == 0:
                ok(f"Learning:   READY (next trigger)")
            else:
                ok(f"Learning:   in {next_in} tasks")
        else:
            info("Cumulative: new session (will create on first task)")
    except Exception:
        pass  # Silently skip if embedding check fails

    # INTERACTIVE REPL MODE
    if interactive:
        print()
        info("Interactive mode — type your goal and press Enter")
        info("Commands: /quit /clear /status")
        print()
        while True:
            try:
                user_input = input(
                    "  Goal: "
                ).strip()
            except (KeyboardInterrupt, EOFError):
                print()
                info("Exiting ENGRAM")
                break
            if not user_input:
                continue
            if user_input == "/quit":
                break
            if user_input == "/clear":
                scratch.set("", "active_task", "objective")
                info("Context cleared")
                continue
            if user_input == "/status":
                _print_runtime_status(db, scratch, contract)
                continue
            _execute_goal(
                user_input, db, scratch, contract,
                stones, str(sp), config, mcp
            )
        return 0

    # SINGLE GOAL MODE
    if not goal:
        fail("No goal provided", "Use --goal or --interactive")
        return 1

    print()
    info(f"Goal: {goal}")
    return _execute_goal(
        goal, db, scratch, contract, stones, str(sp), config, mcp
    )


def _execute_goal(
    goal, db, scratch, contract, stones, session_path, config, mcp=None
) -> int:
    """Execute a single goal and display results."""
    start = time.time()
    divider()

    try:
        # ROUTING
        with Spinner("Routing task..."):
            from engram.core.router import route_task
            from engram.core.assembler import check_pressure_and_evict
            check_pressure_and_evict(db, contract)
            routing = route_task(goal, db, scratch)

        section("Memory")
        if routing.get("promoted"):
            info(f"Promoted: {routing['promoted']}")
        if routing.get("demoted"):
            info(f"Demoted:  {routing['demoted']}")
        info(f"Hot tier: {routing['hot_count']} chunks "
             f"({routing['vram_mb']:.2f} MB)")

        divider()

        # INFERENCE
        with Spinner("Thinking..."):
            from engram.core.agent import agent_turn
            response = agent_turn(
                task_text=goal,
                db=db,
                scratch=scratch,
                contract=contract,
                stones=stones,
                session_path=session_path,
                mcp_client=mcp
            )

        print()
        print(response)
        print()

        # WRITEBACK DISPLAY
        from engram.core.writeback import parse_writeback
        wb = parse_writeback(response)
        if wb:
            divider()
            section("Writeback")
            if wb.get("module"):
                ok(f"module: {wb['module']} → {wb.get('status', '?')}")
            if wb.get("files_modified"):
                ok(f"files:  {wb['files_modified']}")
            if wb.get("evict"):
                ok(f"evict:  {wb['evict']}")

        elapsed = time.time() - start
        divider()
        ok(f"Task complete ({elapsed:.1f}s)")
        divider()
        return 0

    except KeyboardInterrupt:
        print()
        warn("Interrupted — session saved")
        scratch.save(session_path)
        return 0
    except Exception as e:
        fail(f"Run failed: {e}")
        scratch.save(session_path)
        return 1


def _find_recent_session() -> Path | None:
    """Find the most recently modified session file."""
    sessions = sorted(
        SESSIONS_DIR.glob("*.yaml"),
        key=lambda x: x.stat().st_mtime,
        reverse=True
    )
    return sessions[0] if sessions else None


def _print_runtime_status(db, scratch, contract) -> None:
    """Print runtime status for interactive mode."""
    section("Runtime Status")
    if db:
        ok(f"Hot chunks:  {len(db.hot_chunks)}")
        ok(f"Warm chunks: {len(db.warm_chunks)}")
        ok(f"VRAM used:   {db.get_hot_vram_mb():.2f} MB")
        ok(f"Utilization: {db.hot_utilization(contract):.1%}")
    if scratch:
        task = scratch.get("active_task", "objective") or "none"
        ok(f"Active task: {task}")


def register(subparsers) -> None:
    """Register run command with argument parser."""
    p = subparsers.add_parser(
        "run",
        help="Execute a goal using the ENGRAM agent"
    )
    p.add_argument("--goal", help="What you want to accomplish")
    p.add_argument("--session", help="Path to session YAML file")
    p.add_argument("--module", help="Override module selection")
    p.add_argument(
        "--interactive", "-i", action="store_true",
        help="Start interactive REPL mode"
    )
    p.set_defaults(func=lambda args: sys.exit(run(
        goal=args.goal,
        session_path=args.session,
        module_name=args.module,
        interactive=args.interactive
    )))
