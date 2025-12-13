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
    update_count: int


class StreamsDemoLiveView(LiveView[StreamsContext]):
    """
    Streams Demo

    This example demonstrates Phoenix LiveView streams in PyView.
    Streams efficiently send only changed items over the websocket.
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
            update_count=0,
        )

    async def handle_event(self, event, payload, socket: LiveViewSocket[StreamsContext]):
        ctx = socket.context

        if event == "append":
            msg = Message(
                id=ctx["next_id"], text=f"Appended message #{ctx['next_id']}", color="blue"
            )
            ctx["messages"].insert(msg, at=-1)
            ctx["next_id"] += 1

        elif event == "prepend":
            msg = Message(
                id=ctx["next_id"], text=f"Prepended message #{ctx['next_id']}", color="green"
            )
            ctx["messages"].insert(msg, at=0)
            ctx["next_id"] += 1

        elif event == "insert-middle":
            msg = Message(
                id=ctx["next_id"], text=f"Inserted at position 2 #{ctx['next_id']}", color="purple"
            )
            ctx["messages"].insert(msg, at=2)
            ctx["next_id"] += 1

        elif event == "delete":
            dom_id = payload.get("id")
            if dom_id:
                ctx["messages"].delete_by_id(dom_id)

        elif event == "update-first":
            # Update the first message (id=1) with new text
            # Re-inserting with the same ID updates the existing element in place
            ctx["update_count"] += 1
            updated_msg = Message(
                id=1, text=f"Updated {ctx['update_count']} time(s)!", color="amber"
            )
            ctx["messages"].insert(updated_msg)

        elif event == "bulk-add":
            # Add multiple items at once
            new_msgs = [
                Message(id=ctx["next_id"], text=f"Bulk item {i + 1}", color="teal")
                for i in range(3)
            ]
            for i, msg in enumerate(new_msgs):
                msg.id = ctx["next_id"] + i
            ctx["messages"].insert_many(new_msgs)
            ctx["next_id"] += 3

        elif event == "reset":
            # Reset the stream - clears all items and replaces with fresh set
            fresh_msgs = [
                Message(id=ctx["next_id"], text="Fresh start!", color="green"),
                Message(id=ctx["next_id"] + 1, text="Stream was reset", color="blue"),
            ]
            ctx["messages"].reset(fresh_msgs)
            ctx["next_id"] += 2
