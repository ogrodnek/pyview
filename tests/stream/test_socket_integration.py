"""Unit tests for Stream integration with ConnectedLiveViewSocket."""

from dataclasses import dataclass
from pyview import Stream
from pyview.live_socket import ConnectedLiveViewSocket
from unittest.mock import Mock, MagicMock
import pytest


@dataclass
class Message:
    id: int
    text: str


@dataclass
class User:
    id: int
    name: str


@dataclass
class ContextWithStream:
    """Test context with a stream."""
    messages: Stream[Message]


@dataclass
class ContextWithMultipleStreams:
    """Test context with multiple streams."""
    messages: Stream[Message]
    users: Stream[User]


@dataclass
class ContextWithoutStreams:
    """Test context without any streams."""
    count: int
    name: str


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_socket():
    """Create a mock ConnectedLiveViewSocket."""
    socket = Mock(spec=ConnectedLiveViewSocket)
    socket.prev_rendered = None
    return socket


@pytest.fixture
def socket_with_stream():
    """Create a socket with a stream in context."""
    # Create mock objects
    websocket = Mock()
    topic = "test-topic"
    liveview = Mock()
    scheduler = Mock()
    instrumentation = Mock()

    # Create real socket
    socket = ConnectedLiveViewSocket(
        websocket=websocket,
        topic=topic,
        liveview=liveview,
        scheduler=scheduler,
        instrumentation=instrumentation
    )

    # Set up context with stream
    messages_stream = Stream[Message](dom_id=lambda m: f"msg-{m.id}")
    socket.context = ContextWithStream(messages=messages_stream)

    return socket


# ============================================================================
# Stream Detection Tests
# ============================================================================

def test_find_streams_in_dataclass():
    """Test finding streams in a dataclass context."""
    websocket = Mock()
    socket = ConnectedLiveViewSocket(
        websocket=websocket,
        topic="test",
        liveview=Mock(),
        scheduler=Mock(),
        instrumentation=Mock()
    )

    messages_stream = Stream[Message](dom_id="id")
    socket.context = ContextWithStream(messages=messages_stream)

    streams = socket._find_streams_in_context()

    assert len(streams) == 1
    assert streams[0][0] == "messages"
    assert streams[0][1] is messages_stream


def test_find_streams_in_dict():
    """Test finding streams in a dict context."""
    websocket = Mock()
    socket = ConnectedLiveViewSocket(
        websocket=websocket,
        topic="test",
        liveview=Mock(),
        scheduler=Mock(),
        instrumentation=Mock()
    )

    messages_stream = Stream[Message](dom_id="id")
    socket.context = {"messages": messages_stream, "count": 0}

    streams = socket._find_streams_in_context()

    assert len(streams) == 1
    assert streams[0][0] == "messages"
    assert streams[0][1] is messages_stream


def test_find_multiple_streams():
    """Test finding multiple streams in context."""
    websocket = Mock()
    socket = ConnectedLiveViewSocket(
        websocket=websocket,
        topic="test",
        liveview=Mock(),
        scheduler=Mock(),
        instrumentation=Mock()
    )

    messages_stream = Stream[Message](dom_id="id")
    users_stream = Stream[User](dom_id="id")
    socket.context = ContextWithMultipleStreams(
        messages=messages_stream,
        users=users_stream
    )

    streams = socket._find_streams_in_context()

    assert len(streams) == 2
    stream_names = [name for name, _ in streams]
    assert "messages" in stream_names
    assert "users" in stream_names


def test_no_streams_in_context():
    """Test handling context without any streams."""
    websocket = Mock()
    socket = ConnectedLiveViewSocket(
        websocket=websocket,
        topic="test",
        liveview=Mock(),
        scheduler=Mock(),
        instrumentation=Mock()
    )

    socket.context = ContextWithoutStreams(count=0, name="Test")

    streams = socket._find_streams_in_context()

    assert len(streams) == 0


def test_stream_names_set_automatically():
    """Test that stream names are set automatically from context."""
    websocket = Mock()
    socket = ConnectedLiveViewSocket(
        websocket=websocket,
        topic="test",
        liveview=Mock(),
        scheduler=Mock(),
        instrumentation=Mock()
    )

    messages_stream = Stream[Message](dom_id="id")
    assert messages_stream.name is None

    socket.context = ContextWithStream(messages=messages_stream)
    socket._find_streams_in_context()

    assert messages_stream.name == "messages"


# ============================================================================
# Diff Generation Tests
# ============================================================================

