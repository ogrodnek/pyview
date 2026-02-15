"""Tests for ws_handler using TestTransport.

These tests exercise the existing handler logic through a Transport seam,
without needing a running server or real WebSocket connection. They serve
as a safety net for future refactors (typed messages, codec, dispatch).
"""

import json
from typing import Any, Optional
from unittest.mock import patch

import pytest
from starlette.websockets import WebSocketDisconnect

from pyview.instrumentation import NoOpInstrumentation
from pyview.live_routes import LiveViewLookup
from pyview.live_view import LiveView
from pyview.meta import PyViewMeta
from pyview.session import serialize_session
from pyview.transport import Transport
from pyview.ws_handler import LiveSocketHandler

# ---------------------------------------------------------------------------
# TestTransport
# ---------------------------------------------------------------------------


class MemoryTransport:
    """In-memory transport that feeds scripted messages and records output."""

    def __init__(self):
        self._inbox: list[str | dict] = []
        self.sent: list[str] = []
        self.accepted = False
        self.closed = False

    # -- scripting helpers --

    def push_text(self, data: str):
        """Queue a raw text string (consumed by receive_text)."""
        self._inbox.append(data)

    def push_message(self, msg: dict):
        """Queue a raw Message dict (consumed by receive)."""
        self._inbox.append(msg)

    def push_phx(self, join_ref, msg_ref, topic, event, payload):
        """Queue a Phoenix-format message as a websocket.receive Message."""
        text = json.dumps([join_ref, msg_ref, topic, event, payload])
        self._inbox.append({"type": "websocket.receive", "text": text})

    def push_disconnect(self, code=1000):
        """Queue a clean disconnect."""
        self._inbox.append({"type": "websocket.disconnect", "code": code})

    # -- Transport protocol --

    async def accept(self) -> None:
        self.accepted = True

    async def receive_text(self) -> str:
        if not self._inbox:
            raise WebSocketDisconnect(1000)
        item = self._inbox.pop(0)
        if isinstance(item, str):
            return item
        raise WebSocketDisconnect(1000)

    async def receive(self) -> dict:
        if not self._inbox:
            raise WebSocketDisconnect(1000)
        item = self._inbox.pop(0)
        if isinstance(item, dict):
            return item
        return {"type": "websocket.receive", "text": item}

    async def send_text(self, data: str) -> None:
        self.sent.append(data)

    async def close(self) -> None:
        self.closed = True

    # -- assertion helpers --

    @property
    def sent_parsed(self) -> list[list]:
        """All sent messages as parsed Phoenix arrays."""
        return [json.loads(m) for m in self.sent]

    def reply_at(self, index: int) -> dict:
        """Return the full Phoenix reply envelope at a given index."""
        return self.sent_parsed[index]

    def response_at(self, index: int) -> dict:
        """Return just the response payload of the reply at a given index."""
        msg = self.sent_parsed[index]
        assert msg[3] == "phx_reply", f"Expected phx_reply, got {msg[3]}"
        return msg[4]["response"]


# ---------------------------------------------------------------------------
# Minimal RenderedContent for test LiveViews
# ---------------------------------------------------------------------------


class SimpleRenderedContent:
    """Minimal RenderedContent satisfying the protocol."""

    def __init__(self, tree_dict: dict[str, Any], html: str = ""):
        self._tree = tree_dict
        self._html = html

    def tree(self) -> dict[str, Any]:
        return dict(self._tree)  # shallow copy so diff works

    def text(self, socket=None) -> str:
        return self._html


# ---------------------------------------------------------------------------
# Test LiveViews
# ---------------------------------------------------------------------------


class CounterView(LiveView):
    """Simple counter: mount sets count=0, increment adds 1."""

    async def mount(self, socket, session):
        socket.context = {"count": 0}

    async def handle_event(self, event, payload, socket):
        if event == "increment":
            socket.context["count"] += 1

    async def handle_params(self, url, params, socket):
        pass

    async def render(self, assigns, meta):
        count = assigns.get("count", 0)
        return SimpleRenderedContent(
            {"s": ["<div>Count: ", "</div>"], "0": str(count)},
            f"<div>Count: {count}</div>",
        )


