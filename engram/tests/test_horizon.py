"""
Tests for horizon.py - Long-horizon task execution and monitoring.

Phase 09: Testing
"""

import pytest
from datetime import datetime, timedelta
from engram.core.horizon import (
    HorizonManager,
    Horizon,
    HorizonStatus,
    Milestone,
    ProgressTracker,
)
from engram.core.planner import Planner


class TestHorizon:
    """Tests for Horizon dataclass."""

    def test_horizon_creation(self):
        """Test creating a horizon."""
        horizon = Horizon(
            id="h1",
            title="Test Horizon",
            description="A test horizon",
        )
        
        assert horizon.title == "Test Horizon"
        assert horizon.status == HorizonStatus.ACTIVE
        assert horizon.progress == 0.0
        assert horizon.is_complete is False

    def test_horizon_with_target_date(self):
        """Test horizon with target date."""
        target = datetime.now() + timedelta(days=30)
        
        horizon = Horizon(
            id="h1",
            title="Test",
            target_date=target,
        )
        
        assert horizon.days_remaining is not None
        assert horizon.days_remaining <= 30

    def test_horizon_progress_no_milestones(self):
        """Test progress calculation with no milestones."""
        horizon = Horizon(id="h1", title="Test")
        
        assert horizon.progress == 0.0


class TestHorizonManager:
    """Tests for HorizonManager class."""

    def test_manager_creation(self):
        """Test creating a horizon manager."""
        manager = HorizonManager()
        
        assert manager.list_horizons() == []

    def test_create_horizon(self):
        """Test creating a horizon through manager."""
        manager = HorizonManager()
        
        horizon = manager.create_horizon(
            title="New Horizon",
            description="Test description",
        )
        
        assert horizon.id in manager.list_horizons()
        assert horizon.title == "New Horizon"

    def test_add_milestone(self):
        """Test adding a milestone to a horizon."""
        manager = HorizonManager()
        
        horizon = manager.create_horizon(title="Test")
        
        milestone = manager.add_milestone(
            horizon.id,
            title="Milestone 1",
            description="First milestone",
        )
        
        assert milestone.id in horizon.milestones
        assert milestone.title == "Milestone 1"

    def test_complete_milestone(self):
        """Test completing a milestone."""
        manager = HorizonManager()
        
        horizon = manager.create_horizon(title="Test")
        milestone = manager.add_milestone(horizon.id, title="M1")
        
        result = manager.complete_milestone(horizon.id, milestone.id)
        
        assert result is True
        assert milestone.completed is True
        assert milestone.completed_at is not None

    def test_complete_milestone_invalid(self):
        """Test completing non-existent milestone."""
        manager = HorizonManager()
        
        horizon = manager.create_horizon(title="Test")
        
        result = manager.complete_milestone(horizon.id, "nonexistent")
        
        assert result is False

    def test_get_progress(self):
        """Test getting horizon progress."""
        manager = HorizonManager()
        
        horizon = manager.create_horizon(title="Test")
        manager.add_milestone(horizon.id, title="M1")
        manager.add_milestone(horizon.id, title="M2")
        
        progress = manager.get_progress(horizon.id)
        
        assert progress["total_milestones"] == 2
        assert progress["completed_milestones"] == 0
        assert progress["progress"] == 0.0

    def test_get_progress_after_completion(self):
        """Test progress after completing milestones."""
        manager = HorizonManager()
        
        horizon = manager.create_horizon(title="Test")
        m1 = manager.add_milestone(horizon.id, title="M1")
        m2 = manager.add_milestone(horizon.id, title="M2")
        
        manager.complete_milestone(horizon.id, m1.id)
        
        progress = manager.get_progress(horizon.id)
        
        assert progress["completed_milestones"] == 1
        assert progress["progress"] == 0.5

    def test_horizon_completion(self):
        """Test horizon auto-completion when all milestones done."""
        manager = HorizonManager()
        
        horizon = manager.create_horizon(title="Test")
        m1 = manager.add_milestone(horizon.id, title="M1")
        m2 = manager.add_milestone(horizon.id, title="M2")
        
        manager.complete_milestone(horizon.id, m1.id)
        manager.complete_milestone(horizon.id, m2.id)
        
        assert horizon.is_complete is True
        assert horizon.status == HorizonStatus.COMPLETED
        assert horizon.completed_at is not None

    def test_pause_horizon(self):
        """Test pausing a horizon."""
        manager = HorizonManager()
        
        horizon = manager.create_horizon(title="Test")
        
        result = manager.pause_horizon(horizon.id)
        
        assert result is True
        assert horizon.status == HorizonStatus.PAUSED

    def test_resume_horizon(self):
        """Test resuming a paused horizon."""
        manager = HorizonManager()
        
        horizon = manager.create_horizon(title="Test")
        manager.pause_horizon(horizon.id)
        
        result = manager.resume_horizon(horizon.id)
        
        assert result is True
        assert horizon.status == HorizonStatus.ACTIVE

    def test_abandon_horizon(self):
        """Test abandoning a horizon."""
        manager = HorizonManager()
        
        horizon = manager.create_horizon(title="Test")
        
        result = manager.abandon_horizon(horizon.id, reason="No longer needed")
        
        assert result is True
        assert horizon.status == HorizonStatus.ABANDONED
        assert horizon.metadata.get("abandon_reason") == "No longer needed"

    def test_link_plan(self):
        """Test linking a plan to a horizon."""
        manager = HorizonManager()
        planner = Planner()
        
        horizon = manager.create_horizon(title="Test")
        plan = planner.create_plan(title="Linked Plan")
        
        result = manager.link_plan(horizon.id, plan.id)
        
        assert result is True
        assert horizon.plan_id == plan.id

    def test_get_history(self):
        """Test getting checkpoint history."""
        manager = HorizonManager()
        
        horizon = manager.create_horizon(title="Test")
        m1 = manager.add_milestone(horizon.id, title="M1")
        
        manager.complete_milestone(horizon.id, m1.id)
        
        history = manager.get_history(horizon.id)
        
        assert len(history) >= 1
        assert history[0].progress > 0


