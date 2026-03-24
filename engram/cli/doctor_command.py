"""
ENGRAM OS CLI - Doctor Command

System health check for ENGRAM OS.
Checks all system requirements and reports health status.

Usage:
    engram doctor
    engram doctor --json
"""

import sys
import argparse
import importlib
import subprocess
from pathlib import Path

from engram.cli._display import (
    ok, fail, warn, info, section, header, footer,
    divider, Spinner
)
from engram.cli._config import load_config, SESSIONS_DIR


REQUIRED_PACKAGES = {
    "faiss":                  "faiss-gpu",
    "sentence_transformers":  "sentence-transformers",
    "pynvml":                 "pynvml",
    "psutil":                 "psutil",
    "yaml":                   "PyYAML",
    "requests":               "requests",
    "numpy":                  "numpy",
}


def doctor(verbose: bool = False, as_json: bool = False) -> int:
    """
    Run system health check.

    Args:
        verbose: Whether to show detailed hardware output
        as_json: Whether to output results as JSON

    Returns:
        Exit code (0 if all checks pass, 1 otherwise)
    """
    results = {}
    config = load_config()

    if not as_json:
        header("System Health Check")

    # SECTION 1 — DEPENDENCIES
    section("Dependencies")
    missing = []
    for import_name, pkg_name in REQUIRED_PACKAGES.items():
        try:
            mod = importlib.import_module(import_name)
            version = getattr(mod, "__version__", "installed")
            ok(f"{pkg_name}: {version}")
        except ImportError:
            fail(
                f"{pkg_name}: not installed",
                f"pip install {pkg_name} --break-system-packages"
            )
            missing.append(pkg_name)
    results["dependencies"] = {
        "status": "fail" if missing else "ok",
        "missing": missing
    }

    # SECTION 2 — GPU & HARDWARE
    section("GPU & Hardware")
    gpu_info = {}
    try:
        import pynvml
        import psutil
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(name, bytes):
            name = name.decode("utf-8")
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        vram_total = mem.total // (1024**2)
        vram_free  = mem.free  // (1024**2)
        vram_used = vram_total - vram_free
        ram = psutil.virtual_memory()
        ram_total = ram.total // (1024**2)
        ram_avail = ram.available // (1024**2)
        
        gpu_info = {
            "name": name,
            "vram_total_mb": vram_total,
            "vram_free_mb": vram_free,
            "vram_used_mb": vram_used,
        }
        
        ok(f"GPU: {name}")
        ok(f"VRAM: {vram_total} MB total / {vram_free} MB free")
        ok(f"RAM: {ram_total} MB total / {ram_avail} MB available")
        
        # Verbose output with additional hardware details
        if verbose:
            print()
            info("Verbose Hardware Details:")
            ok(f"Free VRAM: {vram_free} MB")
            ok(f"Used VRAM: {vram_used} MB")
            
            # GPU Temperature
            try:
                temperature = pynvml.nvmlDeviceGetTemperature(handle, 0)  # NVML_TEMPERATURE_GPU
                ok(f"GPU Temperature: {temperature}°C")
                gpu_info["temperature_c"] = temperature
            except Exception:
                info("GPU Temperature: not available")
                gpu_info["temperature_c"] = None
            
            # Power Draw
            try:
                power_draw = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0  # Convert mW to W
                ok(f"Power Draw: {power_draw:.1f}W")
                gpu_info["power_w"] = power_draw
            except Exception:
                info("Power Draw: not available")
                gpu_info["power_w"] = None
            
            # Additional details
            try:
                utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)
                ok(f"GPU Utilization: {utilization.gpu}%")
                ok(f"Memory Utilization: {utilization.memory}%")
                gpu_info["utilization_gpu"] = utilization.gpu
                gpu_info["utilization_memory"] = utilization.memory
            except Exception:
                pass
                
        try:
            import torch
            if torch.cuda.is_available():
                ok("CUDA: available")
            else:
                warn("CUDA: not available via torch")
        except ImportError:
            info("CUDA: torch not installed — skipping CUDA check")
        results["hardware"] = {
            "status": "ok",
            "gpu": name,
            "vram_mb": vram_total,
            "ram_mb": ram_total,
            **gpu_info
        }
    except Exception as e:
        fail(f"Hardware probe failed: {e}")
        results["hardware"] = {"status": "fail", "error": str(e)}

    # SECTION 3 — OLLAMA
    section("Ollama")
    try:
        import requests
        ollama_url = config.get("ollama_url", "http://localhost:11434")
        r = requests.get(f"{ollama_url}/api/tags", timeout=5)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        ok(f"Ollama: running at {ollama_url}")

        main_model   = config.get("model", "qwen2.5:14b")
        router_model = config.get("router_model", "qwen2.5:7b")

        if any(main_model in m for m in models):
            ok(f"Model: {main_model} loaded")
        else:
            fail(
                f"Model: {main_model} not found",
                f"ollama pull {main_model}"
            )

        if any(router_model in m for m in models):
            ok(f"Router model: {router_model} loaded")
        else:
            warn(
                f"Router model: {router_model} not found",
                f"ollama pull {router_model}"
            )

        if verbose and models:
            info(f"All loaded models: {', '.join(models)}")

        results["ollama"] = {"status": "ok", "models": models}

    except ImportError:
        fail("requests: not installed", "pip install requests")
        results["ollama"] = {"status": "fail", "error": "requests not installed"}
    except subprocess.TimeoutExpired:
        fail(
            "Ollama: not responding",
            "ollama serve"
        )
        results["ollama"] = {"status": "fail"}
    except Exception as e:
        fail(
            "Ollama: not running",
            "ollama serve"
        )
        results["ollama"] = {"status": "fail", "error": str(e)}

    # SECTION 4 — MEMORY CONTRACT
    section("Memory Contract")
    try:
        from engram.core.probe import get_hardware_state
        from engram.core.contract import calculate_memory_budget
        hw = get_hardware_state()
        contract = calculate_memory_budget(
            weights_mb  = config.get("weights_mb", 14000),
            n_ctx       = config.get("n_ctx", 8192),
            scratch_mb  = config.get("scratch_mb", 512),
            vram_total_mb = hw.get("vram_total_mb", 24576)
        )
        ok(f"weights_mb:      {contract.weights_mb:>8} MB")
        ok(f"kv_ceiling_mb:   {contract.kv_ceiling_mb:>8} MB")
        ok(f"scratch_mb:      {contract.scratch_mb:>8} MB")
        ok(f"vector_floor_mb: {contract.vector_floor_mb:>8} MB")
        ok(f"vector_max_mb:   {contract.vector_max_mb:>8} MB")
        if contract.vector_floor_mb < 512:
            warn(
                "Vector DB floor is very small",
                "Consider reducing n_ctx or using a smaller model"
            )
        results["contract"] = {"status": "ok"}
    except Exception as e:
        fail(f"Contract computation failed: {e}")
        results["contract"] = {"status": "fail", "error": str(e)}

    # SECTION 4B — EMBEDDINGS & LEARNING
    section("Embeddings & Learning")
    try:
        from engram.core.embedder import embedding_info
        emb = embedding_info()
        ok(f"Model:      {emb['model']}")
        ok(f"Source:     {emb['source']}")
        ok(f"Dimension:  {emb['dimension']}")
        if emb['real']:
            ok(f"Status:     Active (real semantic)")
        else:
            warn(f"Status:     Fallback (pseudo-embedding)")
        results["embeddings"] = emb
    except Exception as e:
        fail(f"Embedding check failed: {e}")
        results["embeddings"] = {"status": "fail", "error": str(e)}

    # Check cumulative log
    try:
        sessions_path = Path(config.get("sessions_dir", str(SESSIONS_DIR)))
        cum_log_path = sessions_path / "cumulative_log.jsonl"
        if cum_log_path.exists():
            with open(cum_log_path) as f:
                entries = [l for l in f.read().splitlines() if l.strip()]
            ok(f"Cumulative: {len(entries)} tasks logged")
            
            tasks_since_learning = len(entries) % 10
            next_learning = 10 - tasks_since_learning if tasks_since_learning < 10 else 0
            ok(f"Learning:   next in {next_learning} tasks")
            results["learning"] = {
                "cumulative_tasks": len(entries),
                "next_learning_in": next_learning,
            }
        else:
            info("Cumulative: not yet created (first run)")
            results["learning"] = {"status": "new"}
    except Exception as e:
        warn(f"Learning status check failed: {e}")
        results["learning"] = {"status": "fail", "error": str(e)}

    # SECTION 5 — MCP SERVERS
    section("MCP Servers")
    mcp_config_path = (
        Path(__file__).parent.parent / "config" / "mcp_servers.yaml"
    )
    if not mcp_config_path.exists():
        warn(
            "mcp_servers.yaml not found",
            f"Create: {mcp_config_path}"
        )
        results["mcp"] = {"status": "warn"}
    else:
        import yaml
        with open(mcp_config_path) as f:
            mcp_cfg = yaml.safe_load(f) or {}
        servers = mcp_cfg.get("servers", {})
        mcp_results = []
        for name, srv in servers.items():
            if not srv.get("enabled", False):
                info(f"{name}: disabled")
                mcp_results.append({"name": name, "status": "disabled"})
                continue
            try:
                # Try npx.cmd on Windows, npx on Unix
                import platform
                cmd = ["npx.cmd", "--version"] if platform.system() == "Windows" else ["npx", "--version"]
                proc = subprocess.run(
                    cmd,
                    capture_output=True, timeout=5
                )
                if proc.returncode == 0:
                    ok(f"{name}: npx available")
                    mcp_results.append({"name": name, "status": "ok"})
                else:
                    fail(f"{name}: npx not found", "npm install -g npx")
                    mcp_results.append({"name": name, "status": "fail"})
            except FileNotFoundError:
                fail(f"{name}: npx not found", "npm install -g npx")
                mcp_results.append({"name": name, "status": "fail"})
            except Exception as e:
                warn(f"{name}: {e}")
                mcp_results.append({"name": name, "status": "warn"})
        results["mcp"] = {"status": "ok", "servers": mcp_results}

    # SECTION 6 — SESSIONS
    section("Sessions")
    sessions_path = Path(config.get(
        "sessions_dir", str(SESSIONS_DIR)
    ))
    if not sessions_path.exists():
        try:
            sessions_path.mkdir(parents=True)
            ok(f"Sessions directory created: {sessions_path}")
        except OSError as e:
            fail(f"Cannot create sessions dir: {e}")
            results["sessions"] = {"status": "fail"}
    else:
        ok(f"Directory: {sessions_path}")
    session_files = sorted(
        sessions_path.glob("*.yaml"),
        key=lambda x: x.stat().st_mtime,
        reverse=True
    )
    if session_files:
        ok(f"Existing sessions: {len(session_files)}")
        for sf in session_files[:3]:
            info(f"  {sf.name}")
    else:
        info("No sessions yet — run: engram init")
    results["sessions"] = {
        "status": "ok",
        "count": len(session_files)
    }

    # SECTION 7 — CORE MODULES
    section("Core Modules")
    CORE_MODULES = [
        "engram.core.probe",       "engram.core.contract",
        "engram.core.boot",        "engram.core.scratch",
        "engram.core.stones",      "engram.core.session",
        "engram.core.vector_db",   "engram.core.router",
        "engram.core.assembler",   "engram.core.pipeline",
        "engram.core.llm",         "engram.core.writeback",
        "engram.core.agent",       "engram.core.agent_session",
        "engram.core.shared_scratch", "engram.core.planner",
        "engram.core.horizon",
    ]
    failed_imports = []
    for mod in CORE_MODULES:
        try:
            importlib.import_module(mod)
        except ImportError as e:
            failed_imports.append((mod, str(e)))
    if failed_imports:
        for mod, err in failed_imports:
            fail(f"{mod}: {err}")
        results["modules"] = {"status": "fail"}
    else:
        ok(f"All {len(CORE_MODULES)} core modules import cleanly")
        results["modules"] = {"status": "ok"}

    # FINAL SUMMARY
    print()
    divider()
    total    = len(results)
    passed   = sum(1 for r in results.values()
                   if r.get("status") == "ok")
    warnings = sum(1 for r in results.values()
                   if r.get("status") == "warn")
    failed_n = sum(1 for r in results.values()
                   if r.get("status") == "fail")

    info(f"Checks: {total} | "
         f"Passed: {passed} | "
         f"Warnings: {warnings} | "
         f"Failed: {failed_n}")
    print()

    if failed_n > 0:
        footer("fail",
               "ISSUES FOUND — fix above before running ENGRAM")
    elif warnings > 0:
        footer("warn", "READY WITH WARNINGS — review above")
        info("Run: engram init")
    else:
        footer("ok", "ALL SYSTEMS HEALTHY")
        info("Run: engram init")

    return 0 if failed_n == 0 else 1


def register(subparsers) -> None:
    """Register doctor command with argument parser."""
    import yaml  # Local import to avoid circular dependency
    p = subparsers.add_parser(
        "doctor",
        help="Check system health and diagnose issues"
    )
    p.add_argument("--json", action="store_true",
                   help="Output results as JSON")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Show detailed hardware information")
    p.set_defaults(func=lambda args: sys.exit(doctor(
        verbose=args.verbose,
        as_json=args.json
    )))
