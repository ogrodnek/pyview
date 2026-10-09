from .views import StaticView


async def test_join_on_already_joined_topic_closes_previous_view(connect):
    # Given a client joined to a LiveView
    mounted = []
    disconnected = []

    class Home(StaticView):
        async def mount(self, socket, session):
            await super().mount(socket, session)
            mounted.append(self)

        async def disconnect(self, socket):
            disconnected.append(self)

    client = connect({"/": Home})
    await client.join("/")

    # When the client joins the same topic again without leaving first
    reply = await client.join("/")

    # Then the new view is joined and the previous one is closed
    assert reply["status"] == "ok"
    assert len(mounted) == 2
    assert disconnected == [mounted[0]]


async def test_event_after_live_navigation_reaches_new_view(connect):
    # Given a client that live-navigated from /a to /b (leave the old view, join with `redirect`)
    handled = []

    class PageA(StaticView):
        async def handle_event(self, event, payload, socket):
            handled.append(("PageA", event))

    class PageB(StaticView):
        async def handle_event(self, event, payload, socket):
            handled.append(("PageB", event))

    client = connect({"/a": PageA, "/b": PageB})
    await client.join("/a")
    await client.leave()
    await client.join("/b", redirect=True)

    # When the client sends an event
    reply = await client.event("increment")

    # Then only the new view handles it
    assert reply["status"] == "ok"
    assert handled == [("PageB", "increment")]
