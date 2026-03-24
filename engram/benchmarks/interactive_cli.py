#!/usr/bin/env python
"""
ENGRAM OS - Interactive CLI with Ollama

An interactive command-line interface for chatting with ENGRAM agents
powered by local Ollama models.

Usage:
    python -m engram.benchmarks.interactive_cli
    python -m engram.benchmarks.interactive_cli --model qwen3:30b-a3b-q4_K_M
    python -m engram.benchmarks.interactive_cli --session my_session
"""

import argparse
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional

from engram.core.agent import create_agent
from engram.core.llm import create_llm, Message, MessageRole
from engram.core.session import SessionManager


def check_ollama(base_url: str = "http://127.0.0.1:11434") -> tuple[bool, str]:
    """Check if Ollama is running and get available models."""
    try:
        response = urllib.request.urlopen(f"{base_url}/api/tags", timeout=5)
        data = json.loads(response.read().decode("utf-8"))
        models = [m.get("name", "") for m in data.get("models", [])]
        return True, f"Found {len(models)} model(s): {', '.join(models[:5])}"
    except urllib.error.URLError as e:
        return False, f"Cannot connect to Ollama at {base_url}: {e}"
    except Exception as e:
        return False, f"Error: {e}"


def check_model_exists(base_url: str, model_name: str) -> bool:
    """Check if a specific model is available."""
    try:
        response = urllib.request.urlopen(f"{base_url}/api/tags", timeout=5)
        data = json.loads(response.read().decode("utf-8"))
        models = [m.get("name", "") for m in data.get("models", [])]
        return any(model_name in m for m in models)
    except Exception as e:
        logging.debug(f"[ENGRAM] interactive_cli: model check failed: {e}")
        return False


