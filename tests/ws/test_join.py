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
