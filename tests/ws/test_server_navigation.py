"""Navigation started by the server: push_navigate, replace_navigate, redirect, and push_patch."""

from pyview.events import InfoEvent

from .views import StaticView


class Navigator(StaticView):
    """Navigates according to the event it receives."""

    async def handle_event(self, event, payload, socket):
        if event == "push_navigate":
            await socket.push_navigate("/users", {"page": 2})
        elif event == "replace_navigate":
            await socket.replace_navigate("/users")
        elif event == "redirect":
            await socket.redirect("/login", {"next": "/home"})


async def test_push_navigate_tells_client_to_live_navigate(connect):
    # Given a joined view
    client = connect({"/": Navigator})
    await client.join("/")

    # When an event handler calls push_navigate with params
    reply = await client.event("push_navigate")

    # Then the client is told to live-navigate, pushing a history entry
    assert reply["status"] == "ok"
    [push] = client.pushes()
    assert push[3:] == ["live_redirect", {"kind": "push", "to": "/users?page=2"}]


async def test_replace_navigate_tells_client_to_live_navigate_replacing_history(connect):
    # Given a joined view
    client = connect({"/": Navigator})
    await client.join("/")

    # When an event handler calls replace_navigate
    await client.event("replace_navigate")

    # Then the client is told to live-navigate, replacing the history entry
    [push] = client.pushes()
    assert push[3:] == ["live_redirect", {"kind": "replace", "to": "/users"}]


async def test_redirect_tells_client_to_load_page(connect):
    # Given a joined view
    client = connect({"/": Navigator})
    await client.join("/")

    # When an event handler calls redirect with params
    await client.event("redirect")

    # Then the client is told to do a full page load
    [push] = client.pushes()
    assert push[3:] == ["redirect", {"to": "/login?next=%2Fhome"}]


async def test_push_navigate_from_handle_info_tells_client_to_live_navigate(connect):
    # Given a joined view that navigates when a server-side message arrives
    sockets = []

    class Home(StaticView):
        async def mount(self, socket, session):
            await super().mount(socket, session)
            sockets.append(socket)

        async def handle_info(self, event, socket):
            await socket.push_navigate("/users")

    client = connect({"/": Home})
    await client.join("/")

    # When a message is delivered to the view
    await sockets[0].send_info(InfoEvent("logged_out"))

    # Then the client is told to live-navigate
    assert ["live_redirect", {"kind": "push", "to": "/users"}] in [p[3:] for p in client.pushes()]


async def test_push_patch_runs_handle_params_and_tells_client_before_replying(connect):
    # Given a joined view that patches its own URL on an event
    params_seen = []

    class Users(StaticView):
        async def handle_params(self, url, params, socket):
            params_seen.append(params)

        async def handle_event(self, event, payload, socket):
            await socket.push_patch("/users", {"page": 2})

    client = connect({"/users": Users})
    await client.join("/users")

    # When the event handler calls push_patch
    reply = await client.event("next_page")

    # Then handle_params runs with the new params
    assert params_seen[-1].getlist("page") == ["2"]

    # And the client is told to patch the URL before the event reply arrives
    assert reply["status"] == "ok"
    events = [frame[3] for frame in client.websocket.sent]
    assert events[-2:] == ["live_patch", "phx_reply"]
    assert client.websocket.sent[-2][4] == {"kind": "push", "to": "/users?page=2"}


async def test_events_pushed_before_navigating_are_sent_before_the_navigation(connect):
    # Given a joined view that pushes an event to the client and then navigates away
    class Home(StaticView):
        async def handle_event(self, event, payload, socket):
            await socket.push_event("track", {"action": "saved"})
            await socket.push_navigate("/users")

    client = connect({"/": Home})
    await client.join("/")

    # When the event handler runs
    await client.event("save")

    # Then the pushed event reaches the client before the navigation does,
    # since the client stops applying updates to a view once it navigates away
    after_join = client.websocket.sent[1:]
    carries_track = [
        i for i, frame in enumerate(after_join) if ["track", {"action": "saved"}] in _events(frame)
    ]
    navigation = [i for i, frame in enumerate(after_join) if frame[3] == "live_redirect"]
    assert carries_track and navigation
    assert carries_track[0] < navigation[0]


def _events(frame):
    """push_event payloads carried by a diff push or an event reply."""
    payload = frame[4]
    diff = payload if frame[3] == "diff" else payload.get("response", {}).get("diff", {})
    return diff.get("e", [])
