import json
from unittest.mock import AsyncMock, MagicMock

from pyview.csrf import generate_csrf_token


def make_join_websocket(payload=None):
    """Create a mock websocket that returns a phx_join for /demo."""
    if payload is None:
        payload = {
            "url": "http://testserver/demo",
            "params": {"_csrf_token": generate_csrf_token("lv:test")},
        }
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_text = AsyncMock()
    ws.receive_text = AsyncMock(return_value=json.dumps(["1", "1", "lv:test", "phx_join", payload]))
    return ws
