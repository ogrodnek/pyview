"""Messages broadcast on a pubsub topic reach the views subscribed to it."""

from pyview.events import InfoEvent

from .views import StaticView, TextRendered


async def test_broadcast_reaches_view_subscribed_on_another_connection(connect):
    # Given a view on one connection that broadcasts when an event arrives,
    # and a view on another connection subscribed to that topic
    received = []

    class Publisher(StaticView):
        async def handle_event(self, event, payload, socket):
            await socket.broadcast("news", {"headline": "pyview 1.0"})

    class Reader(StaticView):
        async def mount(self, socket, session):
            socket.context = {"headline": ""}
            await socket.subscribe("news")

        async def handle_info(self, event, socket):
            received.append(event)
            socket.context["headline"] = event.payload["headline"]

        async def render(self, assigns, meta):
            return TextRendered(assigns["headline"])

    publisher = connect({"/": Publisher}, topic="lv:phx-publisher")
    reader = connect({"/": Reader}, topic="lv:phx-reader")
    await publisher.join("/")
    await reader.join("/")

    # When the publisher's view broadcasts
    await publisher.event("publish")

    # Then the reader's view handles the message and its client gets the change
    diff = await reader.wait_for_push("diff")
    assert received == [InfoEvent("news", {"headline": "pyview 1.0"})]
    assert diff[4] == {"0": "pyview 1.0"}
