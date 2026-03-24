"""
Vector DB - Vector storage and retrieval.

Phase 02: Vector Storage
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import numpy as np


@dataclass
class VectorEntry:
    """An entry in the vector database."""
    id: str
    vector: np.ndarray
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "vector": self.vector.tolist(),
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VectorEntry":
        """Create from dictionary representation."""
        return cls(
            id=data["id"],
            vector=np.array(data["vector"]),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
        )


class VectorDB:
    """
    In-memory vector database with similarity search and tier management.

    Tiers control which entries are considered during context assembly:
      - hot:  Active task context — queried first, capped at max_hot_size
      - warm: Recent sessions / frequently accessed — default landing tier
      - cold: Archived sessions / full history — searched only on demand

    Phase 02 implementation.  Hot/warm/cold promotion was added in Phase 10.
    
    Note: Default dimension (384) matches all-MiniLM-L6-v2 embedder output.
    """

    TIERS = ("hot", "warm", "cold")

    def __init__(self, dimension: int = 384, max_hot_size: int = None):
        from engram.cli._config import load_config
        
        # Default 384 matches embedder output; max_hot_size from config
        self.dimension = dimension
        self.max_hot_size = (
            load_config().get('max_hot_size', 100)
            if max_hot_size is None else max_hot_size
        )
        self._entries: Dict[str, VectorEntry] = {}
        self._tiers: Dict[str, str] = {}  # entry_id -> "hot" | "warm" | "cold"
    
    def insert(self, vector: np.ndarray, metadata: Optional[Dict[str, Any]] = None,
               entry_id: Optional[str] = None, tier: str = "warm") -> str:
        """
        Insert a vector into the database.

        Args:
            vector: The vector to insert
            metadata: Optional metadata to store with the vector
            entry_id: Optional ID (auto-generated if not provided)
            tier: Initial tier — "hot", "warm", or "cold" (default "warm").
                  If not provided explicitly, the value stored under
                  ``metadata["tier"]`` is used as a fallback.

        Returns:
            The ID of the inserted entry
        """
        if vector.shape[0] != self.dimension:
            raise ValueError(f"Vector dimension must be {self.dimension}")

        # Guard against zero-norm vectors
        norm = np.linalg.norm(vector)
        if norm == 0:
            raise ValueError(
                f"[ENGRAM] vector_db — zero-norm vector rejected for chunk_id='{entry_id}'. "
                f"Zero-norm vectors cannot be normalized and produce undefined cosine similarity."
            )

        if entry_id is None:
            # Generate ID from vector hash
            vector_hash = hashlib.sha256(vector.tobytes()).hexdigest()[:12]
            entry_id = f"vec_{vector_hash}"

        # Normalize vector for cosine similarity
        normalized = vector / norm
        
        entry = VectorEntry(
            id=entry_id,
            vector=normalized,
            metadata=metadata or {},
        )
        
        self._entries[entry_id] = entry

        # Resolve tier: explicit arg wins; fall back to metadata key.
        actual_tier = tier
        if tier == "warm" and metadata and "tier" in metadata:
            actual_tier = metadata["tier"]
        if actual_tier not in self.TIERS:
            actual_tier = "warm"
        self._tiers[entry_id] = actual_tier

        return entry_id
    
    def search(self, query_vector: np.ndarray, top_k: int = 5) -> List[Tuple[str, float, Dict[str, Any]]]:
        """
        Search for similar vectors.
        
        Args:
            query_vector: The query vector
            top_k: Number of results to return
        
        Returns:
            List of (id, similarity, metadata) tuples
        """
        if query_vector.shape[0] != self.dimension:
            raise ValueError(f"Vector dimension must be {self.dimension}")
        
        # Normalize query
        normalized = query_vector / np.linalg.norm(query_vector)
        
        # Compute cosine similarities
        similarities = []
        for entry_id, entry in self._entries.items():
            similarity = np.dot(normalized, entry.vector)
            similarities.append((entry_id, float(similarity), entry.metadata))
        
        # Sort by similarity (descending)
        similarities.sort(key=lambda x: x[1], reverse=True)
        
        return similarities[:top_k]
    
    def get(self, entry_id: str) -> Optional[VectorEntry]:
        """Retrieve an entry by ID."""
        return self._entries.get(entry_id)
    
    def delete(self, entry_id: str) -> bool:
        """Delete an entry by ID."""
        if entry_id in self._entries:
            del self._entries[entry_id]
            self._tiers.pop(entry_id, None)
            return True
        return False

    def clear(self) -> None:
        """Clear all entries."""
        self._entries.clear()
        self._tiers.clear()
    
    def __len__(self) -> int:
        return len(self._entries)
    
    def list_entries(self) -> List[str]:
        """List all entry IDs."""
        return list(self._entries.keys())
    
    def filter_by_metadata(self, **kwargs) -> List[VectorEntry]:
        """Filter entries by metadata criteria."""
        results = []
        for entry in self._entries.values():
            match = all(
                entry.metadata.get(k) == v
                for k, v in kwargs.items()
            )
            if match:
                results.append(entry)
        return results

    # ------------------------------------------------------------------
    # Tier management
    # ------------------------------------------------------------------

    def add(
        self,
        chunk_id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        tier: str = "warm",
    ) -> str:
        """
        High-level add method used by the ingestion pipeline.

        Creates a deterministic pseudo-embedding from *text* and stores
        the entry under *chunk_id* in the requested *tier*.

        Args:
            chunk_id: Unique identifier for the chunk
            text: Chunk content (used to derive the embedding)
            metadata: Optional metadata dict
            tier: Destination tier — "hot", "warm", or "cold"

        Returns:
            The stored entry ID (equals chunk_id)
        """
        import hashlib as _hl
        text_hash = _hl.md5(text.encode()).hexdigest()
        seed = int(text_hash[:8], 16)
        rng = np.random.RandomState(seed)
        vector = rng.randn(self.dimension)
        m = {**(metadata or {}), "text": text}
        return self.insert(vector, metadata=m, entry_id=chunk_id, tier=tier)

    def promote(self, entry_id: str, to_tier: str = "hot") -> bool:
        """
        Promote an entry to a higher tier.

        When promoting to hot the oldest hot entries are evicted to warm
        so that the hot tier never exceeds *max_hot_size*.

        Args:
            entry_id: Entry to promote
            to_tier: Target tier (default "hot")

        Returns:
            True if the entry existed and was updated, False otherwise
        """
        if entry_id not in self._entries or to_tier not in self.TIERS:
            return False

        if to_tier == "hot":
            current_hot = [e for e, t in self._tiers.items() if t == "hot"]
            while len(current_hot) >= self.max_hot_size:
                evicted = current_hot.pop(0)
                self._tiers[evicted] = "warm"
                if evicted in self._entries:
                    self._entries[evicted].metadata["tier"] = "warm"

        self._tiers[entry_id] = to_tier
        self._entries[entry_id].metadata["tier"] = to_tier
        return True

    def demote(self, entry_id: str, to_tier: str = "warm") -> bool:
        """
        Demote an entry to a lower tier.

        Args:
            entry_id: Entry to demote
            to_tier: Target tier (default "warm")

        Returns:
            True if the entry existed and was updated, False otherwise
        """
        if entry_id not in self._entries or to_tier not in self.TIERS:
            return False
        self._tiers[entry_id] = to_tier
        self._entries[entry_id].metadata["tier"] = to_tier
        return True

    def get_tier(self, entry_id: str) -> Optional[str]:
        """Return the current tier of an entry, or None if not found."""
        return self._tiers.get(entry_id)

    def set_tier(self, entry_id: str, tier: str) -> bool:
        """Set the tier of an entry directly (no eviction logic)."""
        if entry_id not in self._entries or tier not in self.TIERS:
            return False
        self._tiers[entry_id] = tier
        self._entries[entry_id].metadata["tier"] = tier
        return True

    def search_by_tier(
        self,
        query_vector: np.ndarray,
        tier: str,
        top_k: int = 5,
    ) -> List[Tuple[str, float, Dict[str, Any]]]:
        """
        Search within a single tier only.

        Returns an empty list if the tier contains no entries or the query
        vector has zero norm (instead of raising).
        """
        if not self._entries:
            return []
        if query_vector.shape[0] != self.dimension:
            raise ValueError(f"Vector dimension must be {self.dimension}")
        norm = np.linalg.norm(query_vector)
        if norm == 0:
            return []
        normalized = query_vector / norm
        similarities = []
        for entry_id, entry in self._entries.items():
            if self._tiers.get(entry_id) == tier:
                similarity = np.dot(normalized, entry.vector)
                similarities.append((entry_id, float(similarity), entry.metadata))
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:top_k]

    def search_hot(
        self, query_vector: np.ndarray, top_k: int = 5
    ) -> List[Tuple[str, float, Dict[str, Any]]]:
        """Search only the hot tier."""
        return self.search_by_tier(query_vector, "hot", top_k)

    def search_warm(
        self, query_vector: np.ndarray, top_k: int = 5
    ) -> List[Tuple[str, float, Dict[str, Any]]]:
        """Search only the warm tier."""
        return self.search_by_tier(query_vector, "warm", top_k)

    def search_cold(
        self, query_vector: np.ndarray, top_k: int = 5
    ) -> List[Tuple[str, float, Dict[str, Any]]]:
        """Search only the cold tier."""
        return self.search_by_tier(query_vector, "cold", top_k)

    @property
    def hot_chunks(self) -> List[VectorEntry]:
        """All entries currently in the hot tier."""
        return [
            self._entries[eid]
            for eid, t in self._tiers.items()
            if t == "hot" and eid in self._entries
        ]

    @property
    def warm_chunks(self) -> List[VectorEntry]:
        """All entries currently in the warm tier."""
        return [
            self._entries[eid]
            for eid, t in self._tiers.items()
            if t == "warm" and eid in self._entries
        ]

    @property
    def cold_chunks(self) -> List[VectorEntry]:
        """All entries currently in the cold tier."""
        return [
            self._entries[eid]
            for eid, t in self._tiers.items()
            if t == "cold" and eid in self._entries
        ]

    def to_dict(self) -> Dict[str, Any]:
        """Export database to dictionary (tiers are persisted)."""
        return {
            "dimension": self.dimension,
            "max_hot_size": self.max_hot_size,
            "entries": {k: v.to_dict() for k, v in self._entries.items()},
            "tiers": dict(self._tiers),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VectorDB":
        """Import database from dictionary, restoring tier assignments."""
        db = cls(
            dimension=data["dimension"],
            max_hot_size=data.get("max_hot_size", 100),
        )
        for entry_data in data.get("entries", {}).values():
            entry = VectorEntry.from_dict(entry_data)
            db._entries[entry.id] = entry
        # Restore tiers; fall back to metadata key, then default to warm.
        saved_tiers = data.get("tiers", {})
        for entry_id in db._entries:
            tier = saved_tiers.get(
                entry_id,
                db._entries[entry_id].metadata.get("tier", "warm"),
            )
            if tier not in cls.TIERS:
                tier = "warm"
            db._tiers[entry_id] = tier
        return db


class EmbeddingStore:
    """
    High-level interface for storing and retrieving embeddings.
    
    Wraps VectorDB with text-centric operations.
    """
    
    def __init__(self, vector_db: Optional[VectorDB] = None,
                 dimension: int = 768):
        self.vector_db = vector_db or VectorDB(dimension=dimension)
        self._texts: Dict[str, str] = {}
    
    def add(self, text: str, embedding: np.ndarray,
            metadata: Optional[Dict[str, Any]] = None) -> str:
        """Add a text with its embedding."""
        entry_id = self.vector_db.insert(embedding, metadata)
        self._texts[entry_id] = text
        return entry_id
    
    def search(self, query_embedding: np.ndarray, top_k: int = 5) -> List[Dict[str, Any]]:
        """Search for similar texts."""
        results = []
        for entry_id, similarity, metadata in self.vector_db.search(query_embedding, top_k):
            results.append({
                "id": entry_id,
                "text": self._texts.get(entry_id, ""),
                "similarity": similarity,
                "metadata": metadata,
            })
        return results
    
    def get(self, entry_id: str) -> Optional[Dict[str, Any]]:
        """Get a stored entry."""
        entry = self.vector_db.get(entry_id)
        if entry is None:
            return None
        
        return {
            "id": entry_id,
            "text": self._texts.get(entry_id, ""),
            "embedding": entry.vector,
            "metadata": entry.metadata,
        }
    
    def delete(self, entry_id: str) -> bool:
        """Delete an entry."""
        if entry_id in self._texts:
            del self._texts[entry_id]
        return self.vector_db.delete(entry_id)
