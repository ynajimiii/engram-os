"""
Stones - Immutable memory primitives.

Phase 01: Scratch Memory
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class Stone:
    """
    An immutable unit of memory.
    
    Stones are the fundamental building blocks of Engram memory.
    Once created, they cannot be modified - only referenced or linked.
    """
    content: Any
    stone_type: str = "basic"
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict, compare=False)
    
    def __post_init__(self):
        # Set hash after initialization
        object.__setattr__(self, "_hash", self._compute_hash())
    
    def _compute_hash(self) -> str:
        """Compute a unique hash for this stone."""
        content_str = str(self.content)
        timestamp_str = self.created_at.isoformat()
        combined = f"{content_str}:{timestamp_str}:{self.stone_type}"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]
    
    @property
    def id(self) -> str:
        """Return the stone's unique identifier."""
        return self._hash
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert stone to dictionary representation."""
        return {
            "id": self.id,
            "content": self.content,
            "stone_type": self.stone_type,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Stone":
        """Create a stone from dictionary representation."""
        try:
            created_at = datetime.fromisoformat(data["created_at"])
        except (ValueError, KeyError) as e:
            import logging
            logging.warning(
                f"[ENGRAM] stones — created_at parse failed: {e}. "
                f"Using current UTC time as fallback."
            )
            created_at = datetime.utcnow()
        return cls(
            content=data["content"],
            stone_type=data.get("stone_type", "basic"),
            created_at=created_at,
            metadata=data.get("metadata", {}),
        )


@dataclass(frozen=True)
class MemoryStone(Stone):
    """A stone specifically for memory content."""
    
    def __post_init__(self):
        object.__setattr__(self, "_hash", self._compute_hash())
        # Validate memory stone has required content
        if self.content is None:
            raise ValueError("MemoryStone requires content")


@dataclass(frozen=True)
class LinkStone(Stone):
    """
    A stone that links to other stones.
    
    Creates relationships between memory units without modifying them.
    """
    references: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        object.__setattr__(self, "_hash", self._compute_hash())
        object.__setattr__(self, "stone_type", "link")
    
    def add_reference(self, stone_id: str) -> "LinkStone":
        """Create a new link stone with an additional reference."""
        new_refs = list(self.references) + [stone_id]
        return LinkStone(
            content=self.content,
            references=new_refs,
            metadata=dict(self.metadata),
        )


class StoneCollection:
    """A collection of stones with indexing and retrieval."""
    
    def __init__(self):
        self._stones: Dict[str, Stone] = {}
    
    def add(self, stone: Stone) -> None:
        """Add a stone to the collection."""
        self._stones[stone.id] = stone
    
    def get(self, stone_id: str) -> Optional[Stone]:
        """Retrieve a stone by ID."""
        return self._stones.get(stone_id)
    
    def remove(self, stone_id: str) -> bool:
        """Remove a stone from the collection."""
        if stone_id in self._stones:
            del self._stones[stone_id]
            return True
        return False
    
    def find_by_type(self, stone_type: str) -> List[Stone]:
        """Find all stones of a given type."""
        return [s for s in self._stones.values() if s.stone_type == stone_type]
    
    def find_by_metadata(self, **kwargs) -> List[Stone]:
        """Find stones matching metadata criteria."""
        results = []
        for stone in self._stones.values():
            match = all(
                stone.metadata.get(k) == v 
                for k, v in kwargs.items()
            )
            if match:
                results.append(stone)
        return results
    
    def __len__(self) -> int:
        return len(self._stones)
    
    def __iter__(self):
        return iter(self._stones.values())
    
    def to_list(self) -> List[Dict[str, Any]]:
        """Export all stones as list of dictionaries."""
        return [s.to_dict() for s in self._stones.values()]
