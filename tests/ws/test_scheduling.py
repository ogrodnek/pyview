"""Messages a view schedules for itself are delivered to its handle_info."""

import asyncio
from datetime import timedelta

from apscheduler.triggers.interval import IntervalTrigger

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


def ticking_view(name: str, ticks: list):
    """A view that schedules a repeating "tick" when it mounts and records each one it handles."""

    class Ticking(StaticView):
        async def mount(self, socket, session):
            await super().mount(socket, session)
            socket.schedule_info(InfoEvent("tick"), 0.05)

        async def handle_info(self, event, socket):
            ticks.append(name)

    Ticking.__name__ = name
    return Ticking


async def test_leaving_a_view_stops_its_scheduled_messages(connect):
    # Given a view whose repeating message has started arriving
    ticks = []
    client = connect({"/": ticking_view("Home", ticks)})
    await client.join("/")
    await client.next_push()

    # When the client leaves the view
    await client.leave()
    handled = len(ticks)

    # Then its timer is removed, and no more messages reach it over several intervals
    assert client.handler.scheduler.get_jobs() == []
    await asyncio.sleep(0.2)
    assert len(ticks) == handled


async def test_closing_the_connection_stops_its_scheduled_messages(connect):
    # Given a view whose repeating message has started arriving
    ticks = []
    client = connect({"/": ticking_view("Home", ticks)})
    await client.join("/")
    await client.next_push()

    # When the websocket closes
    await client.disconnect()
    handled = len(ticks)

    # Then its timer is removed, and no more messages reach the view over several intervals
    assert client.handler.scheduler.get_jobs() == []
    await asyncio.sleep(0.2)
    assert len(ticks) == handled


async def test_after_live_navigation_only_the_new_view_gets_scheduled_messages(connect):
    # Given a view whose repeating "tick" has started arriving
    ticks = []
    client = connect(
        {"/": ticking_view("FrontPage", ticks), "/article": ticking_view("Article", ticks)}
    )
    await client.join("/")
    await client.next_push()

    # When the client live-navigates to a view that schedules the same message
    await client.leave()
    navigated_at = len(ticks)
    reply = await client.join("/article", redirect=True)

    # Then the new view mounts, and over several intervals only it gets the message
    assert reply["status"] == "ok"
    await asyncio.sleep(0.2)
    after = ticks[navigated_at:]
    assert after and set(after) == {"Article"}


async def test_scheduling_the_same_event_again_replaces_its_timer(connect):
    # Given a view ticking every 50 ms, which an event switches to every 10 s
    class Ticker(StaticView):
        async def mount(self, socket, session):
            await super().mount(socket, session)
            socket.schedule_info(InfoEvent("tick"), 0.05)

        async def handle_event(self, event, payload, socket):
            socket.schedule_info(InfoEvent("tick"), 10)

    client = connect({"/": Ticker})
    await client.join("/")

    # When the event reschedules the same message
    reply = await client.event("slow_down")

    # Then it succeeds, and the view has one timer: the new one
    assert reply["status"] == "ok"
    [job] = client.handler.scheduler.get_jobs()
    assert isinstance(job.trigger, IntervalTrigger)
    assert job.trigger.interval == timedelta(seconds=10)
    assert job.args == (InfoEvent("tick"),)


async def test_rescheduling_an_event_name_with_a_new_payload_replaces_its_timer(connect):
    # Given a view ticking fast, which an event reschedules under the same name, slowly
    class Ticker(StaticView):
        async def mount(self, socket, session):
            await super().mount(socket, session)
            socket.schedule_info(InfoEvent("tick", {"rate": "fast"}), 0.05)

        async def handle_event(self, event, payload, socket):
            socket.schedule_info(InfoEvent("tick", {"rate": "slow"}), 10)

    client = connect({"/": Ticker})
    await client.join("/")

    # When the event reschedules the message with a different payload
    reply = await client.event("slow_down")

    # Then the view has one timer, with the new payload and interval
    assert reply["status"] == "ok"
    [job] = client.handler.scheduler.get_jobs()
    assert isinstance(job.trigger, IntervalTrigger)
    assert job.trigger.interval == timedelta(seconds=10)
    assert job.args == (InfoEvent("tick", {"rate": "slow"}),)
