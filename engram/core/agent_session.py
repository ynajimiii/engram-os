"""
Agent Session - Multi-agent session management.

Phase 07: Multi-Agent
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .agent import Agent, AgentConfig
from .session import Session, SessionManager
from .llm import Message, MessageRole, LLMResponse


@dataclass
class Participant:
    """A participant in a multi-agent session."""
    agent: Agent
    role: str
    active: bool = True
    message_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def name(self) -> str:
        return self.agent.name


@dataclass
class TurnRecord:
    """Record of a turn in a multi-agent session."""
    turn_number: int
    speaker: str
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentSessionState:
    """State of a multi-agent session."""
    active: bool = True
    current_turn: int = 0
    current_speaker: Optional[str] = None
    turn_order: List[str] = field(default_factory=list)
    records: List[TurnRecord] = field(default_factory=list)


class AgentSession:
    """
    Manages a session with multiple participating agents.
    
    Phase 07: Multi-agent coordination with turn-based interaction.
    """
    
    def __init__(self, session_id: Optional[str] = None,
                 session_manager: Optional[SessionManager] = None):
        self.session_id = session_id or str(uuid.uuid4())[:12]
        self._session_manager = session_manager or SessionManager()
        
        self._participants: Dict[str, Participant] = {}
        self._state = AgentSessionState()
        self._session: Optional[Session] = None
        
        self._moderator: Optional[Agent] = None
        self._auto_moderate: bool = True
    
    def add_participant(self, agent: Agent, role: str,
                        metadata: Optional[Dict[str, Any]] = None) -> "AgentSession":
        """
        Add an agent as a participant.
        
        Args:
            agent: The agent to add
            role: The agent's role in the session
            metadata: Optional metadata
        
        Returns:
            Self for chaining
        """
        participant = Participant(
            agent=agent,
            role=role,
            metadata=metadata or {},
        )
        self._participants[agent.id] = participant
        self._state.turn_order.append(agent.id)
        
        return self
    
    def remove_participant(self, agent_id: str) -> bool:
        """Remove a participant from the session."""
        if agent_id in self._participants:
            self._participants[agent_id].active = False
            del self._participants[agent_id]
            
            if agent_id in self._state.turn_order:
                self._state.turn_order.remove(agent_id)
            
            return True
        return False
    
    def set_moderator(self, agent: Agent) -> None:
        """Set a moderator agent."""
        self._moderator = agent
        self._auto_moderate = True
    
    def disable_moderation(self) -> None:
        """Disable automatic moderation."""
        self._auto_moderate = False
    
    def start(self, metadata: Optional[Dict[str, Any]] = None) -> "AgentSession":
        """Start the session."""
        self._session = self._session_manager.create_session(metadata={
            "type": "multi_agent",
            "participants": [p.name for p in self._participants.values()],
            **(metadata or {}),
        })
        self._state.active = True
        
        return self
    
    def end(self) -> Optional[Session]:
        """End the session."""
        if self._session is None:
            return None
        
        self._session.end()
        self._session_manager.save_session(self._session.session_id)
        self._state.active = False
        
        return self._session
    
    def run_turn(self, speaker_id: Optional[str] = None,
                 user_input: Optional[str] = None) -> Optional[TurnRecord]:
        """
        Run a single turn in the session.

        Args:
            speaker_id: ID of the speaking agent (auto-selected if None)
            user_input: Optional user input to include

        Returns:
            TurnRecord of the turn, or None if no agent spoke
        """
        if not self._state.active:
            return None

        # Determine speaker
        if speaker_id is None:
            speaker_id = self._get_next_speaker()

        if speaker_id not in self._participants:
            return None

        participant = self._participants[speaker_id]
        
        # Check if participant is still active
        if not participant.active:
            import logging
            logging.info(
                f"[ENGRAM] agent_session — turn skipped: "
                f"participant '{speaker_id}' is not active."
            )
            return None

        # Build context for the agent
        context = self._build_agent_context(participant, user_input)
        
        # Get response from agent
        response = participant.agent.chat(context)
        
        # Record the turn
        self._state.current_turn += 1
        self._state.current_speaker = participant.name
        
        record = TurnRecord(
            turn_number=self._state.current_turn,
            speaker=participant.name,
            message=response.content,
            metadata={"role": participant.role},
        )
        self._state.records.append(record)
        participant.message_count += 1
        
        # Record in session
        if self._session:
            self._session.add_message(participant.name, response.content)
        
        return record
    
    def run_conversation(self, turns: int, 
                         user_input: Optional[str] = None) -> List[TurnRecord]:
        """
        Run a multi-turn conversation.
        
        Args:
            turns: Number of turns to run
            user_input: Optional initial user input
        
        Returns:
            List of TurnRecords
        """
        records = []
        
        # Initial user input if provided
        initial_context = user_input
        
        for i in range(turns):
            if not self._state.active:
                break
            
            record = self.run_turn(user_input=initial_context)
            if record:
                records.append(record)
            
            # Only first turn gets user input
            initial_context = None
        
        return records
    
    def _get_next_speaker(self) -> Optional[str]:
        """Get the next speaker in turn order."""
        if not self._state.turn_order:
            return None
        
        # Simple round-robin
        current_index = self._state.current_turn % len(self._state.turn_order)
        return self._state.turn_order[current_index]
    
    def _build_agent_context(self, participant: Participant,
                             user_input: Optional[str] = None) -> str:
        """Build context for an agent's turn."""
        context_parts = []
        
        # Role context
        context_parts.append(f"Your role: {participant.role}")
        
        # Conversation history
        if self._state.records:
            history = "\n".join(
                f"{r.speaker}: {r.message}"
                for r in self._state.records[-5:]  # Last 5 turns
            )
            context_parts.append(f"Conversation so far:\n{history}")
        
        # User input
        if user_input:
            context_parts.append(f"User input: {user_input}")
        
        return "\n\n".join(context_parts)
    
    def get_participants(self) -> List[Dict[str, Any]]:
        """Get list of participants."""
        return [
            {
                "name": p.name,
                "role": p.role,
                "active": p.active,
                "message_count": p.message_count,
            }
            for p in self._participants.values()
        ]
    
    def get_state(self) -> Dict[str, Any]:
        """Get session state."""
        return {
            "session_id": self.session_id,
            "active": self._state.active,
            "current_turn": self._state.current_turn,
            "current_speaker": self._state.current_speaker,
            "participant_count": len(self._participants),
            "records_count": len(self._state.records),
        }
    
    def get_transcript(self) -> str:
        """Get full transcript of the session."""
        return "\n".join(
            f"{r.speaker}: {r.message}"
            for r in self._state.records
        )


class MultiAgentCoordinator:
    """
    Coordinates multiple agent sessions.
    
    Phase 07: Basic coordination - future phases may add
    more sophisticated orchestration.
    """
    
    def __init__(self):
        self._sessions: Dict[str, AgentSession] = {}
    
    def create_session(self, session_id: Optional[str] = None) -> AgentSession:
        """Create a new agent session."""
        session = AgentSession(session_id=session_id)
        self._sessions[session.session_id] = session
        return session
    
    def get_session(self, session_id: str) -> Optional[AgentSession]:
        """Get a session by ID."""
        return self._sessions.get(session_id)
    
    def end_session(self, session_id: str) -> bool:
        """End a session."""
        session = self.get_session(session_id)
        if session is None:
            return False
        
        session.end()
        del self._sessions[session_id]
        return True
    
    def list_sessions(self) -> List[str]:
        """List all session IDs."""
        return list(self._sessions.keys())
    
    def get_stats(self) -> Dict[str, Any]:
        """Get coordinator statistics."""
        return {
            "active_sessions": len(self._sessions),
            "sessions": {
                sid: s.get_state()
                for sid, s in self._sessions.items()
            },
        }
