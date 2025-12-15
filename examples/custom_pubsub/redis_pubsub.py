"""Redis-backed pub/sub for multi-instance PyView deployments.

Requirements:
    pip install redis

Usage:
    from redis_pubsub import RedisPubSub

    app = PyView(pubsub=RedisPubSub("redis://localhost:6379"))

How it works:
    - Handlers are stored locally (they're Python callables, not serializable)
    - When broadcast() is called, the message is published to Redis
    - All instances receive the message and dispatch to their local handlers
    - This enables real-time updates across multiple server instances
"""

import asyncio
import json
import logging
from contextlib import suppress
from typing import Any, Callable, Coroutine

import redis.asyncio as redis

logger = logging.getLogger(__name__)

TopicHandler = Callable[[str, Any], Coroutine[Any, Any, None]]


class RedisPubSub:
    """Redis-backed pub/sub implementation."""

    def __init__(
        self,
        url: str = "redis://localhost:6379",
        channel_prefix: str = "pyview:",
    ):
        """Initialize Redis pub/sub.

        Args:
            url: Redis connection URL
            channel_prefix: Prefix for Redis channel names (helps avoid collisions)
        """
        self._url = url
        self._prefix = channel_prefix
        self._client: redis.Redis | None = None
        self._pubsub: redis.client.PubSub | None = None
        self._listener_task: asyncio.Task | None = None

        # Local handler tracking (handlers can't be serialized to Redis)
        self._lock = asyncio.Lock()
        # topic -> {session_id -> handler}
        self._topic_subscribers: dict[str, dict[str, TopicHandler]] = {}
        # session_id -> {topic -> handler}
        self._session_topics: dict[str, dict[str, TopicHandler]] = {}

    async def start(self) -> None:
        """Connect to Redis and start the message listener."""
        self._client = redis.from_url(self._url, decode_responses=True)
        self._pubsub = self._client.pubsub()
        self._listener_task = asyncio.create_task(self._listen())
        logger.info("Redis pub/sub connected to %s", self._url)

    async def stop(self) -> None:
        """Disconnect from Redis and clean up."""
        if self._listener_task:
            self._listener_task.cancel()
            # Suppress CancelledError from listener task - expected during shutdown
            with suppress(asyncio.CancelledError):
                await self._listener_task

        if self._pubsub:
            await self._pubsub.close()

        if self._client:
            await self._client.close()

        logger.info("Redis pub/sub disconnected")

    async def subscribe_topic(
        self,
        session_id: str,
        topic: str,
        handler: TopicHandler,
    ) -> None:
        """Subscribe a session to a topic."""
        channel = f"{self._prefix}{topic}"

        async with self._lock:
            # Track handler locally
            if topic not in self._topic_subscribers:
                self._topic_subscribers[topic] = {}
                # First local subscriber - subscribe to Redis channel
                await self._pubsub.subscribe(channel)
                logger.debug("Subscribed to Redis channel: %s", channel)

            self._topic_subscribers[topic][session_id] = handler

            # Track for session cleanup
            if session_id not in self._session_topics:
                self._session_topics[session_id] = {}
            self._session_topics[session_id][topic] = handler

    async def unsubscribe_topic(self, session_id: str, topic: str) -> None:
        """Unsubscribe a session from a topic."""
        channel = f"{self._prefix}{topic}"

        async with self._lock:
            if topic in self._topic_subscribers:
                self._topic_subscribers[topic].pop(session_id, None)

                if not self._topic_subscribers[topic]:
                    # Last local subscriber - unsubscribe from Redis
                    del self._topic_subscribers[topic]
                    await self._pubsub.unsubscribe(channel)
                    logger.debug("Unsubscribed from Redis channel: %s", channel)

            if session_id in self._session_topics:
                self._session_topics[session_id].pop(topic, None)
                if not self._session_topics[session_id]:
                    del self._session_topics[session_id]

    async def unsubscribe_all(self, session_id: str) -> None:
        """Remove all subscriptions for a session (called on disconnect)."""
        async with self._lock:
            if session_id not in self._session_topics:
                return

            for topic in list(self._session_topics[session_id].keys()):
                channel = f"{self._prefix}{topic}"

                if topic in self._topic_subscribers:
                    self._topic_subscribers[topic].pop(session_id, None)

                    if not self._topic_subscribers[topic]:
                        del self._topic_subscribers[topic]
                        await self._pubsub.unsubscribe(channel)

            del self._session_topics[session_id]

    async def broadcast(self, topic: str, message: Any) -> None:
        """Publish a message to all subscribers across all instances."""
        channel = f"{self._prefix}{topic}"
        # Include topic in payload for routing on receive
        payload = json.dumps({"topic": topic, "message": message})
        await self._client.publish(channel, payload)

    async def _listen(self) -> None:
        """Background task that receives Redis messages and dispatches to handlers."""
        try:
            async for message in self._pubsub.listen():
                if message["type"] != "message":
                    continue

                try:
                    data = json.loads(message["data"])

                    # Validate required fields
                    if "topic" not in data or "message" not in data:
                        logger.warning(
                            "Redis message missing required fields: %s", list(data.keys())
                        )
                        continue

                    topic = data["topic"]
                    payload = data["message"]

                    # Get handlers while holding lock
                    async with self._lock:
                        handlers = list(self._topic_subscribers.get(topic, {}).values())

                    # Dispatch outside lock to prevent deadlocks
                    for handler in handlers:
                        asyncio.create_task(handler(topic, payload))

                except json.JSONDecodeError:
                    # Malformed JSON from Redis - log and continue
                    logger.warning("Invalid JSON in Redis message: %s", message["data"])
                except Exception:
                    # Unexpected error processing message - log and continue
                    logger.exception("Error processing Redis message")

        except asyncio.CancelledError:
            # Task cancelled during shutdown - this is expected
            pass
        except Exception:
            # Unexpected listener crash - log for debugging
            logger.exception("Redis listener crashed")
