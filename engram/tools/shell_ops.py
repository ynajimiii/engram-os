# engram/tools/shell_ops.py
"""
Shell operation tools for ENGRAM OS coding agent.

Run commands and capture output.
"""

import subprocess
import logging
from typing import Any, Dict, List, Optional


def run_command(
    command: str,
    cwd: Optional[str] = None,
    timeout: int = 300,
    shell: bool = True,
) -> Dict[str, Any]:
    """
    Run a shell command and capture output.

    Args:
        command: Command to run
        cwd: Working directory (default: current)
        timeout: Max seconds to wait (default: 300 for complex operations)
        shell: Run via shell (default: True)

    Returns:
        Dict with 'stdout', 'stderr', 'returncode', 'success'
    """
    try:
        result = subprocess.run(
            command,
            shell=shell,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "command": command,
        }

    except subprocess.TimeoutExpired:
        logging.error(f"[ENGRAM] run_command timeout: {command}")
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Command timed out after {timeout}s",
            "returncode": -1,
            "command": command,
            "error": f"Timeout after {timeout}s",
        }

    except Exception as e:
        logging.error(f"[ENGRAM] run_command failed: {e}")
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "returncode": -1,
            "command": command,
            "error": str(e),
        }


def run_shell(
    script: str,
    interpreter: str = "bash",
    cwd: Optional[str] = None,
    timeout: int = 300,
) -> Dict[str, Any]:
    """
    Run a shell script.

    Args:
        script: Script content to run
        interpreter: Shell interpreter (default: bash)
        cwd: Working directory
        timeout: Max seconds to wait (default: 300 for complex operations)

    Returns:
        Dict with 'stdout', 'stderr', 'returncode', 'success'
    """
    try:
        result = subprocess.run(
            [interpreter, "-c", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "script": script[:100] + "..." if len(script) > 100 else script,
        }

    except subprocess.TimeoutExpired:
        logging.error(f"[ENGRAM] run_shell timeout")
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Script timed out after {timeout}s",
            "returncode": -1,
            "error": f"Timeout after {timeout}s",
        }

    except Exception as e:
        logging.error(f"[ENGRAM] run_shell failed: {e}")
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "returncode": -1,
            "error": str(e),
        }


def run_python(
    code: str,
    cwd: Optional[str] = None,
    timeout: int = 60,
) -> Dict[str, Any]:
    """
    Run Python code.

    Args:
        code: Python code to execute
        cwd: Working directory
        timeout: Max seconds to wait

    Returns:
        Dict with 'stdout', 'stderr', 'returncode', 'success'
    """
    return run_command(
        command=f'python -c "{code}"',
        cwd=cwd,
        timeout=timeout,
        shell=True,
    )
