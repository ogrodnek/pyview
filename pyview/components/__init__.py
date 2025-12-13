"""
PyView Components - Phoenix-style LiveComponents for Python.

This module provides stateful, reusable components that can:
- Maintain their own state (context)
- Handle their own events via phx-target
- Have lifecycle hooks (mount, update)

Usage:
    from pyview.components import LiveComponent, ComponentMeta, live_component

    class Counter(LiveComponent[CounterContext]):
        async def mount(self, socket):
            socket.context = {"count": 0}

        def template(self, assigns, meta):
            return t'''
                <div>
                    Count: {assigns["count"]}
                    <button phx-click="increment" phx-target="{meta.myself}">+</button>
                </div>
            '''

        async def handle_event(self, event, payload, socket):
            if event == "increment":
                socket.context["count"] += 1

    # In parent LiveView template:
    {live_component(Counter, id="counter-1")}
"""

from .base import ComponentMeta, ComponentSocket, LiveComponent

__all__ = [
    "LiveComponent",
    "ComponentMeta",
    "ComponentSocket",
]
