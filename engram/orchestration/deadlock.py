# engram/orchestration/deadlock.py
"""
Deadlock detection for the ENGRAM task queue.

A deadlock occurs when a set of tasks all depend on each
other with no possible execution order. This module detects
deadlocks, finds the exact cycle, and suggests how to replan.
"""

import logging
from typing import Optional


def detect_deadlock(pending: dict) -> list:
    """
    Find tasks that are deadlocked.

    A task is deadlocked if it has dependencies that form a cycle -
    meaning the task cannot run because its dependencies cannot run.

    Args:
        pending: {task_id: task_dict} where task_dict
                 has a 'depends_on' list field

    Returns:
        List of deadlocked task IDs.
        Empty list if no deadlock.
    """
    if not pending:
        return []

    # Use find_cycle to detect actual circular dependencies
    cycle = find_cycle(pending)
    if not cycle:
        return []

    # All tasks in the cycle are deadlocked
    deadlocked = list(set(cycle[:-1]))  # Remove duplicate last element

    if deadlocked:
        logging.error(
            f"[ENGRAM] DEADLOCK: {deadlocked} — "
            f"circular dependency detected"
        )

    return deadlocked


def find_cycle(pending: dict) -> Optional[list]:
    """
    Find the exact circular dependency chain using DFS.

    Returns the cycle as an ordered list of task IDs,
    e.g. ['T1', 'T2', 'T3', 'T1'] for a 3-task cycle.
    Returns None if no cycle exists.

    Args:
        pending: {task_id: task_dict}
    """
    if not pending:
        return None

    visited  = set()
    path     = []
    path_set = set()

    def dfs(task_id: str) -> Optional[list]:
        if task_id in path_set:
            idx = path.index(task_id)
            return path[idx:] + [task_id]
        if task_id in visited:
            return None
        if task_id not in pending:
            return None

        visited.add(task_id)
        path.append(task_id)
        path_set.add(task_id)

        for dep in pending[task_id].get("depends_on", []):
            result = dfs(dep)
            if result:
                return result

        path.pop()
        path_set.discard(task_id)
        return None

    for task_id in pending:
        result = dfs(task_id)
        if result:
            logging.error(
                f"[ENGRAM] cycle: {' → '.join(result)}"
            )
            return result

    return None


def suggest_replan(
    pending: dict,
    completed: set,
    deadlocked: list,
) -> dict:
    """
    Given a deadlock, suggest resolution actions.

    Args:
        pending:    remaining pending tasks
        completed:  set of completed task IDs
        deadlocked: list of deadlocked task IDs

    Returns:
        Dict with deadlocked_tasks, completed_tasks,
        and actions list with per-task suggestions.
    """
    actions = []

    for task_id in deadlocked:
        task    = pending.get(task_id, {})
        deps    = task.get("depends_on", [])
        unmet   = [d for d in deps if d in pending]
        met     = [d for d in deps if d in completed]

        if unmet:
            suggestion = (
                f"Remove dependency on {unmet} "
                f"OR complete {unmet[0]} first "
                f"OR reorder task graph"
            )
        else:
            suggestion = (
                f"Task has no unmet deps in pending "
                f"— likely a circular reference. "
                f"Run find_cycle() to identify."
            )

        actions.append({
            "task":       task_id,
            "title":      task.get("title", "?"),
            "unmet_deps": unmet,
            "met_deps":   met,
            "suggestion": suggestion,
        })

    return {
        "deadlocked_tasks": deadlocked,
        "completed_tasks":  list(completed),
        "pending_count":    len(pending),
        "actions":          actions,
    }


def is_queue_healthy(pending: dict, completed: set) -> bool:
    """
    Quick check — returns True if queue can make progress.
    Returns False if deadlocked.

    Use this as a fast guard before expensive detection.
    """
    if not pending:
        return True  # empty queue = complete

    for task_id, task in pending.items():
        deps = set(task.get("depends_on", []))
        # This task can run if all deps are completed
        if deps.issubset(completed):
            return True  # at least one task can run

    return False  # nothing can run = deadlock
