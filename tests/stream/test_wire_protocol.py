"""Tests for Phoenix LiveView wire protocol compatibility."""

from dataclasses import dataclass
from pyview import Stream
from pyview.live_socket import ConnectedLiveViewSocket
from unittest.mock import Mock
import pytest


@dataclass
class Message:
    id: int
    text: str
    user: str


@dataclass
class User:
    id: int
    name: str


@dataclass
class ChatContext:
    messages: Stream[Message]
    users: Stream[User]


# ============================================================================
# Complete Wire Format Tests
# ============================================================================

def test_wire_format_insert_operation():
    """Test complete wire format for an insert operation."""
    websocket = Mock()
    socket = ConnectedLiveViewSocket(
        websocket=websocket,
        topic="test",
        liveview=Mock(),
        scheduler=Mock(),
        instrumentation=Mock()
    )

    messages_stream = Stream[Message](dom_id=lambda m: f"msg-{m.id}")
    new_msg = Message(id=42, text="Hello World", user="Alice")
    messages_stream.prepend(new_msg)

    socket.context = ChatContext(
        messages=messages_stream,
        users=Stream[User](dom_id="id")
    )

    render = {"s": ["<div>", "</div>"], "0": "content"}
    diff = socket.diff(render)

    # Verify wire format structure
    assert "stream" in diff
    assert isinstance(diff["stream"], list)
    assert len(diff["stream"]) == 1

    # Verify stream operation structure
    ref, inserts, deletes, reset = diff["stream"][0]

    assert ref.startswith("phx-")
    assert len(inserts) == 1
    assert len(deletes) == 0
    assert reset is False

    # Verify insert entry
    dom_id, at, limit, update_only = inserts[0]
    assert dom_id == "msg-42"
    assert at == 0  # prepend
    assert limit == -1
    assert update_only is False


def test_wire_format_delete_operation():
    """Test complete wire format for a delete operation."""
    websocket = Mock()
    socket = ConnectedLiveViewSocket(
        websocket=websocket,
        topic="test",
        liveview=Mock(),
        scheduler=Mock(),
        instrumentation=Mock()
    )

    messages_stream = Stream[Message](dom_id=lambda m: f"msg-{m.id}")
    messages_stream.remove_by_id("msg-42")
    messages_stream.remove_by_id("msg-43")

    socket.context = ChatContext(
        messages=messages_stream,
        users=Stream[User](dom_id="id")
    )

    render = {"s": ["<div>", "</div>"], "0": "content"}
    diff = socket.diff(render)

    ref, inserts, deletes, reset = diff["stream"][0]

    assert len(inserts) == 0
    assert len(deletes) == 2
    assert "msg-42" in deletes
    assert "msg-43" in deletes
    assert reset is False


def test_wire_format_reset_operation():
    """Test complete wire format for a reset operation."""
    websocket = Mock()
    socket = ConnectedLiveViewSocket(
        websocket=websocket,
        topic="test",
        liveview=Mock(),
        scheduler=Mock(),
        instrumentation=Mock()
    )

    messages_stream = Stream[Message](dom_id=lambda m: f"msg-{m.id}")
    new_messages = [
        Message(id=1, text="First", user="Alice"),
        Message(id=2, text="Second", user="Bob"),
    ]
    messages_stream.reset(new_messages)

    socket.context = ChatContext(
        messages=messages_stream,
        users=Stream[User](dom_id="id")
    )

    render = {"s": ["<div>", "</div>"], "0": "content"}
    diff = socket.diff(render)

    ref, inserts, deletes, reset = diff["stream"][0]

    assert len(inserts) == 2
    assert len(deletes) == 0
    assert reset is True


def test_wire_format_mixed_operations():
    """Test wire format with mixed insert and delete operations."""
    websocket = Mock()
    socket = ConnectedLiveViewSocket(
        websocket=websocket,
        topic="test",
        liveview=Mock(),
        scheduler=Mock(),
        instrumentation=Mock()
    )

    messages_stream = Stream[Message](dom_id=lambda m: f"msg-{m.id}")

    # Mix of operations
    messages_stream.insert(Message(id=1, text="New", user="Alice"), at=0)
    messages_stream.remove_by_id("msg-99")
    messages_stream.insert(Message(id=2, text="Another", user="Bob"), at=-1)

    socket.context = ChatContext(
        messages=messages_stream,
        users=Stream[User](dom_id="id")
    )

    render = {"s": ["<div>", "</div>"], "0": "content"}
    diff = socket.diff(render)

    ref, inserts, deletes, reset = diff["stream"][0]

    assert len(inserts) == 2
    assert len(deletes) == 1
    assert "msg-99" in deletes
    assert reset is False


