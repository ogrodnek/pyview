"""Tests for the pyview_debug package."""

import weakref
from unittest.mock import MagicMock

from pyview.connection_tracker import ConnectionTracker
from pyview.live_view import LiveView
from pyview_debug.registry import (
    ConnectionInfo,
    ConnectionRegistry,
    deep_getsizeof,
    inspect_context,
)
from pyview_debug.tracker import ChainedTracker, DebugTracker


class FakeView(LiveView):
    pass


class AnotherView(LiveView):
    pass


def _make_mock_socket():
    sock = MagicMock()
    sock.context = {"count": 42, "items": [1, 2, 3]}
    sock.components.component_count = 0
    # weakref requires the actual class to support it; MagicMock does
    return sock


# --- ConnectionRegistry ---


class TestConnectionRegistry:
    def test_register_and_get(self):
        registry = ConnectionRegistry()
        sock = _make_mock_socket()
        registry.register("lv:phx-1", sock, FakeView, "/test")

        info = registry.get("lv:phx-1")
        assert info is not None
        assert info.topic == "lv:phx-1"
        assert info.view_class is FakeView
        assert info.view_name == "FakeView"
        assert info.route == "/test"
        assert info.event_count == 0

    def test_unregister(self):
        registry = ConnectionRegistry()
        sock = _make_mock_socket()
        registry.register("lv:phx-1", sock, FakeView, "/test")
        registry.unregister("lv:phx-1")
        assert registry.get("lv:phx-1") is None
        assert registry.active_count == 0

    def test_unregister_missing_is_noop(self):
        registry = ConnectionRegistry()
        registry.unregister("nonexistent")  # should not raise

    def test_record_event(self):
        registry = ConnectionRegistry()
        sock = _make_mock_socket()
        registry.register("lv:phx-1", sock, FakeView, "/test")

        registry.record_event("lv:phx-1", "increment", 0.005)
        registry.record_event("lv:phx-1", "decrement", 0.003)

        info = registry.get("lv:phx-1")
        assert info.event_count == 2
        assert info.last_action == "decrement"
        assert abs(info.total_event_duration - 0.008) < 1e-9

    def test_record_event_missing_topic(self):
        registry = ConnectionRegistry()
        registry.record_event("nonexistent", "click", 0.01)  # should not raise

    def test_get_all(self):
        registry = ConnectionRegistry()
        registry.register("lv:1", _make_mock_socket(), FakeView, "/a")
        registry.register("lv:2", _make_mock_socket(), AnotherView, "/b")

        all_conns = registry.get_all()
        assert len(all_conns) == 2

    def test_get_all_with_exclusion(self):
        registry = ConnectionRegistry()
        registry.register("lv:1", _make_mock_socket(), FakeView, "/a")
        registry.register("lv:2", _make_mock_socket(), AnotherView, "/b")

        filtered = registry.get_all(exclude_view_classes={FakeView})
        assert len(filtered) == 1
        assert filtered[0].view_class is AnotherView

    def test_active_count(self):
        registry = ConnectionRegistry()
        assert registry.active_count == 0
        registry.register("lv:1", _make_mock_socket(), FakeView, "/a")
        assert registry.active_count == 1
        registry.register("lv:2", _make_mock_socket(), FakeView, "/b")
        assert registry.active_count == 2
        registry.unregister("lv:1")
        assert registry.active_count == 1

    def test_socket_weakref(self):
        registry = ConnectionRegistry()

        # Use a simple object that supports weakref (MagicMock has extra refs)
        class FakeSocket:
            context = {"count": 0}

        sock = FakeSocket()
        registry.register("lv:1", sock, FakeView, "/a")

        info = registry.get("lv:1")
        assert info.socket is sock

        # After deleting the socket, weakref should return None
        del sock
        assert info.socket is None


# --- DebugTracker ---


class TestDebugTracker:
    def test_satisfies_protocol(self):
        tracker = DebugTracker(ConnectionRegistry())
        assert isinstance(tracker, ConnectionTracker)

    def test_on_connect_registers(self):
        registry = ConnectionRegistry()
        tracker = DebugTracker(registry)
        sock = _make_mock_socket()

        tracker.on_connect("lv:1", sock, FakeView, "/test", {"user_id": "123"})

        info = registry.get("lv:1")
        assert info is not None
        assert info.view_name == "FakeView"
        assert info.session_metadata == {"user_id": "123"}

    def test_on_disconnect_unregisters(self):
        registry = ConnectionRegistry()
        tracker = DebugTracker(registry)
        sock = _make_mock_socket()

        tracker.on_connect("lv:1", sock, FakeView, "/test", {})
        tracker.on_disconnect("lv:1")
        assert registry.get("lv:1") is None

    def test_on_event_records(self):
        registry = ConnectionRegistry()
        tracker = DebugTracker(registry)
        sock = _make_mock_socket()

        tracker.on_connect("lv:1", sock, FakeView, "/test", {})
        tracker.on_event("lv:1", "click", 0.01)

        info = registry.get("lv:1")
        assert info.event_count == 1
        assert info.last_action == "click"

    def test_session_metadata_filters_sensitive(self):
        registry = ConnectionRegistry()
        tracker = DebugTracker(registry)
        sock = _make_mock_socket()

        tracker.on_connect(
            "lv:1",
            sock,
            FakeView,
            "/test",
            {"user_id": "123", "password": "secret", "api_key": "abc"},
        )

        info = registry.get("lv:1")
        assert info.session_metadata == {"user_id": "123"}


