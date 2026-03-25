"""Redirect repro: Two pages that use live_redirect to navigate between each other.

This triggers the `redirect=true` path in the Phoenix LiveView JS client,
which sends a phx_join payload with `redirect` instead of `url`.
"""

from typing import TypedDict

from pyview import LiveView, LiveViewSocket


class PageContext(TypedDict):
    page: str


class PageALiveView(LiveView[PageContext]):
    """
    Redirect Repro — Page A

    Click the link to live_redirect to Page B. This exercises the redirect
    payload path in the WebSocket handler.
    """

    async def mount(self, socket: LiveViewSocket[PageContext], session):
        socket.context = PageContext(page="A")

    async def handle_event(self, event: str, socket: LiveViewSocket[PageContext]):
        if event == "go_to_b":
            await socket.redirect("/redirect_b")


class PageBLiveView(LiveView[PageContext]):
    """
    Redirect Repro — Page B

    Click the link to live_redirect back to Page A.
    """

    async def mount(self, socket: LiveViewSocket[PageContext], session):
        socket.context = PageContext(page="B")

    async def handle_event(self, event: str, socket: LiveViewSocket[PageContext]):
        if event == "go_to_a":
            await socket.redirect("/redirect_a")
