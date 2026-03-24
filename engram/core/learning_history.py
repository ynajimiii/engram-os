# engram/core/learning_history.py
"""
Learning History — Track patches and quality improvements over time.

This module provides:
- LearningHistory: Track patches applied over time
- QualityTrend: Calculate quality improvement trends
- Persistent storage in learning_history.jsonl
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any


@dataclass
class PatchRecord:
    """Record of a single patch application."""
    timestamp: str
    module_name: str
    section: str
    expected_improvement: float
    actual_improvement: Optional[float] = None
    session_id: Optional[str] = None
    tasks_analyzed: int = 0
    quality_before: float = 0.0
    quality_after: float = 0.0
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "PatchRecord":
        return cls(**data)


@dataclass
class QualitySnapshot:
    """Quality score snapshot at a point in time."""
    timestamp: str
    session_id: str
    task_count: int
    average_quality: float
    min_quality: float
    max_quality: float
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "QualitySnapshot":
        return cls(**data)


class LearningHistory:
    """
    Track learning patches applied over time.
    
    Persists to learning_history.jsonl in sessions directory.
    Each patch application is recorded as a JSON line.
    """
    
    def __init__(self, sessions_dir: str):
        self.sessions_dir = Path(sessions_dir)
        self.history_file = self.sessions_dir / "learning_history.jsonl"
        self._ensure_dir()
    
    def _ensure_dir(self):
        """Ensure sessions directory exists."""
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
    
    def record_patch(self, patch_record: PatchRecord) -> None:
        """
        Record a patch application.
        
        Args:
            patch_record: PatchRecord with patch details
        """
        try:
            with open(self.history_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(patch_record.to_dict()) + "\n")
            logging.info(
                f"[ENGRAM] learning history: recorded patch for "
                f"{patch_record.module_name}/{patch_record.section}"
            )
        except Exception as e:
            logging.warning(
                f"[ENGRAM] learning history: failed to record patch: {e}"
            )
    
    def get_all_patches(self) -> List[PatchRecord]:
        """
        Get all recorded patches.
        
        Returns:
            List of PatchRecord objects, oldest first
        """
        patches = []
        if not self.history_file.exists():
            return patches
        
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            patches.append(PatchRecord.from_dict(data))
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logging.warning(
                f"[ENGRAM] learning history: failed to read patches: {e}"
            )
        
        return patches
    
    def get_patches_for_module(self, module_name: str) -> List[PatchRecord]:
        """
        Get patches for a specific module.
        
        Args:
            module_name: Module name to filter by
            
        Returns:
            List of PatchRecord objects for the module
        """
        all_patches = self.get_all_patches()
        return [p for p in all_patches if p.module_name == module_name]
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary statistics.
        
        Returns:
            Dict with summary statistics
        """
        patches = self.get_all_patches()
        
        if not patches:
            return {
                "total_patches": 0,
                "modules_improved": 0,
                "average_expected_improvement": 0.0,
                "average_actual_improvement": 0.0,
            }
        
        modules = set(p.module_name for p in patches)
        expected_improvements = [p.expected_improvement for p in patches]
        actual_improvements = [
            p.actual_improvement for p in patches 
            if p.actual_improvement is not None
        ]
        
        return {
            "total_patches": len(patches),
            "modules_improved": len(modules),
            "average_expected_improvement": sum(expected_improvements) / len(expected_improvements),
            "average_actual_improvement": sum(actual_improvements) / len(actual_improvements) if actual_improvements else 0.0,
            "last_patch": patches[-1].timestamp if patches else None,
        }


