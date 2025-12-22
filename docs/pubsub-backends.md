# Custom Pub/Sub Backends

PyView's pub/sub system is pluggable, allowing you to use distributed backends like Redis for multi-machine deployments.

## Overview

By default, PyView uses an in-memory pub/sub implementation suitable for single-instance deployments. For horizontally scaled applications, you'll need a distributed backend.

```python
# Default (in-memory)
app = PyView()

# Custom backend (Redis, PostgreSQL, etc.)
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

## Quick Start with Redis

### 1. Install Redis Client

```bash
pip install redis
```

### 2. Configure Your App

```python
from pyview import PyView
from redis_pubsub import RedisPubSub  # See examples below

app = PyView(
    pubsub=RedisPubSub(
        url="redis://localhost:6379",
        channel_prefix="myapp:"
    )
)
```

### 3. Your LiveViews Work Exactly the Same

```python
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

### 4. Run Multiple Instances

```bash
# Terminal 1
uvicorn app:app --port 8000

# Terminal 2
uvicorn app:app --port 8001

# Terminal 3
uvicorn app:app --port 8002
```

With a load balancer in front, users on different instances will see real-time updates from each other.

## Complete Examples

Full working implementations are available in [`examples/custom_pubsub/`](../../examples/custom_pubsub/):

- **[`redis_pubsub.py`](../../examples/custom_pubsub/redis_pubsub.py)** - Redis backend (recommended for production)
- **[`postgres_pubsub.py`](../../examples/custom_pubsub/postgres_pubsub.py)** - PostgreSQL NOTIFY/LISTEN backend
- **[`test_pubsub.py`](../../examples/custom_pubsub/test_pubsub.py)** - Test backend for unit testing
- **[`app.py`](../../examples/custom_pubsub/app.py)** - Demo counter app
- **[`docker-compose.yml`](../../examples/custom_pubsub/docker-compose.yml)** - Redis + Postgres services

See the [examples README](../../examples/custom_pubsub/README.md) for setup instructions and a working demo.

## Implementation Guide

### Key Concepts

When implementing a custom backend, understand these constraints:

**Handlers are local** - Handlers are Python async callables that can't be serialized. Each instance must:
1. Store handlers in local memory
2. Publish only message data to the distributed backend
3. Route received messages to local handlers only

**Messages must be serializable** - For distributed backends, messages should be JSON-compatible:

```python
# Good - JSON serializable
await socket.broadcast("updates", {"user_id": 123, "action": "joined"})
await socket.broadcast("counter", 42)

# Bad - not serializable
await socket.broadcast("data", my_dataclass)  # Convert with asdict() first
await socket.broadcast("func", some_function)  # Can't serialize functions
```

### Implementation Checklist

When building a custom backend:

- [ ] Store handlers in memory per instance (dict[str, dict[str, TopicHandler]])
- [ ] Subscribe to distributed backend only when first local handler subscribes
- [ ] Publish messages as JSON to distributed backend
- [ ] Listen for messages from distributed backend
- [ ] Route received messages to local handlers using `asyncio.create_task()`
- [ ] Handle errors gracefully (one failing handler shouldn't affect others)
- [ ] Clean up connections in `stop()`

### Backend Comparison

| Backend | Best For | Throughput | Setup Complexity |
|---------|----------|------------|------------------|
| **InMemory** (default) | Single instance, development | High | None |
| **Redis** | Production, multi-instance | Very High | Low (just Redis) |
| **PostgreSQL** | Already using Postgres | Medium | Low (use existing DB) |
| **Test** | Unit/integration tests | N/A | None |

### Testing Your Backend

Use the test implementation to verify your LiveView's pub/sub behavior:

```python
from test_pubsub import TestPubSub

def test_counter_broadcasts():
    test_pubsub = TestPubSub()
    app = PyView(pubsub=test_pubsub)

    # ... test your LiveView ...

    # Verify subscriptions
    assert ("session_123", "counter") in test_pubsub.subscriptions

    # Verify broadcasts
    assert ("counter", 5) in test_pubsub.broadcasts
```

## Production Considerations

### Environment Configuration

Use environment variables for connection URLs:

```python
import os

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
app = PyView(pubsub=RedisPubSub(redis_url))
```

### Error Handling

Implementations should:
- Log but not crash on malformed messages
- Isolate handler errors (use try/except around each handler call)
- Handle reconnection for network failures
- Clean up resources properly in `stop()`

### Channel Prefixes

Use channel prefixes to avoid collisions when multiple apps share the same Redis/Postgres:

```python
# App 1
app1 = PyView(pubsub=RedisPubSub(url, channel_prefix="app1:"))

# App 2
app2 = PyView(pubsub=RedisPubSub(url, channel_prefix="app2:"))
```

## Next Steps

- Check out the [working examples](../../examples/custom_pubsub/) with Docker Compose
- Review the [PubSubProvider Protocol source](../../pyview/pubsub/interfaces.py)
- Consider implementing backends for NATS, RabbitMQ, or AWS SNS/SQS