def test_diff_includes_stream_operations():
    """Test that diff includes stream operations when present."""
    websocket = Mock()
    socket = ConnectedLiveViewSocket(
        websocket=websocket,
        topic="test",
        liveview=Mock(),
        scheduler=Mock(),
        instrumentation=Mock()
    )

    messages_stream = Stream[Message](dom_id="id")
    messages_stream.insert(Message(id=1, text="Hello"))
    socket.context = ContextWithStream(messages=messages_stream)

    render = {"s": ["<div>", "</div>"], "0": "Test"}
    diff = socket.diff(render)

    assert "stream" in diff
    assert isinstance(diff["stream"], list)
    assert len(diff["stream"]) == 1


def test_diff_without_stream_operations():
    """Test that diff doesn't include stream key when no operations."""
    websocket = Mock()
    socket = ConnectedLiveViewSocket(
        websocket=websocket,
        topic="test",
        liveview=Mock(),
        scheduler=Mock(),
        instrumentation=Mock()
    )

    messages_stream = Stream[Message](dom_id="id")
    # No operations on stream
    socket.context = ContextWithStream(messages=messages_stream)

    render = {"s": ["<div>", "</div>"], "0": "Test"}
    diff = socket.diff(render)

    assert "stream" not in diff


def test_diff_with_multiple_streams():
    """Test diff generation with multiple streams."""
    websocket = Mock()
    socket = ConnectedLiveViewSocket(
        websocket=websocket,
        topic="test",
        liveview=Mock(),
        scheduler=Mock(),
        instrumentation=Mock()
    )

    messages_stream = Stream[Message](dom_id="id")
    messages_stream.insert(Message(id=1, text="Hello"))

    users_stream = Stream[User](dom_id="id")
    users_stream.insert(User(id=1, name="Alice"))

    socket.context = ContextWithMultipleStreams(
        messages=messages_stream,
        users=users_stream
    )

    render = {"s": ["<div>", "</div>"], "0": "Test"}
    diff = socket.diff(render)

    assert "stream" in diff
    assert len(diff["stream"]) == 2


def test_diff_preserves_regular_fields():
    """Test that diff preserves regular (non-stream) fields."""
    websocket = Mock()
    socket = ConnectedLiveViewSocket(
        websocket=websocket,
        topic="test",
        liveview=Mock(),
        scheduler=Mock(),
        instrumentation=Mock()
    )

    messages_stream = Stream[Message](dom_id="id")
    messages_stream.insert(Message(id=1, text="Hello"))
    socket.context = ContextWithStream(messages=messages_stream)

    render = {"s": ["<div>", "</div>"], "0": "Test"}
    diff = socket.diff(render)

    # Regular fields should still be present
    assert "s" in diff
    assert "0" in diff
    # Stream operations added
    assert "stream" in diff


def test_stream_operations_cleared_after_diff():
    """Test that stream operations are cleared after being included in diff."""
    websocket = Mock()
    socket = ConnectedLiveViewSocket(
        websocket=websocket,
        topic="test",
        liveview=Mock(),
        scheduler=Mock(),
        instrumentation=Mock()
    )

    messages_stream = Stream[Message](dom_id="id")
    messages_stream.insert(Message(id=1, text="Hello"))
    socket.context = ContextWithStream(messages=messages_stream)

    # First diff should include operations
    render1 = {"s": ["<div>", "</div>"], "0": "Test1"}
    diff1 = socket.diff(render1)
    assert "stream" in diff1

    # Second diff should not include operations (they were consumed)
    render2 = {"s": ["<div>", "</div>"], "0": "Test2"}
    diff2 = socket.diff(render2)
    assert "stream" not in diff2


# ============================================================================
# Wire Protocol Format Tests
# ============================================================================

def test_wire_protocol_structure():
    """Test that stream operations match Phoenix wire protocol structure."""
    websocket = Mock()
    socket = ConnectedLiveViewSocket(
        websocket=websocket,
        topic="test",
        liveview=Mock(),
        scheduler=Mock(),
        instrumentation=Mock()
    )

    messages_stream = Stream[Message](dom_id="id")
    messages_stream.insert(Message(id=1, text="Hello"))
    messages_stream.remove_by_id("msg-2")
    socket.context = ContextWithStream(messages=messages_stream)

    render = {"s": ["<div>", "</div>"], "0": "Test"}
    diff = socket.diff(render)

    stream_ops = diff["stream"]
    assert isinstance(stream_ops, list)
    assert len(stream_ops) == 1

    # Structure should be: [ref, inserts, deleteIds, reset]
    stream_op = stream_ops[0]
    assert len(stream_op) == 4
    ref, inserts, deletes, reset = stream_op

    assert isinstance(ref, str)
    assert ref.startswith("phx-")
    assert isinstance(inserts, list)
    assert isinstance(deletes, list)
    assert isinstance(reset, bool)


