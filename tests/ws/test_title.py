"""Page title changes are sent to the client in the "t" key of a render."""

from pyview.events import InfoEvent

from .views import StaticView


async def test_title_set_in_mount_is_sent_in_join_reply(connect):
    # Given a view that sets its title when mounted
    class Home(StaticView):
        async def mount(self, socket, session):
            await super().mount(socket, session)
            socket.live_title = "Home"

    client = connect({"/": Home})

    # When the client joins
    reply = await client.join("/")

    # Then the title is in the rendered join reply
    assert reply["response"]["rendered"]["t"] == "Home"


async def test_title_set_in_handle_event_is_sent_in_event_reply(connect):
    # Given a joined view that changes its title when an event arrives
    class Home(StaticView):
        async def handle_event(self, event, payload, socket):
            socket.live_title = "Updated"

    client = connect({"/": Home})
    await client.join("/")

    # When the client sends an event
    reply = await client.event("rename")

    # Then the new title is in the event reply's diff
    assert reply["response"]["diff"]["t"] == "Updated"


async def test_title_is_not_resent_when_unchanged(connect):
    # Given a joined view whose title was set by an earlier event
    class Home(StaticView):
        async def handle_event(self, event, payload, socket):
            if event == "rename":
                socket.live_title = "Updated"

    client = connect({"/": Home})
    await client.join("/")
    await client.event("rename")

    # When an event arrives that does not touch the title
    reply = await client.event("noop")

    # Then the reply has no title
    assert "t" not in reply["response"]["diff"]


async def test_title_set_in_handle_params_is_sent_in_live_patch_reply(connect):
    # Given a joined view that titles itself from its query params
    class Users(StaticView):
        async def handle_params(self, url, params, socket):
            page = params.get("page", ["1"])[0]
            socket.live_title = f"Users - Page {page}"

    client = connect({"/users": Users})
    await client.join("/users")

    # When the client patches to another page
    reply = await client.live_patch("/users?page=2")

    # Then the new title is in the live_patch reply's diff
    assert reply["response"]["diff"]["t"] == "Users - Page 2"


async def test_title_set_in_handle_info_is_sent_in_diff_push(connect):
    # Given a joined view that changes its title on a server-side message
    sockets = []

    class Inbox(StaticView):
        async def mount(self, socket, session):
            await super().mount(socket, session)
            sockets.append(socket)

        async def handle_info(self, event, socket):
            socket.live_title = "(1) Inbox"

    client = connect({"/": Inbox})
    await client.join("/")

    # When a message is delivered to the view (as from pubsub or a scheduled job)
    await sockets[0].send_info(InfoEvent("new_message"))

    # Then the new title is in the diff pushed to the client
    [push] = client.pushes()
    assert push[3] == "diff"
    assert push[4]["t"] == "(1) Inbox"
