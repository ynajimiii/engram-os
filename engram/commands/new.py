#!/usr/bin/env python
"""
ENGRAM OS - New Command (Phase 13)

CLI: engram new --project my_project --module coding

Bootstraps a new ENGRAM project with configuration and structure.

Usage:
    engram new --project my_project --module coding
    engram new --project auth_system --module coding --ingest
"""

import sys
import argparse
import os
import yaml
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


def cmd_new(args) -> int:
    """
    CLI command: engram new --project name --module coding
    
    Bootstraps a new ENGRAM project.
    """
    print(f"\n{'=' * 70}")
    print("ENGRAM OS - New Project")
    print(f"{'=' * 70}\n")
    
    project_name = args.project
    project_path = Path(args.path) / project_name if args.path else Path(project_name)
    
    # Create project structure
    print(f"1. Creating project structure: {project_path}")
    
    directories = [
        project_path,
        project_path / "engram_sessions",
        project_path / "engram_config",
        project_path / "src",
        project_path / "tests",
    ]
    
    for dir_path in directories:
        dir_path.mkdir(parents=True, exist_ok=True)
        print(f"   ✓ Created: {dir_path}")
    
    # Create configuration files
    print(f"\n2. Creating configuration files...")
    
    # Project config
    project_config = {
        "name": project_name,
        "module": args.module,
        "created_at": datetime.now().isoformat(),
        "model": args.model,
        "settings": {
            "enable_tools": True,
            "enable_memory": True,
            "enable_learning": True,
            "learning_interval": 10,
            "distillation_interval": 20,
        },
        "paths": {
            "sessions": "engram_sessions",
            "config": "engram_config",
            "source": "src",
            "tests": "tests",
        },
    }
    
    config_path = project_path / "engram_config" / "project.yaml"
    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(project_config, f, indent=2)
    print(f"   ✓ Created: {config_path}")
    
    # MCP config (copy from template)
    mcp_config_path = project_path / "engram_config" / "mcp_servers.yaml"
    default_mcp_config = """
# MCP Servers Configuration for {project_name}

servers:
  filesystem:
    command: "npx"
    args:
      - "@modelcontextprotocol/server-filesystem"
      - "{project_root}"
    enabled: true

  shell:
    command: "echo"
    args:
      - "mock_shell"
    enabled: true
    use_mock: true

settings:
  tool_timeout: 60
  max_tool_calls_per_task: 10
  log_tool_calls: true
  use_mock_fallback: true
""".format(project_name=project_name, project_root=str(project_path.absolute()))
    
    with open(mcp_config_path, 'w', encoding='utf-8') as f:
        f.write(default_mcp_config)
    print(f"   ✓ Created: {mcp_config_path}")
    
    # Create README
    readme_path = project_path / "README.md"
    readme_content = f"""# {project_name}

ENGRAM OS Project

## Configuration

- **Module**: {args.module}
- **Model**: {args.model}
- **Created**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Usage

```bash
# Run a task
engram run --goal "implement feature X" --project {project_path}

# Ingest project
engram ingest --path {project_path}

# View metrics
engram metrics --project {project_path}
```

## Structure

```
{project_name}/
├── engram_config/
│   ├── project.yaml
│   └── mcp_servers.yaml
├── engram_sessions/
├── src/
└── tests/
```
"""
    
    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(readme_content)
    print(f"   ✓ Created: {readme_path}")
    
    # Create .gitignore
    gitignore_path = project_path / ".gitignore"
    gitignore_content = """
# ENGRAM OS
engram_sessions/
engram_config/*.local.yaml
*.pyc
__pycache__/

# Python
venv/
.env
*.egg-info/

# IDE
.vscode/
.idea/
*.swp
"""
    
    with open(gitignore_path, 'w', encoding='utf-8') as f:
        f.write(gitignore_content)
    print(f"   ✓ Created: {gitignore_path}")
    
    # Ingest if requested
    if args.ingest:
        print(f"\n3. Ingesting project...")
        from engram.core.mcp_client import MCPClient
        from engram.core.vector_db import VectorDB
        from engram.core.ingestion import ingest_project
        
        mcp = MCPClient()
        mcp.connect_from_config()

        db = VectorDB(dimension=384)  # Match all-MiniLM-L6-v2 output
        
        files_count, chunks_count = ingest_project(
            root_path=str(project_path),
            db=db,
            mcp=mcp,
            tier="warm",
        )
        
        print(f"   ✓ Ingested {files_count} files, {chunks_count} chunks")
    
    # Summary
    print(f"\n{'=' * 70}")
    print("PROJECT CREATED")
    print(f"{'=' * 70}")
    print(f"Name: {project_name}")
    print(f"Path: {project_path.absolute()}")
    print(f"Module: {args.module}")
    print(f"Model: {args.model}")
    print(f"\nNext steps:")
    print(f"  cd {project_name}")
    print(f"  engram run --goal \"implement your first feature\"")
    print()
    
    return 0


def create_new_parser(subparsers) -> None:
    """Create argument parser for new command."""
    parser = subparsers.add_parser(
        'new',
        help='Create a new ENGRAM project',
        description='Bootstrap a new ENGRAM project with configuration',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  engram new --project my_project --module coding
  engram new --project auth_system --module coding --ingest
  engram new --project api --module coding --model qooba/qwen3-coder-30b-a3b-instruct:q3_k_m
        ''',
    )
    
    parser.add_argument(
        'project',
        help='Project name',
    )
    
    parser.add_argument(
        '--module', '-m',
        default='coding',
        choices=['coding', 'marketing'],
        help='Module to use (default: coding)',
    )
    
    parser.add_argument(
        '--model',
        default='qooba/qwen3-coder-30b-a3b-instruct:q3_k_m',
        help='Default model for this project',
    )
    
    parser.add_argument(
        '--path', '-p',
        default='.',
        help='Parent directory for project (default: current directory)',
    )
    
    parser.add_argument(
        '--ingest', '-i',
        action='store_true',
        help='Ingest project after creation',
    )
    
    parser.set_defaults(func=cmd_new)


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='ENGRAM OS - New Project Command',
    )
    
    create_new_parser(parser)
    args = parser.parse_args()
    
    sys.exit(args.func(args))
