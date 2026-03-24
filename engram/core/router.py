"""
Router - Request routing and dispatch.

Phase 03: Routing
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Pattern, Tuple


class RoutePriority(Enum):
    """Priority levels for route matching."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class Route:
    """A route definition for request dispatch."""
    pattern: str
    handler: Callable
    name: str
    priority: RoutePriority = RoutePriority.NORMAL
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    _compiled_pattern: Optional[Pattern] = field(default=None, repr=False)
    
    def __post_init__(self):
        self._compile_pattern()
    
    def _compile_pattern(self) -> None:
        """Compile the pattern for matching."""
        # Simple pattern compilation - supports * wildcard
        if self.pattern == "*":
            self._compiled_pattern = re.compile("(.*)")
        else:
            # Escape special regex chars except *
            escaped = re.escape(self.pattern).replace(r"\*", "(.*)")
            self._compiled_pattern = re.compile(f"^{escaped}$", re.IGNORECASE)
    
    def matches(self, intent: str) -> bool:
        """Check if an intent matches this route."""
        if self._compiled_pattern is None:
            return False
        return bool(self._compiled_pattern.match(intent))
    
    def match_groups(self, intent: str) -> Tuple[str, ...]:
        """Extract matched groups from an intent."""
        if self._compiled_pattern is None:
            return ()
        match = self._compiled_pattern.match(intent)
        return match.groups() if match else ()


