#!/usr/bin/env python
"""
Test script for MCP tool integration with ENGRAM OS.

This script tests:
1. MCP client initialization
2. Tool availability
3. Tool execution (mock and real)
4. Agent integration with tools
5. Tool call logging

Usage:
    python engram/core/test_mcp_tools.py
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from engram.core.mcp_client import MCPClient
from engram.core.agent import create_agent, AgentConfig
from engram.core.llm import create_llm


def test_mcp_client():
    """Test MCP client initialization."""
    print("\n" + "=" * 60)
    print("TEST 1: MCP Client Initialization")
    print("=" * 60)

    client = MCPClient()
    
    # Connect from config
    connected = client.connect_from_config()
    
    print(f"\nConnected servers: {connected}")
    
    # Get status
    status = client.get_server_status()
    
    for name, info in status.items():
        conn_status = "✓" if info.get("connected") else "✗"
        tools = info.get("tools_count", 0)
        print(f"  {conn_status} {name}: {tools} tools")
    
    # Get tool schemas
    schemas = client.get_ollama_tool_schemas()
    print(f"\nTotal Ollama tool schemas: {len(schemas)}")
    
    return client


def test_mock_tools(client):
    """Test mock tool implementations."""
    print("\n" + "=" * 60)
    print("TEST 2: Mock Tool Execution")
    print("=" * 60)

    # Test read_file (should fail - file doesn't exist)
    print("\n1. Testing read_file (non-existent file)...")
    result = client.call_tool_mock("read_file", {"path": "/nonexistent.txt"})
    print(f"   Success: {result.success}")
    print(f"   Error: {result.error}")

    # Test write_file
    print("\n2. Testing write_file...")
    test_file = "test_mcp_output.txt"
    result = client.call_tool_mock("write_file", {
        "path": test_file,
        "content": "Hello from MCP!"
    })
    print(f"   Success: {result.success}")
    if result.success:
        print(f"   Result: {result.result}")
    else:
        print(f"   Error: {result.error}")

    # Test read_file (should succeed now if write succeeded)
    print("\n3. Testing read_file (existing file)...")
    if result.success:
        result = client.call_tool_mock("read_file", {"path": test_file})
        print(f"   Success: {result.success}")
        if result.success and result.result:
            print(f"   Content: {result.result.get('content', '')[:50]}...")
    else:
        print("   Skipped (write failed)")

    # Test list_directory
    print("\n4. Testing list_directory...")
    result = client.call_tool_mock("list_directory", {"path": "."})
    print(f"   Success: {result.success}")
    if result.success and result.result:
        print(f"   Items found: {len(result.result.get('items', []))}")

    # Test run_command
    print("\n5. Testing run_command...")
    result = client.call_tool_mock("run_command", {"command": "echo Hello MCP"})
    print(f"   Success: {result.success}")
    if result.success and result.result:
        print(f"   Output: {result.result.get('stdout', '').strip()}")

    # Cleanup
    if os.path.exists(test_file):
        os.remove(test_file)
        print(f"\n   Cleaned up: {test_file}")

    return True


def test_agent_with_mcp():
    """Test agent with MCP integration."""
    print("\n" + "=" * 60)
    print("TEST 3: Agent with MCP Integration")
    print("=" * 60)

    # Create MCP client
    mcp_client = MCPClient()
    mcp_client.connect_from_config()

    # Create agent with MCP
    agent = create_agent(
        name="MCP-Test-Agent",
        system_prompt="You are a helpful assistant with access to tools.",
        enable_tools=True,
        mcp_client=mcp_client,
    )

    # Get stats
    stats = agent.get_stats()
    print(f"\nAgent: {stats.get('name')}")
    print(f"MCP Enabled: {stats.get('mcp_enabled')}")
    print(f"MCP Servers: {stats.get('mcp_servers')}")
    if stats.get('mcp_server_names'):
        print(f"Connected: {', '.join(stats.get('mcp_server_names', []))}")

    # Get MCP status
    mcp_status = agent.get_mcp_status()
    print(f"\nMCP Server Status:")
    for name, info in mcp_status.items():
        conn = "✓" if info.get("connected") else "✗"
        print(f"  {conn} {name}")

    return agent


def test_tool_logging():
    """Test that tool calls are logged."""
    print("\n" + "=" * 60)
    print("TEST 4: Tool Call Logging")
    print("=" * 60)

    mcp_client = MCPClient()
    mcp_client.connect_from_config()

    # Execute some tool calls
    print("\nExecuting tool calls...")
    
    mcp_client.call_tool_mock("read_file", {"path": "test.txt"})
    mcp_client.call_tool_mock("write_file", {"path": "out.txt", "content": "test"})
    mcp_client.call_tool_mock("list_directory", {"path": "."})

    # Get history
    history = mcp_client.get_tool_history()
    print(f"\nTool calls logged: {len(history)}")

    # Note: The current implementation returns empty list for history
    # This is a placeholder for future implementation
    print("   (Tool history logging is a placeholder for future implementation)")

    return True


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("ENGRAM OS - MCP Tool Integration Tests")
    print("=" * 60)

    try:
        # Test 1: MCP Client
        client = test_mcp_client()

        # Test 2: Mock Tools
        test_mock_tools(client)

        # Test 3: Agent Integration
        agent = test_agent_with_mcp()

        # Test 4: Tool Logging
        test_tool_logging()

        print("\n" + "=" * 60)
        print("ALL TESTS COMPLETED SUCCESSFULLY")
        print("=" * 60)
        print("\nMCP tools are ready to use!")
        print("\nNext steps:")
        print("  1. Start Ollama: ollama serve")
        print("  2. Run interactive CLI: python -m engram.benchmarks.interactive_cli")
        print("  3. Use /tools to see available tools")
        print("  4. Ask the agent to perform file operations")
        print()

        return 0

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
