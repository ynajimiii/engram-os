"""
ENGRAM OS CLI - Module Command

Lists available modules, shows their capabilities,
and provides extension guidance for custom modules.

Usage:
    engram module list
    engram module info coding
    engram module validate /path/to/custom/module
"""

import sys
import argparse
import importlib
from pathlib import Path

from engram.cli._display import (
    ok, fail, warn, info, section, header, footer, divider
)


MODULES_DIR = Path(__file__).parent.parent / "modules"

KNOWN_MODULES = {
    "coding": {
        "description": "Software development, API design, debugging",
        "extensions": ".py .ts .tsx .js .yaml .sql .md",
    },
    "marketing": {
        "description": "Brand copy, campaigns, content strategy",
        "extensions": ".md .txt .csv .yaml",
    },
    "seo": {
        "description": "Keyword research, audits, content briefs",
        "extensions": ".csv .json .md .txt .yaml",
    },
}


def module_list() -> int:
    """List available modules."""
    header("Available Modules")
    print()
    for name, meta in KNOWN_MODULES.items():
        mod_dir = MODULES_DIR / name
        installed = (
            (mod_dir / "scratch_template.yaml").exists()
            and (mod_dir / "agent_system_prompt.md").exists()
        )
        status = ok if installed else fail
        print(f"  {name}")
        info(f"    {meta['description']}")
        info(f"    Extensions: {meta['extensions']}")
        if installed:
            info("    Status: ✓ installed")
        else:
            info("    Status: ✗ not installed")
        print()

    info("To use:   engram run --module <name> --goal \"...\"")
    info("To build: create engram/modules/<name>/")
    info("          with scratch_template.yaml +")
    info("               agent_system_prompt.md +")
    info("               ingestion/chunkers.py")
    print()
    return 0


def module_info(name: str) -> int:
    """Show module details."""
    mod_dir = MODULES_DIR / name
    if not mod_dir.exists():
        fail(f"Module not found: {name}")
        return 1
    header(f"Module: {name}")

    template = mod_dir / "scratch_template.yaml"
    prompt   = mod_dir / "agent_system_prompt.md"
    chunkers = mod_dir / "ingestion" / "chunkers.py"

    section("Files")
    if template.exists():
        ok("scratch_template.yaml")
    else:
        fail("scratch_template.yaml missing")
    if prompt.exists():
        ok("agent_system_prompt.md")
    else:
        fail("agent_system_prompt.md missing")
    if chunkers.exists():
        ok("ingestion/chunkers.py")
    else:
        warn("ingestion/chunkers.py missing "
             "(ingestion disabled for this module)")

    if template.exists():
        import yaml
        section("Scratch Template Fields")
        with open(template) as f:
            tmpl = yaml.safe_load(f) or {}
        for key in tmpl.keys():
            info(f"  {key}")
    return 0


def module_validate(path: str) -> int:
    """Validate a custom module."""
    mod_path = Path(path)
    header(f"Validating Module: {mod_path.name}")
    errors = 0

    required = [
        "scratch_template.yaml",
        "agent_system_prompt.md",
    ]
    for req in required:
        f = mod_path / req
        if f.exists():
            ok(f"{req}: found")
        else:
            fail(f"{req}: missing")
            errors += 1

    prompt_file = mod_path / "agent_system_prompt.md"
    if prompt_file.exists():
        content = prompt_file.read_text()
        required_sections = [
            "IDENTITY", "SCRATCH NOTE PROTOCOL",
            "TASK INTAKE FORMAT", "WRITEBACK BLOCK FORMAT",
            "CONVENTIONS"
        ]
        section("Prompt Sections")
        for sec in required_sections:
            if sec.upper() in content.upper():
                ok(f"{sec}")
            else:
                fail(f"{sec}: missing")
                errors += 1

    print()
    if errors == 0:
        footer("ok", "Module is valid")
    else:
        footer("fail", f"{errors} issue(s) found")
    return 0 if errors == 0 else 1


def register(subparsers) -> None:
    """Register module command with argument parser."""
    p = subparsers.add_parser("module", help="Manage modules")
    sub = p.add_subparsers(dest="module_cmd")
    sub.add_parser("list", help="List available modules")
    i = sub.add_parser("info", help="Show module details")
    i.add_argument("name")
    v = sub.add_parser("validate",
                        help="Validate a custom module")
    v.add_argument("path")

    def dispatch(args):
        cmd = args.module_cmd
        if cmd == "list":     return module_list()
        if cmd == "info":     return module_info(args.name)
        if cmd == "validate": return module_validate(args.path)
        p.print_help()
        return 1

    p.set_defaults(func=lambda args: sys.exit(dispatch(args)))
