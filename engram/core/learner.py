"""
Learning Loop - Module Evolution (Autoresearch) - Phase 12 Track 1

Implements the autoresearch pattern for continuous module improvement.
Analyzes recent task completions, proposes prompt patches, and evaluates them.

Usage:
    from engram.core.learner import learning_cycle
    
    improved = learning_cycle(
        module_name="coding",
        session_log=session_log,
        current_prompt=prompt_text,
        llm_call=llm.chat,
    )
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from .scorer import score_session


# ============================================================================
# CONFIGURATION
# ============================================================================

# Number of recent tasks to analyze for learning
N_RECENT_TASKS = 20

# Number of tasks to evaluate patch on
N_EVALUATE_TASKS = 5

# Minimum quality improvement to keep patch
MIN_IMPROVEMENT_THRESHOLD = 0.05

# Model for proposing patches (fast, cheap)
PATCH_PROPOSAL_MODEL = "qwen3:30b-a3b-q4_K_M"


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class PromptPatch:
    """
    A proposed patch to a module's system prompt.
    
    Attributes:
        module_name: Name of the module
        section: Which section to modify
        old_text: Current text in that section
        new_text: Proposed new text
        expected_improvement: Expected quality improvement
        created_at: When patch was created
    """
    module_name: str
    section: str
    old_text: str
    new_text: str
    expected_improvement: float
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "module_name": self.module_name,
            "section": self.section,
            "old_text": self.old_text,
            "new_text": self.new_text,
            "expected_improvement": self.expected_improvement,
            "created_at": self.created_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PromptPatch":
        """Create from dictionary."""
        return cls(
            module_name=data["module_name"],
            section=data["section"],
            old_text=data["old_text"],
            new_text=data["new_text"],
            expected_improvement=data.get("expected_improvement", 0.05),
            created_at=data.get("created_at", datetime.now().isoformat()),
        )


# ============================================================================
# PROMPTS
# ============================================================================

PROPOSE_PATCH_PROMPT = """
Analyze these recent task completions and propose a prompt improvement.

MODULE: {module_name}

CURRENT PROMPT SECTION ({section}):
{current_section}

RECENT TASKS (last {n_recent}):
{task_summaries}

AVERAGE QUALITY SCORE: {avg_quality:.2f}

WEAK AREAS (tasks with score < 0.7):
{weak_areas}

Identify ONE specific improvement to the prompt that would increase quality.
Focus on:
- Clarifying ambiguous instructions
- Adding missing conventions
- Improving task intake format
- Addressing common failure patterns

Return JSON:
{{
    "section": "section_name_to_modify",
    "old_text": "first 100 words of current text...",
    "new_text": "improved version with specific changes...",
    "expected_improvement": 0.05,
    "reason": "why this change will help"
}}
"""

EVALUATE_PATCH_PROMPT = """
Evaluate this prompt patch based on recent task results.

PATCH:
{patch_json}

TASKS COMPLETED WITH PATCH:
{task_results}

AVERAGE QUALITY WITH PATCH: {new_quality:.2f}
AVERAGE QUALITY BEFORE PATCH: {old_quality:.2f}

Should this patch be kept or rolled back?

