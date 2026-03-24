"""
MCP Client - Model Context Protocol integration for ENGRAM OS

This module provides MCP server connections and tool dispatch,
allowing ENGRAM to use external tools (filesystem, shell, search, etc.)
without changing core code.

Architecture:
    user input → route_task() → assemble_context() → ollama_call()
                                                            ↓
                                                 model returns tool_call?
                                                 YES → MCP client → MCP server
                                                       ↓
                                                 tool result → back to ollama_call()
                                                 NO → writeback → done

Usage:
    mcp = MCPClient()
    mcp.connect("filesystem", "npx @modelcontextprotocol/server-filesystem /home/user")
    mcp.connect("shell", "npx @modelcontextprotocol/server-shell")
    
    tools = mcp.get_ollama_tool_schemas()
    result = mcp.call_tool("read_file", {"path": "/project/auth.py"})
"""

import json
import logging
import os
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)


@dataclass
class MCPServer:
    """Represents a connected MCP server."""
    name: str
    command: str
    args: List[str]
    enabled: bool = True
    env: Dict[str, str] = field(default_factory=dict)
    process: Optional[subprocess.Popen] = None
    connected: bool = False
    tools: List[Dict[str, Any]] = field(default_factory=list)
    last_error: Optional[str] = None


@dataclass
class ToolCall:
    """Represents a tool call request."""
    id: str
    name: str
    arguments: Dict[str, Any]
    server: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ToolResult:
    """Represents a tool execution result."""
    tool_call_id: str
    success: bool
    result: Any
    error: Optional[str] = None
    duration_ms: float = 0.0


