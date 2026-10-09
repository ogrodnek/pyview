"""A join that fails is answered with an error reply, and the websocket stays open."""

import logging

from .views import StaticView

JOIN_CRASHED = {"status": "error", "response": {"reason": "join crashed"}}


async def test_mount_error_replies_join_crashed_and_keeps_connection_open(connect, caplog):
    # Given a view whose mount raises
    disconnected = []

    class Broken(StaticView):
        async def mount(self, socket, session):
            await super().mount(socket, session)
            raise RuntimeError("mount failed")

        async def disconnect(self, socket):
            disconnected.append("Broken")

    client = connect({"/": Broken})

    # When the client joins
    with caplog.at_level(logging.ERROR):
        reply = await client.join("/")

    # Then the join is answered with an error the client handles by reloading the page
    assert reply == JOIN_CRASHED

    # And the error is logged with its traceback
    assert any(r.exc_info and "mount failed" in str(r.exc_info[1]) for r in caplog.records)

    # And the partially mounted view is closed
    assert disconnected == ["Broken"]

    # And the websocket stays open
    assert (await client.heartbeat())["status"] == "ok"


async def test_handle_params_error_on_join_replies_join_crashed(connect):
    # Given a view whose handle_params raises
    class Broken(StaticView):
        async def handle_params(self, url, params, socket):
            raise RuntimeError("handle_params failed")

    client = connect({"/": Broken})

    # When the client joins
    reply = await client.join("/")

    # Then the join is answered with an error and the websocket stays open
    assert reply == JOIN_CRASHED
    assert (await client.heartbeat())["status"] == "ok"


async def test_mount_error_on_navigation_join_replies_join_crashed(connect):
    # Given a client navigating to a view whose mount raises
    class Broken(StaticView):
        async def mount(self, socket, session):
            await super().mount(socket, session)
            raise RuntimeError("mount failed")

    client = connect({"/": StaticView, "/broken": Broken})
    await client.join("/")
    await client.leave()

    # When the client joins the new view
    reply = await client.join("/broken", redirect=True)

    # Then the join is answered with an error and the websocket stays open
    assert reply == JOIN_CRASHED
    assert (await client.heartbeat())["status"] == "ok"
