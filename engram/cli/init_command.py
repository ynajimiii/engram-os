"""
ENGRAM OS CLI - Init Command

Interactive setup wizard for ENGRAM OS.
Detects hardware, checks Ollama, selects module, ingests codebase,
and creates first session.

Usage:
    engram init
    engram init --path /path/to/project
    engram init --module coding --name my-project --non-interactive
"""

import sys
import argparse
import uuid
from pathlib import Path

from engram.cli._display import (
    ok, fail, warn, info, section, header, footer,
    banner, divider, ProgressBar, Spinner
)
from engram.cli._config import load_config, SESSIONS_DIR


AVAILABLE_MODULES = {
    "1": ("coding",    "Software development, APIs, debugging"),
    "2": ("marketing", "Brand copy, campaigns, content strategy"),
    "3": ("seo",       "Keyword research, audits, content briefs"),
    "4": ("custom",    "Custom module path"),
}


def init(
    path: str | None = None,
    module_name: str | None = None,
    project_name: str | None = None,
    non_interactive: bool = False
) -> int:
    """
    Initialize a new ENGRAM OS project.

    Args:
        path: Project root directory
        module_name: Module to use
        project_name: Project name
        non_interactive: Skip prompts and use defaults

    Returns:
        Exit code (0 on success, 1 on failure)
    """
    banner()
    header("Project Setup Wizard")
    config = load_config()

    # STEP 1 — HARDWARE CHECK
    section("Checking hardware")
    try:
        import pynvml, psutil, requests
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        gpu_name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(gpu_name, bytes):
            gpu_name = gpu_name.decode("utf-8")
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        vram_mb = mem.total // (1024**2)
        ram_mb = psutil.virtual_memory().total // (1024**2)
        ok(f"GPU detected: {gpu_name} ({vram_mb} MB VRAM)")
        ok(f"RAM: {ram_mb // 1024} GB available")
    except Exception as e:
        fail(f"Hardware check failed: {e}")
        fail("Run: engram doctor  for details")
        return 1

    try:
        ollama_url = config.get("ollama_url", "http://localhost:11434")
        r = requests.get(f"{ollama_url}/api/tags", timeout=5)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        ok("Ollama: running")
        main_model = config.get("model", "qwen2.5:14b")
        if any(main_model in m for m in models):
            ok(f"Model: {main_model} ready")
        else:
            fail(
                f"Model {main_model} not loaded",
                f"ollama pull {main_model}"
            )
            return 1
    except Exception:
        fail("Ollama not running", "ollama serve")
        return 1

    # STEP 2 — MODULE SELECTION
    section("What are you working on?")
    if module_name and module_name in [
        v[0] for v in AVAILABLE_MODULES.values()
    ]:
        selected_module = module_name
        ok(f"Module: {selected_module}")
    elif non_interactive:
        selected_module = "coding"
        ok(f"Module: {selected_module} (default)")
    else:
        for key, (name, desc) in AVAILABLE_MODULES.items():
            print(f"    {key}. {name:<12} {desc}")
        print()
        choice = input("  Select [1]: ").strip() or "1"
        if choice not in AVAILABLE_MODULES:
            choice = "1"
        selected_module = AVAILABLE_MODULES[choice][0]
        if selected_module == "custom":
            selected_module = input(
                "  Module name: "
            ).strip() or "coding"

    # STEP 3 — PROJECT NAME
    section("Project details")
    cwd_name = Path.cwd().name
    if project_name:
        name = project_name
    elif non_interactive:
        name = cwd_name
    else:
        name = input(
            f"  Project name [{cwd_name}]: "
        ).strip() or cwd_name

    # STEP 4 — PROJECT PATH
    if path:
        project_path = Path(path).expanduser().resolve()
    elif non_interactive:
        project_path = Path.cwd()
    else:
        path_input = input(
            f"  Project path [{Path.cwd()}]: "
        ).strip()
        project_path = (
            Path(path_input).expanduser().resolve()
            if path_input else Path.cwd()
        )

    if not project_path.exists():
        fail(f"Path does not exist: {project_path}")
        return 1

    ok(f"Name: {name}")
    ok(f"Path: {project_path}")
    ok(f"Module: {selected_module}")

    # STEP 5 — INGESTION
    section("Ingesting codebase")
    try:
        import numpy as np
        from engram.core.boot import boot_system
        from engram.core.ingestion import walk_project, chunk_file, SUPPORTED_EXTENSIONS, SKIP_DIRS
        from engram.core.mcp_client import MCPClient
        from engram.core.vector_db import VectorDB

        contract, db = boot_system(
            weights_mb = config.get("weights_mb", 14000),
            n_ctx      = config.get("n_ctx", 8192),
            scratch_mb = config.get("scratch_mb", 512)
        )

        # Connect MCP client for file operations
        mcp = MCPClient()
        try:
            mcp.connect_from_config()
        except Exception as e:
            warn(f"MCP connection partial: {e}")

        # Walk project and ingest files
        files = list(walk_project(str(project_path), mcp, SKIP_DIRS, SUPPORTED_EXTENSIONS))
        bar = ProgressBar(
            total=max(1, len(files)),
            label="Ingesting"
        )

        chunks_created = 0
        for i, file_path in enumerate(files):
            try:
                # Read file content
                content = file_path.read_text(encoding='utf-8')
                # Chunk the file
                chunks = chunk_file(file_path, content)
                # Add chunks to database with pseudo-embeddings
                for chunk in chunks:
                    # Generate pseudo-embedding (deterministic based on chunk text)
                    pseudo_embedding = np.array([hash(chunk.text) % (2**31) for _ in range(384)], dtype=np.float32)
                    pseudo_embedding = pseudo_embedding / np.linalg.norm(pseudo_embedding)
                    
                    db.insert(
                        vector=pseudo_embedding,
                        metadata={
                            "source_file": str(chunk.source_file),
                            "chunk_type": chunk.chunk_type,
                            "symbols": chunk.symbols,
                            "text": chunk.text[:500],
                        },
                        entry_id=chunk.id
                    )
                    chunks_created += 1
            except Exception as e:
                pass  # Skip files that can't be read
            bar.update(i + 1, suffix=str(file_path.name))

        bar.done(
            f"{chunks_created} chunks "
            f"from {len(files)} files"
        )

        if chunks_created == 0:
            warn(
                "No chunks created",
                "Check file types in project directory"
            )
        else:
            ok(
                f"Ingestion complete — "
                f"{chunks_created} chunks "
                f"from {len(files)} files"
            )

    except Exception as e:
        fail(f"Ingestion failed: {e}")
        return 1

    # STEP 6 — SESSION CREATION
    section("Creating session")
    try:
        from engram.core.session import new_session

        session_path, scratch = new_session(
            selected_module, name
        )
        scratch.set(str(project_path), "project", "path")
        scratch.set(selected_module, "project", "module")
        scratch.save()  # No argument needed

        session_id = Path(session_path).stem
        ok(f"Session: {session_path}")
        ok(f"Module:  {selected_module}")

    except Exception as e:
        fail(f"Session creation failed: {e}")
        return 1

    # DONE
    print()
    divider()
    print()
    print(f"  Next step:")
    print()
    print(f'    engram run --goal "describe what you want to build"')
    print()
    print(f"  Resume this session anytime:")
    print()
    print(f"    engram session resume {name}")
    print()
    footer("ok", "ENGRAM OS ready")
    return 0


def _count_files(path: Path, module_name: str) -> list:
    """Count files that will be ingested."""
    try:
        from engram.core.ingestion import (
            load_domain_chunker, walk_project
        )
        chunker = load_domain_chunker(module_name)
        return list(walk_project(
            str(path), chunker.DOMAIN_EXTENSIONS, chunker.SKIP_DIRS
        ))
    except Exception:
        return list(path.rglob("*"))


def register(subparsers) -> None:
    """Register init command with argument parser."""
    p = subparsers.add_parser(
        "init",
        help="Initialize a project and start your first session"
    )
    p.add_argument("--path", help="Project root directory")
    p.add_argument("--module", help="Module to use")
    p.add_argument("--name", help="Project name")
    p.add_argument(
        "--non-interactive", action="store_true",
        help="Skip prompts and use defaults"
    )
    p.set_defaults(func=lambda args: sys.exit(init(
        path=args.path,
        module_name=args.module,
        project_name=args.name,
        non_interactive=args.non_interactive
    )))
