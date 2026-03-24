"""
Experience Distillation (XSkill Pattern) - Phase 12 Track 2

Distills experiences from multiple task completions into reusable knowledge chunks.
Groups tasks by type, critiques rollouts, and stores insights for future reuse.

Usage:
    from engram.core.experience import distill_experiences
    
    experiences = distill_experiences(
        session_log=session_log,
        db=vector_db,
        llm_call=llm.chat,
    )
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from .vector_db import VectorDB


# ============================================================================
# CONFIGURATION
# ============================================================================

# Minimum tasks per type to distill
MIN_TASKS_PER_TYPE = 3

# Number of tasks to cluster
N_CLUSTER_TASKS = 20

# Model for critique
CRITIQUE_MODEL = "qwen3:30b-a3b-q4_K_M"


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class Experience:
    """
    Distilled experience from multiple task completions.
    
    Attributes:
        id: Unique identifier
        task_type: Type of task (e.g., "form_validation", "api_endpoint")
        insight: The distilled insight
        quality_score: Average quality of source tasks
        source_tasks: IDs of source tasks
        created_at: When experience was created
    """
    id: str
    task_type: str
    insight: str
    quality_score: float
    source_tasks: List[str]
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "task_type": self.task_type,
            "insight": self.insight,
            "quality_score": self.quality_score,
            "source_tasks": self.source_tasks,
            "created_at": self.created_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Experience":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            task_type=data["task_type"],
            insight=data["insight"],
            quality_score=data.get("quality_score", 0.5),
            source_tasks=data.get("source_tasks", []),
            created_at=data.get("created_at", datetime.now().isoformat()),
        )


# ============================================================================
# PROMPTS
# ============================================================================

CRITIQUE_PROMPT = """
Analyze these {n} task completions of type "{task_type}".

TASKS:
{task_examples}

QUALITY SCORES: {scores}
AVERAGE QUALITY: {avg_score:.2f}

Identify patterns that distinguish high-quality from low-quality completions.

Extract ONE actionable insight that would improve future tasks of this type.

GUIDELINES FOR GOOD INSIGHTS:
- Specific: Name concrete actions, not vague advice
- Actionable: Can be applied immediately to next task
- Non-obvious: Goes beyond "write clean code" platitudes
- Bounded: Applies to this task type, not everything
- Evidence-based: Derived from the actual tasks shown

BAD INSIGHT EXAMPLES (avoid these):
- "Write clean, maintainable code" (too vague)
- "Always test your code" (too obvious)
- "Communicate well with stakeholders" (not actionable here)

GOOD INSIGHT EXAMPLES:
- "For form validation, always validate on client AND server — client gives instant feedback, server prevents bypass"
- "When adding API endpoints, create the test file BEFORE implementation — drives cleaner interface design"

IMPORTANT:
- Base your analysis ONLY on the tasks shown above
- Do not invent patterns not supported by the examples
- Reference specific task numbers when describing patterns (e.g., "Tasks 1 and 3 both...")
- Give more weight to high-quality tasks (score > 0.8) when extracting patterns
- If quality scores vary widely (>0.3 range), focus on what distinguishes high from low

CONSTRAINTS:
- insight: 1-3 sentences, under 200 characters
- pattern: 1-2 sentences describing what you observed
- application: When/where to apply (1 sentence)
- example: Concrete example with code or specific values

Return JSON:
{{
    "insight": "specific actionable insight...",
    "pattern": "what pattern was observed...",
    "application": "when to apply this insight...",
    "example": "brief example of applying the insight",
    "confidence": 0.0-1.0
}}
"""

CLUSTER_PROMPT = """
Group these tasks by type based on SHARED SKILLS and KNOWLEDGE.

TASKS:
{tasks}

MERGE CRITERIA (group together if):
- Same domain knowledge (e.g., authentication, database, UI)
- Same tool usage (e.g., pytest, git, docker)
- Same pattern application (e.g., validation, error handling, caching)

DO NOT MERGE if:
- Only superficial similarity (both involve "forms" but one is UI, one is validation)
- Different primary skill (frontend vs backend vs devops)

