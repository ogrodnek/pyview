"""Default in-memory pub/sub implementation."""

import asyncio
import logging
from typing import Any

from .interfaces import TopicHandler

logger = logging.getLogger(__name__)


class InMemoryPubSub:
    """Default in-memory pub/sub implementation.

    Suitable for single-instance deployments. Messages are delivered
    only within the same Python process.

    Satisfies the PubSubProvider protocol via structural typing.
    """

    def __init__(self):
        self._lock = asyncio.Lock()
        # topic -> {session_id -> handler}
        self._topic_subscribers: dict[str, dict[str, TopicHandler]] = {}
        # session_id -> {topic -> handler}
        self._session_topics: dict[str, dict[str, TopicHandler]] = {}

    async def subscribe_topic(
        self,
        session_id: str,
        topic: str,
        handler: TopicHandler,
    ) -> None:
        """Subscribe a session to a topic with a handler."""
        logger.debug("pubsub.subscribe_topic(%s, %s)", session_id, topic)
        async with self._lock:
            # Add to topic subscribers
            if topic not in self._topic_subscribers:
                self._topic_subscribers[topic] = {}
            self._topic_subscribers[topic][session_id] = handler

            # Track for session cleanup
            if session_id not in self._session_topics:
                self._session_topics[session_id] = {}
            self._session_topics[session_id][topic] = handler

    async def unsubscribe_topic(self, session_id: str, topic: str) -> None:
        """Unsubscribe a session from a specific topic."""
        logger.debug("pubsub.unsubscribe_topic(%s, %s)", session_id, topic)
        async with self._lock:
            self._unsubscribe_topic(session_id, topic)

    async def unsubscribe_all(self, session_id: str) -> None:
        """Remove all subscriptions for a session."""
        logger.debug("pubsub.unsubscribe_all(%s)", session_id)
        async with self._lock:
            if session_id in self._session_topics:
                for topic in list(self._session_topics[session_id].keys()):
                    self._unsubscribe_topic(session_id, topic)

    def _unsubscribe_topic(self, session_id: str, topic: str) -> None:
        """Internal unsubscribe (must be called with lock held)."""
        if topic in self._topic_subscribers:
            self._topic_subscribers[topic].pop(session_id, None)
            if not self._topic_subscribers[topic]:
                del self._topic_subscribers[topic]

        if session_id in self._session_topics:
            self._session_topics[session_id].pop(topic, None)
            if not self._session_topics[session_id]:
                del self._session_topics[session_id]

    async def broadcast(self, topic: str, message: Any) -> None:
        """Broadcast a message to all subscribers on a topic."""
        logger.debug("pubsub.broadcast(%s, %s)", topic, message)
        async with self._lock:
            handlers = list(self._topic_subscribers.get(topic, {}).values())

        # Dispatch outside the lock to prevent deadlocks
        for handler in handlers:
            asyncio.create_task(handler(topic, message))

    async def start(self) -> None:
        """No-op for in-memory implementation."""
        pass

    async def stop(self) -> None:
        """No-op for in-memory implementation."""
        pass
