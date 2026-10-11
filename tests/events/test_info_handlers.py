"""@info handlers: BaseEventHandler.handle_info routes each message to the method marked for its name."""

from pyview.events import BaseEventHandler, InfoEvent, info

SOCKET = object()


class Clock(BaseEventHandler):
    def __init__(self):
        self.handled = []

    @info("tick")
    async def handle_tick(self, event, socket):
        self.handled.append(("tick", event, socket))

    @info("pause", "stop")
    async def handle_halt(self, event, socket):
        self.handled.append(("halt", event, socket))


async def test_message_goes_to_the_handler_for_its_name():
    # Given a view with an @info handler for "tick"
    clock = Clock()

    # When a "tick" message arrives
    await clock.handle_info(InfoEvent("tick", 1), SOCKET)

    # Then that handler gets the message and the socket
    assert clock.handled == [("tick", InfoEvent("tick", 1), SOCKET)]


async def test_one_handler_can_take_several_names():
    # Given a view with one @info handler for both "pause" and "stop"
    clock = Clock()

    # When a message for each name arrives
    await clock.handle_info(InfoEvent("pause"), SOCKET)
    await clock.handle_info(InfoEvent("stop"), SOCKET)

    # Then the same handler gets both
    assert clock.handled == [
        ("halt", InfoEvent("pause"), SOCKET),
        ("halt", InfoEvent("stop"), SOCKET),
    ]


async def test_message_with_no_handler_is_ignored():
    # Given a view with no @info handler for "alarm"
    clock = Clock()

    # When an "alarm" message arrives, nothing is raised and no handler runs
    await clock.handle_info(InfoEvent("alarm"), SOCKET)
    assert clock.handled == []


async def test_subclass_inherits_handlers_and_can_replace_one():
    # Given a subclass that replaces the "tick" handler and adds one for "reset"
    class StopWatch(Clock):
        @info("tick")
        async def handle_tick(self, event, socket):
            self.handled.append(("stopwatch tick", event, socket))

        @info("reset")
        async def handle_reset(self, event, socket):
            self.handled.append(("reset", event, socket))

    watch = StopWatch()

    # When messages for a replaced, an added, and an inherited name arrive
    await watch.handle_info(InfoEvent("tick"), SOCKET)
    await watch.handle_info(InfoEvent("reset"), SOCKET)
    await watch.handle_info(InfoEvent("stop"), SOCKET)

    # Then each goes to the subclass's handler for that name
    assert watch.handled == [
        ("stopwatch tick", InfoEvent("tick"), SOCKET),
        ("reset", InfoEvent("reset"), SOCKET),
        ("halt", InfoEvent("stop"), SOCKET),
    ]


async def test_subclass_handlers_do_not_leak_into_the_parent():
    # Given a subclass with its own "reset" handler
    class StopWatch(Clock):
        @info("reset")
        async def handle_reset(self, event, socket):
            self.handled.append(("reset", event, socket))

    # When a "reset" message reaches the parent view
    clock = Clock()
    await clock.handle_info(InfoEvent("reset"), SOCKET)

    # Then the parent has no handler for it
    assert clock.handled == []


async def test_bare_info_handles_the_methods_own_name():
    # Given a view whose handler is marked with @info and no name, as @event allows
    class Clock(BaseEventHandler):
        def __init__(self):
            self.handled = []

        @info
        async def tick(self, event, socket):
            self.handled.append(event)

    # When a message named after the method arrives
    clock = Clock()
    await clock.handle_info(InfoEvent("tick"), SOCKET)

    # Then that method handles it
    assert clock.handled == [InfoEvent("tick")]


async def test_info_with_empty_parentheses_handles_the_methods_own_name():
    # Given a view whose handler is marked with @info() and no name
    class Clock(BaseEventHandler):
        def __init__(self):
            self.handled = []

        @info()
        async def tick(self, event, socket):
            self.handled.append(event)

    # When a message named after the method arrives
    clock = Clock()
    await clock.handle_info(InfoEvent("tick"), SOCKET)

    # Then that method handles it
    assert clock.handled == [InfoEvent("tick")]
