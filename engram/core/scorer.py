"""
LLM-as-Judge Quality Scorer - Phase 11

Scores task completion quality using two paths:
1. Execution truth (ground truth from test results)
2. LLM-as-judge (semantic evaluation when no tests)

Usage:
    from engram.core.scorer import score_task
    
    quality = score_task(
        task="Implement login form",
        response=response_text,
        tool_calls=tool_calls,
        session_log=session_log,
        llm_call=llm.chat,
    )
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from .llm import LLMResponse

# Pydantic for structured outputs (Ollama schema enforcement)
try:
    from pydantic import BaseModel as _PydanticBase
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False
    _PydanticBase = object


# ============================================================================
# CONFIGURATION
# ============================================================================

# Default model for scoring (fast, cheap)
SCORER_MODEL = "qwen3:30b-a3b-q4_K_M"

# Minimum quality threshold
MIN_QUALITY_THRESHOLD = 0.5

# Test framework patterns
TEST_PATTERNS = {
    "pytest": r"(\d+)\s+passed.*?(\d+)\s+failed",
    "jest": r"Tests:\s+(\d+)\s+passed.*?(\d+)\s+total",
    "go_test": r"(\d+)\s+passed.*?(\d+)\s+failed",
    "unittest": r"OK\s+\(tests=(\d+)\)",
    "mocha": r"(\d+)\s+passing.*?(\d+)\s+failing",
}


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class QualityScore:
    """
    Quality score for a task completion.
    
    Attributes:
        score: Score from 0.0 to 1.0
        source: How score was determined (execution or llm_judge)
        reason: Explanation of score
        details: Additional details
    """
    score: float
    source: str  # "execution" or "llm_judge"
    reason: str
    details: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "score": self.score,
            "source": self.source,
            "reason": self.reason,
            "details": self.details or {},
        }


# Pydantic schema for structured judge output (Ollama enforces this)
if HAS_PYDANTIC:
    class _JudgeSchema(_PydanticBase):
        """
        Pydantic schema for structured judge output.
        Ollama enforces this at generation time —
        model cannot deviate from this structure.
        """
        score:               float  # 0.0-1.0 overall
        correctness:         float  # 0.0-1.0
        completeness:        float  # 0.0-1.0
        convention_alignment:float  # 0.0-1.0
        reason:              str    # one sentence


# ============================================================================
# PHASE 1: EXECUTION-BASED SCORING
# ============================================================================

def score_from_execution(tool_calls: List[Dict[str, Any]]) -> Optional[float]:
    """
    Score task based on test execution results.
    
    Parses test framework output to extract pass/fail counts.
    Returns None if no tests were executed.
    
    Args:
        tool_calls: List of tool calls from session
    
    Returns:
        Score 0.0-1.0, or None if no tests executed
    
    Example:
        >>> tool_calls = [
        ...     {
        ...         "name": "run_command",
        ...         "arguments": {"command": "pytest test_auth.py"},
        ...         "result": {"stdout": "5 passed, 0 failed", "returncode": 0}
        ...     }
        ... ]
        >>> score = score_from_execution(tool_calls)
        >>> print(f"Score: {score}")  # Score: 1.0
    """
    test_scores = []
    
    for call in tool_calls:
        # Only consider run_command calls
        if call.get("name") != "run_command":
            continue
        
        command = call.get("arguments", {}).get("command", "")
        
        # Detect test commands
        test_framework = _detect_test_framework(command)
        if not test_framework:
            continue
        
        result = call.get("result", {})
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        returncode = result.get("returncode", -1)
        
        # Parse test output
        score = _parse_test_output(stdout, stderr, returncode, test_framework)
        if score is not None:
            test_scores.append(score)
    
    if not test_scores:
        return None
    
    # Return average score
    return sum(test_scores) / len(test_scores)


def _detect_test_framework(command: str) -> Optional[str]:
    """Detect which test framework is being used."""
    command_lower = command.lower()
    
    if "pytest" in command_lower:
        return "pytest"
    elif "jest" in command_lower:
        return "jest"
    elif "go test" in command_lower:
        return "go_test"
    elif "unittest" in command_lower or "python -m unittest" in command_lower:
        return "unittest"
    elif "mocha" in command_lower or "npm test" in command_lower:
        return "mocha"
    
    return None


def _parse_test_output(
    stdout: str,
    stderr: str,
    returncode: int,
    framework: str
) -> Optional[float]:
    """
    Parse test framework output to extract pass rate.

    Args:
        stdout: Standard output from test run
        stderr: Standard error from test run
        returncode: Return code from test run
        framework: Test framework name

    Returns:
        Pass rate 0.0-1.0, or None if unparseable
    """
    output = stdout + stderr
    results = {"passed": 0, "failed": 0}

    if framework == "pytest":
        # Standard pytest
        passed_match = re.search(r"(\d+) passed", output)
        failed_match = re.search(r"(\d+) failed", output)

        if passed_match:
            results["passed"] = int(passed_match.group(1))
        if failed_match:
            results["failed"] = int(failed_match.group(1))

        # pytest-xdist support
        if "[gw" in output:
            results["passed"] += output.count("] PASSED")
            results["failed"] += output.count("] FAILED")

        total = results["passed"] + results["failed"]
        if total == 0:
            # Unparseable output — fall back to returncode
            pass  # will hit fallback logic below
        else:
            return results["passed"] / total

    elif framework == "jest":
        match = re.search(TEST_PATTERNS["jest"], output)
        if match:
            passed = int(match.group(1))
            total = int(match.group(2))
            return passed / total if total > 0 else 0.0

    elif framework == "go_test":
        if returncode == 0:
            return 1.0
        elif returncode == 1:
            return 0.0

    elif framework == "unittest":
        match = re.search(TEST_PATTERNS["unittest"], output)
        if match and returncode == 0:
            return 1.0
        elif returncode != 0:
            return 0.0
    
    elif framework == "mocha":
        # Pattern: "5 passing (100ms)" or "2 failing"
        match = re.search(TEST_PATTERNS["mocha"], output)
        if match:
            passing = int(match.group(1))
            failing = int(match.group(2)) if match.group(2) else 0
            total = passing + failing
            return passing / total if total > 0 else 0.0
    
    # Fallback: returncode based
    if returncode == 0:
        return 1.0
    elif returncode > 0:
        return 0.0
    
    return None


# ============================================================================
# PHASE 2: LLM-AS-JUDGE SCORING
# ============================================================================

JUDGE_PROMPT = """You are a strict quality evaluator
for an AI coding agent. Be honest and critical.
Poor work should receive low scores.

