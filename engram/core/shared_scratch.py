"""
Shared Scratch - Collaborative workspace for multi-agent sessions.

Phase 07: Multi-Agent
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

from .scratch import Scratch, ScratchEntry


@dataclass
class SharedEntry:
    """An entry in the shared scratch space."""
    key: str
    value: Any
    owner: str  # Agent ID that created this entry
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    access_level: str = "read-write"  # read-write, read-only, owner-only
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkspaceState:
    """State of a shared workspace."""
    name: str
    created_at: datetime = field(default_factory=datetime.now)
    active_agents: Set[str] = field(default_factory=set)
    entry_count: int = 0
    last_activity: datetime = field(default_factory=datetime.now)


class SharedScratch:
    """
    Shared workspace for multi-agent collaboration.
    
    Provides a common space where agents can read/write data,
    with access control and change tracking.
    """
    
    def __init__(self, name: Optional[str] = None,
                 owner_id: Optional[str] = None):
        self.name = name or f"workspace_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.owner_id = owner_id
        self._entries: Dict[str, SharedEntry] = {}
        self._active_agents: Set[str] = set()
        self._lock = threading.RLock()
        self._subscribers: List[Callable[[str, Any], None]] = []
        
        self._state = WorkspaceState(name=self.name)
    
    def join(self, agent_id: str) -> None:
        """Register an agent as active in this workspace."""
        with self._lock:
            self._active_agents.add(agent_id)
            self._state.active_agents.add(agent_id)
            self._state.last_activity = datetime.now()
    
    def leave(self, agent_id: str) -> None:
        """Remove an agent from active participants."""
        with self._lock:
            self._active_agents.discard(agent_id)
            self._state.active_agents.discard(agent_id)
    
    def write(self, key: str, value: Any, agent_id: str,
              access_level: str = "read-write",
              metadata: Optional[Dict[str, Any]] = None,
              overwrite: bool = True) -> SharedEntry:
        """
        Write a value to the shared space.

        Args:
            key: The key to store under
            value: The value to store
            agent_id: ID of the writing agent
            access_level: Access control level
            metadata: Optional metadata
            overwrite: If False, reject write when key exists

        Returns:
            The created/updated SharedEntry
        """
        with self._lock:
            now = datetime.now()

            if key in self._entries:
                existing = self._entries[key]

                # Check access
                if not self._can_write(existing, agent_id):
                    raise PermissionError(
                        f"Agent {agent_id} cannot write to {key}"
                    )

                # Check overwrite permission
                if not overwrite:
                    import logging
                    logging.warning(
                        f"[ENGRAM] shared_scratch — write rejected: key '{key}' "
                        f"already exists and overwrite=False. Agent: {agent_id}"
                    )
                    # Return existing entry without modifying
                    return existing

                # Log overwrite for debugging
                import logging
                logging.debug(
                    f"[ENGRAM] shared_scratch — key '{key}' overwritten "
                    f"by agent '{agent_id}'. Previous value type: {type(existing.value).__name__}"
                )

                existing.value = value
                existing.updated_at = now
                existing.metadata.update(metadata or {})
                entry = existing
            else:
                entry = SharedEntry(
                    key=key,
                    value=value,
                    owner=agent_id,
                    access_level=access_level,
                    metadata=metadata or {},
                )
                self._entries[key] = entry
                self._state.entry_count += 1
            
            self._state.last_activity = now
            self._notify_subscribers("write", {"key": key, "agent_id": agent_id})
            
            return entry
    
    def read(self, key: str, agent_id: str) -> Optional[Any]:
        """
        Read a value from the shared space.
        
        Args:
            key: The key to read
            agent_id: ID of the reading agent
        
        Returns:
            The value, or None if not found/access denied
        """
        with self._lock:
            entry = self._entries.get(key)
            
            if entry is None:
                return None
            
            if not self._can_read(entry, agent_id):
                raise PermissionError(
                    f"Agent {agent_id} cannot read {key}"
                )
            
            return entry.value
    
    def delete(self, key: str, agent_id: str) -> bool:
        """
        Delete a value from the shared space.
        
        Args:
            key: The key to delete
            agent_id: ID of the deleting agent
        
        Returns:
            True if deleted, False if not found
        """
        with self._lock:
            entry = self._entries.get(key)
            
            if entry is None:
                return False
            
            # Only owner or workspace owner can delete
            if agent_id != entry.owner and agent_id != self.owner_id:
                raise PermissionError(
                    f"Agent {agent_id} cannot delete {key}"
                )
            
            del self._entries[key]
            self._state.entry_count -= 1
            self._state.last_activity = datetime.now()
            self._notify_subscribers("delete", {"key": key, "agent_id": agent_id})
            
            return True
    
    def keys(self, agent_id: str) -> List[str]:
        """List all readable keys for an agent."""
        with self._lock:
            return [
                k for k, entry in self._entries.items()
                if self._can_read(entry, agent_id)
            ]
    
    def get_entry(self, key: str) -> Optional[SharedEntry]:
        """Get the full entry (metadata included)."""
        return self._entries.get(key)
    
    def clear(self, agent_id: Optional[str] = None) -> None:
        """
        Clear entries from the workspace.
        
        Args:
            agent_id: If provided, only clear entries owned by this agent
        """
        with self._lock:
            if agent_id:
                # Only clear agent's own entries
                self._entries = {
                    k: v for k, v in self._entries.items()
                    if v.owner != agent_id
                }
            else:
                # Clear all (only owner can do this)
                self._entries.clear()
            
            self._state.entry_count = len(self._entries)
            self._state.last_activity = datetime.now()
    
    def subscribe(self, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        """Subscribe to workspace changes."""
        self._subscribers.append(callback)
    
    def unsubscribe(self, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        """Unsubscribe from workspace changes."""
        if callback in self._subscribers:
            self._subscribers.remove(callback)
    
    def _can_read(self, entry: SharedEntry, agent_id: str) -> bool:
        """Check if an agent can read an entry."""
        if entry.access_level == "read-write":
            return True
        elif entry.access_level == "read-only":
            return True
        elif entry.access_level == "owner-only":
            return agent_id == entry.owner or agent_id == self.owner_id
        return False
    
    def _can_write(self, entry: SharedEntry, agent_id: str) -> bool:
        """Check if an agent can write to an entry."""
        if entry.access_level == "read-write":
            return True
        elif entry.access_level == "owner-only":
            return agent_id == entry.owner or agent_id == self.owner_id
        return False
    
    def _notify_subscribers(self, event: str, data: Dict[str, Any]) -> None:
        """Notify subscribers of a change."""
        for callback in self._subscribers:
            try:
                callback(event, data)
            except Exception:
                pass  # Don't let subscriber errors break the workspace
    
    def get_state(self) -> WorkspaceState:
        """Get the current workspace state."""
        return WorkspaceState(
            name=self._state.name,
            created_at=self._state.created_at,
            active_agents=set(self._state.active_agents),
            entry_count=self._state.entry_count,
            last_activity=self._state.last_activity,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Export workspace to dictionary."""
        return {
            "name": self.name,
            "owner_id": self.owner_id,
            "entries": {
                k: {
                    "value": v.value,
                    "owner": v.owner,
                    "access_level": v.access_level,
                    "metadata": v.metadata,
                }
                for k, v in self._entries.items()
            },
            "active_agents": list(self._active_agents),
            "state": {
                "entry_count": self._state.entry_count,
                "last_activity": self._state.last_activity.isoformat(),
            },
        }


