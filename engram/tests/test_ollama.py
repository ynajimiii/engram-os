"""
Tests for Ollama provider integration.

Note: These tests require a running Ollama instance at http://127.0.0.1:11434
Skip if Ollama is not available.
"""

import pytest
import urllib.request
import urllib.error
from engram.core.llm import (
    OllamaProvider, 
    BaseLLM, 
    Message, 
    MessageRole,
    create_llm,
)


def is_ollama_available() -> bool:
    """Check if Ollama is running."""
    try:
        urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=5)
        return True
    except urllib.error.URLError:
        return False


@pytest.fixture
def ollama_provider():
    """Create an Ollama provider instance."""
    return OllamaProvider(
        model="bazobehram/qwen3-14b-claude-4.5-opus-high-reasoning:latest",
        base_url="http://127.0.0.1:11434",
    )


@pytest.fixture
def ollama_llm():
    """Create a BaseLLM with Ollama provider."""
    llm = BaseLLM()
    llm.set_provider(OllamaProvider(
        model="bazobehram/qwen3-14b-claude-4.5-opus-high-reasoning:latest",
        base_url="http://127.0.0.1:11434",
    ))
    return llm


@pytest.mark.skipif(not is_ollama_available(), reason="Ollama not running")
class TestOllamaProvider:
    """Tests for OllamaProvider."""

    def test_ollama_provider_creation(self, ollama_provider):
        """Test creating Ollama provider."""
        assert ollama_provider.model == "bazobehram/qwen3-14b-claude-4.5-opus-high-reasoning:latest"
        assert ollama_provider.base_url == "http://127.0.0.1:11434"

    def test_ollama_complete(self, ollama_provider):
        """Test Ollama completion."""
        messages = [
            Message(role=MessageRole.USER, content="Say hello"),
        ]
        
        response = ollama_provider.complete(messages)
        
        assert response.content is not None
        assert len(response.content) > 0
        assert response.role == MessageRole.ASSISTANT

    def test_ollama_complete_with_system(self, ollama_provider):
        """Test Ollama completion with system message."""
        messages = [
            Message(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
            Message(role=MessageRole.USER, content="What is 2 + 2?"),
        ]
        
        response = ollama_provider.complete(messages)
        
        assert response.content is not None
        assert "4" in response.content or "four" in response.content.lower()

    def test_ollama_stream(self, ollama_provider):
        """Test Ollama streaming."""
        messages = [
            Message(role=MessageRole.USER, content="Count 1 to 3"),
        ]
        
        chunks = list(ollama_provider.stream_complete(messages))
        
        assert len(chunks) > 0
        full_response = "".join(chunks)
        assert len(full_response) > 0

    def test_ollama_with_custom_options(self):
        """Test Ollama with custom options."""
        provider = OllamaProvider(
            model="bazobehram/qwen3-14b-claude-4.5-opus-high-reasoning:latest",
            options={"temperature": 0.5, "num_predict": 100},
        )
        
        messages = [Message(role=MessageRole.USER, content="Hi")]
        response = provider.complete(messages)
        
        assert response.content is not None


@pytest.mark.skipif(not is_ollama_available(), reason="Ollama not running")
class TestCreateLlmWithOllama:
    """Tests for create_llm with Ollama."""

    def test_create_llm_ollama(self):
        """Test creating LLM with Ollama provider."""
        llm = create_llm(
            provider_name="ollama",
            model="bazobehram/qwen3-14b-claude-4.5-opus-high-reasoning:latest",
        )
        
        assert llm._provider is not None
        assert isinstance(llm._provider, OllamaProvider)

    def test_create_llm_ollama_with_options(self):
        """Test creating LLM with Ollama and options."""
        llm = create_llm(
            provider_name="ollama",
            model="bazobehram/qwen3-14b-claude-4.5-opus-high-reasoning:latest",
            options={"temperature": 0.3},
        )
        
        assert llm._provider.options == {"temperature": 0.3}
