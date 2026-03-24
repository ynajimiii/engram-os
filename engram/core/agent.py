"""
Agent - Base agent implementation.

Phase 06: Agent Core
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
import re


def _count_task_requirements(task_text: str) -> int:
    """
    Count the number of distinct requirements in a task.
    
    Used to identify complex tasks that should be broken down.
    (FAILURE_ANALYSIS_REPORT.md recommendation)
    
    Args:
        task_text: The task description
        
    Returns:
        Number of requirements detected
    """
    if not task_text:
        return 0
    
    # Count numbered steps (1) 2) 3) or 1. 2. 3.)
    numbered = len(re.findall(r'\b\d+[.)]\s*', task_text))
    
    # Count bullet points
    bullets = len(re.findall(r'\n\s*[-•*]\s*', task_text))
    
    # Count imperative verbs (common task indicators)
    verbs = len(re.findall(
        r'\b(create|write|read|explain|analyze|fix|implement|add|remove|'
        r'update|delete|run|test|build|generate|list|identify|check|'
        r'configure|setup|install|deploy|refactor|optimize)\b',
        task_text.lower()
    ))
    
    # Count "and" conjunctions (often joins multiple requirements)
    and_count = len(re.findall(r'\band\b', task_text))
    
    # Count colons followed by lists
    list_colons = len(re.findall(r':\s*\d+\s', task_text))
    
    # Total is weighted sum
    # Note: verbs count directly (not divided) to catch single-verb tasks
    # and_count weighted at 0.5 since not all "and" indicate new requirements
    total = numbered + bullets + verbs + int(and_count * 0.5) + (list_colons * 2)
    
    return total


def _get_complexity_warning(requirements: int) -> Optional[str]:
    """
    Get a warning message if task is too complex.
    
    Args:
        requirements: Number of requirements detected
        
    Returns:
        Warning message or None if task is simple enough
    """
    if requirements <= 4:
        return None  # Simple task (1-4 requirements)
    elif requirements <= 7:
        return (
            f"Note: This task has {requirements} requirements. "
            f"Consider breaking into smaller sub-tasks for better results."
        )
    else:
        return (
            f"Warning: This task has {requirements} requirements (high complexity). "
            f"Recommended: Break into {requirements // 3 + 1} separate tasks: "
            f"1) Read/analyze, 2) Plan, 3) Implement, 4) Test, 5) Document."
        )

from .llm import BaseLLM, LLMResponse, Message, MessageRole
from .session import Session, SessionManager
from .assembler import ContextAssembler, AssembledContext
from .writeback import WritebackManager
from .stones import MemoryStone
from .mcp_client import MCPClient
from .scorer import score_task, QualityScore
from .vector_db import VectorDB


# ── Tool call tracking — populated during agent_turn() ────────
# Reset to [] at the start of every agent_turn() call.
# Read via get_last_tool_calls() immediately after agent_turn().
# Never read this directly — use the getter.
_last_tool_calls: list = []
_tool_call_lock: bool  = False   # re-entrancy guard


@dataclass
class AgentConfig:
    """Configuration for an agent."""
    name: str = "Agent"
    system_prompt: str = "You are a helpful assistant."
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    enable_memory: bool = True
    enable_writeback: bool = True
    enable_tools: bool = True  # Enable MCP tool calling
    context_limit: Optional[int] = None
    mcp_config_path: Optional[str] = None  # Path to MCP servers config


@dataclass
class AgentState:
    """Current state of an agent."""
    active: bool = True
    turn_count: int = 0
    last_activity: datetime = field(default_factory=datetime.now)
    current_task: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class Agent:
    """
    Base agent with memory and context management.
    
    Phase 06: Core agent functionality with LLM integration,
    session management, and memory persistence.
    """
    
    def __init__(self, config: Optional[AgentConfig] = None,
                 llm: Optional[BaseLLM] = None,
                 session_manager: Optional[SessionManager] = None,
                 writeback_manager: Optional[WritebackManager] = None,
                 mcp_client: Optional[MCPClient] = None):
        self.config = config or AgentConfig()
        self._llm = llm or BaseLLM()
        self._session_manager = session_manager or SessionManager()
        self._writeback_manager = writeback_manager or WritebackManager()
        self._mcp_client = mcp_client

        self._assembler = ContextAssembler(system_prompt=self.config.system_prompt)
        self._state = AgentState()
        self._tools: Dict[str, Callable] = {}
        self._tool_history: List[Dict[str, Any]] = []
        self._session_log: List[Dict[str, Any]] = []
        self._quality_scores: List[QualityScore] = []
        self._vector_db: Optional[VectorDB] = None

        self._current_session: Optional[Session] = None

        # Initialize MCP client if tools enabled
        if self.config.enable_tools and mcp_client is None:
            self._init_mcp_client()

    def _init_mcp_client(self) -> None:
        """Initialize MCP client from config."""
        import logging
        try:
            config_path = self.config.mcp_config_path or "engram/config/mcp_servers.yaml"
            self._mcp_client = MCPClient(config_path)
            self._mcp_client.connect_from_config()
        except Exception as e:
            logging.warning(
                f"[ENGRAM] MCP client init failed — tools disabled: {e}. "
                f"Run 'engram doctor' to diagnose."
            )
    
    @property
    def id(self) -> str:
        """Return agent identifier."""
        return f"agent_{self.config.name.lower().replace(' ', '_')}"
    
    @property
    def name(self) -> str:
        """Return agent name."""
        return self.config.name
    
    @property
    def state(self) -> AgentState:
        """Return current agent state."""
        return self._state
    
    def start_session(self, session_id: Optional[str] = None,
                      metadata: Optional[Dict[str, Any]] = None) -> Session:
        """Start or resume a session, promoting relevant experiences on resume."""
        if session_id:
            session = self._session_manager.get_session(session_id)
            if session is None:
                raise ValueError(f"Session not found: {session_id}")
            # Warm up the hot tier with experiences relevant to this session.
            self._promote_experiences_for_session(session)
        else:
            session = self._session_manager.create_session(metadata=metadata)

        self._current_session = session
        self._state.active = True
        self._state.last_activity = datetime.now()

        return session

    def _promote_experiences_for_session(self, session: "Session") -> None:
        """
        Promote relevant experience chunks to the hot tier on session resume.

        Inspects the last few user turns to infer task type, then pulls
        matching experiences from the vector DB and promotes them so they
        appear in context assembly for the next turn.
        """
        import logging
        if self._vector_db is None:
            return

        context = session.state.context_window
        if not context:
            return

        recent_user_msgs = [
            msg.get("content", "")
            for msg in context[-5:]
            if msg.get("role") == "user"
        ]
        if not recent_user_msgs:
            return

        try:
            from .experience import get_relevant_experiences, _extract_task_type
            promoted_count = 0
            for task_text in recent_user_msgs:
                task_type = _extract_task_type(task_text.lower())
                experiences = get_relevant_experiences(
                    task_type, self._vector_db, top_k=3
                )
                for exp in experiences:
                    if self._vector_db.promote(exp.id, to_tier="hot"):
                        promoted_count += 1
            if promoted_count:
                logging.debug(
                    f"[ENGRAM] promoted {promoted_count} experience(s) to hot tier "
                    f"for session '{session.session_id}'."
                )
        except Exception as e:
            logging.debug(f"[ENGRAM] experience promotion skipped: {e}")
    
    def end_session(self) -> Optional[Session]:
        """End the current session."""
        if self._current_session is None:
            return None
        
        session = self._current_session
        session.end()
        
        # Save session
        self._session_manager.save_session(session.session_id)
        
        # Trigger writeback
        if self.config.enable_writeback:
            self._writeback_manager.queue_session(session)
            self._writeback_manager.flush()
        
        self._current_session = None
        self._state.active = False
        
        return session
    
    def chat(self, user_message: str, **kwargs: Any) -> LLMResponse:
        """
        Process a user message and generate a response.

        Args:
            user_message: The user's input message
            **kwargs: Additional context or options

        Returns:
            LLMResponse with the agent's reply
        """
        import time
        start_time = time.time()  # Start timing
        
        # Check task complexity and warn if too complex
        requirements = _count_task_requirements(user_message)
        complexity_warning = _get_complexity_warning(requirements)
        
        if complexity_warning:
            import logging
            logging.warning(f"[ENGRAM] {complexity_warning}")
        
        if self._current_session is None:
            self.start_session()

        # Add user message to session context
        self._current_session.state.context_window.append({
            "role": "user",
            "content": user_message,
            "timestamp": datetime.now().isoformat(),
        })
        self._state.turn_count += 1
        self._state.last_activity = datetime.now()

        # Build context
        context = self._build_context(user_message, **kwargs)

        # Generate response with timing
        response = self._generate_response(context)
        
        # Calculate response time
        response_time = time.time() - start_time
        
        # Log warning for slow responses (>60 seconds)
        if response_time > 60:
            import logging
            logging.warning(
                f"[ENGRAM] Slow response: {response_time:.1f}s for task: {user_message[:50]}..."
            )

        # Score the response (Phase 11) - wrapped in non-blocking guard
        try:
            quality_score = score_task(
                task=user_message,
                response=response.content,
                tool_calls=self._tool_history,
                session_log=self._session_log,
                llm_call=self._llm.chat,
            )
        except Exception as e:
            import logging
            logging.warning(f"[ENGRAM] score_task failed — defaulting to 0.0: {e}")
            from engram.core.scorer import QualityScore
            quality_score = QualityScore(
                score=0.0,
                source="error",
                reason=f"Scoring failed: {str(e)}",
            )

        # Log quality score with response time and complexity
        self._quality_scores.append(quality_score)
        self._session_log.append({
            "task": user_message,
            "response_length": len(response.content),
            "tool_calls_count": len(self._tool_history),
            "quality_score": quality_score.score,
            "quality_source": quality_score.source,
            "quality_reason": quality_score.reason,
            "response_time": round(response_time, 2),
            "task_complexity": requirements,  # Add complexity score
            "timestamp": datetime.now().isoformat(),
        })

        # Trigger learning checks (Phase 12) — non-blocking, runs every 10 tasks.
        try:
            self.check_learning_triggers()
        except Exception as _lte:
            import logging
            logging.debug(f"[ENGRAM] learning trigger check failed: {_lte}")

        # Add assistant response to session context
        self._current_session.state.context_window.append({
            "role": "assistant",
            "content": response.content,
            "timestamp": datetime.now().isoformat(),
        })
        self._current_session.updated_at = datetime.now()

        # Store in memory (stones) only if enabled
        if self.config.enable_memory:
            self._store_memory(user_message, response)

        return response
    
    def _build_context(self, user_message: str, **kwargs: Any) -> AssembledContext:
        """Build context for the LLM."""
        self._assembler.clear()
        
        # Add conversation history
        if self._current_session:
            history = self._current_session.get_context(limit=self.config.context_limit)
            if history:
                self._assembler.add_history(history)
        
        # Add any additional context from kwargs
        if "context" in kwargs:
            self._assembler.add_user_context(kwargs["context"])
        
        if "knowledge" in kwargs:
            self._assembler.add_knowledge(kwargs["knowledge"])
        
        # Assemble
        return self._assembler.assemble(user_message)
    
    def _generate_response(self, context: AssembledContext, retry_count: int = 0) -> LLMResponse:
        """
        Generate response from LLM with optional tool calling.
        
        Includes retry logic for short responses (FAILURE_ANALYSIS_REPORT.md).
        """
        messages = [
            Message(role=MessageRole.SYSTEM, content=self.config.system_prompt),
            Message(role=MessageRole.USER, content=context.prompt),
        ]

        # Configure LLM with max_tokens from config
        self._llm.configure(
            model=self.config.model,
            temperature=self.config.temperature,
            max_tokens=getattr(self.config, 'max_tokens', None),
        )

        # Get tools from MCP client if available
        tools = None
        mcp_client = None

        if self.config.enable_tools and self._mcp_client:
            tools = self._mcp_client.get_ollama_tool_schemas()
            mcp_client = self._mcp_client

        response = self._llm.complete(
            messages=messages,
            tools=tools,
            mcp_client=mcp_client,
        )

        # Check response length and retry if too short
        min_chars = getattr(self.config, 'min_response_chars', 150)
        max_retries = getattr(self.config, 'max_retries', 2)
        
        if len(response.content) < min_chars and retry_count < max_retries:
            import logging
            logging.warning(
                f"[ENGRAM] Response too short ({len(response.content)} chars < {min_chars}), "
                f"retrying ({retry_count + 1}/{max_retries})..."
            )
            
            # Retry with explicit instruction for complete response
            retry_messages = messages + [
                Message(role=MessageRole.ASSISTANT, content=response.content),
                Message(
                    role=MessageRole.USER, 
                    content="Please provide a complete, detailed response. Do not truncate. "
                           "Include all requested information with full explanations."
                ),
            ]
            
            response = self._llm.complete(
                messages=retry_messages,
                tools=tools,
                mcp_client=mcp_client,
            )
            
            # Log if still short after retry
            if len(response.content) < min_chars:
                logging.warning(
                    f"[ENGRAM] Response still short after retry ({len(response.content)} chars)"
                )

        return response
    
    def _store_memory(self, user_message: str, response: LLMResponse) -> None:
        """Store interaction in memory."""
        if self._current_session is None:
            return
        
        if not self.config.enable_memory:
            return

        # Create memory stones
        user_stone = MemoryStone(
            content=user_message,
            stone_type="user_input",
            metadata={"turn": self._state.turn_count},
        )
        
        response_stone = MemoryStone(
            content=response.content,
            stone_type="agent_response",
            metadata={"turn": self._state.turn_count},
        )
        
        self._current_session.stones.add(user_stone)
        self._current_session.stones.add(response_stone)
        
        # Queue for writeback
        if self.config.enable_writeback:
            self._writeback_manager.queue_stone(user_stone)
            self._writeback_manager.queue_stone(response_stone)
    
    def register_tool(self, name: str, tool: Callable) -> None:
        """Register a tool function."""
        self._tools[name] = tool
    
    def get_tool(self, name: str) -> Optional[Callable]:
        """Get a registered tool by name."""
        return self._tools.get(name)
    
    def list_tools(self) -> List[str]:
        """List all registered tools."""
        return list(self._tools.keys())
    
    def get_session(self) -> Optional[Session]:
        """Get the current session."""
        return self._current_session
    
    def get_stats(self) -> Dict[str, Any]:
        """Get agent statistics."""
        from .scorer import score_session
        
        stats = {
            "name": self.config.name,
            "turn_count": self._state.turn_count,
            "active": self._state.active,
            "tools": list(self._tools.keys()),
            "session_id": self._current_session.session_id if self._current_session else None,
            "mcp_enabled": self.config.enable_tools,
            "mcp_servers": 0,
        }

        if self._mcp_client:
            server_status = self._mcp_client.get_server_status()
            stats["mcp_servers"] = len([s for s in server_status.values() if s.get("connected", False)])
            stats["mcp_server_names"] = list(server_status.keys())
        
        # Add quality statistics (Phase 11)
        if self._session_log:
            quality_stats = score_session(self._session_log)
            stats["quality"] = quality_stats

        return stats

    def get_tool_history(self) -> List[Dict[str, Any]]:
        """Get history of tool calls."""
        if self._mcp_client:
            return self._mcp_client.get_tool_history()
        return self._tool_history

    def get_mcp_status(self) -> Dict[str, Any]:
        """Get MCP client status."""
        if self._mcp_client:
            return self._mcp_client.get_server_status()
        return {"enabled": False}

    def check_learning_triggers(self) -> Dict[str, Any]:
        """
        Check and run learning triggers based on session progress.

        Phase 12 Integration:
        - Run learning cycle every 10 tasks (at 10, 20, 30, ...)
        - Run experience distillation every 20 tasks

        Returns:
            Dictionary with learning results
        """
        from .learner import learning_cycle, run_learning_cycles
        from .experience import run_distillation

        results = {
            "learning_cycle_run": False,
            "distillation_run": False,
            "experiences_distilled": 0,
            "patches_proposed": 0,
        }

        session_log = self._session_log
        task_count = len(session_log)

        # Run learning cycle every 10 tasks
        # Use >= to catch cases where tasks were added without triggering
        if task_count >= 10 and task_count % 10 == 0:
            # Get current prompt from config
            current_prompt = self.config.system_prompt

            improved, patch = learning_cycle(
                module_name=self.config.name,
                session_log=session_log,
                current_prompt=current_prompt,
                llm_call=self._llm.chat,
            )

            results["learning_cycle_run"] = True
            if patch:
                results["patches_proposed"] = 1
                if improved:
                    results["patches_committed"] = 1

        # Run distillation every 20 tasks (requires an active vector DB)
        if task_count >= 20 and task_count % 20 == 0 and self._vector_db is not None:
            stats = run_distillation(
                session_log=session_log,
                db=self._vector_db,
                llm_call=self._llm.chat,
            )

            results["distillation_run"] = True
            results["experiences_distilled"] = stats.get("experiences_created", 0)

        return results


def create_agent(name: str = "Agent",
                 system_prompt: Optional[str] = None,
                 llm: Optional[BaseLLM] = None,
                 mcp_client: Optional[MCPClient] = None,
                 **kwargs: Any) -> Agent:
    """
    Factory function to create an agent.

    Args:
        name: Agent name
        system_prompt: Custom system prompt
        llm: Optional LLM instance
        mcp_client: Optional MCP client for tool calling
        **kwargs: Additional configuration options

    Returns:
        Configured Agent instance
    """
    config = AgentConfig(
        name=name,
        system_prompt=system_prompt or "You are a helpful assistant.",
        **kwargs,
    )

    return Agent(config=config, llm=llm, mcp_client=mcp_client)


def agent_turn(
    task_text: str,
    db: Optional[Any] = None,
    scratch: Optional[Any] = None,
    contract: Optional[Any] = None,
    stones: Optional[Any] = None,
    session_path: Optional[str] = None,
    mcp_client: Optional[MCPClient] = None
) -> str:
    """
    Execute one complete agent turn:
    1. Build context from stones + scratch
    2. Call LLM with full context
    3. Return response

    Args:
        task_text: The task/goal to accomplish
        db: Vector database for context retrieval
        scratch: Scratch memory for session state
        contract: Memory contract for resource limits
        stones: Stone collection with system_prompt and scratch_note
        session_path: Path to session file
        mcp_client: MCP client for tool calling

    Returns:
        Agent response as string
    """
    import logging
    import time
    
    # PHASE 1.1: Start response time monitoring
    start_time = time.time()
    
    # PHASE 1.2: Calculate task complexity
    requirements = _count_task_requirements(task_text)
    complexity_warning = _get_complexity_warning(requirements)
    
    if complexity_warning:
        logging.warning(f"[ENGRAM] agent_turn: {complexity_warning}")

    try:
        # Reset tool call tracker for this turn
        global _last_tool_calls, _tool_call_lock
        _last_tool_calls = []
        _tool_call_lock  = True
        # BUILD SYSTEM PROMPT FROM STONES
        # stones is a dict with key "system_prompt"
        # Use the module's actual agent system prompt
        system_prompt = ""
        scratch_context = ""

        if stones and isinstance(stones, dict):
            system_prompt = stones.get(
                "system_prompt", ""
            )
            scratch_context = stones.get(
                "scratch_note", ""
            )
        elif stones and hasattr(stones, 'system_prompt'):
            system_prompt = stones.system_prompt
            scratch_context = getattr(
                stones, 'scratch_note', ""
            )

        # If still empty, use a basic fallback
        if not system_prompt:
            module_name = "coding"
            if scratch and hasattr(scratch, 'get'):
                module_name = scratch.get(
                    "project", "module", default="coding"
                )
            elif isinstance(scratch, dict):
                module_name = scratch.get("project", {}).get("module", "coding")
            system_prompt = (
                f"You are a {module_name} agent within ENGRAM OS. "
                f"You have access to tools that can help you complete tasks. "
                f"If a tool can help, call it first. After receiving tool results, "
                f"provide a clear summary of what you found or accomplished. "
                f"After your response, output a writeback block."
            )

        # ADD EXPLICIT WRITEBACK INSTRUCTION (mandatory block format)
        WRITEBACK_INSTRUCTION = '''

REQUIRED: End every response with this exact block:
```writeback
module: [which module you worked on]
status: [done|in_progress|blocked]
files_modified: [list any files you created or changed]
conventions_learned: [any pattern you discovered, or null]
next_focus: [what should be loaded next]
evict: [chunk IDs no longer needed, or []]
```

This block is mandatory. Do not skip it.
Do not add explanation after it.
'''
        system_prompt = system_prompt + WRITEBACK_INSTRUCTION

        # BUILD FULL CONTEXT PROMPT
        context_parts = []

        if system_prompt:
            context_parts.append(
                f"=== SYSTEM ===\n{system_prompt}"
            )

        if scratch_context:
            context_parts.append(
                f"=== PROJECT MAP ===\n{scratch_context}"
            )
        elif scratch:
            try:
                scratch_str = str(scratch)
                if len(scratch_str) < 4000:
                    context_parts.append(
                        f"=== PROJECT MAP ===\n{scratch_str}"
                    )
            except Exception:
                pass

        context_parts.append(
            f"=== TASK ===\n{task_text}"
        )

        full_prompt = "\n\n".join(context_parts)

        # GET TOOLS FROM MCP
        tools = None
        if mcp_client and hasattr(
            mcp_client, 'get_ollama_tool_schemas'
        ):
            try:
                tools = mcp_client.get_ollama_tool_schemas()
            except Exception as e:
                logging.warning(
                    f"[ENGRAM] tool schema failed: {e}"
                )
                tools = None  # Ensure tools is None on failure

        # Wrap mcp_client to track tool calls
        wrapped_mcp = None
        if mcp_client:
            class _ToolTrackingWrapper:
                def __init__(self, mcp):
                    self._mcp = mcp
                def __getattr__(self, name):
                    # Delegate all attributes to underlying mcp
                    return getattr(self._mcp, name)
                def call_tool(self, tool_name, args):
                    # Call the underlying tool
                    if hasattr(self._mcp, 'call_tool'):
                        result = self._mcp.call_tool(tool_name, args)
                    else:
                        result = self._mcp.call_tool_mock(tool_name, args)
                    # Track this tool call
                    _last_tool_calls.append({
                        "name": tool_name,
                        "arguments": args,
                        "result": {
                            "success": result.success if hasattr(result, 'success') else False,
                            "result": result.result if hasattr(result, 'result') else None,
                            "error": result.error if hasattr(result, 'error') else None,
                        },
                    })
                    return result
            wrapped_mcp = _ToolTrackingWrapper(mcp_client)

        # CALL THE LLM DIRECTLY
        from .llm import BaseLLM, Message, MessageRole, OllamaProvider
        from engram.cli._config import load_config
        
        # Load config to get model and Ollama URL
        config_data = load_config()
        model_name = config_data.get('model', 'qwen2.5:14b')
        ollama_url = config_data.get('ollama_url', 'http://localhost:11434')

        # Create LLM with Ollama provider (NOT mock!)
        llm = BaseLLM(provider=OllamaProvider(model=model_name, base_url=ollama_url))

        # Build messages with full context
        messages = [
            Message(role=MessageRole.SYSTEM, content=system_prompt),
            Message(role=MessageRole.USER, content=full_prompt),
        ]
        
        logging.debug(f"[ENGRAM] agent_turn: system_prompt={repr(system_prompt[:100])}")
        logging.debug(f"[ENGRAM] agent_turn: full_prompt={repr(full_prompt[:200])}")
        logging.debug(f"[ENGRAM] agent_turn: tools={len(tools) if tools else 0}, mcp_client={mcp_client is not None}")

        # Call LLM - only pass tools if mcp_client is available
        # Use wrapped_mcp if available to track tool calls
        actual_mcp = wrapped_mcp if wrapped_mcp else mcp_client
        if actual_mcp and tools:
            response = llm.complete(messages, tools=tools, mcp_client=actual_mcp)
            logging.debug(f"[ENGRAM] agent_turn: response.content={repr(response.content[:100] if response.content else '(empty)')}")
            logging.debug(f"[ENGRAM] agent_turn: response.thinking={repr(response.thinking[:100] if response.thinking else 'None')}")
        else:
            response = llm.complete(messages)

        # Extract string from response - use thinking as fallback for qwen3 models
        result = ""
        if hasattr(response, 'content') and response.content:
            result = response.content
        elif hasattr(response, 'thinking') and response.thinking:
            # For qwen3 models, thinking may contain the actual response
            result = response.thinking
        elif hasattr(response, 'text'):
            result = response.text
        elif isinstance(response, str):
            result = response
        else:
            result = str(response)

        # PHASE 1.3: Retry logic for short responses (FAILURE_FIXES)
        from engram.cli._config import load_config
        config_data = load_config()
        min_chars = config_data.get('min_response_chars', 150)
        max_retries = config_data.get('max_retries', 2)
        
        retry_count = 0
        while len(result) < min_chars and retry_count < max_retries:
            logging.warning(
                f"[ENGRAM] agent_turn: Response too short ({len(result)} chars < {min_chars}), "
                f"retrying ({retry_count + 1}/{max_retries})..."
            )
            
            # Retry with explicit instruction for complete response
            retry_messages = messages + [
                Message(role=MessageRole.ASSISTANT, content=result),
                Message(
                    role=MessageRole.USER,
                    content="Please provide a complete, detailed response. Do not truncate. "
                           "Include all requested information with full explanations."
                ),
            ]
            
            response = llm.complete(messages=retry_messages, tools=tools, mcp_client=actual_mcp)
            result = (
                response.content if hasattr(response, 'content') and response.content else
                response.thinking if hasattr(response, 'thinking') and response.thinking else
                response.text if hasattr(response, 'text') else
                str(response)
            )
            retry_count += 1
        
        if len(result) < min_chars:
            logging.warning(
                f"[ENGRAM] agent_turn: Response still short after {max_retries} retries ({len(result)} chars)"
            )

        # PHASE 1.1: Log response time warning if slow
        response_time = time.time() - start_time
        if response_time > 60:
            logging.warning(
                f"[ENGRAM] agent_turn: Slow response {response_time:.1f}s for: {task_text[:50]}..."
            )

        # LOG TO SESSION via scratch
        if scratch is not None and session_path is not None:
            try:
                vram_mb = 0.0
                if db is not None and hasattr(db, 'get_hot_vram_mb'):
                    vram_mb = db.get_hot_vram_mb()

                # Parse writeback from result
                from engram.core.writeback import parse_writeback
                wb = parse_writeback(result)

                # Use scratch.log() if available, otherwise use manual YAML logging
                if hasattr(scratch, 'log'):
                    scratch.log({
                        "task": task_text,
                        "routing_decision": {},  # routing is done in run_command.py, not here
                        "vram_mb": vram_mb,
                        "writeback_parsed": wb is not None,
                        "quality_score": 0.0,
                        "response_time": round(response_time, 2),      # PHASE 1.1
                        "task_complexity": requirements,               # PHASE 1.2
                    })
                    scratch.save(str(session_path))
                else:
                    # Fallback: manual YAML logging (existing behavior)
                    import yaml
                    from datetime import datetime
                    from pathlib import Path

                    session_path_obj = Path(session_path)
                    if session_path_obj.exists():
                        with open(session_path_obj, 'r') as f:
                            session_data = yaml.safe_load(f) or {}
                    else:
                        session_data = {}

                    if 'session_log' not in session_data:
                        session_data['session_log'] = []

                    log_entry = {
                        "ts": datetime.now().isoformat(),
                        "task": task_text[:200],
                        "event": "agent_turn_completed",
                        "response_length": len(result),
                        "response_time": round(response_time, 2),      # PHASE 1.1
                        "task_complexity": requirements,               # PHASE 1.2
                    }
                    session_data['session_log'].append(log_entry)

                    with open(session_path_obj, 'w') as f:
                        yaml.dump(session_data, f, default_flow_style=False)

                    logging.info(f"[ENGRAM] session log saved to {session_path}")
            except Exception as _log_err:
                logging.warning(
                    f"[ENGRAM] session log failed: {_log_err}"
                )

        # Release tool call lock
        _tool_call_lock = False
        return result

    except Exception as e:
        logging.error(
            f"[ENGRAM] agent_turn failed: {e}"
        )
        raise


def get_last_tool_calls() -> list:
    """
    Return the tool calls recorded during the most recent
    agent_turn() execution.

    This is the ONLY public interface to _last_tool_calls.
    Call it IMMEDIATELY after agent_turn() returns in the
    same thread. The list is replaced on the next
    agent_turn() call.

    Returns:
        List of dicts, one per tool call made:
        [
          {
            "name":      str,   # tool name e.g. "run_command"
            "arguments": dict,  # arguments passed to tool
            "result":    dict,  # result returned by tool
          },
          ...
        ]
        Returns [] if no tools were called or if agent_turn()
        has not been called yet in this process.

    Never raises.
    """
    global _last_tool_calls
    return list(_last_tool_calls)   # defensive copy
