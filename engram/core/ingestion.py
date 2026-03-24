"""
Chunk Ingestion Pipeline - Phase 10

Walks project directories, splits files into semantic chunks,
and ingests them into the vector database.

Usage:
    from engram.core.ingestion import ingest_project
    
    count = ingest_project("/path/to/project", db, mcp_client)
    print(f"Ingested {count} chunks")

CLI:
    python -m engram.commands.ingest --path /path/to/project
"""

import ast
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .mcp_client import MCPClient
from .vector_db import VectorDB


# ============================================================================
# CONFIGURATION
# ============================================================================

# File extensions to ingest
SUPPORTED_EXTENSIONS = {
    '.py', '.ts', '.tsx', '.js', '.jsx',
    '.yaml', '.yml', '.json', '.md',
    '.sql', '.txt', '.rst', '.toml', '.cfg', '.ini',
}

# Directories to skip
SKIP_DIRS = {
    'node_modules', '__pycache__', 'venv', '.venv',
    'dist', 'build', '.git', 'target', 'vendor',
    'egg-info', '.eggs', '*.egg-info', 'coverage',
    '.pytest_cache', '.mypy_cache', '.ruff_cache',
    'minified', 'vendor', 'third_party',
}

# File patterns to skip
SKIP_PATTERNS = {
    '*.min.js', '*.min.css', '*.bundle.js',
    'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml',
    'poetry.lock', 'Pipfile.lock',
}


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class Chunk:
    """
    A semantic chunk of code or documentation.
    
    Attributes:
        id: Unique identifier (format: {type}_{filename}_{symbol})
        text: The chunk content
        chunk_type: Type of chunk (func, class, section, key, etc.)
        source_file: Path to source file
        symbols: List of symbol names (functions, classes, etc.)
        metadata: Additional metadata
    """
    id: str
    text: str
    chunk_type: str
    source_file: str
    symbols: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "text": self.text,
            "chunk_type": self.chunk_type,
            "source_file": self.source_file,
            "symbols": self.symbols,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Chunk":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            text=data["text"],
            chunk_type=data["chunk_type"],
            source_file=data["source_file"],
            symbols=data.get("symbols", []),
            metadata=data.get("metadata", {}),
        )


# ============================================================================
# PHASE 1: WALK PROJECT
# ============================================================================

def walk_project(
    root_path: str,
    mcp: MCPClient,
    skip_dirs: Optional[Set[str]] = None,
    extensions: Optional[Set[str]] = None,
) -> List[Path]:
    """
    Walk project directory and return list of files to ingest.
    
    Uses MCP filesystem tools to traverse the directory tree,
    filtering by extension and skipping common non-source directories.
    
    Args:
        root_path: Project root directory
        mcp: MCP client for filesystem operations
        skip_dirs: Directories to skip (uses SKIP_DIRS if None)
        extensions: File extensions to include (uses SUPPORTED_EXTENSIONS if None)
    
    Returns:
        List of file paths to ingest
    
    Example:
        >>> mcp = MCPClient()
        >>> mcp.connect_from_config()
        >>> files = walk_project("/path/to/project", mcp)
        >>> print(f"Found {len(files)} files to ingest")
    """
    skip_dirs = skip_dirs or SKIP_DIRS
    extensions = extensions or SUPPORTED_EXTENSIONS
    
    root = Path(root_path)
    files: List[Path] = []
    
    def _should_skip_dir(dir_name: str) -> bool:
        """Check if directory should be skipped."""
        if dir_name in skip_dirs:
            return True
        for pattern in skip_dirs:
            if pattern.startswith('*') and dir_name.endswith(pattern[1:]):
                return True
        return False
    
    def _should_skip_file(file_name: str) -> bool:
        """Check if file should be skipped."""
        for pattern in SKIP_PATTERNS:
            if pattern.startswith('*') and file_name.endswith(pattern[1:]):
                return True
        return False
    
    def _has_supported_extension(file_name: str) -> bool:
        """Check if file has supported extension."""
        return Path(file_name).suffix.lower() in extensions
    
    def _walk_directory(dir_path: Path) -> None:
        """Recursively walk directory using MCP."""
        try:
            # Use MCP list_directory
            result = mcp.call_tool("list_directory", {"path": str(dir_path)})
            
            if not result.success:
                raise ValueError("MCP list_directory failed")
            
            items = result.result.get("items", [])
            
            for item in items:
                item_path = dir_path / item
                
                # Skip directories
                if item_path.is_dir():
                    if not _should_skip_dir(item_path.name):
                        _walk_directory(item_path)
                    continue
                
                # Skip files
                if _should_skip_file(item_path.name):
                    continue
                
                # Check extension
                if _has_supported_extension(item_path.name):
                    files.append(item_path)
        
        except Exception:
            # Fallback to standard pathlib walk if MCP fails
            _walk_directory_fallback(dir_path, files, skip_dirs, extensions)
    
    def _walk_directory_fallback(
        path: Path,
        files_list: List[Path],
        skip_dirs_set: Set[str],
        extensions_set: Set[str]
    ) -> None:
        """Fallback walk using standard pathlib."""
        try:
            for item in path.iterdir():
                if item.is_dir():
                    if not _should_skip_dir(item.name):
                        _walk_directory_fallback(item, files_list, skip_dirs_set, extensions_set)
                elif item.is_file():
                    if not _should_skip_file(item.name) and _has_supported_extension(item.name):
                        files_list.append(item)
        except (PermissionError, OSError) as e:
            import logging
            logging.warning(
                f"[ENGRAM] ingestion — skipped directory: {e}. "
                f"Path will not be ingested."
            )
    
    # Start walking - use fallback directly for reliability
    if root.exists():
        _walk_directory_fallback(root, files, skip_dirs, extensions)
    else:
        # Try MCP first if root doesn't exist as local path
        _walk_directory(root)

    return files


