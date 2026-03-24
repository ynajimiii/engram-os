"""
ENGRAM OS CLI - Shared configuration loader.

Reads from ~/.engram/config.yaml.
Creates defaults on first run.
"""

import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field


# Respect ENGRAM_HOME environment variable (for testing)
ENGRAM_HOME = Path(os.environ.get("ENGRAM_HOME", str(Path.home() / ".engram")))
CONFIG_PATH = ENGRAM_HOME / "config.yaml"
SESSIONS_DIR = ENGRAM_HOME / "sessions"

DEFAULT_CONFIG = {
    "model":          "qwen2.5:14b",
    "router_model":   "qwen2.5:7b",
    "weights_mb":     14000,
    "n_ctx":          8192,
    "scratch_mb":     512,
    "vector_db_dim":  384,
    "max_hot_size":   100,
    "ollama_url":     "http://localhost:11434",
    "lmstudio_url":   "http://localhost:1234",
    "tool_backend":   "ollama",
    "sessions_dir":   str(SESSIONS_DIR),
    "default_module": "coding",
    "verbose":        False,
    "color":          True,
    # Context management (FAILURE_ANALYSIS_REPORT.md recommendations)
    "context_limit":  10,        # Last 10 turns in context window
    "max_tokens":     4096,      # Max output tokens for LLM responses
    "min_response_chars": 150,   # Minimum response length before retry
    "max_retries":    2,         # Max retries for short responses
}


def ensure_engram_home() -> None:
    """Ensure ENGRAM home directory and sessions directory exist."""
    ENGRAM_HOME.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    """Load configuration from YAML file, creating defaults if needed."""
    ensure_engram_home()
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    with open(CONFIG_PATH) as f:
        loaded = yaml.safe_load(f) or {}
    merged = DEFAULT_CONFIG.copy()
    merged.update(loaded)
    return merged


def save_config(config: dict) -> None:
    """Save configuration to YAML file."""
    ensure_engram_home()
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False)


def get(key: str, default=None):
    """Get a configuration value by key."""
    return load_config().get(key, default)


def set_value(key: str, value) -> None:
    """Set a configuration value and save."""
    config = load_config()
    if key not in DEFAULT_CONFIG:
        raise KeyError(
            f"Unknown config key: '{key}'. "
            f"Valid keys: {list(DEFAULT_CONFIG.keys())}"
        )
    config[key] = value
    save_config(config)


def _resolve_session(
    session_arg: str = None,
    module: str = None,
):
    """
    Resolve which session to use.

    Priority:
      1. Explicit --session arg         (user specified)
      2. Most recent session for module (auto-select)
      3. Most recent session overall    (any module)
      4. None → caller shows init hint

    Returns Path or None.
    """
    from pathlib import Path
    import yaml

    # Collect all session files from both locations
    candidates = []
    for sessions_dir in [
        Path(__file__).parent.parent / "sessions",
        Path.home() / ".engram" / "sessions",
    ]:
        if sessions_dir.exists():
            candidates.extend(
                sessions_dir.glob("*.yaml")
            )

    if not candidates:
        return None

    # If explicit session given — find it
    if session_arg:
        for p in candidates:
            if session_arg in p.name or session_arg in str(p):
                return p
        return None

    # Sort by most recently modified
    candidates.sort(
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )

    # If module specified — prefer matching sessions
    if module:
        for p in candidates:
            try:
                with open(p, encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                proj = data.get("project", {})
                if isinstance(proj, dict):
                    if proj.get("module") == module:
                        return p
            except Exception:
                continue

    # Fall back to most recent regardless of module
    return candidates[0] if candidates else None
