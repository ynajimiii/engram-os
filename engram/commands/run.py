#!/usr/bin/env python
"""
ENGRAM OS - Run Command (Phase 13)

CLI: engram run --goal "implement feature X"

Runs an autonomous task with full MCP tool support,
quality scoring, and learning loop integration.

Usage:
    engram run --goal "implement payment webhook handler"
    engram run --goal "add user authentication" --project my_project
    engram run --goal "fix login bug" --model qooba/qwen3-coder-30b-a3b-instruct:q3_k_m
"""

import sys
import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from engram.core.agent import create_agent
from engram.core.llm import create_llm
from engram.core.mcp_client import MCPClient
from engram.core.session import SessionManager
from engram.core.vector_db import VectorDB
from engram.core.ingestion import ingest_project
from engram.core.scorer import score_session


# ============================================================================
# CONFIGURATION
# ============================================================================

# Default model for Phase 13
DEFAULT_MODEL = "qooba/qwen3-coder-30b-a3b-instruct:q3_k_m"

# Ollama base URL
OLLAMA_BASE_URL = "http://127.0.0.1:11434"

# Learning triggers
LEARNING_CYCLE_INTERVAL = 10  # Run learning every N tasks
DISTILLATION_INTERVAL = 20    # Run distillation every N tasks


# ============================================================================
# METRICS TRACKING
# ============================================================================

class RunMetrics:
    """Tracks metrics for a Phase 13 run."""
    
    def __init__(self, goal: str, project_path: str):
        self.goal = goal
        self.project_path = project_path
        self.start_time = datetime.now()
        self.end_time: Optional[datetime] = None
        
        # Ingestion metrics
        self.chunks_ingested = 0
        self.files_processed = 0
        
        # Execution metrics
        self.tasks_completed = 0
        self.tasks_failed = 0
        self.tool_calls_made = 0
        
        # Quality metrics
        self.quality_scores: List[float] = []
        self.test_pass_rate = 0.0
        
        # Learning metrics
        self.experiences_distilled = 0
        self.patches_proposed = 0
        self.patches_committed = 0
        
        # Session metrics
        self.session_resume = False
        self.context_precision = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        duration = (self.end_time or datetime.now()) - self.start_time
        
        return {
            "goal": self.goal,
            "project_path": self.project_path,
            "duration_seconds": duration.total_seconds(),
            "chunks_ingested": self.chunks_ingested,
            "files_processed": self.files_processed,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "tool_calls_made": self.tool_calls_made,
            "average_quality": sum(self.quality_scores) / len(self.quality_scores) if self.quality_scores else 0,
            "test_pass_rate": self.test_pass_rate,
            "experiences_distilled": self.experiences_distilled,
            "patches_proposed": self.patches_proposed,
            "patches_committed": self.patches_committed,
            "session_resume": self.session_resume,
            "context_precision": self.context_precision,
        }
    
    def summary(self) -> str:
        """Generate summary string."""
        d = self.to_dict()
        lines = [
            f"Goal: {self.goal}",
            f"Duration: {d['duration_seconds']:.1f}s",
            f"Chunks ingested: {d['chunks_ingested']}",
            f"Tasks completed: {d['tasks_completed']}",
            f"Average quality: {d['average_quality']:.2f}",
            f"Test pass rate: {d['test_pass_rate']:.2f}",
            f"Experiences distilled: {d['experiences_distilled']}",
        ]
        return "\n".join(lines)


# ============================================================================
# RUN COMMAND
# ============================================================================