# ============================================================================
# PHASE 2: CHUNK FILES
# ============================================================================

def chunk_file(path: Path, content: str) -> List[Chunk]:
    """
    Split a file into semantic chunks.
    
    Strategy by file type:
    - Python: function-level + class-level splits
    - TS/JS: function + component splits
    - YAML/JSON: top-level key splits
    - Markdown: section splits (## headers)
    - SQL: table-level splits
    
    Args:
        path: File path
        content: File content
    
    Returns:
        List of semantic chunks
    
    Example:
        >>> path = Path("auth.py")
        >>> content = open(path).read()
        >>> chunks = chunk_file(path, content)
        >>> print(f"Created {len(chunks)} chunks")
    """
    ext = path.suffix.lower()
    
    if ext == '.py':
        return _chunk_python(path, content)
    elif ext in {'.ts', '.tsx', '.js', '.jsx'}:
        return _chunk_typescript(path, content)
    elif ext in {'.yaml', '.yml'}:
        return _chunk_yaml(path, content)
    elif ext == '.json':
        return _chunk_json(path, content)
    elif ext == '.md':
        return _chunk_markdown(path, content)
    elif ext == '.sql':
        return _chunk_sql(path, content)
    elif ext in {'.toml', '.cfg', '.ini'}:
        return _chunk_config(path, content)
    else:
        return [_fallback_chunk(path, content)]


def _generate_chunk_id(chunk_type: str, path: Path, symbol: str) -> str:
    """Generate unique chunk ID."""
    # Sanitize symbol name
    safe_symbol = re.sub(r'[^a-zA-Z0-9_]', '_', symbol)[:50]
    return f"{chunk_type}_{path.stem}_{safe_symbol}"


# ----------------------------------------------------------------------------
# Python Chunking
# ----------------------------------------------------------------------------

