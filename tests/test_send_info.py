"""Tests for push_event delivery during handle_info"""

import json
from unittest.mock import MagicMock

from pyview.events import InfoEvent
from pyview.live_socket import ConnectedLiveViewSocket
from pyview.live_view import LiveView


class SimpleRenderedContent:
    def tree(self) -> dict:
        return {"s": ["<div>hello</div>"]}

    def text(self, socket=None) -> str:
        return "<div>hello</div>"


class PushingView(LiveView):
    """LiveView that pushes an event during handle_info."""

    async def handle_info(self, event, socket):
        await socket.push_event("tick", {"count": 1})

    async def render(self, assigns, meta):
        return SimpleRenderedContent()


class NonPushingView(LiveView):
    """LiveView that does NOT push events during handle_info."""

    async def handle_info(self, event, socket):
        pass

    async def render(self, assigns, meta):
        return SimpleRenderedContent()


def _make_socket(lv):
    sent_messages = []

    async def mock_send_text(text):
        sent_messages.append(json.loads(text))

    mock_ws = MagicMock()
    mock_ws.send_text = mock_send_text

    socket = ConnectedLiveViewSocket(
        websocket=mock_ws,
        topic="lv:test",
        liveview=lv,
        scheduler=MagicMock(),
        instrumentation=MagicMock(),
    )
    socket.context = {}
    return socket, sent_messages


class TestSendInfoPushEvents:
    async def test_send_info_includes_push_events_in_diff(self):
        lv = PushingView()
        socket, sent = _make_socket(lv)

        await socket.send_info(InfoEvent("tick"))

        assert len(sent) == 1
        # Message format: [None, None, topic, "diff", diff_payload]
        diff = sent[0][4]
        assert "e" in diff
        assert diff["e"] == [["tick", {"count": 1}]]

    async def test_send_info_clears_pending_events_after_send(self):
        """After send_info, pending_events should be empty."""
        lv = PushingView()
        socket, _ = _make_socket(lv)

        await socket.send_info(InfoEvent("tick"))

        assert socket.pending_events == []

    async def test_send_info_omits_events_key_when_none_pushed(self):
        """When handle_info does NOT call push_event, diff should not have 'e' key."""
        lv = NonPushingView()
        socket, sent = _make_socket(lv)

        await socket.send_info(InfoEvent("tick"))

        assert len(sent) == 1
        diff = sent[0][4]
        assert "e" not in diff
