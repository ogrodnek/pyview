from typing import Optional


class ComponentRegistry:
    def __init__(self):
        self._registry = {}

    def register(self, name):
        def decorator(cls):
            self._registry[name] = cls
            return cls

        return decorator

    def get_component(self, name) -> Optional[type]:
        component_class = self._registry.get(name)
        return component_class


components = ComponentRegistry()
