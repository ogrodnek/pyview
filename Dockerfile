FROM python:3.14-alpine AS build

RUN apk add build-base libffi-dev zlib-dev jpeg-dev
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY . .

WORKDIR /app/examples
RUN uv sync --no-dev --no-cache

FROM python:3.14-alpine AS runtime

RUN apk add --no-cache zlib jpeg

ENV VIRTUAL_ENV=/app/examples/.venv \
    PATH="/app/examples/.venv/bin:$PATH"

COPY --from=build /app /app

WORKDIR /app/examples

CMD [ "uvicorn", "--host",  "0.0.0.0", "examples.app:app" ]
