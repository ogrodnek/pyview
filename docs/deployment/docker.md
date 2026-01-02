---
title: Docker
---

# Docker

A production-ready Dockerfile using multi-stage build with [uv](https://docs.astral.sh/uv/):

```dockerfile
FROM python:3.14-alpine AS build

# Install build dependencies
RUN apk add build-base libffi-dev

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/

WORKDIR /app
COPY . .

# Install dependencies (no dev dependencies, no cache for smaller image)
RUN uv sync --no-dev --no-cache

FROM python:3.14-alpine AS runtime

WORKDIR /app

# Set up the virtual environment
ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

# Copy the application and virtual environment from build stage
COPY --from=build /app /app

# Expose the port uvicorn will run on
EXPOSE 8000

# Run the application
CMD ["uvicorn", "--host", "0.0.0.0", "myapp.app:app"]
```

**Key points:**
- **Multi-stage build** keeps the final image small by excluding build tools
- **uv** installs dependencies faster than pip
- **`--no-dev`** excludes development dependencies
- **`--host 0.0.0.0`** binds to all interfaces (required in containers)

### Adapting for Your Project

```dockerfile
# If using poetry instead of uv
RUN pip install poetry && poetry install --no-dev

# Update CMD to match your app module
CMD ["uvicorn", "--host", "0.0.0.0", "your_package.app:app"]
```

## Building and Running

```bash
docker build -t myapp .
```

Run with environment variables:

```bash
docker run -p 8000:8000 \
  -e PYVIEW_SECRET="$(openssl rand -base64 32)" \
  myapp
```

Visit `http://localhost:8000` to see your app.

## Docker Compose

For local development with Docker:

```yaml
# docker-compose.yml
services:
  web:
    build: .
    ports:
      - "8000:8000"
    environment:
      - PYVIEW_SECRET=dev-secret-change-in-production
    volumes:
      # Mount source for development (optional)
      - ./src:/app/src:ro
```

Run with:

```bash
docker compose up
```

## Health Checks

Add a health check endpoint to your app:

```python
from starlette.routing import Route
from starlette.responses import PlainTextResponse

async def health(request):
    return PlainTextResponse("ok")

# Add to your routes
app.routes.append(Route("/health", health))
```

Then in your Dockerfile:

```dockerfile
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:8000/health || exit 1
```

Or in docker-compose.yml:

```yaml
services:
  web:
    # ...
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:8000/health"]
      interval: 30s
      timeout: 3s
      retries: 3
```

## Production Tips

### Workers

```dockerfile
CMD ["uvicorn", "--host", "0.0.0.0", "--workers", "4", "myapp.app:app"]
```

LiveView state is per-process. With multiple workers, you need sticky sessions so WebSocket connections reach the same worker that handled the initial request.

### Security

- Never commit secrets to Dockerfiles
- Use environment variables or Docker secrets for `PYVIEW_SECRET`
- Run as non-root:

```dockerfile
RUN adduser -D appuser
USER appuser
```

## Next Steps

- [Fly.io](./fly-io) — Deploy your Docker container to Fly.io
