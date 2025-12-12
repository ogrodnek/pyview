from dataclasses import dataclass
from typing import TypedDict

from pyview import LiveView, LiveViewSocket, Stream


@dataclass
class Message:
    id: int
    text: str
    color: str = "blue"


class StreamsContext(TypedDict):
    messages: Stream[Message]
    next_id: int


class StreamsDemoLiveView(LiveView[StreamsContext]):
    """
    Streams Demo

    This example demonstrates Phoenix LiveView streams in PyView.
    Watch the websocket diff panel to see how only changed items are sent over the wire.
    """

    async def mount(self, socket: LiveViewSocket[StreamsContext], session):
        # Start with a few messages
        initial_messages = [
            Message(id=1, text="Welcome to streams!", color="green"),
            Message(id=2, text="Click buttons to see stream operations", color="blue"),
            Message(id=3, text="Watch the diff panel below", color="purple"),
        ]

        socket.context = StreamsContext(
            messages=Stream(initial_messages, name="messages"),
            next_id=4,
        )

    async def handle_event(self, event, payload, socket: LiveViewSocket[StreamsContext]):
        ctx = socket.context

        if event == "append":
            msg = Message(id=ctx["next_id"], text=f"Appended message #{ctx['next_id']}", color="blue")
            ctx["messages"].insert(msg, at=-1)
            ctx["next_id"] += 1

        elif event == "prepend":
            msg = Message(id=ctx["next_id"], text=f"Prepended message #{ctx['next_id']}", color="green")
            ctx["messages"].insert(msg, at=0)
            ctx["next_id"] += 1

        elif event == "insert-middle":
            msg = Message(id=ctx["next_id"], text=f"Inserted at position 2 #{ctx['next_id']}", color="purple")
            ctx["messages"].insert(msg, at=2)
            ctx["next_id"] += 1

        elif event == "delete":
            dom_id = payload.get("id")
            if dom_id:
                ctx["messages"].delete_by_id(dom_id)

        elif event == "delete-first":
            # Delete first item by constructing the expected dom_id
            # In a real app you'd track IDs differently
            ctx["messages"].delete_by_id("messages-1")

        elif event == "reset":
            # Reset to new items
            new_messages = [
                Message(id=100, text="Stream was reset!", color="red"),
                Message(id=101, text="All previous items cleared", color="orange"),
            ]
            ctx["messages"].reset(new_messages)
            ctx["next_id"] = 102

        elif event == "clear":
            # Clear all items
            ctx["messages"].reset()

        elif event == "bulk-add":
            # Add multiple items at once
            new_msgs = [
                Message(id=ctx["next_id"], text=f"Bulk item {i+1}", color="teal")
                for i in range(3)
            ]
            for i, msg in enumerate(new_msgs):
                msg.id = ctx["next_id"] + i
            ctx["messages"].insert_many(new_msgs)
            ctx["next_id"] += 3
