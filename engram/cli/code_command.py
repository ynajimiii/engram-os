# engram/cli/code_command.py
"""
ENGRAM OS — Code Command

Implements `engram code` — the coding agent CLI command.
Wires tools into agent_turn() for file/shell operations.

Usage:
    engram code "implement login form"
    engram code "fix the auth bug" --session abc123
    engram code "add tests for user module" --module coding
"""

import sys
import time
import argparse
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional

from engram.cli._display import (
    ok, fail, warn, info, section, header, divider, Spinner
)
from engram.cli._config import load_config, SESSIONS_DIR, _resolve_session

# Module-level imports with safe fallbacks to avoid local scoping issues
try:
    from engram.core.llm import OllamaProvider as _OllamaProvider, BaseLLM as _BaseLLM
except ImportError:
    _OllamaProvider = None
    _BaseLLM = None


def run(
    goal: str,
    session_path: Optional[str] = None,
    module_name: Optional[str] = None,
    dry_run: bool = False,
) -> int:
    """
    Execute a coding task using the ENGRAM coding agent.

    Args:
        goal: What to accomplish
        session_path: Path to session YAML file
        module_name: Module to use
        dry_run: Show what would be done without executing

    Returns:
        Exit code (0 on success, 1 on failure)
    """
    config = load_config()

    # Auto-detect session using _resolve_session()
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

    # Load session
    with open(sp) as f:
        scratch_data = yaml.safe_load(f) or {}

    # Create scratch proxy
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
            import logging
            try:
                self._session_log.append(entry)
                logging.debug(f"[ENGRAM] scratch.log: {entry.get('task', '?')[:50]}")
            except Exception as e:
                logging.warning(f"[ENGRAM] scratch.log failed: {e}")
        def save(self, path):
            import yaml
            from pathlib import Path as P
            try:
                path_obj = P(path)
                if path_obj.exists():
                    with open(path_obj, 'r') as f:
                        existing = yaml.safe_load(f) or {}
                else:
                    existing = {}
                existing.update(self._data)
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

    # Boot system
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

    # Load module prompt
    module_prompt = _load_module_prompt(active_module)
    stones = {"system_prompt": module_prompt, "scratch_note": ""}

    # Connect MCP client for tools
    mcp = None
    try:
        from engram.core.mcp_client import MCPClient
        mcp = MCPClient()
        mcp.connect_from_config()
        info(f"MCP connected: {len(mcp.get_server_status())} servers")
    except Exception as e:
        warn(f"MCP connection failed: {e}")
        # Continue without MCP — will use direct tool calls

    # Re-ingest project if DB is empty — SCOPED VERSION
    # Scoped to engram/core/ for fast startup.
    # Full ingest can be run manually if needed.
    project_path = scratch.get("project", "path")
    
    # Directories to skip during ingestion
    _INGEST_SKIP_DIRS = {
        "__pycache__",
        ".pytest_cache",
        ".git",
        "sessions",       # don't ingest session YAML files
        "experience",     # don't ingest experience JSON files
    }
    
    # Focus directories for faster ingestion
    _INGEST_FOCUS_DIRS = [
        "engram/core",
        "engram/cli",
        "engram/tools",
    ]
    
    if project_path and db and len(db.warm_chunks) == 0:
        with Spinner("Loading project context..."):
            try:
                from engram.core.ingestion import (
                    ingest_project,
                    ingest_project_direct,
                )
                from pathlib import Path as _P
                
                _total_chunks = 0
                _ingested_any = False
                
                # Ingest focus dirs one at a time
                for _focus in _INGEST_FOCUS_DIRS:
                    _focus_path = _P(project_path) / _focus
                    if _focus_path.exists():
                        _n = 0
                        
                        # Try MCP path first
                        if mcp is not None:
                            try:
                                _result = ingest_project(
                                    root_path=str(_focus_path),
                                    db=db,
                                    mcp=mcp,
                                    skip_dirs=_INGEST_SKIP_DIRS,
                                    tier="warm",
                                )
                                _n = _result[1] if isinstance(_result, tuple) else _n
                            except Exception as _mcp_err:
                                import logging
                                logging.warning(
                                    f"[ENGRAM] MCP ingest failed: "
                                    f"{_mcp_err} — using filesystem"
                                )
                        
                        # Fallback: filesystem direct
                        if _n == 0:
                            import logging
                            logging.info(
                                f"[ENGRAM] using filesystem ingest "
                                f"for {_focus_path}"
                            )
                            _n = ingest_project_direct(
                                root_path=str(_focus_path),
                                db=db,
                                skip_dirs=_INGEST_SKIP_DIRS,
                                tier="warm",
                            )
                        
                        _total_chunks += _n
                        _ingested_any = True
                        info(f"{_focus}: {_n} chunks")
                
                if not _ingested_any:
                    # Fallback: ingest full root with filesystem direct
                    _total_chunks = ingest_project_direct(
                        root_path=project_path,
                        db=db,
                        skip_dirs=_INGEST_SKIP_DIRS,
                        tier="warm",
                    )
                
                if _total_chunks > 0:
                    info(f"Ingested {_total_chunks} chunks from focus dirs")
                else:
                    import logging
                    logging.error(
                        "[ENGRAM] INGEST PRODUCED 0 CHUNKS — "
                        "agent will run without project memory. "
                        "Check skip_dirs and file extensions."
                    )
            except Exception as _ingest_err:
                import logging
                logging.warning(
                    f"[ENGRAM] auto-ingest failed: {_ingest_err}"
                )

    # Print session header
    header("Coding")
    session_label = f"{sp.stem} (auto)" if session_was_auto else sp.stem
    ok(f"Session:  {session_label}")
    ok(f"Module:   {active_module}")
    ok(f"Model:    {config.get('model', 'qwen3:30b-a3b-q4_K_M')}")
    if db:
        from engram.core.probe import get_hardware_state
        hw = get_hardware_state()
        vram_used = hw["vram_total_mb"] - hw["vram_free_mb"]
        ok(f"VRAM:     {vram_used/1024:.1f} GB / {hw['vram_total_mb']/1024:.1f} GB")

    # Show learning status
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

    # Execute the coding task
    if not goal:
        fail("No goal provided", "Use: engram code \"your task\"")
        return 1

    print()
    info(f"Goal: {goal}")

    if dry_run:
        info("Dry run — showing what would be done")
        return 0

    return _execute_coding_task(
        goal, db, scratch, contract, stones, str(sp), config, mcp,
        active_module=active_module
    )