class InteractiveCLI:
    """Interactive command-line interface for ENGRAM OS."""

    COMMANDS = {
        "/help": "Show this help message",
        "/exit": "Exit the application",
        "/quit": "Exit the application",
        "/save": "Save current session to file",
        "/load <name>": "Load a session from file",
        "/list": "List saved sessions",
        "/clear": "Clear current conversation context",
        "/stats": "Show session statistics",
        "/model": "Show current model",
        "/info": "Show system information",
        "/tools": "Show available MCP tools",
        "/mcp": "Show MCP server status",
    }

    def __init__(
        self,
        model: str = "bazobehram/qwen3-14b-claude-4.5-opus-high-reasoning:latest",
        base_url: str = "http://127.0.0.1:11434",
        session_name: Optional[str] = None,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
        enable_tools: bool = False,  # Disabled by default for compatibility
    ):
        self.model = model
        self.base_url = base_url
        self.temperature = temperature
        self.session_name = session_name
        self.system_prompt = system_prompt or (
            "You are ENGRAM OS, an intelligent AI assistant with persistent memory "
            "and advanced reasoning capabilities. You help users with complex tasks, "
            "maintain conversation context, and provide thoughtful, accurate responses."
        )
        self.enable_tools = enable_tools

        self.agent = None
        self.session_manager = None
        self.running = True

        # Sessions directory
        self.sessions_dir = Path("engram/sessions")
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def initialize(self) -> bool:
        """Initialize the agent and session."""
        print("\n" + "=" * 60)
        print("ENGRAM OS - Interactive CLI")
        print("=" * 60)

        # Check Ollama connection
        print(f"\nConnecting to Ollama at {self.base_url}...")
        connected, message = check_ollama(self.base_url)

        if not connected:
            print(f"✗ {message}")
            print("\nPlease ensure Ollama is running:")
            print("  1. Install from: https://ollama.ai")
            print("  2. Start Ollama service")
            print(f"  3. Pull model: ollama pull {self.model}")
            return False

        print(f"✓ {message}")

        # Check if model exists
        if not check_model_exists(self.base_url, self.model):
            print(f"\n⚠ Model '{self.model}' not found locally.")
            print(f"  Pull it with: ollama pull {self.model}")
            response = input("\nContinue anyway? (y/n): ").strip().lower()
            if response != 'y':
                return False

        # Create agent
        print(f"\nLoading model: {self.model}")
        print("Initializing agent...")

        try:
            llm = create_llm(
                provider_name="ollama",
                model=self.model,
                base_url=self.base_url,
                options={"temperature": self.temperature},
            )

            self.agent = create_agent(
                name="ENGRAM-Assistant",
                system_prompt=self.system_prompt,
                llm=llm,
                temperature=self.temperature,
                enable_tools=self.enable_tools,  # Tools disabled by default
            )

            self.session_manager = SessionManager(str(self.sessions_dir))

            # Load or create session
            if self.session_name:
                session = self.session_manager.get_session(self.session_name)
                if session:
                    self.agent._current_session = session
                    print(f"✓ Loaded session: {self.session_name}")
                else:
                    self.agent.start_session(metadata={"name": self.session_name})
                    print(f"✓ Created new session: {self.session_name}")
            else:
                self.agent.start_session()
                print("✓ Created new session")

            print("\n" + "=" * 60)
            print("Type /help for commands, /exit to quit")
            print("=" * 60 + "\n")

            return True

        except Exception as e:
            logging.error(f"[ENGRAM] interactive_cli: Error initializing agent: {e}")
            print(f"✗ Error initializing agent: {e}")
            return False

    def show_help(self) -> None:
        """Display help message."""
        print("\nAvailable Commands:")
        for cmd, desc in self.COMMANDS.items():
            print(f"  {cmd:15} - {desc}")
        print()

    def show_stats(self) -> None:
        """Show session statistics."""
        if self.agent:
            stats = self.agent.get_stats()
            print("\n--- Session Statistics ---")
            print(f"  Agent: {stats.get('name', 'N/A')}")
            print(f"  Active: {stats.get('active', False)}")
            print(f"  Turn Count: {stats.get('turn_count', 0)}")
            print(f"  MCP Enabled: {stats.get('mcp_enabled', False)}")
            print(f"  MCP Servers: {stats.get('mcp_servers', 0)}")
            if stats.get('mcp_server_names'):
                print(f"  Connected: {', '.join(stats.get('mcp_server_names', []))}")
            if stats.get('session_id'):
                print(f"  Session ID: {stats.get('session_id')}")
            print()

    def show_info(self) -> None:
        """Show system information."""
        print("\n--- System Information ---")
        print(f"  Model: {self.model}")
        print(f"  Base URL: {self.base_url}")
        print(f"  Temperature: {self.temperature}")
        print(f"  Sessions Directory: {self.sessions_dir.absolute()}")
        print(f"  MCP Config: engram/config/mcp_servers.yaml")
        print()

    def show_tools(self) -> None:
        """Show available MCP tools."""
        if not self.agent or not self.agent._mcp_client:
            print("✗ MCP not enabled\n")
            return

        mcp = self.agent._mcp_client
        status = mcp.get_server_status()

        print("\n--- Available MCP Tools ---")

        for server_name, server_status in status.items():
            connected = "✓" if server_status.get("connected") else "✗"
            tools_count = server_status.get("tools_count", 0)
            print(f"\n  {connected} {server_name} ({tools_count} tools)")

            server = mcp._servers.get(server_name)
            if server and server.tools:
                for tool in server.tools[:5]:  # Show first 5 tools
                    print(f"      - {tool.get('name', 'unknown')}: {tool.get('description', '')[:50]}")
                if len(server.tools) > 5:
                    print(f"      ... and {len(server.tools) - 5} more")

        print()

    def show_mcp_status(self) -> None:
        """Show MCP server status."""
        if not self.agent or not self.agent._mcp_client:
            print("✗ MCP not enabled\n")
            return

        mcp = self.agent._mcp_client
        status = mcp.get_server_status()

        print("\n--- MCP Server Status ---")

        for server_name, server_status in status.items():
            connected = "✓ Connected" if server_status.get("connected") else "✗ Disconnected"
            enabled = "enabled" if server_status.get("enabled") else "disabled"
            tools = server_status.get("tools_count", 0)
            error = server_status.get("last_error", "")

            print(f"\n  {server_name}:")
            print(f"    Status: {connected} ({enabled})")
            print(f"    Tools: {tools}")
            if error:
                print(f"    Error: {error[:60]}")

        print()

    def save_session(self) -> None:
        """Save current session."""
        if not self.agent or not self.agent.get_session():
            print("✗ No active session to save\n")
            return

        name = input("Enter session name: ").strip()
        if not name:
            print("✗ Invalid name\n")
            return

        session = self.agent.get_session()
        session_id = session.session_id

        # Save with custom name
        self.session_manager.save_session(session_id)

        # Copy to named file
        named_path = self.sessions_dir / f"{name}.yaml"
        current_path = self.sessions_dir / f"{session_id}.yaml"

        if current_path.exists():
            import shutil
            shutil.copy(current_path, named_path)
            print(f"✓ Session saved as: {name}\n")

    def load_session(self, name: str) -> None:
        """Load a session by name."""
        if not self.agent:
            print("✗ Agent not initialized\n")
            return

        # Try to load by name
        session_path = self.sessions_dir / f"{name}.yaml"
        if not session_path.exists():
            print(f"✗ Session '{name}' not found\n")
            return

        # Load session
        session = self.session_manager.get_session(name.replace(".yaml", ""))
        if session:
            self.agent._current_session = session
            print(f"✓ Loaded session: {name}\n")
        else:
            print(f"✗ Could not load session: {name}\n")

    def list_sessions(self) -> None:
        """List all saved sessions."""
        sessions = list(self.sessions_dir.glob("*.yaml"))

        if not sessions:
            print("No saved sessions\n")
            return

        print("\n--- Saved Sessions ---")
        for session_file in sessions:
            name = session_file.stem
            size = session_file.stat().st_size
            modified = datetime.fromtimestamp(session_file.stat().st_mtime)
            print(f"  {name:20} ({size} bytes, modified {modified.strftime('%Y-%m-%d %H:%M')})")
        print()

    def clear_context(self) -> None:
        """Clear conversation context."""
        if self.agent and self.agent.get_session():
            session = self.agent.get_session()
            session.clear_context()
            print("✓ Conversation context cleared\n")
        else:
            print("✗ No active session\n")

    def process_command(self, user_input: str) -> bool:
        """Process a command. Returns False if should exit."""
        parts = user_input.strip().split()
        cmd = parts[0].lower()

        if cmd in ("/exit", "/quit"):
            self.running = False
            return False

        elif cmd == "/help":
            self.show_help()

        elif cmd == "/stats":
            self.show_stats()

        elif cmd == "/info":
            self.show_info()

        elif cmd == "/tools":
            self.show_tools()

        elif cmd == "/mcp":
            self.show_mcp_status()

        elif cmd == "/save":
            self.save_session()

        elif cmd == "/load":
            if len(parts) > 1:
                self.load_session(parts[1])
            else:
                print("Usage: /load <session_name>\n")

        elif cmd == "/list":
            self.list_sessions()

        elif cmd == "/clear":
            self.clear_context()

        elif cmd == "/model":
            print(f"Current model: {self.model}\n")

        else:
            print(f"Unknown command: {cmd}")
            print("Type /help for available commands\n")

        return True

    def chat(self, user_input: str) -> None:
        """Send a message and display response."""
        if not self.agent:
            print("✗ Agent not initialized\n")
            return

        try:
            print("Assistant: ", end="", flush=True)
            response = self.agent.chat(user_input)
            print(response.content)
            print()
        except Exception as e:
            logging.error(f"[ENGRAM] interactive_cli: chat error: {e}")
            print(f"\n✗ Error: {e}\n")

    def run(self) -> None:
        """Main interaction loop."""
        if not self.initialize():
            sys.exit(1)

        while self.running:
            try:
                user_input = input("You: ").strip()

                if not user_input:
                    continue

                # Check for commands
                if user_input.startswith("/"):
                    if not self.process_command(user_input):
                        break
                else:
                    self.chat(user_input)

            except KeyboardInterrupt:
                print("\n\nInterrupted. Type /exit to quit.\n")
            except EOFError:
                break

        # Cleanup
        self.cleanup()

    def cleanup(self) -> None:
        """Clean up before exit."""
        print("\nSaving session...")

        if self.agent and self.agent.get_session():
            session = self.agent.get_session()
            self.session_manager.save_session(session.session_id)
            print(f"✓ Session saved: {session.session_id}")

        print("\nGoodbye!\n")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="ENGRAM OS Interactive CLI with Ollama",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m engram.benchmarks.interactive_cli
  python -m engram.benchmarks.interactive_cli --model qwen3:30b-a3b-q4_K_M
  python -m engram.benchmarks.interactive_cli --session my_project
  python -m engram.benchmarks.interactive_cli --temperature 0.5
        """,
    )

    parser.add_argument(
        "--model", "-m",
        default="bazobehram/qwen3-14b-claude-4.5-opus-high-reasoning:latest",
        help="Ollama model to use (default: bazobehram/qwen3-14b-claude-4.5-opus-high-reasoning:latest)",
    )

    parser.add_argument(
        "--base-url", "-b",
        default="http://127.0.0.1:11434",
        help="Ollama base URL (default: http://127.0.0.1:11434)",
    )

    parser.add_argument(
        "--session", "-s",
        default=None,
        help="Session name to load/create",
    )

    parser.add_argument(
        "--temperature", "-t",
        type=float,
        default=0.7,
        help="Model temperature (default: 0.7)",
    )

    parser.add_argument(
        "--enable-tools",
        action="store_true",
        default=False,
        help="Enable MCP tool calling (default: disabled for compatibility)",
    )

    parser.add_argument(
        "--system-prompt",
        default=None,
        help="Custom system prompt",
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    cli = InteractiveCLI(
        model=args.model,
        base_url=args.base_url,
        session_name=args.session,
        temperature=args.temperature,
        system_prompt=args.system_prompt,
        enable_tools=args.enable_tools,
    )

    cli.run()


if __name__ == "__main__":
    main()
