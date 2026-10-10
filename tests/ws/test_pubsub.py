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
    diff = await reader.next_push()
    assert diff.event == "diff"
    assert received == [InfoEvent("news", {"headline": "pyview 1.0"})]
    assert diff.payload == {"0": "pyview 1.0"}


async def test_broadcast_reaches_the_sending_view_when_it_is_subscribed(connect):
    # Given a view subscribed to a topic that it also broadcasts on
    received = []

    class Chat(StaticView):
        async def mount(self, socket, session):
            socket.context = {"last": ""}
            await socket.subscribe("chat")

        async def handle_event(self, event, payload, socket):
            await socket.broadcast("chat", {"text": "hello"})

        async def handle_info(self, event, socket):
            received.append(event)
            socket.context["last"] = event.payload["text"]

        async def render(self, assigns, meta):
            return TextRendered(assigns["last"])

    client = connect({"/": Chat})
    await client.join("/")

    # When the view broadcasts
    await client.event("send")

    # Then its own handle_info gets the message and its client gets the change
    diff = await client.next_push()
    assert diff.event == "diff"
    assert received == [InfoEvent("chat", {"text": "hello"})]
    assert diff.payload == {"0": "hello"}


def news_views(received: list):
    """A publisher that also reads its own broadcasts, and a reader that records them."""

    class Publisher(StaticView):
        async def mount(self, socket, session):
            await super().mount(socket, session)
            await socket.subscribe("news")

        async def handle_event(self, event, payload, socket):
            await socket.broadcast("news", {"headline": "pyview 1.0"})

    class Reader(StaticView):
        async def mount(self, socket, session):
            await super().mount(socket, session)
            await socket.subscribe("news")

        async def handle_info(self, event, socket):
            received.append(event)

    return Publisher, Reader


async def test_broadcast_does_not_reach_a_view_that_left(connect):
    # Given a reader subscribed to a topic, which then leaves its view
    received = []
    Publisher, Reader = news_views(received)
    publisher = connect({"/": Publisher}, topic="lv:phx-publisher")
    reader = connect({"/": Reader}, topic="lv:phx-reader")
    await publisher.join("/")
    await reader.join("/")
    await reader.leave()

    # When a message is broadcast on the topic, and has reached the publisher's own view
    await publisher.event("publish")
    assert (await publisher.next_push()).event == "diff"

    # Then the view that left never handles it
    assert received == []
    assert reader.pushes() == []


async def test_broadcast_does_not_reach_a_view_whose_connection_closed(connect):
    # Given a reader subscribed to a topic, whose websocket then closes
    received = []
    Publisher, Reader = news_views(received)
    publisher = connect({"/": Publisher}, topic="lv:phx-publisher")
    reader = connect({"/": Reader}, topic="lv:phx-reader")
    await publisher.join("/")
    await reader.join("/")
    await reader.disconnect()

    # When a message is broadcast on the topic, and has reached the publisher's own view
    await publisher.event("publish")
    assert (await publisher.next_push()).event == "diff"

    # Then the closed view never handles it
    assert received == []


async def test_after_live_navigation_only_the_new_view_receives_broadcasts(connect):
    # Given a client that live-navigated from one subscribed view to another on the same topic
    received = []

    class Publisher(StaticView):
        async def handle_event(self, event, payload, socket):
            await socket.broadcast("news", {"headline": "pyview 1.0"})

    class FrontPage(StaticView):
        async def mount(self, socket, session):
            await super().mount(socket, session)
            await socket.subscribe("news")

        async def handle_info(self, event, socket):
            received.append(("FrontPage", event))

    class Article(StaticView):
        async def mount(self, socket, session):
            socket.context = {"headline": ""}
            await socket.subscribe("news")

        async def handle_info(self, event, socket):
            received.append(("Article", event))
            socket.context["headline"] = event.payload["headline"]

        async def render(self, assigns, meta):
            return TextRendered(assigns["headline"])

    publisher = connect({"/": Publisher}, topic="lv:phx-publisher")
    reader = connect({"/": FrontPage, "/article": Article}, topic="lv:phx-reader")
    await publisher.join("/")
    await reader.join("/")
    await reader.leave()
    await reader.join("/article", redirect=True)

    # When a message is broadcast on the topic
    await publisher.event("publish")

    # Then only the view navigated to handles it, and its client gets the change
    diff = await reader.next_push()
    assert diff.event == "diff"
    assert received == [("Article", InfoEvent("news", {"headline": "pyview 1.0"}))]
    assert diff.payload == {"0": "pyview 1.0"}
