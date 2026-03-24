"""
Pipeline - Processing pipelines for request handling.

Phase 04: Assembly
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


class PipelineStatus(Enum):
    """Status of a pipeline execution."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass
class PipelineContext:
    """Context passed through pipeline stages."""
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from context."""
        return self.data.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Set a value in context."""
        self.data[key] = value
    
    def has_error(self) -> bool:
        """Check if there are any errors."""
        return len(self.errors) > 0
    
    def add_error(self, error: str) -> None:
        """Add an error message."""
        self.errors.append(error)


@dataclass
class StageResult:
    """Result of a pipeline stage execution."""
    success: bool
    output: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class PipelineStage:
    """A single stage in a processing pipeline."""
    
    def __init__(self, name: str, processor: Callable[[PipelineContext], StageResult]):
        self.name = name
        self.processor = processor
        self._stats: Dict[str, Any] = {
            "runs": 0,
            "successes": 0,
            "failures": 0,
            "total_time": 0.0,
        }
    
    def execute(self, context: PipelineContext) -> StageResult:
        """Execute this stage."""
        import time
        start_time = time.time()
        
        try:
            result = self.processor(context)
            self._stats["runs"] += 1
            if result.success:
                self._stats["successes"] += 1
            else:
                self._stats["failures"] += 1
            return result
        except Exception as e:
            self._stats["runs"] += 1
            self._stats["failures"] += 1
            return StageResult(success=False, error=str(e))
        finally:
            elapsed = time.time() - start_time
            self._stats["total_time"] += elapsed
    
    def get_stats(self) -> Dict[str, Any]:
        """Get stage statistics."""
        return dict(self._stats)


class Pipeline:
    """
    A processing pipeline with multiple stages.
    
    Phase 04: Sequential pipeline execution with error handling.
    """
    
    def __init__(self, name: str = "pipeline"):
        self.name = name
        self._stages: List[PipelineStage] = []
        self._on_error: Optional[Callable[[PipelineContext, Exception], None]] = None
        self._on_complete: Optional[Callable[[PipelineContext], None]] = None
    
    def add_stage(self, name: str, processor: Callable[[PipelineContext], StageResult]) -> "Pipeline":
        """
        Add a stage to the pipeline.
        
        Args:
            name: Stage name
            processor: Function that processes context and returns StageResult
        
        Returns:
            Self for chaining
        """
        stage = PipelineStage(name, processor)
        self._stages.append(stage)
        return self
    
    def on_error(self, handler: Callable[[PipelineContext, Exception], None]) -> "Pipeline":
        """Set error handler."""
        self._on_error = handler
        return self
    
    def on_complete(self, handler: Callable[[PipelineContext], None]) -> "Pipeline":
        """Set completion handler."""
        self._on_complete = handler
        return self
    
    def execute(self, initial_data: Optional[Dict[str, Any]] = None,
                stop_on_failure: bool = False) -> PipelineContext:
        """
        Execute the pipeline.

        Args:
            initial_data: Initial data for the context
            stop_on_failure: If True, halt pipeline on first stage failure

        Returns:
            PipelineContext with results
        """
        context = PipelineContext(data=initial_data or {})
        context.started_at = datetime.now()

        try:
            for stage in self._stages:
                result = stage.execute(context)

                if not result.success:
                    context.add_error(f"Stage '{stage.name}' failed: {result.error}")

                    if self._on_error:
                        self._on_error(context, Exception(result.error))

                    # Continue or stop based on stop_on_failure parameter
                    if stop_on_failure:
                        import logging
                        logging.error(
                            f"[ENGRAM] pipeline — stage '{stage.name}' failed with "
                            f"stop_on_failure=True. Halting pipeline."
                        )
                        context.metadata["status"] = PipelineStatus.STOPPED.value
                        return context
                    else:
                        import logging
                        logging.warning(
                            f"[ENGRAM] pipeline — stage '{stage.name}' failed, continuing. "
                            f"Error: {result.error}"
                        )
                        continue

                # Merge output into context if present
                if result.output:
                    if isinstance(result.output, dict):
                        context.data.update(result.output)
                    else:
                        context.data["last_output"] = result.output
            
            context.completed_at = datetime.now()
            context.metadata["status"] = PipelineStatus.COMPLETED.value
            
            if self._on_complete:
                self._on_complete(context)
            
        except Exception as e:
            context.add_error(f"Pipeline error: {str(e)}")
            context.metadata["status"] = PipelineStatus.FAILED.value
            
            if self._on_error:
                self._on_error(context, e)
        
        return context
    
    def execute_async(self, initial_data: Optional[Dict[str, Any]] = None) -> "Pipeline":
        """Execute pipeline asynchronously (placeholder)."""
        # Phase 04: Basic implementation
        # Future phases may add proper async support
        self.execute(initial_data)
        return self
    
    def get_stats(self) -> Dict[str, Any]:
        """Get pipeline statistics."""
        return {
            "name": self.name,
            "stage_count": len(self._stages),
            "stages": {s.name: s.get_stats() for s in self._stages},
        }
    
    def clear(self) -> "Pipeline":
        """Clear all stages."""
        self._stages.clear()
        return self


class PipelineBuilder:
    """Fluent builder for creating pipelines."""
    
    def __init__(self, name: str = "pipeline"):
        self._pipeline = Pipeline(name)
    
    def stage(self, name: str, processor: Callable[[PipelineContext], StageResult]) -> "PipelineBuilder":
        """Add a stage."""
        self._pipeline.add_stage(name, processor)
        return self
    
    def transform(self, name: str, fn: Callable[[Any], Any],
                  input_key: str = "input", output_key: str = "output") -> "PipelineBuilder":
        """Add a transformation stage."""
        def processor(ctx: PipelineContext) -> StageResult:
            try:
                input_val = ctx.get(input_key)
                output_val = fn(input_val)
                ctx.set(output_key, output_val)
                return StageResult(success=True, output=output_val)
            except Exception as e:
                return StageResult(success=False, error=str(e))
        
        self._pipeline.add_stage(name, processor)
        return self
    
    def validate(self, name: str, validator: Callable[[Any], bool],
                 error_msg: str = "Validation failed") -> "PipelineBuilder":
        """Add a validation stage."""
        def processor(ctx: PipelineContext) -> StageResult:
            input_val = ctx.get("input")
            if validator(input_val):
                return StageResult(success=True)
            return StageResult(success=False, error=error_msg)
        
        self._pipeline.add_stage(name, processor)
        return self
    
    def branch(self, condition: Callable[[PipelineContext], bool],
               true_pipeline: Pipeline,
               false_pipeline: Optional[Pipeline] = None) -> "PipelineBuilder":
        """Add a branching stage."""
        if not isinstance(true_pipeline, Pipeline):
            raise TypeError(
                f"[ENGRAM] pipeline — branch() true_pipeline must be Pipeline, "
                f"got {type(true_pipeline).__name__}"
            )
        if false_pipeline is not None and not isinstance(false_pipeline, Pipeline):
            raise TypeError(
                f"[ENGRAM] pipeline — branch() false_pipeline must be Pipeline, "
                f"got {type(false_pipeline).__name__}"
            )
        def processor(ctx: PipelineContext) -> StageResult:
            if condition(ctx):
                result = true_pipeline.execute(ctx.data)
            elif false_pipeline:
                result = false_pipeline.execute(ctx.data)
            else:
                result = ctx
            
            return StageResult(success=not result.has_error(), output=result.data)
        
        self._pipeline.add_stage("branch", processor)
        return self
    
    def build(self) -> Pipeline:
        """Build the pipeline."""
        return self._pipeline
