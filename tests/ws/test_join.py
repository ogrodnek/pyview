import pytest

from pyview.csrf import generate_csrf_token

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


async def test_mount_receives_the_session_the_page_was_rendered_with(connect):
    # Given a view that records the session it mounts with
    sessions = []

    class Home(StaticView):
        async def mount(self, socket, session):
            await super().mount(socket, session)
            sessions.append(session)

    client = connect({"/": Home})

    # When the client joins with the signed session from the page
    await client.join("/", session={"user_id": 42})

    # Then mount gets that session
    assert sessions == [{"user_id": 42}]


async def test_navigation_join_passes_the_session_to_the_new_view(connect):
    # Given a client that navigates from one view to another
    sessions = []

    class PageA(StaticView):
        pass

    class PageB(StaticView):
        async def mount(self, socket, session):
            await super().mount(socket, session)
            sessions.append(session)

    client = connect({"/a": PageA, "/b": PageB})
    await client.join("/a", session={"user_id": 42})
    await client.leave()

    # When it joins the new view with the signed session
    await client.join("/b", redirect=True, session={"user_id": 42})

    # Then the new view's mount gets that session
    assert sessions == [{"user_id": 42}]


async def test_message_before_the_first_join_is_unmatched_and_connection_stays_open(connect):
    # Given a new connection that hasn't joined a view yet
    client = connect({"/": StaticView})

    # When the client sends an event before joining
    reply = await client.event("increment")

    # Then it is answered "unmatched topic", and a join afterwards still works
    assert reply == {"status": "error", "response": {"reason": "unmatched topic"}}
    assert (await client.join("/"))["status"] == "ok"


async def test_first_join_can_use_redirect_instead_of_url(connect):
    # Given a new connection, as when a browser reconnects after a live navigation
    client = connect({"/": StaticView})

    # When its first join names the page with `redirect` rather than `url`
    reply = await client.join("/", redirect=True)

    # Then the view is joined and rendered
    assert reply["status"] == "ok"
    assert "rendered" in reply["response"]


async def test_join_without_url_or_redirect_closes_the_connection(connect):
    # Given a new connection
    client = connect({"/": StaticView})

    # When its join names no page at all
    with pytest.raises(AssertionError, match="without replying"):
        await client.push(
            "phx_join", {"params": {"_csrf_token": generate_csrf_token(client.topic)}}
        )

    # Then the websocket is closed, without a reply
    assert client.websocket.closed