class TestProgressTracker:
    """Tests for ProgressTracker class."""

    def test_tracker_creation(self):
        """Test creating a progress tracker."""
        manager = HorizonManager()
        tracker = ProgressTracker(manager)
        
        assert tracker.horizon_manager is manager

    def test_get_summary(self):
        """Test getting summary of all horizons."""
        manager = HorizonManager()
        tracker = ProgressTracker(manager)
        
        manager.create_horizon(title="H1")
        manager.create_horizon(title="H2")
        
        summary = tracker.get_summary()
        
        assert summary["total_horizons"] == 2
        assert summary["by_status"]["active"] == 2

    def test_visual_progress(self):
        """Test visual progress bar."""
        manager = HorizonManager()
        tracker = ProgressTracker(manager)
        
        horizon = manager.create_horizon(title="Test")
        m1 = manager.add_milestone(horizon.id, title="M1")
        m2 = manager.add_milestone(horizon.id, title="M2")
        
        manager.complete_milestone(horizon.id, m1.id)
        
        visual = tracker.get_visual_progress(horizon.id, width=10)
        
        assert "[" in visual
        assert "]" in visual
        assert "50%" in visual

    def test_generate_report(self):
        """Test generating a text report."""
        manager = HorizonManager()
        tracker = ProgressTracker(manager)
        
        horizon = manager.create_horizon(
            title="Report Test",
            description="Testing reports",
        )
        
        report = tracker.generate_report(horizon.id)
        
        assert "Report Test" in report
        assert "Status:" in report
        assert "Progress:" in report

    def test_generate_report_not_found(self):
        """Test report for non-existent horizon."""
        manager = HorizonManager()
        tracker = ProgressTracker(manager)
        
        report = tracker.generate_report("nonexistent")
        
        assert "not found" in report.lower()

    def test_upcoming_deadlines(self):
        """Test getting upcoming deadlines."""
        manager = HorizonManager()
        tracker = ProgressTracker(manager)
        
        horizon = manager.create_horizon(title="Test")
        
        # Add milestone with near deadline
        near_deadline = datetime.now() + timedelta(days=3)
        manager.add_milestone(
            horizon.id,
            title="Urgent",
            due_date=near_deadline,
        )
        
        # Add milestone with far deadline
        far_deadline = datetime.now() + timedelta(days=30)
        manager.add_milestone(
            horizon.id,
            title="Later",
            due_date=far_deadline,
        )
        
        deadlines = tracker.get_upcoming_deadlines(days=7)
        
        assert len(deadlines) == 1
        assert deadlines[0]["milestone_title"] == "Urgent"
