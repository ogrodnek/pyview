# Pluggable Pub/Sub Design for PyView

## Overview

This document outlines the design for making PyView's pub/sub system pluggable, enabling multi-machine deployments with backends like Redis, while maintaining backward compatibility and adding no new dependencies to the core library.

## Current State

### Architecture
- **`PubSubHub`** (`pyview/vendor/flet/pubsub/pub_sub.py`): Central message hub that stores subscriptions in memory using dictionaries
- **`PubSub`**: Session-scoped wrapper that delegates to `PubSubHub` with automatic `session_id` injection
- **Global singleton**: `pub_sub_hub = PubSubHub()` instantiated at module level in `live_socket.py:40`

### Current Usage in ConnectedLiveViewSocket

```python
# live_socket.py
self.pub_sub = PubSub(pub_sub_hub, topic)

# Methods used:
await self.pub_sub.subscribe_topic_async(topic, handler)
await self.pub_sub.send_all_on_topic_async(topic, message)
await self.pub_sub.unsubscribe_all_async()
```

### Limitations
1. In-memory only - doesn't work across multiple server instances
2. Not configurable - hardcoded singleton instantiation
3. No abstraction layer for alternative implementations

---

## Proposed Design

### Design Goals
1. **Pluggable backends**: Support Redis, PostgreSQL NOTIFY/LISTEN, or custom implementations
2. **Zero new dependencies**: Core PyView remains lightweight
3. **Backward compatible**: Existing code works unchanged
4. **Follow existing patterns**: Mirror the `InstrumentationProvider` architecture
5. **Minimal API surface**: Only abstract what's actually needed

### Core Interface

Create an abstract base class following the existing `InstrumentationProvider` pattern:

```python
# pyview/pubsub/interfaces.py
from abc import ABC, abstractmethod
from typing import Any, Callable, Coroutine

# Type alias for async handlers
TopicHandler = Callable[[str, Any], Coroutine[Any, Any, None]]


class PubSubProvider(ABC):
    """Abstract base class for pub/sub implementations.

    Implementations must handle:
    - Topic-based subscriptions per session
    - Broadcasting messages to all subscribers on a topic
    - Proper cleanup when sessions disconnect

    For distributed implementations (Redis, etc.):
    - Handlers are local Python callables (not serializable)
    - Messages must be serializable (JSON-compatible recommended)
    - Implementation should handle cross-instance message routing
    """

    @abstractmethod
    async def subscribe_topic(
        self,
        session_id: str,
        topic: str,
        handler: TopicHandler
    ) -> None:
        """Subscribe a session to a topic with a handler.

        Args:
            session_id: Unique identifier for the session
            topic: Topic name to subscribe to
            handler: Async callable(topic, message) to invoke on messages
        """
        pass

    @abstractmethod
    async def unsubscribe_topic(self, session_id: str, topic: str) -> None:
        """Unsubscribe a session from a specific topic."""
        pass

    @abstractmethod
    async def unsubscribe_all(self, session_id: str) -> None:
        """Remove all subscriptions for a session (cleanup on disconnect)."""
        pass

    @abstractmethod
    async def broadcast(self, topic: str, message: Any) -> None:
        """Broadcast a message to all subscribers on a topic.

        Note: For distributed implementations, `message` should be
        JSON-serializable. Complex objects should be converted before
        broadcasting.
        """
        pass

    # Optional lifecycle hooks for implementations that need them
    async def start(self) -> None:
        """Called when the PyView app starts. Override for setup."""
        pass

    async def stop(self) -> None:
        """Called when the PyView app shuts down. Override for cleanup."""
        pass
```

### Default In-Memory Implementation

Refactor the existing `PubSubHub` to implement the new interface:

```python
# pyview/pubsub/memory.py
import asyncio
from typing import Any

from .interfaces import PubSubProvider, TopicHandler


class InMemoryPubSub(PubSubProvider):
    """Default in-memory pub/sub implementation.

    Suitable for single-instance deployments. Messages are delivered
    only within the same Python process.
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
        handler: TopicHandler
    ) -> None:
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
        async with self._lock:
            if topic in self._topic_subscribers:
                self._topic_subscribers[topic].pop(session_id, None)
                if not self._topic_subscribers[topic]:
                    del self._topic_subscribers[topic]

            if session_id in self._session_topics:
                self._session_topics[session_id].pop(topic, None)
                if not self._session_topics[session_id]:
                    del self._session_topics[session_id]

    async def unsubscribe_all(self, session_id: str) -> None:
        async with self._lock:
            if session_id in self._session_topics:
                for topic in list(self._session_topics[session_id].keys()):
                    if topic in self._topic_subscribers:
                        self._topic_subscribers[topic].pop(session_id, None)
                        if not self._topic_subscribers[topic]:
                            del self._topic_subscribers[topic]
                del self._session_topics[session_id]

    async def broadcast(self, topic: str, message: Any) -> None:
        async with self._lock:
            handlers = list(self._topic_subscribers.get(topic, {}).values())

        # Dispatch outside the lock to prevent deadlocks
        for handler in handlers:
            asyncio.create_task(handler(topic, message))
```

