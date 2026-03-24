"""
Writeback - Memory persistence and write operations.

Phase 06: Agent Core
"""

import json
import yaml
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .stones import Stone, MemoryStone, StoneCollection
from .session import Session


@dataclass
class WriteOperation:
    """A pending write operation."""
    operation: str  # create, update, delete
    target: str  # stone_id, session_id, etc.
    data: Optional[Dict[str, Any]] = None
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WriteResult:
    """Result of a write operation."""
    success: bool
    operation: str
    target: str
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class WriteStrategy(ABC):
    """Abstract base class for write strategies."""
    
    @abstractmethod
    def execute(self, op: WriteOperation) -> WriteResult:
        """Execute a write operation."""
        pass
    
    @abstractmethod
    def batch_execute(self, operations: List[WriteOperation]) -> List[WriteResult]:
        """Execute multiple write operations."""
        pass


class ImmediateWriteStrategy(WriteStrategy):
    """Writes are executed immediately."""
    
    def __init__(self, storage: "WriteStorage"):
        self.storage = storage
    
    def execute(self, op: WriteOperation) -> WriteResult:
        """Execute immediately."""
        return self.storage._execute_operation(op)
    
    def batch_execute(self, operations: List[WriteOperation]) -> List[WriteResult]:
        """Execute each operation immediately."""
        return [self.execute(op) for op in operations]


class BatchedWriteStrategy(WriteStrategy):
    """Writes are batched and flushed periodically."""
    
    def __init__(self, storage: "WriteStorage", batch_size: int = 10):
        self.storage = storage
        self.batch_size = batch_size
        self._pending: List[WriteOperation] = []
    
    def execute(self, op: WriteOperation) -> WriteResult:
        """Add to pending batch."""
        self._pending.append(op)
        
        if len(self._pending) >= self.batch_size:
            self.flush()
        
        return WriteResult(
            success=True,
            operation=op.operation,
            target=op.target,
            metadata={"queued": True},
        )
    
    def batch_execute(self, operations: List[WriteOperation]) -> List[WriteResult]:
        """Add operations to pending batch."""
        self._pending.extend(operations)
        
        return [
            WriteResult(success=True, operation=op.operation, target=op.target, metadata={"queued": True})
            for op in operations
        ]
    
    def flush(self) -> List[WriteResult]:
        """Flush pending operations."""
        results = [self.storage._execute_operation(op) for op in self._pending]
        self._pending.clear()
        return results


