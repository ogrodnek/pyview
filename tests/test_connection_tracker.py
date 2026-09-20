"""Tests for the ConnectionTracker protocol and its integration points."""

from pyview.connection_tracker import ConnectionTracker
from pyview.instrumentation import NoOpInstrumentation
from pyview.live_routes import LiveViewLookup
from pyview.live_view import LiveView
from pyview.pyview import PyView
from pyview.ws_handler import LiveSocketHandler


class DummyView(LiveView):
    pass


class FakeTracker:
    """A concrete ConnectionTracker implementation for testing."""

    def __init__(self):
        self.connects = []
        self.disconnects = []
        self.events = []

    def on_connect(self, topic, socket, view_class, route, session):
        self.connects.append(
            {
                "topic": topic,
                "socket": socket,
                "view_class": view_class,
                "route": route,
                "session": session,
            }
        )

    def on_disconnect(self, topic):
        self.disconnects.append(topic)

    def on_event(self, topic, event_name, duration_seconds):
        self.events.append(
            {
                "topic": topic,
                "event_name": event_name,
                "duration_seconds": duration_seconds,
            }
        )


def test_fake_tracker_satisfies_protocol():
    """FakeTracker should satisfy the ConnectionTracker protocol."""
    tracker = FakeTracker()
    assert isinstance(tracker, ConnectionTracker)


def test_handler_accepts_none_tracker():
    """LiveSocketHandler should work fine with no tracker (default)."""
    routes = LiveViewLookup()
    handler = LiveSocketHandler(routes, NoOpInstrumentation())
    assert handler.connection_tracker is None


def test_handler_accepts_tracker():
    """LiveSocketHandler should store the tracker when provided."""
    routes = LiveViewLookup()
    tracker = FakeTracker()
    handler = LiveSocketHandler(routes, NoOpInstrumentation(), connection_tracker=tracker)
    assert handler.connection_tracker is tracker


def test_protocol_is_runtime_checkable():
    """ConnectionTracker should be runtime-checkable via isinstance."""

    class NotATracker:
        pass

    class MinimalTracker:
        def on_connect(self, topic, socket, view_class, route, session):
            pass

        def on_disconnect(self, topic):
            pass

        def on_event(self, topic, event_name, duration_seconds):
            pass

    assert isinstance(MinimalTracker(), ConnectionTracker)
    assert not isinstance(NotATracker(), ConnectionTracker)


def test_registered_routes_empty():
    """PyView.registered_routes should return empty list with no routes."""
    app = PyView()
    assert app.registered_routes == []


def test_registered_routes_returns_routes():
    """PyView.registered_routes should return (path, view_class) tuples."""
    app = PyView()
    app.add_live_view("/test", DummyView)
    routes = app.registered_routes
    assert len(routes) == 1
    assert routes[0] == ("/test", DummyView)


def test_registered_routes_multiple():
    """PyView.registered_routes should return all registered routes."""

    class AnotherView(LiveView):
        pass

    app = PyView()
    app.add_live_view("/a", DummyView)
    app.add_live_view("/b", AnotherView)
    routes = app.registered_routes
    assert len(routes) == 2
    assert routes[0] == ("/a", DummyView)
    assert routes[1] == ("/b", AnotherView)


def test_pyview_passes_tracker_to_handler():
    """PyView should pass connection_tracker through to LiveSocketHandler."""
    tracker = FakeTracker()
    app = PyView(connection_tracker=tracker)
    assert app.live_handler.connection_tracker is tracker


def test_pyview_no_tracker_by_default():
    """PyView should have no tracker by default."""
    app = PyView()
    assert app.connection_tracker is None
    assert app.live_handler.connection_tracker is None
