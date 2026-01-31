"""Integration tests for binding helper functions.

These tests verify that call_handle_event and call_handle_params actually
use the binder, not just that the binder works in isolation.

The key pattern: pass string values and verify the handler receives typed values.
If type conversion happened, the binder was used.
"""

from dataclasses import dataclass
from typing import Optional
from unittest.mock import MagicMock
from urllib.parse import urlparse

import pytest

from pyview.binding.helpers import call_handle_event, call_handle_params
from pyview.live_routes import LiveViewLookup
from pyview.live_socket import ConnectedLiveViewSocket
from pyview.live_view import LiveView


class TestCallHandleEvent:
    """Integration tests for call_handle_event."""

    @pytest.mark.asyncio
    async def test_binds_typed_params_from_payload(self):
        """Verify typed params are bound from payload with conversion."""

        class MyView(LiveView):
            async def handle_event(self, socket, count: int):
                self.received_count = count
                self.received_socket = socket

        lv = MyView()
        socket = MagicMock()

        # Pass string "5" - if binder runs, it converts to int 5
        await call_handle_event(lv, "increment", {"count": "5"}, socket)

        assert lv.received_count == 5  # int, not "5"
        assert lv.received_socket is socket

    @pytest.mark.asyncio
    async def test_legacy_event_payload_socket_signature(self):
        """Verify legacy (event, payload, socket) signature still works."""

        class MyView(LiveView):
            async def handle_event(self, event, payload, socket):
                self.received = (event, payload, socket)

        lv = MyView()
        socket = MagicMock()

        await call_handle_event(lv, "click", {"x": 10, "y": 20}, socket)

        assert lv.received[0] == "click"
        assert lv.received[1] == {"x": 10, "y": 20}
        assert lv.received[2] is socket

    @pytest.mark.asyncio
    async def test_injects_event_name(self):
        """Verify event name is injectable."""

        class MyView(LiveView):
            async def handle_event(self, event: str, socket):
                self.received_event = event

        lv = MyView()
        await call_handle_event(lv, "my-event", {}, MagicMock())

        assert lv.received_event == "my-event"

    @pytest.mark.asyncio
    async def test_multiple_typed_params(self):
        """Verify multiple typed params from payload."""

        class MyView(LiveView):
            async def handle_event(self, socket, x: int, y: int, label: str):
                self.received = (x, y, label)

        lv = MyView()
        await call_handle_event(lv, "move", {"x": "10", "y": "20", "label": "point"}, MagicMock())

        assert lv.received == (10, 20, "point")

    @pytest.mark.asyncio
    async def test_optional_params_with_default(self):
        """Verify optional params use defaults when missing."""

        class MyView(LiveView):
            async def handle_event(self, socket, count: int = 1):
                self.received_count = count

        lv = MyView()
        await call_handle_event(lv, "inc", {}, MagicMock())

        assert lv.received_count == 1  # default value

    @pytest.mark.asyncio
    async def test_optional_none_when_missing(self):
        """Verify Optional params get None when missing."""

        class MyView(LiveView):
            async def handle_event(self, socket, tag: Optional[str] = None):
                self.received_tag = tag

        lv = MyView()
        await call_handle_event(lv, "filter", {}, MagicMock())

        assert lv.received_tag is None

    @pytest.mark.asyncio
    async def test_dataclass_from_payload(self):
        """Verify dataclass binding from payload fields."""

        @dataclass
        class MoveEvent:
            x: int
            y: int

        class MyView(LiveView):
            async def handle_event(self, socket, move: MoveEvent):
                self.received_move = move

        lv = MyView()
        await call_handle_event(lv, "drag", {"x": "100", "y": "200"}, MagicMock())

        assert lv.received_move.x == 100
        assert lv.received_move.y == 200


