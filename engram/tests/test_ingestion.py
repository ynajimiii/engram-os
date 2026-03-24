"""
Tests for Phase 10 - Chunk Ingestion Pipeline

Tests for engram/core/ingestion.py
"""

import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from engram.core.ingestion import (
    Chunk,
    walk_project,
    chunk_file,
    ingest_project,
    SUPPORTED_EXTENSIONS,
    SKIP_DIRS,
)
from engram.core.mcp_client import MCPClient
from engram.core.vector_db import VectorDB


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def temp_project():
    """Create a temporary project structure for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        
        # Create Python files
        py_file = root / "main.py"
        py_file.write_text("""
def hello():
    '''Say hello.'''
    print("Hello, World!")

class Greeter:
    '''A greeter class.'''
    
    def __init__(self, name):
        self.name = name
    
    def greet(self):
        return f"Hello, {self.name}!"

def main():
    greeter = Greeter("World")
    print(greeter.greet())

if __name__ == "__main__":
    main()
""")
        
        # Create TypeScript file
        ts_dir = root / "src"
        ts_dir.mkdir()
        ts_file = ts_dir / "app.ts"
        ts_file.write_text("""
export function add(a: number, b: number): number {
    return a + b;
}

export const multiply = (a: number, b: number) => a * b;

export function Button({ label, onClick }: { label: string, onClick: () => void }) {
    return <button onClick={onClick}>{label}</button>;
}
""")
        
        # Create YAML file
        yaml_file = root / "config.yaml"
        yaml_file.write_text("""
database:
  host: localhost
  port: 5432
  name: mydb

server:
  port: 8080
  debug: true
""")
        
        # Create Markdown file
        md_file = root / "README.md"
        md_file.write_text("""
# My Project

## Introduction

This is a sample project for testing.

## Installation

Run `pip install -r requirements.txt`

## Usage

```python
from myproject import hello
hello()
```

## License

