"""
ENGRAM OS CLI - Main Dispatcher

Main CLI entry point. Registers all subcommands and dispatches
to the right handler.

Usage:
    python -m engram <command>
    engram <command>  (after pip install -e .)
"""

import sys
import argparse

from engram.cli._display import banner


def main() -> int:
    """Main entry point for ENGRAM CLI."""
    parser = argparse.ArgumentParser(
        prog="engram",
        description=(
            "ENGRAM OS — Cognitive OS for autonomous "
            "long-horizon AI execution"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  engram doctor      Check system health
  engram init        Set up a new project
  engram run         Execute a goal
  engram code        Execute a coding task
  engram score       Inject human corrections or view stats
  engram learn       Trigger learning cycle or view history
  engram experience  View and search distilled experiences
  engram rubric      View and compare scoring rubrics
  engram status      Show session state
  engram session     Manage sessions
  engram module      Manage modules
  engram config      View/set configuration
  engram export      Export session report
  engram benchmark   Run benchmark suite

Quick start:
  engram doctor
  engram init
  engram code "implement login form"
  engram learn --history
        """
    )

    parser.add_argument(
        "--version", action="version",
        version="ENGRAM OS 0.1.0"
    )

    subparsers = parser.add_subparsers(
        dest="command",
        metavar="<command>"
    )

    # Register all commands
    from engram.cli import (
        doctor_command,
        init_command,
        run_command,
        status_command,
        session_command,
        module_command,
        config_command,
        export_command,
        benchmark_command,
        code_command,
        score_command,
        learn_command,
        experience_command,
        rubric_command,
    )

    doctor_command.register(subparsers)
    init_command.register(subparsers)
    run_command.register(subparsers)
    status_command.register(subparsers)
    session_command.register(subparsers)
    module_command.register(subparsers)
    config_command.register(subparsers)
    export_command.register(subparsers)
    benchmark_command.register(subparsers)
    code_command.register(subparsers)
    score_command.register(subparsers)
    learn_command.register(subparsers)
    experience_command.register(subparsers)
    rubric_command.register(subparsers)

    args = parser.parse_args()

    if not args.command:
        banner()
        parser.print_help()
        return 0

    if not hasattr(args, "func"):
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
