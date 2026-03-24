"""
LLM - LLM abstraction layer.

Phase 06: Agent Core
"""

import json
import logging
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Callable, Dict, Iterator, List, Optional


class MessageRole(Enum):
    """Roles for LLM messages."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class Message:
    """A message in an LLM conversation."""
    role: MessageRole
    content: str
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None  # For tool result messages (Ollama format)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to API-compatible dictionary."""
        result = {
            "role": self.role.value,
            "content": self.content,
        }
        if self.name:
            result["name"] = self.name
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        if self.tool_name:
            result["tool_name"] = self.tool_name  # Ollama requires this for tool results
        return result


@dataclass
class LLMResponse:
    """Response from an LLM."""
    content: str
    role: MessageRole = MessageRole.ASSISTANT
    finish_reason: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    tool_calls: Optional[List[Dict[str, Any]]] = None  # Tool calls from model
    thinking: Optional[str] = None  # Thinking/reasoning content (qwen3 models)

    def to_message(self) -> Message:
        """Convert response to a Message."""
        return Message(
            role=self.role,
            content=self.content,
            tool_calls=self.tool_calls,
        )


@dataclass
class ToolCall:
    """Represents a tool call from the model."""
    id: str
    name: str
    arguments: Dict[str, Any]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolCall":
        """Create from dictionary."""
        return cls(
            id=data.get("id", ""),
            name=data.get("function", {}).get("name", ""),
            arguments=data.get("function", {}).get("arguments", {}),
        )


@dataclass
class LLMConfig:
    """Configuration for LLM requests."""
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    stop: Optional[List[str]] = None
    stream: bool = False


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    def complete(self, messages: List[Message], config: Optional[LLMConfig] = None) -> LLMResponse:
        """Generate a completion."""
        pass
    
    @abstractmethod
    def stream_complete(self, messages: List[Message], config: Optional[LLMConfig] = None) -> Iterator[str]:
        """Stream a completion."""
        pass


