from pyview.live_component.live_component import LiveComponent
from pyview.live_component.component_registry import components


@components.register("RecipeCard")
class RecipeCardComponent(LiveComponent):
    def __init__(self):
        super().__init__()
