FROM python:3.9-alpine

# TODO don't need gcc on the final image, but need it for poetry install
RUN apk add build-base libffi-dev


ENV PYTHONUNBUFFERED 1

WORKDIR /app

RUN pip3 install poetry

COPY . .

WORKDIR /app/examples
RUN poetry install --no-root --only main

CMD [ "poetry", "run", "uvicorn", "--host",  "0.0.0.0", "examples.app:app" ]
