"""Replies to the client's housekeeping messages: heartbeats and component cleanup."""

from .views import StaticView


async def test_heartbeat_is_acknowledged_on_phoenix_topic(connect):
    # Given a client joined to a LiveView
    client = connect({"/": StaticView})
    await client.join("/")

    # When the client sends a heartbeat
    reply = await client.heartbeat()

    # Then it is acknowledged on the "phoenix" topic, outside any join
    assert reply == {"status": "ok", "response": {}}
    join_ref, _, topic, event, _ = client.websocket.sent[-1]
    assert (join_ref, topic, event) == (None, "phoenix", "phx_reply")


async def test_heartbeat_does_not_reach_view(connect):
    # Given a client joined to a LiveView
    handled = []

    class Home(StaticView):
        async def handle_event(self, event, payload, socket):
            handled.append(event)

    client = connect({"/": Home})
    await client.join("/")

    # When the client sends a heartbeat
    await client.heartbeat()

    # Then the view is not involved and nothing is pushed
    assert handled == []
    assert client.pushes() == []


async def test_cids_will_destroy_is_acknowledged(connect):
    # Given a client joined to a LiveView
    client = connect({"/": StaticView})
    await client.join("/")

    # When the client reports components about to be removed from the page
    reply = await client.push("cids_will_destroy", {"cids": [1, 2]})

    # Then it is acknowledged with an empty response
    assert reply == {"status": "ok", "response": {}}


async def test_cids_destroyed_replies_with_the_destroyed_cids(connect):
    # Given a client joined to a LiveView
    client = connect({"/": StaticView})
    await client.join("/")

    # When the client reports components removed from the page
    reply = await client.push("cids_destroyed", {"cids": [1, 2]})

    # Then the reply lists the cids, so the client can drop them from its render cache
    assert reply == {"status": "ok", "response": {"cids": [1, 2]}}
