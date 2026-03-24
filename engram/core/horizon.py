"""
Horizon - Long-horizon task execution and monitoring.

Phase 08: Horizon
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .planner import Planner, Plan, Task, TaskStatus, TaskPriority, TaskExecutor

# Orchestration layer imports (Phase 10)
try:
    from engram.orchestration.signal import (
        signal_from_writeback,
        AgentSignal,
    )
    from engram.orchestration.board import SharedBoard
    from engram.orchestration.deadlock import (
        detect_deadlock,
        find_cycle,
        suggest_replan,
        is_queue_healthy,
    )
    HAS_ORCHESTRATION = True
except ImportError:
    HAS_ORCHESTRATION = False
    import logging as _log
    _log.warning(
        "[ENGRAM] orchestration layer not available — "
        "running in single-agent mode"
    )


class HorizonStatus(Enum):
    """Status of a horizon."""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"


@dataclass
class Milestone:
    """A milestone in a long-horizon goal."""
    id: str
    title: str
    description: str = ""
    due_date: Optional[datetime] = None
    completed: bool = False
    completed_at: Optional[datetime] = None
    linked_task_ids: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Horizon:
    """
    A long-horizon goal with milestones and progress tracking.
    """
    id: str
    title: str
    description: str = ""
    status: HorizonStatus = HorizonStatus.ACTIVE
    milestones: Dict[str, Milestone] = field(default_factory=dict)
    plan_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    target_date: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def progress(self) -> float:
        """Calculate horizon progress based on milestones."""
        if not self.milestones:
            return 0.0
        
        completed = sum(1 for m in self.milestones.values() if m.completed)
        return completed / len(self.milestones)
    
    @property
    def is_complete(self) -> bool:
        """Check if all milestones are completed."""
        return all(m.completed for m in self.milestones.values()) if self.milestones else False
    
    @property
    def days_remaining(self) -> Optional[int]:
        """Calculate days remaining until target date."""
        if self.target_date is None:
            return None
        
        delta = self.target_date - datetime.now()
        return max(0, delta.days)


@dataclass
class Checkpoint:
    """A progress checkpoint."""
    timestamp: datetime
    horizon_id: str
    progress: float
    completed_milestones: List[str] = field(default_factory=list)
    pending_milestones: List[str] = field(default_factory=list)
    notes: str = ""


class HorizonManager:
    """
    Manages long-horizon goals and execution.
    
    Phase 08: Horizon tracking with milestone-based progress.
    """
    
    def __init__(self, planner: Optional[Planner] = None):
        self._horizons: Dict[str, Horizon] = {}
        self._planner = planner or Planner()
        self._checkpoints: Dict[str, List[Checkpoint]] = {}
        self._on_milestone_complete: Optional[Callable[[str, Milestone], None]] = None
    
    def create_horizon(self, title: str, description: str = "",
                       target_date: Optional[datetime] = None,
                       metadata: Optional[Dict[str, Any]] = None) -> Horizon:
        """Create a new long-horizon goal."""
        import uuid
        horizon = Horizon(
            id=f"horizon_{uuid.uuid4().hex[:12]}",
            title=title,
            description=description,
            target_date=target_date,
            metadata=metadata or {},
        )
        self._horizons[horizon.id] = horizon
        self._checkpoints[horizon.id] = []

        return horizon
    
    def add_milestone(self, horizon_id: str, title: str,
                      description: str = "",
                      due_date: Optional[datetime] = None,
                      linked_task_ids: Optional[List[str]] = None,
                      metadata: Optional[Dict[str, Any]] = None) -> Milestone:
        """Add a milestone to a horizon."""
        horizon = self._horizons.get(horizon_id)
        if horizon is None:
            raise ValueError(f"Horizon not found: {horizon_id}")
        
        milestone = Milestone(
            id=f"milestone_{len(horizon.milestones) + 1}",
            title=title,
            description=description,
            due_date=due_date,
            linked_task_ids=linked_task_ids or [],
            metadata=metadata or {},
        )
        
        horizon.milestones[milestone.id] = milestone
        return milestone
    
    def link_plan(self, horizon_id: str, plan_id: str) -> bool:
        """Link a plan to a horizon."""
        horizon = self._horizons.get(horizon_id)
        if horizon is None:
            return False
        
        horizon.plan_id = plan_id
        return True
    
    def complete_milestone(self, horizon_id: str, milestone_id: str) -> bool:
        """Mark a milestone as completed."""
        horizon = self._horizons.get(horizon_id)
        if horizon is None:
            return False
        
        milestone = horizon.milestones.get(milestone_id)
        if milestone is None:
            return False
        
        milestone.completed = True
        milestone.completed_at = datetime.now()

        # Record checkpoint
        self._record_checkpoint(horizon)

        # Trigger callback
        if self._on_milestone_complete:
            self._on_milestone_complete(horizon_id, milestone)

        # Check if horizon is complete
        if horizon.is_complete:
            horizon.status = HorizonStatus.COMPLETED
            horizon.completed_at = datetime.now()

        # Save checkpoint to disk before returning
        try:
            self._save_checkpoint()
        except Exception as e:
            import logging
            logging.warning(
                f"[ENGRAM] horizon — checkpoint save failed after milestone "
                f"'{milestone_id}': {e}. Progress is in memory but not persisted."
            )

        return True
    
    def get_horizon(self, horizon_id: str) -> Optional[Horizon]:
        """Get a horizon by ID."""
        return self._horizons.get(horizon_id)
    
    def get_progress(self, horizon_id: str) -> Dict[str, Any]:
        """Get detailed progress for a horizon."""
        horizon = self._horizons.get(horizon_id)
        if horizon is None:
            return {}
        
        completed = [m for m in horizon.milestones.values() if m.completed]
        pending = [m for m in horizon.milestones.values() if not m.completed]
        overdue = [
            m for m in pending
            if m.due_date and m.due_date < datetime.now()
        ]
        
        return {
            "horizon_id": horizon_id,
            "title": horizon.title,
            "status": horizon.status.value,
            "progress": horizon.progress,
            "total_milestones": len(horizon.milestones),
            "completed_milestones": len(completed),
            "pending_milestones": len(pending),
            "overdue_milestones": len(overdue),
            "days_remaining": horizon.days_remaining,
            "is_complete": horizon.is_complete,
        }

    def _save_checkpoint(self) -> None:
        """Persist current horizon state to disk."""
        import yaml
        from pathlib import Path

        horizons_dir = Path("engram/sessions/horizons")
        try:
            horizons_dir.mkdir(parents=True, exist_ok=True)
            for horizon_id, horizon in self._horizons.items():
                data = {
                    "id": horizon.id,
                    "title": horizon.title,
                    "status": horizon.status.value,
                    "milestones": {
                        mid: {
                            "id": m.id,
                            "title": m.title,
                            "completed": m.completed,
                            "completed_at": m.completed_at.isoformat() if m.completed_at else None,
                        }
                        for mid, m in horizon.milestones.items()
                    },
                    "progress": horizon.progress,
                    "completed_at": horizon.completed_at.isoformat() if horizon.completed_at else None,
                }
                filepath = horizons_dir / f"{horizon_id}.yaml"
                with open(filepath, "w", encoding="utf-8") as f:
                    yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
        except Exception as e:
            import logging
            logging.warning(
                f"[ENGRAM] horizon — _save_checkpoint failed: {e}. "
                f"Progress is in memory but not written to disk."
            )

    def list_horizons(self, status: Optional[HorizonStatus] = None) -> List[str]:
        """List horizon IDs, optionally filtered by status."""
        if status is None:
            return list(self._horizons.keys())
        
        return [
            h.id for h in self._horizons.values()
            if h.status == status
        ]
    
    def pause_horizon(self, horizon_id: str) -> bool:
        """Pause a horizon."""
        horizon = self._horizons.get(horizon_id)
        if horizon is None:
            return False
        
        horizon.status = HorizonStatus.PAUSED
        return True
    
    def resume_horizon(self, horizon_id: str) -> bool:
        """Resume a paused horizon."""
        horizon = self._horizons.get(horizon_id)
        if horizon is None:
            return False
        
        if horizon.status == HorizonStatus.PAUSED:
            horizon.status = HorizonStatus.ACTIVE
        
        return True
    
    def abandon_horizon(self, horizon_id: str, reason: str = "") -> bool:
        """Abandon a horizon."""
        horizon = self._horizons.get(horizon_id)
        if horizon is None:
            return False
        
        horizon.status = HorizonStatus.ABANDONED
        horizon.metadata["abandon_reason"] = reason
        horizon.metadata["abandoned_at"] = datetime.now().isoformat()
        
        return True
    
    def _record_checkpoint(self, horizon: Horizon) -> None:
        """Record a progress checkpoint."""
        completed = [m.id for m in horizon.milestones.values() if m.completed]
        pending = [m.id for m in horizon.milestones.values() if not m.completed]
        
        checkpoint = Checkpoint(
            timestamp=datetime.now(),
            horizon_id=horizon.id,
            progress=horizon.progress,
            completed_milestones=completed,
            pending_milestones=pending,
        )
        
        self._checkpoints[horizon.id].append(checkpoint)
    
    def get_history(self, horizon_id: str) -> List[Checkpoint]:
        """Get checkpoint history for a horizon."""
        return list(self._checkpoints.get(horizon_id, []))
    
    def on_milestone_complete(self, callback: Callable[[str, Milestone], None]) -> None:
        """Register a callback for milestone completion."""
        self._on_milestone_complete = callback


class HorizonExecutor:
    """
    Executes long-horizon goals with monitoring.
    
    Phase 08: Basic execution with progress tracking.
    """
    
    def __init__(self, horizon_manager: HorizonManager,
                 task_executor: Optional[TaskExecutor] = None):
        self.horizon_manager = horizon_manager
        self.task_executor = task_executor or TaskExecutor(horizon_manager._planner)
        self._running_horizons: Set[str] = set()
    
    def execute_horizon(self, horizon_id: str) -> Dict[str, Any]:
        """
        Execute a horizon's linked plan.
        
        Args:
            horizon_id: ID of the horizon to execute
        
        Returns:
            Execution results
        """
        horizon = self.horizon_manager.get_horizon(horizon_id)
        if horizon is None:
            return {"error": "Horizon not found"}
        
        if horizon.plan_id is None:
            return {"error": "No plan linked to horizon"}
        
        self._running_horizons.add(horizon_id)
        
        # Execute the linked plan
        results = self.task_executor.execute_plan(horizon.plan_id)
        
        self._running_horizons.discard(horizon_id)
        
        # Update horizon status based on plan completion
        plan = self.horizon_manager._planner.get_plan(horizon.plan_id)
        if plan and plan.is_complete:
            # Mark all milestones as completed
            for milestone_id in horizon.milestones:
                self.horizon_manager.complete_milestone(horizon_id, milestone_id)
        
        return {
            "horizon_id": horizon_id,
            "plan_results": results,
            "final_progress": horizon.progress,
        }
    
    def get_running_horizons(self) -> List[str]:
        """Get list of currently running horizons."""
        return list(self._running_horizons)


class ProgressTracker:
    """
    Tracks and reports progress on horizons.
    
    Phase 08: Progress tracking with milestone visualization.
    """
    
    def __init__(self, horizon_manager: HorizonManager):
        self.horizon_manager = horizon_manager
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all horizons."""
        horizons = self.horizon_manager._horizons.values()
        
        by_status = {}
        for h in horizons:
            status = h.status.value
            by_status[status] = by_status.get(status, 0) + 1
        
        total_progress = sum(h.progress for h in horizons) / len(horizons) if horizons else 0
        
        return {
            "total_horizons": len(horizons),
            "by_status": by_status,
            "average_progress": total_progress,
            "completed": sum(1 for h in horizons if h.is_complete),
        }
    
    def get_visual_progress(self, horizon_id: str, width: int = 20) -> str:
        """Get visual progress bar for a horizon."""
        horizon = self.horizon_manager.get_horizon(horizon_id)
        if horizon is None:
            return "Horizon not found"
        
        progress = horizon.progress
        filled = int(progress * width)
        empty = width - filled
        
        bar = "█" * filled + "░" * empty
        pct = f"{progress * 100:.0f}%"
        
        return f"[{bar}] {pct}"
    
    def get_upcoming_deadlines(self, days: int = 7) -> List[Dict[str, Any]]:
        """Get milestones with upcoming deadlines."""
        upcoming = []
        deadline = datetime.now() + timedelta(days=days)
        
        for horizon in self.horizon_manager._horizons.values():
            for milestone in horizon.milestones.values():
                if milestone.completed:
                    continue
                if milestone.due_date and milestone.due_date <= deadline:
                    upcoming.append({
                        "horizon_id": horizon.id,
                        "horizon_title": horizon.title,
                        "milestone_id": milestone.id,
                        "milestone_title": milestone.title,
                        "due_date": milestone.due_date.isoformat(),
                        "days_remaining": (milestone.due_date - datetime.now()).days,
                    })
        
        # Sort by due date
        upcoming.sort(key=lambda x: x["due_date"])
        
        return upcoming
    
    def generate_report(self, horizon_id: str) -> str:
        """Generate a text report for a horizon."""
        progress = self.horizon_manager.get_progress(horizon_id)
        
        if not progress:
            return "Horizon not found"
        
        lines = [
            f"Horizon Report: {progress.get('title', 'Unknown')}",
            "=" * 50,
            f"Status: {progress.get('status', 'unknown')}",
            f"Progress: {self.get_visual_progress(horizon_id)}",
            f"Completed: {progress.get('completed_milestones', 0)}/{progress.get('total_milestones', 0)} milestones",
        ]
        
        if progress.get('days_remaining') is not None:
            lines.append(f"Days Remaining: {progress['days_remaining']}")
        
        if progress.get('overdue_milestones', 0) > 0:
            lines.append(f"⚠️  Overdue: {progress['overdue_milestones']} milestones")

        return "\n".join(lines)


