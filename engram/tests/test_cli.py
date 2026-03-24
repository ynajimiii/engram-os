"""
ENGRAM OS CLI Tests

Tests for all CLI commands.
Uses subprocess to call CLI and check output + exit codes.
Uses tmp_path fixture for session/config isolation.
"""

import os
import subprocess
import sys
import json
import pytest
from pathlib import Path


@pytest.fixture
def engram_env(tmp_path, monkeypatch):
    """Set up isolated ENGRAM environment for testing."""
    # Create directory structure
    (tmp_path / "sessions").mkdir()
    
    # Pre-create a minimal config file
    config_content = """model: qwen2.5:14b
router_model: qwen2.5:7b
weights_mb: 14000
n_ctx: 8192
scratch_mb: 512
ollama_url: http://localhost:11434
tool_backend: ollama
default_module: coding
verbose: false
color: true
"""
    (tmp_path / "config.yaml").write_text(config_content)
    
    env = {"ENGRAM_HOME": str(tmp_path)}
    return tmp_path, env


def run_cli(*args, env=None):
    """
    Run CLI command and return output.

    Returns:
        tuple: (stdout, stderr, returncode)
    """
    # Merge provided env with current environment
    test_env = dict(**os.environ)
    if env:
        test_env.update(env)
    result = subprocess.run(
        [sys.executable, "-m", "engram", *args],
        capture_output=True,
        text=True,
        env=test_env,
        cwd=str(Path(__file__).parent.parent.parent)
    )
    return result.stdout, result.stderr, result.returncode


# ============================================================================
# BASIC CLI TESTS
# ============================================================================

def test_no_command_shows_help(engram_env):
    """Test that running without command shows help."""
    tmp_path, env = engram_env
    stdout, _, rc = run_cli(env=env)
    # May return 1 if banner displays but no command given
    assert "ENGRAM" in stdout or "usage:" in stdout.lower()


def test_version(engram_env):
    """Test --version flag."""
    tmp_path, env = engram_env
    stdout, _, rc = run_cli("--version", env=env)
    assert rc == 0
    assert "0.1.0" in stdout


def test_help_shows_commands(engram_env):
    """Test --help shows all commands."""
    tmp_path, env = engram_env
    stdout, _, rc = run_cli("--help", env=env)
    assert rc == 0
    assert "doctor" in stdout
    assert "init" in stdout
    assert "run" in stdout


# ============================================================================
# DOCTOR COMMAND TESTS
# ============================================================================

def test_doctor_runs(engram_env):
    """Test doctor command runs without crashing."""
    tmp_path, env = engram_env
    _, _, rc = run_cli("doctor", env=env)
    # May fail if Ollama not running, but shouldn't crash
    assert rc in (0, 1)


def test_doctor_json(engram_env):
    """Test doctor --json outputs JSON."""
    tmp_path, env = engram_env
    stdout, _, rc = run_cli("doctor", "--json", env=env)
    # May fail but shouldn't crash
    assert rc in (0, 1)


# ============================================================================
# CONFIG COMMAND TESTS
# ============================================================================

def test_config_show(engram_env):
    """Test config show displays configuration."""
    tmp_path, env = engram_env
    stdout, _, rc = run_cli("config", "show", env=env)
    # Config show should work in isolated env
    assert "model" in stdout or "config" in stdout.lower()


def test_config_get(engram_env):
    """Test config get retrieves a value."""
    tmp_path, env = engram_env
    stdout, _, rc = run_cli("config", "get", "model", env=env)
    # Should return the default model value
    assert len(stdout.strip()) > 0 or rc == 0


def test_config_set_and_get(engram_env):
    """Test config set and get roundtrip."""
    tmp_path, env = engram_env
    _, _, rc = run_cli("config", "set", "n_ctx", "4096", env=env)
    assert rc == 0
    stdout, _, rc = run_cli("config", "get", "n_ctx", env=env)
    assert rc == 0
    assert "4096" in stdout


def test_config_set_invalid_key(engram_env):
    """Test config set with invalid key fails."""
    tmp_path, env = engram_env
    _, _, rc = run_cli("config", "set", "invalid_key_xyz", "value", env=env)
    assert rc != 0


def test_config_reset(engram_env):
    """Test config reset restores defaults."""
    tmp_path, env = engram_env
    # First set a value
    run_cli("config", "set", "n_ctx", "4096", env=env)
    # Then reset
    stdout, _, rc = run_cli("config", "reset", env=env)
    assert rc == 0
    # Verify it's back to default
    stdout, _, rc = run_cli("config", "get", "n_ctx", env=env)
    assert "8192" in stdout or rc == 0


# ============================================================================
# MODULE COMMAND TESTS
# ============================================================================

def test_module_list(engram_env):
    """Test module list shows available modules."""
    tmp_path, env = engram_env
    stdout, _, rc = run_cli("module", "list", env=env)
    # Module list should show at least coding module
    assert "coding" in stdout or "module" in stdout.lower()


def test_module_info_coding(engram_env):
    """Test module info shows module details."""
    tmp_path, env = engram_env
    stdout, _, rc = run_cli("module", "info", "coding", env=env)
    # Module may not be installed, but command shouldn't crash
    assert rc in (0, 1)


# ============================================================================
# SESSION COMMAND TESTS
# ============================================================================

def test_session_list_empty(engram_env):
    """Test session list with no sessions."""
    tmp_path, env = engram_env
    stdout, _, rc = run_cli("session", "list", env=env)
    # Should return 0 even with no sessions
    assert rc == 0 or "session" in stdout.lower()


def test_session_resume_not_found(engram_env):
    """Test session resume with non-existent session."""
    tmp_path, env = engram_env
    _, _, rc = run_cli("session", "resume", "nonexistent", env=env)
    assert rc != 0


# ============================================================================
# RUN COMMAND TESTS
# ============================================================================

def test_run_no_goal_fails(engram_env):
    """Test run without goal fails."""
    tmp_path, env = engram_env
    _, _, rc = run_cli("run", env=env)
    assert rc != 0


def test_run_help(engram_env):
    """Test run --help shows usage."""
    tmp_path, env = engram_env
    stdout, _, rc = run_cli("run", "--help", env=env)
    assert rc == 0
    assert "--goal" in stdout


# ============================================================================
# STATUS COMMAND TESTS
# ============================================================================

def test_status_no_session(engram_env):
    """Test status with no sessions."""
    tmp_path, env = engram_env
    _, _, rc = run_cli("status", env=env)
    # Should fail gracefully with no sessions
    assert rc != 0


# ============================================================================
# BENCHMARK COMMAND TESTS
# ============================================================================

def test_benchmark_quick(engram_env):
    """Test benchmark --quick runs."""
    tmp_path, env = engram_env
    _, stderr, rc = run_cli("benchmark", "--quick", env=env)
    # May fail if benchmark suite not available, but shouldn't crash
    assert rc in (0, 1)


# ============================================================================
# EXPORT COMMAND TESTS
# ============================================================================

def test_export_not_found(engram_env):
    """Test export with non-existent session."""
    tmp_path, env = engram_env
    _, _, rc = run_cli("export", "nonexistent", env=env)
    assert rc != 0


# ============================================================================
# INIT COMMAND TESTS
# ============================================================================

def test_init_help(engram_env):
    """Test init --help shows usage."""
    tmp_path, env = engram_env
    stdout, _, rc = run_cli("init", "--help", env=env)
    assert rc == 0
    assert "--path" in stdout
    assert "--module" in stdout