Return JSON with task types as keys and task indices as values:
{{
    "form_validation": [0, 3, 7],
    "api_endpoint": [1, 4, 8],
    ...
}}
"""


# ============================================================================
# PHASE 1: CLUSTER BY TASK TYPE
# ============================================================================

def cluster_by_task_type(
    session_log: List[Dict[str, Any]],
    llm_call: Optional[Callable[[str], str]] = None,
    n_tasks: int = N_CLUSTER_TASKS,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Group tasks by type.
    
    Uses simple heuristics first, then LLM for ambiguous cases.
    
    Args:
        session_log: Session logs to cluster
        llm_call: LLM call function (optional)
        n_tasks: Number of recent tasks to cluster
    
    Returns:
        Dictionary of task_type -> list of task entries
    
    Example:
        >>> clusters = cluster_by_task_type(session_log)
        >>> print(f"Found {len(clusters)} task types")
    """
    recent = session_log[-n_tasks:] if len(session_log) >= n_tasks else session_log
    
    if len(recent) < 2:
        return {}
    
    # Simple heuristic clustering based on task text
    clusters: Dict[str, List[Dict[str, Any]]] = {}
    
    for task in recent:
        task_text = task.get("task", "").lower()
        
        # Extract keywords for clustering
        task_type = _extract_task_type(task_text)
        
        if task_type not in clusters:
            clusters[task_type] = []
        
        clusters[task_type].append(task)
    
    # If too many clusters, use LLM to merge similar types
    if len(clusters) > 10 and llm_call:
        clusters = _merge_clusters_with_llm(clusters, llm_call)
    
    return clusters


def _extract_task_type(task_text: str) -> str:
    """Extract task type from task text using heuristics."""
    task_text = task_text.lower()
    
    # Common patterns
    patterns = {
        "form_validation": ["form", "validate", "input", "field"],
        "api_endpoint": ["api", "endpoint", "route", "handler", "request"],
        "database": ["database", "table", "query", "sql", "model"],
        "authentication": ["auth", "login", "register", "password", "token"],
        "testing": ["test", "spec", "assert"],
        "documentation": ["document", "readme", "docstring", "comment"],
        "refactoring": ["refactor", "clean", "simplify", "optimize"],
        "bug_fix": ["fix", "bug", "error", "issue", "broken"],
        "feature": ["implement", "add", "create", "new"],
    }
    
    for task_type, keywords in patterns.items():
        if any(kw in task_text for kw in keywords):
            return task_type
    
    # Fallback: use first few words
    words = task_text.split()[:3]
    return "_".join(words) if words else "unknown"


def _merge_clusters_with_llm(
    clusters: Dict[str, List[Dict[str, Any]]],
    llm_call: Callable[[str], str],
) -> Dict[str, List[Dict[str, Any]]]:
    """Merge similar clusters using LLM."""
    # Build task list for prompt
    task_list = []
    for i, (task_type, tasks) in enumerate(clusters.items()):
        for task in tasks[:3]:  # Sample tasks
            task_text = task.get("task", "")[:100]
            task_list.append(f"[{i}] {task_type}: {task_text}")
    
    prompt = CLUSTER_PROMPT.format(tasks="\n".join(task_list))
    
    try:
        response = llm_call(prompt, model=CRITIQUE_MODEL)
        
        # Parse response
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            grouping = json.loads(json_match.group(0))
            
            # Rebuild clusters
            new_clusters = {}
            task_index = 0
            
            for original_type, tasks in clusters.items():
                for task in tasks:
                    new_type = grouping.get(original_type, original_type)
                    if new_type not in new_clusters:
                        new_clusters[new_type] = []
                    new_clusters[new_type].append(task)
            
            return new_clusters
    except Exception:
        pass
    
    # Return original if merge fails
    return clusters


# ============================================================================
# PHASE 2: CRITIQUE ROLLOUTS
# ============================================================================

def critique_rollouts(
    entries: List[Dict[str, Any]],
    llm_call: Callable[[str], str],
    model: str = CRITIQUE_MODEL,
) -> str:
    """
    Critique multiple task rollouts to extract patterns.
    
    Args:
        entries: Task entries to critique
        llm_call: LLM call function
        model: Model to use
    
    Returns:
        Distilled insight string
    """
    if len(entries) < MIN_TASKS_PER_TYPE:
        return ""
    
    # Format task examples
    task_examples = _format_task_examples(entries)
    
    # Calculate scores
    scores = [e.get("quality_score", 0.5) for e in entries]
    avg_score = sum(scores) / len(scores)
    
    # Build critique prompt
    prompt = CRITIQUE_PROMPT.format(
        n=len(entries),
        task_type=entries[0].get("task", "unknown")[:50],
        task_examples=task_examples,
        scores=scores,
        avg_score=avg_score,
    )
    
    # Call LLM
    try:
        raw_response = llm_call(prompt, model=model)
        
        # Parse response
        result = _parse_critique_response(raw_response)
        
        return result.get("insight", "")
    
    except Exception:
        return ""