class QualityTrend:
    """
    Calculate and track quality improvement trends.
    
    Analyzes session logs to compute quality trends over time.
    """
    
    def __init__(self, sessions_dir: str):
        self.sessions_dir = Path(sessions_dir)
        self.snapshots_file = self.sessions_dir / "quality_snapshots.jsonl"
        self._ensure_dir()
    
    def _ensure_dir(self):
        """Ensure sessions directory exists."""
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
    
    def record_snapshot(self, snapshot: QualitySnapshot) -> None:
        """
        Record a quality snapshot.
        
        Args:
            snapshot: QualitySnapshot with quality metrics
        """
        try:
            with open(self.snapshots_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(snapshot.to_dict()) + "\n")
        except Exception as e:
            logging.warning(
                f"[ENGRAM] quality trend: failed to record snapshot: {e}"
            )
    
    def get_all_snapshots(self) -> List[QualitySnapshot]:
        """
        Get all recorded snapshots.
        
        Returns:
            List of QualitySnapshot objects, oldest first
        """
        snapshots = []
        if not self.snapshots_file.exists():
            return snapshots
        
        try:
            with open(self.snapshots_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            snapshots.append(QualitySnapshot.from_dict(data))
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logging.warning(
                f"[ENGRAM] quality trend: failed to read snapshots: {e}"
            )
        
        return snapshots
    
    def calculate_trend(self, window_size: int = 10) -> Dict[str, Any]:
        """
        Calculate quality trend over recent sessions.
        
        Args:
            window_size: Number of snapshots to analyze
            
        Returns:
            Dict with trend analysis
        """
        snapshots = self.get_all_snapshots()
        
        if len(snapshots) < 2:
            return {
                "trend": "insufficient_data",
                "change": 0.0,
                "percent_change": 0.0,
                "snapshots_analyzed": len(snapshots),
            }
        
        # Use last N snapshots
        recent = snapshots[-window_size:] if len(snapshots) > window_size else snapshots
        
        if len(recent) < 2:
            return {
                "trend": "insufficient_data",
                "change": 0.0,
                "percent_change": 0.0,
                "snapshots_analyzed": len(recent),
            }
        
        # Calculate trend
        first_avg = recent[0].average_quality
        last_avg = recent[-1].average_quality
        change = last_avg - first_avg
        percent_change = (change / first_avg * 100) if first_avg > 0 else 0.0
        
        # Determine trend direction
        if change > 0.02:
            trend = "improving"
        elif change < -0.02:
            trend = "declining"
        else:
            trend = "stable"
        
        return {
            "trend": trend,
            "change": round(change, 4),
            "percent_change": round(percent_change, 2),
            "snapshots_analyzed": len(recent),
            "first_average": round(first_avg, 4),
            "last_average": round(last_avg, 4),
            "overall_average": round(sum(s.average_quality for s in recent) / len(recent), 4),
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary statistics.
        
        Returns:
            Dict with summary statistics
        """
        snapshots = self.get_all_snapshots()
        
        if not snapshots:
            return {
                "total_snapshots": 0,
                "average_quality": 0.0,
                "trend": "no_data",
            }
        
        all_qualities = [s.average_quality for s in snapshots]
        trend = self.calculate_trend()
        
        return {
            "total_snapshots": len(snapshots),
            "average_quality": round(sum(all_qualities) / len(all_qualities), 4),
            "min_quality": round(min(all_qualities), 4),
            "max_quality": round(max(all_qualities), 4),
            "trend": trend.get("trend", "unknown"),
            "trend_change": trend.get("change", 0.0),
        }


def record_learning_event(
    sessions_dir: str,
    module_name: str,
    patch,
    session_id: str = None,
    tasks_analyzed: int = 0,
    quality_before: float = 0.0,
    quality_after: float = 0.0,
) -> bool:
    """
    Convenience function to record a learning event.
    
    Args:
        sessions_dir: Path to sessions directory
        module_name: Module that was improved
        patch: PromptPatch object (or None)
        session_id: Optional session ID
        tasks_analyzed: Number of tasks analyzed
        quality_before: Average quality before learning
        quality_after: Average quality after learning
        
    Returns:
        True if recorded successfully, False otherwise
    """
    try:
        history = LearningHistory(sessions_dir)
        
        if patch:
            record = PatchRecord(
                timestamp=datetime.utcnow().isoformat(),
                module_name=module_name,
                section=getattr(patch, 'section', 'unknown'),
                expected_improvement=getattr(patch, 'expected_improvement', 0.0),
                session_id=session_id,
                tasks_analyzed=tasks_analyzed,
                quality_before=quality_before,
                quality_after=quality_after,
            )
            history.record_patch(record)
            return True
        return False
    except Exception as e:
        logging.warning(f"[ENGRAM] failed to record learning event: {e}")
        return False


def record_quality_snapshot(
    sessions_dir: str,
    session_id: str,
    session_log: list,
) -> bool:
    """
    Convenience function to record a quality snapshot.
    
    Args:
        sessions_dir: Path to sessions directory
        session_id: Session ID
        session_log: Session log with quality scores
        
    Returns:
        True if recorded successfully, False otherwise
    """
    try:
        trend = QualityTrend(sessions_dir)
        
        # Extract quality scores from session log
        scores = [
            entry.get("quality_score", 0.0)
            for entry in session_log
            if "quality_score" in entry
        ]
        
        if not scores:
            return False
        
        snapshot = QualitySnapshot(
            timestamp=datetime.utcnow().isoformat(),
            session_id=session_id,
            task_count=len(scores),
            average_quality=sum(scores) / len(scores),
            min_quality=min(scores),
            max_quality=max(scores),
        )
        
        trend.record_snapshot(snapshot)
        return True
    except Exception as e:
        logging.warning(f"[ENGRAM] failed to record quality snapshot: {e}")
        return False
