#!/usr/bin/env python
"""
ENGRAM OS - Command Line Interface

Usage:
    engram <command> [options]

Commands:
    run      - Run an autonomous task (Phase 13)
    new      - Create a new project (Phase 13)
    ingest   - Ingest a project into vector DB (Phase 10)
    score    - Score a session (Phase 11)
    learn    - Run learning cycle (Phase 12)
    distill  - Distill experiences (Phase 12)

Examples:
    engram run --goal "implement login form" --model qooba/qwen3-coder-30b-a3b-instruct:q3_k_m
    engram new --project my_project --module coding
    engram ingest --path ./my_project
    engram score --session abc123
"""

import sys
import argparse


def main():
    """Main entry point for ENGRAM CLI."""
    parser = argparse.ArgumentParser(
        prog='engram',
        description='ENGRAM OS - Cognitive Architecture for AI Agents',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Phase 13 Commands:
  run      Run an autonomous task with full MCP support
  new      Create a new ENGRAM project

Phase 12 Commands:
  learn    Run learning cycle for module improvement
  distill  Distill experiences from sessions

Phase 11 Commands:
  score    Score a session's quality

Phase 10 Commands:
  ingest   Ingest a project into vector database

Examples:
  engram run --goal "implement payment webhook" --model qooba/qwen3-coder-30b-a3b-instruct:q3_k_m
  engram new --project auth_system --module coding
  engram ingest --path ./my_project --tier warm
  engram score --session session_abc123
  engram learn --module coding
  engram distill --session session_xyz789
        ''',
    )
    
    # Create subparsers
    subparsers = parser.add_subparsers(
        dest='command',
        title='commands',
        description='Available commands',
    )
    
    # Import and register commands
    from engram.commands.run import create_run_parser
    from engram.commands.new import create_new_parser
    from engram.commands.ingest import create_ingest_parser
    from engram.core.scorer import create_score_parser
    from engram.core.learner import create_learn_parser
    from engram.core.experience import create_distill_parser
    
    create_run_parser(subparsers)
    create_new_parser(subparsers)
    create_ingest_parser(subparsers)
    create_score_parser(subparsers)
    create_learn_parser(subparsers)
    create_distill_parser(subparsers)
    
    # Parse arguments
    args = parser.parse_args()
    
    # Execute command
    if hasattr(args, 'func'):
        return args.func(args)
    else:
        parser.print_help()
        return 0


if __name__ == '__main__':
    sys.exit(main())
