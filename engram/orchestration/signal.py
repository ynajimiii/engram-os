# engram/orchestration/signal.py
"""
AgentSignal — structured output from one agent turn.

Agents NEVER write to the shared board directly.
They produce an AgentSignal which the orchestrator
reads and applies to the board.

This is the ONLY communication channel upward.
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
import logging


@dataclass
class AgentSignal:
    """Structured output from one complete agent turn."""

    agent_id: str
    task_id: str
    timestamp: str = field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )

    # Task outcome
    # done | in_progress | blocked | needs_handoff
    status: str = "done"

    # What the agent produced
    # [{"path": "file.py", "description": "..."}]
    deliverables: list = field(default_factory=list)

    # Handoff to another agent
    # {"to": "qa", "message": "...", "requires_ack": True}
    handoff: Optional[dict] = None

    # What the orchestrator should write to the shared board
    # {"blockers_resolved": [], "milestone_progress": {}}
    board_updates: dict = field(default_factory=dict)

    # Vector DB chunk IDs to evict after this turn
    evict: list = field(default_factory=list)

    # Full model response (for audit log)
    raw_response: str = ""

    # Quality score for this turn (0.0 = not scored)
    quality_score: float = 0.0

    # Error description if something failed
    error: Optional[str] = None


def signal_from_writeback(
    wb: Optional[dict],
    agent_id: str,
    task_id: str,
    raw_response: str = "",
    quality_score: float = 0.0,
) -> "AgentSignal":
    """
    Convert a parsed writeback block into an AgentSignal.

    This is the bridge between agent_turn() output
    and the orchestration layer.
    Called by the orchestrator after every agent turn.
    """
    if wb is None:
        return AgentSignal(
            agent_id=agent_id,
            task_id=task_id,
            status="done",
            raw_response=raw_response,
            quality_score=quality_score,
        )

    # Resolve status
    status = wb.get("status", "done")
    if status not in (
        "done", "in_progress", "blocked", "needs_handoff"
    ):
        status = "done"

    # Resolve deliverables from files_modified
    files = wb.get("files_modified", [])
    if isinstance(files, str):
        files = [f.strip() for f in files.split(",") if f.strip()]
    elif not isinstance(files, list):
        files = []
    deliverables = [
        {"path": f, "description": "modified"}
        for f in files
    ]

    # Resolve handoff
    handoff = None
    handoff_to = (
        wb.get("handoff_to")
        or wb.get("next_agent")
        or wb.get("handoff")
    )
    if handoff_to and isinstance(handoff_to, str):
        handoff = {
            "to": handoff_to.strip(),
            "message": wb.get("handoff_message", ""),
            "requires_ack": bool(wb.get("requires_ack", True)),
        }

    # Resolve board updates
    board_updates = {}

    resolved = wb.get("blockers_resolved", [])
    if resolved:
        if isinstance(resolved, str):
            resolved = [resolved]
        board_updates["blockers_resolved"] = resolved

    conv = wb.get("conventions_learned")
    if conv and conv not in ("null", "none", "None"):
        board_updates["conventions_learned"] = conv

    progress = wb.get("milestone_progress")
    if progress and isinstance(progress, dict):
        board_updates["milestone_progress"] = progress

    # Resolve evict list
    evict = wb.get("evict", [])
    if isinstance(evict, str):
        if evict.lower() in ("[]", "none", "null", ""):
            evict = []
        else:
            evict = [
                e.strip().strip("[]'\"")
                for e in evict.split(",")
                if e.strip().strip("[]'\"")
            ]
    elif not isinstance(evict, list):
        evict = []

    return AgentSignal(
        agent_id=agent_id,
        task_id=task_id,
        status=status,
        deliverables=deliverables,
        handoff=handoff,
        board_updates=board_updates,
        evict=evict,
        raw_response=raw_response,
        quality_score=quality_score,
    )


def serialize_signal(signal: "AgentSignal") -> dict:
    """Convert AgentSignal to plain dict for YAML/logging."""
    return {
        "agent_id": signal.agent_id,
        "task_id": signal.task_id,
        "timestamp": signal.timestamp,
        "status": signal.status,
        "deliverables": signal.deliverables,
        "handoff": signal.handoff,
        "board_updates": signal.board_updates,
        "evict": signal.evict,
        "quality_score": signal.quality_score,
        "error": signal.error,
    }
