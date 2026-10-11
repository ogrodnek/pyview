"""LiveView streams over the websocket: what the client receives as a stream's items change."""

from dataclasses import dataclass

from pyview.live_socket import is_connected
from pyview.live_view import LiveView
from pyview.stream import Stream
from pyview.template.live_template import LiveRender, LiveTemplate
from pyview.vendor.ibis import Template

CHAT = LiveTemplate(
    Template(
        "<h1>{{ title }}</h1>"
        '<ul id="messages" phx-update="stream">'
        "{% for dom_id, message in messages %}"
        '<li id="{{ dom_id }}">{{ message.text }}</li>'
        "{% endfor %}"
        "</ul>"
    )
)


@dataclass
class Message:
    id: int
    text: str


@dataclass
class Chat:
    title: str
    messages: Stream[Message]


def chat_view(initial: list[Message]):
    """A chat that renders its messages as a stream, starting with `initial`.

    Events change the stream ("send", "delete", "reset"), change only the title ("rename"),
    or post a message to every chat subscribed to the "stream-chat" pubsub topic ("post").
    """

    class ChatView(LiveView[Chat]):
        async def mount(self, socket, session):
            socket.context = Chat(title="Chat", messages=Stream(initial, name="messages"))
            if is_connected(socket):
                await socket.subscribe("stream-chat")

        async def handle_event(self, event, payload, socket):
            messages = socket.context.messages
            if event == "send":
                message = Message(payload["id"], payload["text"])
                messages.insert(message, at=payload.get("at", -1), limit=payload.get("limit"))
            elif event == "delete":
                messages.delete_by_id(f"messages-{payload['id']}")
            elif event == "reset":
                messages.reset([Message(m["id"], m["text"]) for m in payload["messages"]])
            elif event == "rename":
                socket.context.title = payload["title"]
            elif event == "post":
                await socket.broadcast("stream-chat", Message(payload["id"], payload["text"]))

        async def handle_info(self, event, socket):
            socket.context.messages.insert(event.payload)

        async def render(self, assigns, meta):
            return LiveRender(CHAT, assigns, meta)

    return ChatView


async def test_join_reply_has_the_streams_initial_items(connect):
    # Given a view that starts its stream with two messages
    client = connect({"/": chat_view([Message(1, "hi"), Message(2, "hello")])})

    # When the client joins
    reply = await client.join("/")

    # Then the stream's comprehension has each item, and the inserts that place them
    assert reply["response"]["rendered"]["1"] == {
        "s": ['<li id="', '">', "</li>"],
        "d": [["messages-1", "hi"], ["messages-2", "hello"]],
        "stream": ["messages", [["messages-1", -1, None], ["messages-2", -1, None]], []],
    }


async def test_insert_sends_only_the_new_item(connect):
    # Given a joined view whose stream has two messages
    client = connect({"/": chat_view([Message(1, "hi"), Message(2, "hello")])})
    await client.join("/")

    # When an event inserts a third
    reply = await client.event("send", {"id": 3, "text": "hey"})

    # Then the diff has only the new item and its insert, without the statics again
    assert reply["response"]["diff"] == {
        "1": {
            "d": [["messages-3", "hey"]],
            "stream": ["messages", [["messages-3", -1, None]], []],
        }
    }


async def test_insert_position_and_limit_are_sent_as_given(connect):
    # Given a joined view with one message
    client = connect({"/": chat_view([Message(1, "hi")])})
    await client.join("/")

    # When an event prepends a message, keeping at most the last ten
    reply = await client.event("send", {"id": 2, "text": "first!", "at": 0, "limit": -10})

    # Then the insert carries the position and the limit for the client to apply
    assert reply["response"]["diff"]["1"]["stream"] == ["messages", [["messages-2", 0, -10]], []]


async def test_delete_sends_only_the_delete(connect):
    # Given a joined view whose stream has two messages
    client = connect({"/": chat_view([Message(1, "hi"), Message(2, "hello")])})
    await client.join("/")

    # When an event deletes the first
    reply = await client.event("delete", {"id": 1})

    # Then the diff has only the delete, with no items
    assert reply["response"]["diff"] == {"1": {"stream": ["messages", [], ["messages-1"]]}}


async def test_reset_sends_the_new_items_with_the_reset_flag(connect):
    # Given a joined view whose stream has two messages
    client = connect({"/": chat_view([Message(1, "hi"), Message(2, "hello")])})
    await client.join("/")

    # When an event resets the stream to a single new message
    reply = await client.event("reset", {"messages": [{"id": 5, "text": "fresh start"}]})

    # Then the diff has the new item, and the stream ends with the flag that clears the old ones
    assert reply["response"]["diff"] == {
        "1": {
            "d": [["messages-5", "fresh start"]],
            "stream": ["messages", [["messages-5", -1, None]], [], True],
        }
    }


async def test_change_outside_the_stream_leaves_the_stream_out_of_the_diff(connect):
    # Given a joined view whose stream has two messages
    client = connect({"/": chat_view([Message(1, "hi"), Message(2, "hello")])})
    await client.join("/")

    # When an event changes only the title
    reply = await client.event("rename", {"title": "Team chat"})

    # Then the diff has only the title; the client keeps the items it already has
    assert reply["response"]["diff"] == {"0": "Team chat"}


async def test_insert_after_a_change_outside_the_stream_sends_the_new_item(connect):
    # Given a joined view whose last change didn't touch the stream
    client = connect({"/": chat_view([Message(1, "hi")])})
    await client.join("/")
    await client.event("rename", {"title": "Team chat"})

    # When an event inserts a message
    reply = await client.event("send", {"id": 2, "text": "hello"})

    # Then the diff has the new item and its insert
    stream_diff = reply["response"]["diff"]["1"]
    assert stream_diff["d"] == [["messages-2", "hello"]]
    assert stream_diff["stream"] == ["messages", [["messages-2", -1, None]], []]


async def test_insert_from_a_broadcast_is_pushed_to_the_client(connect):
    # Given two joined chats subscribed to the same pubsub topic
    sender = connect({"/": chat_view([])}, topic="lv:phx-sender")
    reader = connect({"/": chat_view([])}, topic="lv:phx-reader")
    await sender.join("/")
    await reader.join("/")

    # When one chat posts a message that each chat inserts in its handle_info
    await sender.event("post", {"id": 1, "text": "hi all"})

    # Then the other chat's client is pushed a diff with the new item
    push = await reader.next_push()
    assert push.event == "diff"
    assert push.payload == {
        "1": {
            "s": ['<li id="', '">', "</li>"],
            "d": [["messages-1", "hi all"]],
            "stream": ["messages", [["messages-1", -1, None]], []],
        }
    }
