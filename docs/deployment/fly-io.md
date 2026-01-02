---
title: Fly.io
---

# Deploying to Fly.io

[Fly.io](https://fly.io) supports WebSockets and provides automatic HTTPS—a good fit for PyView apps.

## Prerequisites

1. [Create a Fly.io account](https://fly.io/app/sign-up)
2. Install the Fly CLI:

```bash
# macOS
brew install flyctl

# Linux
curl -L https://fly.io/install.sh | sh
```

3. Log in:

```bash
fly auth login
```

## Initial Setup

From your project directory:

```bash
fly launch
```

This creates a `fly.toml` configuration file. When prompted:
- Choose a unique app name (or accept the generated one)
- Select a region close to your users
- Skip database setup unless you need it

## Configuration

Here's a complete `fly.toml` for a PyView app:

```toml
app = "your-app-name"
primary_region = "ewr"  # Change to your preferred region

[build]
  # Uses Dockerfile in the current directory

[env]
  # Non-secret environment variables
  PORT = "8000"

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = false  # Keep alive for WebSocket connections
  auto_start_machines = true
  min_machines_running = 1

  [http_service.concurrency]
    type = "connections"
    hard_limit = 100
    soft_limit = 50

[[vm]]
  size = "shared-cpu-1x"
  memory = "256mb"
```

**Key settings:**
- **`force_https = true`** — Redirects HTTP to HTTPS (recommended)
- **`auto_stop_machines = false`** — Keeps machines running for WebSocket connections
- **`internal_port = 8000`** — Matches uvicorn's default port

## Setting Secrets

```bash
fly secrets set PYVIEW_SECRET="$(openssl rand -base64 32)"
```

Secrets are encrypted and injected as environment variables. List them with:

```bash
fly secrets list
```

## Deploying

```bash
fly deploy
```

Fly builds your Docker image remotely and deploys it. Once deployed:

```bash
fly open
```

## Monitoring

View logs in real-time:

```bash
fly logs
```

Check app status:

```bash
fly status
```

SSH into a running machine for debugging:

```bash
fly ssh console
```

## Scaling

### Regions

```bash
fly regions add lax ord  # Los Angeles, Chicago
```

### Machine Size

```bash
fly scale vm shared-cpu-2x --memory 512
```

Or update `fly.toml`:

```toml
[[vm]]
  size = "shared-cpu-2x"
  memory = "512mb"
```

### Multiple Machines

```bash
fly scale count 2
```

Fly's load balancer uses sticky sessions by default, which works well with PyView's WebSocket connections.

## Custom Domain

```bash
fly certs add your-domain.com
```

Follow the DNS instructions provided. Fly handles TLS certificates automatically.

## Troubleshooting

### App won't start

Check the logs:

```bash
fly logs
```

Common issues:
- Missing `PYVIEW_SECRET` — Set it with `fly secrets set`
- Wrong port — Ensure `internal_port` matches your uvicorn port
- Build failures — Check Dockerfile syntax

### WebSocket not connecting

- Verify HTTPS is working (WebSocket requires secure connection in production)
- Check that `auto_stop_machines = false` if using aggressive auto-stop

### Slow cold starts

If your app stops and restarts frequently:

```toml
[http_service]
  auto_stop_machines = false
  min_machines_running = 1
```

## Example: PyView Demo

The [PyView examples](https://examples.pyview.rocks) run on Fly.io. See the [fly.toml in the repository](https://github.com/ogrodnek/pyview/blob/main/fly.toml) for a working configuration.