def _chunk_python(path: Path, content: str) -> List[Chunk]:
    """Split Python file by functions and classes."""
    chunks = []
    
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return [_fallback_chunk(path, content)]
    
    # Track top-level items to avoid duplicates
    processed: Set[str] = set()
    
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # Skip methods (they're handled by class chunking)
            if _is_method(node):
                continue
            
            chunk_id = _generate_chunk_id("func", path, node.name)
            if chunk_id in processed:
                continue
            processed.add(chunk_id)
            
            chunk = Chunk(
                id=chunk_id,
                text=_extract_function_source(content, node),
                chunk_type="func",
                source_file=str(path),
                symbols=[node.name],
                metadata={
                    "args": [arg.arg for arg in node.args.args if arg.arg != 'self'],
                    "decorators": [_get_decorator_name(d) for d in node.decorator_list],
                    "returns": _get_return_annotation(node),
                    "docstring": ast.get_docstring(node),
                }
            )
            chunks.append(chunk)
        
        elif isinstance(node, ast.ClassDef):
            chunk_id = _generate_chunk_id("class", path, node.name)
            if chunk_id in processed:
                continue
            processed.add(chunk_id)
            
            methods = [m.name for m in node.body if isinstance(m, ast.FunctionDef)]
            
            chunk = Chunk(
                id=chunk_id,
                text=_extract_class_source(content, node),
                chunk_type="class",
                source_file=str(path),
                symbols=[node.name] + methods,
                metadata={
                    "bases": [_get_base_name(base) for base in node.bases],
                    "methods": methods,
                    "docstring": ast.get_docstring(node),
                }
            )
            chunks.append(chunk)
    
    # If no functions/classes found, return file-level chunk
    if not chunks:
        chunks.append(_fallback_chunk(path, content, "module"))
    
    return chunks


def _is_method(node: ast.FunctionDef) -> bool:
    """Check if function is a method (has 'self' as first arg)."""
    if node.args.args:
        first_arg = node.args.args[0]
        return first_arg.arg in ('self', 'cls')
    return False


def _extract_function_source(content: str, node: ast.FunctionDef) -> str:
    """Extract function source code."""
    lines = content.split('\n')
    start_line = node.lineno - 1
    end_line = node.end_lineno if hasattr(node, 'end_lineno') and node.end_lineno else start_line + 1
    
    return '\n'.join(lines[start_line:end_line])


def _extract_class_source(content: str, node: ast.ClassDef) -> str:
    """Extract class source code."""
    lines = content.split('\n')
    start_line = node.lineno - 1
    end_line = node.end_lineno if hasattr(node, 'end_lineno') and node.end_lineno else start_line + 1
    
    return '\n'.join(lines[start_line:end_line])


def _get_decorator_name(decorator: ast.expr) -> str:
    """Get decorator name as string."""
    if isinstance(decorator, ast.Name):
        return decorator.id
    elif isinstance(decorator, ast.Attribute):
        return ast.unparse(decorator)
    elif isinstance(decorator, ast.Call):
        if isinstance(decorator.func, ast.Name):
            return decorator.func.id
        return ast.unparse(decorator)
    return ast.unparse(decorator)


def _get_return_annotation(node: ast.FunctionDef) -> Optional[str]:
    """Get function return annotation."""
    if node.returns:
        return ast.unparse(node.returns)
    return None


def _get_base_name(base: ast.expr) -> str:
    """Get base class name."""
    if isinstance(base, ast.Name):
        return base.id
    return ast.unparse(base)


# ----------------------------------------------------------------------------
# TypeScript/JavaScript Chunking
# ----------------------------------------------------------------------------

def _chunk_typescript(path: Path, content: str) -> List[Chunk]:
    """Split TypeScript/JavaScript file by functions and components."""
    chunks = []
    
    # Function pattern (arrow functions and regular functions)
    func_pattern = r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\([^)]*\)'
    arrow_pattern = r'(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>'
    component_pattern = r'(?:export\s+)?(?:function|const)\s+([A-Z]\w*)\s*(?:\([^)]*\))?\s*(?:=>|{)'
    
    lines = content.split('\n')
    
    # Find functions
    for match in re.finditer(func_pattern, content):
        func_name = match.group(1)
        start_pos = match.start()
        start_line = content[:start_pos].count('\n')
        
        # Find function end (simplified - looks for closing brace)
        end_line = _find_block_end(lines, start_line)
        
        chunk = Chunk(
            id=_generate_chunk_id("func", path, func_name),
            text='\n'.join(lines[start_line:end_line]),
            chunk_type="func",
            source_file=str(path),
            symbols=[func_name],
            metadata={"exported": 'export' in match.group(0)}
        )
        chunks.append(chunk)
    
    # Find arrow functions
    for match in re.finditer(arrow_pattern, content):
        func_name = match.group(1)
        start_pos = match.start()
        start_line = content[:start_pos].count('\n')
        
        end_line = _find_block_end(lines, start_line)
        
        chunk = Chunk(
            id=_generate_chunk_id("func", path, func_name),
            text='\n'.join(lines[start_line:end_line]),
            chunk_type="func",
            source_file=str(path),
            symbols=[func_name],
            metadata={"exported": 'export' in match.group(0), "type": "arrow"}
        )
        chunks.append(chunk)
    
    # Find React components
    for match in re.finditer(component_pattern, content):
        comp_name = match.group(1)
        if comp_name[0].isupper():  # React components start with uppercase
            start_pos = match.start()
            start_line = content[:start_pos].count('\n')
            
            end_line = _find_block_end(lines, start_line)
            
            chunk = Chunk(
                id=_generate_chunk_id("component", path, comp_name),
                text='\n'.join(lines[start_line:end_line]),
                chunk_type="component",
                source_file=str(path),
                symbols=[comp_name],
                metadata={"type": "react_component"}
            )
            chunks.append(chunk)
    
    if not chunks:
        chunks.append(_fallback_chunk(path, content, "module"))
    
    return chunks


