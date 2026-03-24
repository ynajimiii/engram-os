"""
Tests for Phase 11 - LLM-as-Judge Quality Scorer

Tests for engram/core/scorer.py
"""

import pytest
from unittest.mock import MagicMock, patch

from engram.core.scorer import (
    QualityScore,
    score_from_execution,
    score_from_llm_judge,
    score_task,
    score_session,
    score_agent_turn,
    _detect_test_framework,
    _parse_test_output,
    _summarize_tool_calls,
    _parse_judge_response,
)
from engram.core.llm import LLMResponse, MessageRole


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_llm_call():
    """Create a mock LLM call function."""
    def mock_call(prompt, model="qwen3:30b-a3b-q4_K_M"):
        # Return a valid JSON response
        return '{"score": 0.85, "reason": "Good implementation", "correctness": 0.9, "completeness": 0.8, "convention_alignment": 0.85}'
    
    return mock_call


@pytest.fixture
def sample_tool_calls():
    """Sample tool calls for testing."""
    return [
        {
            "name": "read_file",
            "arguments": {"path": "src/auth.py"},
            "result": {"success": True, "result": {"content": "def login(): pass"}},
        },
        {
            "name": "write_file",
            "arguments": {"path": "src/auth.py", "content": "def login(): pass"},
            "result": {"success": True, "result": {"success": True}},
        },
        {
            "name": "run_command",
            "arguments": {"command": "pytest test_auth.py"},
            "result": {
                "success": True,
                "result": {"stdout": "5 passed, 0 failed", "returncode": 0},
            },
        },
    ]


# ============================================================================
# QUALITY SCORE DATA STRUCTURE TESTS
# ============================================================================

class TestQualityScore:
    """Tests for QualityScore dataclass."""
    
    def test_quality_score_creation(self):
        """Test creating a QualityScore."""
        score = QualityScore(
            score=0.85,
            source="execution",
            reason="5 tests passed",
        )
        
        assert score.score == 0.85
        assert score.source == "execution"
        assert score.reason == "5 tests passed"
    
    def test_quality_score_to_dict(self):
        """Test converting QualityScore to dictionary."""
        score = QualityScore(
            score=0.75,
            source="llm_judge",
            reason="Good but incomplete",
            details={"correctness": 0.8, "completeness": 0.7},
        )
        
        data = score.to_dict()
        
        assert data["score"] == 0.75
        assert data["source"] == "llm_judge"
        assert data["reason"] == "Good but incomplete"
        assert data["details"]["correctness"] == 0.8


# ============================================================================
# EXECUTION-BASED SCORING TESTS
# ============================================================================

class TestScoreFromExecution:
    """Tests for execution-based scoring."""
    
    def test_score_from_execution_pytest(self):
        """Test scoring from pytest output."""
        tool_calls = [
            {
                "name": "run_command",
                "arguments": {"command": "pytest test_auth.py"},
                "result": {
                    "stdout": "5 passed, 0 failed in 0.1s",
                    "returncode": 0,
                },
            }
        ]
        
        score = score_from_execution(tool_calls)
        
        assert score == 1.0
    
    def test_score_from_execution_pytest_failures(self):
        """Test scoring from pytest with failures."""
        tool_calls = [
            {
                "name": "run_command",
                "arguments": {"command": "pytest test_auth.py"},
                "result": {
                    "stdout": "3 passed, 2 failed in 0.1s",
                    "returncode": 1,
                },
            }
        ]
        
        score = score_from_execution(tool_calls)
        
        assert score == 0.6  # 3/5
    
    def test_score_from_execution_jest(self):
        """Test scoring from Jest output."""
        tool_calls = [
            {
                "name": "run_command",
                "arguments": {"command": "npm test"},
                "result": {
                    "stdout": "Tests:       8 passed, 8 total",
                    "returncode": 0,
                },
            }
        ]
        
        score = score_from_execution(tool_calls)
        
        assert score == 1.0
    
    def test_score_from_execution_go_test(self):
        """Test scoring from Go test output."""
        tool_calls = [
            {
                "name": "run_command",
                "arguments": {"command": "go test ./..."},
                "result": {
                    "stdout": "ok\tpackage\t0.001s",
                    "returncode": 0,
                },
            }
        ]
        
        score = score_from_execution(tool_calls)
        
        assert score == 1.0
    
    def test_score_from_execution_no_tests(self):
        """Test scoring when no tests executed."""
        tool_calls = [
            {
                "name": "read_file",
                "arguments": {"path": "src/auth.py"},
                "result": {"success": True},
            }
        ]
        
        score = score_from_execution(tool_calls)
        
        assert score is None
    
    def test_score_from_execution_multiple_test_runs(self):
        """Test scoring from multiple test runs."""
        tool_calls = [
            {
                "name": "run_command",
                "arguments": {"command": "pytest test_auth.py"},
                "result": {"stdout": "5 passed, 0 failed", "returncode": 0},
            },
            {
                "name": "run_command",
                "arguments": {"command": "pytest test_api.py"},
                "result": {"stdout": "3 passed, 2 failed", "returncode": 1},
            },
        ]
        
        score = score_from_execution(tool_calls)
        
        # Average of 1.0 and 0.6
        assert score == 0.8


