"""
Planner - Task planning and decomposition.

Phase 08: Horizon
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class TaskStatus(Enum):
    """Status of a task."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(Enum):
    """Priority levels for tasks."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class Task:
    """A single task in a plan."""
    id: str
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.NORMAL
    dependencies: List[str] = field(default_factory=list)
    subtasks: List[str] = field(default_factory=list)
    result: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    blocked_by: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    @property
    def is_ready(self) -> bool:
        """Check if task is ready to execute (dependencies met)."""
        if self.status != TaskStatus.PENDING:
            return False
        return len(self.dependencies) == 0
    
    @property
    def is_complete(self) -> bool:
        """Check if task is completed."""
        return self.status == TaskStatus.COMPLETED


@dataclass
class Plan:
    """A plan containing tasks."""
    id: str
    title: str
    description: str = ""
    tasks: Dict[str, Task] = field(default_factory=dict)
    status: str = "active"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    
    @property
    def progress(self) -> float:
        """Calculate plan progress (0.0 to 1.0)."""
        if not self.tasks:
            return 0.0
        
        completed = sum(
            1 for t in self.tasks.values()
            if t.status == TaskStatus.COMPLETED
        )
        return completed / len(self.tasks)
    
    @property
    def is_complete(self) -> bool:
        """Check if all tasks are completed."""
        return all(
            t.status == TaskStatus.COMPLETED
            for t in self.tasks.values()
        ) if self.tasks else False


class Planner:
    """
    Task planner for breaking down goals into executable tasks.
    
    Phase 08: Basic planning with dependency tracking and
    task decomposition.
    """
    
    def __init__(self):
        self._plans: Dict[str, Plan] = {}
        self._task_counter: int = 0
    
    def create_plan(self, title: str, description: str = "",
                    metadata: Optional[Dict[str, Any]] = None) -> Plan:
        """Create a new plan."""
        plan = Plan(
            id=f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            title=title,
            description=description,
            metadata=metadata or {},
        )
        self._plans[plan.id] = plan
        return plan
    
    def add_task(self, plan_id: str, title: str,
                 description: str = "",
                 dependencies: Optional[List[str]] = None,
                 priority: TaskPriority = TaskPriority.NORMAL,
                 metadata: Optional[Dict[str, Any]] = None) -> Task:
        """
        Add a task to a plan.
        
        Args:
            plan_id: ID of the plan to add to
            title: Task title
            description: Task description
            dependencies: List of task IDs this task depends on
            priority: Task priority
            metadata: Optional metadata
        
        Returns:
            The created Task
        """
        plan = self._plans.get(plan_id)
        if plan is None:
            raise ValueError(f"Plan not found: {plan_id}")
        
        self._task_counter += 1
        task_id = f"task_{self._task_counter}"
        
        task = Task(
            id=task_id,
            title=title,
            description=description,
            dependencies=dependencies or [],
            priority=priority,
            metadata=metadata or {},
        )
        
        plan.tasks[task_id] = task
        return task
    
    def add_subtasks(self, plan_id: str, parent_task_id: str,
                     subtasks: List[Dict[str, Any]]) -> List[Task]:
        """
        Add subtasks to an existing task.
        
        Args:
            plan_id: ID of the plan
            parent_task_id: ID of the parent task
            subtasks: List of subtask definitions
        
        Returns:
            List of created subtask Tasks
        """
        plan = self._plans.get(plan_id)
        if plan is None:
            raise ValueError(f"Plan not found: {plan_id}")
        
        parent = plan.tasks.get(parent_task_id)
        if parent is None:
            raise ValueError(f"Task not found: {parent_task_id}")
        
        created_tasks = []
        for subtask_def in subtasks:
            subtask = self.add_task(
                plan_id,
                title=subtask_def.get("title", "Subtask"),
                description=subtask_def.get("description", ""),
                dependencies=[parent_task_id],  # Depend on parent
                priority=subtask_def.get("priority", TaskPriority.NORMAL),
                metadata=subtask_def.get("metadata", {}),
            )
            parent.subtasks.append(subtask.id)
            created_tasks.append(subtask)
        
        return created_tasks
    
    def start_task(self, plan_id: str, task_id: str) -> bool:
        """Mark a task as in progress."""
        plan = self._plans.get(plan_id)
        if plan is None:
            return False

        task = plan.tasks.get(task_id)
        if task is None:
            return False

        # Check dependencies
        unmet = [
            dep for dep in task.dependencies
            if plan.tasks.get(dep) is None or plan.tasks.get(dep).status != TaskStatus.COMPLETED
        ]
        if unmet:
            task.status = TaskStatus.BLOCKED
            task.blocked_by = unmet
            import logging
            logging.info(
                f"[ENGRAM] planner — task '{task_id}' blocked by: {unmet}"
            )
            return False

        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.now()
        return True
    
    def complete_task(self, plan_id: str, task_id: str,
                      result: Optional[str] = None) -> bool:
        """Mark a task as completed."""
        plan = self._plans.get(plan_id)
        if plan is None:
            return False
        
        task = plan.tasks.get(task_id)
        if task is None:
            return False
        
        task.status = TaskStatus.COMPLETED
        task.result = result
        task.completed_at = datetime.now()
        
        # Check if plan is complete
        if plan.is_complete:
            plan.status = "completed"
            plan.completed_at = datetime.now()
        
        return True
    
    def fail_task(self, plan_id: str, task_id: str,
                  reason: str) -> bool:
        """Mark a task as failed."""
        plan = self._plans.get(plan_id)
        if plan is None:
            return False
        
        task = plan.tasks.get(task_id)
        if task is None:
            return False
        
        task.status = TaskStatus.FAILED
        task.result = f"Failed: {reason}"
        task.completed_at = datetime.now()
        
        # Block dependent tasks
        for other_task in plan.tasks.values():
            if task_id in other_task.dependencies:
                other_task.status = TaskStatus.BLOCKED
        
        return True
    
    def get_next_task(self, plan_id: str) -> Optional[Task]:
        """Get the next ready task to execute."""
        plan = self._plans.get(plan_id)
        if plan is None:
            return None
        
        # Find ready tasks by priority
        ready_tasks = [
            t for t in plan.tasks.values()
            if t.is_ready
        ]
        
        if not ready_tasks:
            return None
        
        # Sort by priority (highest first)
        ready_tasks.sort(key=lambda t: t.priority.value, reverse=True)
        
        return ready_tasks[0]
    
    def get_plan(self, plan_id: str) -> Optional[Plan]:
        """Get a plan by ID."""
        return self._plans.get(plan_id)
    
    def get_plan_status(self, plan_id: str) -> Dict[str, Any]:
        """Get detailed plan status."""
        plan = self._plans.get(plan_id)
        if plan is None:
            return {}
        
        status_counts = {}
        for task in plan.tasks.values():
            status = task.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return {
            "plan_id": plan_id,
            "title": plan.title,
            "status": plan.status,
            "progress": plan.progress,
            "total_tasks": len(plan.tasks),
            "task_status": status_counts,
            "is_complete": plan.is_complete,
        }
    
    def list_plans(self) -> List[str]:
        """List all plan IDs."""
        return list(self._plans.keys())
    
    def decompose_goal(self, goal: str, max_depth: int = 3) -> Plan:
        """
        Decompose a high-level goal into a plan.
        
        Phase 08: Basic decomposition - creates a simple plan structure.
        Future versions may use LLM for intelligent decomposition.
        """
        plan = self.create_plan(
            title=f"Goal: {goal[:50]}...",
            description=f"Plan to achieve: {goal}",
        )
        
        # Basic decomposition template
        phases = [
            ("Analysis", "Analyze the goal and requirements"),
            ("Planning", "Create detailed approach"),
            ("Execution", "Execute the plan"),
            ("Review", "Review and validate results"),
        ]
        
        prev_task_id = None
        for phase_title, phase_desc in phases:
            task = self.add_task(
                plan.id,
                title=phase_title,
                description=phase_desc,
                dependencies=[prev_task_id] if prev_task_id else [],
            )
            prev_task_id = task.id
        
        return plan


class TaskExecutor:
    """
    Executes tasks from a plan.
    
    Phase 08: Basic execution with callback-based task handling.
    """
    
    def __init__(self, planner: Planner):
        self.planner = planner
        self._handlers: Dict[str, callable] = {}
        self._current_plan: Optional[str] = None
    
    def register_handler(self, task_type: str,
                         handler: Callable[[Task], Any]) -> None:
        """Register a handler for a task type."""
        self._handlers[task_type] = handler
    
    def execute_plan(self, plan_id: str) -> Dict[str, Any]:
        """
        Execute all tasks in a plan.
        
        Args:
            plan_id: ID of the plan to execute
        
        Returns:
            Execution results
        """
        self._current_plan = plan_id
        results = {}
        
        while True:
            task = self.planner.get_next_task(plan_id)
            if task is None:
                break
            
            # Start the task
            if not self.planner.start_task(plan_id, task.id):
                # Task is blocked
                results[task.id] = {"status": "blocked"}
                continue
            
            # Execute the task
            try:
                handler = self._get_handler_for_task(task)
                if handler:
                    result = handler(task)
                    self.planner.complete_task(plan_id, task.id, str(result))
                    results[task.id] = {"status": "completed", "result": result}
                else:
                    # No handler - mark as completed anyway
                    self.planner.complete_task(plan_id, task.id, "No handler available")
                    results[task.id] = {"status": "completed", "result": "No handler"}
            except Exception as e:
                self.planner.fail_task(plan_id, task.id, str(e))
                results[task.id] = {"status": "failed", "error": str(e)}
        
        return results
    
    def _get_handler_for_task(self, task: Task) -> Optional[Callable]:
        """Get the appropriate handler for a task."""
        task_type = task.metadata.get("type")
        if task_type and task_type in self._handlers:
            return self._handlers[task_type]
        return None