def _find_block_end(lines: List[str], start_line: int) -> int:
    """Find the end of a code block by counting braces."""
    brace_count = 0
    in_string = False
    string_char = None
    
    for i, line in enumerate(lines[start_line:], start=start_line):
        for char in line:
            if char in '"\'`' and not in_string:
                in_string = True
                string_char = char
            elif char == string_char and in_string:
                in_string = False
                string_char = None
            elif not in_string:
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
        
        if brace_count <= 0 and i > start_line:
            return i + 1
    
    return min(start_line + 50, len(lines))  # Fallback limit


# ----------------------------------------------------------------------------
# YAML Chunking
# ----------------------------------------------------------------------------

def _chunk_yaml(path: Path, content: str) -> List[Chunk]:
    """Split YAML file by top-level keys."""
    chunks = []
    
    try:
        import yaml
        data = yaml.safe_load(content)
    except Exception:
        return [_fallback_chunk(path, content, "yaml")]
    
    if not isinstance(data, dict):
        return [_fallback_chunk(path, content, "yaml")]
    
    lines = content.split('\n')
    
    for key in data.keys():
        # Find the line where this key starts
        key_line = None
        for i, line in enumerate(lines):
            if line.startswith(f'{key}:') or line.startswith(f'- {key}:'):
                key_line = i
                break
        
        if key_line is None:
            continue
        
        # Find next top-level key
        end_line = len(lines)
        for i in range(key_line + 1, len(lines)):
            if lines[i] and not lines[i].startswith(' ') and not lines[i].startswith('#'):
                end_line = i
                break
        
        chunk_content = '\n'.join(lines[key_line:end_line])
        
        chunks.append(Chunk(
            id=_generate_chunk_id("key", path, key),
            text=chunk_content,
            chunk_type="key",
            source_file=str(path),
            symbols=[key],
            metadata={"yaml_key": key}
        ))
    
    if not chunks:
        chunks.append(_fallback_chunk(path, content, "yaml"))
    
    return chunks


# ----------------------------------------------------------------------------
# JSON Chunking
# ----------------------------------------------------------------------------

def _chunk_json(path: Path, content: str) -> List[Chunk]:
    """Split JSON file by top-level keys."""
    chunks = []
    
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return [_fallback_chunk(path, content, "json")]
    
    if not isinstance(data, dict):
        return [_fallback_chunk(path, content, "json")]
    
    for key, value in data.items():
        chunk_content = json.dumps({key: value}, indent=2)
        
        chunks.append(Chunk(
            id=_generate_chunk_id("key", path, key),
            text=chunk_content,
            chunk_type="key",
            source_file=str(path),
            symbols=[key],
            metadata={"json_key": key, "value_type": type(value).__name__}
        ))
    
    if not chunks:
        chunks.append(_fallback_chunk(path, content, "json"))
    
    return chunks


# ----------------------------------------------------------------------------
# Markdown Chunking
# ----------------------------------------------------------------------------

