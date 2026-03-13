from __future__ import annotations

from typing import TYPE_CHECKING

from pyview_debug.dashboard import make_dashboard_view
from pyview_debug.registry import ConnectionRegistry
from pyview_debug.tracker import ChainedTracker, DebugTracker

if TYPE_CHECKING:
    from pyview.pyview import PyView


def enable_debug(app: PyView, path: str = "/debug") -> ConnectionRegistry:
    """Enable the debug dashboard on a PyView app.

    Installs a ConnectionTracker that populates a ConnectionRegistry,
    and registers a dashboard LiveView at the given path.

    Args:
        app: The PyView application instance.
        path: URL path for the debug dashboard (default: "/debug").

    Returns:
        The ConnectionRegistry, in case you want to inspect it programmatically.
    """
    registry = ConnectionRegistry()
    tracker = DebugTracker(registry)

    # Chain with existing tracker if one is already set
    if app.connection_tracker:
        tracker = ChainedTracker(app.connection_tracker, tracker)

    app.connection_tracker = tracker
    app.live_handler.connection_tracker = tracker

    # Create and register the dashboard view
    dashboard_view = make_dashboard_view(registry, app)
    app.add_live_view(path, dashboard_view)

    return registry
