# engram/orchestration/board.py
"""
SharedBoard — the cognitive workspace for all agents.

Three invariants enforced by this class:
  1. Only the orchestrator writes — agents call
     snapshot_for_agent(), never write directly.
  2. All writes are serialized via file lock.
  3. Decisions and signal_log are append-only forever.
"""

import yaml
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

# File locking — Linux/Mac only
try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False  # Windows — uses .lock file fallback

# Sections every agent sees regardless of domain
GLOBAL_SECTIONS = [
    "goal", "deadline", "progress",
    "decisions", "blockers",
]

# Conventions each domain is allowed to see
DOMAIN_CONVENTIONS = {
    "coding":    ["naming", "error_handling", "db_patterns"],
    "marketing": ["tone", "brand_voice", "audience"],
    "seo":       ["keywords", "structure", "intent"],
    "research":  ["citation", "methodology", "scope"],
    "orchestrator": [],  # orchestrator reads nothing from conventions
}


class SharedBoard:
    """
    The shared cognitive workspace for all agents.
    One writer (orchestrator), many filtered readers (agents).
    """

    def __init__(self, board_path: str | Path):
        self.path = Path(board_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._initialize()
        logging.info(f"[ENGRAM] SharedBoard: {self.path}")

    # ── Initialization ──────────────────────────────────────

    def _initialize(self) -> None:
        """Create empty board with required structure."""
        self._write_raw({
            "goal":           "",
            "deadline":       "",
            "progress":       0,
            "decisions":      [],
            "blockers":       [],
            "board": {
                "backlog":      [],
                "in_progress":  [],
                "review":       [],
                "done":         [],
            },
            "handoff_queue":  [],
            "conventions":    {},
            "signal_log":     [],
        })

    # ── Internal read/write ─────────────────────────────────

    def _read_raw(self) -> dict:
        """Read board YAML. Returns {} on any error."""
        try:
            with open(self.path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logging.error(f"[ENGRAM] board read failed: {e}")
            return {}

    def _write_raw(self, data: dict) -> None:
        """
        Write board YAML with file lock.
        THIS IS THE ONLY WRITE PATH.
        All public methods route through here.
        """
        lock_path = self.path.with_suffix(".lock")
        try:
            with open(lock_path, "w") as lock_file:
                if HAS_FCNTL:
                    fcntl.flock(
                        lock_file.fileno(), fcntl.LOCK_EX
                    )
                with open(
                    self.path, "w", encoding="utf-8"
                ) as f:
                    yaml.dump(
                        data, f,
                        default_flow_style=False,
                        allow_unicode=True,
                    )
                if HAS_FCNTL:
                    fcntl.flock(
                        lock_file.fileno(), fcntl.LOCK_UN
                    )
        except Exception as e:
            logging.error(f"[ENGRAM] board write failed: {e}")
            raise

    # ── Orchestrator write methods ──────────────────────────

    def apply_signal(
        self,
        signal,
        writer_id: str = "orchestrator",
    ) -> None:
        """
        Apply an AgentSignal to the shared board.
        ONLY the orchestrator should call this method.
        All updates are logged to signal_log (append-only).
        """
        from engram.orchestration.signal import serialize_signal

        board   = self._read_raw()
        updates = signal.board_updates

        # Resolve blockers
        for bid in updates.get("blockers_resolved", []):
            before = len(board.get("blockers", []))
            board["blockers"] = [
                b for b in board.get("blockers", [])
                if b.get("id") != bid
            ]
            if len(board.get("blockers", [])) < before:
                logging.info(
                    f"[ENGRAM] board: blocker {bid} "
                    f"resolved by {signal.agent_id}"
                )

        # Add conventions (never overwrite existing keys)
        conv = updates.get("conventions_learned")
        if conv:
            existing = board.setdefault("conventions", {})
            if isinstance(conv, dict):
                for k, v in conv.items():
                    if k not in existing:
                        existing[k] = v
            elif isinstance(conv, str) and conv:
                existing.setdefault("learned_notes", []).append(
                    conv
                )

        # Update milestone progress
        for k, v in updates.get(
            "milestone_progress", {}
        ).items():
            board.setdefault(
                "milestone_progress", {}
            )[k] = v

        # Queue handoff
        if signal.handoff:
            board.setdefault("handoff_queue", []).append({
                "from":         signal.agent_id,
                "to":           signal.handoff["to"],
                "task_id":      signal.task_id,
                "message":      signal.handoff.get("message",""),
                "requires_ack": signal.handoff.get(
                    "requires_ack", True
                ),
                "status":       "pending",
                "ts":           signal.timestamp,
            })
            logging.info(
                f"[ENGRAM] handoff queued: "
                f"{signal.agent_id} → {signal.handoff['to']} "
                f"task={signal.task_id}"
            )

        # Move task to done on kanban when status is done
        if signal.status == "done":
            b = board.get("board", {})
            for col in ("in_progress", "review", "backlog"):
                tasks = b.get(col, [])
                for i, task in enumerate(tasks):
                    if task.get("id") == signal.task_id:
                        b.setdefault("done", []).append(
                            tasks.pop(i)
                        )
                        logging.info(
                            f"[ENGRAM] task {signal.task_id} "
                            f"→ done"
                        )
                        break

        # Append to signal_log — APPEND ONLY, never truncate
        board.setdefault("signal_log", []).append(
            serialize_signal(signal)
        )

        self._write_raw(board)
        logging.info(
            f"[ENGRAM] board updated: writer={writer_id} "
            f"agent={signal.agent_id} task={signal.task_id}"
        )

    def acknowledge_handoff(
        self, task_id: str, agent_id: str
    ) -> None:
        """
        Mark a handoff as acknowledged.
        Called when the receiving agent reads
        and accepts the handoff.
        """
        board = self._read_raw()
        for h in board.get("handoff_queue", []):
            if (
                h.get("task_id") == task_id
                and h.get("to")      == agent_id
                and h.get("status")  == "pending"
            ):
                h["status"] = "acknowledged"
                h["ack_ts"] = datetime.utcnow().isoformat()
                self._write_raw(board)
                logging.info(
                    f"[ENGRAM] handoff ACK: "
                    f"task={task_id} agent={agent_id}"
                )
                return
        logging.warning(
            f"[ENGRAM] no pending handoff found: "
            f"task={task_id} agent={agent_id}"
        )

    def add_blocker(
        self,
        blocker_id: str,
        text: str,
        severity: str = "high",
        assigned: str = "",
    ) -> None:
        """Add a blocker. Orchestrator only."""
        board = self._read_raw()
        board.setdefault("blockers", []).append({
            "id":       blocker_id,
            "text":     text,
            "severity": severity,
            "assigned": assigned,
            "ts":       datetime.utcnow().isoformat(),
        })
        self._write_raw(board)

    def add_decision(
        self,
        text: str,
        made_by: str = "orchestrator",
    ) -> None:
        """Append a decision. Append-only — never modifiable."""
        board = self._read_raw()
        board.setdefault("decisions", []).append({
            "ts":   datetime.utcnow().isoformat(),
            "text": text,
            "by":   made_by,
        })
        self._write_raw(board)

    def update_progress(self, progress: int) -> None:
        """Update overall goal completion percentage."""
        board = self._read_raw()
        board["progress"] = max(0, min(100, int(progress)))
        self._write_raw(board)

    def move_task(
        self,
        task_id: str,
        from_col: str,
        to_col: str,
    ) -> bool:
        """Move a task between kanban columns."""
        board = self._read_raw()
        b = board.get("board", {})
        for i, task in enumerate(b.get(from_col, [])):
            if task.get("id") == task_id:
                b.setdefault(to_col, []).append(
                    b[from_col].pop(i)
                )
                self._write_raw(board)
                logging.info(
                    f"[ENGRAM] task {task_id}: "
                    f"{from_col} → {to_col}"
                )
                return True
        logging.warning(
            f"[ENGRAM] task {task_id} not found in {from_col}"
        )
        return False

    def set_goal(self, goal: str, deadline: str = "") -> None:
        """Set the team goal. Orchestrator only."""
        board = self._read_raw()
        board["goal"]     = goal
        board["deadline"] = deadline
        self._write_raw(board)

    # ── Agent read methods (filtered) ───────────────────────

    def snapshot_for_agent(
        self,
        agent_id: str,
        module_name: str = "coding",
    ) -> dict:
        """
        Return a filtered READ-ONLY snapshot for one agent.

        AGENTS SEE:
          - Goal, deadline, progress (global)
          - Decisions and blockers (global)
          - Current task board (so they understand deps)
          - Handoffs addressed TO this agent only
          - Conventions for their domain ONLY

        AGENTS NEVER SEE:
          - Other domains' conventions
          - The full signal_log
          - Other agents' private handoffs
          - Lock files or board internals
        """
        board = self._read_raw()

        # Global sections — all agents see these
        snapshot = {
            k: board.get(k)
            for k in GLOBAL_SECTIONS
            if k in board
        }

        # Full task board — agents need to see dependencies
        snapshot["board"] = board.get("board", {})

        # Only handoffs addressed TO this agent, pending only
        snapshot["my_handoffs"] = [
            h for h in board.get("handoff_queue", [])
            if (
                h.get("to")     == agent_id
                and h.get("status") == "pending"
            )
        ]

        # Conventions filtered strictly by domain
        all_conv    = board.get("conventions", {})
        domain_keys = DOMAIN_CONVENTIONS.get(
            module_name, []
        )
        if domain_keys:
            snapshot["conventions"] = {
                k: v for k, v in all_conv.items()
                if k in domain_keys
            }
        else:
            # Unknown domain — show nothing from conventions
            snapshot["conventions"] = {}

        return snapshot

    def is_handoff_acknowledged(
        self, task_id: str, to_agent: str
    ) -> bool:
        """Check if a specific handoff has been ACKed."""
        board = self._read_raw()
        for h in board.get("handoff_queue", []):
            if (
                h.get("task_id") == task_id
                and h.get("to")      == to_agent
            ):
                return h.get("status") == "acknowledged"
        return False

    def get_pending_handoff(
        self, to_agent: str, task_id: str
    ) -> Optional[dict]:
        """Get a pending handoff for an agent."""
        board = self._read_raw()
        for h in board.get("handoff_queue", []):
            if (
                h.get("to")      == to_agent
                and h.get("task_id") == task_id
                and h.get("status")  == "pending"
            ):
                return h
        return None

    def read_full(self) -> dict:
        """
        Full unfiltered board.
        ORCHESTRATOR ONLY. Never call from agent code.
        """
        return self._read_raw()
