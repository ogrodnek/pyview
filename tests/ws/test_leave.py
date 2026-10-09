from .views import StaticView


async def test_leave_replies_ok_and_closes_view(connect):
    # Given a client joined to a LiveView
    disconnected = []

    class Home(StaticView):
        async def disconnect(self, socket):
            disconnected.append("Home")

    client = connect({"/": Home})
    await client.join("/")

    # When the client leaves the view
    reply = await client.leave()

    # Then the leave is acknowledged and the view is closed
    assert reply == {"status": "ok", "response": {}}
    assert disconnected == ["Home"]


async def test_event_after_leave_is_rejected_without_reaching_view(connect):
    # Given a client that has left the view it joined
    handled = []

    class Home(StaticView):
        async def handle_event(self, event, payload, socket):
            handled.append(event)

    client = connect({"/": Home})
    await client.join("/")
    await client.leave()

    # When the client sends an event to the view it left
    reply = await client.event("increment")

    # Then the event is rejected and never reaches the closed view
    assert reply == {"status": "error", "response": {"reason": "unmatched topic"}}
    assert handled == []