class MCPClient:
    """
    MCP client for ENGRAM OS.
    
    Manages connections to MCP servers and dispatches tool calls.
    
    Example:
        mcp = MCPClient()
        mcp.connect_from_config()  # Load from mcp_servers.yaml
        
        # Get tool schemas for Ollama
        tools = mcp.get_ollama_tool_schemas()
        
        # Call a tool
        result = mcp.call_tool("read_file", {"path": "README.md"})
    """
    
    def __init__(self, config_path: Optional[str] = None,
                 tool_timeout: int = 60):
        self.config_path = config_path or "engram/config/mcp_servers.yaml"
        self._servers: Dict[str, MCPServer] = {}
        self._tool_map: Dict[str, str] = {}  # tool_name -> server_name
        self._running = False
        self._lock = threading.RLock()
        self.tool_timeout = tool_timeout
        
    def connect(self, name: str, command: str, args: List[str],
                enabled: bool = True, env: Optional[Dict[str, str]] = None) -> bool:
        """
        Connect to an MCP server.
        
        Args:
            name: Server name (e.g., "filesystem", "shell")
            command: Command to run (e.g., "npx")
            args: Command arguments
            enabled: Whether server is enabled
            env: Environment variables
            
        Returns:
            True if connection successful
        """
        with self._lock:
            server = MCPServer(
                name=name,
                command=command,
                args=args,
                enabled=enabled,
                env=env or {},
            )
            
            if not enabled:
                logger.info(f"Server '{name}' is disabled")
                self._servers[name] = server
                return True
            
            try:
                # Start the MCP server process
                full_env = {**os.environ, **server.env}
                server.process = subprocess.Popen(
                    [command] + args,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=full_env,
                    cwd=str(Path.home()),
                )
                
                # Wait for server to initialize
                import time
                time.sleep(1.0)
                
                # Check if process is still running (good sign)
                if server.process.poll() is None:
                    server.connected = True
                    self._servers[name] = server

                    # Fetch tool schemas from server
                    self._fetch_tool_schemas(name)

                    logger.info(f"Connected to MCP server: {name}")
                    return True
                else:
                    # Process exited - get error with proper timeout handling
                    try:
                        server.process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        server.process.kill()
                        server.last_error = f"MCP server '{name}' did not respond within 5 seconds"
                        logger.error(f"Failed to connect to '{name}': {server.last_error}")
                        return False
                    
                    _, stderr = server.process.communicate()
                    server.last_error = stderr.decode() if stderr else "Process exited immediately"
                    logger.error(f"Failed to connect to '{name}': {server.last_error}")
                    return False
                    
            except Exception as e:
                server.last_error = str(e)
                logger.error(f"Error connecting to MCP server '{name}': {e}")
                return False
    
    def connect_from_config(self, config_path: Optional[str] = None) -> List[str]:
        """
        Connect to all servers defined in config.
        
        Args:
            config_path: Path to YAML config file
            
        Returns:
            List of successfully connected server names
        """
        path = config_path or self.config_path
        
        if not os.path.exists(path):
            logger.warning(f"MCP config not found: {path}")
            return []
        
        try:
            with open(path) as f:
                config = yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load MCP config: {e}")
            return []
        
        servers_config = config.get("servers", {})
        connected = []
        
        for name, server_cfg in servers_config.items():
            if not server_cfg.get("enabled", True):
                continue
            
            command = server_cfg.get("command", "npx")
            args = server_cfg.get("args", [])
            env = server_cfg.get("env", {})
            
            if self.connect(name, command, args, True, env):
                connected.append(name)
        
        return connected
    
    def disconnect(self, name: Optional[str] = None) -> None:
        """
        Disconnect from MCP server(s).
        
        Args:
            name: Server name to disconnect (None for all)
        """
        with self._lock:
            names = [name] if name else list(self._servers.keys())
            
            for server_name in names:
                server = self._servers.get(server_name)
                if server and server.process:
                    try:
                        server.process.terminate()
                        server.process.wait(timeout=5)
                        server.connected = False
                        logger.info(f"Disconnected from MCP server: {server_name}")
                    except Exception as e:
                        logger.error(f"Error disconnecting '{server_name}': {e}")
                    finally:
                        if server_name in self._servers:
                            del self._servers[server_name]
    
    def disconnect_all(self) -> None:
        """Disconnect from all servers."""
        self.disconnect(None)
    
    def _fetch_tool_schemas(self, server_name: str) -> None:
        """Fetch available tools from an MCP server."""
        server = self._servers.get(server_name)
        if not server or not server.connected:
            return
        
        # Send JSON-RPC request for tools/list
        try:
            request = {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "tools/list",
                "params": {},
            }
            
            server.process.stdin.write(
                (json.dumps(request) + "\n").encode()
            )
            server.process.stdin.flush()
            
            # Read response
            response_line = server.process.stdout.readline()
            if response_line:
                response = json.loads(response_line.decode())
                tools = response.get("result", {}).get("tools", [])
                
                server.tools = tools
                for tool in tools:
                    tool_name = tool.get("name", "")
                    self._tool_map[tool_name] = server_name
                    
                logger.info(f"Fetched {len(tools)} tools from '{server_name}'")
                
        except Exception as e:
            logger.error(f"Failed to fetch tools from '{server_name}': {e}")
            # Use mock tools for common servers
            self._use_mock_tools(server_name)
    
    def _use_mock_tools(self, server_name: str) -> None:
        """Use mock tool schemas for known servers."""
        server = self._servers.get(server_name)
        if not server:
            return
        
        mock_tools = {
            "filesystem": [
                {
                    "name": "read_file",
                    "description": "Read contents of a file",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "File path"}
                        },
                        "required": ["path"],
                    },
                },
                {
                    "name": "write_file",
                    "description": "Write content to a file",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["path", "content"],
                    },
                },
                {
                    "name": "list_directory",
                    "description": "List directory contents",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                        },
                        "required": ["path"],
                    },
                },
                {
                    "name": "create_directory",
                    "description": "Create a directory",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                        },
                        "required": ["path"],
                    },
                },
            ],
            "shell": [
                {
                    "name": "run_command",
                    "description": "Execute a shell command",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string"},
                            "cwd": {"type": "string"},
                        },
                        "required": ["command"],
                    },
                },
            ],
            "brave_search": [
                {
                    "name": "search",
                    "description": "Search the web using Brave Search",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "count": {"type": "integer"},
                        },
                        "required": ["query"],
                    },
                },
            ],
            "git": [
                {
                    "name": "git_commit",
                    "description": "Create a git commit",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "message": {"type": "string"},
                            "files": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["message"],
                    },
                },
                {
                    "name": "git_status",
                    "description": "Get git status",
                    "inputSchema": {
                        "type": "object",
                        "properties": {},
                    },
                },
                {
                    "name": "git_diff",
                    "description": "Get git diff",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                        },
                    },
                },
            ],
        }
        
        tools = mock_tools.get(server_name, [])
        server.tools = tools
        
        for tool in tools:
            tool_name = tool.get("name", "")
            self._tool_map[tool_name] = server_name
        
        logger.info(f"Using mock tools for '{server_name}': {[t['name'] for t in tools]}")
    
    def get_ollama_tool_schemas(self) -> List[Dict[str, Any]]:
        """
        Get all available tools in Ollama format.
        
        Returns:
            List of tool schemas for Ollama API
        """
        ollama_tools = []
        
        for server_name, server in self._servers.items():
            if not server.enabled or not server.tools:
                continue
            
            for tool in server.tools:
                ollama_tool = {
                    "type": "function",
                    "function": {
                        "name": tool.get("name", ""),
                        "description": tool.get("description", ""),
                        "parameters": tool.get("inputSchema", {}),
                    },
                }
                ollama_tools.append(ollama_tool)
        
        return ollama_tools
    
    def call_tool(self, name: str, arguments: Dict[str, Any]) -> ToolResult:
        """
        Call a tool by name.
        
        Args:
            name: Tool name
            arguments: Tool arguments
            
        Returns:
            ToolResult with success status and result/error
        """
        import time
        start_time = time.time()
        
        with self._lock:
            server_name = self._tool_map.get(name)
            
            if not server_name:
                return ToolResult(
                    tool_call_id=str(uuid.uuid4()),
                    success=False,
                    result=None,
                    error=f"Unknown tool: {name}",
                )
            
            server = self._servers.get(server_name)
            if not server or not server.connected:
                return ToolResult(
                    tool_call_id=str(uuid.uuid4()),
                    success=False,
                    result=None,
                    error=f"Server not connected: {server_name}",
                )
        
        # Send tool call to server
        tool_call_id = str(uuid.uuid4())
        
        try:
            request = {
                "jsonrpc": "2.0",
                "id": tool_call_id,
                "method": "tools/call",
                "params": {
                    "name": name,
                    "arguments": arguments,
                },
            }
            
            server.process.stdin.write(
                (json.dumps(request) + "\n").encode()
            )
            server.process.stdin.flush()
            
            # Read response
            response_line = server.process.stdout.readline()
            if response_line:
                response = json.loads(response_line.decode())
                
                if "error" in response:
                    return ToolResult(
                        tool_call_id=tool_call_id,
                        success=False,
                        result=None,
                        error=response["error"].get("message", "Unknown error"),
                        duration_ms=(time.time() - start_time) * 1000,
                    )
                
                result = response.get("result", {})
                return ToolResult(
                    tool_call_id=tool_call_id,
                    success=True,
                    result=result,
                    duration_ms=(time.time() - start_time) * 1000,
                )
            else:
                return ToolResult(
                    tool_call_id=tool_call_id,
                    success=False,
                    result=None,
                    error="No response from server",
                    duration_ms=(time.time() - start_time) * 1000,
                )
                
        except Exception as e:
            return ToolResult(
                tool_call_id=tool_call_id,
                success=False,
                result=None,
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000,
            )
    
    def call_tool_mock(self, name: str, arguments: Dict[str, Any]) -> ToolResult:
        """
        Call a tool using mock implementation (fallback).
        
        Args:
            name: Tool name
            arguments: Tool arguments
            
        Returns:
            ToolResult with success status and result/error
        """
        import time
        start_time = time.time()
        tool_call_id = str(uuid.uuid4())
        
        try:
            # Filesystem tools
            if name == "read_file":
                path = arguments.get("path", "")
                if os.path.exists(path):
                    with open(path) as f:
                        content = f.read()
                    return ToolResult(
                        tool_call_id=tool_call_id,
                        success=True,
                        result={"content": content},
                        duration_ms=(time.time() - start_time) * 1000,
                    )
                else:
                    return ToolResult(
                        tool_call_id=tool_call_id,
                        success=False,
                        result=None,
                        error=f"File not found: {path}",
                        duration_ms=(time.time() - start_time) * 1000,
                    )
            
            elif name == "write_file":
                path = arguments.get("path", "")
                content = arguments.get("content", "")
                dir_name = os.path.dirname(path)
                if dir_name:
                    os.makedirs(dir_name, exist_ok=True)
                with open(path, "w") as f:
                    f.write(content)
                return ToolResult(
                    tool_call_id=tool_call_id,
                    success=True,
                    result={"success": True, "path": path},
                    duration_ms=(time.time() - start_time) * 1000,
                )
            
            elif name == "list_directory":
                path = arguments.get("path", ".")
                if os.path.exists(path):
                    items = os.listdir(path)
                    return ToolResult(
                        tool_call_id=tool_call_id,
                        success=True,
                        result={"items": items},
                        duration_ms=(time.time() - start_time) * 1000,
                    )
            
            elif name == "create_directory":
                path = arguments.get("path", "")
                os.makedirs(path, exist_ok=True)
                return ToolResult(
                    tool_call_id=tool_call_id,
                    success=True,
                    result={"success": True, "path": path},
                    duration_ms=(time.time() - start_time) * 1000,
                )
            
            # Shell tool
            elif name == "run_command":
                command = arguments.get("command", "")
                cwd = arguments.get("cwd", None)

                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    cwd=cwd,
                    timeout=self.tool_timeout,
                )
                
                return ToolResult(
                    tool_call_id=tool_call_id,
                    success=result.returncode == 0,
                    result={
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "returncode": result.returncode,
                    },
                    duration_ms=(time.time() - start_time) * 1000,
                )
            
            else:
                return ToolResult(
                    tool_call_id=tool_call_id,
                    success=False,
                    result=None,
                    error=f"Unknown tool: {name}",
                    duration_ms=(time.time() - start_time) * 1000,
                )
                
        except subprocess.TimeoutExpired:
            return ToolResult(
                tool_call_id=tool_call_id,
                success=False,
                result=None,
                error="Command timed out",
                duration_ms=(time.time() - start_time) * 1000,
            )
        except Exception as e:
            return ToolResult(
                tool_call_id=tool_call_id,
                success=False,
                result=None,
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000,
            )
    
    def get_server_status(self) -> Dict[str, Any]:
        """Get status of all MCP servers."""
        status = {}
        
        for name, server in self._servers.items():
            status[name] = {
                "connected": server.connected,
                "enabled": server.enabled,
                "tools_count": len(server.tools),
                "last_error": server.last_error,
            }
        
        return status
    
    def get_tool_history(self) -> List[Dict[str, Any]]:
        """Get history of tool calls (for logging)."""
        # This would be populated from actual tool call logs
        return []


def create_mcp_client(config_path: Optional[str] = None) -> MCPClient:
    """
    Factory function to create and initialize MCP client.
    
    Args:
        config_path: Path to MCP servers config
        
    Returns:
        Initialized MCPClient
    """
    client = MCPClient(config_path)
    client.connect_from_config()
    return client
