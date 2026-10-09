"""Events queued with push_event are delivered with the render that follows them."""

from .views import StaticView


class Chart(StaticView):
    """Pushes initial data to a client-side hook when mounted."""

    async def mount(self, socket, session):
        await super().mount(socket, session)
        await socket.push_event("init_chart", {"points": [1, 2, 3]})


async def test_events_pushed_in_mount_are_sent_in_join_reply(connect):
    # Given a view that pushes an event when mounted
    client = connect({"/": Chart})

    # When the client joins
    reply = await client.join("/")

    # Then the event is in the rendered join reply
    assert reply["response"]["rendered"]["e"] == [["init_chart", {"points": [1, 2, 3]}]]

    # And it is not sent again with the next reply
    assert "e" not in (await client.event("click"))["response"]["diff"]


async def test_events_pushed_in_handle_params_on_join_are_sent_in_join_reply(connect):
    # Given a view that pushes an event from handle_params
    class Users(StaticView):
        async def handle_params(self, url, params, socket):
            await socket.push_event("page_changed", {"page": 1})

    client = connect({"/users": Users})

    # When the client joins
    reply = await client.join("/users")

    # Then the event is in the rendered join reply
    assert reply["response"]["rendered"]["e"] == [["page_changed", {"page": 1}]]


async def test_events_pushed_in_mount_are_sent_in_navigation_join_reply(connect):
    # Given a client that live-navigates to a view that pushes an event when mounted
    client = connect({"/": StaticView, "/chart": Chart})
    await client.join("/")
    await client.leave()

    # When the client joins the new view
    reply = await client.join("/chart", redirect=True)

    # Then the event is in the rendered join reply
    assert reply["response"]["rendered"]["e"] == [["init_chart", {"points": [1, 2, 3]}]]