def _chunk_markdown(path: Path, content: str) -> List[Chunk]:
    """Split Markdown file by sections (## headers)."""
    chunks = []
    lines = content.split('\n')
    
    current_section = None
    current_content: List[str] = []
    section_start = 0
    
    for i, line in enumerate(lines):
        # Check for section header (## or ###)
        header_match = re.match(r'^(#{2,3})\s+(.+)$', line)
        
        if header_match:
            # Save previous section
            if current_section and current_content:
                chunks.append(Chunk(
                    id=_generate_chunk_id("section", path, current_section),
                    text='\n'.join(current_content),
                    chunk_type="section",
                    source_file=str(path),
                    symbols=[current_section],
                    metadata={"header_level": len(header_match.group(1)) if current_section else 0}
                ))
            
            # Start new section
            current_section = header_match.group(2).strip()
            current_content = [line]
            section_start = i
        else:
            if current_section:
                current_content.append(line)
    
    # Don't forget the last section
    if current_section and current_content:
        chunks.append(Chunk(
            id=_generate_chunk_id("section", path, current_section),
            text='\n'.join(current_content),
            chunk_type="section",
            source_file=str(path),
            symbols=[current_section],
            metadata={"header_level": 2}
        ))
    
    # If no sections found, create file-level chunk
    if not chunks:
        chunks.append(_fallback_chunk(path, content, "document"))
    
    return chunks


# ----------------------------------------------------------------------------
# SQL Chunking
# ----------------------------------------------------------------------------

def _chunk_sql(path: Path, content: str) -> List[Chunk]:
    """Split SQL file by table definitions."""
    chunks = []
    
    # Match CREATE TABLE statements
    table_pattern = r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\((.*?)\);'
    
    for match in re.finditer(table_pattern, content, re.IGNORECASE | re.DOTALL):
        table_name = match.group(1)
        table_def = match.group(0)
        
        # Extract column names
        columns_match = match.group(2)
        columns = []
        for line in columns_match.split(','):
            line = line.strip()
            if line and not line.startswith('--'):
                col_name = line.split()[0] if line.split() else None
                if col_name and col_name not in ('PRIMARY', 'FOREIGN', 'UNIQUE', 'INDEX'):
                    columns.append(col_name)
        
        chunks.append(Chunk(
            id=_generate_chunk_id("table", path, table_name),
            text=table_def,
            chunk_type="table",
            source_file=str(path),
            symbols=[table_name] + columns,
            metadata={"columns": columns}
        ))
    
    if not chunks:
        chunks.append(_fallback_chunk(path, content, "sql"))
    
    return chunks


# ----------------------------------------------------------------------------
# Config File Chunking (TOML, INI, CFG)
# ----------------------------------------------------------------------------

def _chunk_config(path: Path, content: str) -> List[Chunk]:
    """Split config file by sections."""
    chunks = []
    lines = content.split('\n')
    
    current_section = "root"
    current_content: List[str] = []
    
    for line in lines:
        # Check for section header [section]
        section_match = re.match(r'^\[([^\]]+)\]$', line.strip())
        
        if section_match:
            # Save previous section
            if current_content:
                chunks.append(Chunk(
                    id=_generate_chunk_id("section", path, current_section),
                    text='\n'.join(current_content),
                    chunk_type="section",
                    source_file=str(path),
                    symbols=[current_section],
                    metadata={"config_section": current_section}
                ))
            
            # Start new section
            current_section = section_match.group(1)
            current_content = [line]
        else:
            current_content.append(line)
    
    # Don't forget the last section
    if current_content:
        chunks.append(Chunk(
            id=_generate_chunk_id("section", path, current_section),
            text='\n'.join(current_content),
            chunk_type="section",
            source_file=str(path),
            symbols=[current_section],
            metadata={"config_section": current_section}
        ))
    
    if not chunks:
        chunks.append(_fallback_chunk(path, content, "config"))
    
    return chunks


# ----------------------------------------------------------------------------
# Fallback Chunking
# ----------------------------------------------------------------------------

def _fallback_chunk(path: Path, content: str, chunk_type: str = "file") -> Chunk:
    """Create a single chunk for the entire file."""
    # Truncate if too large (> 10KB)
    max_size = 10000
    if len(content) > max_size:
        content = content[:max_size] + "\n... [truncated]"
    
    return Chunk(
        id=_generate_chunk_id(chunk_type, path, path.stem),
        text=content,
        chunk_type=chunk_type,
        source_file=str(path),
        symbols=[path.stem],
        metadata={
            "file_size": len(content),
            "extension": path.suffix,
        }
    )