class WriteStorage:
    """
    Storage backend for write operations.
    
    Phase 06: File-based storage with stone and session support.
    """
    
    def __init__(self, base_path: Optional[Union[str, Path]] = None):
        self.base_path = Path(base_path) if base_path else Path("engram_data")
        self._strategy: WriteStrategy = ImmediateWriteStrategy(self)
        self._stones: Dict[str, Stone] = {}
        self._sessions: Dict[str, Session] = {}
        
        self._ensure_dirs()
    
    def _ensure_dirs(self) -> None:
        """Ensure storage directories exist."""
        self.base_path.mkdir(parents=True, exist_ok=True)
        (self.base_path / "stones").mkdir(exist_ok=True)
        (self.base_path / "sessions").mkdir(exist_ok=True)
    
    def set_strategy(self, strategy: WriteStrategy) -> None:
        """Set the write strategy."""
        self._strategy = strategy
    
    def write_stone(self, stone: Stone) -> WriteResult:
        """Write a stone to storage."""
        op = WriteOperation(
            operation="create",
            target=f"stone:{stone.id}",
            data=stone.to_dict(),
        )
        result = self._strategy.execute(op)
        
        if result.success:
            self._stones[stone.id] = stone
        
        return result
    
    def read_stone(self, stone_id: str) -> Optional[Stone]:
        """Read a stone from storage."""
        if stone_id in self._stones:
            return self._stones[stone_id]
        
        filepath = self.base_path / "stones" / f"{stone_id}.json"
        if filepath.exists():
            with open(filepath) as f:
                data = json.load(f)
                stone = Stone.from_dict(data)
                self._stones[stone_id] = stone
                return stone
        
        return None
    
    def delete_stone(self, stone_id: str) -> WriteResult:
        """Delete a stone from storage."""
        op = WriteOperation(
            operation="delete",
            target=f"stone:{stone_id}",
        )
        result = self._strategy.execute(op)
        
        if result.success and stone_id in self._stones:
            del self._stones[stone_id]
        
        return result
    
    def write_session(self, session: Session) -> WriteResult:
        """Write a session to storage."""
        op = WriteOperation(
            operation="create",
            target=f"session:{session.session_id}",
            data=session.to_dict(),
        )
        result = self._strategy.execute(op)
        
        if result.success:
            self._sessions[session.session_id] = session
            self._persist_session(session)
        
        return result
    
    def read_session(self, session_id: str) -> Optional[Session]:
        """Read a session from storage."""
        if session_id in self._sessions:
            return self._sessions[session_id]
        
        filepath = self.base_path / "sessions" / f"{session_id}.yaml"
        if filepath.exists():
            with open(filepath) as f:
                data = yaml.safe_load(f)
                session = Session.from_dict(data)
                self._sessions[session_id] = session
                return session
        
        return None
    
    def _persist_session(self, session: Session) -> None:
        """Persist session to disk."""
        filepath = self.base_path / "sessions" / f"{session.session_id}.yaml"
        with open(filepath, "w") as f:
            yaml.dump(session.to_dict(), f)
    
    def _execute_operation(self, op: WriteOperation) -> WriteResult:
        """Execute a single write operation."""
        try:
            if op.target.startswith("stone:"):
                return self._execute_stone_op(op)
            elif op.target.startswith("session:"):
                return self._execute_session_op(op)
            else:
                return WriteResult(
                    success=False,
                    operation=op.operation,
                    target=op.target,
                    error=f"Unknown target type: {op.target}",
                )
        except Exception as e:
            return WriteResult(
                success=False,
                operation=op.operation,
                target=op.target,
                error=str(e),
            )
    
    def _execute_stone_op(self, op: WriteOperation) -> WriteResult:
        """Execute a stone operation."""
        stone_id = op.target.replace("stone:", "")

        if op.operation == "create":
            # Validate schema before write
            REQUIRED_FIELDS = {"content", "stone_type"}
            missing = REQUIRED_FIELDS - set(op.data.keys()) if op.data else REQUIRED_FIELDS
            if missing:
                return WriteResult(
                    success=False,
                    operation=op.operation,
                    target=op.target,
                    error=f"Missing required fields: {missing}",
                )

            if not isinstance(op.data.get("content"), (str, dict, list)):
                return WriteResult(
                    success=False,
                    operation=op.operation,
                    target=op.target,
                    error=f"content must be str/dict/list, got {type(op.data.get('content')).__name__}",
                )

            filepath = self.base_path / "stones" / f"{stone_id}.json"
            with open(filepath, "w") as f:
                json.dump(op.data, f, indent=2)

            return WriteResult(
                success=True,
                operation=op.operation,
                target=op.target,
                metadata={"path": str(filepath)},
            )
        
        elif op.operation == "delete":
            filepath = self.base_path / "stones" / f"{stone_id}.json"
            if filepath.exists():
                filepath.unlink()
            
            return WriteResult(
                success=True,
                operation=op.operation,
                target=op.target,
            )
        
        return WriteResult(
            success=False,
            operation=op.operation,
            target=op.target,
            error=f"Unknown operation: {op.operation}",
        )
    
    def _execute_session_op(self, op: WriteOperation) -> WriteResult:
        """Execute a session operation."""
        session_id = op.target.replace("session:", "")
        
        if op.operation == "create":
            self._persist_session(Session.from_dict(op.data))
            
            return WriteResult(
                success=True,
                operation=op.operation,
                target=op.target,
            )
        
        return WriteResult(
            success=False,
            operation=op.operation,
            target=op.target,
            error=f"Unknown operation: {op.operation}",
        )