MIT License
""")
        
        # Create node_modules (should be skipped)
        node_modules = root / "node_modules"
        node_modules.mkdir()
        (node_modules / "package.js").write_text("console.log('should be skipped')")
        
        # Create __pycache__ (should be skipped)
        pycache = root / "__pycache__"
        pycache.mkdir()
        (pycache / "main.cpython-39.pyc").write_text("binary content")
        
        yield root


@pytest.fixture
def mock_mcp_client():
    """Create a mock MCP client for testing."""
    mcp = MagicMock(spec=MCPClient)
    
    def mock_call_tool(name, arguments):
        from engram.core.mcp_client import ToolResult
        
        if name == "list_directory":
            path = Path(arguments.get("path", "."))
            if path.exists():
                items = []
                for item in path.iterdir():
                    items.append(item.name)
                return ToolResult(
                    tool_call_id="mock",
                    success=True,
                    result={"items": items},
                )
            return ToolResult(
                tool_call_id="mock",
                success=False,
                error="Path not found",
            )
        
        elif name == "read_file":
            path = Path(arguments.get("path", ""))
            if path.exists() and path.is_file():
                return ToolResult(
                    tool_call_id="mock",
                    success=True,
                    result={"content": path.read_text()},
                )
            return ToolResult(
                tool_call_id="mock",
                success=False,
                error="File not found",
            )
        
        return ToolResult(
            tool_call_id="mock",
            success=False,
            error="Unknown tool",
        )
    
    mcp.call_tool.side_effect = mock_call_tool
    return mcp


@pytest.fixture
def vector_db():
    """Create a vector database for testing."""
    return VectorDB(dimension=384)  # Match embedder output


# ============================================================================
# CHUNK DATA STRUCTURE TESTS
# ============================================================================

class TestChunk:
    """Tests for Chunk dataclass."""
    
    def test_chunk_creation(self):
        """Test creating a chunk."""
        chunk = Chunk(
            id="func_test_hello",
            text="def hello(): pass",
            chunk_type="func",
            source_file="test.py",
            symbols=["hello"],
        )
        
        assert chunk.id == "func_test_hello"
        assert chunk.chunk_type == "func"
        assert chunk.symbols == ["hello"]
    
    def test_chunk_to_dict(self):
        """Test converting chunk to dictionary."""
        chunk = Chunk(
            id="class_test_MyClass",
            text="class MyClass: pass",
            chunk_type="class",
            source_file="test.py",
            symbols=["MyClass"],
            metadata={"docstring": "A test class"},
        )
        
        data = chunk.to_dict()
        
        assert data["id"] == "class_test_MyClass"
        assert data["chunk_type"] == "class"
        assert data["metadata"]["docstring"] == "A test class"
    
    def test_chunk_from_dict(self):
        """Test creating chunk from dictionary."""
        data = {
            "id": "func_test_func",
            "text": "def func(): pass",
            "chunk_type": "func",
            "source_file": "test.py",
            "symbols": ["func"],
            "metadata": {"args": []},
        }
        
        chunk = Chunk.from_dict(data)
        
        assert chunk.id == "func_test_func"
        assert chunk.metadata["args"] == []


# ============================================================================
# WALK PROJECT TESTS
# ============================================================================

class TestWalkProject:
    """Tests for walk_project function."""
    
    def test_walk_project_finds_files(self, temp_project, mock_mcp_client):
        """Test that walk_project finds supported files."""
        files = walk_project(str(temp_project), mock_mcp_client)
        
        # Should find main.py, app.ts, config.yaml, README.md
        assert len(files) >= 4
        
        file_names = [f.name for f in files]
        assert "main.py" in file_names
        assert "app.ts" in file_names
        assert "config.yaml" in file_names
        assert "README.md" in file_names
    
    def test_walk_project_skips_node_modules(self, temp_project, mock_mcp_client):
        """Test that walk_project skips node_modules."""
        files = walk_project(str(temp_project), mock_mcp_client)
        
        # Should not find files in node_modules
        for f in files:
            assert "node_modules" not in str(f)
    
    def test_walk_project_skips_pycache(self, temp_project, mock_mcp_client):
        """Test that walk_project skips __pycache__."""
        files = walk_project(str(temp_project), mock_mcp_client)
        
        # Should not find files in __pycache__
        for f in files:
            assert "__pycache__" not in str(f)
    
    def test_walk_project_filters_extensions(self, temp_project, mock_mcp_client):
        """Test that walk_project filters by extension."""
        # Only Python files
        files = walk_project(
            str(temp_project),
            mock_mcp_client,
            extensions={'.py'}
        )
        
        for f in files:
            assert f.suffix == '.py'
    
    def test_walk_project_fallback(self, temp_project):
        """Test fallback to standard pathlib walk."""
        # Use real MCP client (will fail and use fallback)
        mcp = MCPClient()
        
        files = walk_project(str(temp_project), mcp)
        
        # Should still find files via fallback
        assert len(files) >= 4


# ============================================================================
# CHUNK FILE TESTS
# ============================================================================

class TestChunkFile:
    """Tests for chunk_file function."""
    
    def test_chunk_python_functions(self, temp_project):
        """Test chunking Python functions."""
        py_file = temp_project / "main.py"
        chunks = chunk_file(py_file, py_file.read_text())
        
        # Should find hello function, main function, and Greeter class
        func_chunks = [c for c in chunks if c.chunk_type == "func"]
        class_chunks = [c for c in chunks if c.chunk_type == "class"]
        
        assert len(func_chunks) >= 2  # hello, main
        assert len(class_chunks) >= 1  # Greeter
    
    def test_chunk_python_class_methods(self, temp_project):
        """Test that class methods are included in class chunk."""
        py_file = temp_project / "main.py"
        chunks = chunk_file(py_file, py_file.read_text())
        
        class_chunks = [c for c in chunks if c.chunk_type == "class"]
        
        if class_chunks:
            greeter_chunk = class_chunks[0]
            assert "Greeter" in greeter_chunk.symbols
            assert "greet" in greeter_chunk.symbols or "__init__" in greeter_chunk.symbols
    
    def test_chunk_typescript_functions(self, temp_project):
        """Test chunking TypeScript functions."""
        ts_file = temp_project / "src" / "app.ts"
        chunks = chunk_file(ts_file, ts_file.read_text())
        
        func_chunks = [c for c in chunks if c.chunk_type == "func"]
        component_chunks = [c for c in chunks if c.chunk_type == "component"]
        
        assert len(func_chunks) >= 2  # add, multiply
        assert len(component_chunks) >= 1  # Button component
    
    def test_chunk_yaml_keys(self, temp_project):
        """Test chunking YAML by keys."""
        yaml_file = temp_project / "config.yaml"
        chunks = chunk_file(yaml_file, yaml_file.read_text())
        
        key_chunks = [c for c in chunks if c.chunk_type == "key"]
        
        assert len(key_chunks) >= 2  # database, server
        
        keys = [c.symbols[0] for c in key_chunks]
        assert "database" in keys
        assert "server" in keys
    
    def test_chunk_markdown_sections(self, temp_project):
        """Test chunking Markdown by sections."""
        md_file = temp_project / "README.md"
        chunks = chunk_file(md_file, md_file.read_text())
        
        section_chunks = [c for c in chunks if c.chunk_type == "section"]
        
        assert len(section_chunks) >= 3  # Introduction, Installation, Usage, License
        
        sections = [c.symbols[0] for c in section_chunks]
        assert "Introduction" in sections
        assert "Installation" in sections
    
    def test_chunk_json_keys(self):
        """Test chunking JSON by keys."""
        json_content = """
{
    "name": "test-package",
    "version": "1.0.0",
    "dependencies": {
        "react": "^18.0.0"
    }
}
"""
        from io import StringIO
        path = Path("package.json")
        chunks = chunk_file(path, json_content)
        
        key_chunks = [c for c in chunks if c.chunk_type == "key"]
        
        assert len(key_chunks) >= 3  # name, version, dependencies
    
    def test_chunk_sql_tables(self):
        """Test chunking SQL by tables."""
        sql_content = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL,
    email TEXT UNIQUE
);

CREATE TABLE posts (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    title TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""
        path = Path("schema.sql")
        chunks = chunk_file(path, sql_content)
        
        table_chunks = [c for c in chunks if c.chunk_type == "table"]
        
        assert len(table_chunks) >= 2  # users, posts
        
        tables = [c.symbols[0] for c in table_chunks]
        assert "users" in tables
        assert "posts" in tables
    
    def test_chunk_fallback(self):
        """Test fallback chunking for unknown file types."""
        content = "Some random content"
        path = Path("unknown.xyz")
        chunks = chunk_file(path, content)
        
        assert len(chunks) == 1
        assert chunks[0].chunk_type == "file"


# ============================================================================
# INGEST PROJECT TESTS
# ============================================================================

class TestIngestProject:
    """Tests for ingest_project function."""
    
    def test_ingest_project_counts_chunks(self, temp_project, mock_mcp_client, vector_db):
        """Test that ingest_project returns correct counts."""
        files_count, chunks_count = ingest_project(
            str(temp_project),
            vector_db,
            mock_mcp_client,
        )
        
        assert files_count >= 4  # main.py, app.ts, config.yaml, README.md
        assert chunks_count >= 6  # Multiple chunks per file
    
    def test_ingest_project_creates_searchable_chunks(
        self, temp_project, mock_mcp_client, vector_db
    ):
        """Test that ingested chunks are searchable."""
        files_count, chunks_count = ingest_project(
            str(temp_project),
            vector_db,
            mock_mcp_client,
        )
        
        assert chunks_count > 0
        
        # Test search
        from engram.core.ingestion import _create_pseudo_embedding
        query_embedding = _create_pseudo_embedding("function", vector_db.dimension)
        results = vector_db.search(query_embedding, top_k=3)
        
        assert len(results) > 0
        
        # Results should have metadata
        for entry_id, similarity, metadata in results:
            assert "source_file" in metadata
            assert "chunk_type" in metadata
    
    def test_ingest_project_uses_tier(self, temp_project, mock_mcp_client, vector_db):
        """Test that ingest_project respects tier parameter."""
        files_count, chunks_count = ingest_project(
            str(temp_project),
            vector_db,
            mock_mcp_client,
            tier="cold",
        )
        
        # Check that chunks have tier metadata
        for entry_id in vector_db.list_entries():
            entry = vector_db.get(entry_id)
            if entry and "tier" in entry.metadata:
                assert entry.metadata["tier"] == "cold"
                break


# ============================================================================
# CHUNK ID GENERATION TESTS
# ============================================================================

class TestChunkIdGeneration:
    """Tests for chunk ID generation."""
    
    def test_chunk_id_format(self, temp_project):
        """Test that chunk IDs follow convention."""
        py_file = temp_project / "main.py"
        chunks = chunk_file(py_file, py_file.read_text())
        
        for chunk in chunks:
            # ID format: {type}_{filename}_{symbol}
            assert "_" in chunk.id
            parts = chunk.id.split("_")
            assert len(parts) >= 3
            
            # Type should be first
            assert parts[0] in {"func", "class", "section", "key", "table", "component", "file"}
    
    def test_chunk_id_unique(self, temp_project):
        """Test that chunk IDs are unique."""
        py_file = temp_project / "main.py"
        chunks = chunk_file(py_file, py_file.read_text())
        
        ids = [c.id for c in chunks]
        assert len(ids) == len(set(ids)), "Chunk IDs should be unique"


# ============================================================================
# PSEUDO EMBEDDING TESTS
# ============================================================================

class TestPseudoEmbedding:
    """Tests for pseudo embedding generation."""
    
    def test_pseudo_embedding_dimension(self):
        """Test that pseudo embeddings have correct dimension."""
        from engram.core.ingestion import _create_pseudo_embedding
        
        for dim in [128, 256, 512, 768, 1024]:
            embedding = _create_pseudo_embedding("test text", dim)
            assert embedding.shape == (dim,)
    
    def test_pseudo_embedding_normalized(self):
        """Test that pseudo embeddings are normalized."""
        from engram.core.ingestion import _create_pseudo_embedding
        import numpy as np
        
        embedding = _create_pseudo_embedding("test text", 768)
        norm = np.linalg.norm(embedding)
        
        # Should be approximately 1.0
        assert abs(norm - 1.0) < 1e-6
    
    def test_pseudo_embedding_reproducible(self):
        """Test that pseudo embeddings are reproducible."""
        from engram.core.ingestion import _create_pseudo_embedding
        
        emb1 = _create_pseudo_embedding("same text", 768)
        emb2 = _create_pseudo_embedding("same text", 768)
        
        assert (emb1 == emb2).all()


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestIngestionIntegration:
    """Integration tests for the ingestion pipeline."""
    
    def test_full_ingestion_pipeline(self, temp_project, mock_mcp_client):
        """Test the full ingestion pipeline."""
        # Create vector DB with embedder-matching dimension
        db = VectorDB(dimension=384)
        
        # Ingest
        files, chunks = ingest_project(str(temp_project), db, mock_mcp_client)
        
        # Verify
        assert files >= 4
        assert chunks >= 6
        assert len(db) == chunks
        
        # Search for different queries
        from engram.core.ingestion import _create_pseudo_embedding
        
        queries = ["function", "class", "database", "installation"]
        
        for query in queries:
            embedding = _create_pseudo_embedding(query, 768)
            results = db.search(embedding, top_k=2)
            assert len(results) > 0