class TestDetectTestFramework:
    """Tests for test framework detection."""
    
    def test_detect_pytest(self):
        """Test pytest detection."""
        assert _detect_test_framework("pytest test.py") == "pytest"
        assert _detect_test_framework("python -m pytest") == "pytest"
    
    def test_detect_jest(self):
        """Test Jest detection."""
        assert _detect_test_framework("jest") == "jest"
        assert _detect_test_framework("npm test") == "mocha"
    
    def test_detect_go_test(self):
        """Test Go test detection."""
        assert _detect_test_framework("go test ./...") == "go_test"
    
    def test_detect_unittest(self):
        """Test unittest detection."""
        assert _detect_test_framework("python -m unittest") == "unittest"
    
    def test_detect_unknown(self):
        """Test unknown framework."""
        assert _detect_test_framework("make test") is None


class TestParseTestOutput:
    """Tests for test output parsing."""
    
    def test_parse_pytest_output(self):
        """Test parsing pytest output."""
        score = _parse_test_output(
            stdout="5 passed, 0 failed in 0.1s",
            stderr="",
            returncode=0,
            framework="pytest",
        )
        
        assert score == 1.0
    
    def test_parse_jest_output(self):
        """Test parsing Jest output."""
        score = _parse_test_output(
            stdout="Tests:       8 passed, 8 total",
            stderr="",
            returncode=0,
            framework="jest",
        )
        
        assert score == 1.0
    
    def test_parse_unparseable_output(self):
        """Test parsing unparseable output."""
        score = _parse_test_output(
            stdout="Some random output",
            stderr="",
            returncode=0,
            framework="pytest",
        )
        
        # Should fall back to returncode
        assert score == 1.0


# ============================================================================
# LLM-AS-JUDGE SCORING TESTS
# ============================================================================

class TestScoreFromLLMJudge:
    """Tests for LLM-as-judge scoring."""
    
    def test_score_from_llm_judge(self, mock_llm_call):
        """Test LLM judge scoring."""
        score = score_from_llm_judge(
            task="Implement login form",
            output="def login(): pass",
            files=["src/auth.py"],
            tool_calls=[],
            llm_call=mock_llm_call,
        )
        
        assert score.score == 0.85
        assert score.source == "llm_judge"
        assert "Good implementation" in score.reason
    
    def test_score_from_llm_judge_with_tool_calls(self, mock_llm_call):
        """Test LLM judge scoring with tool calls."""
        tool_calls = [
            {"name": "read_file", "arguments": {"path": "src/auth.py"}},
            {"name": "write_file", "arguments": {"path": "src/auth.py"}},
        ]
        
        score = score_from_llm_judge(
            task="Implement login",
            output="def login(): pass",
            files=["src/auth.py"],
            tool_calls=tool_calls,
            llm_call=mock_llm_call,
        )
        
        assert score.score == 0.85
    
    def test_score_from_llm_judge_error_handling(self):
        """Test LLM judge error handling."""
        def bad_llm_call(prompt, model="qwen3:30b-a3b-q4_K_M"):
            raise Exception("LLM error")
        
        score = score_from_llm_judge(
            task="Test",
            output="Output",
            files=[],
            tool_calls=[],
            llm_call=bad_llm_call,
        )
        
        assert score.score == 0.5
        assert "Error" in score.reason