### Session-Scoped Wrapper

Keep a thin wrapper for ergonomic use in sockets:

```python
# pyview/pubsub/session.py
from typing import Any

from .interfaces import PubSubProvider, TopicHandler


class SessionPubSub:
    """Session-scoped pub/sub wrapper.

    Provides a convenient API that automatically includes the session_id
    in all operations.
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
```

### Integration with PyView

Update `PyView.__init__()` to accept an optional pub/sub provider:

```python
# pyview/pyview.py
from pyview.pubsub import PubSubProvider, InMemoryPubSub

class PyView(Starlette):
    def __init__(
        self,
        *args,
        instrumentation: Optional[InstrumentationProvider] = None,
        pubsub: Optional[PubSubProvider] = None,  # NEW
        **kwargs
    ):
        # ...
        self.pubsub = pubsub or InMemoryPubSub()
        self.live_handler = LiveSocketHandler(
            self.view_lookup,
            self.instrumentation,
            self.pubsub  # Pass to handler
        )
```

Update lifecycle management:

```python
# In _create_lifespan()
async def lifespan(app):
    app.live_handler.start_scheduler()
    await app.pubsub.start()  # NEW: Initialize pub/sub

    if user_lifespan:
        async with user_lifespan(app):
            yield
    else:
        yield

    await app.pubsub.stop()  # NEW: Cleanup pub/sub
    await app.live_handler.shutdown_scheduler()
```

Update `ConnectedLiveViewSocket`:

```python
# live_socket.py
from pyview.pubsub import SessionPubSub, PubSubProvider

class ConnectedLiveViewSocket(Generic[T]):
    def __init__(
        self,
        websocket: WebSocket,
        topic: str,
        liveview: LiveView,
        scheduler: AsyncIOScheduler,
        instrumentation: InstrumentationProvider,
        pubsub_provider: PubSubProvider,  # NEW
    ):
        # ...
        self._pubsub = SessionPubSub(pubsub_provider, topic)

    async def subscribe(self, topic: str):
        await self._pubsub.subscribe(topic, self._topic_callback_internal)

    async def broadcast(self, topic: str, message: Any):
        await self._pubsub.broadcast(topic, message)

    async def close(self):
        # ...
        await self._pubsub.unsubscribe_all()
```

---

## Redis Implementation Example

This would be a **separate package** (e.g., `pyview-redis`) that users install if needed:

```python
# Example: pyview_redis/pubsub.py
import asyncio
import json
from typing import Any

import redis.asyncio as redis

from pyview.pubsub import PubSubProvider, TopicHandler


class RedisPubSub(PubSubProvider):
    """Redis-backed pub/sub for multi-instance deployments.

    Install: pip install pyview-redis

    Usage:
        from pyview_redis import RedisPubSub

        app = PyView(pubsub=RedisPubSub("redis://localhost:6379"))
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379",
        channel_prefix: str = "pyview:",
    ):
        self._url = url
        self._prefix = channel_prefix
        self._client: redis.Redis | None = None
        self._pubsub: redis.client.PubSub | None = None
        self._listener_task: asyncio.Task | None = None

        # Local handler tracking (handlers are not serializable)
        self._lock = asyncio.Lock()
        self._topic_subscribers: dict[str, dict[str, TopicHandler]] = {}
        self._session_topics: dict[str, dict[str, TopicHandler]] = {}

    async def start(self) -> None:
        """Connect to Redis and start listening for messages."""
        self._client = redis.from_url(self._url)
        self._pubsub = self._client.pubsub()
        self._listener_task = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        """Disconnect from Redis and cleanup."""
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

    async def subscribe_topic(
        self,
        session_id: str,
        topic: str,
        handler: TopicHandler
    ) -> None:
        channel = f"{self._prefix}{topic}"

        async with self._lock:
            # Track handler locally
            if topic not in self._topic_subscribers:
                self._topic_subscribers[topic] = {}
                # First subscriber to topic - subscribe in Redis
                await self._pubsub.subscribe(channel)

            self._topic_subscribers[topic][session_id] = handler

            if session_id not in self._session_topics:
                self._session_topics[session_id] = {}
            self._session_topics[session_id][topic] = handler

    async def unsubscribe_topic(self, session_id: str, topic: str) -> None:
        channel = f"{self._prefix}{topic}"

        async with self._lock:
            if topic in self._topic_subscribers:
                self._topic_subscribers[topic].pop(session_id, None)

                if not self._topic_subscribers[topic]:
                    # Last subscriber - unsubscribe from Redis
                    del self._topic_subscribers[topic]
                    await self._pubsub.unsubscribe(channel)

            if session_id in self._session_topics:
                self._session_topics[session_id].pop(topic, None)
                if not self._session_topics[session_id]:
                    del self._session_topics[session_id]

    async def unsubscribe_all(self, session_id: str) -> None:
        async with self._lock:
            if session_id in self._session_topics:
                for topic in list(self._session_topics[session_id].keys()):
                    channel = f"{self._prefix}{topic}"

                    if topic in self._topic_subscribers:
                        self._topic_subscribers[topic].pop(session_id, None)

                        if not self._topic_subscribers[topic]:
                            del self._topic_subscribers[topic]
                            await self._pubsub.unsubscribe(channel)

                del self._session_topics[session_id]

    async def broadcast(self, topic: str, message: Any) -> None:
        """Publish message to Redis channel."""
        channel = f"{self._prefix}{topic}"
        payload = json.dumps({"topic": topic, "message": message})
        await self._client.publish(channel, payload)

    async def _listen(self) -> None:
        """Background task to receive Redis messages and dispatch to handlers."""
        async for message in self._pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    topic = data["topic"]
                    payload = data["message"]

                    async with self._lock:
                        handlers = list(
                            self._topic_subscribers.get(topic, {}).values()
                        )

                    for handler in handlers:
                        asyncio.create_task(handler(topic, payload))

                except Exception as e:
                    # Log but don't crash the listener
                    import logging
                    logging.error(f"Error processing Redis message: {e}")
```

