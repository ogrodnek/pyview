"""Only the joined topic reaches the LiveView; frames for any other topic are not routed to it."""

from .views import StaticView


async def test_event_on_unjoined_topic_is_rejected_without_reaching_view(connect):
    # Given a client joined to a LiveView
    handled = []

    class Home(StaticView):
        async def handle_event(self, event, payload, socket):
            handled.append(event)

    client = connect({"/": Home})
    await client.join("/")

    # When an event arrives for a topic that was never joined
    reply = await client.event("increment", topic="lv:other")

    # Then it is rejected and never reaches the joined view
    assert reply == {"status": "error", "response": {"reason": "unmatched topic"}}
    assert handled == []


async def test_event_on_unjoined_topic_after_leave_is_rejected_without_reaching_view(connect):
    # Given a client that has left the view it joined
    handled = []

    class Home(StaticView):
        async def handle_event(self, event, payload, socket):
            handled.append(event)

    client = connect({"/": Home})
    await client.join("/")
    await client.leave()

    # When an event arrives for a different topic
    reply = await client.event("increment", topic="lv:other")

    # Then it is rejected and never reaches the closed view
    assert reply == {"status": "error", "response": {"reason": "unmatched topic"}}
    assert handled == []


async def test_leave_on_unjoined_topic_does_not_close_joined_view(connect):
    # Given a client joined to a LiveView
    handled = []
    disconnected = []

    class Home(StaticView):
        async def handle_event(self, event, payload, socket):
            handled.append(event)

        async def disconnect(self, socket):
            disconnected.append("Home")

    client = connect({"/": Home})
    await client.join("/")

    # When a leave arrives for a topic that was never joined
    reply = await client.leave(topic="lv:other")

    # Then it is acknowledged, and the joined view stays open and keeps handling events
    assert reply == {"status": "ok", "response": {}}
    assert disconnected == []
    assert (await client.event("increment"))["status"] == "ok"
    assert handled == ["increment"]
