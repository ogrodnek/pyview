"""Parameter binding for pyview handlers.

This module provides signature-driven parameter binding, allowing handlers to
declare typed parameters that are automatically converted from request data.

Example:
    # Old style (manual extraction):
    async def handle_params(self, url, params, socket):
        page = int(params["page"][0]) if "page" in params else 1

    # New style (typed binding):
    async def handle_params(self, socket: LiveViewSocket[MyContext], page: int = 1):
        # page is already an int!
        pass

Reserved parameter names (injected from context, not from URL params):
    - socket: The LiveViewSocket instance
    - url: The parsed URL
    - event: The event name (for event handlers)
    - payload: The event payload dict (for event handlers)

Type-based injection:
    - params: Params  -> injects Params container
    - params: dict    -> injects params as dict
    - params: str     -> treats "params" as a URL param name (not injected)
"""

from .binder import Binder
from .context import BindContext
from .converters import ConversionError, ConverterRegistry
from .helpers import call_handle_event, call_handle_params
from .injectables import InjectableRegistry
from .params import Params
from .result import BindResult, ParamError

__all__ = [
    "Params",
    "BindContext",
    "BindResult",
    "ParamError",
    "ConverterRegistry",
    "ConversionError",
    "InjectableRegistry",
    "Binder",
    "call_handle_event",
    "call_handle_params",
]