class TestCallHandleParams:
    """Integration tests for call_handle_params."""

    @pytest.mark.asyncio
    async def test_binds_typed_params_from_query(self):
        """Verify typed params are bound from query params."""

        class MyView(LiveView):
            async def handle_params(self, socket, page: int = 1):
                self.received_page = page

        lv = MyView()
        socket = MagicMock()
        url = urlparse("/items?page=5")

        await call_handle_params(lv, url, {"page": ["5"]}, socket)

        assert lv.received_page == 5  # int, not "5"

    @pytest.mark.asyncio
    async def test_legacy_url_params_socket_signature(self):
        """Verify legacy (url, params, socket) signature still works."""

        class MyView(LiveView):
            async def handle_params(self, url, params, socket):
                self.received = (url, params, socket)

        lv = MyView()
        socket = MagicMock()
        url = urlparse("/items?page=1")

        await call_handle_params(lv, url, {"page": ["1"]}, socket)

        assert lv.received[0] is url
        # params is wrapped in Params object for legacy, check it has the data
        assert lv.received[2] is socket

    @pytest.mark.asyncio
    async def test_injects_url(self):
        """Verify URL is injectable."""

        class MyView(LiveView):
            async def handle_params(self, url, socket):
                self.received_url = url

        lv = MyView()
        url = urlparse("/items?page=1")

        await call_handle_params(lv, url, {"page": ["1"]}, MagicMock())

        assert lv.received_url is url

    @pytest.mark.asyncio
    async def test_multiple_typed_params(self):
        """Verify multiple typed params from query."""

        class MyView(LiveView):
            async def handle_params(self, socket, page: int = 1, per_page: int = 10):
                self.received = (page, per_page)

        lv = MyView()
        await call_handle_params(
            lv, urlparse("/items"), {"page": ["2"], "per_page": ["25"]}, MagicMock()
        )

        assert lv.received == (2, 25)

    @pytest.mark.asyncio
    async def test_default_when_param_missing(self):
        """Verify defaults are used when params are missing."""

        class MyView(LiveView):
            async def handle_params(self, socket, page: int = 1):
                self.received_page = page

        lv = MyView()
        await call_handle_params(lv, urlparse("/items"), {}, MagicMock())

        assert lv.received_page == 1

    @pytest.mark.asyncio
    async def test_dataclass_from_params(self):
        """Verify dataclass binding from query params."""

        @dataclass
        class PagingParams:
            page: int = 1
            per_page: int = 10

        class MyView(LiveView):
            async def handle_params(self, socket, paging: PagingParams):
                self.received_paging = paging

        lv = MyView()
        await call_handle_params(
            lv, urlparse("/items"), {"page": ["3"], "per_page": ["50"]}, MagicMock()
        )

        assert lv.received_paging.page == 3
        assert lv.received_paging.per_page == 50

    @pytest.mark.asyncio
    async def test_list_params(self):
        """Verify list params are bound correctly."""

        class MyView(LiveView):
            async def handle_params(self, socket, tags: list[str]):
                self.received_tags = tags

        lv = MyView()
        await call_handle_params(
            lv, urlparse("/items"), {"tags": ["python", "rust", "go"]}, MagicMock()
        )

        assert lv.received_tags == ["python", "rust", "go"]


