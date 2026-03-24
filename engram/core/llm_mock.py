# engram/core/llm_mock.py
"""
MockLLM — deterministic LLM replacement for testing.

Drop-in replacement for BaseLLM.
Returns crafted strings that satisfy every downstream
consumer in the ENGRAM OS pipeline.

Usage:
    from engram.core.llm_mock import MockLLM
    llm = MockLLM()

    # In code_command.py smoke test:
    # Pass MockLLM() wherever BaseLLM instance is used.

Never calls Ollama. Never requires GPU.
Deterministic — same input always produces same output.
"""

import json
import logging
from datetime import datetime
from typing import Optional


# ── Canned responses ────────────────────────────────────────────
# Each response is crafted to satisfy one specific consumer.
# The writeback block satisfies parse_writeback().
# The score JSON satisfies score_task().
# The patch text satisfies apply_patch() + learning_cycle().

_AGENT_RESPONSE = """\
I have completed the task successfully.

Found the following structure:
- engram/core/ — 12 files
- engram/cli/  — 6 files
- engram/tools/ — 4 files
- tests/        — 8 files

Total: 30 Python files identified via list_directory.

```writeback
module: coding
status: done
files_modified: []
conventions_learned: null
next_focus: null
evict: []
```
"""

_SCORE_RESPONSE = json.dumps({
    "score":   0.82,
    "reasons": [
        "Task completed accurately",
        "Writeback block present and valid",
        "No hallucinated file paths",
    ]
})

_PATCH_RESPONSE = """\
You are ENGRAM — a surgical CLI coding agent.
You operate inside a project codebase.
You have tools: read_text_file, write_file, list_directory,
run_command, diff_files, search_code.

RULES:
1. Read before you write. Always read the file first.
2. Preserve existing functionality. Never delete working code.
3. Make the smallest change that satisfies the task.
4. Run tests after every change. Use run_command for pytest.
5. If a task is ambiguous, read more files before asking.
6. Never use run_command for destructive filesystem ops.
7. Report exactly what changed. No hallucinated file paths.

LEARNED PATTERNS (auto-applied):
- Always check file exists before reading (prevents tool errors)
- Run pytest after every write to confirm no regressions

WRITEBACK:
End every response with this exact block:
```writeback
module: coding
status: done|in_progress|blocked
files_modified: [list files you actually changed]
conventions_learned: [pattern you discovered, or null]
next_focus: [what should be loaded next, or null]
evict: [chunk IDs no longer needed, or []]
```
This block is mandatory. Do not skip it.
"""

_DISTILL_RESPONSE = json.dumps([{
    "task_type":  "file_listing",
    "insight":    "Use list_directory recursively for project-wide file counts",
    "quality_score": 0.82,
    "source_tasks": ["mock_task_001"],
}])

_LEARNING_CYCLE_RESPONSE = json.dumps({
    "section": "RULES",
    "old_text": "1. Read before you write. Always read the file first.",
    "new_text": "1. Read before you write. Always read the file first. Check if file exists.",
    "expected_improvement": 0.08,
    "reason": "Added explicit file existence check based on observed patterns"
})


class MockLLMResponse:
    """
    Minimal LLMResponse replacement.
    Satisfies all field accesses used across the codebase.
    """
    def __init__(
        self,
        content: str = "",
        role = None,
        finish_reason: Optional[str] = None,
        usage: Optional[dict] = None,
        metadata: Optional[dict] = None,
        tool_calls: Optional[list] = None,
        thinking: Optional[str] = None,
    ):
        from engram.core.llm import MessageRole
        self.content    = content
        self.role       = role or MessageRole.ASSISTANT
        self.finish_reason = finish_reason
        self.usage      = usage or {}
        self.metadata   = metadata or {}
        self.tool_calls = tool_calls or []
        self.thinking   = thinking
        # Alias for compatibility
        self.text       = content

    def to_message(self):
        """Convert to Message like real LLMResponse."""
        from engram.core.llm import Message
        return Message(
            role=self.role,
            content=self.content,
            tool_calls=self.tool_calls,
        )


