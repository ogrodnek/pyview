"""Tests for WebSocket handler URL/redirect payload handling.

Verifies that phx_join works with both 'url' and 'redirect' payload fields,
matching the Phoenix LiveView client behavior where the JS client sends either
'url' or 'redirect' but never both.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pyview.csrf import generate_csrf_token
from pyview.instrumentation import NoOpInstrumentation
from pyview.live_routes import LiveViewLookup
from pyview.live_socket import ConnectedLiveViewSocket
from pyview.live_view import LiveView
from pyview.ws_handler import LiveSocketHandler


class EmptyRendered:
    def tree(self):
        return {}

    def text(self, socket=None):
        return ""


class MountingLiveView(LiveView[dict]):
    async def mount(self, socket, session):
        socket.context = {}

    async def render(self, assigns, meta):
        return EmptyRendered()


def make_handler():
    routes = LiveViewLookup()
    routes.add("/demo", MountingLiveView)
    handler = LiveSocketHandler(routes, NoOpInstrumentation())
    return handler


def make_websocket(payload):
    websocket = MagicMock()
    websocket.accept = AsyncMock()
    websocket.send_text = AsyncMock()
    websocket.receive_text = AsyncMock(
        return_value=json.dumps(
            ["1", "1", "lv:test", "phx_join", payload]
        )
    )
    return websocket


def suppress_close(monkeypatch):
    """Suppress socket.close() to avoid cleanup errors in tests."""
    async def fake_close(self):
        pass
    monkeypatch.setattr(ConnectedLiveViewSocket, "close", fake_close)


async def test_phx_join_with_url_payload(monkeypatch):
    """Standard phx_join with 'url' field works (regression guard)."""
    handler = make_handler()
    payload = {
        "url": "http://testserver/demo",
        "params": {"_csrf_token": generate_csrf_token("lv:test")},
    }
    websocket = make_websocket(payload)
    suppress_close(monkeypatch)

    async def stop_after_join(topic, socket):
        pass  # Don't enter the connected loop

    monkeypatch.setattr(handler, "handle_connected", stop_after_join)
    await handler.handle(websocket)

    # Should have sent a phx_reply with rendered content
    websocket.send_text.assert_called_once()
    resp = json.loads(websocket.send_text.call_args[0][0])
    assert resp[3] == "phx_reply"
    assert resp[4]["status"] == "ok"
    assert "rendered" in resp[4]["response"]


async def test_phx_join_with_redirect_payload(monkeypatch):
    """phx_join with 'redirect' field instead of 'url' works.

    The Phoenix LiveView JS client sends 'redirect' (not 'url') when
    this.redirect is true (e.g. during live_redirect navigation).
    """
    handler = make_handler()
    payload = {
        "redirect": "http://testserver/demo",
        "params": {"_csrf_token": generate_csrf_token("lv:test")},
    }
    websocket = make_websocket(payload)
    suppress_close(monkeypatch)

    async def stop_after_join(topic, socket):
        pass

    monkeypatch.setattr(handler, "handle_connected", stop_after_join)
    await handler.handle(websocket)

    # Should have sent a phx_reply with rendered content
    websocket.send_text.assert_called_once()
    resp = json.loads(websocket.send_text.call_args[0][0])
    assert resp[3] == "phx_reply"
    assert resp[4]["status"] == "ok"
    assert "rendered" in resp[4]["response"]


async def test_connected_loop_error_sends_error_reply_and_continues(monkeypatch):
    """An error in one message shouldn't kill the WebSocket connection.

    The handler should send an error reply and continue processing the next message.
    """
    from starlette.websockets import WebSocketDisconnect

    handler = make_handler()
    suppress_close(monkeypatch)

    dispatch_count = 0
    original_dispatch = handler._dispatch_event

    async def counting_dispatch(*args, **kwargs):
        nonlocal dispatch_count
        dispatch_count += 1
        if dispatch_count == 1:
            raise ValueError("simulated error")
        # Second call: just return normally (heartbeat will be handled)
        return await original_dispatch(*args, **kwargs)

    handler._dispatch_event = counting_dispatch

    # Three messages: bad one, heartbeat, then disconnect
    messages = [
        {"text": json.dumps(["1", "2", "lv:test", "event", {"bad": "payload"}])},
        {"text": json.dumps([None, "3", "phoenix", "heartbeat", {}])},
        {"type": "websocket.disconnect", "code": 1000},
    ]

    mock_socket = MagicMock(spec=ConnectedLiveViewSocket)
    mock_socket.websocket = MagicMock()
    mock_socket.websocket.receive = AsyncMock(side_effect=messages)
    mock_socket.websocket.send_text = AsyncMock()

    with pytest.raises(WebSocketDisconnect):
        await handler._handle_connected_loop("lv:test", mock_socket)

    # Should have dispatched twice (error on first, success on second)
    assert dispatch_count == 2

    # Verify an error reply was sent for the first message
    sent_messages = [
        json.loads(call[0][0])
        for call in mock_socket.websocket.send_text.call_args_list
    ]
    error_replies = [m for m in sent_messages if m[4].get("status") == "error"]
    assert len(error_replies) == 1
    assert error_replies[0][3] == "phx_reply"

    # Verify the heartbeat was also handled (ok reply)
    ok_replies = [m for m in sent_messages if m[4].get("status") == "ok"]
    assert len(ok_replies) == 1
