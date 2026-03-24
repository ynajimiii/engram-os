# engram/tools/__init__.py
"""
ENGRAM OS — File and Shell Tools

Pure file/shell operations for coding agent.
No core dependencies — safe to import anywhere.
"""

from .file_ops import (
    read_text_file,
    write_file,
    create_directory,
    list_directory,
    list_allowed_directories,
)
from .shell_ops import (
    run_command,
    run_shell,
)


class LocalToolClient:
    """
    Adapter that wraps engram.tools functions as an
    MCP-compatible client for use with llm.complete().

    Implements the execute() method that mcp_client needs.
    """

    def __init__(
        self,
        sandbox_root: str,
        allowed_commands: list = None,
    ):
        self.sandbox_root = sandbox_root
        self.allowed_commands = allowed_commands or []
        self._dispatch = {
            "read_text_file": self._read_text_file,
            "read_file": self._read_text_file,
            "write_file": self._write_file,
            "create_directory": self._create_directory,
            "list_directory": self._list_directory,
            "list_dir": self._list_directory,
            "run_command": self._run_command,
            "shell_exec": self._run_command,
        }

    def execute(self, tool_name: str, arguments: dict) -> dict:
        """
        Execute a tool by name with given arguments.
        Returns a plain dict result.
        Never raises — returns {"error": ...} on failure.
        """
        handler = self._dispatch.get(tool_name)
        if handler is None:
            return {"error": f"Unknown tool: {tool_name}"}
        try:
            return handler(arguments)
        except Exception as e:
            return {"error": str(e)}

    def call_tool(self, tool_name: str, arguments: dict):
        """MCP-compatible wrapper for execute()."""
        result = self.execute(tool_name, arguments)
        # Return MCP-compatible result
        class ToolResult:
            def __init__(self, r):
                self.success = r.get("success", False)
                self.result = r.get("content", r.get("stdout", r))
                self.error = r.get("error")
        return ToolResult(result)

    # ── Internal handlers ────────────────────────────────────

    def _read_text_file(self, args: dict) -> dict:
        return read_text_file(
            path=args.get("path", ""),
            limit=args.get("limit", None),
        )

    def _write_file(self, args: dict) -> dict:
        return write_file(
            path=args.get("path", ""),
            content=args.get("content", ""),
            create_dirs=args.get("create_dirs", True),
        )

    def _create_directory(self, args: dict) -> dict:
        return create_directory(
            path=args.get("path", ""),
        )

    def _list_directory(self, args: dict) -> dict:
        return list_directory(
            path=args.get("path", "."),
            recursive=args.get("recursive", False),
        )

    def _run_command(self, args: dict) -> dict:
        return run_command(
            command=args.get("command", ""),
            cwd=args.get("cwd", self.sandbox_root),
            timeout=args.get("timeout", 120),
        )

    def get_ollama_tool_schemas(self) -> list:
        """
        Return Ollama-compatible tool schemas for all available tools.

        These schemas are passed to the LLM so it knows what tools
        are available and how to call them.

        Returns:
            List of tool schemas in Ollama format
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": "read_text_file",
                    "description": "Read the contents of a text file. Returns the file content and line count.",
                    "parameters": {
                        "type": "object",
                        "required": ["path"],
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Path to the file to read"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of lines to read (optional)"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Write content to a file. Creates the file if it doesn't exist, overwrites if it does.",
                    "parameters": {
                        "type": "object",
                        "required": ["path", "content"],
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Path to the file to write"
                            },
                            "content": {
                                "type": "string",
                                "description": "Content to write to the file"
                            },
                            "create_dirs": {
                                "type": "boolean",
                                "description": "Create parent directories if needed (default: true)"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "create_directory",
                    "description": "Create a directory. Creates parent directories if needed.",
                    "parameters": {
                        "type": "object",
                        "required": ["path"],
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Path to the directory to create"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_directory",
                    "description": "List contents of a directory. Returns files and subdirectories.",
                    "parameters": {
                        "type": "object",
                        "required": ["path"],
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Path to the directory to list"
                            },
                            "recursive": {
                                "type": "boolean",
                                "description": "List recursively (default: false)"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "run_command",
                    "description": "Execute a shell command and return stdout, stderr, and exit code.",
                    "parameters": {
                        "type": "object",
                        "required": ["command"],
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "The shell command to execute"
                            },
                            "cwd": {
                                "type": "string",
                                "description": "Working directory for the command (optional)"
                            },
                            "timeout": {
                                "type": "integer",
                                "description": "Timeout in seconds (default: 120)"
                            }
                        }
                    }
                }
            }
        ]


__all__ = [
    "read_text_file",
    "write_file",
    "create_directory",
    "list_directory",
    "list_allowed_directories",
    "run_command",
    "run_shell",
    "LocalToolClient",
]