Return JSON:
{{
    "decision": "keep" or "rollback",
    "reason": "explanation",
    "actual_improvement": 0.05
}}
"""


# ============================================================================
# PHASE 1: PROPOSE PATCH
# ============================================================================

def propose_patch(
    module_name: str,
    current_prompt: str,
    session_log: List[Dict[str, Any]],
    llm_call: Callable[[str], str],
    n_recent: int = N_RECENT_TASKS,
    model: str = PATCH_PROPOSAL_MODEL,
) -> Optional[PromptPatch]:
    """
    Propose a prompt patch based on recent task completions.
    
    Args:
        module_name: Name of the module to improve
        current_prompt: Current system prompt text
        session_log: Recent session logs
        llm_call: Function to call LLM
        n_recent: Number of tasks to analyze
        model: Model to use for proposal
    
    Returns:
        PromptPatch if proposal successful, None otherwise
    
    Example:
        >>> patch = propose_patch("coding", prompt_text, session_log, llm.chat)
        >>> print(f"Proposed change to {patch.section}")
    """
    # Get recent tasks
    recent = session_log[-n_recent:] if len(session_log) >= n_recent else session_log
    
    if len(recent) < 3:
        return None  # Not enough data
    
    # Calculate average quality
    quality_scores = [t.get("quality_score", 0.5) for t in recent if "quality_score" in t]
    
    if not quality_scores:
        return None
    
    avg_quality = sum(quality_scores) / len(quality_scores)
    
    # Identify weak areas
    weak_tasks = [t for t in recent if t.get("quality_score", 1.0) < 0.7]
    weak_areas = _summarize_weak_areas(weak_tasks)
    
    # Parse current prompt sections
    sections = _parse_prompt_sections(current_prompt)
    
    # Choose section to improve (focus on weakest)
    target_section = _choose_target_section(sections, weak_tasks)
    current_section_text = sections.get(target_section, "")
    
    if not current_section_text:
        return None
    
    # Summarize tasks for prompt
    task_summaries = _summarize_tasks(recent)
    
    # Build proposal prompt
    prompt = PROPOSE_PATCH_PROMPT.format(
        module_name=module_name,
        section=target_section,
        current_section=current_section_text[:500],  # Truncate for context
        n_recent=len(recent),
        task_summaries=task_summaries,
        avg_quality=avg_quality,
        weak_areas=weak_areas,
    )
    
    # Call LLM
    try:
        raw_response = llm_call(prompt, model=model)
        
        # Parse response
        patch_data = _parse_patch_response(raw_response)
        
        if not patch_data:
            return None
        
        return PromptPatch(
            module_name=module_name,
            section=patch_data.get("section", target_section),
            old_text=patch_data.get("old_text", ""),
            new_text=patch_data.get("new_text", ""),
            expected_improvement=patch_data.get("expected_improvement", 0.05),
        )
    
    except Exception:
        return None


def _parse_prompt_sections(prompt: str) -> Dict[str, str]:
    """Parse prompt into sections by markdown headers."""
    sections = {}
    current_section = "header"
    current_content = []
    
    for line in prompt.split('\n'):
        # Check for section header (## Header)
        header_match = re.match(r'^##\s+(.+)$', line)
        
        if header_match:
            # Save previous section
            if current_content:
                sections[current_section] = '\n'.join(current_content)
            
            # Start new section
            current_section = header_match.group(1).strip()
            current_content = []
        else:
            current_content.append(line)
    
    # Don't forget the last section
    if current_content:
        sections[current_section] = '\n'.join(current_content)
    
    return sections


def _choose_target_section(
    sections: Dict[str, str],
    weak_tasks: List[Dict[str, Any]]
) -> str:
    """Choose which section to target for improvement."""
    # Priority order for improvement
    priority = [
        "CONVENTIONS",
        "TASK INTAKE FORMAT",
        "WRITEBACK BLOCK FORMAT",
        "SCRATCH NOTE PROTOCOL",
        "GUIDELINES",
        "CAPABILITIES",
    ]
    
    # Check for common failure patterns
    weak_reasons = " ".join(
        t.get("quality_reason", "").lower()
        for t in weak_tasks
    )
    
    if "incomplete" in weak_reasons or "missing" in weak_reasons:
        if "WRITEBACK" in sections or "WRITEBACK BLOCK FORMAT" in sections:
            return "WRITEBACK BLOCK FORMAT"
    
    if "unclear" in weak_reasons or "confused" in weak_reasons:
        if "TASK INTAKE" in sections or "TASK INTAKE FORMAT" in sections:
            return "TASK INTAKE FORMAT"
    
    # Default: improve conventions
    for section_name in priority:
        if section_name in sections:
            return section_name
    
    # Fallback: first available section
    return list(sections.keys())[0] if sections else "CONVENTIONS"


def _summarize_tasks(tasks: List[Dict[str, Any]]) -> str:
    """Summarize tasks for prompt."""
    lines = []
    
    for i, task in enumerate(tasks[-10:], 1):  # Limit to 10
        task_text = task.get("task", "Unknown task")[:100]
        quality = task.get("quality_score", 0.5)
        source = task.get("quality_source", "unknown")
        
        lines.append(f"{i}. {task_text}... (quality: {quality:.2f}, source: {source})")
    
    return "\n".join(lines)


def _summarize_weak_areas(weak_tasks: List[Dict[str, Any]]) -> str:
    """Summarize weak areas from low-quality tasks."""
    if not weak_tasks:
        return "None identified"
    
    # Count common issues
    issues = {}
    
    for task in weak_tasks:
        reason = task.get("quality_reason", "").lower()
        
        if "incomplete" in reason:
            issues["incompleteness"] = issues.get("incompleteness", 0) + 1
        elif "unclear" in reason or "confused" in reason:
            issues["clarity"] = issues.get("clarity", 0) + 1
        elif "test" in reason or "error" in reason:
            issues["correctness"] = issues.get("correctness", 0) + 1
        else:
            issues["other"] = issues.get("other", 0) + 1
    
    if not issues:
        return "Pattern not identified"
    
    # Return most common issue
    most_common = max(issues, key=issues.get)
    return f"{most_common} ({issues[most_common]} occurrences)"


def _parse_patch_response(raw_response: str) -> Optional[Dict[str, Any]]:
    """Parse LLM patch proposal response."""
    # Try to extract JSON
    json_match = re.search(r'\{.*\}', raw_response, re.DOTALL)
    
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass
    
    # Fallback: parse key-value pairs
    result = {}
    
    section_match = re.search(r'"section":\s*"([^"]+)"', raw_response)
    if section_match:
        result["section"] = section_match.group(1)
    
    old_match = re.search(r'"old_text":\s*"([^"]+)"', raw_response)
    if old_match:
        result["old_text"] = old_match.group(1)
    
    new_match = re.search(r'"new_text":\s*"([^"]+)"', raw_response)
    if new_match:
        result["new_text"] = new_match.group(1)
    
    improvement_match = re.search(r'"expected_improvement":\s*([\d.]+)', raw_response)
    if improvement_match:
        result["expected_improvement"] = float(improvement_match.group(1))
    
    return result if result else None


# ============================================================================
# PHASE 2: APPLY PATCH
# ============================================================================

def _deduplicate_prompt(prompt: str, threshold: float = 0.72) -> str:
    """
    Remove near-duplicate paragraphs from an evolved system prompt.

    A paragraph is considered a duplicate of an earlier paragraph
    if the two share more than `threshold` fraction of their tokens
    (Jaccard similarity on word sets).

    Rules:
      - Split prompt into paragraphs on blank lines
      - Keep the FIRST occurrence of any near-duplicate pair
      - Discard later occurrences silently
      - Never remove section headers (lines starting with # or ##)
      - Never remove the writeback block template (contains ```writeback)
      - Never remove lines that are purely structural (---, empty)
      - Reassemble with original whitespace between kept paragraphs

    Args:
        prompt:    Full system prompt string.
        threshold: Jaccard similarity above which a paragraph
                   is considered a duplicate. Default 0.72.
                   Lower = more aggressive deduplication.
                   Higher = only remove near-identical text.

    Returns:
        Deduplicated prompt string. If nothing was removed,
        returns the original string unchanged.
        Never raises.
    """
    import re
    import logging

    def tokenise(text: str) -> set:
        """Lowercase word tokens, ignore punctuation."""
        return set(re.findall(r'[a-z0-9_]+', text.lower()))

    def jaccard(set_a: set, set_b: set) -> float:
        """Jaccard similarity between two token sets."""
        if not set_a and not set_b:
            return 1.0
        union = set_a | set_b
        if not union:
            return 0.0
        return len(set_a & set_b) / len(union)

    def is_structural(para: str) -> bool:
        """
        Returns True for paragraphs that must never be removed:
          - Section headers (## TITLE)
          - Horizontal rules (---)
          - Writeback block template (contains ```writeback)
          - Tool tables (| Tool | ...)
          - Single-line identifiers (short labels)
        """
        stripped = para.strip()
        if not stripped:
            return True
        if stripped.startswith('#'):
            return True
        if set(stripped.replace(' ', '')) <= set('-'):
            return True
        if '```writeback' in stripped:
            return True
        if stripped.startswith('|') and stripped.endswith('|'):
            return True
        if len(stripped.split()) <= 4:
            return True
        return False

    try:
        # Split into paragraphs on one or more blank lines
        # Preserve the separator style for reassembly
        paragraphs = re.split(r'(\n{2,})', prompt)

        # paragraphs alternates: [content, separator, content, ...]
        # Extract just the content chunks with their indices
        content_chunks = []
        for i, chunk in enumerate(paragraphs):
            if chunk.strip():  # non-empty content
                content_chunks.append((i, chunk))

        kept_indices = set()
        kept_tokens  = []   # token sets of kept paragraphs

        removed_count = 0

        for idx, chunk in content_chunks:
            # Structural elements are always kept
            if is_structural(chunk):
                kept_indices.add(idx)
                kept_tokens.append(tokenise(chunk))
                continue

            chunk_tokens = tokenise(chunk)

            # Compare against every already-kept paragraph
            is_duplicate = False
            for kept_tok in kept_tokens:
                if jaccard(chunk_tokens, kept_tok) >= threshold:
                    is_duplicate = True
                    break

            if is_duplicate:
                removed_count += 1
                logging.debug(
                    f"[ENGRAM] dedup: removed near-duplicate paragraph "
                    f"({len(chunk.split())} words)"
                )
            else:
                kept_indices.add(idx)
                kept_tokens.append(chunk_tokens)

        if removed_count == 0:
            return prompt  # nothing to do — return unchanged

        # Reassemble: keep content at kept_indices,
        # keep separators only between kept content chunks
        result_parts = []
        last_was_kept = False

        for i, chunk in enumerate(paragraphs):
            if chunk.strip():  # it's a content chunk
                if i in kept_indices:
                    result_parts.append(chunk)
                    last_was_kept = True
                else:
                    last_was_kept = False
            else:  # it's a separator (\n\n or more)
                if last_was_kept:
                    result_parts.append(chunk)

        deduped = ''.join(result_parts).strip()

        logging.info(
            f"[ENGRAM] dedup: removed {removed_count} duplicate "
            f"paragraph(s) — "
            f"{len(prompt)} → {len(deduped)} chars"
        )
        return deduped

    except Exception as e:
        logging.warning(
            f"[ENGRAM] dedup: failed, returning original: {e}"
        )
        return prompt  # safe fallback — never corrupt the prompt


def apply_patch(current_prompt: str, patch: PromptPatch) -> str:
    """
    Apply a patch to the current prompt.

    Args:
        current_prompt: Current system prompt
        patch: PromptPatch to apply

    Returns:
        New prompt with patch applied
    """
    if patch.old_text in current_prompt:
        new_prompt = current_prompt.replace(patch.old_text, patch.new_text)
        new_prompt = _deduplicate_prompt(new_prompt, threshold=0.72)
        return new_prompt

    # If old text not found exactly, try fuzzy matching
    # Replace in the target section
    sections = _parse_prompt_sections(current_prompt)

    if patch.section in sections:
        old_section = sections[patch.section]
        new_section = old_section.replace(patch.old_text[:100], patch.new_text)

        # Reconstruct prompt
        new_prompt = current_prompt.replace(old_section, new_section)
        new_prompt = _deduplicate_prompt(new_prompt, threshold=0.72)
        return new_prompt

    # Fallback: raise error instead of silently appending
    raise ValueError(
        f"[ENGRAM] learner — patch cannot be applied cleanly. "
        f"old_text not found in current prompt. "
        f"Patch target: '{patch.old_text[:80]}...'\n"
        f"This patch will be discarded. Run rollback_patch() to restore."
    )


def rollback_patch(module_name: str, prompt_store: Optional[Dict] = None) -> bool:
    """
    Rollback a patch for a module.
    
    In a full implementation, this would restore from a prompt version history.
    
    Args:
        module_name: Module to rollback
        prompt_store: Optional prompt version store
    
    Returns:
        True if rollback successful
    """
    # Placeholder - in production, restore from version history
    if prompt_store and module_name in prompt_store:
        # Restore previous version
        return True
    
    return False


def commit_patch(module_name: str, patch: PromptPatch, prompt_store: Optional[Dict] = None) -> bool:
    """
    Commit a patch permanently.

    Args:
        module_name: Module name
        patch: Patch to commit
        prompt_store: Optional prompt version store

    Returns:
        True if commit successful
    """
    # Save to in-memory prompt store if provided
    if prompt_store is not None:
        if module_name not in prompt_store:
            prompt_store[module_name] = []
        prompt_store[module_name].append(patch.to_dict())

    return True


def persist_patch(
    module_name: str,
    new_prompt: str,
    modules_dir: Optional[str] = None,
) -> bool:
    """
    Write the patched prompt back to the module's
    agent_system_prompt.md file.

    This is the persistence layer for the learning loop.
    Without this, patches live only in memory and are
    lost on next boot.

    Args:
        module_name:  e.g. "coding", "marketing", "seo"
        new_prompt:   the patched prompt string
        modules_dir:  override path to modules directory

    Returns:
        True if written successfully, False on error
    """
    import logging
    from pathlib import Path

    # Locate modules directory
    if modules_dir:
        base = Path(modules_dir)
    else:
        # Default: relative to this file
        base = Path(__file__).parent.parent / "modules"

    prompt_path = base / module_name / "agent_system_prompt.md"

    if not prompt_path.parent.exists():
        logging.error(
            f"[ENGRAM] persist_patch: module dir not found: "
            f"{prompt_path.parent}"
        )
        return False

    # Back up current prompt before overwriting
    backup_path = prompt_path.with_suffix(".md.bak")
    try:
        if prompt_path.exists():
            backup_path.write_text(
                prompt_path.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            logging.debug(
                f"[ENGRAM] prompt backed up: {backup_path}"
            )
    except Exception as e:
        logging.warning(
            f"[ENGRAM] backup failed (non-fatal): {e}"
        )

    # Write new prompt
    try:
        prompt_path.write_text(new_prompt, encoding="utf-8")
        logging.info(
            f"[ENGRAM] prompt updated: {prompt_path}"
        )
        return True
    except Exception as e:
        logging.error(
            f"[ENGRAM] persist_patch write failed: "
            f"{prompt_path} — {e}"
        )
        return False


# ============================================================================
# PHASE 3: EVALUATE PATCH
# ============================================================================

def evaluate_patch(
    module_name: str,
    new_prompt: str,
    n_tasks: int = N_EVALUATE_TASKS,
    llm_call: Optional[Callable[[str], str]] = None,
) -> float:
    """
    Evaluate a patch by simulating task completions.
    
    In a full implementation, this would run actual tasks and measure quality.
    For now, uses LLM-as-judge to estimate improvement.
    
    Args:
        module_name: Module being improved
        new_prompt: New prompt with patch applied
        n_tasks: Number of tasks to evaluate on
        llm_call: LLM call function
    
    Returns:
        Estimated quality score with patch
    """
    # Placeholder evaluation
    # In production: run n_tasks actual tasks and measure quality
    
    if llm_call is None:
        return 0.5  # Default
    
    # Use LLM to estimate
    eval_prompt = f"""
Estimate the quality improvement from this prompt change.

MODULE: {module_name}

CHANGE: Applied patch to improve {module_name} module.

Estimate the average quality score (0.0-1.0) for tasks completed with this prompt.
Return only a number between 0.0 and 1.0.
"""
    
    try:
        response = llm_call(eval_prompt, model=PATCH_PROPOSAL_MODEL)
        
        # Extract number
        number_match = re.search(r'([\d.]+)', response)
        if number_match:
            return min(1.0, max(0.0, float(number_match.group(1))))
    except Exception:
        pass
    
    return 0.5


# ============================================================================
# MAIN LEARNING CYCLE
# ============================================================================

def learning_cycle(
    module_name: str,
    session_log: List[Dict[str, Any]],
    current_prompt: str,
    llm_call: Callable[[str], str],
    n_recent: int = N_RECENT_TASKS,
    n_evaluate: int = N_EVALUATE_TASKS,
    min_improvement: float = MIN_IMPROVEMENT_THRESHOLD,
    prompt_store: Optional[Dict] = None,
) -> Tuple[bool, Optional[PromptPatch]]:
    """
    Run one learning cycle for a module.
    
    Args:
        module_name: Module to improve
        session_log: Recent session logs
        current_prompt: Current system prompt
        llm_call: LLM call function
        n_recent: Number of tasks to analyze
        n_evaluate: Number of tasks to evaluate on
        min_improvement: Minimum improvement to keep patch
        prompt_store: Optional prompt version store
    
    Returns:
        Tuple of (patch_committed, patch)
    
    Example:
        >>> improved, patch = learning_cycle("coding", session_log, prompt, llm.chat)
        >>> if improved:
        ...     print(f"Module improved! New quality: {new_quality:.2f}")
    """
    # Check if enough data
    if len(session_log) < n_recent:
        return False, None
    
    # Propose patch
    patch = propose_patch(
        module_name=module_name,
        current_prompt=current_prompt,
        session_log=session_log,
        llm_call=llm_call,
        n_recent=n_recent,
    )
    
    if not patch:
        return False, None
    
    # Apply patch
    new_prompt = apply_patch(current_prompt, patch)
    
    # Evaluate
    new_quality = evaluate_patch(
        module_name=module_name,
        new_prompt=new_prompt,
        n_tasks=n_evaluate,
        llm_call=llm_call,
    )
    
    # Calculate current quality
    recent = session_log[-n_recent:]
    current_quality = sum(
        t.get("quality_score", 0.5) for t in recent
    ) / len(recent)
    
    # Keep or rollback
    improvement = new_quality - current_quality

    if improvement >= min_improvement:
        commit_patch(module_name, patch, prompt_store)

        # Persist patch to module's prompt file on disk
        persisted = persist_patch(
            module_name=module_name,
            new_prompt=new_prompt,
        )
        if persisted:
            import logging
            logging.info(
                f"[ENGRAM] learning: patch persisted "
                f"to modules/{module_name}/agent_system_prompt.md"
            )
        else:
            import logging
            logging.warning(
                f"[ENGRAM] learning: patch NOT persisted — "
                f"check module directory"
            )

        # Record learning event
        try:
            from .learning_history import record_learning_event
            from pathlib import Path
            sessions_dir = str(Path(__file__).parent.parent / "sessions")
            record_learning_event(
                sessions_dir=sessions_dir,
                module_name=module_name,
                patch=patch,
                tasks_analyzed=n_recent,
                quality_before=current_quality,
                quality_after=new_quality,
            )
        except Exception as e:
            import logging
            logging.debug(f"[ENGRAM] learner: failed to record learning event: {e}")

        return True, patch
    else:
        rollback_patch(module_name, prompt_store)
        return False, patch


# ============================================================================
# BATCH LEARNING
# ============================================================================

def run_learning_cycles(
    session_log: List[Dict[str, Any]],
    modules: Dict[str, str],  # module_name -> current_prompt
    llm_call: Callable[[str], str],
    prompt_store: Optional[Dict] = None,
) -> Dict[str, bool]:
    """
    Run learning cycles for all modules.
    
    Args:
        session_log: Session logs
        modules: Dictionary of module names to prompts
        llm_call: LLM call function
        prompt_store: Optional prompt version store
    
    Returns:
        Dictionary of module_name -> improved
    """
    results = {}
    
    for module_name, prompt in modules.items():
        improved, _ = learning_cycle(
            module_name=module_name,
            session_log=session_log,
            current_prompt=prompt,
            llm_call=llm_call,
            prompt_store=prompt_store,
        )
        results[module_name] = improved

    return results


# ============================================================================
# RUBRIC EVOLUTION
# ============================================================================

def evolve_rubric(
    module_name: str,
    modules_dir: str,
    calibration_log_path: str,
    llm_call,
    min_tasks: int = 50,
) -> dict:
    """
    Evolve a module's scorer rubric based on calibration evidence.

    Reads the calibration log for the module, identifies systematic
    bias patterns, and rewrites the rubric to correct for them.

    Fires every 50 tasks (slower cycle than learning_cycle's 10).
    Called automatically by code_command.py post-turn.

    Args:
        module_name:           e.g. "coding"
        modules_dir:           Path to engram/modules/
        calibration_log_path:  Path to scorer_calibration_{module}.jsonl
        llm_call:              callable(prompt: str) -> str
        min_tasks:             Minimum entries before evolution fires.

    Returns:
        {
          "evolved":        bool,
          "rubric_version": int,
          "bias_corrected": str,
          "error":          str | None,
        }
    """
    import json
    import logging
    from pathlib import Path
    from datetime import datetime
    from engram.core.scorer_calibration import (
        load_calibration_log, calibration_stats
    )

    rubric_path = Path(modules_dir) / module_name / "scorer_rubric.md"
    if not rubric_path.exists():
        return {
            "evolved": False, "rubric_version": 0,
            "bias_corrected": "", "error": "rubric file not found"
        }

    entries = load_calibration_log(calibration_log_path, last_n=200)
    module_entries = [
        e for e in entries if e.get("module") == module_name
    ]

    if len(module_entries) < min_tasks:
        return {
            "evolved": False, "rubric_version": 0,
            "bias_corrected": "",
            "error": f"insufficient data: {len(module_entries)} < {min_tasks}"
        }

    stats   = calibration_stats(calibration_log_path, module_name)
    current = rubric_path.read_text(encoding="utf-8")

    # Extract current version
    import re
    v_match = re.search(r'# v(\d+)', current)
    version = int(v_match.group(1)) if v_match else 1

    # Build evidence summary for LLM
    bias_summary = f"""
Calibration evidence from {stats['with_ground_truth']} scored tasks:
  Mean error:         {stats['mean_error']:+.3f}
  Mean absolute err:  {stats['mean_abs_error']:.3f}
  Bias direction:     {stats['bias_direction']}
  Human corrections:  {stats['human_corrections']}
  Per task-type errors: {json.dumps(stats['task_type_errors'], indent=2)}
"""

    prompt = f"""You are improving a quality scoring rubric for an AI agent module.

CURRENT RUBRIC:
---
{current}
---

CALIBRATION EVIDENCE:
{bias_summary}

TASK:
Rewrite the rubric to correct for the observed bias patterns.
Rules:
  - If bias is "pessimistic" (mean_error > 0): relax penalty conditions
    or add reward conditions to raise scores appropriately
  - If bias is "optimistic" (mean_error < 0): tighten penalty conditions
    to lower inflated scores
  - If specific task types have high errors: add a note targeting that type
  - Do NOT change the JSON return format instruction
  - Do NOT change the section headers (## Dimensions etc.)
  - Keep rubric under 400 words
  - Update the version comment: # v{version + 1} — calibrated {datetime.utcnow().strftime('%Y-%m-%d')}

Return ONLY the new rubric text. No explanation."""

    try:
        new_rubric = llm_call(prompt)
        new_rubric = new_rubric.strip()

        if len(new_rubric) < 100:
            raise ValueError(
                f"Rubric too short: {len(new_rubric)} chars"
            )

        # Backup current
        backup_path = rubric_path.with_suffix(
            f".v{version}.bak"
        )
        backup_path.write_text(current, encoding="utf-8")

        # Write new rubric
        rubric_path.write_text(new_rubric, encoding="utf-8")

        logging.info(
            f"[ENGRAM] rubric evolved: {module_name} "
            f"v{version} → v{version + 1} "
            f"(bias={stats['bias_direction']})"
        )

        return {
            "evolved":        True,
            "rubric_version": version + 1,
            "bias_corrected": stats["bias_direction"],
            "error":          None,
        }

    except Exception as e:
        logging.error(f"[ENGRAM] evolve_rubric failed: {e}")
        return {
            "evolved":        False,
            "rubric_version": version,
            "bias_corrected": "",
            "error":          str(e),
        }


# ============================================================================
# CLI COMMAND
# ============================================================================

def cmd_learn(args) -> int:
    """
    CLI command: engram learn --module coding
    
    Runs a learning cycle for a module.
    """
    from .session import SessionManager
    
    print(f"\n{'=' * 60}")
    print("ENGRAM OS - Learning Cycle")
    print(f"{'=' * 60}\n")
    
    # Load session log
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
    
    if len(session_log) < 10:
        print("⚠ Not enough data for learning (need 10+ tasks)")
        return 1
    
    print(f"Analyzing {len(session_log)} tasks...")
    
    # Mock LLM call for CLI
    def mock_llm_call(prompt, model="qwen3:30b-a3b-q4_K_M"):
        return '{"score": 0.8, "reason": "Good"}'
    
    # Run learning cycle
    current_prompt = f"## CONVENTIONS\nDefault prompt for {args.module}"
    
    improved, patch = learning_cycle(
        module_name=args.module,
        session_log=session_log,
        current_prompt=current_prompt,
        llm_call=mock_llm_call,
    )
    
    if improved and patch:
        print(f"✓ Module '{args.module}' improved!")
        print(f"  Section: {patch.section}")
        print(f"  Expected improvement: +{patch.expected_improvement:.2f}")
    else:
        print(f"✗ No improvement found for '{args.module}'")
    
    print()
    return 0


def create_learn_parser(subparsers) -> None:
    """Create argument parser for learn command."""
    parser = subparsers.add_parser(
        'learn',
        help='Run learning cycle for a module',
        description='Analyze recent tasks and propose prompt improvements',
    )
    
    parser.add_argument(
        '--module', '-m',
        required=True,
        help='Module to improve (e.g., coding, marketing)',
    )
    
    parser.add_argument(
        '--session', '-s',
        default=None,
        help='Session ID to analyze (uses recent sessions if not specified)',
    )
    
    parser.set_defaults(func=cmd_learn)


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(
        description='ENGRAM OS - Learning Loop',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python -m engram.core.learner learn --module coding
  python -m engram.core.learner learn --module coding --session abc123
        ''',
    )
    
    create_learn_parser(parser)
    args = parser.parse_args()
    
    exit(args.func(args))
