from typing import Callable

from .BaseEventHandler import BaseEventHandler


class BoundEventMethod:
    """
    A bound method wrapper that can be stringified to its event name.

    This allows methods to be referenced in templates like {self.increment}
    and have them automatically convert to their event name string.
    """

    def __init__(self, instance, func: Callable, event_name: str):
        self.instance = instance
        self.func = func
        self.event_name = event_name

    def __str__(self) -> str:
        """Return the event name when converted to string (for template interpolation)."""
        return self.event_name

    async def __call__(self, *args, **kwargs):
        """Still callable as a normal async method."""
        return await self.func(self.instance, *args, **kwargs)


class EventMethodDescriptor:
    """
    Descriptor that wraps event handler methods.

    When accessed, returns a BoundEventMethod that:
    1. Stringifies to the event name (for templates)
    2. Remains callable (for direct invocation)
    """

    def __init__(self, func: Callable, event_name: str):
        self.func = func
        self.event_name = event_name
        self.__name__ = func.__name__
        self.__doc__ = func.__doc__

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return BoundEventMethod(obj, self.func, self.event_name)

    def __set_name__(self, owner, name):
        """Called when the descriptor is assigned to a class attribute."""
        if not self.event_name:
            self.event_name = name


class AutoEventDispatch(BaseEventHandler):
    """
    Base class that enables automatic event dispatch from function references.

    Methods decorated with @event (with or without explicit names) can be
    referenced directly in templates, automatically converting to their event name.

    Inherits from BaseEventHandler and extends it by wrapping decorated methods
    with descriptors for template stringification.

    Usage:
        class MyView(AutoEventDispatch, TemplateView, LiveView):
            @event  # or @event()
            async def increment(self, event, payload, socket):
                socket.context["count"] += 1

            @event("custom-name")
            async def some_handler(self, event, payload, socket):
                pass

            def template(self, assigns, meta):
                return t'''
                    <button phx-click={self.increment}>+</button>
                    <button phx-click={self.some_handler}>Custom</button>
                '''
    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        # BaseEventHandler already populated _event_handlers with raw functions
        # Now we wrap them with descriptors for template stringification
        for event_name, handler in list(cls._event_handlers.items()):
            # Find which attribute this handler came from
            for attr_name in dir(cls):
                if not attr_name.startswith("_"):
                    attr = getattr(cls, attr_name, None)
                    if attr is handler or (
                        isinstance(attr, EventMethodDescriptor) and attr.func is handler
                    ):
                        # Wrap with descriptor if not already wrapped
                        if not isinstance(attr, EventMethodDescriptor):
                            descriptor = EventMethodDescriptor(handler, event_name)
                            setattr(cls, attr_name, descriptor)
                        break
