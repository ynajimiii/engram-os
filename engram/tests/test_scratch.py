"""
Tests for scratch.py - Temporary workspace management.

Phase 01: Scratch Memory
"""

import pytest
import tempfile
from pathlib import Path
from engram.core.scratch import Scratch, ScratchEntry


class TestScratch:
    """Tests for Scratch class."""

    def test_scratch_creation(self):
        """Test creating a scratch space."""
        scratch = Scratch()
        
        assert scratch.session_id is not None
        assert scratch.scratch_dir.exists()

    def test_scratch_with_custom_dir(self):
        """Test creating scratch with custom directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scratch = Scratch(base_dir=tmpdir)
            
            assert scratch.base_dir == Path(tmpdir)
            assert scratch.scratch_dir.exists()

    def test_scratch_set_get(self):
        """Test setting and getting values."""
        scratch = Scratch()
        
        scratch.set("key1", "value1")
        assert scratch.get("key1") == "value1"

    def test_scratch_get_default(self):
        """Test getting non-existent key with default."""
        scratch = Scratch()
        
        assert scratch.get("nonexistent", "default") == "default"
        assert scratch.get("nonexistent") is None

    def test_scratch_delete(self):
        """Test deleting a value."""
        scratch = Scratch()
        
        scratch.set("key1", "value1")
        assert scratch.delete("key1") is True
        assert scratch.get("key1") is None
        assert scratch.delete("key1") is False

    def test_scratch_clear(self):
        """Test clearing all values."""
        scratch = Scratch()
        
        scratch.set("key1", "value1")
        scratch.set("key2", "value2")
        
        scratch.clear()
        
        assert scratch.keys() == []

    def test_scratch_keys(self):
        """Test listing keys."""
        scratch = Scratch()
        
        scratch.set("key1", "value1")
        scratch.set("key2", "value2")
        
        keys = scratch.keys()
        assert "key1" in keys
        assert "key2" in keys
        assert len(keys) == 2

    def test_scratch_to_dict(self):
        """Test exporting to dictionary."""
        scratch = Scratch()
        
        scratch.set("key1", "value1")
        scratch.set("key2", 42)
        
        result = scratch.to_dict()
        
        assert result == {"key1": "value1", "key2": 42}

    def test_scratch_with_metadata(self):
        """Test setting value with metadata."""
        scratch = Scratch()
        
        scratch.set("key1", "value1", metadata={"type": "test"})
        
        entry = scratch.get_entry("key1") if hasattr(scratch, "get_entry") else scratch._entries.get("key1")
        assert entry is not None
        assert entry.metadata == {"type": "test"}

    def test_scratch_persistence(self):
        """Test that values are persisted to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scratch = Scratch(base_dir=tmpdir)
            
            scratch.set("key1", {"nested": "value"})
            scratch.save()
            
            # Check file exists
            filepath = scratch.scratch_dir / "key1.yaml"
            assert filepath.exists()

    def test_scratch_load(self):
        """Test loading values from disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scratch1 = Scratch(base_dir=tmpdir, session_id="test123")
            scratch1.set("key1", "value1")
            scratch1.save()
            
            # Create new scratch with same session
            scratch2 = Scratch(base_dir=tmpdir, session_id="test123")
            scratch2.load()
            
            assert scratch2.get("key1") == "value1"


class TestScratchEntry:
    """Tests for ScratchEntry dataclass."""

    def test_entry_creation(self):
        """Test creating a scratch entry."""
        entry = ScratchEntry(
            key="test_key",
            value="test_value",
        )
        
        assert entry.key == "test_key"
        assert entry.value == "test_value"
        assert entry.created_at is not None
        assert entry.updated_at is not None

    def test_entry_with_metadata(self):
        """Test creating entry with metadata."""
        entry = ScratchEntry(
            key="test_key",
            value="test_value",
            metadata={"source": "test"},
        )
        
        assert entry.metadata == {"source": "test"}
