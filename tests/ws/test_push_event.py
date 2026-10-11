"""Events queued with push_event are delivered with the render that follows them."""

from pyview.events import InfoEvent

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


def ticking_view(sockets: list, pushes: bool):
    """A view that, on each message, pushes a "tick" event to its hook if `pushes`."""

    class Ticking(StaticView):
        async def mount(self, socket, session):
            await super().mount(socket, session)
            sockets.append(socket)

        async def handle_info(self, event, socket):
            if pushes:
                await socket.push_event("tick", {"count": 1})

    return Ticking


async def test_events_pushed_in_handle_info_are_sent_in_the_pushed_diff(connect):
    # Given a joined view that pushes an event when a server-side message arrives
    sockets = []
    client = connect({"/": ticking_view(sockets, pushes=True)})
    await client.join("/")

    # When a message is delivered to the view
    await sockets[0].send_info(InfoEvent("tick"))

    # Then the pushed diff carries the event
    push = await client.next_push()
    assert push.event == "diff"
    assert push.payload["e"] == [["tick", {"count": 1}]]


async def test_events_pushed_in_handle_info_are_not_sent_again(connect):
    # Given a view whose pushed event was already delivered with a handle_info diff
    sockets = []
    client = connect({"/": ticking_view(sockets, pushes=True)})
    await client.join("/")
    await sockets[0].send_info(InfoEvent("tick"))
    await client.next_push()

    # When the client sends an event that pushes nothing
    reply = await client.event("click")

    # Then the earlier event isn't repeated
    assert "e" not in reply["response"]["diff"]


async def test_pushed_diff_has_no_events_when_none_were_pushed(connect):
    # Given a joined view that pushes nothing when a server-side message arrives
    sockets = []
    client = connect({"/": ticking_view(sockets, pushes=False)})
    await client.join("/")

    # When a message is delivered to the view
    await sockets[0].send_info(InfoEvent("tick"))

    # Then the pushed diff has no events key
    push = await client.next_push()
    assert push.event == "diff"
    assert "e" not in push.payload
