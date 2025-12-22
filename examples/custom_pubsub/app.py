"""Demo app showing multi-instance pub/sub with Redis.

This counter app demonstrates how pub/sub enables real-time updates across
multiple server instances. When any user clicks increment/decrement, ALL
connected users see the update immediately - even if they're connected to
different server instances.

To test locally:
    1. Start Redis: docker-compose up -d
    2. Run multiple instances:
       Terminal 1: uvicorn app:app --port 8000
       Terminal 2: uvicorn app:app --port 8001
       Terminal 3: uvicorn app:app --port 8002
    3. Open http://localhost:8000 and http://localhost:8001 in different browsers
    4. Click increment on one - see it update on both!

To switch backends:
    - Redis (recommended): RedisPubSub("redis://localhost:6379")
    - PostgreSQL: PostgresPubSub("postgresql://user:pass@localhost/db")
    - Testing: TestPubSub()
"""

import os
from typing import TypedDict

from redis_pubsub import RedisPubSub

from pyview import LiveView, PyView, is_connected


class CounterContext(TypedDict):
    count: int


class CounterLiveView(LiveView[CounterContext]):
    """Shared counter across all instances."""

    async def mount(self, socket, session):
        socket.context = {"count": 0}
        if is_connected(socket):
            # Subscribe to counter updates from any instance
            await socket.subscribe("counter")

    async def handle_event(self, event, payload, socket):
        if event == "increment":
            socket.context["count"] += 1
            # Broadcast to ALL instances via Redis
            await socket.broadcast("counter", socket.context["count"])
        elif event == "decrement":
            socket.context["count"] -= 1
            await socket.broadcast("counter", socket.context["count"])
        elif event == "reset":
            socket.context["count"] = 0
            await socket.broadcast("counter", 0)

    async def handle_info(self, event, socket):
        # Received update from another instance
        socket.context["count"] = event.payload

    async def render(self, context, meta):
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Multi-Instance Counter</title>
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                }
                .container {
                    background: white;
                    padding: 3rem;
                    border-radius: 1rem;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                    text-align: center;
                    min-width: 300px;
                }
                h1 {
                    margin: 0 0 2rem 0;
                    color: #333;
                    font-size: 2rem;
                }
                .count {
                    font-size: 5rem;
                    font-weight: bold;
                    color: #667eea;
                    margin: 2rem 0;
                }
                .buttons {
                    display: flex;
                    gap: 1rem;
                    justify-content: center;
                    margin-top: 2rem;
                }
                button {
                    padding: 1rem 2rem;
                    font-size: 1.2rem;
                    border: none;
                    border-radius: 0.5rem;
                    cursor: pointer;
                    transition: all 0.2s;
                    font-weight: 600;
                }
                button:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                }
                .increment {
                    background: #10b981;
                    color: white;
                }
                .decrement {
                    background: #ef4444;
                    color: white;
                }
                .reset {
                    background: #6b7280;
                    color: white;
                }
                .info {
                    margin-top: 2rem;
                    padding: 1rem;
                    background: #f3f4f6;
                    border-radius: 0.5rem;
                    font-size: 0.875rem;
                    color: #6b7280;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Multi-Instance Counter</h1>
                <div class="count">{{ count }}</div>
                <div class="buttons">
                    <button phx-click="increment" class="increment">+</button>
                    <button phx-click="decrement" class="decrement">-</button>
                    <button phx-click="reset" class="reset">Reset</button>
                </div>
                <div class="info">
                    🚀 Try opening this page in multiple browsers or run multiple instances on different ports.
                    All instances stay in sync via Redis pub/sub!
                </div>
            </div>
        </body>
        </html>
        """


# Create app with Redis pub/sub
# Uses REDIS_URL environment variable if set, otherwise defaults to localhost
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
app = PyView(pubsub=RedisPubSub(redis_url))

app.add_live_view("/", CounterLiveView)
