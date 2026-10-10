"""Messages a view schedules for itself are delivered to its handle_info."""

import asyncio

from pyview.events import InfoEvent

from .views import StaticView, TextRendered


async def test_schedule_info_once_delivers_one_message(connect):
    # Given a view that schedules a single message for itself when it mounts
    received = []

    class Reminder(StaticView):
        async def mount(self, socket, session):
            socket.context = {"text": ""}
            socket.schedule_info_once(InfoEvent("remind", "time to stretch"), 0.05)

        async def handle_info(self, event, socket):
            received.append(event)
            socket.context["text"] = event.payload

        async def render(self, assigns, meta):
            return TextRendered(assigns["text"])

    client = connect({"/": Reminder})

    # When the client joins and the delay passes
    await client.join("/")
    push = await client.next_push()

    # Then the view handles the message and its client gets the change
    assert received == [InfoEvent("remind", "time to stretch")]
    assert push.event == "diff"
    assert push.payload == {"0": "time to stretch"}

    # And nothing more arrives after several more delays
    await asyncio.sleep(0.2)
    assert received == [InfoEvent("remind", "time to stretch")]
    assert len(client.pushes()) == 1


async def test_schedule_info_delivers_repeatedly(connect):
    # Given a view that schedules a repeating message for itself when it mounts
    class Ticker(StaticView):
        async def mount(self, socket, session):
            socket.context = {"ticks": 0}
            socket.schedule_info(InfoEvent("tick"), 0.05)

        async def handle_info(self, event, socket):
            socket.context["ticks"] += 1

        async def render(self, assigns, meta):
            return TextRendered(str(assigns["ticks"]))

    client = connect({"/": Ticker})

    # When the client joins and two intervals pass
    await client.join("/")
    first = await client.next_push()
    second = await client.next_push()

    # Then the view handled the message twice, and its client got each change
    assert (first.event, first.payload) == ("diff", {"0": "1"})
    assert (second.event, second.payload) == ("diff", {"0": "2"})
