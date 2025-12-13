"""
LiveView support for t-string templates.

This module requires Python 3.14+ for t-string support.
"""

import sys
from typing import Any, TypeVar, Generic

# T-string support requires Python 3.14+
if sys.version_info < (3, 14):
    raise ImportError(
        "T-string template support requires Python 3.14 or later. "
        f"Current version: {sys.version_info.major}.{sys.version_info.minor}"
    )

from .live_view_template import LiveViewTemplate
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

    def text(self) -> str:
        """Convert tree back to HTML string (for testing/debugging)."""
        return self._tree_to_html(self._tree_data)

    def _tree_to_html(self, tree: dict[str, Any] | list[Any]) -> str:
        """Convert tree back to HTML (simplified version)."""
        if isinstance(tree, str):
            return tree

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
                        if isinstance(dyn, dict):
                            parts.append(self._tree_to_html(dyn))
                        else:
                            parts.append(str(dyn))
                html_items.append("".join(parts))

            return "".join(html_items)

        # Handle "d" without "s" (just a list of items)
        if "d" in tree:
            items = tree["d"]
            html_items = []
            for item in items:
                if isinstance(item, list) and len(item) == 1:
                    html_items.append(str(item[0]))
                else:
                    html_items.append(self._tree_to_html(item))
            return "".join(html_items)

        html_parts = []
        statics = tree.get("s", [])

        for i, static in enumerate(statics):
            html_parts.append(static)

            # Look for dynamic content
            key = str(i)
            if key in tree:
                dynamic = tree[key]
                if isinstance(dynamic, dict):
                    html_parts.append(self._tree_to_html(dynamic))
                else:
                    html_parts.append(str(dynamic))

        return "".join(html_parts)


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
