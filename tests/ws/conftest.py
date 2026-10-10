import pytest

from pyview.instrumentation import NoOpInstrumentation
from pyview.live_routes import LiveViewLookup
from pyview.live_view import LiveView
from pyview.ws_handler import LiveSocketHandler

from .fake_client import FakeClient


@pytest.fixture
async def connect():
    """Return a factory that builds a FakeClient for a {path: LiveView} route table.

    Each client is its own connection; give clients that run side by side distinct topics,
    as two browser tabs would have.
    """
    clients: list[FakeClient] = []

    def _connect(routes: dict[str, type[LiveView]], topic: str = "lv:phx-test") -> FakeClient:
        lookup = LiveViewLookup()
        for path, view in routes.items():
            lookup.add(path, view)
        client = FakeClient(LiveSocketHandler(lookup, NoOpInstrumentation()), topic)
        clients.append(client)
        return client

    try:
        yield _connect
    finally:
        for client in clients:
            await client.close()