def run_long_horizon(
    goal: str,
    project_name: str,
    shared_board_path: str = None,
    weights_mb: int = 15000,
    n_ctx: int = 8192,
    scratch_mb: int = 512,
) -> str:
    """
    Execute a long-horizon goal with multi-agent orchestration.

    Args:
        goal: The goal to accomplish
        project_name: Name of the project
        shared_board_path: Path to shared board YAML file
        weights_mb: Model weights size in MB
        n_ctx: Context length
        scratch_mb: Scratch memory in MB

    Returns:
        Final status message
    """
    import logging
    from engram.core.boot import boot_system
    from engram.core.planner import goal_to_task_graph, TaskQueue
    from engram.core.agent import agent_turn
    from engram.core.writeback import parse_writeback, apply_writeback
    from engram.core.scratch import Scratch

    # Boot system
    contract, db = boot_system(
        weights_mb=weights_mb,
        n_ctx=n_ctx,
        scratch_mb=scratch_mb,
    )

    # Initialize SharedBoard if orchestration enabled
    board = None
    if shared_board_path and HAS_ORCHESTRATION:
        board = SharedBoard(shared_board_path)
        board.set_goal(goal)
        logging.info(
            f"[ENGRAM] SharedBoard loaded: "
            f"{shared_board_path}"
        )

    # Create scratch note
    scratch = Scratch(session_id=project_name)
    scratch.set("project_name", project_name)
    scratch.set("active_task", {"objective": goal})
    scratch.save()

    # Generate task graph
    try:
        tasks = goal_to_task_graph(goal, str(scratch.scratch_dir))
        queue = TaskQueue(tasks)
        logging.info(f"[ENGRAM] {len(tasks)} tasks planned")
    except Exception as e:
        logging.error(f"[ENGRAM] planning failed: {e}")
        return f"Planning failed: {e}"

    domain = "coding"  # Default domain for single-agent mode
    completed_tasks = []

    # Main execution loop
    while True:
        task = queue.next_task()
        if task is None:
            # Check for deadlock if orchestration enabled
            if HAS_ORCHESTRATION:
                deadlocked = detect_deadlock(queue.pending)
                if deadlocked:
                    cycle = find_cycle(queue.pending)
                    suggestions = suggest_replan(
                        queue.pending,
                        queue.completed,
                        deadlocked,
                    )
                    logging.error(
                        f"[ENGRAM] deadlock: "
                        f"{suggestions['actions']}"
                    )
                    if cycle:
                        logging.error(
                            f"[ENGRAM] cycle: "
                            f"{' → '.join(cycle)}"
                        )
            logging.warning(
                "[ENGRAM] queue exhausted or deadlocked"
            )
            break

        logging.info(
            f"[ENGRAM] executing task: {task.get('id', '?')} — "
            f"{task.get('objective', '?')[:50]}"
        )

        # Execute agent turn
        try:
            response = agent_turn(
                task_text=task.get("objective", ""),
                db=db,
                scratch=scratch,
                contract=contract,
                stones=None,
                session_path=str(scratch.scratch_dir / f"{task.get('id', 'task')}.yaml"),
                mcp_client=None,
            )

            # Process signal through orchestration layer
            if board and HAS_ORCHESTRATION:
                try:
                    wb  = parse_writeback(response)
                    sig = signal_from_writeback(
                        wb,
                        agent_id=domain,
                        task_id=task.get("id", "unknown"),
                        raw_response=response,
                    )
                    board.apply_signal(sig)

                    # Apply writeback to scratch
                    evict_ids = apply_writeback(wb, scratch, str(scratch.scratch_dir))
                    for chunk_id in evict_ids:
                        if db and hasattr(db, 'demote'):
                            db.demote(chunk_id)

                    # Wait for handoff ACK if required
                    if (
                        sig.handoff
                        and sig.handoff.get("requires_ack")
                    ):
                        import time
                        to_agent  = sig.handoff["to"]
                        task_id   = task.get("id", "")
                        max_wait  = 30
                        waited    = 0
                        while (
                            not board.is_handoff_acknowledged(
                                task_id, to_agent
                            )
                            and waited < max_wait
                        ):
                            time.sleep(2)
                            waited += 2
                        if waited >= max_wait:
                            logging.warning(
                                f"[ENGRAM] handoff ACK timeout: "
                                f"task={task_id} to={to_agent}"
                            )
                except Exception as _sig_err:
                    logging.warning(
                        f"[ENGRAM] signal processing failed: "
                        f"{_sig_err}"
                    )

            queue.mark_done(task.get("id"))
            completed_tasks.append(task.get("id"))
            logging.info(f"[ENGRAM] task {task.get('id')} completed")

        except Exception as e:
            logging.error(f"[ENGRAM] task failed: {e}")
            queue.mark_blocked(task.get("id"))
            break

    scratch.save()
    return f"Horizon complete: {len(completed_tasks)} tasks done"
