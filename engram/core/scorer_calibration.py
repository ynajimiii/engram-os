"""
Scorer calibration — accumulate evidence, correct bias.

This module owns:
  - Writing calibration entries to JSONL log
  - Reading calibration log and computing bias corrections
  - Proxy signal computation per domain
  - Proxy adjustment rules per domain

It does NOT own:
  - LLM calls (scorer.py owns those)
  - Rubric files (stored in modules/{domain}/)
  - Rubric evolution (learner.py owns that)
"""

import re
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional


# ── Calibration log I/O ─────────────────────────────────────────

def append_calibration_entry(
    log_path: str,
    module_name: str,
    task_type: str,
    llm_judge_score: float,
    execution_score: Optional[float],
    proxy_signals: dict,
    source: str = "auto",
) -> None:
    """
    Append one calibration entry to the module's JSONL log.

    Called after every score_task() call.
    When execution_score is available (tests ran),
    the difference is the ground truth calibration signal.
    When execution_score is None, only proxy signals are recorded.

    Args:
        log_path:         Path to scorer_calibration_{module}.jsonl
        module_name:      e.g. "coding"
        task_type:        e.g. "write_tests", "fix_bug", "refactor"
        llm_judge_score:  Raw score from LLM-as-judge (0.0–1.0)
        execution_score:  Score from test execution or None
        proxy_signals:    Dict of computed proxy metrics
        source:           "auto" or "human"

    Never raises.
    """
    entry = {
        "ts":               datetime.utcnow().isoformat(),
        "module":           module_name,
        "task_type":        task_type,
        "llm_judge":        round(llm_judge_score, 4),
        "execution":        round(execution_score, 4) if execution_score is not None else None,
        "error":            round(execution_score - llm_judge_score, 4)
                            if execution_score is not None else None,
        "proxy_signals":    proxy_signals,
        "source":           source,
    }
    try:
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logging.warning(
            f"[ENGRAM] calibration: append failed: {e}"
        )


def load_calibration_log(
    log_path: str,
    last_n: int = 100,
    min_source_weight: float = 0.0,
) -> list:
    """
    Load calibration entries from JSONL log.

    Args:
        log_path:   Path to the JSONL file.
        last_n:     Max entries to return (most recent).
        min_source_weight: Filter by minimum weight
                   (human entries have weight 3.0, auto 1.0).

    Returns:
        List of entry dicts. Empty if file missing.
        Never raises.
    """
    path = Path(log_path)
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        entries = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                weight = 3.0 if obj.get("source") == "human" else 1.0
                if weight >= min_source_weight:
                    entries.append({**obj, "_weight": weight})
            except json.JSONDecodeError:
                continue
        return entries[-last_n:]
    except Exception as e:
        logging.warning(
            f"[ENGRAM] calibration: load failed: {e}"
        )
        return []


# ── Bias correction ─────────────────────────────────────────────

def get_bias_correction(
    module_name: str,
    task_type: str,
    log_path: str,
    min_observations: int = 3,
) -> float:
    """
    Compute average calibration error for this module+task_type.

    Uses only entries where execution_score is available
    (ground truth comparisons). Human entries are weighted 3x.

    Returns:
        float: average error (execution - llm_judge).
        Positive = LLM judge was pessimistic (scores too low).
        Negative = LLM judge was optimistic (scores too high).
        Returns 0.0 if fewer than min_observations available.

    Never raises.
    """
    entries = load_calibration_log(log_path, last_n=200)

    # Filter to entries with ground truth for this domain
    relevant = [
        e for e in entries
        if e.get("module") == module_name
        and e.get("error") is not None   # has execution score
        and abs(e["error"]) > 0.03       # ignore near-zero noise
        and (
            e.get("task_type") == task_type
            or task_type == "any"
        )
    ]

    if len(relevant) < min_observations:
        return 0.0

    # Weighted average (human corrections count 3x)
    total_weight = sum(e.get("_weight", 1.0) for e in relevant)
    weighted_sum = sum(
        e["error"] * e.get("_weight", 1.0)
        for e in relevant
    )

    correction = weighted_sum / total_weight
    # Cap correction at ±0.25 — don't over-correct
    correction = max(-0.25, min(0.25, correction))

    logging.debug(
        f"[ENGRAM] calibration: {module_name}/{task_type} "
        f"correction={correction:+.3f} "
        f"(n={len(relevant)}, weighted)"
    )
    return round(correction, 4)