def test_wire_format_multiple_streams():
    """Test wire format with multiple streams in one diff."""
    websocket = Mock()
    socket = ConnectedLiveViewSocket(
        websocket=websocket,
        topic="test",
        liveview=Mock(),
        scheduler=Mock(),
        instrumentation=Mock()
    )

    messages_stream = Stream[Message](dom_id=lambda m: f"msg-{m.id}")
    messages_stream.insert(Message(id=1, text="Hello", user="Alice"))

    users_stream = Stream[User](dom_id=lambda u: f"user-{u.id}")
    users_stream.insert(User(id=1, name="Alice"))

    socket.context = ChatContext(
        messages=messages_stream,
        users=users_stream
    )

    render = {"s": ["<div>", "</div>"], "0": "content"}
    diff = socket.diff(render)

    assert "stream" in diff
    assert len(diff["stream"]) == 2

    # Check both streams are present
    refs = [op[0] for op in diff["stream"]]
    assert messages_stream.ref in refs
    assert users_stream.ref in refs


# ============================================================================
# Phoenix Compatibility Tests
# ============================================================================

def test_phoenix_insert_tuple_structure():
    """Test that insert tuples match Phoenix LiveView structure exactly."""
    websocket = Mock()
    socket = ConnectedLiveViewSocket(
        websocket=websocket,
        topic="test",
        liveview=Mock(),
        scheduler=Mock(),
        instrumentation=Mock()
    )

    messages_stream = Stream[Message](dom_id="id")
    msg = Message(id=42, text="Test", user="Alice")
    messages_stream.insert(msg, at=5, limit=100, update_only=True)

    socket.context = ChatContext(
        messages=messages_stream,
        users=Stream[User](dom_id="id")
    )

    render = {"s": [], "0": ""}
    diff = socket.diff(render)

    ref, inserts, deletes, reset = diff["stream"][0]
    insert_entry = inserts[0]

    # Phoenix format: [dom_id, at, limit, update_only]
    assert len(insert_entry) == 4
    assert insert_entry[0] == "42"  # dom_id
    assert insert_entry[1] == 5     # at
    assert insert_entry[2] == 100   # limit
    assert insert_entry[3] is True  # update_only


def test_phoenix_stream_array_structure():
    """Test that stream array matches Phoenix LiveView structure exactly."""
    websocket = Mock()
    socket = ConnectedLiveViewSocket(
        websocket=websocket,
        topic="test",
        liveview=Mock(),
        scheduler=Mock(),
        instrumentation=Mock()
    )

    messages_stream = Stream[Message](dom_id="id")
    messages_stream.insert(Message(id=1, text="Test", user="Alice"))
    messages_stream.remove_by_id("msg-2")

    socket.context = ChatContext(
        messages=messages_stream,
        users=Stream[User](dom_id="id")
    )

    render = {"s": [], "0": ""}
    diff = socket.diff(render)

    stream_op = diff["stream"][0]

    # Phoenix format: [ref, inserts, deleteIds, reset]
    assert len(stream_op) == 4
    assert isinstance(stream_op[0], str)   # ref
    assert isinstance(stream_op[1], list)  # inserts
    assert isinstance(stream_op[2], list)  # deleteIds
    assert isinstance(stream_op[3], bool)  # reset


def test_phoenix_stream_key_name():
    """Test that the stream key is exactly 'stream'."""
    websocket = Mock()
    socket = ConnectedLiveViewSocket(
        websocket=websocket,
        topic="test",
        liveview=Mock(),
        scheduler=Mock(),
        instrumentation=Mock()
    )

    messages_stream = Stream[Message](dom_id="id")
    messages_stream.insert(Message(id=1, text="Test", user="Alice"))

    socket.context = ChatContext(
        messages=messages_stream,
        users=Stream[User](dom_id="id")
    )

    render = {"s": [], "0": ""}
    diff = socket.diff(render)

    # Key must be exactly "stream" (not "streams", "s", or anything else)
    assert "stream" in diff
    assert "streams" not in diff
    assert "s" in diff  # Regular static key should still exist


def test_phoenix_compatibility_prepend():
    """Test Phoenix-compatible prepend operation (at=0)."""
    websocket = Mock()
    socket = ConnectedLiveViewSocket(
        websocket=websocket,
        topic="test",
        liveview=Mock(),
        scheduler=Mock(),
        instrumentation=Mock()
    )

    messages_stream = Stream[Message](dom_id="id")
    messages_stream.prepend(Message(id=1, text="Test", user="Alice"))

    socket.context = ChatContext(
        messages=messages_stream,
        users=Stream[User](dom_id="id")
    )

    render = {"s": [], "0": ""}
    diff = socket.diff(render)

    ref, inserts, deletes, reset = diff["stream"][0]
    dom_id, at, limit, update_only = inserts[0]

    assert at == 0  # Phoenix prepend