class MockLLM:
    """
    Deterministic mock LLM for smoke testing.

    Inherits from nothing — it is a structural duck-type
    replacement for BaseLLM.
    """

    def __init__(
        self,
        provider=None,
        config=None,
        model: str = "mock",
        base_url: str = "http://localhost:11434",
        **kwargs,
    ):
        self.model    = model
        self.base_url = base_url
        self._provider = provider
        self._config = config
        self._call_log: list = []
        logging.info("[ENGRAM] MockLLM initialized")

    def _select_response(self, prompt: str) -> str:
        """
        Select which canned response to return based on
        prompt content. Order matters — check most specific
        patterns first.
        """
        p = prompt.lower() if prompt else ""

        # Scorer prompt — contains rubric keywords
        if (
            '"score"' in p
            or 'score the response' in p
            or ('task:' in p and 'response:' in p)
            or 'rubric' in p
            or 'criteria' in p
            or 'quality' in p
        ):
            return _SCORE_RESPONSE

        # Learner / patch prompt
        if (
            'system prompt' in p
            or 'improve' in p
            or 'observed patterns' in p
            or 'prompt_version' in p
            or 'rewrite' in p
            or 'learning cycle' in p
        ):
            return _LEARNING_CYCLE_RESPONSE

        # Distillation prompt
        if (
            'distill' in p
            or 'extract' in p and 'pattern' in p
            or 'tactical' in p
            or 'experience' in p
        ):
            return _DISTILL_RESPONSE

        # Default — agent response with writeback
        return _AGENT_RESPONSE

    def _log_call(self, method: str, prompt: str, response: str) -> None:
        """Record every call for test inspection."""
        self._call_log.append({
            "method":    method,
            "prompt":    prompt[:100] if prompt else "",
            "response":  response[:100],
            "ts":        datetime.utcnow().isoformat(),
        })

    def _extract_prompt(self, messages) -> str:
        """
        Extract a single prompt string from a messages list.
        Handles list of dicts and Message objects.
        """
        if isinstance(messages, str):
            return messages
        if not messages:
            return ""
        parts = []
        for m in messages:
            if isinstance(m, dict):
                parts.append(str(m.get("content", "")))
            elif hasattr(m, "content"):
                parts.append(str(m.content))
            else:
                parts.append(str(m))
        return " ".join(parts)

    # ── Primary generation methods ──────────────────────────────

    def complete(
        self,
        messages=None,
        prompt: Optional[str] = None,
        config=None,
        tools=None,
        mcp_client=None,
        **kwargs,
    ):
        """
        Primary method used by agent_turn() / worker_call().
        Returns MockLLMResponse.
        """
        # Extract prompt text
        p = prompt or self._extract_prompt(messages or [])
        text = self._select_response(p)
        self._log_call("complete", p, text)
        logging.debug(f"[MockLLM] complete() → {text[:60]}")
        return MockLLMResponse(content=text)

    def chat(
        self,
        user_message: str = "",
        system_prompt: Optional[str] = None,
        prompt: str = "",
        messages=None,
        **kwargs,
    ):
        """
        Method used by score_task() via llm_call=llm.chat.
        Returns MockLLMResponse.
        """
        # Build prompt from various input styles
        p = prompt or user_message or self._extract_prompt(messages or [])
        if system_prompt:
            p = f"{system_prompt}\n\n{p}"
        text = self._select_response(p)
        self._log_call("chat", p, text)
        logging.debug(f"[MockLLM] chat() → {text[:60]}")
        return MockLLMResponse(content=text)

    def generate(
        self,
        prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs,
    ):
        """
        Method used by scorer.py and learner.py directly.
        Returns MockLLMResponse.
        """
        text = self._select_response(prompt)
        self._log_call("generate", prompt, text)
        logging.debug(f"[MockLLM] generate() → {text[:60]}")
        return MockLLMResponse(content=text)

    # ── Utility ─────────────────────────────────────────────────

    def get_call_log(self) -> list:
        """Return all recorded calls for test inspection."""
        return list(self._call_log)

    def reset_call_log(self) -> None:
        """Clear call log between test runs."""
        self._call_log = []

    def configure(self, **kwargs) -> None:
        """Configure mock LLM (no-op for compatibility)."""
        pass

    def set_provider(self, provider) -> None:
        """Set provider (no-op for compatibility)."""
        self._provider = provider


def make_mock_llm_call(mock_llm: MockLLM):
    """
    Return a plain callable suitable for llm_call= params.
    score_task(), distill_experiences(), learning_cycle()
    all take llm_call as a function(prompt: str) -> str.

    Usage:
        mock = MockLLM()
        scored = score_task(
            ...,
            llm_call=make_mock_llm_call(mock),
        )
    """
    def _call(prompt: str, model: str = None, **kwargs) -> str:
        del model  # unused
        result = mock_llm.chat(prompt=prompt, **kwargs)
        if hasattr(result, "text"):    return result.text
        if hasattr(result, "content"): return result.content
        return str(result)
    return _call
