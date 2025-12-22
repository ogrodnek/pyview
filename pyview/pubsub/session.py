"""Session-scoped pub/sub wrapper."""

from typing import Any

from .interfaces import PubSubProvider, TopicHandler


class SessionPubSub:
    """Session-scoped pub/sub wrapper.

    Provides a convenient API that automatically includes the session_id
    in all operations. Used internally by ConnectedLiveViewSocket.
    """

    def __init__(self, provider: PubSubProvider, session_id: str):
        self._provider = provider
        self._session_id = session_id

    async def subscribe(self, topic: str, handler: TopicHandler) -> None:
        """Subscribe to a topic."""
        await self._provider.subscribe_topic(self._session_id, topic, handler)

    async def unsubscribe(self, topic: str) -> None:
        """Unsubscribe from a specific topic."""
        await self._provider.unsubscribe_topic(self._session_id, topic)

    async def unsubscribe_all(self) -> None:
        """Unsubscribe from all topics (called on disconnect)."""
        await self._provider.unsubscribe_all(self._session_id)

    async def broadcast(self, topic: str, message: Any) -> None:
        """Broadcast a message to all subscribers on a topic."""
        await self._provider.broadcast(topic, message)