def _execute_coding_task(
    goal, db, scratch, contract, stones, session_path, config, mcp=None,
    active_module="coding"
) -> int:
    """Execute a coding task and display results."""
    start = time.time()
    divider()

    try:
        # Route task
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

        # Build tool client for agent_turn
        from pathlib import Path as PathObj
        project_root = PathObj(__file__).parent.parent.parent
        from engram.tools import LocalToolClient
        tool_client = LocalToolClient(sandbox_root=str(project_root))

        # Execute with tools
        with Spinner("Coding..."):
            from engram.core.agent import agent_turn

            # Execute agent turn with tool client
            response = agent_turn(
                task_text=goal,
                db=db,
                scratch=scratch,
                contract=contract,
                stones=stones,
                session_path=session_path,
                mcp_client=tool_client  # Use LocalToolClient for tools
            )

            # Retrieve real tool calls for execution scoring
            # Must be called immediately after agent_turn() —
            # the list is replaced on the next call.
            from engram.core.agent import get_last_tool_calls
            import logging
            _tool_calls = get_last_tool_calls()
            logging.debug(
                f"[ENGRAM] tool calls this turn: {len(_tool_calls)} "
                f"({[tc['name'] for tc in _tool_calls]})"
            )

        print()
        print(response)
        print()

        # Parse and display writeback
        from engram.core.writeback import parse_writeback, apply_writeback
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

            # Apply writeback
            evict_ids = apply_writeback(wb, scratch, session_path)
            for chunk_id in evict_ids:
                if db and hasattr(db, 'demote'):
                    db.demote(chunk_id)

        # ── QUALITY SCORING ───────────────────────────────────
        # CORRECT ORDER:
        # 1. Create log_entry with placeholder score
        # 2. Append to session_log FIRST
        # 3. Score AFTER
        # 4. Update in place (dict is mutable)
        # 5. Save LAST
        quality_score = 0.0
        quality_method = "none"
        try:
            from engram.core.scorer import score_task

            def _llm_call(prompt: str) -> str:
                """Real LLM callable for quality scoring."""
                try:
                    _llm = _BaseLLM(provider=_OllamaProvider(
                        model=config.get('model', 'qwen3:30b-a3b-q4_K_M'),
                        base_url=config.get('ollama_url', 'http://localhost:11434')
                    ))
                    resp = _llm.complete(prompt)
                    if hasattr(resp, 'content') and resp.content:
                        return resp.content
                    if hasattr(resp, 'text') and resp.text:
                        return resp.text
                    if isinstance(resp, str):
                        return resp
                    return str(resp)
                except Exception as _e:
                    import logging
                    logging.warning(
                        f"[ENGRAM] scorer llm_call: {_e}"
                    )
                    return ""

            # Get tool calls from this turn
            try:
                from engram.core.agent import get_last_tool_calls
                _tool_calls = get_last_tool_calls()
            except Exception:
                _tool_calls = []

            # Get files modified from writeback
            _files = []
            if wb and isinstance(wb, dict):
                _raw_files = wb.get('files_modified', [])
                if isinstance(_raw_files, list):
                    _files = _raw_files
                elif isinstance(_raw_files, str):
                    _files = [_raw_files]

            # PHASE 2: Calculate task complexity using imported function
            from engram.core.agent import _count_task_requirements
            task_complexity = _count_task_requirements(goal)
            
            # STEP 1: Create log_entry with placeholder score
            log_entry = {
                "task":             goal,
                "response_length":  len(response),
                "tool_calls_count": len(_tool_calls),
                "quality_score":    0.0,        # placeholder
                "quality_source":   "pending",
                "quality_reason":   "",
                "response_time":    round(time.time() - start, 2),  # Add response time
                "task_complexity":  task_complexity,                # Add complexity score
            }

            # STEP 2: Append FIRST (before scoring)
            if hasattr(scratch, '_session_log'):
                scratch._session_log.append(log_entry)

            # STEP 3: Score AFTER appending (with domain-aware calibration)
            quality = score_task(
                task=goal,
                response=response,
                tool_calls=_tool_calls,
                session_log=[],  # Not used by structured scorer
                llm_call=_llm_call,
                model=config.get('model', 'qwen3:30b-a3b-q4_K_M'),
                files_modified=_files,
                module_name=active_module,
                task_type=wb.get("module", "general") if wb else "general",
            )

            # Extract score — handle all QualityScore variants
            if quality is None:
                quality_score = 0.0
                quality_method = "none"
            elif hasattr(quality, 'score'):
                quality_score = float(quality.score or 0.0)
                quality_method = getattr(quality, 'source', 'scored')
            elif hasattr(quality, 'value'):
                quality_score = float(quality.value or 0.0)
                quality_method = 'scored'
            elif hasattr(quality, 'overall'):
                quality_score = float(quality.overall or 0.0)
                quality_method = 'scored'
            elif isinstance(quality, (int, float)):
                quality_score = float(quality)
                quality_method = 'direct'
            else:
                quality_score = 0.0
                quality_method = "unknown"

            import logging
            logging.info(
                f"[ENGRAM] quality: {quality_score:.3f} "
                f"method={quality_method}"
            )

            info(f"Quality: {quality_score:.2f} ({quality_method})")

            # STEP 4: Update IN PLACE — works because dict is mutable
            log_entry["quality_score"]  = quality_score
            log_entry["quality_source"] = quality_method
            log_entry["quality_reason"] = getattr(quality, 'reason', '')

            # STEP 5: Save LAST
            try:
                if hasattr(scratch, 'save') and session_path:
                    scratch.save(session_path)
            except Exception as _upd_err:
                import logging
                logging.debug(f"[ENGRAM] session_log save skipped: {_upd_err}")

        except Exception as _score_err:
            import logging, traceback
            logging.error(
                f"[ENGRAM] scoring failed: {_score_err}"
            )
            logging.debug(traceback.format_exc())
            quality_score = 0.0
            quality_method = "error"

        # ── END SCORING ───────────────────────────────────────

        # ── Ring 2 continued: Experience extraction ──────────────
        if quality_score >= 0.7:
            try:
                from engram.core.experience import (
                    distill_experiences,
                    get_relevant_experiences,
                )
                from engram.core.llm import make_llm_call

                # Create LLM for experience extraction
                llm_for_exp = _BaseLLM(provider=_OllamaProvider(
                    model="qwen3:30b-a3b-q4_K_M",
                    base_url=config.get('ollama_url', 'http://localhost:11434')
                ))
                llm_call = make_llm_call(llm_for_exp)

                # Build session_log format that distill_experiences expects
                session_log_for_distill = [{
                    "task": goal,
                    "response": response,
                    "quality_score": quality_score,
                    "task_id": session_path,
                }]

                # Need multiple tasks for distillation (MIN_TASKS_PER_TYPE=3)
                # So we accumulate in session_log via scratch
                existing_log = getattr(scratch, '_session_log', [])
                if len(existing_log) >= 2:
                    session_log_for_distill = existing_log + [{
                        "task": goal,
                        "response": response,
                        "quality_score": quality_score,
                        "task_id": session_path,
                    }]

                experiences = distill_experiences(
                    session_log=session_log_for_distill,
                    db=db,
                    llm_call=llm_call,
                    min_tasks=2,  # Lower threshold for single-session
                    tier="warm",
                )

                if experiences:
                    info(f"[ENGRAM] {len(experiences)} experience(s) distilled")
            except Exception as e:
                import logging
                logging.warning(f"[ENGRAM] experience extraction failed: {e}")

        # ── Ring 3: Cross-session learning trigger ──────────────────────────────
        from engram.core.scratch import (
            append_to_cumulative_log,
            load_cumulative_log,
        )

        # Cumulative log path
        _cumulative_log_path = str(
            project_root / "engram" / "sessions" / "cumulative_log.jsonl"
        )

        # Append to cumulative log (cross-session evidence)
        _log_entry = {
            "session_id": session_path,
            "task": goal,
            "response": response[:500],  # Truncate for storage
            "quality_score": quality_score,
            "writeback_parsed": wb is not None if wb else False,
            "files_modified": wb.get("files_modified") if wb else [],
        }
        append_to_cumulative_log(
            entry=_log_entry,
            log_path=_cumulative_log_path,
        )

        # Load cross-session evidence (not just this session)
        _cumulative_log = load_cumulative_log(
            log_path=_cumulative_log_path,
            last_n=50,
            min_score=0.0,
        )

        # Count TOTAL entries in file (not filtered last_n) for trigger
        _cum_log_count = 0
        try:
            with open(_cumulative_log_path, encoding='utf-8') as f:
                _cum_log_count = len([l for l in f.readlines() if l.strip()])
        except Exception:
            _cum_log_count = len(_cumulative_log)

        # Trigger every 10 entries in cumulative log (only on non-zero multiples)
        if _cum_log_count > 0 and _cum_log_count % 10 == 0:
            try:
                from engram.core.learner import (
                    learning_cycle,
                    PromptPatch,
                    apply_patch,
                )
                from engram.core.llm import make_llm_call

                # Create LLM for learning
                llm_for_learn = _BaseLLM(provider=_OllamaProvider(
                    model=config.get('model', 'qwen3:30b-a3b-q4_K_M'),
                    base_url=config.get('ollama_url', 'http://localhost:11434')
                ))
                llm_call = make_llm_call(llm_for_learn)

                # Load current prompt
                current_prompt = stones.get("system_prompt", "") if stones else ""

                # Run learning cycle with cumulative log (cross-session)
                improved, patch = learning_cycle(
                    module_name=active_module,
                    session_log=_cumulative_log,
                    current_prompt=current_prompt,
                    llm_call=llm_call,
                    n_recent=10,
                    n_evaluate=3,
                    min_improvement=0.05,
                )

                if improved and patch:
                    # Get new prompt string from patch
                    new_prompt = apply_patch(current_prompt, patch)

                    # Update in-memory stones
                    if stones:
                        stones["system_prompt"] = new_prompt

                    # Persist to disk (Fix A)
                    _current_version = getattr(
                        patch, 'version',
                        getattr(patch, 'prompt_version', 1)
                    )
                    _persist_prompt(
                        new_prompt=new_prompt,
                        module_name=active_module,
                        modules_dir=str(project_root / "engram" / "modules"),
                        version=_current_version + 1,
                    )
                    info(f"[ENGRAM] Ring 3: prompt improved (v{_current_version} → v{_current_version + 1})")
            except Exception as e:
                import logging
                logging.warning(f"[ENGRAM] Ring 3 learning failed: {e}")

        # ── Rubric evolution (every 50 tasks) ────────────────────
        _cal_log_path = str(
            project_root / "engram" / "sessions"
            / f"scorer_calibration_{active_module}.jsonl"
        )
        _cum_count = _cum_log_count   # reuse existing count variable

        if _cum_count > 0 and _cum_count % 50 == 0:
            try:
                from engram.core.learner import evolve_rubric
                from engram.core.llm import make_llm_call

                # Create LLM for rubric evolution
                llm_for_evolve = _BaseLLM(provider=_OllamaProvider(
                    model=config.get('model', 'qwen3:30b-a3b-q4_K_M'),
                    base_url=config.get('ollama_url', 'http://localhost:11434')
                ))
                llm_call = make_llm_call(llm_for_evolve)

                _rubric_result = evolve_rubric(
                    module_name=active_module,
                    modules_dir=str(project_root / "engram" / "modules"),
                    calibration_log_path=_cal_log_path,
                    llm_call=llm_call,
                    min_tasks=50,
                )
                if _rubric_result["evolved"]:
                    info(
                        f"[ENGRAM] rubric evolved: v{_rubric_result['rubric_version']} "
                        f"(bias was {_rubric_result['bias_corrected']})"
                    )
            except Exception as _re_err:
                import logging
                logging.warning(f"[ENGRAM] rubric evolution: {_re_err}")

        divider()
        ok(f"Task complete ({time.time() - start:.1f}s)")
        divider()

        return 0

    except KeyboardInterrupt:
        print()
        warn("Interrupted — session saved")
        scratch.save(session_path)
        return 0
    except Exception as e:
        fail(f"Code failed: {e}")
        scratch.save(session_path)
        return 1