# ── Proxy signals ────────────────────────────────────────────────

def compute_proxy_signals(
    response: str,
    task: str,
    module_name: str,
) -> dict:
    """
    Compute domain-specific proxy signals for one response.

    These signals serve two purposes:
      1. Stored in calibration log for correlation analysis
      2. Used by apply_proxy_adjustment() for immediate scoring

    Returns a flat dict of signal name → value.
    Never raises — returns empty dict on any error.
    """
    try:
        if module_name == "coding":
            return _coding_proxies(response, task)
        elif module_name == "marketing":
            return _marketing_proxies(response, task)
        elif module_name == "research":
            return _research_proxies(response, task)
        else:
            return _generic_proxies(response, task)
    except Exception as e:
        logging.debug(
            f"[ENGRAM] proxy_signals: failed for {module_name}: {e}"
        )
        return {}


def _coding_proxies(response: str, task: str) -> dict:
    """Proxy signals for coding module."""
    resp_lower = response.lower()
    task_lower = task.lower()

    # write_file was called (strong signal of implementation)
    write_file_called = "write_file" in resp_lower or \
                        "files_modified" in resp_lower

    # Tests mentioned and appear to have been run
    pytest_in_response = "passed" in resp_lower and \
                         ("test" in resp_lower or "pytest" in resp_lower)

    # Writeback block present
    writeback_present = "```writeback" in response or \
                        "writeback" in response.lower()

    # Count claimed file modifications
    files_modified = len(re.findall(
        r'files_modified:\s*\[([^\]]+)\]', response
    ))

    return {
        "write_file_called":  write_file_called,
        "pytest_in_response": pytest_in_response,
        "writeback_present":  writeback_present,
        "files_modified_count": files_modified,
        "response_length":    len(response.split()),
    }


def _marketing_proxies(response: str, task: str) -> dict:
    """Proxy signals for marketing module."""
    # Generic filler phrases (quality killers)
    generic_phrases = [
        "world-class", "cutting-edge", "innovative solution",
        "take it to the next level", "synergy", "game-changing",
        "revolutionary", "best-in-class", "state-of-the-art",
        "leverage", "paradigm shift", "holistic approach",
    ]
    generic_count = sum(
        1 for phrase in generic_phrases
        if phrase.lower() in response.lower()
    )

    # Specificity signals: numbers with business context
    specificity_signals = len(re.findall(
        r'\d+[\.,]?\d*\s*(%|percent|x\b|times|days|hours|weeks|'
        r'months|customers|users|revenue|churn|conversion|'
        r'clicks|opens|downloads|signups)',
        response, re.IGNORECASE
    ))

    # Audience named: persona or role
    audience_named = bool(re.search(
        r'\b(CEO|CTO|founder|developer|marketer|designer|'
        r'engineer|manager|director|startup|enterprise|'
        r'SMB|agency|team|freelancer)\b',
        response, re.IGNORECASE
    ))

    # CTA present
    cta_present = bool(re.search(
        r'\b(get started|try it|book a|schedule|download|'
        r'sign up|start free|request a|learn more|'
        r'see how|watch|join)\b',
        response, re.IGNORECASE
    ))

    # Structure: bullets delivered
    bullet_count = (
        response.count('\n-') +
        response.count('\n•') +
        response.count('\n*') +
        response.count('\n–')
    )
    task_requested_bullets = any(
        w in task.lower()
        for w in ['bullet', 'list', 'points', '•', '-']
    )

    return {
        "generic_phrase_count": generic_count,
        "specificity_signals":  specificity_signals,
        "audience_named":       audience_named,
        "cta_present":          cta_present,
        "bullet_count":         bullet_count,
        "structure_match":      not task_requested_bullets
                                or bullet_count >= 2,
        "response_length":      len(response.split()),
    }


