"""
Tests for agent.py - Base agent implementation.

Phase 06: Agent Core
"""

import pytest
from engram.core.agent import Agent, AgentConfig, AgentState, create_agent
from engram.core.llm import BaseLLM, LLMResponse, Message, MessageRole, MockProvider


class TestAgentConfig:
    """Tests for AgentConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = AgentConfig()
        
        assert config.name == "Agent"
        assert config.temperature == 0.7
        assert config.enable_memory is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = AgentConfig(
            name="TestAgent",
            system_prompt="You are a test agent.",
            temperature=0.5,
            max_tokens=100,
        )
        
        assert config.name == "TestAgent"
        assert config.system_prompt == "You are a test agent."
        assert config.temperature == 0.5
        assert config.max_tokens == 100


class TestAgent:
    """Tests for Agent class."""

    def test_agent_creation(self):
        """Test creating an agent."""
        agent = create_agent(name="TestAgent")
        
        assert agent.name == "TestAgent"
        assert agent.state.active is True

    def test_agent_id(self):
        """Test agent ID generation."""
        agent = create_agent(name="My Agent")
        
        assert agent.id == "agent_my_agent"

    def test_agent_start_session(self):
        """Test starting a session."""
        agent = create_agent()
        
        session = agent.start_session()
        
        assert session is not None
        assert session.is_active is True
        assert agent.get_session() is not None

    def test_agent_end_session(self):
        """Test ending a session."""
        agent = create_agent()
        
        agent.start_session()
        session = agent.end_session()
        
        assert session is not None
        assert session.is_active is False
        assert agent.get_session() is None

    def test_agent_chat(self):
        """Test chatting with agent."""
        llm = BaseLLM()
        llm.set_provider(MockProvider())
        
        agent = create_agent(llm=llm)
        
        response = agent.chat("Hello!")
        
        assert response is not None
        assert response.content is not None
        assert agent.state.turn_count == 1

    def test_agent_chat_creates_session(self):
        """Test that chat auto-starts a session."""
        agent = create_agent()
        
        assert agent.get_session() is None
        
        agent.chat("Hello!")
        
        assert agent.get_session() is not None

    def test_agent_chat_records_messages(self):
        """Test that chat records messages in session."""
        llm = BaseLLM()
        llm.set_provider(MockProvider({
            "hello": "Hi there!",
        }))
        
        agent = create_agent(llm=llm)
        agent.chat("hello")
        
        session = agent.get_session()
        context = session.get_context()
        
        assert len(context) == 2  # User + Assistant
        assert context[0]["role"] == "user"
        assert context[1]["role"] == "assistant"

    def test_agent_register_tool(self):
        """Test registering a tool."""
        agent = create_agent()
        
        def my_tool():
            return "tool result"
        
        agent.register_tool("my_tool", my_tool)
        
        assert "my_tool" in agent.list_tools()
        assert agent.get_tool("my_tool") == my_tool

    def test_agent_get_stats(self):
        """Test getting agent statistics."""
        agent = create_agent(name="StatsAgent")
        
        stats = agent.get_stats()
        
        assert stats["name"] == "StatsAgent"
        assert stats["active"] is True
        assert stats["turn_count"] == 0


class TestAgentWithMockLLM:
    """Tests for agent with mock LLM responses."""

    def test_agent_custom_responses(self):
        """Test agent with custom mock responses."""
        llm = BaseLLM()
        llm.set_provider(MockProvider({
            "weather": "It's sunny today!",
            "joke": "Why did the chicken cross the road?",
        }))

        # Test weather response
        agent1 = create_agent(llm=llm)
        response = agent1.chat("What's the weather?")
        assert "sunny" in response.content.lower()

        # Test joke response with fresh agent (no history interference)
        agent2 = create_agent(llm=llm)
        response = agent2.chat("Tell me a joke")
        assert "chicken" in response.content.lower()

    def test_agent_multiple_turns(self):
        """Test multiple conversation turns."""
        llm = BaseLLM()
        llm.set_provider(MockProvider())

        agent = create_agent(llm=llm)

        agent.chat("First message")
        agent.chat("Second message")
        agent.chat("Third message")

        assert agent.state.turn_count == 3

        session = agent.get_session()
        context = session.get_context()

        assert len(context) == 6  # 3 user + 3 assistant messages


class TestAgentMemory:
    """Tests for agent memory functionality."""

    def test_agent_memory_enabled(self):
        """Test agent with memory enabled."""
        config = AgentConfig(enable_memory=True)
        llm = BaseLLM()
        llm.set_provider(MockProvider())
        
        agent = Agent(config=config, llm=llm)
        agent.chat("Test message")
        
        session = agent.get_session()
        
        # Messages should be stored as stones
        assert session.stones is not None
        assert len(session.stones) > 0

    def test_agent_memory_disabled(self):
        """Test agent with memory disabled."""
        config = AgentConfig(enable_memory=False)
        llm = BaseLLM()
        llm.set_provider(MockProvider())
        
        agent = Agent(config=config, llm=llm)
        agent.chat("Test message")
        
        session = agent.get_session()
        
        # Stones should not be created
        assert len(session.stones) == 0


class TestCreateAgent:
    """Tests for create_agent factory function."""

    def test_create_agent_with_system_prompt(self):
        """Test creating agent with custom system prompt."""
        agent = create_agent(
            name="CustomAgent",
            system_prompt="You are a custom assistant.",
        )
        
        assert agent.config.system_prompt == "You are a custom assistant."

    def test_create_agent_with_options(self):
        """Test creating agent with various options."""
        agent = create_agent(
            name="OptionAgent",
            temperature=0.3,
            max_tokens=500,
            enable_memory=False,
        )
        
        assert agent.config.temperature == 0.3
        assert agent.config.max_tokens == 500
        assert agent.config.enable_memory is False
