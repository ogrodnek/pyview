"""
Component rendering utilities.

This module requires Python 3.14+ for t-string support.
"""

from typing import Any

from pyview.template.live_view_template import LiveViewTemplate


def render_component_tree(template: Any, socket: Any) -> dict[str, Any]:
    """Process a component template into Phoenix wire format."""
    return LiveViewTemplate.process(template, socket=socket)