TASK: {task}

RESPONSE:
{output}

FILES MODIFIED: {files}
TOOL CALLS: {tool_summary}

Score each dimension 0.0-1.0 using these anchors:

correctness:
  0.0 = factually wrong, hallucinated, harmful
  0.2 = mostly wrong with minor correct parts
  0.5 = half correct, half wrong
  0.8 = mostly correct, minor errors
  1.0 = completely accurate, no errors

completeness:
  0.0 = task ignored or not addressed
  0.2 = barely started, major parts missing
  0.5 = half done, significant gaps remain
  0.8 = mostly complete, minor omissions
  1.0 = fully addressed, nothing missing

convention_alignment:
  0.0 = ignores all established patterns
  0.5 = some patterns followed, others ignored
  1.0 = perfectly follows all conventions

IMPORTANT:
- A response that just says "CONFIRMED" with no
  content scores 0.1-0.2 on completeness
- A response with hallucinated fields scores 0.0-0.2
  on correctness
- Only truly excellent responses earn 0.9-1.0
- Most responses should score 0.5-0.8
- Use the full range — do not cluster near 1.0

score = average of correctness + completeness +
        convention_alignment
reason = one critical sentence explaining the score"""


def score_from_llm_judge(
    task: str,
    output: str,
    files: List[str],
    tool_calls: List[Dict[str, Any]],
    llm_call: Callable[[str], str],
    model: str = SCORER_MODEL,
    ollama_url: str = "http://localhost:11434",
) -> QualityScore:
    """
    Score using Ollama structured outputs.
    Model is schema-constrained — guaranteed valid JSON.
    No parsing, no regex, no fallback needed.
    """
    import logging

    tool_summary = _summarize_tool_calls(tool_calls)
    files_text = (
        "\n".join(f"  - {f}" for f in files)
        if files else "  (none)"
    )
    if len(output) > 3000:
        output = output[:3000] + "\n... [truncated]"

    prompt = JUDGE_PROMPT.format(
        task=task,
        output=output,
        files=files_text,
        tool_summary=tool_summary,
    )

    # PATH A — Ollama Python package with schema enforcement
    if HAS_PYDANTIC:
        try:
            import ollama as _ollama

            resp = _ollama.chat(
                model=model,
                messages=[{
                    "role": "user",
                    "content": prompt,
                }],
                format=_JudgeSchema.model_json_schema(),
                options={"temperature": 0},
            )

            judge = _JudgeSchema.model_validate_json(
                resp.message.content
            )

            # Average sub-scores for final score
            sub = [
                judge.correctness,
                judge.completeness,
                judge.convention_alignment,
            ]
            computed = sum(sub) / len(sub)

            # Use explicit score if provided and
            # close to computed average
            final_score = judge.score
            if abs(judge.score - computed) > 0.15:
                # Model deviated — use computed average
                final_score = round(computed, 3)

            logging.info(
                f"[ENGRAM] judge: score={final_score:.3f} "
                f"correct={judge.correctness:.2f} "
                f"complete={judge.completeness:.2f} "
                f"conv={judge.convention_alignment:.2f}"
            )

            return QualityScore(
                score=max(0.0, min(1.0, final_score)),
                source="llm_judge",
                reason=judge.reason,
                details={
                    "correctness":
                        judge.correctness,
                    "completeness":
                        judge.completeness,
                    "convention_alignment":
                        judge.convention_alignment,
                    "model": model,
                },
            )

        except Exception as e:
            logging.warning(
                f"[ENGRAM] structured judge failed: {e}"
                f" — falling back to requests"
            )
            # Fall through to PATH B

    # PATH B — Direct requests with format parameter
    # (works without ollama Python package)
    try:
        import requests, json

        schema = {
            "type": "object",
            "properties": {
                "score": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
                "correctness": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
                "completeness": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
                "convention_alignment": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
                "reason": {"type": "string"},
            },
            "required": [
                "score", "correctness", "completeness",
                "convention_alignment", "reason",
            ],
        }

        payload = {
            "model":    model,
            "messages": [{
                "role":    "user",
                "content": prompt,
            }],
            "stream":   False,
            "format":   schema,
            "options":  {"temperature": 0},
        }

        r = requests.post(
            f"{ollama_url}/api/chat",
            json=payload,
            timeout=60,
        )
        r.raise_for_status()

        content = r.json()["message"]["content"]
        data    = json.loads(content)

        sub = [
            float(data.get("correctness", 0.5)),
            float(data.get("completeness", 0.5)),
            float(data.get("convention_alignment", 0.5)),
        ]
        final_score = float(
            data.get("score", sum(sub) / len(sub))
        )

        logging.info(
            f"[ENGRAM] judge (requests): "
            f"score={final_score:.3f}"
        )

        return QualityScore(
            score=max(0.0, min(1.0, final_score)),
            source="llm_judge",
            reason=data.get("reason", ""),
            details={
                "correctness":
                    data.get("correctness"),
                "completeness":
                    data.get("completeness"),
                "convention_alignment":
                    data.get("convention_alignment"),
                "model": model,
            },
        )

    except Exception as e:
        logging.error(
            f"[ENGRAM] judge PATH B failed: {e}"
        )
        return QualityScore(
            score=0.0,
            source="judge_error",
            reason=f"Both judge paths failed: {str(e)[:80]}",
        )


def _summarize_tool_calls(tool_calls: List[Dict[str, Any]]) -> str:
    """Summarize tool calls for judge prompt."""
    if not tool_calls:
        return "  (no tool calls)"
    
    lines = []
    for call in tool_calls[:10]:  # Limit to 10 calls
        name = call.get("name", "unknown")
        args = call.get("arguments", {})
        result = call.get("result", {})
        
        # Summarize arguments
        args_summary = ", ".join(f"{k}={v}" for k, v in list(args.items())[:3])
        
        # Summarize result
        if result.get("success"):
            result_summary = "success"
        else:
            result_summary = f"error: {result.get('error', 'unknown')}"
        
        lines.append(f"  - {name}({args_summary}) → {result_summary}")
    
    if len(tool_calls) > 10:
        lines.append(f"  ... and {len(tool_calls) - 10} more calls")
    
    return "\n".join(lines)


def _parse_judge_response(raw_response: str) -> Dict[str, Any]:
    """Parse LLM judge response — handles fences and think blocks."""
    import re, json

    clean = raw_response.strip()

    # Strip <think> blocks (qwen3 thinking mode)
    clean = re.sub(
        r'<think>.*?</think>', '',
        clean, flags=re.DOTALL
    ).strip()

    # Strip markdown fences
    if '```' in clean:
        clean = re.sub(r'```(?:json)?\s*', '', clean)
        clean = clean.replace('```', '').strip()

    # Non-greedy: find first complete JSON object only
    json_match = re.search(r'\{[^{}]*\}', clean, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    # Fallback: extract each field individually
    result = {}
    for key in [
        'score', 'correctness',
        'completeness', 'convention_alignment'
    ]:
        m = re.search(
            rf'"{key}":\s*([\d.]+)', clean
        )
        if m:
            result[key] = float(m.group(1))

    reason_m = re.search(
        r'"reason":\s*"([^"]+)"', clean
    )
    if reason_m:
        result["reason"] = reason_m.group(1)

    return result


# ============================================================================
# MAIN SCORING FUNCTION
# ============================================================================

def score_task(
    task: str,
    response: str,
    tool_calls: List[Dict[str, Any]],
    session_log: Optional[List[Dict[str, Any]]] = None,
    llm_call: Optional[Callable[[str], str]] = None,
    model: str = SCORER_MODEL,
    files_modified: Optional[List[str]] = None,
    module_name: str = "coding",
    task_type: str = "general",
) -> QualityScore:
    """
    Score a task completion.

    Tries execution-based scoring first (ground truth),
    falls back to LLM judge (semantic evaluation).
    
    Now with domain-aware calibration:
      - Loads rubric from modules/{module_name}/scorer_rubric.md
      - Computes domain-specific proxy signals
      - Applies bias correction from calibration history
      - Applies proxy-based floor/ceiling adjustments
      - Logs to calibration file for future improvement

    Args:
        task: Task description
        response: Agent's response/output
        tool_calls: List of tool calls made
        session_log: Full session log (optional)
        llm_call: Function to call LLM (required for fallback)
        model: Model to use for judging
        files_modified: List of files modified (optional)
        module_name: Module domain (coding, marketing, research)
        task_type: Task type for calibration (fix_bug, write_tests, etc.)

    Returns:
        QualityScore with score 0.0-1.0 and reasoning

    Example:
        >>> from engram.core.llm import BaseLLM
        >>> llm = BaseLLM()
        >>> score = score_task(
        ...     task="Implement login form",
        ...     response=response_text,
        ...     tool_calls=tool_calls,
        ...     llm_call=llm.chat,
        ...     module_name="coding",
        ...     task_type="implement_feature",
        ... )
        >>> print(f"Quality: {score.score:.2f} ({score.source})")
    """
    # Load domain-specific rubric from module file
    # Falls back to hardcoded rubric if file not found
    from pathlib import Path as _Path
    _rubric_path = (
        _Path(__file__).parent.parent
        / "modules" / module_name / "scorer_rubric.md"
    )
    if _rubric_path.exists():
        _RUBRIC = _rubric_path.read_text(encoding="utf-8")
    else:
        # Fallback to hardcoded rubric (JUDGE_PROMPT already defined)
        _RUBRIC = JUDGE_PROMPT

    # Compute domain-specific proxy signals
    from engram.core.scorer_calibration import (
        compute_proxy_signals,
        apply_proxy_adjustment,
        append_calibration_entry,
        get_bias_correction,
    )

    _proxy_signals = compute_proxy_signals(response, task, module_name)

    _cal_log_path = str(
        _Path(__file__).parent.parent
        / "sessions"
        / f"scorer_calibration_{module_name}.jsonl"
    )

    # PATH 1: Try execution-based scoring (ground truth)
    exec_score = score_from_execution(tool_calls)

    if exec_score is not None:
        # Apply proxy adjustment even for execution scores
        _adjusted = apply_proxy_adjustment(
            exec_score, _proxy_signals, module_name, exec_score
        )
        
        # Append to calibration log
        try:
            append_calibration_entry(
                log_path=_cal_log_path,
                module_name=module_name,
                task_type=task_type,
                llm_judge_score=_adjusted,
                execution_score=exec_score,
                proxy_signals=_proxy_signals,
                source="auto",
            )
        except Exception as _cal_err:
            logging.debug(f"[ENGRAM] calibration append: {_cal_err}")
        
        return QualityScore(
            score=_adjusted,
            source="execution",
            reason=f"Test execution: {exec_score * 100:.0f}% pass rate (calibrated)",
            details={"test_framework": _detect_test_framework(
                tool_calls[-1].get("arguments", {}).get("command", "")
            ) if tool_calls else None, "proxy_signals": _proxy_signals},
        )

    # PATH 2: Fall back to LLM judge
    if llm_call is None:
        # No LLM available - return default score
        return QualityScore(
            score=0.5,
            source="default",
            reason="No execution results or LLM available for scoring",
        )

    # Get raw LLM judge score
    _judge_result = score_from_llm_judge(
        task=task,
        output=response,
        files=files_modified or [],
        tool_calls=tool_calls,
        llm_call=llm_call,
        model=model,
    )
    
    # Apply bias correction from calibration history
    _bias = get_bias_correction(
        module_name, task_type, _cal_log_path
    )
    _corrected = max(0.0, min(1.0, _judge_result.score + _bias))

    # Apply proxy adjustment (domain-specific floor/ceiling)
    _execution = None  # No execution score available in this path
    _final_score = apply_proxy_adjustment(
        _corrected, _proxy_signals, module_name, _execution
    )

    # Append to calibration log for future bias correction
    try:
        append_calibration_entry(
            log_path=_cal_log_path,
            module_name=module_name,
            task_type=task_type,
            llm_judge_score=_final_score,
            execution_score=_execution,
            proxy_signals=_proxy_signals,
            source="auto",
        )
    except Exception as _cal_err:
        logging.debug(f"[ENGRAM] calibration append: {_cal_err}")

    return QualityScore(
        score=_final_score,
        source="llm_judge_calibrated",
        reason=_judge_result.reason + f" [calibrated: bias={_bias:+.3f}]",
        details={
            **(_judge_result.details or {}),
            "bias_correction": _bias,
            "proxy_signals": _proxy_signals,
        },
    )


# ============================================================================
# INTEGRATION WITH AGENT
# ============================================================================

def score_agent_turn(
    task: str,
    response: LLMResponse,
    tool_calls: List[Dict[str, Any]],
    session_log: List[Dict[str, Any]],
    llm: Any,  # BaseLLM
    files_modified: Optional[List[str]] = None,
) -> Tuple[float, Dict[str, Any]]:
    """
    Score an agent turn and log to session.
    
    Convenience wrapper for integration with agent_turn().
    
    Args:
        task: Task description
        response: LLM response
        tool_calls: Tool calls made
        session_log: Session log to update
        llm: LLM instance for judging
        files_modified: Files modified
    
    Returns:
        Tuple of (quality_score, log_entry)
    """
    # Score the task
    quality = score_task(
        task=task,
        response=response.content,
        tool_calls=tool_calls,
        session_log=session_log,
        llm_call=llm.chat,
        files_modified=files_modified,
    )
    
    # Create log entry
    log_entry = {
        "task": task,
        "response_length": len(response.content),
        "tool_calls_count": len(tool_calls),
        "quality_score": quality.score,
        "quality_source": quality.source,
        "quality_reason": quality.reason,
        "timestamp": datetime.now().isoformat(),
    }
    
    # Append to session log
    session_log.append(log_entry)
    
    return quality.score, log_entry


# ============================================================================
# BATCH SCORING
# ============================================================================

def score_session(session_log: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Score an entire session.
    
    Args:
        session_log: Session log with quality_score entries
    
    Returns:
        Session statistics
    """
    scores = [
        entry.get("quality_score", 0)
        for entry in session_log
        if "quality_score" in entry
    ]
    
    if not scores:
        return {
            "average_quality": 0.0,
            "min_quality": 0.0,
            "max_quality": 0.0,
            "tasks_scored": 0,
        }
    
    return {
        "average_quality": sum(scores) / len(scores),
        "min_quality": min(scores),
        "max_quality": max(scores),
        "tasks_scored": len(scores),
        "quality_trend": _calculate_quality_trend(scores),
    }


