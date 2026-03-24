"""
ENGRAM OS Benchmark Metrics

Implements the six essential metrics for measuring ENGRAM OS performance:
- Context Precision (immediate)
- VRAM Efficiency (immediate)
- Writeback Integrity (immediate)
- Goal Coherence Decay Rate (longitudinal)
- Session Resume Fidelity (longitudinal)
- Experience Compound Rate (longitudinal)

All metrics return scores between 0.0 and 1.0.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import numpy as np


@dataclass
class Chunk:
    """Represents a context chunk for benchmarking."""
    id: str
    text: str
    domain: str = "general"
    relevance_score: float = 0.0
    last_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BenchmarkMetrics:
    """Container for all benchmark metrics."""
    context_precision: float = 0.0
    vram_efficiency: float = 0.0
    writeback_integrity: float = 0.0
    goal_coherence_decay: float = 0.0
    resume_fidelity: float = 0.0
    experience_compound_rate: float = 0.0
    
    # Metadata
    task_name: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    baseline_scores: Dict[str, float] = field(default_factory=dict)
    engram_scores: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "context_precision": self.context_precision,
            "vram_efficiency": self.vram_efficiency,
            "writeback_integrity": self.writeback_integrity,
            "goal_coherence_decay": self.goal_coherence_decay,
            "resume_fidelity": self.resume_fidelity,
            "experience_compound_rate": self.experience_compound_rate,
            "task_name": self.task_name,
            "timestamp": self.timestamp,
            "baseline_scores": self.baseline_scores,
            "engram_scores": self.engram_scores,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BenchmarkMetrics":
        """Create from dictionary representation."""
        return cls(
            context_precision=data.get("context_precision", 0.0),
            vram_efficiency=data.get("vram_efficiency", 0.0),
            writeback_integrity=data.get("writeback_integrity", 0.0),
            goal_coherence_decay=data.get("goal_coherence_decay", 0.0),
            resume_fidelity=data.get("resume_fidelity", 0.0),
            experience_compound_rate=data.get("experience_compound_rate", 0.0),
            task_name=data.get("task_name", ""),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            baseline_scores=data.get("baseline_scores", {}),
            engram_scores=data.get("engram_scores", {}),
        )
    
    def get_delta(self, metric_name: str) -> float:
        """Calculate ENGRAM delta over baseline for a metric."""
        baseline = self.baseline_scores.get(metric_name, 0.0)
        engram = self.engram_scores.get(metric_name, 0.0)
        return engram - baseline
    
    def summary(self) -> str:
        """Generate a summary string of all metrics."""
        lines = [
            f"Benchmark Metrics Summary",
            f"=========================",
            f"Task: {self.task_name}",
            f"Timestamp: {self.timestamp}",
            f"",
            f"Context Precision:     {self.context_precision:.3f} (baseline: {self.baseline_scores.get('context_precision', 'N/A')})",
            f"VRAM Efficiency:       {self.vram_efficiency:.3f} (baseline: {self.baseline_scores.get('vram_efficiency', 'N/A')})",
            f"Writeback Integrity:   {self.writeback_integrity:.3f} (baseline: {self.baseline_scores.get('writeback_integrity', 'N/A')})",
            f"Goal Coherence Decay:  {self.goal_coherence_decay:.3f} (baseline: {self.baseline_scores.get('goal_coherence_decay', 'N/A')})",
            f"Resume Fidelity:       {self.resume_fidelity:.3f} (baseline: {self.baseline_scores.get('resume_fidelity', 'N/A')})",
            f"Experience Compound:   {self.experience_compound_rate:.3f} (baseline: {self.baseline_scores.get('experience_compound_rate', 'N/A')})",
        ]
        return "\n".join(lines)


def context_precision(hot_chunks: List[Chunk], model_response: str) -> float:
    """
    Context Precision Metric
    
    Measures what percentage of the loaded context was actually relevant
    to the task output.
    
    Args:
        hot_chunks: List of chunks that were loaded into context
        model_response: The model's response text
        
    Returns:
        Score between 0.0 and 1.0
        
    Target:
        - Baseline: 0.2-0.4 (noise-heavy context)
        - ENGRAM: 0.7-0.9 (surgical loading)
    """
    if not hot_chunks:
        return 0.0
    
    referenced_chunks = []
    
    for chunk in hot_chunks:
        # Extract key terms from chunk (first 10 words)
        words = chunk.text.split()[:10]
        terms = [w.lower().strip(".,!?;:()[]{}\"'") for w in words if len(w) > 2]
        
        # Check if any term appears in the response
        response_lower = model_response.lower()
        is_referenced = any(term in response_lower for term in terms)
        
        # Also check for chunk ID reference
        if chunk.id in model_response:
            is_referenced = True
            
        if is_referenced:
            referenced_chunks.append(chunk)
    
    precision = len(referenced_chunks) / max(1, len(hot_chunks))
    return min(1.0, max(0.0, precision))


def vram_efficiency(db: Any, contract: Any) -> float:
    """
    VRAM Efficiency Metric
    
    Measures what fraction of the available vector budget was actually used
    vs wasted on irrelevant chunks.
    
    Args:
        db: Vector database with hot_chunks attribute
        contract: Contract with threshold information
        
    Returns:
        Score between 0.0 and 1.0
        
    Target:
        - ENGRAM: > 0.80
        - Below 0.65 means threshold calibration is off
    """
    # Get hot chunks from database
    hot_chunks = getattr(db, 'hot_chunks', [])
    
    if not hot_chunks:
        return 1.0  # No chunks = no waste
    
    # Count chunks with high relevance scores
    threshold = getattr(contract, 'hot_threshold', 0.65)
    relevant_hot = sum(1 for c in hot_chunks if getattr(c, 'last_score', 0) > threshold)
    
    efficiency = relevant_hot / max(1, len(hot_chunks))
    return min(1.0, max(0.0, efficiency))


def writeback_integrity(response: str, scratch_before: Dict[str, Any],
                        scratch_after: Dict[str, Any]) -> float:
    """
    Writeback Integrity Metric
    
    Measures whether the model wrote back correctly - parsed, applied,
    and scratch updated.
    
    Args:
        response: The model's response text
        scratch_before: Scratch state before the operation
        scratch_after: Scratch state after the operation
        
    Returns:
        Score between 0.0 and 1.0
        
    Target:
        - Average across session: > 0.85
        - Below 0.6 means agent prompt needs refinement
    """
    # Parse writeback from response
    writeback = parse_writeback(response)
    
    if not writeback:
        return 0.0
    
    # Check for key fields that should be updated
    key_fields = ["module", "status", "next_focus", "task", "action"]
    fields_updated = 0
    
    for field_name in key_fields:
        # Check if field exists in writeback
        if writeback.get(field_name):
            fields_updated += 1
        # Also check if field was actually changed in scratch
        elif field_name in scratch_after and field_name in scratch_before:
            if scratch_after[field_name] != scratch_before[field_name]:
                fields_updated += 1
    
    # Normalize to 0-1 scale (expecting at least 3 fields)
    score = fields_updated / max(1, len(key_fields))
    return min(1.0, max(0.0, score))


def parse_writeback(response: str) -> Dict[str, Any]:
    """
    Parse writeback data from model response.
    
    Looks for structured data in formats like:
    - YAML blocks
    - JSON blocks
    - Key: Value pairs
    
    Args:
        response: Model response text
        
    Returns:
        Dictionary of parsed writeback data
    """
    writeback = {}
    
    # Try to find YAML block
    yaml_pattern = r'```(?:yaml|yml)?\s*\n(.*?)\n```'
    yaml_match = re.search(yaml_pattern, response, re.DOTALL | re.IGNORECASE)
    
    if yaml_match:
        try:
            import yaml
            yaml_content = yaml_match.group(1).strip()
            parsed = yaml.safe_load(yaml_content)
            if isinstance(parsed, dict):
                return parsed
        except Exception as e:
            logging.debug(f"[ENGRAM] metrics: YAML parse failed, trying JSON: {e}")

    # Try to find JSON block
    json_pattern = r'```(?:json)?\s*\n(.*?)\n```'
    json_match = re.search(json_pattern, response, re.DOTALL | re.IGNORECASE)

    if json_match:
        try:
            import json
            json_content = json_match.group(1).strip()
            parsed = json.loads(json_content)
            if isinstance(parsed, dict):
                return parsed
        except Exception as e:
            logging.debug(f"[ENGRAM] metrics: JSON parse failed, trying KV: {e}")
    
    # Try to find key: value pairs
    kv_pattern = r'^\s*(\w+)\s*:\s*(.+?)\s*$'
    for match in re.finditer(kv_pattern, response, re.MULTILINE):
        key = match.group(1).strip()
        value = match.group(2).strip()
        writeback[key] = value
    
    return writeback


def goal_coherence_decay(quality_scores: List[float]) -> float:
    """
    Goal Coherence Decay Rate Metric
    
    Measures how much output quality drops from task 1 to task 10 in a long session.
    Calculates the slope of the regression line.
    
    Args:
        quality_scores: List of quality scores (0-1) for each task in sequence
        
    Returns:
        Slope of the regression line
        - Negative slope = quality degrades over time
        - Near zero = quality holds steady
        - Positive slope = quality improves over time
        
    Target:
        - Baseline: negative slope (quality degrades)
        - ENGRAM: flat or positive slope (quality holds or improves)
    """
    if len(quality_scores) < 2:
        return 0.0
    
    # Convert to numpy array
    y = np.array(quality_scores, dtype=float)
    x = np.arange(len(y))
    
    # Calculate linear regression slope
    n = len(x)
    sum_x = np.sum(x)
    sum_y = np.sum(y)
    sum_xy = np.sum(x * y)
    sum_x2 = np.sum(x ** 2)
    
    denominator = n * sum_x2 - sum_x ** 2
    if denominator == 0:
        return 0.0
    
    slope = (n * sum_xy - sum_x * sum_y) / denominator
    
    # Normalize slope to 0-1 range for consistency
    # Slope of -0.1 or worse = 0.0, slope of 0.1 or better = 1.0
    normalized = 0.5 + slope  # Center around 0.5
    normalized = max(0.0, min(1.0, normalized))
    
    return normalized


def resume_fidelity(scratch_path: str, ground_truth_state: Dict[str, Any]) -> float:
    """
    Session Resume Fidelity Metric
    
    Measures what percentage of project context the agent reconstructs correctly
    from the scratch note alone after a session restart.
    
    Args:
        scratch_path: Path to the scratch YAML file
        ground_truth_state: The expected state to compare against
        
    Returns:
        Score between 0.0 and 1.0
        
    Target:
        - Baseline: 0.0 (no session persistence)
        - ENGRAM: > 0.85
    """
    import os
    import yaml

    if not os.path.exists(scratch_path):
        return 0.0

    try:
        with open(scratch_path, 'r') as f:
            resumed_state = yaml.safe_load(f) or {}
    except Exception as e:
        logging.debug(f"[ENGRAM] metrics: scratch load failed, returning 0: {e}")
        return 0.0

    if not resumed_state:
        return 0.0
    
    # Define fields to check
    fields_to_check = [
        "active_task.module",
        "active_task.status",
        "modules",
        "conventions",
        "last_completed_task",
        "next_task",
    ]
    
    correct = 0
    total_checked = 0
    
    for field_path in fields_to_check:
        ground_value = get_nested_value(ground_truth_state, field_path)
        resumed_value = get_nested_value(resumed_state, field_path)
        
        if ground_value is not None:
            total_checked += 1
            if values_match(ground_value, resumed_value):
                correct += 1
    
    if total_checked == 0:
        return 0.0
    
    fidelity = correct / total_checked
    return min(1.0, max(0.0, fidelity))


def get_nested_value(data: Dict[str, Any], path: str) -> Any:
    """Get a nested value from a dictionary using dot notation."""
    keys = path.split('.')
    value = data
    
    for key in keys:
        if isinstance(value, dict):
            value = value.get(key)
        else:
            return None
    
    return value


def values_match(val1: Any, val2: Any) -> bool:
    """Check if two values match (with some tolerance for floats)."""
    if val1 is None and val2 is None:
        return True
    if val1 is None or val2 is None:
        return False
    
    if isinstance(val1, float) and isinstance(val2, float):
        return abs(val1 - val2) < 0.01
    
    if isinstance(val1, (list, tuple)) and isinstance(val2, (list, tuple)):
        if len(val1) != len(val2):
            return False
        return all(values_match(v1, v2) for v1, v2 in zip(val1, val2))
    
    if isinstance(val1, dict) and isinstance(val2, dict):
        if val1.keys() != val2.keys():
            return False
        return all(values_match(val1[k], val2[k]) for k in val1.keys())
    
    return val1 == val2


def experience_compound_rate(first_scores: List[float], last_scores: List[float]) -> float:
    """
    Experience Compound Rate Metric
    
    Measures whether output quality on similar tasks improves after experience
    distillation.
    
    Args:
        first_scores: Quality scores from first N tasks of a type
        last_scores: Quality scores from last N tasks of the same type
        
    Returns:
        Improvement rate (0.0 = no improvement, 1.0 = maximum improvement)
        
    Target:
        - Expected: 15-25% improvement as experiences accumulate
        - Score of 0.15-0.25 indicates healthy learning
    """
    if not first_scores or not last_scores:
        return 0.0
    
    # Calculate average scores
    first_avg = np.mean(first_scores)
    last_avg = np.mean(last_scores)
    
    # Calculate improvement rate
    if first_avg == 0:
        if last_avg > 0:
            return 1.0
        return 0.0
    
    improvement = (last_avg - first_avg) / first_avg
    
    # Normalize: 0.25 (25%) improvement = 1.0 score
    normalized = min(1.0, max(0.0, improvement / 0.25))
    
    return normalized


def calculate_quality_score(response: str, task: str,
                            reference_answer: Optional[str] = None) -> float:
    """
    Calculate a quality score for a model response.
    
    Uses simple heuristics when no reference answer is provided:
    - Response length (not too short, not too long)
    - Presence of key terms from task
    - Structured output (code blocks, lists, etc.)
    
    Args:
        response: Model response text
        task: The original task description
        reference_answer: Optional ground truth for comparison
        
    Returns:
        Quality score between 0.0 and 1.0
    """
    if not response or not response.strip():
        return 0.0
    
    score = 0.5  # Base score
    
    # Length check (prefer responses between 100-2000 chars)
    length = len(response)
    if 100 <= length <= 2000:
        score += 0.1
    elif length < 50:
        score -= 0.3
    elif length > 5000:
        score -= 0.1
    
    # Task keyword presence
    task_words = set(task.lower().split())
    response_lower = response.lower()
    matched_keywords = sum(1 for w in task_words if len(w) > 3 and w in response_lower)
    keyword_ratio = matched_keywords / max(1, len(task_words))
    score += 0.2 * keyword_ratio
    
    # Structure check (code blocks, lists, etc.)
    if '```' in response:
        score += 0.1
    if re.search(r'^\s*[-*]\s', response, re.MULTILINE):
        score += 0.05
    if re.search(r'^\s*\d+\.\s', response, re.MULTILINE):
        score += 0.05
    
    # Reference answer comparison if available
    if reference_answer:
        # Simple overlap check
        ref_words = set(reference_answer.lower().split())
        resp_words = set(response_lower.split())
        overlap = len(ref_words & resp_words) / max(1, len(ref_words))
        score = (score + overlap) / 2
    
    return min(1.0, max(0.0, score))


def estimate_tokens(text: str) -> int:
    """Estimate token count from text (rough approximation)."""
    # Rough estimate: 1 token ≈ 4 characters
    return len(text) // 4
