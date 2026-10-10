"""The CSRF token is checked once per connection, on its first join.

A connection whose first join fails the check gets a "stale" reply, which the
client handles with a full page load that picks up a fresh token.
"""

from .views import StaticView

STALE = {"status": "error", "response": {"reason": "stale"}}


def recording_view(mounted):
    class Home(StaticView):
        async def mount(self, socket, session):
            await super().mount(socket, session)
            mounted.append(type(self).__name__)

    return Home


async def test_first_join_with_invalid_token_replies_stale(connect):
    # Given a client whose CSRF token does not validate
    mounted = []
    client = connect({"/": recording_view(mounted)})

    # When the client joins
    reply = await client.join("/", params={"_csrf_token": "not-a-valid-token"})

    # Then the join is answered "stale", nothing is mounted, and the websocket stays open
    assert reply == STALE
    assert mounted == []
    assert (await client.heartbeat())["status"] == "ok"


async def test_first_join_without_token_replies_stale(connect):
    # Given a client that sends no CSRF token
    mounted = []
    client = connect({"/": recording_view(mounted)})

    # When the client joins
    reply = await client.join("/", params={})

    # Then the join is answered "stale" and nothing is mounted
    assert reply == STALE
    assert mounted == []


async def test_connection_that_failed_csrf_cannot_join_through_navigation(connect):
    # Given a connection whose first join failed the CSRF check
    mounted = []
    client = connect({"/": recording_view(mounted), "/other": recording_view(mounted)})
    await client.join("/", params={"_csrf_token": "not-a-valid-token"})

    # When it tries a navigation join, which is not checked on a validated connection
    reply = await client.join("/other", redirect=True, params={"_csrf_token": "not-a-valid-token"})

    # Then it is also answered "stale" and nothing is mounted
    assert reply == STALE
    assert mounted == []


async def test_navigation_join_on_validated_connection_does_not_recheck_token(connect):
    # Given a connection whose first join passed the CSRF check
    mounted = []
    client = connect({"/": recording_view(mounted), "/other": recording_view(mounted)})
    await client.join("/")
    await client.leave()

    # When it navigates with a token that no longer validates (as after it expires
    # on a page left open)
    reply = await client.join("/other", redirect=True, params={"_csrf_token": "not-a-valid-token"})

    # Then the navigation still succeeds
    assert reply["status"] == "ok"
    assert mounted == ["Home", "Home"]
