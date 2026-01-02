---
title: Deployment Overview
---

# Deployment

PyView apps are standard Starlette applications. Deploy anywhere that supports Python with HTTP and WebSocket connections.

## Platform Requirements

PyView requires **WebSocket support** for real-time updates. Without it, the initial page loads but live features won't work.

## Configuration

### Secret Key

Set `PYVIEW_SECRET` for session security and persistence:

```bash
export PYVIEW_SECRET="your-secret-key-here"
```

Generate a secure key:

```bash
openssl rand -base64 32
```

**Why this matters:**

- Without a secret, PyView generates a random key on startup
- Sessions won't persist across server restarts or multiple instances
- In production with multiple containers, all instances need the same secret

### Server

PyView apps run with any ASGI server. We recommend [uvicorn](https://www.uvicorn.org/):

```bash
uvicorn myapp.app:app --host 0.0.0.0 --port 8000
```

For production, consider:

- `--workers N` for multiple worker processes (but see scaling notes below)
- Running behind a reverse proxy (nginx, Caddy) for TLS termination

### Scaling Considerations

LiveView maintains stateful WebSocket connections. Each connection is tied to a specific server process. This means:

- **Sticky sessions required** - Load balancers must route a user's WebSocket to the same backend that served their initial HTTP request
- **In-memory state** - By default, LiveView state lives in the process. If a process crashes, connected clients reconnect and remount (state is lost)
- **PubSub** - The built-in PubSub works within a single process. For multi-process setups, you'd need an external broker (Redis, etc.)

For most applications, a single process handles many concurrent connections efficiently. Start simple and scale when needed.

## Deployment Guides

- [Docker](./docker) — Containerize your PyView application
- [Fly.io](./fly-io) — Deploy to Fly.io with automatic HTTPS