def test_phoenix_compatibility_append():
    """Test Phoenix-compatible append operation (at=-1)."""
    websocket = Mock()
    socket = ConnectedLiveViewSocket(
        websocket=websocket,
        topic="test",
        liveview=Mock(),
        scheduler=Mock(),
        instrumentation=Mock()
    )

    messages_stream = Stream[Message](dom_id="id")
    messages_stream.append(Message(id=1, text="Test", user="Alice"))

    socket.context = ChatContext(
        messages=messages_stream,
        users=Stream[User](dom_id="id")
    )

    render = {"s": [], "0": ""}
    diff = socket.diff(render)

    ref, inserts, deletes, reset = diff["stream"][0]
    dom_id, at, limit, update_only = inserts[0]

    assert at == -1  # Phoenix append


def test_phoenix_ref_format():
    """Test that stream ref matches Phoenix format (phx-XXX)."""
    stream = Stream[Message](dom_id="id")

    assert stream.ref.startswith("phx-")
    assert len(stream.ref) > 4  # Has actual ID after prefix
    assert "-" in stream.ref


def test_empty_operations_not_sent():
    """Test that empty operation lists don't get sent."""
    websocket = Mock()
    socket = ConnectedLiveViewSocket(
        websocket=websocket,
        topic="test",
        liveview=Mock(),
        scheduler=Mock(),
        instrumentation=Mock()
    )

    # Stream with no operations
    messages_stream = Stream[Message](dom_id="id")

    socket.context = ChatContext(
        messages=messages_stream,
        users=Stream[User](dom_id="id")
    )

    render = {"s": [], "0": ""}
    diff = socket.diff(render)

    # Stream key should not be present if no operations
    assert "stream" not in diff


def test_complex_scenario_phoenix_compatible():
    """Test a complex realistic scenario for Phoenix compatibility."""
    websocket = Mock()
    socket = ConnectedLiveViewSocket(
        websocket=websocket,
        topic="test",
        liveview=Mock(),
        scheduler=Mock(),
        instrumentation=Mock()
    )

    # Simulate a chat app scenario
    messages_stream = Stream[Message](dom_id=lambda m: f"msg-{m.id}")

    # User sends new message (prepend to top)
    messages_stream.prepend(
        Message(id=100, text="New message!", user="Alice"),
        limit=50  # Keep only 50 messages
    )

    # Delete an old message
    messages_stream.remove_by_id("msg-1")

    # Update an existing message
    messages_stream.update(
        Message(id=50, text="Edited message", user="Bob")
    )

    socket.context = ChatContext(
        messages=messages_stream,
        users=Stream[User](dom_id="id")
    )

    render = {"s": ["<div>", "</div>"], "0": "chat content"}
    diff = socket.diff(render)

    # Verify complete structure
    assert "stream" in diff
    ref, inserts, deletes, reset = diff["stream"][0]

    # Should have 2 inserts (new + update)
    assert len(inserts) == 2

    # First insert (new message) - prepended first, so appears first after reversal
    new_entry = inserts[0]
    assert new_entry[0] == "msg-100"
    assert new_entry[1] == 0  # prepend
    assert new_entry[2] == 50  # limit
    assert new_entry[3] is False  # not update_only

    # Second insert (update) - check update_only flag
    update_entry = inserts[1]
    assert update_entry[3] is True  # update_only

    # Should have 1 delete
    assert len(deletes) == 1
    assert "msg-1" in deletes

    # No reset
    assert reset is False


def test_json_serializable():
    """Test that the wire format is JSON serializable."""
    import json

    websocket = Mock()
    socket = ConnectedLiveViewSocket(
        websocket=websocket,
        topic="test",
        liveview=Mock(),
        scheduler=Mock(),
        instrumentation=Mock()
    )

    messages_stream = Stream[Message](dom_id="id")
    messages_stream.insert(Message(id=1, text="Test", user="Alice"))
    messages_stream.remove_by_id("msg-2")

    socket.context = ChatContext(
        messages=messages_stream,
        users=Stream[User](dom_id="id")
    )

    render = {"s": ["<div>", "</div>"], "0": "content"}
    diff = socket.diff(render)

    # Should not raise an exception
    json_str = json.dumps(diff)
    assert isinstance(json_str, str)

    # Should be able to parse back
    parsed = json.loads(json_str)
    assert "stream" in parsed
