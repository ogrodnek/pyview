import importlib
import inspect
from typing import Any
from pyview.live_component.live_component import LiveComponent
from pyview.live_component.live_components_context import (
    LiveComponentsContext,
)
from pyview.live_component.component_registry import components
from pyview.vendor.ibis.components.component_factory import (
    ComponentReference,
)


class LiveComponentFactory:
    def __init__(self, context: LiveComponentsContext):
        self.context = context

    def register_component(
        self, id: str, component_name: str, template_vars: dict[str, Any]
    ) -> ComponentReference:
        component_class = get_live_component(component_name)
        return self.context.register_component(id, component_class(), template_vars)


def get_live_component(class_name: str) -> type[LiveComponent]:

    registered_component = components.get_component(class_name)
    if registered_component:
        # TODO: check type
        return registered_component

    # Split the fully qualified name into module and class
    module_name, class_name = class_name.rsplit(".", 1)

    # Dynamically import the module
    module = importlib.import_module(module_name)

    # Get the class from the module
    component_class = getattr(module, class_name)

    # Check if it's a subclass of LiveComponent
    if not inspect.isclass(component_class) or not issubclass(
        component_class, LiveComponent
    ):
        raise TypeError(f"{component_class} is not a subclass of LiveComponent")

    return component_class
