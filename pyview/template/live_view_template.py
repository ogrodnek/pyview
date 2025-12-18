"""
LiveViewTemplate processor for Python t-strings.
Converts Template objects into LiveView's diff tree structure.

This module requires Python 3.14+ for t-string support.
"""

import sys
from typing import TYPE_CHECKING, Any, Callable, TypeVar, Union
from dataclasses import dataclass

# T-string support requires Python 3.14+
if sys.version_info < (3, 14):
    raise ImportError(
        "T-string template support requires Python 3.14 or later. "
        f"Current version: {sys.version_info.major}.{sys.version_info.minor}"
    )

from string.templatelib import Template

if TYPE_CHECKING:
    from pyview.components.base import LiveComponent
    from pyview.stream import Stream

T = TypeVar("T")


@dataclass
class StreamList:
    """
    A list wrapper that carries stream metadata for T-string templates.

    This is returned by stream_for() and detected by LiveViewTemplate._process_list()
    to include the "stream" key in the wire format.
    """

    items: list[Any]
    stream: "Stream"


def stream_for(
    stream: "Stream[T]",
    render_fn: Callable[[str, T], "Template"],
) -> StreamList:
    """
    Render a stream in a T-string template.

    This function iterates over the stream and applies the render function to each item,
    returning a StreamList that LiveViewTemplate will process to include stream metadata.

    Args:
        stream: The Stream to render
        render_fn: A function that takes (dom_id, item) and returns a Template

    Returns:
        StreamList containing rendered items and stream reference

    Example:
        def template(self, assigns, meta):
            return t'''
            <div id="messages" phx-update="stream">
                {stream_for(assigns.messages, lambda dom_id, msg:
                    t'<div id="{dom_id}">{msg.text}</div>'
                )}
            </div>
            '''
    """
    items = [render_fn(dom_id, item) for dom_id, item in stream]
    return StreamList(items=items, stream=stream)


@dataclass
class LiveComponentPlaceholder:
    """Placeholder for live components in templates."""

    component_class: "type[LiveComponent]"
    component_id: str
    assigns: dict[str, Any]

    def __str__(self):
        # Return a placeholder that gets replaced during rendering
        return f"<pyview-component cid='{self.component_id}'/>"


@dataclass
class ComponentMarker:
    """Marker for component that will be resolved lazily in .text().

    Used during unconnected (HTTP) phase to defer component rendering
    until after lifecycle methods have run.
    """

    cid: int