class BaseLLM:
    """
    Base LLM client with common functionality.
    
    Phase 06: Abstract interface - concrete implementations
    for specific providers (OpenAI, Anthropic, etc.) added later.
    """
    
    def __init__(self, provider: Optional[LLMProvider] = None,
                 config: Optional[LLMConfig] = None):
        self._provider = provider
        self._config = config or LLMConfig()
        self._history: List[List[Message]] = []
    
    def set_provider(self, provider: LLMProvider) -> None:
        """Set the LLM provider."""
        self._provider = provider
    
    def configure(self, **kwargs: Any) -> None:
        """Update configuration."""
        for key, value in kwargs.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)
    
    def complete(self, messages: Optional[List[Message]] = None,
                 prompt: Optional[str] = None,
                 config: Optional[LLMConfig] = None,
                 tools: Optional[List[Dict[str, Any]]] = None,
                 mcp_client=None) -> LLMResponse:
        """
        Generate a completion with optional tool calling support.

        Args:
            messages: List of conversation messages
            prompt: Simple prompt (converted to single message)
            config: Optional config override
            tools: List of tool schemas for tool calling
            mcp_client: MCP client for tool execution (enables agentic loop)

        Returns:
            LLMResponse with generated content

        Tool Calling Flow:
            1. Send messages + tools to model
            2. If model returns tool_calls, execute via MCP
            3. Add tool results to messages
            4. Loop back to step 1 until model returns content
        """
        if self._provider is None:
            # Mock response for development
            return self._mock_complete(messages or [], config)

        msg_list = messages or []
        if prompt:
            msg_list = [Message(role=MessageRole.USER, content=prompt)]

        effective_config = config or self._config

        # If MCP client provided, run agentic tool loop
        if mcp_client and tools:
            return self._complete_with_tools(msg_list, effective_config, tools, mcp_client)

        # Standard completion without tools
        response = self._provider.complete(msg_list, effective_config)

        # Store in history
        self._history.append(msg_list + [response.to_message()])

        return response

    def _complete_with_tools(self, messages: List[Message],
                             config: LLMConfig,
                             tools: List[Dict[str, Any]],
                             mcp_client) -> LLMResponse:
        """
        Execute completion with tool calling loop.

        This implements the agentic loop:
        - Call model with tools
        - If tool calls returned, execute them
        - Add results to messages
        - Loop until model returns final content
        """
        # Guard: tools requested but no MCP client — fall back to standard completion
        if tools and mcp_client is None:
            import warnings
            warnings.warn(
                "tools provided but mcp_client is None — falling back to standard completion",
                RuntimeWarning,
                stacklevel=2
            )
            # Fall back to standard completion without tools
            response = self._provider.complete(messages, config, tools=None)
            self._history.append(messages + [response.to_message()])
            return response
        
        max_iterations = 20  # Prevent infinite loops (increased for complex multi-turn tasks)
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            import logging
            logging.debug(f"[ENGRAM] Tool loop iteration {iteration}, messages count: {len(messages)}")

            # Call provider with tools
            response = self._provider.complete(messages, config, tools=tools)
            logging.debug(f"[ENGRAM] Provider response: content={repr(response.content[:50] if response.content else '(empty)')}, tool_calls={len(response.tool_calls) if response.tool_calls else 0}, thinking={repr(response.thinking[:50] if response.thinking else 'None')}")

            # Check for tool calls
            if not response.tool_calls:
                # No tool calls - model is done, return final response
                logging.debug(f"[ENGRAM] No tool calls, returning response with content: {repr(response.content[:100] if response.content else '(empty)')}")
                self._history.append(messages + [response.to_message()])
                return response

            # Add assistant's tool call request to history FIRST (before executing tools)
            messages.append(response.to_message())

            # Execute each tool call
            for tool_call_data in response.tool_calls:
                tool_call = ToolCall.from_dict(tool_call_data)
                logging.debug(f"[ENGRAM] Executing tool: {tool_call.name}")

                # Execute tool via MCP client
                try:
                    # Parse arguments (may be JSON string or dict)
                    args = tool_call.arguments
                    if isinstance(args, str):
                        import json
                        args = json.loads(args)

                    # Call tool (use mock fallback if needed)
                    if hasattr(mcp_client, 'call_tool'):
                        result = mcp_client.call_tool(tool_call.name, args)
                    else:
                        result = mcp_client.call_tool_mock(tool_call.name, args)

                    logging.debug(f"[ENGRAM] Tool result: success={result.success}")

                    # Add tool result as message (Ollama format)
                    tool_message = Message(
                        role=MessageRole.TOOL,
                        content=str(result.result) if result.success else f"Error: {result.error}",
                        tool_name=tool_call.name,  # Ollama requires tool_name for tool results
                        tool_call_id=tool_call.id,
                    )
                    messages.append(tool_message)

                except Exception as e:
                    logging.error(f"[ENGRAM] Tool execution error: {e}")
                    # Add error result
                    error_message = Message(
                        role=MessageRole.TOOL,
                        content=f"Tool execution error: {str(e)}",
                        tool_name=tool_call.name,  # Ollama requires tool_name for tool results
                        tool_call_id=tool_call.id,
                    )
                    messages.append(error_message)

        # Max iterations reached - return what we have
        response.content = f"[Max tool iterations ({max_iterations}) reached]"
        self._history.append(messages + [response.to_message()])
        return response
    
    def stream(self, messages: Optional[List[Message]] = None,
               prompt: Optional[str] = None,
               config: Optional[LLMConfig] = None) -> Iterator[str]:
        """Stream a completion."""
        if self._provider is None:
            # Mock streaming
            yield from self._mock_stream(messages or [], config)
            return
        
        msg_list = messages or []
        if prompt:
            msg_list = [Message(role=MessageRole.USER, content=prompt)]
        
        effective_config = config or self._config
        effective_config.stream = True
        
        yield from self._provider.stream_complete(msg_list, effective_config)
    
    def chat(self, user_message: str, system_prompt: Optional[str] = None) -> LLMResponse:
        """
        Simple chat interface.
        
        Args:
            user_message: User's message
            system_prompt: Optional system prompt
        
        Returns:
            LLMResponse with assistant's reply
        """
        messages = []
        
        if system_prompt:
            messages.append(Message(role=MessageRole.SYSTEM, content=system_prompt))
        
        messages.append(Message(role=MessageRole.USER, content=user_message))
        
        return self.complete(messages=messages)
    
    def get_history(self) -> List[List[Message]]:
        """Get conversation history."""
        return list(self._history)
    
    def clear_history(self) -> None:
        """Clear conversation history."""
        self._history.clear()
    
    def _mock_complete(self, messages: List[Message], 
                       config: Optional[LLMConfig] = None) -> LLMResponse:
        """Mock completion for development."""
        last_message = messages[-1].content if messages else ""
        
        return LLMResponse(
            content=f"[Mock Response] I received: {last_message[:100]}...",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )
    
    def _mock_stream(self, messages: List[Message],
                     config: Optional[LLMConfig] = None) -> Iterator[str]:
        """Mock streaming for development."""
        mock_text = "[Mock Stream] This is a simulated streaming response."
        for word in mock_text.split():
            yield word + " "


