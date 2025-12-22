"""Backward compatibility tests for existing handler signatures.

These tests ensure that existing handler patterns continue to work unchanged
after integrating the binder.
"""

from unittest.mock import MagicMock
from urllib.parse import urlparse

import pytest

from pyview.binding import BindContext, Binder, Params
from pyview.live_socket import LiveViewSocket


class TestLegacyHandleParams:
    """Ensure existing handle_params signatures work."""

    @pytest.fixture
    def binder(self) -> Binder:
        return Binder()

    @pytest.fixture
    def ctx(self) -> BindContext:
        return BindContext(
            params=Params({"c": ["5"], "tag": ["a", "b"]}),
            payload=None,
            url=urlparse("/path?c=5&tag=a&tag=b"),
            socket=MagicMock(),
            event=None,
        )

    def test_legacy_url_params_socket(self, binder: Binder, ctx: BindContext):
        """Original (url, params, socket) signature must work."""

        async def handle_params(url, params, socket):
            pass

        result = binder.bind(handle_params, ctx)
        assert result.success
        assert result.bound_args["url"] is ctx.url
        assert isinstance(result.bound_args["params"], Params)
        assert result.bound_args["socket"] is ctx.socket

    def test_legacy_self_url_params_socket(self, binder: Binder, ctx: BindContext):
        """Method signature (self, url, params, socket) must work."""

        class MyView:
            async def handle_params(self, url, params, socket):
                pass

        view = MyView()
        result = binder.bind(view.handle_params, ctx)
        assert result.success
        assert "self" not in result.bound_args
        assert result.bound_args["url"] is ctx.url
        assert isinstance(result.bound_args["params"], Params)
        assert result.bound_args["socket"] is ctx.socket

    def test_legacy_params_dict_annotation(self, binder: Binder, ctx: BindContext):
        """Explicit dict[str, list[str]] annotation returns raw dict."""

        async def handle_params(url, params: dict[str, list[str]], socket):
            pass

        result = binder.bind(handle_params, ctx)
        assert result.success
        assert result.bound_args["params"] == {"c": ["5"], "tag": ["a", "b"]}

    def test_params_wrapper_supports_list_access(self, binder: Binder, ctx: BindContext):
        """Params wrapper allows params["c"][0] via getlist."""

        async def handle_params(params: Params, socket):
            pass

        result = binder.bind(handle_params, ctx)
        assert result.success
        params = result.bound_args["params"]
        # User can still do legacy patterns:
        assert params.get("c") == "5"
        assert params.getlist("c") == ["5"]
        assert params.getlist("c")[0] == "5"
        assert params.getlist("tag") == ["a", "b"]


class TestLegacyHandleEvent:
    """Ensure existing handle_event signatures work."""

    @pytest.fixture
    def binder(self) -> Binder:
        return Binder()

    @pytest.fixture
    def ctx(self) -> BindContext:
        return BindContext(
            params=Params({}),
            payload={"value": {"field": ["data"]}, "type": "click"},
            url=None,
            socket=MagicMock(),
            event="click",
        )

    def test_legacy_event_payload_socket(self, binder: Binder, ctx: BindContext):
        """Original (event, payload, socket) signature must work."""

        async def handle_event(event, payload, socket):
            pass

        result = binder.bind(handle_event, ctx)
        assert result.success
        assert result.bound_args["event"] == "click"
        assert result.bound_args["payload"] == {"value": {"field": ["data"]}, "type": "click"}
        assert result.bound_args["socket"] is ctx.socket

    def test_legacy_self_event_payload_socket(self, binder: Binder, ctx: BindContext):
        """@event decorated method with (self, event, payload, socket)."""

        class MyView:
            async def on_click(self, event, payload, socket):
                pass

        view = MyView()
        result = binder.bind(view.on_click, ctx)
        assert result.success
        assert "self" not in result.bound_args
        assert result.bound_args["event"] == "click"
        assert result.bound_args["payload"]["type"] == "click"

    def test_payload_dict_access(self, binder: Binder, ctx: BindContext):
        """Payload dict allows direct key access."""

        async def handle_event(event, payload, socket):
            pass

        result = binder.bind(handle_event, ctx)
        assert result.success
        payload = result.bound_args["payload"]
        # User can still do legacy patterns:
        assert payload["type"] == "click"
        assert payload["value"]["field"] == ["data"]