def _calculate_quality_trend(scores: List[float]) -> str:
    """Calculate quality trend from scores."""
    if len(scores) < 2:
        return "insufficient_data"
    
    # Compare first half vs second half
    mid = len(scores) // 2
    first_half_avg = sum(scores[:mid]) / mid if mid > 0 else 0
    second_half_avg = sum(scores[mid:]) / (len(scores) - mid) if len(scores) - mid > 0 else 0
    
    diff = second_half_avg - first_half_avg
    
    if diff > 0.1:
        return "improving"
    elif diff < -0.1:
        return "declining"
    else:
        return "stable"


# ============================================================================
# CLI COMMAND
# ============================================================================

def cmd_score(args) -> int:
    """
    CLI command: engram score --session session_id
    
    Scores a past session.
    """
    from .session import SessionManager
    
    print(f"\n{'=' * 60}")
    print("ENGRAM OS - Session Scoring")
    print(f"{'=' * 60}\n")
    
    # Load session
    manager = SessionManager()
    session = manager.get_session(args.session)
    
    if not session:
        print(f"✗ Session not found: {args.session}")
        return 1
    
    # Score session
    stats = score_session(session.state.context_window)
    
    print(f"Session: {session.session_id}")
    print(f"Tasks scored: {stats['tasks_scored']}")
    print(f"Average quality: {stats['average_quality']:.2f}")
    print(f"Min quality: {stats['min_quality']:.2f}")
    print(f"Max quality: {stats['max_quality']:.2f}")
    print(f"Quality trend: {stats['quality_trend']}")
    print()
    
    return 0


def create_score_parser(subparsers) -> None:
    """Create argument parser for score command."""
    parser = subparsers.add_parser(
        'score',
        help='Score a past session',
        description='Calculate quality scores for a session',
    )
    
    parser.add_argument(
        '--session', '-s',
        required=True,
        help='Session ID to score',
    )
    
    parser.set_defaults(func=cmd_score)


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(
        description='ENGRAM OS - Quality Scorer',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python -m engram.core.scorer --session abc123
        ''',
    )
    
    create_score_parser(parser)
    args = parser.parse_args()
    
    exit(args.func(args))