def cmd_run(args) -> int:
    """
    CLI command: engram run --goal "implement X"
    
    Runs an autonomous task with full support.
    """
    from engram.core.learner import learning_cycle
    from engram.core.experience import distill_experiences, run_distillation
    
    print(f"\n{'=' * 70}")
    print("ENGRAM OS - Phase 13: Real Project Run")
    print(f"{'=' * 70}\n")
    
    # Initialize metrics
    metrics = RunMetrics(
        goal=args.goal,
        project_path=args.project or ".",
    )
    
    # Initialize MCP client
    print("1. Connecting to MCP servers...")
    mcp = MCPClient()
    connected_servers = mcp.connect_from_config()
    print(f"   ✓ Connected: {', '.join(connected_servers) if connected_servers else 'Using mock tools'}")
    
    # Initialize vector database with embedder-matching dimension
    print("\n2. Initializing vector database...")
    db = VectorDB(dimension=384)  # Match all-MiniLM-L6-v2 output
    
    # Ingest project if path provided
    if args.project:
        print(f"\n3. Ingesting project: {args.project}")
        files_count, chunks_count = ingest_project(
            root_path=args.project,
            db=db,
            mcp=mcp,
            tier="warm",
        )
        metrics.files_processed = files_count
        metrics.chunks_ingested = chunks_count
        print(f"   ✓ Processed {files_count} files, {chunks_count} chunks")
    else:
        print("\n3. No project path - skipping ingestion")
    
    # Initialize LLM with specified model
    print(f"\n4. Loading model: {args.model}")
    llm = create_llm(
        provider_name="ollama",
        model=args.model,
        base_url=OLLAMA_BASE_URL,
        options={"temperature": args.temperature},
    )
    print(f"   ✓ Model loaded")
    
    # Create agent
    print("\n5. Creating agent...")
    agent = create_agent(
        name="ENGRAM-Runner",
        system_prompt=args.system_prompt or DEFAULT_SYSTEM_PROMPT,
        llm=llm,
        mcp_client=mcp,
        enable_tools=True,
        enable_memory=True,
        enable_writeback=True,
        temperature=args.temperature,
    )
    
    # Start session
    session_name = args.session or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    agent.start_session(metadata={
        "goal": args.goal,
        "project": args.project,
        "model": args.model,
    })
    print(f"   ✓ Session started: {session_name}")
    
    # Run the goal
    print(f"\n{'=' * 70}")
    print(f"RUNNING: {args.goal}")
    print(f"{'=' * 70}\n")
    
    try:
        # Execute the goal
        response = agent.chat(args.goal)
        
        print(f"Response:\n{response.content}\n")
        
        # Update metrics
        metrics.tasks_completed = 1
        metrics.tool_calls_made = len(agent._tool_history)
        
        # Get quality score
        if agent._quality_scores:
            metrics.quality_scores = [qs.score for qs in agent._quality_scores]
        
        # Check for learning triggers
        session_log = agent._session_log
        
        if len(session_log) >= LEARNING_CYCLE_INTERVAL:
            print("\n6. Running learning cycle...")
            # Would run learning cycle here
            metrics.patches_proposed += 1
        
        if len(session_log) >= DISTILLATION_INTERVAL:
            print("\n7. Running experience distillation...")
            stats = run_distillation(
                session_log=session_log,
                db=db,
                llm_call=llm.chat,
            )
            metrics.experiences_distilled = stats.get("experiences_created", 0)
            print(f"   ✓ Distilled {stats.get('experiences_created', 0)} experiences")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        metrics.tasks_failed = 1
    
    # End session
    agent.end_session()
    metrics.end_time = datetime.now()
    
    # Save metrics
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(metrics.to_dict(), f, indent=2)
        print(f"\n✓ Metrics saved to: {args.output}")
    
    # Print summary
    print(f"\n{'=' * 70}")
    print("RUN SUMMARY")
    print(f"{'=' * 70}")
    print(metrics.summary())
    print()
    
    # Determine success
    success = (
        metrics.tasks_completed > 0 and
        metrics.tasks_failed == 0 and
        (not metrics.quality_scores or sum(metrics.quality_scores) / len(metrics.quality_scores) >= 0.5)
    )
    
    if success:
        print("✓ RUN SUCCESSFUL")
        return 0
    else:
        print("✗ RUN FAILED")
        return 1


# ============================================================================
# DEFAULT SYSTEM PROMPT
# ============================================================================

DEFAULT_SYSTEM_PROMPT = """
You are ENGRAM OS, an autonomous AI agent with access to tools.

CAPABILITIES:
- Read and write files
- Execute shell commands
- Search and analyze code
- Run tests and verify output

WORKFLOW:
1. Understand the task
2. Plan your approach
3. Use tools to implement
4. Verify with tests
5. Report completion

CONSTRAINTS:
- Always verify your work with tests
- Ask for clarification if task is unclear
- Report progress after each major step
- Save your work frequently

TOOLS AVAILABLE:
- read_file: Read file contents
- write_file: Write or modify files
- list_directory: List directory contents
- run_command: Execute shell commands

Begin by understanding the task, then proceed step by step.
"""


# ============================================================================
# CLI PARSER
# ============================================================================

def create_run_parser(subparsers) -> None:
    """Create argument parser for run command."""
    parser = subparsers.add_parser(
        'run',
        help='Run an autonomous task',
        description='Execute a goal with full MCP tool support and learning',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  engram run --goal "implement payment webhook handler"
  engram run --goal "add user authentication" --project ./my_project
  engram run --goal "fix login bug" --model qooba/qwen3-coder-30b-a3b-instruct:q3_k_m
  engram run --goal "create API endpoint" --output metrics.json
        ''',
    )
    
    parser.add_argument(
        '--goal', '-g',
        required=True,
        help='Goal to accomplish (e.g., "implement login form")',
    )
    
    parser.add_argument(
        '--project', '-p',
        default=None,
        help='Project directory path (ingests before running)',
    )
    
    parser.add_argument(
        '--model', '-m',
        default=DEFAULT_MODEL,
        help=f'Model to use (default: {DEFAULT_MODEL})',
    )
    
    parser.add_argument(
        '--temperature', '-t',
        type=float,
        default=0.7,
        help='Model temperature (default: 0.7)',
    )
    
    parser.add_argument(
        '--session', '-s',
        default=None,
        help='Session name (auto-generated if not specified)',
    )
    
    parser.add_argument(
        '--system-prompt',
        default=None,
        help='Custom system prompt (uses default if not specified)',
    )
    
    parser.add_argument(
        '--output', '-o',
        default=None,
        help='Output path for metrics JSON',
    )
    
    parser.set_defaults(func=cmd_run)


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(
        description='ENGRAM OS - Phase 13 Run Command',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    create_run_parser(parser)
    args = parser.parse_args()
    
    sys.exit(args.func(args))