class TestMixedLegacyAndTyped:
    """Test mixing legacy and typed parameters."""

    @pytest.fixture
    def binder(self) -> Binder:
        return Binder()

    def test_typed_params_with_legacy_socket(self):
        """Can mix typed params with untyped socket."""
        ctx = BindContext(
            params=Params({"page": ["5"]}),
            payload=None,
            url=MagicMock(),
            socket=MagicMock(),
            event=None,
        )
        binder = Binder()

        async def handle_params(url, page: int, socket):
            pass

        result = binder.bind(handle_params, ctx)
        assert result.success
        assert result.bound_args["url"] is ctx.url
        assert result.bound_args["page"] == 5
        assert result.bound_args["socket"] is ctx.socket

    def test_typed_socket_with_legacy_params(self):
        """Can use typed socket with legacy params."""
        ctx = BindContext(
            params=Params({"c": ["5"]}),
            payload=None,
            url=MagicMock(),
            socket=MagicMock(),
            event=None,
        )
        binder = Binder()

        async def handle_params(url, params, socket: LiveViewSocket):
            pass

        result = binder.bind(handle_params, ctx)
        assert result.success
        assert result.bound_args["url"] is ctx.url
        assert isinstance(result.bound_args["params"], Params)
        assert result.bound_args["socket"] is ctx.socket


class TestRealWorldPatterns:
    """Test patterns from actual pyview examples."""

    @pytest.fixture
    def binder(self) -> Binder:
        return Binder()

    def test_count_example_pattern(self):
        """Pattern from count.py example."""
        ctx = BindContext(
            params=Params({"c": ["5"]}),
            payload=None,
            url=MagicMock(),
            socket=MagicMock(),
            event=None,
        )
        binder = Binder()

        # Legacy pattern
        async def handle_params_legacy(url, params, socket):
            if "c" in params:
                count = int(params.get("c"))
                return count
            return 0

        result = binder.bind(handle_params_legacy, ctx)
        assert result.success
        params = result.bound_args["params"]
        assert params.get("c") == "5"

        # New typed pattern
        async def handle_params_typed(socket, c: int = 0):
            return c

        result = binder.bind(handle_params_typed, ctx)
        assert result.success
        assert result.bound_args["c"] == 5

    def test_fifa_pagination_pattern(self):
        """Pattern from fifa.py example with multiple params."""
        ctx = BindContext(
            params=Params({"page": ["2"], "perPage": ["25"]}),
            payload=None,
            url=MagicMock(),
            socket=MagicMock(),
            event=None,
        )
        binder = Binder()

        # New typed pattern
        async def handle_params(socket, page: int = 1, perPage: int = 10):
            pass

        result = binder.bind(handle_params, ctx)
        assert result.success
        assert result.bound_args["page"] == 2
        assert result.bound_args["perPage"] == 25

    def test_kanban_event_pattern(self):
        """Pattern from kanban.py example with payload fields."""
        ctx = BindContext(
            params=Params({}),
            payload={"taskId": "task-1", "from": "todo", "to": "done", "order": 0},
            url=None,
            socket=MagicMock(),
            event="task-moved",
        )
        binder = Binder()

        # Legacy pattern
        async def handle_event_legacy(event, payload, socket):
            task_id = payload["taskId"]
            return task_id

        result = binder.bind(handle_event_legacy, ctx)
        assert result.success
        assert result.bound_args["payload"]["taskId"] == "task-1"

        # New typed pattern - accessing payload fields directly
        async def handle_event_typed(socket, taskId: str, order: int):
            pass

        result = binder.bind(handle_event_typed, ctx)
        assert result.success
        assert result.bound_args["taskId"] == "task-1"
        assert result.bound_args["order"] == 0