class LiveViewTemplate:
    """Processes Python t-string Templates into LiveView diff tree format."""

    @staticmethod
    def process(template: Template, socket: Any = None) -> dict[str, Any]:
        """
        Convert a Python Template to LiveView diff tree format.

        The LiveView tree format:
        {
            "s": ["static", "parts", "here"],  # Static strings
            "0": "dynamic value",              # Dynamic values indexed by position
            "1": { "s": [...], "0": ... },    # Nested structures
            "d": [[...], [...]]               # For comprehensions (loops)
        }
        """
        # Use the template.strings directly for the static parts
        parts: dict[str, Any] = {"s": list(template.strings)}

        # Process only the interpolations
        interp_index = 0
        for item in template:
            if not isinstance(item, str):
                # This is an Interpolation object
                key = str(interp_index)

                # Get the actual value from the interpolation
                interp_value = item.value

                # Apply format specifier if present
                if hasattr(item, "format_spec") and item.format_spec:
                    try:
                        formatted_value = format(interp_value, item.format_spec)
                    except (ValueError, TypeError):
                        # If formatting fails, use the value as-is
                        formatted_value = interp_value
                else:
                    formatted_value = interp_value

                # Handle different interpolation types
                if isinstance(formatted_value, LiveComponentPlaceholder):
                    # Handle live component - Phoenix.js expects CID as a number
                    # which it looks up in output.components[cid]
                    if socket and hasattr(socket, "components"):
                        cid = socket.components.register(
                            formatted_value.component_class,
                            formatted_value.component_id,
                            formatted_value.assigns,
                        )
                        if getattr(socket, "connected", True):
                            # Connected: return CID for wire format
                            parts[key] = cid
                        else:
                            # Unconnected: store marker for lazy resolution in .text()
                            parts[key] = ComponentMarker(cid=cid)
                    else:
                        # Fallback if no socket available
                        parts[key] = str(formatted_value)

                elif isinstance(formatted_value, Template):
                    # Handle nested templates
                    parts[key] = LiveViewTemplate.process(formatted_value, socket)

                elif isinstance(formatted_value, str):
                    # Simple string interpolation (HTML escaped)
                    parts[key] = LiveViewTemplate.escape_html(formatted_value)

                elif isinstance(formatted_value, (int, float, bool)):
                    # Primitive types
                    parts[key] = str(formatted_value)

                elif isinstance(formatted_value, StreamList):
                    # Handle stream_for() results
                    parts[key] = LiveViewTemplate._process_stream_list(formatted_value, socket)

                elif isinstance(formatted_value, list):
                    # Handle list comprehensions
                    parts[key] = LiveViewTemplate._process_list(formatted_value, socket)

                elif hasattr(formatted_value, "__html__"):
                    # Handle objects that can render as HTML (like Markup)
                    parts[key] = str(formatted_value.__html__())

                else:
                    # Default: convert to string and escape
                    parts[key] = LiveViewTemplate.escape_html(str(formatted_value))

                interp_index += 1

        return parts

    @staticmethod
    def _process_list(items: list, socket: Any = None) -> Union[dict[str, Any], str]:
        """Process a list of items for the 'd' (dynamics) format."""
        if not items:
            return ""

        # Process each item based on its type
        processed_items = []
        for item in items:
            if isinstance(item, Template):
                # Process template items - produces {"s": [...], "0": ..., ...}
                processed_items.append(LiveViewTemplate.process(item, socket))
            elif isinstance(item, LiveComponentPlaceholder):
                # Handle component placeholders in lists
                # Phoenix.js expects CID as a number for component lookup
                if socket and hasattr(socket, "components"):
                    cid = socket.components.register(
                        item.component_class,
                        item.component_id,
                        item.assigns,
                    )
                    if getattr(socket, "connected", True):
                        # Connected: return CID for wire format
                        processed_items.append(cid)
                    else:
                        # Unconnected: store marker for lazy resolution in .text()
                        processed_items.append(ComponentMarker(cid=cid))
                else:
                    # Fallback if no socket available - just escaped string
                    processed_items.append(LiveViewTemplate.escape_html(str(item)))
            else:
                # Plain strings - just escape, will be wrapped once in fallback
                processed_items.append(LiveViewTemplate.escape_html(str(item)))

        # Phoenix.js comprehension format ALWAYS requires:
        # - "s": array of static strings (shared across all items)
        # - "d": array where each item is an array of dynamic values
        #
        # processed_items contains either:
        #   - dicts with {"s": [...], "0": val, "1": val, ...} for Template items
        #   - integer CIDs for component references
        #   - escaped strings for non-Template items

        # Check if all items are dicts with the same statics (true comprehension)
        if processed_items and isinstance(processed_items[0], dict) and "s" in processed_items[0]:
            first_statics = processed_items[0]["s"]
            all_same_statics = all(
                isinstance(item, dict) and item.get("s") == first_statics
                for item in processed_items
            )

            if all_same_statics:
                # True comprehension: all items share same statics
                # Extract statics to top level, keep only dynamics in "d"
                # Note: We rely on Python 3.7+ dict insertion order here.
                # Keys are inserted as "0", "1", "2", ... in process(), so
                # item.items() yields them in correct order without sorting.
                return {
                    "s": first_statics,
                    "d": [
                        [v for k, v in item.items() if k != "s"]
                        for item in processed_items
                    ],
                }

        # For all other cases (mixed types, different statics, components, etc.):
        # Use empty statics and wrap each item as a single dynamic
        # This ensures Phoenix.js comprehensionToBuffer always has valid statics
        return {
            "s": ["", ""],
            "d": [[item] for item in processed_items],
        }

    @staticmethod
    def _process_stream_list(
        stream_list: StreamList, socket: Any = None
    ) -> Union[dict[str, Any], str]:
        """Process a StreamList (from stream_for) including stream metadata."""
        from pyview.stream import Stream

        stream = stream_list.stream
        items = stream_list.items

        # Handle empty stream
        if not items:
            # Still check for delete/reset operations
            ops = stream._get_pending_ops()
            if ops is None:
                return ""
            return {"stream": stream._to_wire_format(ops)}

        # Process each item
        processed_items = []
        for item in items:
            if isinstance(item, Template):
                processed_items.append(LiveViewTemplate.process(item, socket))
            else:
                processed_items.append([LiveViewTemplate.escape_html(str(item))])

        result: dict[str, Any] = {"d": processed_items}

        # Extract statics from first item if it has them.
        # processed_items contains either:
        #   - dicts with {"s": [...], "0": val, "1": val, ...} for Template items
        #   - lists of escaped strings for non-Template items
        if processed_items and isinstance(processed_items[0], dict) and "s" in processed_items[0]:
            # All Template items share the same statics (the template's static strings),
            # so we extract "s" from the first item and use it for the entire result.
            result["s"] = processed_items[0]["s"]
            # Convert each item to just its dynamic values (excluding "s").
            # We rely on Python 3.7+ dict insertion order - keys are inserted as
            # "0", "1", "2", ... in process(), so item.items() yields correct order.
            # Non-dict items (lists): pass through as-is.
            result["d"] = [
                [v for k, v in item.items() if k != "s"]
                if isinstance(item, dict)
                else item
                for item in processed_items
            ]

        # Add stream metadata
        ops = stream._get_pending_ops()
        if ops is not None:
            result["stream"] = stream._to_wire_format(ops)

        return result

    @staticmethod
    def escape_html(text: str) -> str:
        """Escape HTML special characters."""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#x27;")
        )


def live_component(
    component_class: "type[LiveComponent]", id: str, **assigns
) -> LiveComponentPlaceholder:
    """
    Insert a live component into a template.

    Usage:
        comp = live_component(MyComponent, id="comp-1", foo="bar")
        template = t'<div>{comp}</div>'
    """
    return LiveComponentPlaceholder(
        component_class=component_class, component_id=id, assigns=assigns
    )
