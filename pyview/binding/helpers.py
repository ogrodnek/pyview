"""Helper functions for runtime integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from urllib.parse import ParseResult

from .binder import Binder
from .context import BindContext
from .params import Params

if TYPE_CHECKING:
    from pyview.live_socket import LiveViewSocket

logger = logging.getLogger(__name__)


async def call_mount(
    lv, socket: "LiveViewSocket", session: dict[str, Any]
) -> None:
    """Bind and call mount with Depends() support.

    Args:
        lv: The LiveView instance
        socket: The socket instance
        session: Session dict

    Returns:
        Result of lv.mount()
    """
    ctx = BindContext(
        params=Params({}),
        payload=None,
        url=None,
        socket=socket,
        event=None,
        extra={"session": session},
    )
    binder = Binder()
    result = await binder.abind(lv.mount, ctx)

    if not result.success:
        for err in result.errors:
            logger.warning(f"Mount binding error: {err}")
        raise ValueError(f"Mount binding failed: {result.errors}")

    return await lv.mount(**result.bound_args)


async def call_handle_params(
    lv, url: ParseResult, params: dict[str, list[str]], socket: "LiveViewSocket"
):
    """Bind params and call handle_params with signature-matched args.

    Args:
        lv: The LiveView instance
        url: Parsed URL
        params: Raw dict[str, list[str]] from parse_qs
        socket: The socket instance

    Returns:
        Result of lv.handle_params()
    """
    ctx = BindContext(
        params=Params(params),
        payload=None,
        url=url,
        socket=socket,
        event=None,
    )
    binder = Binder()
    result = await binder.abind(lv.handle_params, ctx)

    if not result.success:
        for err in result.errors:
            logger.warning(f"Param binding error: {err}")
        raise ValueError(f"Parameter binding failed: {result.errors}")

    return await lv.handle_params(**result.bound_args)


async def call_handle_event(lv, event: str, payload: dict, socket: "LiveViewSocket"):
    """Bind event payload and call handle_event with signature-matched args.

    Args:
        lv: The LiveView instance
        event: Event name (e.g., "increment", "submit")
        payload: Event payload dict
        socket: The socket instance

    Returns:
        Result of lv.handle_event()
    """
    ctx = BindContext(
        params=Params({}),
        payload=payload,
        url=None,
        socket=socket,
        event=event,
    )
    binder = Binder()
    result = await binder.abind(lv.handle_event, ctx)

    if not result.success:
        for err in result.errors:
            logger.warning(f"Event binding error: {err}")
        raise ValueError(f"Event binding failed: {result.errors}")

    return await lv.handle_event(**result.bound_args)
