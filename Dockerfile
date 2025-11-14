FROM python:3.14-alpine AS build

RUN apk add build-base libffi-dev zlib-dev jpeg-dev
RUN pip install poetry
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    PYTHONUNBUFFERED=1


WORKDIR /app
COPY . .

WORKDIR /app/examples
RUN poetry install --no-root --only main --no-cache

FROM python:3.14-alpine AS runtime

RUN apk add --no-cache zlib jpeg

ENV VIRTUAL_ENV=/app/examples/.venv \
    PATH="/app/examples/.venv/bin:$PATH"

COPY --from=build /app /app

WORKDIR /app/examples

CMD [ "uvicorn", "--host",  "0.0.0.0", "examples.app:app" ]
