"""PostgreSQL NOTIFY/LISTEN pub/sub backend.

Requirements:
    pip install asyncpg

Usage:
    app = PyView(pubsub=PostgresPubSub("postgresql://user:pass@localhost/db"))

Pros:
    - No additional infrastructure if you already use PostgreSQL
    - Transactional guarantees available if needed

Cons:
    - Lower throughput than Redis
    - Not designed for high-volume pub/sub
"""

import asyncio
import json
import logging
from typing import Any, Callable, Coroutine

import asyncpg

logger = logging.getLogger(__name__)

TopicHandler = Callable[[str, Any], Coroutine[Any, Any, None]]


class PostgresPubSub:
    """PostgreSQL NOTIFY/LISTEN pub/sub implementation."""

    def __init__(self, dsn: str, channel_prefix: str = "pyview_"):
        self._dsn = dsn
        self._prefix = channel_prefix
        self._conn: asyncpg.Connection | None = None
        self._listen_conn: asyncpg.Connection | None = None

        self._lock = asyncio.Lock()
        self._topic_subscribers: dict[str, dict[str, TopicHandler]] = {}
        self._session_topics: dict[str, dict[str, TopicHandler]] = {}
        self._subscribed_channels: set[str] = set()

    async def start(self) -> None:
        """Connect to PostgreSQL."""
        # Separate connections for publish and listen
        self._conn = await asyncpg.connect(self._dsn)
        self._listen_conn = await asyncpg.connect(self._dsn)
        logger.info("PostgreSQL pub/sub connected")

    async def stop(self) -> None:
        """Disconnect from PostgreSQL."""
        if self._conn:
            await self._conn.close()
        if self._listen_conn:
            await self._listen_conn.close()
        logger.info("PostgreSQL pub/sub disconnected")

    async def subscribe_topic(
        self,
        session_id: str,
        topic: str,
        handler: TopicHandler,
    ) -> None:
        """Subscribe to a topic using LISTEN."""
        channel = f"{self._prefix}{topic}"

        async with self._lock:
            if topic not in self._topic_subscribers:
                self._topic_subscribers[topic] = {}

                if channel not in self._subscribed_channels:
                    await self._listen_conn.add_listener(
                        channel, self._make_listener(topic)
                    )
                    self._subscribed_channels.add(channel)

            self._topic_subscribers[topic][session_id] = handler

            if session_id not in self._session_topics:
                self._session_topics[session_id] = {}
            self._session_topics[session_id][topic] = handler

    def _make_listener(self, topic: str):
        """Create a listener callback for a topic."""
        def listener(conn, pid, channel, payload):
            asyncio.create_task(self._handle_notification(topic, payload))
        return listener

    async def _handle_notification(self, topic: str, payload: str) -> None:
        """Handle incoming NOTIFY."""
        try:
            message = json.loads(payload)

            async with self._lock:
                handlers = list(self._topic_subscribers.get(topic, {}).values())

            for handler in handlers:
                asyncio.create_task(handler(topic, message))
        except Exception:
            logger.exception("Error handling PostgreSQL notification")

    async def unsubscribe_topic(self, session_id: str, topic: str) -> None:
        """Unsubscribe from a topic."""
        channel = f"{self._prefix}{topic}"

        async with self._lock:
            if topic in self._topic_subscribers:
                self._topic_subscribers[topic].pop(session_id, None)

                if not self._topic_subscribers[topic]:
                    del self._topic_subscribers[topic]
                    if channel in self._subscribed_channels:
                        await self._listen_conn.remove_listener(channel, None)
                        self._subscribed_channels.discard(channel)

            if session_id in self._session_topics:
                self._session_topics[session_id].pop(topic, None)
                if not self._session_topics[session_id]:
                    del self._session_topics[session_id]

    async def unsubscribe_all(self, session_id: str) -> None:
        """Remove all subscriptions for a session."""
        async with self._lock:
            if session_id not in self._session_topics:
                return

            for topic in list(self._session_topics[session_id].keys()):
                channel = f"{self._prefix}{topic}"

                if topic in self._topic_subscribers:
                    self._topic_subscribers[topic].pop(session_id, None)

                    if not self._topic_subscribers[topic]:
                        del self._topic_subscribers[topic]
                        if channel in self._subscribed_channels:
                            await self._listen_conn.remove_listener(channel, None)
                            self._subscribed_channels.discard(channel)

            del self._session_topics[session_id]

    async def broadcast(self, topic: str, message: Any) -> None:
        """Broadcast using NOTIFY."""
        channel = f"{self._prefix}{topic}"
        payload = json.dumps(message)
        # PostgreSQL NOTIFY has an 8000 byte payload limit
        await self._conn.execute(f"NOTIFY {channel}, $1", payload)
