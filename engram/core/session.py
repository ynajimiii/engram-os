"""
Session - Session state and lifecycle management.

Phase 01: Scratch Memory
"""

import uuid
import yaml
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .stones import Stone, StoneCollection, MemoryStone


@dataclass
class SessionState:
    """Represents the current state of a session."""
    active: bool = True
    turn_count: int = 0
    last_activity: datetime = field(default_factory=datetime.now)
    context_window: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class Session:
    """
    A session represents a continuous interaction with an agent.
    
    Sessions persist state across multiple turns and provide
    context continuity for conversations.
    """
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    state: SessionState = field(default_factory=SessionState)
    stones: StoneCollection = field(default_factory=StoneCollection)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_message(self, role: str, content: str) -> None:
        """Add a message to the session context."""
        self.state.context_window.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        })
        self.state.turn_count += 1
        self.updated_at = datetime.now()

        # Store as stone for long-term memory - wrapped in error handling
        try:
            stone = MemoryStone(
                content={"role": role, "content": content},
                stone_type="message",
                metadata={"turn": self.state.turn_count},
            )
        except (TypeError, ValueError) as e:
            import logging
            logging.error(
                f"[ENGRAM] session — stone creation failed for message "
                f"role='{role}': {e}. "
                f"Message added to session but not persisted as stone."
            )
            stone = None

        if stone is not None:
            self.stones.add(stone)
    
    def get_context(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get recent context window."""
        if limit is None:
            return self.state.context_window
        return self.state.context_window[-limit:]
    
    def clear_context(self) -> None:
        """Clear the context window."""
        self.state.context_window.clear()
    
    def end(self) -> None:
        """End the session."""
        self.state.active = False
        self.updated_at = datetime.now()
    
    @property
    def is_active(self) -> bool:
        """Check if session is active."""
        return self.state.active
    
    @property
    def turn_count(self) -> int:
        """Get the number of turns in this session."""
        return self.state.turn_count
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize session to dictionary."""
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "state": {
                "active": self.state.active,
                "turn_count": self.state.turn_count,
                "last_activity": self.state.last_activity.isoformat(),
                "context_window": self.state.context_window,
            },
            "stones": self.stones.to_list(),
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Session":
        """Deserialize session from dictionary."""
        session = cls(
            session_id=data["session_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            metadata=data.get("metadata", {}),
        )
        
        state_data = data.get("state", {})
        session.state = SessionState(
            active=state_data.get("active", True),
            turn_count=state_data.get("turn_count", 0),
            last_activity=datetime.fromisoformat(state_data.get("last_activity", datetime.now().isoformat())),
            context_window=state_data.get("context_window", []),
        )
        
        for stone_data in data.get("stones", []):
            session.stones.add(Stone.from_dict(stone_data))
        
        return session


class SessionManager:
    """Manages multiple sessions."""

    def __init__(self, session_dir: Optional[str] = None):
        self.session_dir = Path(session_dir) if session_dir else Path("engram/sessions")
        self._sessions: Dict[str, Session] = {}
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        """Ensure session directory exists."""
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def create_session(self, metadata: Optional[Dict[str, Any]] = None) -> Session:
        """Create a new session."""
        session = Session(metadata=metadata or {})
        self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID."""
        if session_id in self._sessions:
            return self._sessions[session_id]

        # Try to load from disk
        filepath = self.session_dir / f"{session_id}.yaml"
        if filepath.exists():
            with open(filepath) as f:
                data = yaml.safe_load(f)
                session = Session.from_dict(data)
                self._sessions[session_id] = session
                return session

        return None

    def save_session(self, session_id: str) -> bool:
        """Save a session to disk."""
        session = self._sessions.get(session_id)
        if session is None:
            return False

        filepath = self.session_dir / f"{session_id}.yaml"
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                yaml.dump(session.to_dict(), f, default_flow_style=False, allow_unicode=True)
        except Exception as e:
            import logging
            logging.error(
                f"[ENGRAM] session — save_session failed for '{session_id}': {e}. "
                f"Session state is in memory but not persisted to disk."
            )
            return False

        return True

    def close_session(self, session_id: str) -> bool:
        """Close and save a session."""
        session = self.get_session(session_id)
        if session is None:
            return False

        session.end()
        self.save_session(session_id)

        if session_id in self._sessions:
            del self._sessions[session_id]

        return True

    def list_sessions(self) -> List[str]:
        """List all session IDs."""
        in_memory = list(self._sessions.keys())

        # Also check disk
        if self.session_dir.exists():
            on_disk = [f.stem for f in self.session_dir.glob("*.yaml")]
            in_memory = list(set(in_memory + on_disk))

        return in_memory


def new_session(module_name: str, project_name: str, sessions_dir: Optional[str] = None) -> tuple:
    """
    Create a new session for a project.
    
    Args:
        module_name: Name of the module to use
        project_name: Name of the project
        sessions_dir: Optional custom sessions directory
    
    Returns:
        Tuple of (session_path, scratch) where scratch is a Scratch instance
    """
    import uuid
    from engram.core.scratch import Scratch
    
    session_id = f"{project_name}_{uuid.uuid4().hex[:6]}"
    mgr = SessionManager(session_dir=sessions_dir)
    session = mgr.create_session(metadata={
        "project": {"name": project_name, "module": module_name},
        "use_case": module_name,
    })
    
    # Save session
    mgr.save_session(session.session_id)
    session_path = mgr.session_dir / f"{session.session_id}.yaml"

    # Create scratch note
    scratch = Scratch(session_id)
    scratch.set("project_name", project_name)
    scratch.set("project_module", module_name)
    scratch.save()

    return str(session_path), scratch
