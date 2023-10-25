# --- Build Stage ---
FROM python:3.9-alpine AS builder

RUN apk add --no-cache build-base libffi-dev
ENV PYTHONUNBUFFERED 1
WORKDIR /app
RUN pip3 install --no-cache-dir poetry
COPY . .

WORKDIR /app/examples
RUN poetry install --no-root --only main

# --- Runtime Stage ---
FROM python:3.9-alpine

COPY --from=builder /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app


WORKDIR /app/examples
CMD [ "poetry", "run", "uvicorn", "--host",  "0.0.0.0", "examples.app:app" ]
