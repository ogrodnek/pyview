"""Tests for InjectableRegistry."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from pyview.binding import BindContext, Params
from pyview.binding.injectables import _NOT_FOUND, InjectableRegistry
from pyview.components.base import ComponentSocket
from pyview.live_socket import ConnectedLiveViewSocket, UnconnectedSocket


class TestInjectableRegistry:
    """Test injectable parameter resolution."""

    @pytest.fixture
    def registry(self) -> InjectableRegistry:
        return InjectableRegistry()

    @pytest.fixture
    def ctx(self) -> BindContext:
        return BindContext(
            params=Params({"page": ["1"], "tags": ["a", "b"]}),
            payload={"amount": 10},
            url=MagicMock(),
            socket=MagicMock(),
            event="test-event",
        )

    # --- Name-based injection ---

    def test_inject_socket_by_name(self, registry: InjectableRegistry, ctx: BindContext):
        result = registry.resolve("socket", Any, ctx)
        assert result is ctx.socket

    def test_inject_event_by_name(self, registry: InjectableRegistry, ctx: BindContext):
        result = registry.resolve("event", Any, ctx)
        assert result == "test-event"

    def test_inject_payload_by_name(self, registry: InjectableRegistry, ctx: BindContext):
        result = registry.resolve("payload", Any, ctx)
        assert result == {"amount": 10}

    def test_inject_url_by_name(self, registry: InjectableRegistry, ctx: BindContext):
        result = registry.resolve("url", Any, ctx)
        assert result is ctx.url

    def test_missing_socket_returns_none(self, registry: InjectableRegistry):
        ctx = BindContext(
            params=Params({}),
            payload=None,
            url=None,
            socket=None,
            event=None,
        )
        result = registry.resolve("socket", Any, ctx)
        assert result is None

    # --- Params injection variants ---

    def test_inject_params_as_Params(self, registry: InjectableRegistry, ctx: BindContext):
        result = registry.resolve("params", Params, ctx)
        assert isinstance(result, Params)
        assert result.get("page") == "1"

    def test_inject_params_as_raw_dict(self, registry: InjectableRegistry, ctx: BindContext):
        result = registry.resolve("params", dict[str, list[str]], ctx)
        assert result == {"page": ["1"], "tags": ["a", "b"]}

    def test_inject_params_as_flat_dict(self, registry: InjectableRegistry, ctx: BindContext):
        result = registry.resolve("params", dict[str, Any], ctx)
        assert result == {"page": "1", "tags": ["a", "b"]}

    def test_inject_params_as_typed_dict_int(self, registry: InjectableRegistry):
        ctx = BindContext(
            params=Params({"page": ["1"], "count": ["5"]}),
            payload=None,
            url=None,
            socket=None,
            event=None,
        )
        result = registry.resolve("params", dict[str, int], ctx)
        assert result == {"page": 1, "count": 5}

    def test_inject_bare_dict(self, registry: InjectableRegistry, ctx: BindContext):
        result = registry.resolve("params", dict, ctx)
        assert result == {"page": "1", "tags": ["a", "b"]}

    # --- Extra injectables ---

    def test_extra_injectables(self, registry: InjectableRegistry, ctx: BindContext):
        ctx.extra["custom"] = "custom_value"
        result = registry.resolve("custom", Any, ctx)
        assert result == "custom_value"

    def test_unknown_param_returns_not_found(self, registry: InjectableRegistry, ctx: BindContext):
        result = registry.resolve("unknown", int, ctx)
        assert result is _NOT_FOUND

    # --- params name with non-dict type ---

    def test_params_with_str_type_returns_not_found(
        self, registry: InjectableRegistry, ctx: BindContext
    ):
        """When 'params' is typed as str, treat it as a URL param name."""
        result = registry.resolve("params", str, ctx)
        assert result is _NOT_FOUND

    def test_params_with_int_type_returns_not_found(
        self, registry: InjectableRegistry, ctx: BindContext
    ):
        """When 'params' is typed as int, treat it as a URL param name."""
        result = registry.resolve("params", int, ctx)
        assert result is _NOT_FOUND

    # --- Type-based socket injection ---

    def test_inject_component_socket_by_type(self, registry: InjectableRegistry, ctx: BindContext):
        """ComponentSocket type annotation injects socket regardless of param name."""
        result = registry.resolve("any_name", ComponentSocket, ctx)
        assert result is ctx.socket

    def test_inject_component_socket_generic_by_type(
        self, registry: InjectableRegistry, ctx: BindContext
    ):
        """ComponentSocket[T] generic type annotation injects socket."""
        result = registry.resolve("sock", ComponentSocket[dict], ctx)
        assert result is ctx.socket

    def test_inject_connected_socket_by_type(self, registry: InjectableRegistry, ctx: BindContext):
        """ConnectedLiveViewSocket type annotation injects socket."""
        result = registry.resolve("s", ConnectedLiveViewSocket, ctx)
        assert result is ctx.socket

    def test_inject_connected_socket_generic_by_type(
        self, registry: InjectableRegistry, ctx: BindContext
    ):
        """ConnectedLiveViewSocket[T] generic type annotation injects socket."""
        result = registry.resolve("x", ConnectedLiveViewSocket[dict], ctx)
        assert result is ctx.socket

    def test_inject_unconnected_socket_by_type(
        self, registry: InjectableRegistry, ctx: BindContext
    ):
        """UnconnectedSocket type annotation injects socket."""
        result = registry.resolve("whatever", UnconnectedSocket, ctx)
        assert result is ctx.socket

    def test_inject_unconnected_socket_generic_by_type(
        self, registry: InjectableRegistry, ctx: BindContext
    ):
        """UnconnectedSocket[T] generic type annotation injects socket."""
        result = registry.resolve("foo", UnconnectedSocket[dict], ctx)
        assert result is ctx.socket

    def test_non_socket_name_without_type_not_injected(
        self, registry: InjectableRegistry, ctx: BindContext
    ):
        """Non-socket parameter name without socket type is not injected."""
        result = registry.resolve("sock", Any, ctx)
        assert result is _NOT_FOUND

    # --- Assigns injection (for components) ---

    def test_inject_assigns_by_name(self, registry: InjectableRegistry):
        """assigns parameter is injected from extra context."""
        ctx = BindContext(
            params=Params({}),
            payload=None,
            url=None,
            socket=None,
            event=None,
            extra={"assigns": {"label": "test", "count": 5}},
        )
        result = registry.resolve("assigns", dict, ctx)
        assert result == {"label": "test", "count": 5}

    def test_assigns_missing_returns_not_found(self, registry: InjectableRegistry):
        """assigns returns NOT_FOUND when not in extra context."""
        ctx = BindContext(
            params=Params({}),
            payload=None,
            url=None,
            socket=None,
            event=None,
        )
        result = registry.resolve("assigns", dict, ctx)
        assert result is _NOT_FOUND
