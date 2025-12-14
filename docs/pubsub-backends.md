# Custom Pub/Sub Backends

PyView's pub/sub system is pluggable, allowing you to use distributed backends like Redis for multi-machine deployments. This guide shows how to implement custom backends.

## Overview

By default, PyView uses an in-memory pub/sub implementation suitable for single-instance deployments. For horizontally scaled applications, you'll need a distributed backend.

```python
# Default (in-memory)
app = PyView()

# Custom backend
app = PyView(pubsub=RedisPubSub("redis://localhost:6379"))
```

## The PubSubProvider Protocol

Any class implementing these methods is compatible:

```python
from typing import Any, Callable, Coroutine

TopicHandler = Callable[[str, Any], Coroutine[Any, Any, None]]

class PubSubProvider:
    async def subscribe_topic(self, session_id: str, topic: str, handler: TopicHandler) -> None:
        """Subscribe a session to a topic."""
        ...

    async def unsubscribe_topic(self, session_id: str, topic: str) -> None:
        """Unsubscribe a session from a topic."""
        ...

    async def unsubscribe_all(self, session_id: str) -> None:
        """Remove all subscriptions for a session."""
        ...

    async def broadcast(self, topic: str, message: Any) -> None:
        """Broadcast a message to all subscribers on a topic."""
        ...

    async def start(self) -> None:
        """Called when the app starts."""
        ...

    async def stop(self) -> None:
        """Called when the app shuts down."""
        ...
```

## Redis Implementation

Here's a complete Redis implementation you can use as a starting point:

```python
# redis_pubsub.py
import asyncio
import json
import logging
from typing import Any, Callable, Coroutine

import redis.asyncio as redis

logger = logging.getLogger(__name__)

TopicHandler = Callable[[str, Any], Coroutine[Any, Any, None]]


class RedisPubSub:
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
        self._client = redis.from_url(self._url)
        self._pubsub = self._client.pubsub()
        self._listener_task = asyncio.create_task(self._listen())
        logger.info("Redis pub/sub connected to %s", self._url)

    async def stop(self) -> None:
        """Disconnect from Redis and clean up."""
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

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
                    topic = data["topic"]
                    payload = data["message"]

                    # Get handlers while holding lock
                    async with self._lock:
                        handlers = list(
                            self._topic_subscribers.get(topic, {}).values()
                        )

                    # Dispatch outside lock to prevent deadlocks
                    for handler in handlers:
                        asyncio.create_task(handler(topic, payload))

                except json.JSONDecodeError:
                    logger.warning("Invalid JSON in Redis message: %s", message["data"])
                except Exception:
                    logger.exception("Error processing Redis message")

        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Redis listener crashed")
```

### Usage Example

```python
# app.py
from pyview import PyView
from redis_pubsub import RedisPubSub

# Create app with Redis pub/sub
app = PyView(
    pubsub=RedisPubSub(
        url="redis://localhost:6379",
        channel_prefix="myapp:",  # Namespace your channels
    )
)

# Your LiveViews work exactly the same
@app.add_live_view("/counter")
class CounterLiveView(LiveView):
    async def mount(self, socket, session):
        socket.context = {"count": 0}
        if is_connected(socket):
            await socket.subscribe("counter")

    async def handle_event(self, event, payload, socket):
        if event == "increment":
            socket.context["count"] += 1
            # This now broadcasts via Redis to ALL instances
            await socket.broadcast("counter", socket.context["count"])

    async def handle_info(self, event, socket):
        socket.context["count"] = event.payload
```

### Running Multiple Instances

```bash
# Terminal 1
uvicorn app:app --port 8000

# Terminal 2
uvicorn app:app --port 8001

# Terminal 3
uvicorn app:app --port 8002
```

With a load balancer in front, users on different instances will see real-time updates from each other.

## PostgreSQL Implementation

If you're already using PostgreSQL, you can use NOTIFY/LISTEN:

```python
# postgres_pubsub.py
import asyncio
import json
import logging
from typing import Any, Callable, Coroutine

import asyncpg

logger = logging.getLogger(__name__)

TopicHandler = Callable[[str, Any], Coroutine[Any, Any, None]]


class PostgresPubSub:
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
```

## Key Implementation Notes

### Handlers Are Local

Handlers are Python async functions - they can't be serialized and sent over the network. Your implementation must:

1. Store handlers in local memory (per-instance)
2. Publish only the message data to the distributed backend
3. Route received messages to local handlers

### Message Serialization

Messages must be JSON-serializable for distributed backends:

```python
# Good - JSON serializable
await socket.broadcast("updates", {"user_id": 123, "action": "joined"})
await socket.broadcast("counter", 42)

# Bad - not serializable
await socket.broadcast("data", my_dataclass)  # Convert with asdict() first
await socket.broadcast("func", some_function)  # Can't serialize functions
```

### Error Handling

Your implementation should:

- Not crash if one handler fails (isolate errors)
- Log but continue on malformed messages
- Handle reconnection for network failures

### Testing

Consider creating a test implementation:

```python
class TestPubSub:
    """Records all pub/sub operations for testing."""

    def __init__(self):
        self.subscriptions: list[tuple[str, str]] = []  # (session_id, topic)
        self.broadcasts: list[tuple[str, Any]] = []  # (topic, message)
        self.handlers: dict[str, dict[str, TopicHandler]] = {}

    async def subscribe_topic(self, session_id: str, topic: str, handler: TopicHandler) -> None:
        self.subscriptions.append((session_id, topic))
        if topic not in self.handlers:
            self.handlers[topic] = {}
        self.handlers[topic][session_id] = handler

    async def broadcast(self, topic: str, message: Any) -> None:
        self.broadcasts.append((topic, message))
        # Immediately dispatch to local handlers for testing
        for handler in self.handlers.get(topic, {}).values():
            await handler(topic, message)

    # ... other methods
```