class MockProvider(LLMProvider):
    """Mock LLM provider for testing."""

    def __init__(self, responses: Optional[Dict[str, str]] = None):
        self._responses = responses or {}
        self._default_response = "I am a mock LLM. How can I help?"

    def complete(self, messages: List[Message], config: Optional[LLMConfig] = None,
                 tools: Optional[List[Dict[str, Any]]] = None) -> LLMResponse:
        """Return a mock completion (ignores tools for testing)."""
        last_content = messages[-1].content if messages else ""

        # Check for specific responses
        for trigger, response in self._responses.items():
            if trigger.lower() in last_content.lower():
                return LLMResponse(content=response)

        return LLMResponse(content=self._default_response)

    def stream_complete(self, messages: List[Message], config: Optional[LLMConfig] = None) -> Iterator[str]:
        """Stream mock completion."""
        response = self.complete(messages, config)
        yield from response.content.split()


class OllamaProvider(LLMProvider):
    """
    Ollama provider for local LLM inference.

    Connects to a local Ollama instance at http://127.0.0.1:11434/
    """

    def __init__(self,
                 model: str = "bazobehram/qwen3-14b-claude-4.5-opus-high-reasoning:latest",
                 base_url: str = "http://127.0.0.1:11434",
                 options: Optional[Dict[str, Any]] = None):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.options = options or {}

    def _complete_with_retry(self, payload: dict,
                             max_attempts: int = 3) -> dict:
        """Complete with exponential backoff retry."""
        import time
        import logging
        last_error = None

        for attempt in range(max_attempts):
            try:
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    self.base_url + "/api/chat",
                    data=data,
                    headers={"Content-Type": "application/json"},
                )

                with urllib.request.urlopen(req, timeout=300) as response:
                    return json.loads(response.read().decode("utf-8"))

            except urllib.error.HTTPError as e:
                # Log HTTP error details
                last_error = e
                logging.error(f"[ENGRAM] Ollama HTTP {e.code}: {e.reason}")
                try:
                    error_body = e.read().decode('utf-8')
                    logging.error(f"[ENGRAM] Ollama error body: {error_body[:500]}")
                except Exception as e:
                    logging.warning(f"[ENGRAM] Ollama error body read failed: {e}")
                # Don't retry HTTP 400 - it's a bad request, not transient
                if e.code == 400:
                    raise
                if attempt < max_attempts - 1:
                    wait = 2 ** attempt
                    logging.warning(
                        f"[ENGRAM] llm — attempt {attempt+1} failed: {e}. "
                        f"Retrying in {wait}s..."
                    )
                    time.sleep(wait)
                    
            except (ConnectionError,
                    urllib.error.URLError,
                    urllib.error.HTTPError,
                    TimeoutError) as e:
                last_error = e
                if attempt < max_attempts - 1:
                    wait = 2 ** attempt  # 1s, 2s, 4s
                    import logging
                    logging.warning(
                        f"[ENGRAM] llm — attempt {attempt+1} failed: {e}. "
                        f"Retrying in {wait}s..."
                    )
                    time.sleep(wait)
        
        raise ConnectionError(
            f"[ENGRAM] llm — all {max_attempts} attempts failed. "
            f"Last error: {last_error}"
        )

    def complete(self, messages: List[Message], config: Optional[LLMConfig] = None,
                 tools: Optional[List[Dict[str, Any]]] = None) -> LLMResponse:
        """Generate a completion using Ollama with optional tool calling."""
        import logging

        url = f"{self.base_url}/api/chat"

        # Enable thinking only for qwen3 models that support it
        # qwen3.5, qwen3 support thinking; qwen3-coder variants do not
        model_name = self.model.lower()
        supports_thinking = (
            model_name.startswith('qwen3.5') or 
            (model_name.startswith('qwen3') and 'coder' not in model_name)
        )

        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "stream": False,
            "options": self._build_options(config),
        }
        
        # Only add think parameter for models that support it
        if supports_thinking:
            payload["think"] = True

        # Only add tools if provided and non-empty (some models don't support tools)
        if tools:
            payload["tools"] = tools
            logging.debug(f"[ENGRAM] Ollama payload: model={self.model}, messages={len(messages)}, tools={len(tools)}")
        else:
            logging.debug(f"[ENGRAM] Ollama payload: model={self.model}, messages={len(messages)}, no tools")

        try:
            # Use retry wrapper for transient errors
            result = self._complete_with_retry(payload)

            message = result.get("message", {})

            return LLMResponse(
                content=message.get("content", ""),
                role=MessageRole.ASSISTANT,
                finish_reason=result.get("done_reason"),
                tool_calls=message.get("tool_calls"),
                thinking=message.get("thinking"),  # Capture thinking content (qwen3 models)
                usage={
                    "prompt_tokens": result.get("prompt_eval_count", 0),
                    "completion_tokens": result.get("eval_count", 0),
                    "total_tokens": result.get("prompt_eval_count", 0) + result.get("eval_count", 0),
                },
            )
        except urllib.error.HTTPError as e:
            # Log error details
            import logging
            logging.error(f"[ENGRAM] Ollama HTTP error {e.code}: {e.reason}")
            try:
                error_body = e.read().decode('utf-8')
                logging.error(f"[ENGRAM] Ollama error body: {error_body}")
            except Exception as e:
                logging.warning(f"[ENGRAM] Ollama error body read failed: {e}")

            # HTTP 400 - model may not support tools, retry without tools
            if e.code == 400 and tools:
                payload.pop("tools", None)
                logging.info("[ENGRAM] Retrying without tools...")
                try:
                    data = json.dumps(payload).encode("utf-8")
                    req = urllib.request.Request(
                        url,
                        data=data,
                        headers={"Content-Type": "application/json"},
                    )

                    with urllib.request.urlopen(req, timeout=120) as response:
                        result = json.loads(response.read().decode("utf-8"))
                        message = result.get("message", {})

                        return LLMResponse(
                            content=message.get("content", ""),
                            role=MessageRole.ASSISTANT,
                            finish_reason=result.get("done_reason"),
                            usage={
                                "prompt_tokens": result.get("prompt_eval_count", 0),
                                "completion_tokens": result.get("eval_count", 0),
                                "total_tokens": result.get("prompt_eval_count", 0) + result.get("eval_count", 0),
                            },
                        )
                except Exception as retry_error:
                    return LLMResponse(
                        content=f"Ollama error (retry failed): {str(retry_error)}",
                        role=MessageRole.ASSISTANT,
                    )
            
            return LLMResponse(
                content=f"Error connecting to Ollama: HTTP Error {e.code}",
                role=MessageRole.ASSISTANT,
            )
        except urllib.error.URLError as e:
            return LLMResponse(
                content=f"Error connecting to Ollama: {str(e)}",
                role=MessageRole.ASSISTANT,
            )
        except Exception as e:
            return LLMResponse(
                content=f"Ollama error: {str(e)}",
                role=MessageRole.ASSISTANT,
            )
    
    def stream_complete(self, messages: List[Message], config: Optional[LLMConfig] = None) -> Iterator[str]:
        """Stream a completion using Ollama."""
        url = f"{self.base_url}/api/chat"
        
        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "stream": True,
            "options": self._build_options(config),
        }
        
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
            )
            
            with urllib.request.urlopen(req, timeout=120) as response:
                for line in response:
                    if line:
                        chunk = json.loads(line.decode("utf-8"))
                        if chunk.get("message", {}).get("content"):
                            yield chunk["message"]["content"]
                        if chunk.get("done", False):
                            break
        except Exception as e:
            yield f"Error: {str(e)}"
    
    def _build_options(self, config: Optional[LLMConfig] = None) -> Dict[str, Any]:
        """Build Ollama options from config."""
        options = dict(self.options)

        if config:
            # Only include options that Ollama supports
            if config.temperature is not None:
                options["temperature"] = config.temperature
            if config.max_tokens is not None:
                options["num_predict"] = config.max_tokens
            if config.top_p is not None and config.top_p != 1.0:
                options["top_p"] = config.top_p
            if config.stop:
                options["stop"] = config.stop
            # Note: frequency_penalty and presence_penalty not supported by Ollama

        return options


