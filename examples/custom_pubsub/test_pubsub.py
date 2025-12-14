"""Test pub/sub implementation that records all operations.

Useful for integration testing LiveViews that use pub/sub without needing
Redis or other external dependencies.

Usage:
    test_pubsub = TestPubSub()
    app = PyView(pubsub=test_pubsub)

    # In your tests
    assert ("user_123", "updates") in test_pubsub.subscriptions
    assert ("updates", {"action": "joined"}) in test_pubsub.broadcasts
"""

from typing import Any, Callable, Coroutine

TopicHandler = Callable[[str, Any], Coroutine[Any, Any, None]]


class TestPubSub:
    """Records all pub/sub operations for testing."""

    def __init__(self):
        self.subscriptions: list[tuple[str, str]] = []  # (session_id, topic)
        self.unsubscriptions: list[tuple[str, str]] = []  # (session_id, topic)
        self.broadcasts: list[tuple[str, Any]] = []  # (topic, message)
        self.handlers: dict[str, dict[str, TopicHandler]] = {}
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        """Mark as started."""
        self.started = True

    async def stop(self) -> None:
        """Mark as stopped."""
        self.stopped = True

    async def subscribe_topic(
        self,
        session_id: str,
        topic: str,
        handler: TopicHandler,
    ) -> None:
        """Record subscription and store handler."""
        self.subscriptions.append((session_id, topic))
        if topic not in self.handlers:
            self.handlers[topic] = {}
        self.handlers[topic][session_id] = handler

    async def unsubscribe_topic(self, session_id: str, topic: str) -> None:
        """Record unsubscription."""
        self.unsubscriptions.append((session_id, topic))
        if topic in self.handlers and session_id in self.handlers[topic]:
            del self.handlers[topic][session_id]
            if not self.handlers[topic]:
                del self.handlers[topic]

    async def unsubscribe_all(self, session_id: str) -> None:
        """Record unsubscribe all."""
        for topic in list(self.handlers.keys()):
            if session_id in self.handlers[topic]:
                self.unsubscriptions.append((session_id, topic))
                del self.handlers[topic][session_id]
                if not self.handlers[topic]:
                    del self.handlers[topic]

    async def broadcast(self, topic: str, message: Any) -> None:
        """Record broadcast and dispatch to local handlers."""
        self.broadcasts.append((topic, message))
        # Immediately dispatch to local handlers for testing
        if topic in self.handlers:
            for handler in list(self.handlers[topic].values()):
                await handler(topic, message)

    def clear(self) -> None:
        """Clear all recorded operations."""
        self.subscriptions.clear()
        self.unsubscriptions.clear()
        self.broadcasts.clear()
        self.handlers.clear()
