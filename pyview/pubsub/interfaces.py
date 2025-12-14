"""Protocol definition for pluggable pub/sub implementations."""

from typing import Any, Callable, Coroutine, Protocol, runtime_checkable

# Type alias for async topic handlers
TopicHandler = Callable[[str, Any], Coroutine[Any, Any, None]]


@runtime_checkable
class PubSubProvider(Protocol):
    """Protocol for pub/sub implementations.

    Implementations must handle:
    - Topic-based subscriptions per session
    - Broadcasting messages to all subscribers on a topic
    - Proper cleanup when sessions disconnect

    For distributed implementations (Redis, etc.):
    - Handlers are local Python callables (not serializable)
    - Messages must be serializable (JSON-compatible recommended)
    - Implementation should handle cross-instance message routing

    Using Protocol enables structural typing - any class implementing
    these methods is compatible, no inheritance required.
    """

    async def subscribe_topic(
        self,
        session_id: str,
        topic: str,
        handler: TopicHandler,
    ) -> None:
        """Subscribe a session to a topic with a handler.

        Args:
            session_id: Unique identifier for the session
            topic: Topic name to subscribe to
            handler: Async callable(topic, message) to invoke on messages
        """
        ...

    async def unsubscribe_topic(self, session_id: str, topic: str) -> None:
        """Unsubscribe a session from a specific topic."""
        ...

    async def unsubscribe_all(self, session_id: str) -> None:
        """Remove all subscriptions for a session (cleanup on disconnect)."""
        ...

    async def broadcast(self, topic: str, message: Any) -> None:
        """Broadcast a message to all subscribers on a topic.

        Note: For distributed implementations, `message` should be
        JSON-serializable. Complex objects should be converted before
        broadcasting.
        """
        ...

    async def start(self) -> None:
        """Called when the PyView app starts. Override for setup."""
        ...

    async def stop(self) -> None:
        """Called when the PyView app shuts down. Override for cleanup."""
        ...