class WritebackManager:
    """
    Manages writeback operations for agent memory.
    
    Coordinates between agent actions and persistent storage.
    """
    
    def __init__(self, storage: Optional[WriteStorage] = None):
        self.storage = storage or WriteStorage()
        self._pending: List[WriteOperation] = []
        self._history: List[WriteResult] = []
    
    def queue_stone(self, stone: Stone) -> None:
        """Queue a stone for writeback."""
        self._pending.append(WriteOperation(
            operation="create",
            target=f"stone:{stone.id}",
            data=stone.to_dict(),
        ))
    
    def queue_session(self, session: Session) -> None:
        """Queue a session for writeback."""
        self._pending.append(WriteOperation(
            operation="create",
            target=f"session:{session.session_id}",
            data=session.to_dict(),
        ))
    
    def flush(self) -> List[WriteResult]:
        """Flush all pending writebacks."""
        results = []
        for op in self._pending:
            result = self.storage._strategy.execute(op)
            results.append(result)
            self._history.append(result)
        
        self._pending.clear()
        return results
    
    def get_history(self) -> List[WriteResult]:
        """Get writeback history."""
        return list(self._history)

    def clear_history(self) -> None:
        """Clear writeback history."""
        self._history.clear()


def parse_writeback(response: str) -> Optional[Dict]:
    """
    Extract and parse the writeback block from
    model response. Supports both fenced block
    and plain WRITEBACK: formats.
    
    Args:
        response: Model response text
        
    Returns:
        Parsed writeback dict or None if not found
    """
    import re
    import yaml
    import logging

    if not response:
        return None

    # PRIMARY: fenced writeback block
    # Matches ```writeback ... ```
    fenced_pattern = (
        r'`{3}writeback\s*\n(.*?)`{3}'
    )
    match = re.search(
        fenced_pattern, response, re.DOTALL | re.IGNORECASE
    )

    if match:
        try:
            parsed = yaml.safe_load(match.group(1))
            if isinstance(parsed, dict):
                return parsed
        except yaml.YAMLError as e:
            logging.warning(
                f"[ENGRAM] writeback YAML parse error: {e}"
            )

    # SECONDARY: plain WRITEBACK: block (fallback)
    plain_pattern = r'WRITEBACK:\s*\n((?:  .*\n?)*)'
    match = re.search(plain_pattern, response, re.MULTILINE)

    if match:
        result = {}
        for line in match.group(1).strip().split('\n'):
            line = line.strip()
            if ':' in line:
                key, _, value = line.partition(':')
                result[key.strip().lower()] = value.strip()
        if result:
            return result

    # TERTIARY: JSON block fallback
    json_pattern = r'```json\s*\n(.*?)```'
    match = re.search(
        json_pattern, response, re.DOTALL | re.IGNORECASE
    )
    if match:
        try:
            import json
            parsed = json.loads(match.group(1))
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    return None


def apply_writeback(
    wb: dict,
    scratch,
    session_path: str
) -> list:
    """
    Apply a parsed writeback block to the scratch note.
    Returns list of chunk IDs to evict.
    Called by orchestrator after agent_turn().
    """
    import logging
    if not wb:
        return []

    evict_ids = []
    try:
        module = wb.get("module")
        status = wb.get("status")

        # Update module status if scratch supports it
        if module and status and scratch and hasattr(scratch, 'set'):
            try:
                scratch.set(
                    status, "modules", module, "status"
                )
            except Exception:
                pass

        # Update active task next focus
        next_focus = wb.get("next_focus")
        if next_focus and hasattr(scratch, 'set'):
            try:
                scratch.set(
                    next_focus, "active_task", "objective"
                )
            except Exception:
                pass

        # Store conventions learned
        conv = wb.get("conventions_learned")
        if conv and hasattr(scratch, 'set'):
            try:
                scratch.set(conv, "conventions", "learned")
            except Exception:
                pass

        # Collect evict IDs
        evict = wb.get("evict", [])
        if isinstance(evict, list):
            evict_ids = evict
        elif isinstance(evict, str) and evict:
            evict_ids = [evict]

        # Save scratch note
        if session_path and hasattr(scratch, 'save'):
            scratch.save(str(session_path))
        elif session_path:
            # Fallback for ScratchProxy or other types
            try:
                scratch.save(str(session_path))
            except Exception as e:
                logging.warning(
                    f"[ENGRAM] apply_writeback save failed: {e}"
                )

    except Exception as e:
        logging.error(
            f"[ENGRAM] apply_writeback error: {e}"
        )

    return evict_ids