def test_insert_entry_format():
    """Test that insert entries are formatted correctly."""
    websocket = Mock()
    socket = ConnectedLiveViewSocket(
        websocket=websocket,
        topic="test",
        liveview=Mock(),
        scheduler=Mock(),
        instrumentation=Mock()
    )

    messages_stream = Stream[Message](dom_id="id")
    messages_stream.insert(Message(id=1, text="Hello"), at=0, limit=50)
    socket.context = ContextWithStream(messages=messages_stream)

    render = {"s": ["<div>", "</div>"], "0": "Test"}
    diff = socket.diff(render)

    ref, inserts, deletes, reset = diff["stream"][0]

    # Insert entry format: [dom_id, at, limit, update_only]
    assert len(inserts) == 1
    insert_entry = inserts[0]
    assert len(insert_entry) == 4

    dom_id, at, limit, update_only = insert_entry
    assert dom_id == "1"
    assert at == 0
    assert limit == 50
    assert update_only is False


def test_delete_ids_format():
    """Test that delete IDs are formatted correctly."""
    websocket = Mock()
    socket = ConnectedLiveViewSocket(
        websocket=websocket,
        topic="test",
        liveview=Mock(),
        scheduler=Mock(),
        instrumentation=Mock()
    )

    messages_stream = Stream[Message](dom_id="id")
    messages_stream.remove_by_id("msg-1")
    messages_stream.remove_by_id("msg-2")
    socket.context = ContextWithStream(messages=messages_stream)

    render = {"s": ["<div>", "</div>"], "0": "Test"}
    diff = socket.diff(render)

    ref, inserts, deletes, reset = diff["stream"][0]

    assert isinstance(deletes, list)
    assert len(deletes) == 2
    assert "msg-1" in deletes
    assert "msg-2" in deletes


def test_reset_flag_format():
    """Test that reset flag is formatted correctly."""
    websocket = Mock()
    socket = ConnectedLiveViewSocket(
        websocket=websocket,
        topic="test",
        liveview=Mock(),
        scheduler=Mock(),
        instrumentation=Mock()
    )

    messages_stream = Stream[Message](dom_id="id")
    messages_stream.reset([Message(id=1, text="New")])
    socket.context = ContextWithStream(messages=messages_stream)

    render = {"s": ["<div>", "</div>"], "0": "Test"}
    diff = socket.diff(render)

    ref, inserts, deletes, reset = diff["stream"][0]

    assert reset is True


def test_stream_ref_included():
    """Test that stream ref is included in operations."""
    websocket = Mock()
    socket = ConnectedLiveViewSocket(
        websocket=websocket,
        topic="test",
        liveview=Mock(),
        scheduler=Mock(),
        instrumentation=Mock()
    )

    messages_stream = Stream[Message](dom_id="id")
    messages_stream.insert(Message(id=1, text="Hello"))
    socket.context = ContextWithStream(messages=messages_stream)

    render = {"s": ["<div>", "</div>"], "0": "Test"}
    diff = socket.diff(render)

    ref, inserts, deletes, reset = diff["stream"][0]

    assert ref == messages_stream.ref
    assert ref.startswith("phx-")


def test_extract_stream_operations_with_no_operations():
    """Test _extract_stream_operations when stream has no operations."""
    websocket = Mock()
    socket = ConnectedLiveViewSocket(
        websocket=websocket,
        topic="test",
        liveview=Mock(),
        scheduler=Mock(),
        instrumentation=Mock()
    )

    messages_stream = Stream[Message](dom_id="id")
    socket.context = ContextWithStream(messages=messages_stream)

    render = {"s": ["<div>", "</div>"], "0": "Test"}
    stream_ops = socket._extract_stream_operations(render)

    assert stream_ops is None


def test_limit_default_value():
    """Test that limit defaults to -1 when not specified."""
    websocket = Mock()
    socket = ConnectedLiveViewSocket(
        websocket=websocket,
        topic="test",
        liveview=Mock(),
        scheduler=Mock(),
        instrumentation=Mock()
    )

    messages_stream = Stream[Message](dom_id="id")
    messages_stream.insert(Message(id=1, text="Hello"))  # No limit specified
    socket.context = ContextWithStream(messages=messages_stream)

    render = {"s": ["<div>", "</div>"], "0": "Test"}
    diff = socket.diff(render)

    ref, inserts, deletes, reset = diff["stream"][0]
    dom_id, at, limit, update_only = inserts[0]

    assert limit == -1  # Default value