class TestSummarizeToolCalls:
    """Tests for tool call summarization."""
    
    def test_summarize_empty(self):
        """Test summarizing empty tool calls."""
        summary = _summarize_tool_calls([])
        
        assert "(no tool calls)" in summary
    
    def test_summarize_tool_calls(self, sample_tool_calls):
        """Test summarizing tool calls."""
        summary = _summarize_tool_calls(sample_tool_calls)
        
        assert "read_file" in summary
        assert "write_file" in summary
        assert "run_command" in summary
    
    def test_summarize_limits_to_10(self):
        """Test that summarization limits to 10 calls."""
        tool_calls = [{"name": f"tool_{i}", "arguments": {}} for i in range(15)]
        
        summary = _summarize_tool_calls(tool_calls)
        
        assert "10" in summary or "more" in summary


class TestParseJudgeResponse:
    """Tests for judge response parsing."""
    
    def test_parse_valid_json(self):
        """Test parsing valid JSON response."""
        response = '{"score": 0.8, "reason": "Good work"}'
        
        result = _parse_judge_response(response)
        
        assert result["score"] == 0.8
        assert result["reason"] == "Good work"
    
    def test_parse_json_in_text(self):
        """Test parsing JSON embedded in text."""
        response = """
        Here's my evaluation:
        {"score": 0.75, "reason": "Decent"}
        Hope this helps!
        """
        
        result = _parse_judge_response(response)
        
        assert result["score"] == 0.75
    
    def test_parse_key_value_fallback(self):
        """Test key-value parsing fallback."""
        response = '"score": 0.9, "reason": "Excellent"'
        
        result = _parse_judge_response(response)
        
        assert result.get("score") == 0.9
    
    def test_parse_invalid_response(self):
        """Test parsing invalid response."""
        response = "This is not valid at all"
        
        result = _parse_judge_response(response)
        
        # Should return empty dict or partial result
        assert isinstance(result, dict)


# ============================================================================
# MAIN SCORING FUNCTION TESTS
# ============================================================================

class TestScoreTask:
    """Tests for main score_task function."""
    
    def test_score_task_uses_execution_when_available(self):
        """Test that score_task uses execution scoring when available."""
        tool_calls = [
            {
                "name": "run_command",
                "arguments": {"command": "pytest test.py"},
                "result": {"stdout": "5 passed, 0 failed", "returncode": 0},
            }
        ]
        
        score = score_task(
            task="Test task",
            response="Output",
            tool_calls=tool_calls,
        )
        
        assert score.source == "execution"
        assert score.score == 1.0
    
    def test_score_task_falls_back_to_llm(self, mock_llm_call):
        """Test that score_task falls back to LLM when no tests."""
        tool_calls = [
            {"name": "read_file", "arguments": {"path": "test.py"}}
        ]
        
        score = score_task(
            task="Test task",
            response="Output",
            tool_calls=tool_calls,
            llm_call=mock_llm_call,
        )
        
        assert score.source == "llm_judge"
        assert score.score == 0.85
    
    def test_score_task_default_when_no_llm(self):
        """Test that score_task returns default when no LLM available."""
        tool_calls = [
            {"name": "read_file", "arguments": {"path": "test.py"}}
        ]
        
        score = score_task(
            task="Test task",
            response="Output",
            tool_calls=tool_calls,
            llm_call=None,
        )
        
        assert score.source == "default"
        assert score.score == 0.5


# ============================================================================
# AGENT INTEGRATION TESTS
# ============================================================================