class ParamView(LiveView):
    """View that stores params in context for inspection."""

    async def mount(self, socket, session):
        socket.context = {"page": "1"}

    async def handle_params(self, url, params, socket):
        if "page" in params:
            val = params["page"]
            socket.context["page"] = val[0] if isinstance(val, list) else val

    async def render(self, assigns, meta):
        page = assigns.get("page", "1")
        return SimpleRenderedContent(
            {"s": ["<div>Page: ", "</div>"], "0": str(page)},
            f"<div>Page: {page}</div>",
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TOPIC = "lv:phx-test-id"


def _make_join_text(topic=TOPIC, url="http://localhost/count", csrf_token="valid"):
    """Build the raw text for an initial phx_join (consumed by receive_text)."""
    return json.dumps(
        [
            "1",
            "1",
            topic,
            "phx_join",
            {
                "url": url,
                "params": {"_csrf_token": csrf_token},
                "session": serialize_session({}),
            },
        ]
    )


@pytest.fixture
def routes():
    lookup = LiveViewLookup()
    lookup.add("/count", CounterView)
    lookup.add("/params", ParamView)
    return lookup


@pytest.fixture
async def handler(routes):
    instrumentation = NoOpInstrumentation()
    h = LiveSocketHandler(routes, instrumentation)
    h.start_scheduler()
    yield h
    h.scheduler.shutdown(wait=False)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestJoinFlow:
    @patch("pyview.ws_handler.validate_csrf_token", return_value=True)
    async def test_successful_join_returns_rendered(self, _csrf, handler):
        transport = MemoryTransport()
        transport.push_text(_make_join_text())
        transport.push_disconnect()

        await handler.handle(transport)

        assert transport.accepted
        assert len(transport.sent) >= 1

        reply = transport.reply_at(0)
        assert reply[3] == "phx_reply"
        assert reply[4]["status"] == "ok"
        response = reply[4]["response"]
        assert "rendered" in response
        assert "liveview_version" in response
        # count=0 should appear in the rendered tree
        assert "0" in str(response["rendered"])

    @patch("pyview.ws_handler.validate_csrf_token", return_value=False)
    async def test_invalid_csrf_closes_connection(self, _csrf, handler):
        transport = MemoryTransport()
        transport.push_text(_make_join_text())

        await handler.handle(transport)

        assert transport.closed
        assert len(transport.sent) == 0

    @patch("pyview.ws_handler.validate_csrf_token", return_value=True)
    async def test_join_increments_sessions(self, _csrf, handler):
        transport = MemoryTransport()
        transport.push_text(_make_join_text())
        transport.push_disconnect()

        initial = handler.sessions
        await handler.handle(transport)
        # Session count goes up then back down after disconnect
        assert handler.sessions == initial


class TestHeartbeat:
    @patch("pyview.ws_handler.validate_csrf_token", return_value=True)
    async def test_heartbeat_returns_ok(self, _csrf, handler):
        transport = MemoryTransport()
        transport.push_text(_make_join_text())
        transport.push_phx(None, "5", "phoenix", "heartbeat", {})
        transport.push_disconnect()

        await handler.handle(transport)

        # First sent message is the join reply, second is heartbeat reply
        hb = transport.reply_at(1)
        assert hb[3] == "phx_reply"
        assert hb[4] == {"response": {}, "status": "ok"}
        # Heartbeat reply should be on the "phoenix" topic with the correct ref
        assert hb[1] == "5"
        assert hb[2] == "phoenix"


class TestEventFlow:
    @patch("pyview.ws_handler.validate_csrf_token", return_value=True)
    async def test_click_event_returns_diff(self, _csrf, handler):
        transport = MemoryTransport()
        transport.push_text(_make_join_text())
        transport.push_phx("1", "2", TOPIC, "event", {
            "type": "click",
            "event": "increment",
            "value": {},
        })
        transport.push_disconnect()

        await handler.handle(transport)

        assert len(transport.sent) >= 2
        event_reply = transport.reply_at(1)
        assert event_reply[3] == "phx_reply"
        assert event_reply[4]["status"] == "ok"
        diff = event_reply[4]["response"]["diff"]
        # count went from 0 to 1
        assert "1" in str(diff)

    @patch("pyview.ws_handler.validate_csrf_token", return_value=True)
    async def test_multiple_events_accumulate_state(self, _csrf, handler):
        transport = MemoryTransport()
        transport.push_text(_make_join_text())

        for i in range(3):
            transport.push_phx("1", str(i + 2), TOPIC, "event", {
                "type": "click",
                "event": "increment",
                "value": {},
            })
        transport.push_disconnect()

        await handler.handle(transport)

        # 1 join reply + 3 event replies
        assert len(transport.sent) == 4

        # Last event reply should have count=3
        last_reply = transport.reply_at(3)
        diff = last_reply[4]["response"]["diff"]
        assert "3" in str(diff)

    @patch("pyview.ws_handler.validate_csrf_token", return_value=True)
    async def test_clear_flash_event(self, _csrf, handler):
        transport = MemoryTransport()
        transport.push_text(_make_join_text())
        transport.push_phx("1", "2", TOPIC, "event", {
            "type": "click",
            "event": "lv:clear-flash",
            "value": {"key": "info"},
        })
        transport.push_disconnect()

        await handler.handle(transport)

        # Should get a reply (no error)
        assert len(transport.sent) >= 2
        reply = transport.reply_at(1)
        assert reply[4]["status"] == "ok"


class TestLivePatch:
    @patch("pyview.ws_handler.validate_csrf_token", return_value=True)
    async def test_patch_returns_diff(self, _csrf, handler):
        transport = MemoryTransport()
        transport.push_text(_make_join_text())
        transport.push_phx("1", "3", TOPIC, "live_patch", {
            "url": "http://localhost/count?page=2",
        })
        transport.push_disconnect()

        await handler.handle(transport)

        assert len(transport.sent) >= 2
        patch_reply = transport.reply_at(1)
        assert patch_reply[3] == "phx_reply"
        assert patch_reply[4]["status"] == "ok"
        assert "diff" in patch_reply[4]["response"]


class TestLeave:
    @patch("pyview.ws_handler.validate_csrf_token", return_value=True)
    async def test_leave_replies_ok(self, _csrf, handler):
        transport = MemoryTransport()
        transport.push_text(_make_join_text())
        transport.push_phx("1", "4", TOPIC, "phx_leave", {})
        transport.push_disconnect()

        await handler.handle(transport)

        assert len(transport.sent) >= 2
        leave_reply = transport.reply_at(1)
        assert leave_reply[3] == "phx_reply"
        assert leave_reply[4] == {"response": {}, "status": "ok"}


class TestCidsLifecycle:
    @patch("pyview.ws_handler.validate_csrf_token", return_value=True)
    async def test_cids_will_destroy_replies_ok(self, _csrf, handler):
        transport = MemoryTransport()
        transport.push_text(_make_join_text())
        transport.push_phx("1", "5", TOPIC, "cids_will_destroy", {"cids": [1, 2]})
        transport.push_disconnect()

        await handler.handle(transport)

        reply = transport.reply_at(1)
        assert reply[4] == {"response": {}, "status": "ok"}

    @patch("pyview.ws_handler.validate_csrf_token", return_value=True)
    async def test_cids_destroyed_returns_cids(self, _csrf, handler):
        transport = MemoryTransport()
        transport.push_text(_make_join_text())
        transport.push_phx("1", "6", TOPIC, "cids_destroyed", {"cids": [1, 2]})
        transport.push_disconnect()

        await handler.handle(transport)

        reply = transport.reply_at(1)
        assert reply[4]["status"] == "ok"
        assert reply[4]["response"]["cids"] == [1, 2]


class TestNavigationJoin:
    @patch("pyview.ws_handler.validate_csrf_token", return_value=True)
    async def test_navigation_join_renders_new_view(self, _csrf, handler):
        transport = MemoryTransport()

        # Initial join to /count
        transport.push_text(_make_join_text())

        # Navigate to /params via phx_join with redirect
        new_topic = "lv:phx-nav-id"
        transport.push_phx("2", "10", new_topic, "phx_join", {
            "redirect": "http://localhost/params",
            "params": {"_csrf_token": "valid"},
            "session": serialize_session({}),
        })
        transport.push_disconnect()

        await handler.handle(transport)

        assert len(transport.sent) >= 2

        # Second reply should be a rendered response for the new view
        nav_reply = transport.reply_at(1)
        assert nav_reply[3] == "phx_reply"
        assert nav_reply[4]["status"] == "ok"
        assert "rendered" in nav_reply[4]["response"]


class TestDisconnectCleanup:
    @patch("pyview.ws_handler.validate_csrf_token", return_value=True)
    async def test_disconnect_decrements_session_count(self, _csrf, handler):
        transport = MemoryTransport()
        transport.push_text(_make_join_text())
        transport.push_disconnect()

        sessions_before = handler.sessions
        await handler.handle(transport)
        assert handler.sessions == sessions_before

    @patch("pyview.ws_handler.validate_csrf_token", return_value=True)
    async def test_disconnect_without_join(self, _csrf, handler):
        """Disconnect before join completes should not raise."""
        transport = MemoryTransport()
        # No messages -- receive_text will raise WebSocketDisconnect

        await handler.handle(transport)

        assert transport.accepted
        # Should not crash


class TestMemoryTransportProtocol:
    """Verify MemoryTransport satisfies the Transport protocol."""

    def test_is_transport(self):
        t = MemoryTransport()
        assert isinstance(t, Transport)

    async def test_round_trip(self):
        t = MemoryTransport()
        t.push_text("hello")
        result = await t.receive_text()
        assert result == "hello"

    async def test_message_round_trip(self):
        t = MemoryTransport()
        msg = {"type": "websocket.receive", "text": "data"}
        t.push_message(msg)
        result = await t.receive()
        assert result == msg

    async def test_empty_inbox_disconnects(self):
        t = MemoryTransport()
        with pytest.raises(WebSocketDisconnect):
            await t.receive_text()

    async def test_sent_messages_recorded(self):
        t = MemoryTransport()
        await t.send_text('{"test": true}')
        assert len(t.sent) == 1
        assert t.sent[0] == '{"test": true}'
