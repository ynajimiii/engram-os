"""
Tests for MCP (Model Context Protocol) integration.

Tests for mcp_client.py and tool calling functionality.
"""

import os
import tempfile
import pytest
import yaml
from pathlib import Path

from engram.core.mcp_client import MCPClient, MCPServer, ToolResult, create_mcp_client
from engram.core.llm import create_llm, ToolCall as LLMToolCall
from engram.core.agent import create_agent, AgentConfig


class TestMCPClient:
    """Tests for MCPClient class."""

    def test_mcp_client_creation(self):
        """Test creating MCP client."""
        client = MCPClient()
        
        assert client.config_path == "engram/config/mcp_servers.yaml"
        assert len(client._servers) == 0

    def test_mcp_client_manual_server_add(self):
        """Test manually adding MCP server."""
        client = MCPClient()
        
        # Manually add server (since real connection may fail)
        server = MCPServer(
            name="test_server",
            command="echo",
            args=["test"],
            enabled=True,
        )
        client._servers["test_server"] = server
        
        # Server should be registered
        assert "test_server" in client._servers

    def test_mcp_client_get_ollama_schemas(self):
        """Test getting Ollama tool schemas."""
        client = MCPClient()
        
        # Add mock server with tools
        server = MCPServer(
            name="filesystem",
            command="echo",
            args=["test"],
            enabled=True,
            connected=True,
        )
        server.tools = [
            {
                "name": "read_file",
                "description": "Read a file",
                "inputSchema": {"type": "object"},
            }
        ]
        client._servers["filesystem"] = server
        client._tool_map["read_file"] = "filesystem"
        
        schemas = client.get_ollama_tool_schemas()
        
        assert len(schemas) > 0
        assert schemas[0]["type"] == "function"
        assert schemas[0]["function"]["name"] == "read_file"

    def test_mcp_client_call_tool_mock(self):
        """Test calling tool via mock implementation."""
        client = MCPClient()
        
        # Test read_file with non-existent file
        result = client.call_tool_mock("read_file", {"path": "/nonexistent"})
        
        assert result.success is False
        assert "not found" in result.error.lower()

    def test_mcp_client_call_tool_mock_write_file(self):
        """Test write_file tool."""
        client = MCPClient()
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            temp_path = f.name
        
        try:
            result = client.call_tool_mock("write_file", {
                "path": temp_path,
                "content": "test content"
            })
            
            assert result.success is True
            
            # Verify content
            with open(temp_path) as f:
                assert f.read() == "test content"
        finally:
            os.unlink(temp_path)

    def test_mcp_client_call_tool_mock_run_command(self):
        """Test run_command tool."""
        client = MCPClient()
        
        result = client.call_tool_mock("run_command", {
            "command": "echo hello"
        })
        
        assert result.success is True
        assert "hello" in result.result.get("stdout", "")

    def test_mcp_client_get_server_status(self):
        """Test getting server status."""
        client = MCPClient()
        
        server = MCPServer(
            name="test",
            command="echo",
            args=[],
            enabled=True,
            connected=False,
        )
        client._servers["test"] = server
        
        status = client.get_server_status()
        
        assert "test" in status
        assert status["test"]["enabled"] is True
        assert status["test"]["connected"] is False

    def test_mcp_client_disconnect(self):
        """Test disconnecting from server."""
        client = MCPClient()
        
        server = MCPServer(
            name="test",
            command="echo",
            args=[],
            enabled=True,
        )
        # Simulate a connected server with process (use shell=True for Windows)
        import subprocess
        import sys
        try:
            if sys.platform == 'win32':
                server.process = subprocess.Popen(
                    "echo test",
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
            else:
                server.process = subprocess.Popen(
                    ["echo", "test"],
                    stdout=subprocess.PIPE
                )
        except Exception:
            # If we can't create process, just test that server gets added
            server.process = None
            server.connected = True
        
        client._servers["test"] = server
        client._tool_map["test_tool"] = "test"
        
        client.disconnect("test")
        
        # Server should be removed after disconnect (or at least marked disconnected)
        if server.process:
            assert "test" not in client._servers
        else:
            # Without process, server stays but should be disconnected
            assert client._servers["test"].connected is False
        
        assert "test" not in client._tool_map

    def test_create_mcp_client_factory(self):
        """Test factory function."""
        client = create_mcp_client(config_path="nonexistent.yaml")
        
        assert isinstance(client, MCPClient)


class TestMCPConfig:
    """Tests for MCP configuration."""

    def test_config_file_exists(self):
        """Test that default config file exists."""
        config_path = "engram/config/mcp_servers.yaml"
        
        # Config should exist
        assert os.path.exists(config_path)

    def test_config_load(self):
        """Test loading config file."""
        config_path = "engram/config/mcp_servers.yaml"
        
        with open(config_path) as f:
            config = yaml.safe_load(f)
        
        assert "servers" in config
        assert "filesystem" in config["servers"]
        assert "shell" in config["servers"]

    def test_config_server_structure(self):
        """Test config server structure."""
        config_path = "engram/config/mcp_servers.yaml"
        
        with open(config_path) as f:
            config = yaml.safe_load(f)
        
        fs_config = config["servers"]["filesystem"]
        
        assert "command" in fs_config
        assert "args" in fs_config
        assert "enabled" in fs_config


class TestLLMToolCalling:
    """Tests for LLM tool calling support."""

    def test_tool_call_from_dict(self):
        """Test creating ToolCall from dict."""
        data = {
            "id": "call_123",
            "function": {
                "name": "read_file",
                "arguments": {"path": "/test.txt"},
            }
        }
        
        tool_call = LLMToolCall.from_dict(data)
        
        assert tool_call.id == "call_123"
        assert tool_call.name == "read_file"
        assert tool_call.arguments == {"path": "/test.txt"}

    def test_llm_response_with_tool_calls(self):
        """Test LLMResponse with tool calls."""
        from engram.core.llm import LLMResponse, MessageRole
        
        response = LLMResponse(
            content="Let me check that file",
            tool_calls=[
                {
                    "id": "call_1",
                    "function": {
                        "name": "read_file",
                        "arguments": {"path": "test.txt"},
                    }
                }
            ]
        )
        
        assert response.tool_calls is not None
        assert len(response.tool_calls) == 1


class TestAgentWithMCP:
    """Tests for Agent with MCP integration."""

    def test_agent_config_has_enable_tools(self):
        """Test AgentConfig has enable_tools option."""
        config = AgentConfig()
        
        assert hasattr(config, 'enable_tools')
        assert config.enable_tools is True

    def test_agent_config_has_mcp_config_path(self):
        """Test AgentConfig has mcp_config_path."""
        config = AgentConfig()
        
        assert hasattr(config, 'mcp_config_path')
        assert config.mcp_config_path is None

    def test_agent_create_with_mcp_client(self):
        """Test creating agent with MCP client."""
        mcp_client = MCPClient()
        
        agent = create_agent(
            name="TestAgent",
            mcp_client=mcp_client,
            enable_tools=True,
        )
        
        assert agent._mcp_client is mcp_client
        assert agent.config.enable_tools is True

    def test_agent_get_stats_includes_mcp(self):
        """Test agent stats include MCP info."""
        agent = create_agent(name="TestAgent")
        
        stats = agent.get_stats()
        
        assert "mcp_enabled" in stats
        assert "mcp_servers" in stats

    def test_agent_get_mcp_status(self):
        """Test getting MCP status from agent."""
        agent = create_agent(name="TestAgent")
        
        status = agent.get_mcp_status()
        
        assert isinstance(status, dict)


class TestToolCallDataclass:
    """Tests for ToolCall dataclass (from llm module)."""

    def test_tool_call_creation(self):
        """Test creating ToolCall."""
        tool_call = LLMToolCall(
            id="test_123",
            name="read_file",
            arguments={"path": "/test.txt"}
        )
        
        assert tool_call.id == "test_123"
        assert tool_call.name == "read_file"
        assert tool_call.arguments == {"path": "/test.txt"}

    def test_tool_call_from_dict(self):
        """Test creating ToolCall from dict."""
        data = {
            "id": "test_456",
            "function": {
                "name": "write_file",
                "arguments": {"path": "/out.txt", "content": "hello"},
            }
        }
        
        tool_call = LLMToolCall.from_dict(data)
        
        assert tool_call.id == "test_456"
        assert tool_call.name == "write_file"


class TestToolResult:
    """Tests for ToolResult dataclass."""

    def test_tool_result_success(self):
        """Test successful tool result."""
        result = ToolResult(
            tool_call_id="call_1",
            success=True,
            result={"content": "file contents"},
        )
        
        assert result.success is True
        assert result.error is None

    def test_tool_result_error(self):
        """Test failed tool result."""
        result = ToolResult(
            tool_call_id="call_2",
            success=False,
            result=None,
            error="File not found",
        )
        
        assert result.success is False
        assert result.error == "File not found"


class TestMCPServer:
    """Tests for MCPServer dataclass."""

    def test_server_creation(self):
        """Test creating MCP server."""
        server = MCPServer(
            name="test",
            command="npx",
            args=["@modelcontextprotocol/server-filesystem"],
            enabled=True,
        )
        
        assert server.name == "test"
        assert server.enabled is True
        assert server.connected is False

    def test_server_with_env(self):
        """Test server with environment variables."""
        server = MCPServer(
            name="brave_search",
            command="npx",
            args=["@modelcontextprotocol/server-brave-search"],
            env={"BRAVE_API_KEY": "test_key"},
        )
        
        assert server.env == {"BRAVE_API_KEY": "test_key"}


class TestMockTools:
    """Tests for mock tool implementations."""

    def test_list_directory(self):
        """Test list_directory tool."""
        client = MCPClient()
        
        result = client.call_tool_mock("list_directory", {
            "path": str(Path(__file__).parent)
        })
        
        assert result.success is True
        assert "items" in result.result

    def test_create_directory(self):
        """Test create_directory tool."""
        client = MCPClient()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            new_dir = os.path.join(temp_dir, "test_subdir")
            
            result = client.call_tool_mock("create_directory", {
                "path": new_dir
            })
            
            assert result.success is True
            assert os.path.exists(new_dir)

    def test_unknown_tool(self):
        """Test unknown tool returns error."""
        client = MCPClient()
        
        result = client.call_tool_mock("unknown_tool", {})
        
        assert result.success is False
        assert "Unknown tool" in result.error
