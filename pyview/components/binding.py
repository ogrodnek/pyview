"""Binding helpers for LiveComponent lifecycle methods."""

from __future__ import annotations

import logging
from typing import Any

from pyview.binding.binder import Binder
from pyview.binding.context import BindContext
from pyview.binding.params import Params

from .base import ComponentSocket, LiveComponent

logger = logging.getLogger(__name__)


async def call_component_mount(
    component: LiveComponent,
    socket: ComponentSocket,
    assigns: dict[str, Any],
) -> None:
    """Bind and call component.mount() with Depends() support.

    Args:
        component: The LiveComponent instance
        socket: The ComponentSocket instance
        assigns: Props from parent template

    Note:
        Session is not available to components. Session-dependent data
        should be passed from parent LiveView via assigns.
    """
    ctx = BindContext(
        params=Params({}),
        payload=None,
        url=None,
        socket=socket,
        event=None,
        extra={"assigns": assigns},
    )
    binder = Binder()
    result = await binder.abind(component.mount, ctx)

    if not result.success:
        component_name = component.__class__.__name__
        for err in result.errors:
            logger.warning(f"Component {component_name} mount binding error: {err}")
        raise ValueError(f"Component mount binding failed: {result.errors}")

    await component.mount(**result.bound_args)


async def call_component_update(
    component: LiveComponent,
    socket: ComponentSocket,
    assigns: dict[str, Any],
) -> None:
    """Bind and call component.update() with Depends() support.

    Args:
        component: The LiveComponent instance
        socket: The ComponentSocket instance
        assigns: Updated props from parent template
    """
    ctx = BindContext(
        params=Params({}),
        payload=None,
        url=None,
        socket=socket,
        event=None,
        extra={"assigns": assigns},
    )
    binder = Binder()
    result = await binder.abind(component.update, ctx)

    if not result.success:
        component_name = component.__class__.__name__
        for err in result.errors:
            logger.warning(f"Component {component_name} update binding error: {err}")
        raise ValueError(f"Component update binding failed: {result.errors}")

    await component.update(**result.bound_args)


async def call_component_handle_event(
    component: LiveComponent,
    event: str,
    payload: dict[str, Any],
    socket: ComponentSocket,
) -> None:
    """Bind and call component.handle_event() with Depends() support.

    Args:
        component: The LiveComponent instance
        event: Event name
        payload: Event payload dict
        socket: The ComponentSocket instance
    """
    ctx = BindContext(
        params=Params({}),
        payload=payload,
        url=None,
        socket=socket,
        event=event,
        extra={},
    )
    binder = Binder()
    result = await binder.abind(component.handle_event, ctx)

    if not result.success:
        component_name = component.__class__.__name__
        for err in result.errors:
            logger.warning(f"Component {component_name} event binding error: {err}")
        raise ValueError(f"Component event binding failed: {result.errors}")

    await component.handle_event(**result.bound_args)
