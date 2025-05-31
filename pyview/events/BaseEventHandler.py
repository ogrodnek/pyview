from typing import Callable
import logging


def event(*event_names):
    """Decorator that marks methods as event handlers."""

    def decorator(func):
        func._event_names = event_names
        return func

    return decorator


class BaseEventHandler:
    """Base class for event handlers to handle dispatching events."""

    _event_handlers: dict[str, Callable] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        # Find all decorated methods and register them
        cls._event_handlers = {}
        for attr_name in dir(cls):
            if not attr_name.startswith("_"):
                attr = getattr(cls, attr_name)
                if hasattr(attr, "_event_names"):
                    for event_name in attr._event_names:
                        cls._event_handlers[event_name] = attr

    async def handle_event(self, event: str, payload: dict, socket):
        handler = self._event_handlers.get(event)

        if handler:
            return await handler(self, event, payload, socket)
        else:
            logging.warning(f"Unhandled event: {event} {payload}")
