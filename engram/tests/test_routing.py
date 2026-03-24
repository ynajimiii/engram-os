"""
Tests for router.py - Request routing and dispatch.

Phase 03: Routing
"""

import pytest
from engram.core.router import (
    Router,
    Route,
    RoutePriority,
    RoutingResult,
    IntentClassifier,
)


class TestRoute:
    """Tests for Route class."""

    def test_route_creation(self):
        """Test creating a route."""
        def handler(intent):
            return "handled"
        
        route = Route(
            pattern="test",
            handler=handler,
            name="test_route",
        )
        
        assert route.pattern == "test"
        assert route.name == "test_route"
        assert route.priority == RoutePriority.NORMAL

    def test_route_matches_exact(self):
        """Test exact pattern matching."""
        def handler(intent):
            pass
        
        route = Route(pattern="hello", handler=handler, name="test")
        
        assert route.matches("hello") is True
        assert route.matches("Hello") is True  # Case insensitive
        assert route.matches("world") is False

    def test_route_matches_wildcard(self):
        """Test wildcard pattern matching."""
        def handler(intent):
            pass
        
        route = Route(pattern="*", handler=handler, name="test")
        
        assert route.matches("anything") is True
        assert route.matches("hello world") is True

    def test_route_match_groups(self):
        """Test extracting match groups."""
        def handler(intent):
            pass
        
        route = Route(pattern="*", handler=handler, name="test")
        
        groups = route.match_groups("test input")
        assert groups == ("test input",)


class TestRouter:
    """Tests for Router class."""

    def test_router_creation(self):
        """Test creating a router."""
        router = Router()
        
        assert router.list_routes() == []

    def test_router_add_route(self):
        """Test adding a route."""
        router = Router()
        
        def handler(intent):
            return "handled"
        
        router.add_route("hello", handler, name="greeting")
        
        assert "greeting" in router.list_routes()

    def test_router_route_match(self):
        """Test routing to correct handler."""
        router = Router()
        
        def hello_handler(intent):
            return "hello"
        
        def bye_handler(intent):
            return "bye"
        
        router.add_route("hello", hello_handler, name="hello")
        router.add_route("bye", bye_handler, name="bye")
        
        result = router.route("hello")
        
        assert result.matched is True
        assert result.route_name == "hello"
        assert result.handler == hello_handler

    def test_router_route_no_match(self):
        """Test routing with no match."""
        router = Router()
        
        result = router.route("unknown")
        
        assert result.matched is False
        assert result.handler is None

    def test_router_default_handler(self):
        """Test default handler for unmatched routes."""
        router = Router()
        
        def default_handler(intent):
            return "default"
        
        router.set_default(default_handler)
        
        result = router.route("unknown")
        
        assert result.matched is False
        assert result.handler == default_handler

    def test_router_dispatch(self):
        """Test dispatching to handler."""
        router = Router()
        
        def handler(intent, **kwargs):
            return f"handled: {intent}"
        
        router.add_route("test", handler, name="test")
        
        result = router.dispatch("test")
        
        assert result == "handled: test"

    def test_router_dispatch_no_handler(self):
        """Test dispatching with no handler."""
        router = Router()
        
        with pytest.raises(ValueError):
            router.dispatch("unknown")

    def test_router_priority(self):
        """Test route priority ordering."""
        router = Router()
        
        def low_handler(intent):
            return "low"
        
        def high_handler(intent):
            return "high"
        
        router.add_route("*", low_handler, name="low", priority=RoutePriority.LOW)
        router.add_route("test", high_handler, name="high", priority=RoutePriority.HIGH)
        
        # High priority route should match first
        result = router.route("test")
        
        assert result.route_name == "high"

    def test_router_stats(self):
        """Test routing statistics."""
        router = Router()
        
        def handler(intent):
            pass
        
        router.add_route("test", handler, name="test")
        
        router.route("test")
        router.route("test")
        
        stats = router.get_stats()
        
        assert stats["test"] == 2

    def test_router_remove_route(self):
        """Test removing a route."""
        router = Router()
        
        def handler(intent):
            pass
        
        router.add_route("test", handler, name="test")
        
        assert router.remove_route("test") is True
        assert "test" not in router.list_routes()
        assert router.remove_route("test") is False


class TestIntentClassifier:
    """Tests for IntentClassifier class."""

    def test_classifier_creation(self):
        """Test creating an intent classifier."""
        classifier = IntentClassifier()
        
        assert classifier._keywords == {}

    def test_classifier_add_intent(self):
        """Test adding keywords for an intent."""
        classifier = IntentClassifier()
        
        classifier.add_intent("greeting", ["hello", "hi", "hey"])
        
        assert "greeting" in classifier._keywords
        assert "hello" in classifier._keywords["greeting"]

    def test_classifier_classify(self):
        """Test classifying text."""
        classifier = IntentClassifier()
        
        classifier.add_intent("greeting", ["hello", "hi"])
        classifier.add_intent("farewell", ["bye", "goodbye"])
        
        intent, confidence = classifier.classify("Hello there!")
        
        assert intent == "greeting"
        assert confidence > 0

    def test_classifier_classify_unknown(self):
        """Test classifying unknown text."""
        classifier = IntentClassifier()
        
        classifier.add_intent("greeting", ["hello"])
        
        intent, confidence = classifier.classify("something random")
        
        assert intent == "unknown" or intent == classifier._fallback
        assert confidence == 0.0

    def test_classifier_fallback(self):
        """Test setting fallback intent."""
        classifier = IntentClassifier()
        classifier.set_fallback("general")
        
        classifier.add_intent("greeting", ["hello"])
        
        intent, _ = classifier.classify("random text")
        
        assert intent == "general"
