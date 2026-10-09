"""Every LiveView joined on a websocket is closed when the websocket closes."""

import pytest

from .views import StaticView


async def test_disconnect_closes_joined_view(connect):
    # Given a client joined to a LiveView
    disconnected = []

    class Home(StaticView):
        async def disconnect(self, socket):
            disconnected.append("Home")

    client = connect({"/": Home})
    reply = await client.join("/")
    assert reply["status"] == "ok"

    # When the websocket closes
    await client.disconnect()

    # Then the view is disconnected exactly once
    assert disconnected == ["Home"]


async def test_disconnect_after_live_navigation_closes_navigated_view(connect):
    # Given a client that live-navigated from /a to /b (leave the old view, join with `redirect`)
    disconnected = []

    class PageA(StaticView):
        async def disconnect(self, socket):
            disconnected.append("PageA")

    class PageB(StaticView):
        async def disconnect(self, socket):
            disconnected.append("PageB")

    client = connect({"/a": PageA, "/b": PageB})
    await client.join("/a")
    await client.leave()
    reply = await client.join("/b", redirect=True)
    assert reply["status"] == "ok"

    # When the websocket closes
    await client.disconnect()

    # Then both views have been disconnected, each exactly once
    assert disconnected == ["PageA", "PageB"]


async def test_failed_mount_during_live_navigation_closes_navigated_view(connect):
    # Given a client on /a navigating to a view whose mount fails after subscribing
    disconnected = []

    class PageA(StaticView):
        async def disconnect(self, socket):
            disconnected.append("PageA")

    class PageB(StaticView):
        async def mount(self, socket, session):
            await super().mount(socket, session)
            await socket.subscribe("updates")
            raise RuntimeError("mount failed")

        async def disconnect(self, socket):
            disconnected.append("PageB")

    client = connect({"/a": PageA, "/b": PageB})
    await client.join("/a")
    await client.leave()

    # When the client navigates to /b
    with pytest.raises(RuntimeError, match="mount failed"):
        await client.join("/b", redirect=True)

    # Then the partially mounted view is still closed, exactly once
    assert disconnected == ["PageA", "PageB"]
