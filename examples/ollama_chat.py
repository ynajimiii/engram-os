#!/usr/bin/env python
"""
Example: Using Engram OS with Ollama (local LLM)

This script demonstrates how to connect an Engram agent to a local
Ollama instance for inference.

Prerequisites:
1. Ollama installed and running at http://127.0.0.1:11434
2. Model pulled: ollama pull bazobehram/qwen3-14b-claude-4.5-opus-high-reasoning:latest

Usage:
    python examples/ollama_chat.py
"""

from engram.core.llm import BaseLLM, OllamaProvider, create_llm
from engram.core.agent import create_agent


def test_ollama_direct():
    """Test Ollama provider directly."""
    print("=" * 50)
    print("Testing Ollama Provider Directly")
    print("=" * 50)
    
    # Create LLM with Ollama provider
    llm = create_llm(
        provider_name="ollama",
        model="bazobehram/qwen3-14b-claude-4.5-opus-high-reasoning:latest",
        base_url="http://127.0.0.1:11434",
        options={"temperature": 0.7},
    )
    
    # Test completion
    from engram.core.llm import Message, MessageRole
    
    messages = [
        Message(role=MessageRole.USER, content="Hello! Who are you?"),
    ]
    
    print("\nSending request to Ollama...")
    response = llm.complete(messages=messages)
    
    print(f"\nResponse: {response.content}")
    print(f"Tokens used: {response.usage}")
    
    return llm


def test_agent_with_ollama():
    """Test agent with Ollama provider."""
    print("\n" + "=" * 50)
    print("Testing Agent with Ollama")
    print("=" * 50)
    
    # Create agent with Ollama
    agent = create_agent(
        name="OllamaAssistant",
        system_prompt="You are a helpful AI assistant powered by Qwen3-14B via Ollama.",
        llm=create_llm(
            provider_name="ollama",
            model="bazobehram/qwen3-14b-claude-4.5-opus-high-reasoning:latest",
        ),
        temperature=0.7,
    )
    
    # Start a session
    agent.start_session()
    
    # Chat
    print("\nUser: What is 2 + 2?")
    response = agent.chat("What is 2 + 2?")
    print(f"Assistant: {response.content}")
    
    print("\nUser: Explain quantum computing in one sentence.")
    response = agent.chat("Explain quantum computing in one sentence.")
    print(f"Assistant: {response.content}")
    
    # End session
    agent.end_session()
    
    print(f"\nSession stats: {agent.get_stats()}")


def test_streaming():
    """Test streaming with Ollama."""
    print("\n" + "=" * 50)
    print("Testing Streaming with Ollama")
    print("=" * 50)
    
    llm = create_llm(
        provider_name="ollama",
        model="bazobehram/qwen3-14b-claude-4.5-opus-high-reasoning:latest",
    )
    
    from engram.core.llm import Message, MessageRole
    
    messages = [
        Message(role=MessageRole.USER, content="Count from 1 to 5."),
    ]
    
    print("\nStreaming response: ", end="", flush=True)
    
    for chunk in llm.stream(messages=messages):
        print(chunk, end="", flush=True)
    
    print("\n\nStreaming complete!")


if __name__ == "__main__":
    import sys
    
    # Check if Ollama is running
    import urllib.request
    import urllib.error
    
    try:
        urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=5)
        print("✓ Ollama is running at http://127.0.0.1:11434\n")
    except urllib.error.URLError:
        print("✗ Ollama is not running at http://127.0.0.1:11434")
        print("  Please start Ollama and ensure the model is pulled:")
        print("  ollama pull bazobehram/qwen3-14b-claude-4.5-opus-high-reasoning:latest")
        sys.exit(1)
    
    # Run tests
    test_ollama_direct()
    test_agent_with_ollama()
    # test_streaming()  # Uncomment to test streaming