@dataclass
class RoutingResult:
    """Result of a routing operation."""
    matched: bool
    route_name: Optional[str] = None
    handler: Optional[Callable] = None
    groups: Tuple[str, ...] = field(default_factory=tuple)
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class Router:
    """
    Routes requests to appropriate handlers based on intent.
    
    Supports pattern matching with wildcards and priority-based
    route selection.
    """
    
    def __init__(self):
        self._routes: List[Route] = []
        self._default_handler: Optional[Callable] = None
        self._stats: Dict[str, int] = {}
    
    def add_route(self, pattern: str, handler: Callable, name: Optional[str] = None,
                  priority: RoutePriority = RoutePriority.NORMAL,
                  metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Add a route to the router.
        
        Args:
            pattern: Pattern to match (supports * wildcard)
            handler: Handler function to call when matched
            name: Optional name for the route
            priority: Priority level for matching
            metadata: Optional metadata for the route
        """
        route = Route(
            pattern=pattern,
            handler=handler,
            name=name or pattern,
            priority=priority,
            metadata=metadata or {},
        )
        self._routes.append(route)
        # Sort by priority (highest first)
        self._routes.sort(key=lambda r: r.priority.value, reverse=True)
    
    def set_default(self, handler: Callable) -> None:
        """Set a default handler for unmatched requests."""
        self._default_handler = handler
    
    def route(self, intent: str) -> RoutingResult:
        """
        Route an intent to the appropriate handler.
        
        Args:
            intent: The intent string to route
        
        Returns:
            RoutingResult with matched handler or default
        """
        # Try to match routes in priority order
        for route in self._routes:
            if route.matches(intent):
                groups = route.match_groups(intent)
                
                # Update stats
                self._stats[route.name] = self._stats.get(route.name, 0) + 1
                
                return RoutingResult(
                    matched=True,
                    route_name=route.name,
                    handler=route.handler,
                    groups=groups,
                    confidence=self._calculate_confidence(intent, route.pattern),
                    metadata=route.metadata,
                )
        
        # No match - use default if available
        if self._default_handler:
            return RoutingResult(
                matched=False,
                handler=self._default_handler,
                confidence=0.0,
            )
        
        return RoutingResult(matched=False)
    
    def dispatch(self, intent: str, **kwargs: Any) -> Any:
        """
        Route and dispatch an intent to its handler.
        
        Args:
            intent: The intent string
            **kwargs: Arguments to pass to the handler
        
        Returns:
            Result of the handler execution
        """
        result = self.route(intent)
        
        if result.handler is None:
            raise ValueError(f"No handler found for intent: {intent}")
        
        return result.handler(intent, **kwargs)
    
    def _calculate_confidence(self, intent: str, pattern: str) -> float:
        """Calculate match confidence score."""
        if pattern == "*":
            return 0.5

        # Exact match = 1.0 (explicit maximum confidence)
        if pattern.lower() == intent.lower():
            return 1.0

        # Partial match based on length similarity
        ratio = len(intent) / len(pattern) if len(pattern) > 0 else 0
        result = min(0.8, 0.5 + ratio * 0.3)
        
        # Safety clamp — no confidence score should ever exceed 1.0
        return max(0.0, min(1.0, result))
    
    def get_stats(self) -> Dict[str, int]:
        """Get routing statistics."""
        return dict(self._stats)
    
    def clear_stats(self) -> None:
        """Clear routing statistics."""
        self._stats.clear()
    
    def list_routes(self) -> List[str]:
        """List all registered route names."""
        return [r.name for r in self._routes]
    
    def remove_route(self, name: str) -> bool:
        """Remove a route by name."""
        for i, route in enumerate(self._routes):
            if route.name == name:
                del self._routes[i]
                return True
        return False


class IntentClassifier:
    """
    Simple intent classifier for routing.
    
    Phase 03: Rule-based classification with keyword matching.
    Future phases may integrate ML-based classification.
    """
    
    def __init__(self):
        self._keywords: Dict[str, List[str]] = {}
        self._fallback: Optional[str] = None
    
    def add_intent(self, intent: str, keywords: List[str]) -> None:
        """Add keywords for an intent."""
        self._keywords[intent] = [k.lower() for k in keywords]
    
    def classify(self, text: str) -> Tuple[str, float]:
        """
        Classify text into an intent.
        
        Returns:
            Tuple of (intent, confidence)
        """
        text_lower = text.lower()
        best_intent = self._fallback
        best_score = 0.0
        
        for intent, keywords in self._keywords.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > best_score:
                best_score = score
                best_intent = intent
        
        confidence = best_score / max(len(kw) for kw in self._keywords.values()) if self._keywords else 0
        return best_intent or "unknown", min(1.0, confidence)

    def set_fallback(self, intent: str) -> None:
        """Set the fallback intent."""
        self._fallback = intent


# ── Router thresholds ────────────────────────────────────────────────
# Calibrated for sentence-transformers all-MiniLM-L6-v2
# Real embeddings produce cosine similarity typically in range 0.0-0.6
# for diverse code/text content (not 0.0-1.0 as with normalized pairs)
#
# Thresholds set to promote top ~5% and demote bottom ~10% of chunks.
#
# To use more aggressive promotion (more chunks in hot tier):
#   LOAD_THRESHOLD  = 0.40  (promotes ~10%)
# To use more conservative promotion (fewer chunks in hot tier):
#   LOAD_THRESHOLD  = 0.50  (promotes ~2-3%)
#
# To revert to pseudo-embedding thresholds:
#   LOAD_THRESHOLD  = 0.12
#   EVICT_THRESHOLD = -0.05
#   ANCHOR_BONUS    = 0.05
LOAD_THRESHOLD = 0.45   # promote top ~5% of semantic matches
EVICT_THRESHOLD = 0.05   # demote bottom ~10%
ANCHOR_BONUS = 0.10   # scratch active_task match boost


def route_task(goal: str, db: Any, scratch: Any) -> Dict[str, Any]:
    """
    Route a task to get context from vector DB.

    Uses semantic scoring to promote/demote chunks based on
    cosine similarity with the task embedding.

    Args:
        goal: The task goal
        db: Vector database with hot_chunks/warm_chunks
        scratch: Scratch memory

    Returns:
        Routing result dictionary with promoted/demoted chunks
    """
    import logging

    promoted = []
    demoted = []
    hot_count = 0
    vram_mb = 0.0

    try:
        if db is None:
            return {
                "promoted": promoted, "demoted": demoted,
                "hot_count": hot_count, "vram_mb": vram_mb
            }

        # Embed the query using real sentence-transformers
        from engram.core.embedder import get_embedding
        task_emb = get_embedding(goal)
        task_emb = task_emb.reshape(1, -1)

        all_chunks = (
            (db.hot_chunks if hasattr(db, 'hot_chunks') else []) +
            (db.warm_chunks if hasattr(db, 'warm_chunks') else [])
        )

        if not all_chunks:
            return {
                "promoted": promoted, "demoted": demoted,
                "hot_count": len(db.hot_chunks if hasattr(db, 'hot_chunks') else []),
                "vram_mb": vram_mb
            }

        import numpy as np
        
        # Access vector from VectorEntry objects
        # VectorEntry has .vector attribute (not .embedding)
        # Also handle dict-like chunks for backwards compatibility
        def get_vector(c):
            if hasattr(c, 'vector'):
                return c.vector
            elif hasattr(c, 'embedding'):
                return c.embedding
            elif hasattr(c, 'metadata') and 'embedding' in c.metadata:
                return c.metadata['embedding']
            else:
                return None
        
        vectors = [get_vector(c) for c in all_chunks]
        vectors = [v for v in vectors if v is not None]
        
        if not vectors:
            logging.warning("[ENGRAM] route_task: no valid vectors found")
            return {
                "promoted": promoted, "demoted": demoted,
                "hot_count": len(db.hot_chunks if hasattr(db, 'hot_chunks') else []),
                "vram_mb": vram_mb
            }
        
        all_embs = np.vstack(vectors)
        scores = (all_embs @ task_emb.T).flatten()

        anchor_ids = set()
        if scratch and hasattr(scratch, 'get'):
            try:
                active = scratch.get("active_task", "module")
                if active:
                    anchor_ids.add(f"module_{active}")
                    anchor_ids.add(str(active))
            except Exception:
                pass

        # Helper to get tier from chunk (VectorEntry or dict)
        def get_tier(c):
            if hasattr(c, 'metadata') and 'tier' in c.metadata:
                return c.metadata['tier']
            elif hasattr(c, 'tier'):
                return c.tier
            return 'warm'  # default
        
        for i, chunk in enumerate(all_chunks):
            score = float(scores[i])
            if chunk.id in anchor_ids:
                score = min(1.0, score + ANCHOR_BONUS)
            chunk.last_score = score
            
            tier = get_tier(chunk)
            
            # Debug logging for top scores
            if score > 0.5:
                logging.debug(
                    f"[ENGRAM] chunk {chunk.id}: score={score:.3f} tier={tier}"
                )

            if score >= LOAD_THRESHOLD and tier == "warm":
                if hasattr(db, 'promote'):
                    db.promote(chunk.id)
                    promoted.append(chunk.id)
            elif score < EVICT_THRESHOLD and tier == "hot":
                if hasattr(db, 'demote'):
                    db.demote(chunk.id)
                    demoted.append(chunk.id)

        hot_count = len(db.hot_chunks) if hasattr(db, 'hot_chunks') else 0
        if hasattr(db, 'get_hot_vram_mb'):
            vram_mb = db.get_hot_vram_mb()

        logging.info(
            f"[ENGRAM] route_task: "
            f"+{len(promoted)} promoted, "
            f"-{len(demoted)} demoted, "
            f"{hot_count} hot"
        )

    except Exception as e:
        logging.warning(f"[ENGRAM] route_task error: {e}")

    return {
        "promoted": promoted,
        "demoted": demoted,
        "hot_count": hot_count,
        "vram_mb": vram_mb,
    }
