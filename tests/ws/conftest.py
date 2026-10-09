import pytest

from pyview.instrumentation import NoOpInstrumentation
from pyview.live_routes import LiveViewLookup
from pyview.live_view import LiveView
from pyview.ws_handler import LiveSocketHandler

from .fake_client import FakeClient


@pytest.fixture
async def connect():
    """Return a factory that builds a FakeClient for a {path: LiveView} route table."""
    clients: list[FakeClient] = []

    def _connect(routes: dict[str, type[LiveView]]) -> FakeClient:
        lookup = LiveViewLookup()
        for path, view in routes.items():
            lookup.add(path, view)
        client = FakeClient(LiveSocketHandler(lookup, NoOpInstrumentation()))
        clients.append(client)
        return client

    try:
        yield _connect
    finally:
        for client in clients:
            await client.close()