def _load_module_prompt(module_name: str) -> str:
    """Load system prompt for a module."""
    from pathlib import Path

    # Try modules directory first
    module_file = Path(f"engram/modules/{module_name}/agent_system_prompt.md")
    if module_file.exists():
        with open(module_file, encoding='utf-8') as f:
            prompt = f.read()
        # Apply deduplication on load to clean up any existing duplicates
        from engram.core.learner import _deduplicate_prompt
        prompt = _deduplicate_prompt(prompt, threshold=0.72)
        return prompt

    # Fallback to YAML module file
    yaml_file = Path(f"engram/modules/{module_name}.yaml")
    if yaml_file.exists():
        with open(yaml_file, encoding='utf-8') as f:
            data = yaml.safe_load(f)
            prompt = data.get("system_prompt", f"You are a {module_name} assistant.")
        # Apply deduplication on load
        from engram.core.learner import _deduplicate_prompt
        prompt = _deduplicate_prompt(prompt, threshold=0.72)
        return prompt

    # Default prompt
    return f"You are a {module_name} agent within ENGRAM OS. You have access to tools that can help you complete tasks."


def _persist_prompt(
    new_prompt: str,
    module_name: str,
    modules_dir: str,
    version: int,
) -> bool:
    """
    Write an improved system prompt back to the module's
    prompt file on disk so the next session boots with it.

    Writes a version comment as the first line so every
    version is traceable and a regression is one file
    restore away.

    Args:
        new_prompt:  The full improved prompt string.
        module_name: e.g. "coding"
        modules_dir: Path to engram/modules/
        version:     The new version number (old + 1).

    Returns:
        True if write succeeded, False otherwise.
        Never raises.
    """
    import logging
    from pathlib import Path
    from datetime import datetime

    # Candidate locations in priority order.
    candidates = [
        Path(modules_dir) / module_name / "agent_system_prompt.md",
        Path(modules_dir) / module_name / "prompt.txt",
        Path(modules_dir) / module_name / "system_prompt.txt",
        Path(modules_dir) / f"{module_name}.yaml",
    ]

    # Find which one exists (first candidate should be .md file)
    target = None
    for c in candidates:
        if c.exists():
            target = c
            break

    if target is None:
        # File does not exist yet — create at first candidate
        target = candidates[0]
        target.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Back up current version before overwriting.
        # Backup name: agent_system_prompt.v{N}.bak
        if target.exists():
            backup = target.with_suffix(
                f".v{version - 1}.bak"
            )
            backup.write_text(
                target.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            logging.debug(
                f"[ENGRAM] prompt backup: {backup}"
            )

        # Write version header + new prompt.
        ts      = datetime.utcnow().strftime("%Y-%m-%d")
        header  = f"# v{version} — auto-learned {ts}\n"

        # If target is a YAML file, update system_prompt key.
        if target.suffix in (".yaml", ".yml"):
            import yaml
            with open(target, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            data["system_prompt"]  = new_prompt
            data["prompt_version"] = version
            data["last_learned"]   = datetime.utcnow().isoformat()
            with open(target, "w", encoding="utf-8") as f:
                yaml.dump(
                    data, f,
                    default_flow_style=False,
                    allow_unicode=True,
                )
        else:
            # Markdown or plain text — write header + body
            target.write_text(
                header + new_prompt,
                encoding="utf-8",
            )

        logging.info(
            f"[ENGRAM] prompt persisted: {target} "
            f"v{version} ({len(new_prompt)} chars)"
        )
        return True

    except Exception as e:
        logging.error(
            f"[ENGRAM] _persist_prompt failed: {e}"
        )
        return False


def _find_recent_session() -> Optional[Path]:
    """Find the most recently modified session file."""
    sessions = sorted(
        SESSIONS_DIR.glob("*.yaml"),
        key=lambda x: x.stat().st_mtime,
        reverse=True
    )
    return sessions[0] if sessions else None


def register(subparsers) -> None:
    """Register code command with argument parser."""
    p = subparsers.add_parser(
        "code",
        help="Execute a coding task using the ENGRAM coding agent"
    )
    p.add_argument(
        "goal",
        nargs="?",
        help="What you want to accomplish"
    )
    p.add_argument("--session", help="Path to session YAML file")
    p.add_argument("--module", help="Override module selection")
    p.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be done without executing"
    )
    p.set_defaults(func=lambda args: sys.exit(run(
        goal=args.goal,
        session_path=args.session,
        module_name=args.module,
        dry_run=args.dry_run
    )))
