"""
ENGRAM OS CLI - Config Command

Get and set persistent configuration values stored in
~/.engram/config.yaml. Adapts ENGRAM to different hardware
and preferences without code changes.

Usage:
    engram config show
    engram config set model qwen2.5:27b
    engram config set n_ctx 4096
    engram config get model
    engram config reset
"""

import sys
import argparse

from engram.cli._display import (
    ok, fail, info, section, header, footer, divider
)
from engram.cli._config import (
    load_config, save_config, set_value,
    DEFAULT_CONFIG, CONFIG_PATH
)


CONFIG_GROUPS = {
    "Inference": ["model", "router_model", "ollama_url",
                  "lmstudio_url", "tool_backend"],
    "Memory":    ["weights_mb", "n_ctx", "scratch_mb"],
    "Paths":     ["sessions_dir"],
    "Behavior":  ["default_module", "verbose", "color"],
}


def config_show() -> int:
    """Show all configuration values."""
    config = load_config()
    header("Configuration")
    info(f"File: {CONFIG_PATH}")
    for group, keys in CONFIG_GROUPS.items():
        section(group)
        for key in keys:
            val = config.get(key, DEFAULT_CONFIG.get(key, "?"))
            print(f"    {key:<20} {val}")
    print()
    return 0


def config_get(key: str) -> int:
    """Get a configuration value."""
    config = load_config()
    if key not in DEFAULT_CONFIG:
        fail(
            f"Unknown key: '{key}'",
            f"Valid keys: {', '.join(DEFAULT_CONFIG.keys())}"
        )
        return 1
    print(config.get(key, DEFAULT_CONFIG[key]))
    return 0


def config_set(key: str, value: str) -> int:
    """Set a configuration value."""
    try:
        # Type coercion
        expected = DEFAULT_CONFIG.get(key)
        if isinstance(expected, bool):
            typed_val = value.lower() in ("true", "1", "yes")
        elif isinstance(expected, int):
            typed_val = int(value)
        else:
            typed_val = value
        set_value(key, typed_val)
        ok(f"{key} = {typed_val}")
        return 0
    except (KeyError, ValueError) as e:
        fail(str(e))
        return 1


def config_reset() -> int:
    """Reset configuration to defaults."""
    save_config(DEFAULT_CONFIG)
    ok("Configuration reset to defaults")
    return 0


def register(subparsers) -> None:
    """Register config command with argument parser."""
    p = subparsers.add_parser(
        "config",
        help="View and modify ENGRAM configuration"
    )
    sub = p.add_subparsers(dest="config_cmd")
    sub.add_parser("show", help="Show all config values")
    g = sub.add_parser("get", help="Get a config value")
    g.add_argument("key")
    s = sub.add_parser("set", help="Set a config value")
    s.add_argument("key")
    s.add_argument("value")
    sub.add_parser("reset", help="Reset to defaults")

    def dispatch(args):
        cmd = args.config_cmd
        if cmd == "show":  return config_show()
        if cmd == "get":   return config_get(args.key)
        if cmd == "set":   return config_set(args.key, args.value)
        if cmd == "reset": return config_reset()
        p.print_help()
        return 1

    p.set_defaults(func=lambda args: sys.exit(dispatch(args)))
