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

from typing import Any, Protocol

from .base import ComponentMeta, ComponentSocket, LiveComponent
from .manager import ComponentsManager
from .slots import Slots, slots


class ComponentsManagerProtocol(Protocol):
    """Protocol for component manager used in text() rendering."""

    def render_component(self, cid: int, parent_meta: Any) -> Any: ...

    def has_pending_lifecycle(self) -> bool: ...

    def get_all_cids(self) -> list[int]: ...

    def get_seen_cids(self) -> set[int]: ...

    async def run_pending_lifecycle(self) -> None: ...

    @property
    def component_count(self) -> int: ...


class SocketWithComponents(Protocol):
    """Protocol for socket with components manager (for template rendering)."""

    @property
    def components(self) -> ComponentsManagerProtocol: ...


__all__ = [
    "LiveComponent",
    "ComponentMeta",
    "ComponentSocket",
    "ComponentsManager",
    "ComponentsManagerProtocol",
    "SocketWithComponents",
    "Slots",
    "slots",
]
