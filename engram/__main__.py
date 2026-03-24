"""
ENGRAM OS - CLI Entry Point

Enables running ENGRAM CLI via:
    python -m engram <command>
"""

from engram.cli.main import main
import sys

sys.exit(main())