### Usage Example

```python
# app.py
from pyview import PyView
from pyview_redis import RedisPubSub  # Separate package

# Single instance (default)
app = PyView()

# Multi-instance with Redis
app = PyView(
    pubsub=RedisPubSub(
        url="redis://localhost:6379",
        channel_prefix="myapp:"
    )
)
```

---

## Alternative Backend Examples

### PostgreSQL NOTIFY/LISTEN

```python
# Example structure for PostgreSQL backend
class PostgresPubSub(PubSubProvider):
    """PostgreSQL NOTIFY/LISTEN for deployments already using PostgreSQL.

    Pros: No additional infrastructure if you have PostgreSQL
    Cons: Less throughput than Redis, doesn't persist messages
    """

    def __init__(self, dsn: str, channel_prefix: str = "pyview_"):
        self._dsn = dsn
        self._prefix = channel_prefix
        # ... similar pattern to Redis

    async def broadcast(self, topic: str, message: Any) -> None:
        channel = f"{self._prefix}{topic}"
        payload = json.dumps(message)
        await self._conn.execute(f"NOTIFY {channel}, '{payload}'")
```

### NATS

```python
# Example structure for NATS backend
class NatsPubSub(PubSubProvider):
    """NATS for high-performance distributed messaging.

    Pros: Very high throughput, built for pub/sub
    Cons: Additional infrastructure to manage
    """
    pass
```

---

## File Structure

```
pyview/
├── pubsub/
│   ├── __init__.py          # Exports: PubSubProvider, InMemoryPubSub, SessionPubSub
│   ├── interfaces.py        # Abstract PubSubProvider class
│   ├── memory.py            # InMemoryPubSub implementation
│   └── session.py           # SessionPubSub wrapper
├── vendor/
│   └── flet/
│       └── pubsub/          # DEPRECATED - keep for backward compat temporarily
├── live_socket.py           # Updated to use new pub/sub
├── pyview.py                # Updated with pubsub parameter
└── ws_handler.py            # Updated to pass pubsub to sockets
```

---

## Migration Path

### Phase 1: Add New Interface (Non-Breaking)
1. Create `pyview/pubsub/` module with interface and in-memory impl
2. Add optional `pubsub` parameter to `PyView.__init__()`
3. Default to `InMemoryPubSub` when not provided
4. Update internal code to use new interface
5. Keep old `vendor/flet/pubsub` working for any direct imports

### Phase 2: Documentation
1. Document the `PubSubProvider` interface
2. Provide Redis implementation example
3. Add guide for implementing custom backends

### Phase 3: Deprecation (Future)
1. Add deprecation warning to `vendor/flet/pubsub` imports
2. Eventually remove in a future major version

---

## Considerations

### Message Serialization
For distributed backends, messages must be serializable. Recommend documenting:
- Use JSON-serializable types (dict, list, str, int, float, bool, None)
- For dataclasses, convert with `asdict()` before broadcasting
- Complex objects need explicit serialization

### Handler Execution
- Handlers are async callables executed via `asyncio.create_task()`
- Distributed implementations must route messages to local handlers only
- A session's handler is only callable within the same Python process

### Error Handling
- Implementations should not raise on message delivery failure to one handler
- Failed handlers shouldn't prevent delivery to other subscribers
- Connection errors (Redis down) should be logged, with optional retry logic

### Testing
- Add mock/test implementation: `TestPubSub` that records all operations
- Useful for integration testing LiveViews that use pub/sub

---

## Summary

This design:
1. **Mirrors existing patterns** - Follows `InstrumentationProvider` architecture
2. **Minimal interface** - Only 4 abstract methods needed
3. **Zero new deps** - Core PyView stays lightweight
4. **Easy to implement** - Redis example is ~100 lines
5. **Backward compatible** - Default in-memory behavior unchanged
6. **Production ready** - Lifecycle hooks for proper startup/shutdown