def _research_proxies(response: str, task: str) -> dict:
    """Proxy signals for research module."""
    # Named references: citations, authors, studies
    named_refs = len(re.findall(
        r'(?:according to|[A-Z][a-z]+ et al\.?|'
        r'study by|research by|[A-Z][a-z]+,\s*\d{4}|'
        r'\(\d{4}\))',
        response
    ))

    # Quantified claims: numbers with analytical context
    quantified_claims = len(re.findall(
        r'\d+[\.,]?\d*\s*(%|percent|x\b|times|fold|'
        r'participants|subjects|studies|trials|samples|'
        r'p\s*[<>=]\s*0\.\d+)',
        response, re.IGNORECASE
    ))

    # Qualification language (intellectual honesty signal)
    qualifiers = len(re.findall(
        r'\b(however|although|while|despite|limited by|'
        r'caveat|note that|importantly|nevertheless|'
        r'on the other hand|in contrast)\b',
        response, re.IGNORECASE
    ))

    # Word count
    word_count = len(response.split())

    # Structure: sections present
    has_sections = bool(re.search(r'\n##?\s+\w', response))

    return {
        "named_refs":         named_refs,
        "quantified_claims":  quantified_claims,
        "qualifier_count":    qualifiers,
        "word_count":         word_count,
        "has_sections":       has_sections,
        "refs_per_100_words": round(named_refs / max(word_count / 100, 1), 2),
    }


def _generic_proxies(response: str, task: str) -> dict:
    """Fallback proxies for unknown modules."""
    return {
        "response_length":    len(response.split()),
        "writeback_present":  "writeback" in response.lower(),
    }


# ── Proxy adjustment ─────────────────────────────────────────────

def apply_proxy_adjustment(
    score: float,
    proxy_signals: dict,
    module_name: str,
    execution_score: Optional[float] = None,
) -> float:
    """
    Apply domain-specific floor/ceiling rules based on proxy signals.

    These are hard overrides — they cap or floor the score
    when objective signals indicate the LLM judge is wrong.

    Returns: adjusted score, clamped to [0.0, 1.0].
    Never raises.
    """
    adjusted = score

    try:
        if module_name == "coding":
            adjusted = _coding_adjustment(
                adjusted, proxy_signals, execution_score
            )
        elif module_name == "marketing":
            adjusted = _marketing_adjustment(adjusted, proxy_signals)
        elif module_name == "research":
            adjusted = _research_adjustment(adjusted, proxy_signals)

    except Exception as e:
        logging.debug(
            f"[ENGRAM] proxy_adjustment: failed: {e}"
        )

    return round(max(0.0, min(1.0, adjusted)), 4)


def _coding_adjustment(
    score: float,
    signals: dict,
    execution_score: Optional[float],
) -> float:
    """Floor/ceiling rules for coding module."""
    # Execution score overrides LLM judge when available
    if execution_score is not None:
        if execution_score == 1.0:
            score = max(score, 0.80)   # floor: all tests pass
        elif execution_score == 0.0:
            score = min(score, 0.45)   # ceiling: all tests fail

    # No write_file but task type implies implementation
    if not signals.get("write_file_called") and score > 0.70:
        score = min(score, 0.65)

    return score


def _marketing_adjustment(score: float, signals: dict) -> float:
    """Floor/ceiling rules for marketing module."""
    # Too many generic phrases — hard ceiling
    generic = signals.get("generic_phrase_count", 0)
    if generic >= 3:
        score = min(score, 0.50)
    elif generic >= 1:
        score = min(score, 0.75)

    # Zero specificity — hard ceiling
    if signals.get("specificity_signals", 0) == 0:
        score = min(score, 0.55)

    # Audience not named in copy task
    if not signals.get("audience_named", True):
        score = min(score, 0.70)

    return score