# --- ChainedTracker ---


class TestChainedTracker:
    def test_chains_connect(self):
        r1 = ConnectionRegistry()
        r2 = ConnectionRegistry()
        chained = ChainedTracker(DebugTracker(r1), DebugTracker(r2))
        sock = _make_mock_socket()

        chained.on_connect("lv:1", sock, FakeView, "/test", {})
        assert r1.get("lv:1") is not None
        assert r2.get("lv:1") is not None

    def test_chains_disconnect(self):
        r1 = ConnectionRegistry()
        r2 = ConnectionRegistry()
        chained = ChainedTracker(DebugTracker(r1), DebugTracker(r2))
        sock = _make_mock_socket()

        chained.on_connect("lv:1", sock, FakeView, "/test", {})
        chained.on_disconnect("lv:1")
        assert r1.get("lv:1") is None
        assert r2.get("lv:1") is None

    def test_chains_event(self):
        r1 = ConnectionRegistry()
        r2 = ConnectionRegistry()
        chained = ChainedTracker(DebugTracker(r1), DebugTracker(r2))
        sock = _make_mock_socket()

        chained.on_connect("lv:1", sock, FakeView, "/test", {})
        chained.on_event("lv:1", "click", 0.01)
        assert r1.get("lv:1").event_count == 1
        assert r2.get("lv:1").event_count == 1

    def test_satisfies_protocol(self):
        chained = ChainedTracker(DebugTracker(ConnectionRegistry()))
        assert isinstance(chained, ConnectionTracker)


# --- Context introspection ---


class TestDeepGetsizeof:
    def test_simple_int(self):
        size = deep_getsizeof(42)
        assert size > 0

    def test_dict(self):
        d = {"a": 1, "b": [1, 2, 3]}
        size = deep_getsizeof(d)
        # Should be larger than just the dict shell
        import sys

        assert size > sys.getsizeof(d)

    def test_shared_references_not_double_counted(self):
        shared = [1, 2, 3]
        d = {"a": shared, "b": shared}
        size = deep_getsizeof(d)
        # The shared list should only be counted once
        separate = {"a": [1, 2, 3], "b": [4, 5, 6]}
        separate_size = deep_getsizeof(separate)
        assert size < separate_size


class TestInspectContext:
    def test_dict_context(self):
        ctx = {"count": 42, "name": "test"}
        result = inspect_context(ctx)
        assert result["type"] == "dict"
        assert result["total_size_bytes"] > 0
        assert "count" in result["fields"]
        assert "name" in result["fields"]
        assert result["fields"]["count"]["type"] == "int"
        assert result["fields"]["count"]["repr"] == "42"

    def test_sensitive_fields_redacted(self):
        ctx = {"username": "alice", "password": "s3cret", "api_token": "abc123"}
        result = inspect_context(ctx)
        assert result["fields"]["username"]["repr"] == "'alice'"
        assert result["fields"]["password"]["repr"] == "***"
        assert result["fields"]["api_token"]["repr"] == "***"

    def test_per_field_sizes(self):
        ctx = {"small": 1, "big": list(range(1000))}
        result = inspect_context(ctx)
        assert result["fields"]["big"]["size_bytes"] > result["fields"]["small"]["size_bytes"]


# --- enable_debug ---


class TestEnableDebug:
    def test_enable_debug_registers_route(self):
        from pyview.pyview import PyView
        from pyview_debug import enable_debug

        app = PyView()
        registry = enable_debug(app, path="/debug")

        routes = app.registered_routes
        paths = [path for path, _ in routes]
        assert "/debug" in paths

    def test_enable_debug_installs_tracker(self):
        from pyview.pyview import PyView
        from pyview_debug import enable_debug

        app = PyView()
        enable_debug(app)

        assert app.connection_tracker is not None
        assert app.live_handler.connection_tracker is not None

    def test_enable_debug_chains_existing_tracker(self):
        from pyview.pyview import PyView
        from pyview_debug import enable_debug

        existing = MagicMock()
        existing.on_connect = MagicMock()
        existing.on_disconnect = MagicMock()
        existing.on_event = MagicMock()

        app = PyView(connection_tracker=existing)
        enable_debug(app)

        # Should be a ChainedTracker now
        assert isinstance(app.connection_tracker, ChainedTracker)

    def test_enable_debug_returns_registry(self):
        from pyview.pyview import PyView
        from pyview_debug import enable_debug

        app = PyView()
        registry = enable_debug(app)
        assert isinstance(registry, ConnectionRegistry)
