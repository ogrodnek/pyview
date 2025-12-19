"""
Helper for running component lifecycle with nested component discovery.

This module handles nested component discovery (e.g., components inside slots),
which requires iterating lifecycle + template rendering until no new components
are discovered. Used by both HTTP (unconnected) and WebSocket (connected) flows.
"""

import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pyview.components import SocketWithComponents
    from pyview.meta import PyViewMeta

MAX_COMPONENT_ITERATIONS = 10


async def run_nested_component_lifecycle(
    socket: "SocketWithComponents",
    meta: "PyViewMeta",
    max_iterations: int = MAX_COMPONENT_ITERATIONS,
) -> None:
    """
    Run component lifecycle, discovering nested components.

    On Python 3.14+, this iterates to discover components nested inside
    other components' templates. On earlier versions, it just runs the
    initial lifecycle (no t-string support means no nested components).

    Args:
        socket: Socket with components manager
        meta: PyViewMeta for component rendering
        max_iterations: Maximum iteration limit to catch circular dependencies
    """
    await socket.components.run_pending_lifecycle()

    # Nested component discovery only works with t-strings (Python 3.14+)
    if sys.version_info < (3, 14):
        return

    # Import t-string support (guarded by version check above)
    from string.templatelib import Template

    from pyview.template.live_view_template import LiveViewTemplate

    # Track which CIDs we've already discovered nested components for
    discovered_cids: set[int] = set()
    iterations = 0

    while True:
        # Find CIDs that haven't been processed yet
        all_cids = set(socket.components.get_all_cids())
        new_cids = all_cids - discovered_cids

        # Exit if no new components and no pending lifecycle
        if not new_cids and not socket.components.has_pending_lifecycle():
            break

        # Render new component templates to discover nested components
        for cid in new_cids:
            discovered_cids.add(cid)
            template: Any = socket.components.render_component(cid, meta)
            if isinstance(template, Template):
                LiveViewTemplate.process(template, socket=socket)

        # If nested components were discovered, run their lifecycle
        if socket.components.has_pending_lifecycle():
            if iterations >= max_iterations:
                raise RuntimeError(
                    f"Component lifecycle exceeded {max_iterations} iterations. "
                    "Check for circular component dependencies."
                )
            await socket.components.run_pending_lifecycle()
            iterations += 1
