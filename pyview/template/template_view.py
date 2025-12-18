"""
LiveView support for t-string templates.

This module requires Python 3.14+ for t-string support.
"""

import sys
from typing import Any, TypeVar, Generic, Optional

# T-string support requires Python 3.14+
if sys.version_info < (3, 14):
    raise ImportError(
        "T-string template support requires Python 3.14 or later. "
        f"Current version: {sys.version_info.major}.{sys.version_info.minor}"
    )

from pyview.components import SocketWithComponents
from .live_view_template import LiveViewTemplate, ComponentMarker
from string.templatelib import Template
from pyview.meta import PyViewMeta

T = TypeVar("T")


class TStringRenderedContent:
    """RenderedContent implementation for t-string templates."""

    def __init__(self, tree_data: dict[str, Any]):
        self._tree_data = tree_data

    def tree(self) -> dict[str, Any]:
        """Return the LiveView diff tree."""
        return self._tree_data

    def text(self, socket: Optional[SocketWithComponents] = None) -> str:
        """Convert tree back to HTML string, resolving any component markers.

        Args:
            socket: Optional socket with components manager for resolving
                    ComponentMarkers during unconnected phase.
        """
        return self._tree_to_html(self._tree_data, socket)

    def _tree_to_html(self, tree: dict[str, Any] | list[Any], socket: Optional[SocketWithComponents] = None) -> str:
        """Convert tree back to HTML, resolving ComponentMarkers."""
        if isinstance(tree, str):
            return tree

        if isinstance(tree, ComponentMarker):
            return self._resolve_component_marker(tree, socket)

        if not isinstance(tree, dict):
            return str(tree)

        # Handle comprehension format with "s" and "d" keys
        # This is the format for loops: {"s": ["<div>", "</div>"], "d": [["value1"], ["value2"]]}
        if "d" in tree and "s" in tree:
            statics = tree["s"]
            dynamics_list = tree["d"]
            html_items = []

            for dynamics in dynamics_list:
                # Each dynamics is a list of values to interleave with statics
                parts = []
                for i, static in enumerate(statics):
                    parts.append(static)
                    if i < len(dynamics):
                        dyn = dynamics[i]
                        parts.append(self._value_to_html(dyn, socket))
                html_items.append("".join(parts))

            return "".join(html_items)

        # Handle "d" without "s" (just a list of items)
        if "d" in tree:
            items = tree["d"]
            html_items = []
            for item in items:
                if isinstance(item, list) and len(item) == 1:
                    html_items.append(self._value_to_html(item[0], socket))
                else:
                    html_items.append(self._tree_to_html(item, socket))
            return "".join(html_items)

        html_parts = []
        statics = tree.get("s", [])

        for i, static in enumerate(statics):
            html_parts.append(static)

            # Look for dynamic content
            key = str(i)
            if key in tree:
                dynamic = tree[key]
                html_parts.append(self._value_to_html(dynamic, socket))

        return "".join(html_parts)

    def _value_to_html(self, value: Any, socket: Optional[SocketWithComponents]) -> str:
        """Convert a tree value to HTML string."""
        if isinstance(value, ComponentMarker):
            return self._resolve_component_marker(value, socket)
        elif isinstance(value, dict):
            return self._tree_to_html(value, socket)
        elif isinstance(value, list):
            return "".join(self._value_to_html(item, socket) for item in value)
        else:
            return str(value)

    def _resolve_component_marker(self, marker: ComponentMarker, socket: Optional[SocketWithComponents]) -> str:
        """Resolve a ComponentMarker to HTML by rendering the component."""
        if not socket or not hasattr(socket, "components"):
            return ""  # Component not available

        meta = PyViewMeta(socket=socket)
        template = socket.components.render_component(marker.cid, meta)
        if template is None:
            return ""

        # Process the component template and recursively convert to HTML
        component_tree = LiveViewTemplate.process(template, socket)
        return self._tree_to_html(component_tree, socket)


class TemplateView(Generic[T]):
    """
    Mixin for LiveView classes to support t-string templates.

    Usage:
        class MyView(TemplateView, LiveView[MyContext]):
            def template(self, assigns: MyContext, meta: PyViewMeta):
                return t'<div>{assigns.name}</div>'
    """

    async def render(self, assigns: T, meta: PyViewMeta):
        """Override render to check for t-string template method."""

        # Check if this class has a template method
        if hasattr(self, "template") and callable(self.template):
            # Call template method with both assigns and meta
            template = self.template(assigns, meta)

            # Ensure it returns a Template
            if not isinstance(template, Template):
                raise ValueError(
                    f"template() method must return a Template, got {type(template)}"
                )

            # Process the template into LiveView tree format
            # Pass socket for component registration if available
            socket = meta.socket if meta else None
            tree = LiveViewTemplate.process(template, socket=socket)

            return TStringRenderedContent(tree)

        # Fall back to parent implementation (Ibis templates)
        return await super().render(assigns, meta)  # type: ignore

    def template(self, assigns: T, meta: PyViewMeta) -> Template:
        """
        Override this method to provide a t-string template.

        Args:
            assigns: The typed context object (dataclass)
            meta: PyViewMeta object with request info

        Returns:
            Template: A t-string Template object
        """
        raise NotImplementedError("Subclasses must implement the template() method")
