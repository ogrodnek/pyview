from pyview.live_component.live_component import LiveComponent
from pyview.live_component.component_registry import components


@components.register("Ratings")
class RatingsComponent(LiveComponent):
    async def mount(self, socket):
        print("Ratings mounted")

    async def update(self, socket, template_vars):
        print("Ratings updated", template_vars)
