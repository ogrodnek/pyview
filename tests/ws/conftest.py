import uuid
from typing import Optional

import pytest

from pyview.instrumentation import NoOpInstrumentation
from pyview.live_routes import LiveViewLookup
from pyview.live_view import LiveView
from pyview.ws_handler import LiveSocketHandler

from .fake_client import FakeClient


@pytest.fixture
async def connect():
    """Return a factory that builds a FakeClient for a {path: LiveView} route table.

    Each client is its own connection with its own topic, as a browser tab would have;
    pass `topic` to name it.
    """
    clients: list[FakeClient] = []

    def _connect(routes: dict[str, type[LiveView]], topic: Optional[str] = None) -> FakeClient:
        lookup = LiveViewLookup()
        for path, view in routes.items():
            lookup.add(path, view)
        handler = LiveSocketHandler(lookup, NoOpInstrumentation())
        client = FakeClient(handler, topic or f"lv:phx-{uuid.uuid4().hex[:8]}")
        clients.append(client)
        return client

    try:
        yield _connect
    finally:
        for client in clients:
            await client.close()
