from pyview.live_component.live_component import LiveComponent
from pyview.live_component.component_registry import components


@components.register("Ratings")
class RatingsComponent(LiveComponent):
    pass
