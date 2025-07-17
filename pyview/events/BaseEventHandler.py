from typing import Callable, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from pyview.live_view import InfoEvent


def event(*event_names):
    """Decorator that marks methods as event handlers."""

    def decorator(func):
        func._event_names = event_names
        return func

    return decorator


def info(*info_names):
    """Decorator that marks methods as info handlers."""

    def decorator(func):
        func._info_names = info_names
        return func

    return decorator


class BaseEventHandler:
    """Base class for event handlers to handle dispatching events and info."""

    _event_handlers: dict[str, Callable] = {}
    _info_handlers: dict[str, Callable] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        # Find all decorated methods and register them
        cls._event_handlers = {}
        cls._info_handlers = {}
        for attr_name in dir(cls):
            if not attr_name.startswith("_"):
                attr = getattr(cls, attr_name)
                if hasattr(attr, "_event_names"):
                    for event_name in attr._event_names:
                        cls._event_handlers[event_name] = attr
                if hasattr(attr, "_info_names"):
                    for info_name in attr._info_names:
                        cls._info_handlers[info_name] = attr

    async def handle_event(self, event: str, payload: dict, socket):
        handler = self._event_handlers.get(event)

        if handler:
            return await handler(self, event, payload, socket)
        else:
            logging.warning(f"Unhandled event: {event} {payload}")

    async def handle_info(self, event: "InfoEvent", socket):
        handler = self._info_handlers.get(event.name)

        if handler:
            return await handler(self, event, socket)
        else:
            logging.warning(f"Unhandled info: {event.name} {event}")
