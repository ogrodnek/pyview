"""Default in-memory pub/sub implementation."""

from typing import Any

from pyview.vendor.flet.pubsub import PubSubHub

from .interfaces import TopicHandler


class InMemoryPubSub:
    """Default in-memory pub/sub implementation.

    Delegates to the battle-tested Flet PubSubHub implementation.
    Suitable for single-instance deployments. Messages are delivered
    only within the same Python process.

    Satisfies the PubSubProvider protocol via structural typing.
    """

    def __init__(self):
        self._hub = PubSubHub()

    async def subscribe_topic(
        self,
        session_id: str,
        topic: str,
        handler: TopicHandler,
    ) -> None:
        """Subscribe a session to a topic with a handler."""
        await self._hub.subscribe_topic_async(session_id, topic, handler)

    async def unsubscribe_topic(self, session_id: str, topic: str) -> None:
        """Unsubscribe a session from a specific topic."""
        await self._hub.unsubscribe_topic_async(session_id, topic)

    async def unsubscribe_all(self, session_id: str) -> None:
        """Remove all subscriptions for a session."""
        await self._hub.unsubscribe_all_async(session_id)

    async def broadcast(self, topic: str, message: Any) -> None:
        """Broadcast a message to all subscribers on a topic."""
        await self._hub.send_all_on_topic_async(topic, message)

    async def start(self) -> None:
        """No-op for in-memory implementation."""
        pass

    async def stop(self) -> None:
        """No-op for in-memory implementation."""
        pass