def _research_adjustment(score: float, signals: dict) -> float:
    """Floor/ceiling rules for research module."""
    # Zero named references — hard ceiling
    if signals.get("named_refs", 0) == 0:
        score = min(score, 0.55)

    # Zero quantified claims in analytical task
    if signals.get("quantified_claims", 0) == 0:
        score = min(score, 0.65)

    # Very short response for synthesis task
    if signals.get("word_count", 999) < 100:
        score = min(score, 0.50)

    return score


# ── Human correction injection ───────────────────────────────────

def inject_human_correction(
    log_path: str,
    module_name: str,
    task_id: str,
    llm_judge_score: float,
    human_score: float,
) -> None:
    """
    Record a human correction as a high-weight calibration entry.

    Called by: engram score --session X --task N --correct 0.95

    Human entries are weighted 3x in bias correction calculation.
    10 human corrections are worth ~30 auto entries for calibration.

    Never raises.
    """
    entry = {
        "ts":           datetime.utcnow().isoformat(),
        "module":       module_name,
        "task_type":    "human_correction",
        "task_id":      task_id,
        "llm_judge":    round(llm_judge_score, 4),
        "execution":    round(human_score, 4),
        "error":        round(human_score - llm_judge_score, 4),
        "proxy_signals": {},
        "source":       "human",
    }
    try:
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        logging.info(
            f"[ENGRAM] human correction: {module_name} "
            f"llm={llm_judge_score:.2f} → human={human_score:.2f} "
            f"(error={human_score - llm_judge_score:+.2f})"
        )
    except Exception as e:
        logging.warning(
            f"[ENGRAM] human correction: write failed: {e}"
        )


# ── Calibration statistics ───────────────────────────────────────

def calibration_stats(
    log_path: str,
    module_name: str,
) -> dict:
    """
    Summary statistics for a module's calibration log.
    Used by `engram doctor` and `engram module status`.

    Returns:
        {
          "total_entries":      int,
          "with_ground_truth":  int,
          "human_corrections":  int,
          "mean_error":         float,
          "mean_abs_error":     float,
          "bias_direction":     "pessimistic" | "optimistic" | "calibrated",
          "task_type_errors":   {task_type: mean_error},
        }
    """
    entries = load_calibration_log(log_path, last_n=500)
    module_entries = [e for e in entries if e.get("module") == module_name]

    with_gt  = [e for e in module_entries if e.get("error") is not None]
    human    = [e for e in module_entries if e.get("source") == "human"]

    if not with_gt:
        return {
            "total_entries":     len(module_entries),
            "with_ground_truth": 0,
            "human_corrections": len(human),
            "mean_error":        0.0,
            "mean_abs_error":    0.0,
            "bias_direction":    "unknown",
            "task_type_errors":  {},
        }

    errors     = [e["error"] for e in with_gt]
    mean_error = sum(errors) / len(errors)
    mean_abs   = sum(abs(e) for e in errors) / len(errors)

    bias = "calibrated"
    if mean_error > 0.05:
        bias = "pessimistic"   # scoring too low
    elif mean_error < -0.05:
        bias = "optimistic"    # scoring too high

    # Per task type
    task_types = set(e.get("task_type", "unknown") for e in with_gt)
    tt_errors  = {}
    for tt in task_types:
        tt_entries = [e for e in with_gt if e.get("task_type") == tt]
        if len(tt_entries) >= 2:
            tt_errors[tt] = round(
                sum(e["error"] for e in tt_entries) / len(tt_entries), 3
            )

    return {
        "total_entries":     len(module_entries),
        "with_ground_truth": len(with_gt),
        "human_corrections": len(human),
        "mean_error":        round(mean_error, 4),
        "mean_abs_error":    round(mean_abs, 4),
        "bias_direction":    bias,
        "task_type_errors":  tt_errors,
    }
