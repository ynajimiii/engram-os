"""
Tests for vector_db.py - Vector storage and retrieval.

Phase 02: Vector Storage
"""

import pytest
import numpy as np
from engram.core.vector_db import VectorDB, VectorEntry, EmbeddingStore


class TestVectorDB:
    """Tests for VectorDB class."""

    def test_vector_db_creation(self):
        """Test creating a vector database."""
        db = VectorDB(dimension=128)
        
        assert db.dimension == 128
        assert len(db) == 0

    def test_vector_db_insert(self):
        """Test inserting a vector."""
        db = VectorDB(dimension=3)
        vector = np.array([1.0, 2.0, 3.0])
        
        entry_id = db.insert(vector)
        
        assert entry_id is not None
        assert len(db) == 1

    def test_vector_db_insert_custom_id(self):
        """Test inserting with custom ID."""
        db = VectorDB(dimension=3)
        vector = np.array([1.0, 2.0, 3.0])
        
        entry_id = db.insert(vector, entry_id="custom_id")
        
        assert entry_id == "custom_id"

    def test_vector_db_insert_wrong_dimension(self):
        """Test inserting vector with wrong dimension."""
        db = VectorDB(dimension=3)
        vector = np.array([1.0, 2.0])  # Wrong dimension
        
        with pytest.raises(ValueError):
            db.insert(vector)

    def test_vector_db_search(self):
        """Test searching for similar vectors."""
        db = VectorDB(dimension=3)
        
        # Insert vectors
        db.insert(np.array([1.0, 0.0, 0.0]), metadata={"label": "a"})
        db.insert(np.array([0.0, 1.0, 0.0]), metadata={"label": "b"})
        db.insert(np.array([0.0, 0.0, 1.0]), metadata={"label": "c"})
        
        # Search
        query = np.array([1.0, 0.0, 0.0])
        results = db.search(query, top_k=2)
        
        assert len(results) == 2
        # First result should be the most similar
        assert results[0][1] > results[1][1]  # Similarity scores

    def test_vector_db_search_returns_metadata(self):
        """Test that search returns metadata."""
        db = VectorDB(dimension=3)
        vector = np.array([1.0, 0.0, 0.0])
        
        db.insert(vector, metadata={"label": "test", "value": 42})
        
        results = db.search(vector, top_k=1)
        
        assert results[0][2] == {"label": "test", "value": 42}

    def test_vector_db_get(self):
        """Test retrieving an entry by ID."""
        db = VectorDB(dimension=3)
        vector = np.array([1.0, 2.0, 3.0])
        
        entry_id = db.insert(vector, metadata={"test": True})
        
        entry = db.get(entry_id)
        
        assert entry is not None
        assert entry.id == entry_id
        assert entry.metadata == {"test": True}

    def test_vector_db_get_not_found(self):
        """Test getting non-existent entry."""
        db = VectorDB(dimension=3)
        
        entry = db.get("nonexistent")
        
        assert entry is None

    def test_vector_db_delete(self):
        """Test deleting an entry."""
        db = VectorDB(dimension=3)
        vector = np.array([1.0, 0.0, 0.0])
        
        entry_id = db.insert(vector)
        
        assert db.delete(entry_id) is True
        assert len(db) == 0
        assert db.delete(entry_id) is False

    def test_vector_db_clear(self):
        """Test clearing all entries."""
        db = VectorDB(dimension=3)
        
        db.insert(np.array([1.0, 0.0, 0.0]))
        db.insert(np.array([0.0, 1.0, 0.0]))
        
        db.clear()
        
        assert len(db) == 0

    def test_vector_db_list_entries(self):
        """Test listing all entry IDs."""
        db = VectorDB(dimension=3)
        
        id1 = db.insert(np.array([1.0, 0.0, 0.0]))
        id2 = db.insert(np.array([0.0, 1.0, 0.0]))
        
        entries = db.list_entries()
        
        assert id1 in entries
        assert id2 in entries

    def test_vector_db_filter_by_metadata(self):
        """Test filtering entries by metadata."""
        db = VectorDB(dimension=3)
        
        db.insert(np.array([1.0, 0.0, 0.0]), metadata={"type": "A", "value": 1})
        db.insert(np.array([0.0, 1.0, 0.0]), metadata={"type": "B", "value": 2})
        db.insert(np.array([0.0, 0.0, 1.0]), metadata={"type": "A", "value": 3})
        
        results = db.filter_by_metadata(type="A")
        
        assert len(results) == 2
        assert all(e.metadata["type"] == "A" for e in results)

    def test_vector_db_to_dict(self):
        """Test exporting to dictionary."""
        db = VectorDB(dimension=3)
        db.insert(np.array([1.0, 0.0, 0.0]), metadata={"test": True})
        
        data = db.to_dict()
        
        assert data["dimension"] == 3
        assert len(data["entries"]) == 1

    def test_vector_db_from_dict(self):
        """Test importing from dictionary."""
        data = {
            "dimension": 3,
            "entries": {
                "test_id": {
                    "id": "test_id",
                    "vector": [1.0, 0.0, 0.0],
                    "metadata": {"test": True},
                    "created_at": "2024-01-01T00:00:00",
                }
            },
        }
        
        db = VectorDB.from_dict(data)
        
        assert db.dimension == 3
        assert len(db) == 1


class TestEmbeddingStore:
    """Tests for EmbeddingStore class."""

    def test_embedding_store_creation(self):
        """Test creating an embedding store."""
        store = EmbeddingStore(dimension=128)
        
        assert store.vector_db.dimension == 128

    def test_embedding_store_add(self):
        """Test adding text with embedding."""
        store = EmbeddingStore(dimension=3)
        embedding = np.array([0.1, 0.2, 0.3])
        
        entry_id = store.add("Hello world", embedding)
        
        assert entry_id is not None

    def test_embedding_store_search(self):
        """Test searching for similar texts."""
        store = EmbeddingStore(dimension=3)
        
        store.add("Apple fruit", np.array([1.0, 0.0, 0.0]))
        store.add("Banana fruit", np.array([0.0, 1.0, 0.0]))
        
        results = store.search(np.array([1.0, 0.0, 0.0]), top_k=1)
        
        assert len(results) == 1
        assert "Apple" in results[0]["text"]

    def test_embedding_store_get(self):
        """Test retrieving an entry."""
        store = EmbeddingStore(dimension=3)
        embedding = np.array([0.1, 0.2, 0.3])
        
        entry_id = store.add("Test text", embedding)
        
        entry = store.get(entry_id)
        
        assert entry is not None
        assert entry["text"] == "Test text"

    def test_embedding_store_delete(self):
        """Test deleting an entry."""
        store = EmbeddingStore(dimension=3)
        embedding = np.array([0.1, 0.2, 0.3])
        
        entry_id = store.add("Test", embedding)
        
        assert store.delete(entry_id) is True
        assert store.get(entry_id) is None