class WorkspaceManager:
    """
    Manages multiple shared workspaces.
    
    Phase 07: Basic workspace management for multi-agent sessions.
    """
    
    def __init__(self):
        self._workspaces: Dict[str, SharedScratch] = {}
        self._agent_workspaces: Dict[str, Set[str]] = {}  # agent_id -> workspace names
    
    def create_workspace(self, name: Optional[str] = None,
                         owner_id: Optional[str] = None) -> SharedScratch:
        """Create a new workspace."""
        workspace = SharedScratch(name=name, owner_id=owner_id)
        self._workspaces[workspace.name] = workspace
        
        if owner_id:
            if owner_id not in self._agent_workspaces:
                self._agent_workspaces[owner_id] = set()
            self._agent_workspaces[owner_id].add(workspace.name)
        
        return workspace
    
    def get_workspace(self, name: str) -> Optional[SharedScratch]:
        """Get a workspace by name."""
        return self._workspaces.get(name)
    
    def delete_workspace(self, name: str) -> bool:
        """Delete a workspace."""
        if name not in self._workspaces:
            return False
        
        del self._workspaces[name]
        
        # Remove from agent mappings
        for agent_id, workspaces in self._agent_workspaces.items():
            workspaces.discard(name)
        
        return True
    
    def join_workspace(self, workspace_name: str, agent_id: str) -> bool:
        """Join an agent to a workspace."""
        workspace = self.get_workspace(workspace_name)
        if workspace is None:
            return False
        
        workspace.join(agent_id)
        
        if agent_id not in self._agent_workspaces:
            self._agent_workspaces[agent_id] = set()
        self._agent_workspaces[agent_id].add(workspace_name)
        
        return True
    
    def get_agent_workspaces(self, agent_id: str) -> List[str]:
        """Get all workspaces an agent is part of."""
        return list(self._agent_workspaces.get(agent_id, set()))
    
    def list_workspaces(self) -> List[str]:
        """List all workspace names."""
        return list(self._workspaces.keys())