# ============================================================================
# PHASE 3: INGEST PROJECT
# ============================================================================

def _read_file_direct(file_path: str) -> str:
    """
    Read a file directly from the filesystem.
    Used as fallback when MCP read returns empty or fails.

    Returns file content as string, or "" on any error.
    Never raises.

    Handles:
      - UTF-8 with BOM
      - Latin-1 fallback for files with encoding errors
      - Files too large to read (> 500KB skipped)
    """
    import logging
    from pathlib import Path

    MAX_FILE_BYTES = 500_000   # 500KB ceiling per file

    try:
        path = Path(file_path)
        if not path.exists():
            return ""
        if not path.is_file():
            return ""

        size = path.stat().st_size
        if size == 0:
            return ""
        if size > MAX_FILE_BYTES:
            logging.debug(
                f"[ENGRAM] ingest: skipping large file "
                f"({size} bytes): {path.name}"
            )
            return ""

        # Try UTF-8 first (handles BOM via utf-8-sig)
        try:
            return path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            pass

        # Latin-1 fallback — never raises on any byte sequence
        try:
            return path.read_text(encoding="latin-1")
        except Exception:
            return ""

    except Exception as e:
        logging.debug(
            f"[ENGRAM] ingest: direct read failed "
            f"for {file_path}: {e}"
        )
        return ""


def ingest_project(
    root_path: str,
    db: VectorDB,
    mcp: MCPClient,
    tier: str = "warm",
    skip_dirs: Optional[Set[str]] = None,
    extensions: Optional[Set[str]] = None,
) -> Tuple[int, int]:
    """
    Ingest entire project into vector database.
    
    Walks the project directory, chunks each file semantically,
    and adds all chunks to the vector database.
    
    Args:
        root_path: Project root directory
        db: Vector database instance
        mcp: MCP client for file operations
        tier: Initial tier for chunks (warm, cold)
        skip_dirs: Directories to skip
        extensions: File extensions to include
    
    Returns:
        Tuple of (files_processed, chunks_created)
    
    Example:
        >>> mcp = MCPClient()
        >>> mcp.connect_from_config()
        >>> db = VectorDB(dimension=768)
        >>> files, chunks = ingest_project("/path/to/project", db, mcp)
        >>> print(f"Ingested {chunks} chunks from {files} files")
    """
    # Walk project
    files = walk_project(root_path, mcp, skip_dirs, extensions)

    chunk_count = 0
    error_count = 0

    for file_path in files:
        try:
            # Convert to absolute path for MCP (relative paths cause truncation)
            abs_path = str(Path(file_path).absolute())
            
            # Read file via MCP
            result = mcp.call_tool("read_file", {"path": abs_path})

            if not result.success:
                error_count += 1
                continue

            # MCP returns content as list of blocks: [{'type': 'text', 'text': '...'}]
            content_raw = result.result.get("content", "")
            
            # Extract text from content blocks
            if isinstance(content_raw, list) and content_raw:
                content = "\n".join(
                    block.get("text", "") 
                    for block in content_raw 
                    if isinstance(block, dict) and block.get("type") == "text"
                )
            elif isinstance(content_raw, str):
                content = content_raw
            else:
                content = ""

            # ADD filesystem fallback when MCP returns empty
            if not content:
                import logging
                logging.debug(
                    f"[ENGRAM] ingest: MCP read empty for "
                    f"{file_path} — using filesystem fallback"
                )
                content = _read_file_direct(str(file_path))

            if not content:
                import logging
                logging.debug(
                    f"[ENGRAM] ingest: skipping empty file: "
                    f"{file_path}"
                )
                continue

            # Chunk semantically
            chunks = chunk_file(file_path, content)

            # Add per-file chunk count logging
            import logging
            logging.debug(
                f"[ENGRAM] ingest: {Path(file_path).name} "
                f"→ {len(chunks)} chunk(s)"
            )
            
            # Add to database
            for chunk in chunks:
                # Create embedding using real sentence-transformers
                from engram.core.embedder import get_embedding
                embedding = get_embedding(chunk.text)
                
                db.insert(
                    vector=embedding,
                    metadata={
                        **chunk.to_dict(),
                        "tier": tier,
                        "ingested_at": datetime.now().isoformat(),
                    },
                    entry_id=chunk.id,
                )
                chunk_count += 1
        
        except Exception as e:
            error_count += 1
            continue
    
    return len(files), chunk_count


def ingest_project_direct(
    root_path: str,
    db,
    skip_dirs: list = None,
    extensions: list = None,
    tier: str = "warm",
    min_chunk_chars: int = 50,
) -> int:
    """
    Ingest a codebase into the vector DB using direct
    filesystem reads — no MCP client required.

    Produces the same chunk schema as ingest_project().
    Use when mcp is None or when MCP reads return empty.

    Args:
        root_path:       Root directory to ingest.
        db:              VectorDB instance.
        skip_dirs:       Directory names to skip.
        extensions:      File extensions to include.
                         Default: .py .ts .js .md .yaml .yml
                         .json .txt .toml .sql .rst .cfg .ini
        tier:            DB tier to insert into (default "warm").
        min_chunk_chars: Minimum chars for a chunk to be stored.

    Returns:
        Total number of chunks inserted.
        Returns 0 if root_path does not exist.
        Never raises.
    """
    import logging
    import hashlib
    import numpy as np
    from pathlib import Path

    _DEFAULT_EXTENSIONS = {
        ".py", ".ts", ".tsx", ".js", ".jsx",
        ".yaml", ".yml", ".json", ".md", ".sql",
        ".txt", ".rst", ".toml", ".cfg", ".ini",
    }

    _DEFAULT_SKIP_DIRS = {
        ".git", "__pycache__", ".pytest_cache",
        "node_modules", ".venv", "venv", "env",
        "dist", "build", ".mypy_cache",
        "sessions", "experience", "versions",
    }

    root        = Path(root_path)
    skip_set    = set(skip_dirs or []) | _DEFAULT_SKIP_DIRS
    ext_set     = set(extensions or _DEFAULT_EXTENSIONS)
    total       = 0

    if not root.exists():
        logging.warning(
            f"[ENGRAM] ingest_direct: path not found: {root}"
        )
        return 0

    logging.info(
        f"[ENGRAM] ingest_direct: scanning {root} "
        f"(skip={len(skip_set)} dirs)"
    )

    # ── Walk and collect files ────────────────────────────────
    files_found = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        # Skip any file whose parent chain contains a skip dir
        if any(part in skip_set for part in path.parts):
            continue
        if path.suffix.lower() not in ext_set:
            continue
        files_found.append(path)

    logging.info(
        f"[ENGRAM] ingest_direct: {len(files_found)} files "
        f"to process"
    )

    # ── Process each file ─────────────────────────────────────
    for file_path in files_found:
        content = _read_file_direct(str(file_path))
        if not content or len(content) < min_chunk_chars:
            logging.debug(
                f"[ENGRAM] ingest_direct: skipping "
                f"{file_path.name} (empty or too short)"
            )
            continue

        # ── Chunk the content ─────────────────────────────────
        chunks = chunk_file(file_path, content)

        # ── Insert chunks ─────────────────────────────────────
        for chunk in chunks:
            if len(chunk.text) < min_chunk_chars:
                continue
            try:
                # Create embedding using real sentence-transformers
                from engram.core.embedder import get_embedding
                embedding = get_embedding(chunk.text)
                
                db.insert(
                    vector=embedding,
                    metadata={
                        **chunk.to_dict(),
                        "tier": tier,
                        "ingested_at": datetime.now().isoformat(),
                    },
                    entry_id=chunk.id,
                )
                total += 1
            except Exception as e:
                logging.debug(
                    f"[ENGRAM] ingest_direct: db.insert failed "
                    f"for {file_path.name}: {e}"
                )

        logging.debug(
            f"[ENGRAM] ingest_direct: {file_path.name} "
            f"→ {len(chunks)} chunk(s)"
        )

    logging.info(
        f"[ENGRAM] ingest_direct: complete — "
        f"{total} chunks from {len(files_found)} files"
    )
    return total


def _create_pseudo_embedding(text: str, dimension: int) -> 'np.ndarray':
    """
    Create a pseudo-embedding for testing purposes.
    
    In production, this would use a real embedding model like
    sentence-transformers or OpenAI embeddings.
    
    Args:
        text: Text to embed
        dimension: Embedding dimension
    
    Returns:
        Numpy array of shape (dimension,)
    """
    import numpy as np
    
    # Create deterministic pseudo-embedding based on text hash
    text_hash = hashlib.md5(text.encode()).hexdigest()
    
    # Use hash to seed random generation for reproducibility
    seed = int(text_hash[:8], 16)
    rng = np.random.RandomState(seed)
    
    # Generate normalized vector
    vector = rng.randn(dimension)
    vector = vector / np.linalg.norm(vector)
    
    return vector


# ============================================================================
# CLI COMMAND
# ============================================================================

def cmd_ingest(args) -> int:
    """
    CLI command: engram ingest --path /path/to/project
    
    Args:
        args: Command line arguments
    
    Returns:
        Exit code (0 for success)
    """
    from .mcp_client import MCPClient
    from .vector_db import VectorDB
    
    print(f"\n{'=' * 60}")
    print("ENGRAM OS - Project Ingestion")
    print(f"{'=' * 60}\n")
    
    # Initialize MCP client
    print(f"Connecting to MCP servers...")
    mcp = MCPClient()
    connected = mcp.connect_from_config()
    
    if not connected:
        print("⚠ Warning: No MCP servers connected. Using fallback file access.")
    
    # Initialize vector database
    print(f"Initializing vector database (dimension={args.dimension})...")
    db = VectorDB(dimension=args.dimension)
    
    # Ingest project
    print(f"\nIngesting project: {args.path}")
    print(f"  Skip directories: {SKIP_DIRS}")
    print(f"  Extensions: {SUPPORTED_EXTENSIONS}")
    print()
    
    files_count, chunks_count = ingest_project(
        root_path=args.path,
        db=db,
        mcp=mcp,
        tier=args.tier,
    )
    
    # Report results
    print(f"\n{'=' * 60}")
    print(f"INGESTION COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Files processed: {files_count}")
    print(f"  Chunks created:  {chunks_count}")
    print(f"  Vector DB size:  {len(db)} entries")
    print()
    
    # Test search
    if chunks_count > 0 and args.test_search:
        print("Testing search...")
        test_query = "function"
        embedding = _create_pseudo_embedding(test_query, args.dimension)
        results = db.search(embedding, top_k=3)
        
        print(f"  Query: '{test_query}'")
        print(f"  Top results:")
        for i, (entry_id, similarity, metadata) in enumerate(results, 1):
            source = metadata.get('source_file', 'unknown')
            chunk_type = metadata.get('chunk_type', 'unknown')
            print(f"    {i}. [{chunk_type}] {source} (similarity: {similarity:.3f})")
        print()
    
    return 0


def create_ingest_parser(subparsers) -> None:
    """Create argument parser for ingest command."""
    parser = subparsers.add_parser(
        'ingest',
        help='Ingest a project into the vector database',
        description='Walk a project directory, chunk files semantically, and ingest into vector DB',
    )
    
    parser.add_argument(
        '--path', '-p',
        required=True,
        help='Path to project directory',
    )
    
    parser.add_argument(
        '--tier', '-t',
        default='warm',
        choices=['warm', 'cold'],
        help='Initial tier for chunks (default: warm)',
    )
    
    parser.add_argument(
        '--dimension', '-d',
        type=int,
        default=384,
        help='Vector dimension (default: 384, matches all-MiniLM-L6-v2)',
    )
    
    parser.add_argument(
        '--test-search',
        action='store_true',
        help='Test search after ingestion',
    )
    
    parser.set_defaults(func=cmd_ingest)


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(
        description='ENGRAM OS - Project Ingestion',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python -m engram.core.ingestion --path /path/to/project
  python -m engram.core.ingestion --path ./my_project --tier warm --test-search
        ''',
    )
    
    create_ingest_parser(parser)
    args = parser.parse_args()
    
    exit(cmd_ingest(args))
