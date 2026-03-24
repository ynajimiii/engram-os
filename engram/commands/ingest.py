#!/usr/bin/env python
"""
ENGRAM OS - Ingest Command

CLI: engram ingest --path /path/to/project

Ingests a project into the vector database for semantic search.
"""

import sys
import argparse

from engram.core.ingestion import cmd_ingest, create_ingest_parser


def main():
    """Main entry point for ingest command."""
    parser = argparse.ArgumentParser(
        prog='engram ingest',
        description='Ingest a project into the vector database',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  engram ingest --path /path/to/project
  engram ingest --path ./my_project --tier warm
  engram ingest --path ./my_project --test-search
        ''',
    )
    
    create_ingest_parser(parser)
    args = parser.parse_args()
    
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
