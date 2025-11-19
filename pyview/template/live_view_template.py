"""
LiveViewTemplate processor for Python t-strings.
Converts Template objects into LiveView's diff tree structure.

This module requires Python 3.14+ for t-string support.
"""

import sys
from typing import Any, Union
from dataclasses import dataclass

# T-string support requires Python 3.14+
if sys.version_info < (3, 14):
    raise ImportError(
        "T-string template support requires Python 3.14 or later. "
        f"Current version: {sys.version_info.major}.{sys.version_info.minor}"
    )

from string.templatelib import Template


@dataclass
class LiveComponentPlaceholder:
    """Placeholder for live components in templates."""

    component_class: type
    component_id: str
    assigns: dict[str, Any]

    def __str__(self):
        # Return a placeholder that gets replaced during rendering
        return f"<pyview-component cid='{self.component_id}'/>"


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
                    # Handle live component
                    if socket and hasattr(socket, "components"):
                        cid = socket.components.register(
                            formatted_value.component_class,
                            formatted_value.component_id,
                            formatted_value.assigns,
                        )
                        parts[key] = {"c": cid}
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
                # Process template items
                processed_items.append(LiveViewTemplate.process(item, socket))
            else:
                # Convert non-template items to escaped strings
                processed_items.append([LiveViewTemplate.escape_html(str(item))])

        return {"d": processed_items}

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
    component_class: type, id: str, **assigns
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
