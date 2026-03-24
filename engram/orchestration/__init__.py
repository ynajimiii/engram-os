# ENGRAM OS — Multi-agent orchestration layer
# Three invariants:
#   1. Only orchestrator writes to shared board
#   2. Agents read filtered snapshots only
#   3. Handoffs require explicit acknowledgment

from engram.orchestration.signal import (
    AgentSignal,
    signal_from_writeback,
    serialize_signal,
)
from engram.orchestration.board import SharedBoard
from engram.orchestration.deadlock import (
    detect_deadlock,
    find_cycle,
    suggest_replan,
    is_queue_healthy,
)

__all__ = [
    "AgentSignal",
    "signal_from_writeback",
    "serialize_signal",
    "SharedBoard",
    "detect_deadlock",
    "find_cycle",
    "suggest_replan",
    "is_queue_healthy",
]
