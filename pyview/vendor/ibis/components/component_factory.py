import contextvars
from typing import Protocol, Any
from dataclasses import dataclass

live_component_factory_var = contextvars.ContextVar("live_component_factory")


@dataclass
class ComponentReference:
    id: str
    cid: int

    @property
    def target(self):
        return self.cid


class ComponentFactory(Protocol):
    def register_component(
        self, id: str, component_name: str, template_vars: dict[str, Any]
    ) -> ComponentReference: ...


def get_component_factory() -> ComponentFactory:
    return live_component_factory_var.get()


def set_component_factory(factory: ComponentFactory):
    live_component_factory_var.set(factory)
