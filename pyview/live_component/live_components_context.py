from dataclasses import dataclass
from pyview.live_component.live_component import LiveComponent
from pyview.vendor.ibis.components.component_factory import ComponentReference
from pyview.live_component.live_component_socket import (
    LiveComponentSocket,
    LiveComponentMeta,
)
from typing import Any


@dataclass
class LiveComponentContext:
    ref: ComponentReference
    component: LiveComponent
    context: dict[str, Any]


class LiveComponentsContext:
    cid_index = 1
    components: list[LiveComponentContext]
    component_sockets: dict[str, LiveComponentSocket]

    def __init__(self):
        self.components = []
        self.component_sockets = {}

    def register_component(
        self, user_id: str, component: LiveComponent, context: dict[str, Any]
    ) -> ComponentReference:

        id = f"{user_id}-{component.__class__.__name__}"
        ref = ComponentReference(id, self.cid_index)

        print("Registering component", id, ref)
        for c in self.components:
            if c.ref.id == id:
                c.context = context
                print("Component already registered", id)
                return c.ref

        print("Component not registered", id)

        self.components.append(LiveComponentContext(ref, component, context))
        self.cid_index += 1
        return ref

    async def _update_component(self, component: LiveComponentContext):
        if component.ref.id not in self.component_sockets:
            socket = LiveComponentSocket()
            socket.meta = LiveComponentMeta(component.ref)
            await component.component.mount(socket)
            self.component_sockets[component.ref.id] = socket

        socket = self.component_sockets[component.ref.id]
        await component.component.update(socket, component.context)

    async def update_components(self):
        for component in self.components:
            await self._update_component(component)

    async def _render_component(
        self, component: LiveComponentContext, rendered: dict[int, Any]
    ):
        if component.ref.id not in self.component_sockets:
            await self._update_component(component)

        socket = self.component_sockets[component.ref.id]
        rendered[component.ref.cid] = (
            await component.component.render(component.context, socket.meta)
        ).tree()

    async def render_components(self):
        rendered = {}

        for component in self.components:
            await self._render_component(component, rendered)

        return rendered