def _format_task_examples(entries: List[Dict[str, Any]]) -> str:
    """Format task examples for critique prompt."""
    lines = []
    
    for i, entry in enumerate(entries[:5], 1):  # Limit to 5 examples
        task = entry.get("task", "Unknown")[:100]
        quality = entry.get("quality_score", 0.5)
        reason = entry.get("quality_reason", "")[:50]
        
        lines.append(f"{i}. Task: {task}")
        lines.append(f"   Quality: {quality:.2f}")
        if reason:
            lines.append(f"   Reason: {reason}")
        lines.append("")
    
    return "\n".join(lines)


def _parse_critique_response(raw_response: str) -> Dict[str, Any]:
    """Parse critique response."""
    # Try to extract JSON
    json_match = re.search(r'\{.*\}', raw_response, re.DOTALL)

    if json_match:
        try:
            result = json.loads(json_match.group(0))
            # Add confidence default if not provided (backward compatibility)
            if "confidence" not in result:
                result["confidence"] = 0.5  # Default neutral confidence
            return result
        except json.JSONDecodeError:
            pass

    # Fallback
    return {"insight": raw_response[:200], "confidence": 0.5}


# ============================================================================
# PHASE 3: STORE EXPERIENCE
# ============================================================================

def distill_experiences(
    session_log: List[Dict[str, Any]],
    db: VectorDB,
    llm_call: Callable[[str], str],
    min_tasks: int = MIN_TASKS_PER_TYPE,
    tier: str = "warm",
) -> List[Experience]:
    """
    Distill experiences from session logs.
    
    Args:
        session_log: Session logs to analyze
        db: Vector database to store experiences
        llm_call: LLM call function
        min_tasks: Minimum tasks per type to distill
        tier: Tier to store experiences in
    
    Returns:
        List of distilled experiences
    
    Example:
        >>> experiences = distill_experiences(session_log, db, llm.chat)
        >>> print(f"Distilled {len(experiences)} experiences")
    """
    # Cluster by task type
    clusters = cluster_by_task_type(session_log, llm_call)
    
    experiences = []
    
    for task_type, entries in clusters.items():
        if len(entries) < min_tasks:
            continue
        
        # Critique rollouts
        insight = critique_rollouts(entries, llm_call)
        
        if not insight:
            continue
        
        # Calculate average quality
        quality_scores = [e.get("quality_score", 0.5) for e in entries]
        avg_quality = sum(quality_scores) / len(quality_scores)
        
        # Create experience
        source_ids = [e.get("task_id", str(i)) for i, e in enumerate(entries)]
        
        exp = Experience(
            id=f"exp_{task_type}_{hashlib.md5(task_type.encode()).hexdigest()[:8]}",
            task_type=task_type,
            insight=insight,
            quality_score=avg_quality,
            source_tasks=source_ids,
        )
        
        # Store in database
        _store_experience(db, exp, tier)
        
        experiences.append(exp)
    
    return experiences


def _store_experience(db: VectorDB, exp: Experience, tier: str) -> None:
    """Store experience in vector database."""
    # Create embedding placeholder
    import numpy as np

    # Deterministic pseudo-embedding
    text_hash = hashlib.md5(exp.insight.encode()).hexdigest()
    seed = int(text_hash[:8], 16)
    rng = np.random.RandomState(seed)

    vector = rng.randn(db.dimension)
    vector = vector / np.linalg.norm(vector)

    # Validate embedding dimension matches DB dimension
    expected_dim = db.dimension
    actual_dim = len(vector)
    if actual_dim != expected_dim:
        raise ValueError(
            f"[ENGRAM] experience — embedding dimension mismatch. "
            f"DB expects {expected_dim}-dim, got {actual_dim}-dim. "
            f"Experience '{exp.id}' not stored."
        )

    # Store
    db.insert(
        vector=vector,
        metadata={
            "type": "experience",
            "experience_id": exp.id,
            "task_type": exp.task_type,
            "insight": exp.insight,
            "quality_score": exp.quality_score,
            "source_tasks": exp.source_tasks,
            "tier": tier,
            "created_at": exp.created_at,
        },
        entry_id=exp.id,
    )


# ============================================================================
# EXPERIENCE RETRIEVAL
# ============================================================================

