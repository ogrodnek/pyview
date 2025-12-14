# Custom Pub/Sub Backend Examples

This directory contains complete, working implementations of custom pub/sub backends for PyView, along with a demo app and Docker Compose setup for testing.

## What's Included

- **`redis_pubsub.py`** - Redis-backed pub/sub (recommended for production)
- **`postgres_pubsub.py`** - PostgreSQL NOTIFY/LISTEN pub/sub
- **`test_pubsub.py`** - Test implementation for unit testing
- **`app.py`** - Demo counter app showing multi-instance pub/sub
- **`docker-compose.yml`** - Redis and PostgreSQL services

## Quick Start

### Option 1: Everything with Docker (Easiest)

Run the entire demo with one command:

```bash
docker-compose up --build
```

This starts:
- Redis on `localhost:6379`
- PostgreSQL on `localhost:5432`
- Three app instances (app1, app2, app3)
- Nginx load balancer on `localhost:8000`

**Test it**: Open http://localhost:8000 in multiple browsers and click increment. All browsers stay in sync via Redis pub/sub! 🎉

To see which backend instance you're connected to:
- http://localhost:8001 (app1 directly)
- http://localhost:8002 (app2 directly)
- http://localhost:8003 (app3 directly)
- http://localhost:8000 (load balanced across all three)

### Option 2: Run Locally

If you want to run the app locally (for development):

#### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

#### 2. Start Redis

```bash
docker-compose up -d redis postgres
```

This starts just Redis and PostgreSQL, without the app instances.

#### 3. Run Multiple App Instances

Open three terminals and run:

```bash
# Terminal 1
uvicorn app:app --port 8000

# Terminal 2
uvicorn app:app --port 8001

# Terminal 3
uvicorn app:app --port 8002
```

#### 4. Test It Out

1. Open http://localhost:8000 in one browser
2. Open http://localhost:8001 in another browser
3. Click increment on either one
4. Watch both update in real-time! 🎉

The counter stays in sync across all instances because they're communicating through Redis pub/sub.

## Using in Your App

### Redis (Recommended)

```python
from pyview import PyView
from redis_pubsub import RedisPubSub

app = PyView(
    pubsub=RedisPubSub(
        url="redis://localhost:6379",
        channel_prefix="myapp:"
    )
)
```

**When to use**: Production deployments with multiple app instances behind a load balancer.

### PostgreSQL

```python
from pyview import PyView
from postgres_pubsub import PostgresPubSub

app = PyView(
    pubsub=PostgresPubSub(
        dsn="postgresql://pyview:pyview@localhost/pyview",
        channel_prefix="myapp_"
    )
)
```

**When to use**: You're already using PostgreSQL and want to avoid adding Redis. Note: Lower throughput than Redis.

### Testing

```python
from pyview import PyView
from test_pubsub import TestPubSub

test_pubsub = TestPubSub()
app = PyView(pubsub=test_pubsub)

# In your tests
assert ("session_123", "updates") in test_pubsub.subscriptions
assert ("updates", {"action": "joined"}) in test_pubsub.broadcasts
```

**When to use**: Unit and integration tests where you don't want external dependencies.

## Implementation Details

### How It Works

Distributed pub/sub backends must handle a key challenge: **handlers are local Python callables** that can't be serialized and sent over the network. The solution:

1. **Local handler storage**: Each instance stores handlers in memory
2. **Message broadcasting**: Only message data is sent through Redis/Postgres
3. **Local dispatch**: Each instance routes received messages to its own handlers

### Redis Implementation

The Redis implementation uses:
- `redis.asyncio` for async operations
- Pub/sub channels for message distribution
- Reference counting for channel subscriptions (only subscribe when first local handler subscribes)
- Background listener task for receiving messages

### PostgreSQL Implementation

The PostgreSQL implementation uses:
- `asyncpg` for async operations
- `NOTIFY`/`LISTEN` for pub/sub
- Separate connections for publish and listen
- Callback-based notification handling

### Message Serialization

Messages must be JSON-serializable:

```python
# Good
await socket.broadcast("updates", {"user_id": 123, "action": "joined"})
await socket.broadcast("counter", 42)

# Bad - won't work with distributed backends
await socket.broadcast("data", my_dataclass)  # Use asdict() first
await socket.broadcast("func", some_function)  # Can't serialize functions
```

## Implementing Your Own Backend

To create a custom backend, implement these methods:

```python
class MyPubSub:
    async def subscribe_topic(self, session_id: str, topic: str, handler: TopicHandler) -> None:
        """Subscribe a session to a topic."""
        ...

    async def unsubscribe_topic(self, session_id: str, topic: str) -> None:
        """Unsubscribe from a topic."""
        ...

    async def unsubscribe_all(self, session_id: str) -> None:
        """Remove all subscriptions for a session."""
        ...

    async def broadcast(self, topic: str, message: Any) -> None:
        """Broadcast a message to all subscribers."""
        ...

    async def start(self) -> None:
        """Called when the app starts."""
        ...

    async def stop(self) -> None:
        """Called when the app shuts down."""
        ...
```

See the [PubSubProvider Protocol](../../pyview/pubsub/interfaces.py) for full documentation.

## Production Deployment

### Environment Variables

The demo app reads `REDIS_URL` from the environment:

```bash
export REDIS_URL="redis://your-redis-host:6379"
uvicorn app:app
```

### Connection Pooling

For production, consider connection pooling:

```python
class RedisPubSub:
    def __init__(self, url: str, max_connections: int = 50):
        self._pool = redis.ConnectionPool.from_url(
            url,
            max_connections=max_connections,
            decode_responses=False
        )
        self._client = redis.Redis(connection_pool=self._pool)
```

### Error Handling

Both implementations include:
- Graceful handling of malformed messages
- Isolated error handling (one failing handler doesn't affect others)
- Proper cleanup on shutdown

### Monitoring

Add metrics for:
- Active subscriptions per instance
- Message publish rate
- Message receive rate
- Handler execution time

## Troubleshooting

### Redis connection errors

```
redis.exceptions.ConnectionError: Error connecting to Redis
```

Make sure Redis is running:
```bash
docker-compose up -d redis
redis-cli ping  # Should return PONG
```

### PostgreSQL connection errors

```
asyncpg.exceptions.CannotConnectNowError
```

Check PostgreSQL is running and credentials are correct:
```bash
docker-compose up -d postgres
psql postgresql://pyview:pyview@localhost/pyview -c "SELECT 1"
```

### Messages not syncing across instances

- Check all instances are connected to the same Redis/Postgres
- Verify `channel_prefix` is the same across all instances
- Check logs for subscription/broadcast errors

## Next Steps

- See the [pub/sub documentation](../../docs/pubsub-backends.md) for more details
- Check out [production deployment patterns](../../docs/deployment.md) (if available)
- Consider implementing NATS, RabbitMQ, or AWS SNS/SQS backends

## License

These examples are part of the PyView project and use the same license.
