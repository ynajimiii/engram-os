# engram/tools/file_ops.py
"""
File operation tools for ENGRAM OS coding agent.

These tools are designed to be called via MCP or directly.
Each tool returns a structured result dict.
"""

import os
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional


# Base directories allowed for file operations
ALLOWED_BASE_DIRS = [
    Path.cwd(),  # Current working directory
    Path.home(),  # Home directory
]


def list_allowed_directories() -> Dict[str, Any]:
    """
    List directories that are allowed for file operations.

    Returns:
        Dict with 'allowed_dirs' list and 'success' flag
    """
    return {
        "success": True,
        "allowed_dirs": [str(d) for d in ALLOWED_BASE_DIRS],
        "current_dir": str(Path.cwd()),
    }


def _is_allowed_path(path: Path) -> bool:
    """Check if path is within allowed directories."""
    try:
        resolved = path.resolve()
        for base in ALLOWED_BASE_DIRS:
            try:
                resolved.relative_to(base.resolve())
                return True
            except ValueError:
                continue
        return False
    except Exception:
        return False


def read_text_file(path: str, limit: Optional[int] = None) -> Dict[str, Any]:
    """
    Read contents of a text file.

    Args:
        path: Path to file
        limit: Max lines to read (None = unlimited)

    Returns:
        Dict with 'content', 'lines', 'success', and optional 'error'
    """
    try:
        file_path = Path(path)

        if not file_path.exists():
            return {
                "success": False,
                "error": f"File not found: {path}",
            }

        if not file_path.is_file():
            return {
                "success": False,
                "error": f"Not a file: {path}",
            }

        # Security check
        if not _is_allowed_path(file_path):
            return {
                "success": False,
                "error": f"Access denied: {path} (outside allowed directories)",
            }

        with open(file_path, 'r', encoding='utf-8') as f:
            if limit:
                lines = []
                for i, line in enumerate(f):
                    if i >= limit:
                        break
                    lines.append(line)
                content = ''.join(lines)
            else:
                content = f.read()

        return {
            "success": True,
            "content": content,
            "lines": len(content.splitlines()),
            "path": str(file_path),
        }

    except Exception as e:
        logging.error(f"[ENGRAM] read_text_file failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


def write_file(path: str, content: str, create_dirs: bool = True) -> Dict[str, Any]:
    """
    Write content to a file (creates or overwrites).

    Args:
        path: Path to file
        content: Content to write
        create_dirs: Create parent directories if needed

    Returns:
        Dict with 'success' and optional 'error' or 'path'
    """
    try:
        file_path = Path(path)

        # Security check
        if not _is_allowed_path(file_path):
            return {
                "success": False,
                "error": f"Access denied: {path} (outside allowed directories)",
            }

        # Create parent directories if needed
        if create_dirs and file_path.parent != file_path:
            file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

        return {
            "success": True,
            "path": str(file_path),
            "bytes_written": len(content.encode('utf-8')),
        }

    except Exception as e:
        logging.error(f"[ENGRAM] write_file failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


def create_directory(path: str, parents: bool = True) -> Dict[str, Any]:
    """
    Create a directory.

    Args:
        path: Path to directory
        parents: Create parent directories if needed

    Returns:
        Dict with 'success' and optional 'error' or 'path'
    """
    try:
        dir_path = Path(path)

        # Security check
        if not _is_allowed_path(dir_path):
            return {
                "success": False,
                "error": f"Access denied: {path} (outside allowed directories)",
            }

        if parents:
            dir_path.mkdir(parents=True, exist_ok=True)
        else:
            dir_path.mkdir(exist_ok=True)

        return {
            "success": True,
            "path": str(dir_path),
        }

    except Exception as e:
        logging.error(f"[ENGRAM] create_directory failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


def list_directory(path: str = ".", recursive: bool = False) -> Dict[str, Any]:
    """
    List directory contents.

    Args:
        path: Path to directory (default: current)
        recursive: List recursively

    Returns:
        Dict with 'entries' list, 'success', and optional 'error'
    """
    try:
        dir_path = Path(path) if path != "." else Path.cwd()

        # Security check
        if not _is_allowed_path(dir_path):
            return {
                "success": False,
                "error": f"Access denied: {path} (outside allowed directories)",
            }

        if not dir_path.exists():
            return {
                "success": False,
                "error": f"Directory not found: {path}",
            }

        if not dir_path.is_dir():
            return {
                "success": False,
                "error": f"Not a directory: {path}",
            }

        entries = []

        if recursive:
            for item in dir_path.rglob("*"):
                rel_path = item.relative_to(dir_path)
                entries.append({
                    "name": str(rel_path),
                    "is_dir": item.is_dir(),
                    "is_file": item.is_file(),
                })
        else:
            for item in dir_path.iterdir():
                entries.append({
                    "name": item.name,
                    "is_dir": item.is_dir(),
                    "is_file": item.is_file(),
                })

        # Sort: directories first, then files
        entries.sort(key=lambda x: (not x["is_dir"], x["name"]))

        return {
            "success": True,
            "entries": entries,
            "count": len(entries),
            "path": str(dir_path),
        }

    except Exception as e:
        logging.error(f"[ENGRAM] list_directory failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }
