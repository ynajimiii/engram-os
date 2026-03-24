"""
Scratch - Temporary workspace management.

Phase 01: Scratch Memory
"""

import os
import tempfile
import yaml
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ScratchEntry:
    """A single entry in the scratch space."""
    key: str
    value: Any
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


class Scratch:
    """
    Temporary workspace for agent operations.
    
    Provides a structured space for agents to store intermediate
    results, working data, and transient state.
    """

    def __init__(self, session_id: Optional[str] = None, 
                 base_dir: Optional[str] = None):
        self.session_id = session_id or self._generate_session_id()
        self.base_dir = Path(base_dir) if base_dir else Path(tempfile.gettempdir())
        self.scratch_dir = self.base_dir / "engram_scratch" / self.session_id
        self._entries: Dict[str, ScratchEntry] = {}
        
        self._ensure_dir()

    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        import uuid
        return str(uuid.uuid4())[:8]

    def _ensure_dir(self) -> None:
        """Ensure the scratch directory exists."""
        self.scratch_dir.mkdir(parents=True, exist_ok=True)

    def set(self, key: str, value: Any, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Set a value in the scratch space."""
        entry = ScratchEntry(
            key=key,
            value=value,
            metadata=metadata or {}
        )
        self._entries[key] = entry
        self._persist_entry(entry)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from the scratch space."""
        entry = self._entries.get(key)
        if entry is None:
            return default
        
        # Try to load from disk if not in memory
        if entry.value is None:
            self._load_entry(entry)
        
        return entry.value

    def delete(self, key: str) -> bool:
        """Delete a value from the scratch space."""
        if key in self._entries:
            del self._entries[key]
            self._remove_persisted_entry(key)
            return True
        return False

    def clear(self) -> None:
        """Clear all entries from the scratch space."""
        self._entries.clear()
        if self.scratch_dir.exists():
            for f in self.scratch_dir.glob("*"):
                f.unlink()

    def keys(self) -> List[str]:
        """Return all keys in the scratch space."""
        return list(self._entries.keys())

    def to_dict(self) -> Dict[str, Any]:
        """Export scratch contents as dictionary."""
        return {k: v.value for k, v in self._entries.items()}

    def _persist_entry(self, entry: ScratchEntry) -> None:
        """Persist an entry to disk."""
        filepath = self.scratch_dir / f"{entry.key}.yaml"
        data = {
            "key": entry.key,
            "value": entry.value,
            "created_at": entry.created_at.isoformat(),
            "updated_at": entry.updated_at.isoformat(),
            "metadata": entry.metadata,
        }
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
        except OSError as e:
            import logging
            logging.error(
                f"[ENGRAM] scratch.py — failed to persist entry '{entry.key}': {e}. "
                f"Entry is in memory but not on disk."
            )
            raise  # re-raise so caller knows persistence failed

    def _load_entry(self, entry: ScratchEntry) -> None:
        """Load an entry from disk."""
        filepath = self.scratch_dir / f"{entry.key}.yaml"
        if filepath.exists():
            with open(filepath) as f:
                data = yaml.safe_load(f)
                entry.value = data.get("value")

    def _remove_persisted_entry(self, key: str) -> None:
        """Remove a persisted entry from disk."""
        filepath = self.scratch_dir / f"{key}.yaml"
        if filepath.exists():
            filepath.unlink()

    def save(self) -> None:
        """Save all entries to disk."""
        for entry in self._entries.values():
            self._persist_entry(entry)

    def load(self) -> None:
        """Load all entries from disk."""
        if not self.scratch_dir.exists():
            return

        for filepath in self.scratch_dir.glob("*.yaml"):
            with open(filepath) as f:
                data = yaml.safe_load(f)
                entry = ScratchEntry(
                    key=data["key"],
                    value=data.get("value"),
                    created_at=datetime.fromisoformat(data["created_at"]),
                    updated_at=datetime.fromisoformat(data["updated_at"]),
                    metadata=data.get("metadata", {}),
                )
                self._entries[entry.key] = entry


def append_to_cumulative_log(
    entry: dict,
    log_path: str,
) -> None:
    """
    Append one session log entry to the cumulative JSONL log.

    Called after every agent_turn() completes.
    The file grows forever — it is the cross-session
    evidence base for Ring 3 learning.

    Format: one JSON object per line (JSONL).
    Each entry must include at minimum:
      task, quality_score, session_id, ts

    Never raises. Logs on error.
    """
    import json
    import logging
    from pathlib import Path
    from datetime import datetime

    # Ensure required fields have defaults
    entry.setdefault("ts", datetime.utcnow().isoformat())

    try:
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logging.warning(
            f"[ENGRAM] cumulative log append failed: {e}"
        )


def load_cumulative_log(
    log_path: str,
    last_n: int = 50,
    min_score: float = 0.0,
) -> list:
    """
    Load the most recent N entries from the cumulative log.

    Used by Ring 3 to read cross-session evidence.

    Args:
        log_path: Path to the JSONL file.
        last_n:   Max number of entries to return.
                  Returns the most recent ones.
        min_score: Filter entries below this quality score.

    Returns:
        List of dicts. Empty list if file doesn't exist.
        Never raises.
    """
    import json
    import logging
    from pathlib import Path

    path = Path(log_path)
    if not path.exists():
        return []

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        entries = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if obj.get("quality_score", 0.0) >= min_score:
                    entries.append(obj)
            except json.JSONDecodeError:
                continue

        # Return most recent last_n
        return entries[-last_n:] if len(entries) > last_n else entries

    except Exception as e:
        logging.warning(
            f"[ENGRAM] cumulative log load failed: {e}"
        )
        return []
