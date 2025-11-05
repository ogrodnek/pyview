"""
Typed Parameters Demo

This example demonstrates the @typed_params decorator for automatic parameter
conversion. Compare this to the basic count example to see how much cleaner
parameter handling becomes!

Features demonstrated:
- Automatic type conversion for URL parameters
- Type conversion for event payloads
- Optional parameters with defaults
- List parameters (multiple values)
- Compatible with @event decorator
"""

from pyview import LiveView, LiveViewSocket
from pyview.params import typed_params
from pyview.events import event, BaseEventHandler
from typing import TypedDict, Optional


class DemoContext(TypedDict):
    count: int
    multiplier: int
    tags: list[str]
    enabled: bool
    message: Optional[str]


class TypedParamsDemoLiveView(BaseEventHandler, LiveView[DemoContext]):
    """
    Demonstrates automatic parameter type conversion.

    Try these URLs:
    - /typed_params_demo?count=10
    - /typed_params_demo?count=5&multiplier=3
    - /typed_params_demo?count=100&multiplier=2&enabled=true
    - /typed_params_demo?tags=python&tags=web&tags=liveview
    """

    async def mount(self, socket: LiveViewSocket[DemoContext], session):
        socket.context = DemoContext({
            "count": 0,
            "multiplier": 1,
            "tags": [],
            "enabled": True,
            "message": None,
        })

    @typed_params
    async def handle_params(
        self,
        socket: LiveViewSocket[DemoContext],
        count: int = 0,
        multiplier: int = 1,
        enabled: bool = True,
        tags: Optional[list[str]] = None,
    ):
        """
        Look ma, no manual conversion!

        Compare to the traditional approach:
            if "count" in params:
                count = int(params["count"][0])
            if "multiplier" in params:
                multiplier = int(params["multiplier"][0])
            ...

        With @typed_params, all the conversion happens automatically!
        """
        socket.context["count"] = count
        socket.context["multiplier"] = multiplier
        socket.context["enabled"] = enabled
        socket.context["tags"] = tags or []

    @event("increment")
    @typed_params
    async def on_increment(self, event, amount: int = 1, socket=None):
        """
        Increment by a specified amount.

        The 'amount' parameter is automatically converted from the payload!
        """
        socket.context["count"] += amount * socket.context["multiplier"]
        socket.context["message"] = f"Incremented by {amount}"

    @event("decrement")
    @typed_params
    async def on_decrement(self, event, amount: int = 1, socket=None):
        """Decrement by a specified amount."""
        socket.context["count"] -= amount * socket.context["multiplier"]
        socket.context["message"] = f"Decremented by {amount}"

    @event("set_multiplier")
    @typed_params
    async def on_set_multiplier(self, event, value: int, socket=None):
        """Set the multiplier value."""
        socket.context["multiplier"] = value
        socket.context["message"] = f"Multiplier set to {value}"

    @event("toggle_enabled")
    @typed_params
    async def on_toggle(self, event, socket=None):
        """Toggle the enabled state."""
        socket.context["enabled"] = not socket.context["enabled"]
        socket.context["message"] = (
            "Enabled" if socket.context["enabled"] else "Disabled"
        )

    @event("add_tag")
    @typed_params
    async def on_add_tag(self, event, tag: str, socket=None):
        """Add a tag to the list."""
        if tag and tag not in socket.context["tags"]:
            socket.context["tags"].append(tag)
            socket.context["message"] = f"Added tag: {tag}"

    @event("clear_tags")
    async def on_clear_tags(self, event, payload, socket):
        """Clear all tags (demonstrates traditional style still works)."""
        socket.context["tags"] = []
        socket.context["message"] = "Tags cleared"

    @event("reset")
    async def on_reset(self, event, payload, socket):
        """Reset everything to defaults."""
        socket.context["count"] = 0
        socket.context["multiplier"] = 1
        socket.context["tags"] = []
        socket.context["enabled"] = True
        socket.context["message"] = "Reset to defaults"