class TestBindingErrorHandling:
    """Tests for error handling when binding fails."""

    @pytest.mark.asyncio
    async def test_call_handle_event_raises_on_missing_required_param(self):
        """Verify ValueError is raised when required param is missing."""

        class MyView(LiveView):
            async def handle_event(self, socket, count: int):
                pass  # Should never be called

        lv = MyView()

        with pytest.raises(ValueError) as exc_info:
            await call_handle_event(lv, "inc", {}, MagicMock())  # missing 'count'

        assert "Event binding failed" in str(exc_info.value)
        assert "count" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_call_handle_params_raises_on_missing_required_param(self):
        """Verify ValueError is raised when required param is missing."""

        class MyView(LiveView):
            async def handle_params(self, socket, page: int):
                pass  # Should never be called

        lv = MyView()

        with pytest.raises(ValueError) as exc_info:
            await call_handle_params(lv, urlparse("/items"), {}, MagicMock())  # missing 'page'

        assert "Parameter binding failed" in str(exc_info.value)
        assert "page" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_call_handle_event_raises_on_conversion_error(self):
        """Verify ValueError is raised when type conversion fails."""

        class MyView(LiveView):
            async def handle_event(self, socket, count: int):
                pass

        lv = MyView()

        with pytest.raises(ValueError) as exc_info:
            await call_handle_event(lv, "inc", {"count": "not-a-number"}, MagicMock())

        assert "Event binding failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_call_handle_params_raises_on_conversion_error(self):
        """Verify ValueError is raised when type conversion fails."""

        class MyView(LiveView):
            async def handle_params(self, socket, page: int):
                pass

        lv = MyView()

        with pytest.raises(ValueError) as exc_info:
            await call_handle_params(lv, urlparse("/items"), {"page": ["invalid"]}, MagicMock())

        assert "Parameter binding failed" in str(exc_info.value)


class TestPushPatchPathParams:
    """Tests for push_patch extracting and merging path params."""

    @pytest.mark.asyncio
    async def test_push_patch_merges_path_params(self):
        """Verify push_patch extracts and merges path params with query params."""

        class MyView(LiveView):
            async def handle_params(self, socket, item_id: str, page: int = 1):
                self.received_item_id = item_id
                self.received_page = page

        # Set up routes with a path parameter
        routes = LiveViewLookup()
        lv = MyView()
        routes.add("/items/{item_id}", MyView)

        # Create socket with routes
        mock_websocket = MagicMock()
        mock_websocket.send_text = MagicMock(return_value=None)

        # Make send_text a coroutine
        async def mock_send_text(text):
            pass

        mock_websocket.send_text = mock_send_text

        socket = ConnectedLiveViewSocket(
            websocket=mock_websocket,
            topic="lv:test",
            liveview=lv,
            scheduler=MagicMock(),
            instrumentation=MagicMock(),
            routes=routes,
        )

        # Call push_patch - should merge path param {item_id} with query param {page}
        await socket.push_patch("/items/123", {"page": 2})

        assert lv.received_item_id == "123"  # path param extracted
        assert lv.received_page == 2  # query param passed

    @pytest.mark.asyncio
    async def test_push_patch_path_params_only(self):
        """Verify push_patch works with only path params (no query params)."""

        class MyView(LiveView):
            async def handle_params(self, socket, job_id: str):
                self.received_job_id = job_id

        routes = LiveViewLookup()
        lv = MyView()
        routes.add("/analysis/{job_id}/summary", MyView)

        mock_websocket = MagicMock()

        async def mock_send_text(text):
            pass

        mock_websocket.send_text = mock_send_text

        socket = ConnectedLiveViewSocket(
            websocket=mock_websocket,
            topic="lv:test",
            liveview=lv,
            scheduler=MagicMock(),
            instrumentation=MagicMock(),
            routes=routes,
        )

        # Call push_patch with no explicit query params
        await socket.push_patch("/analysis/456/summary")

        assert lv.received_job_id == "456"  # path param extracted

    @pytest.mark.asyncio
    async def test_push_patch_without_routes(self):
        """Verify push_patch works when routes is None (backwards compat)."""

        class MyView(LiveView):
            async def handle_params(self, socket, page: int = 1):
                self.received_page = page

        lv = MyView()

        mock_websocket = MagicMock()

        async def mock_send_text(text):
            pass

        mock_websocket.send_text = mock_send_text

        # Create socket without routes (backwards compat)
        socket = ConnectedLiveViewSocket(
            websocket=mock_websocket,
            topic="lv:test",
            liveview=lv,
            scheduler=MagicMock(),
            instrumentation=MagicMock(),
            routes=None,
        )

        # Should still work, just without path params
        await socket.push_patch("/items", {"page": 3})

        assert lv.received_page == 3
