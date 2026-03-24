"""
Contract - Interface definitions and type contracts.

Phase 00: Foundation
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol


class ContractViolationError(Exception):
    """Raised when a contract is violated."""
    pass


@dataclass
class Contract:
    """Base contract for interface validation."""
    name: str
    required_fields: List[str] = field(default_factory=list)
    optional_fields: List[str] = field(default_factory=list)

    def validate(self, data: Dict[str, Any]) -> bool:
        """Validate data against this contract."""
        violations = []
        
        for field_name in self.required_fields:
            if field_name not in data:
                violations.append(f"Missing required field: {field_name}")
        
        if violations:
            raise ContractViolationError(
                f"Contract has {len(violations)} violation(s):\n"
                + "\n".join(f"  - {v}" for v in violations)
            )
        return True


class SessionContract(Contract):
    """Contract for session objects."""

    def __init__(self):
        super().__init__(
            name="SessionContract",
            required_fields=["session_id", "created_at"],
            optional_fields=["context", "history", "metadata"],
        )


class AgentContract(Contract):
    """Contract for agent objects."""

    def __init__(self):
        super().__init__(
            name="AgentContract",
            required_fields=["agent_id", "name"],
            optional_fields=["capabilities", "state", "config"],
        )


class MessageContract(Contract):
    """Contract for message objects."""

    def __init__(self):
        super().__init__(
            name="MessageContract",
            required_fields=["role", "content"],
            optional_fields=["timestamp", "metadata"],
        )


class Executable(Protocol):
    """Protocol for executable components."""

    def execute(self, **kwargs: Any) -> Any:
        """Execute the component."""
        ...


class Serializable(Protocol):
    """Protocol for serializable components."""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        ...

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Serializable":
        """Deserialize from dictionary."""
        ...


class Identifiable(ABC):
    """Abstract base class for identifiable components."""

    @property
    @abstractmethod
    def id(self) -> str:
        """Return the unique identifier."""
        pass


@dataclass
class MemoryContract:
    """Memory contract for resource allocation."""
    weights_mb: int = 14000
    kv_ceiling_mb: int = 4096
    scratch_mb: int = 512
    vector_floor_mb: int = 5968
    vector_max_mb: int = 10064

    def validate(self) -> None:
        """Validate memory contract values."""
        violations = []

        if self.weights_mb <= 0:
            violations.append(f"weights_mb must be > 0, got {self.weights_mb}")
        if self.kv_ceiling_mb <= 0:
            violations.append(f"kv_ceiling_mb must be > 0, got {self.kv_ceiling_mb}")
        if self.scratch_mb <= 0:
            violations.append(f"scratch_mb must be > 0, got {self.scratch_mb}")
        if self.vector_floor_mb < 0:
            violations.append(
                f"vector_floor_mb is negative ({self.vector_floor_mb}MB). "
                f"weights + kv_ceiling + scratch exceeds total VRAM. "
                f"Reduce n_ctx or scratch_mb."
            )

        if violations:
            raise ContractViolationError(
                f"MemoryContract has {len(violations)} violation(s):\n"
                + "\n".join(f"  - {v}" for v in violations)
            )


def calculate_memory_budget(
    weights_mb: int = 14000,
    n_ctx: int = 8192,
    scratch_mb: int = 512,
    vram_total_mb: int = 24576
) -> MemoryContract:
    """
    Calculate memory budget based on available VRAM.
    
    Args:
        weights_mb: Model weights size in MB
        n_ctx: Context length
        scratch_mb: Scratch memory in MB
        vram_total_mb: Total VRAM in MB
    
    Returns:
        MemoryContract with calculated values
    """
    # Calculate KV cache size (simplified formula: 1024 MB per 8192 context)
    kv_ceiling_mb = int(n_ctx / 8192 * 1024)

    # Calculate vector DB floor
    vector_floor_mb = vram_total_mb - weights_mb - kv_ceiling_mb - scratch_mb
    
    return MemoryContract(
        weights_mb=weights_mb,
        kv_ceiling_mb=kv_ceiling_mb,
        scratch_mb=scratch_mb,
        vector_floor_mb=max(0, vector_floor_mb),
        vector_max_mb=max(0, vram_total_mb - weights_mb - scratch_mb)
    )