def get_relevant_experiences(
    task_type: str,
    db: VectorDB,
    top_k: int = 3,
) -> List[Experience]:
    """
    Get relevant experiences for a task type.
    
    Args:
        task_type: Type of task
        db: Vector database
        top_k: Number of experiences to return
    
    Returns:
        List of relevant experiences
    """
    # Search by task type in metadata
    experiences = []
    
    for entry_id in db.list_entries():
        entry = db.get(entry_id)
        
        if not entry:
            continue
        
        metadata = entry.metadata
        
        if metadata.get("type") != "experience":
            continue
        
        if metadata.get("task_type") == task_type:
            experiences.append(Experience(
                id=metadata.get("experience_id", entry_id),
                task_type=metadata.get("task_type", ""),
                insight=metadata.get("insight", ""),
                quality_score=metadata.get("quality_score", 0.5),
                source_tasks=metadata.get("source_tasks", []),
                created_at=metadata.get("created_at", ""),
            ))
    
    # Sort by quality score
    experiences.sort(key=lambda e: e.quality_score, reverse=True)
    
    return experiences[:top_k]


# ============================================================================
# BATCH DISTILLATION
# ============================================================================

def run_distillation(
    session_log: List[Dict[str, Any]],
    db: VectorDB,
    llm_call: Callable[[str], str],
    force: bool = False,
) -> Dict[str, Any]:
    """
    Run experience distillation.
    
    Args:
        session_log: Session logs
        db: Vector database
        llm_call: LLM call function
        force: Force distillation even with few tasks
    
    Returns:
        Distillation statistics
    """
    min_tasks = 2 if force else MIN_TASKS_PER_TYPE
    
    experiences = distill_experiences(
        session_log=session_log,
        db=db,
        llm_call=llm_call,
        min_tasks=min_tasks,
    )
    
    return {
        "experiences_created": len(experiences),
        "task_types": list(set(e.task_type for e in experiences)),
        "average_quality": sum(e.quality_score for e in experiences) / len(experiences) if experiences else 0,
    }


# ============================================================================
# CLI COMMAND
# ============================================================================

def cmd_distill(args) -> int:
    """
    CLI command: engram distill --session session_id
    
    Distills experiences from a session.
    """
    from .session import SessionManager
    from .vector_db import VectorDB
    
    print(f"\n{'=' * 60}")
    print("ENGRAM OS - Experience Distillation")
    print(f"{'=' * 60}\n")
    
    # Load session
    manager = SessionManager()
    
    if args.session:
        session = manager.get_session(args.session)
        if not session:
            print(f"✗ Session not found: {args.session}")
            return 1
        session_log = session.state.context_window
    else:
        # Load all recent sessions
        session_log = []
        for session_id in manager.list_sessions()[-10:]:
            session = manager.get_session(session_id)
            if session:
                session_log.extend(session.state.context_window)
    
    if len(session_log) < 5:
        print("⚠ Not enough data for distillation (need 5+ tasks)")
        return 1
    
    print(f"Analyzing {len(session_log)} tasks...")

    # Initialize database with embedder-matching dimension
    db = VectorDB(dimension=384)  # Match all-MiniLM-L6-v2 output
    
    # Mock LLM call for CLI
    def mock_llm_call(prompt, model="qwen3:30b-a3b-q4_K_M"):
        return '{"insight": "Always validate inputs before processing", "pattern": "High quality tasks validate early", "application": "When processing user input"}'
    
    # Run distillation
    stats = run_distillation(
        session_log=session_log,
        db=db,
        llm_call=mock_llm_call,
        force=args.force,
    )
    
    print(f"\nDistilled {stats['experiences_created']} experiences")
    print(f"Task types: {', '.join(stats['task_types'])}")
    print(f"Average quality: {stats['average_quality']:.2f}")
    print()
    
    return 0


def create_distill_parser(subparsers) -> None:
    """Create argument parser for distill command."""
    parser = subparsers.add_parser(
        'distill',
        help='Distill experiences from sessions',
        description='Extract reusable insights from task completions',
    )
    
    parser.add_argument(
        '--session', '-s',
        default=None,
        help='Session ID to analyze (uses recent sessions if not specified)',
    )
    
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force distillation even with few tasks',
    )
    
    parser.set_defaults(func=cmd_distill)


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(
        description='ENGRAM OS - Experience Distillation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python -m engram.core.experience distill --session abc123
  python -m engram.core.experience distill --force
        ''',
    )
    
    create_distill_parser(parser)
    args = parser.parse_args()
    
    exit(args.func(args))