class TestScoreAgentTurn:
    """Tests for agent integration."""
    
    def test_score_agent_turn(self, sample_tool_calls):
        """Test scoring an agent turn."""
        response = LLMResponse(
            content="Implemented login function",
            role=MessageRole.ASSISTANT,
        )

        session_log = []
        llm = MagicMock()
        llm.chat.return_value = '{"score": 0.9, "reason": "Excellent"}'

        score, log_entry = score_agent_turn(
            task="Implement login",
            response=response,
            tool_calls=sample_tool_calls,
            session_log=session_log,
            llm=llm,
        )

        # Score from execution (tests passed) - should be high
        assert score >= 0.9  # From execution (tests passed)
        assert "quality_score" in log_entry
        assert len(session_log) == 1


# ============================================================================
# SESSION SCORING TESTS
# ============================================================================

class TestScoreSession:
    """Tests for session scoring."""
    
    def test_score_session_empty(self):
        """Test scoring empty session."""
        stats = score_session([])
        
        assert stats["average_quality"] == 0.0
        assert stats["tasks_scored"] == 0
    
    def test_score_session_with_scores(self):
        """Test scoring session with quality scores."""
        session_log = [
            {"quality_score": 0.8, "task": "task1"},
            {"quality_score": 0.9, "task": "task2"},
            {"quality_score": 0.7, "task": "task3"},
        ]

        stats = score_session(session_log)

        assert abs(stats["average_quality"] - 0.8) < 0.001
        assert stats["min_quality"] == 0.7
        assert stats["max_quality"] == 0.9
        assert stats["tasks_scored"] == 3
    
    def test_score_session_quality_trend_improving(self):
        """Test quality trend detection - improving."""
        session_log = [
            {"quality_score": 0.5},
            {"quality_score": 0.6},
            {"quality_score": 0.8},
            {"quality_score": 0.9},
        ]
        
        stats = score_session(session_log)
        
        assert stats["quality_trend"] == "improving"
    
    def test_score_session_quality_trend_declining(self):
        """Test quality trend detection - declining."""
        session_log = [
            {"quality_score": 0.9},
            {"quality_score": 0.8},
            {"quality_score": 0.6},
            {"quality_score": 0.5},
        ]
        
        stats = score_session(session_log)
        
        assert stats["quality_trend"] == "declining"
    
    def test_score_session_quality_trend_stable(self):
        """Test quality trend detection - stable."""
        session_log = [
            {"quality_score": 0.7},
            {"quality_score": 0.75},
            {"quality_score": 0.7},
            {"quality_score": 0.8},
        ]
        
        stats = score_session(session_log)
        
        assert stats["quality_trend"] == "stable"


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestScorerIntegration:
    """Integration tests for the scorer."""
    
    def test_full_scoring_pipeline(self, mock_llm_call):
        """Test the full scoring pipeline."""
        # Task with test execution
        tool_calls_with_tests = [
            {
                "name": "run_command",
                "arguments": {"command": "pytest test.py"},
                "result": {"stdout": "5 passed, 0 failed", "returncode": 0},
            }
        ]
        
        score1 = score_task(
            task="Task with tests",
            response="Output",
            tool_calls=tool_calls_with_tests,
        )
        
        assert score1.source == "execution"
        assert score1.score == 1.0
        
        # Task without tests (uses LLM judge)
        tool_calls_no_tests = [
            {"name": "read_file", "arguments": {"path": "test.py"}}
        ]
        
        score2 = score_task(
            task="Task without tests",
            response="Output",
            tool_calls=tool_calls_no_tests,
            llm_call=mock_llm_call,
        )
        
        assert score2.source == "llm_judge"
        assert score2.score == 0.85
        
        # Session scoring
        session_log = [
            {"quality_score": score1.score, "task": "task1"},
            {"quality_score": score2.score, "task": "task2"},
        ]
        
        stats = score_session(session_log)
        
        assert stats["average_quality"] > 0.9
        assert stats["tasks_scored"] == 2