def make_llm_call(llm: "BaseLLM") -> Callable[[str], str]:
    """
    Wrap a BaseLLM instance into a plain Callable[[str], str].

    scorer.py, learner.py, and experience.py expect llm_call to have the
    signature (prompt: str, model: str = ...) -> str, but BaseLLM.chat()
    returns an LLMResponse.  This adapter bridges the two contracts.

    Args:
        llm: A configured BaseLLM instance

    Returns:
        A callable that takes (prompt, model=...) and returns response text

    Example:
        >>> llm = create_llm("ollama", model="qwen3:30b-a3b-q4_K_M")
        >>> llm_call = make_llm_call(llm)
        >>> score = score_task(task, response, tool_calls, llm_call=llm_call)
    """
    def _call(prompt: str, model: Optional[str] = None) -> str:
        response = llm.chat(prompt)
        return response.content
    return _call


def create_llm(provider_name: str = "mock", **kwargs: Any) -> "BaseLLM":
    """
    Factory function to create an LLM instance.

    Args:
        provider_name: Name of the provider ("mock", "openai", "anthropic", "ollama")
        **kwargs: Provider-specific arguments

    Returns:
        Configured BaseLLM instance
    """
    llm = BaseLLM()

    if provider_name == "mock":
        llm.set_provider(MockProvider())
    elif provider_name == "ollama":
        llm.set_provider(OllamaProvider(**kwargs))
    elif provider_name == "openai":
        # Placeholder for OpenAI provider
        # from .providers.openai import OpenAIProvider
        # llm.set_provider(OpenAIProvider(**kwargs))
        pass
    elif provider_name == "anthropic":
        # Placeholder for Anthropic provider
        pass

    return llm
