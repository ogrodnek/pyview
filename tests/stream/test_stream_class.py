"""Unit tests for Stream class."""

from dataclasses import dataclass
from pyview import Stream
import pytest


@dataclass
class Message:
    id: int
    text: str


# ============================================================================
# Initialization Tests
# ============================================================================

def test_stream_init_with_attribute_name():
    """Test stream initialization with attribute name for dom_id."""
    stream = Stream[Message](dom_id="id")

    assert stream._dom_id == "id"
    assert callable(stream._dom_id_fn)
    assert stream.ref.startswith("phx-")


def test_stream_init_with_function():
    """Test stream initialization with function for dom_id."""
    stream = Stream[Message](dom_id=lambda m: f"msg-{m.id}")

    assert callable(stream._dom_id)
    assert callable(stream._dom_id_fn)


def test_stream_init_default():
    """Test stream initialization with default dom_id."""
    stream = Stream[Message]()

    assert stream._dom_id == "id"


def test_stream_ref_is_unique():
    """Test that each stream gets a unique ref."""
    stream1 = Stream[Message]()
    stream2 = Stream[Message]()

    assert stream1.ref != stream2.ref
    assert stream1.ref.startswith("phx-")
    assert stream2.ref.startswith("phx-")


def test_stream_name_optional():
    """Test that stream name is optional."""
    stream = Stream[Message]()

    assert stream.name is None


# ============================================================================
# DOM ID Extraction Tests
# ============================================================================

def test_dom_id_from_dataclass_attribute():
    """Test extracting DOM ID from dataclass using attribute name."""
    stream = Stream[Message](dom_id="id")
    msg = Message(id=42, text="Hello")

    dom_id = stream._dom_id_fn(msg)

    assert dom_id == "42"


def test_dom_id_from_dict_attribute():
    """Test extracting DOM ID from dict using attribute name."""
    stream = Stream[dict](dom_id="id")
    msg = {"id": 42, "text": "Hello"}

    dom_id = stream._dom_id_fn(msg)

    assert dom_id == "42"


def test_dom_id_from_custom_function():
    """Test extracting DOM ID using custom function."""
    stream = Stream[Message](dom_id=lambda m: f"message-{m.id}")
    msg = Message(id=42, text="Hello")

    dom_id = stream._dom_id_fn(msg)

    assert dom_id == "message-42"


# ============================================================================
# Insert Operations Tests
# ============================================================================

def test_prepend_single_item():
    """Test prepending a single item."""
    stream = Stream[Message](dom_id="id")
    msg = Message(id=1, text="Hello")

    result = stream.prepend(msg)

    assert result is stream  # Method chaining
    assert len(stream._inserts) == 1
    assert stream._inserts[0][0] == "1"  # dom_id
    assert stream._inserts[0][1] == 0    # at position
    assert stream._inserts[0][2] == msg  # item


def test_append_single_item():
    """Test appending a single item."""
    stream = Stream[Message](dom_id="id")
    msg = Message(id=1, text="Hello")

    result = stream.append(msg)

    assert result is stream
    assert len(stream._inserts) == 1
    assert stream._inserts[0][1] == -1  # at position


def test_insert_at_position():
    """Test inserting at a specific position."""
    stream = Stream[Message](dom_id="id")
    msg = Message(id=1, text="Hello")

    stream.insert(msg, at=5)

    assert stream._inserts[0][1] == 5


def test_insert_with_limit():
    """Test inserting with a limit parameter."""
    stream = Stream[Message](dom_id="id")
    msg = Message(id=1, text="Hello")

    stream.insert(msg, limit=50)

    assert stream._inserts[0][3] == 50  # limit


def test_insert_with_update_only():
    """Test inserting with update_only flag."""
    stream = Stream[Message](dom_id="id")
    msg = Message(id=1, text="Hello")

    stream.insert(msg, update_only=True)

    assert stream._inserts[0][4] is True  # update_only


def test_insert_method_chaining():
    """Test that insert operations can be chained."""
    stream = Stream[Message](dom_id="id")
    msg1 = Message(id=1, text="Hello")
    msg2 = Message(id=2, text="World")

    result = stream.insert(msg1).insert(msg2)

    assert result is stream
    assert len(stream._inserts) == 2


def test_multiple_inserts_tracked():
    """Test that multiple inserts are tracked in order."""
    stream = Stream[Message](dom_id="id")
    msg1 = Message(id=1, text="First")
    msg2 = Message(id=2, text="Second")
    msg3 = Message(id=3, text="Third")

    stream.insert(msg1)
    stream.insert(msg2)
    stream.insert(msg3)

    assert len(stream._inserts) == 3
    # Note: inserts are prepended, so order is reversed
    assert stream._inserts[0][2].text == "Third"
    assert stream._inserts[1][2].text == "Second"
    assert stream._inserts[2][2].text == "First"


# ============================================================================
# Bulk Operations Tests
# ============================================================================

def test_extend_items():
    """Test extending stream with multiple items."""
    stream = Stream[Message](dom_id="id")
    messages = [
        Message(id=1, text="First"),
        Message(id=2, text="Second"),
    ]

    result = stream.extend(messages)

    assert result is stream
    # First extend populates _initial_items, not _inserts
    assert len(stream._initial_items) == 2
    assert len(stream._inserts) == 0


def test_extend_at_beginning():
    """Test extending at the beginning."""
    stream = Stream[Message](dom_id="id")
    messages = [Message(id=1, text="First")]

    stream.extend(messages, at=0)

    # First extend populates _initial_items regardless of 'at' parameter
    assert len(stream._initial_items) == 1
    assert len(stream._inserts) == 0


def test_extend_at_end():
    """Test extending at the end."""
    stream = Stream[Message](dom_id="id")
    messages = [Message(id=1, text="First")]

    stream.extend(messages, at=-1)

    # First extend populates _initial_items regardless of 'at' parameter
    assert len(stream._initial_items) == 1
    assert len(stream._inserts) == 0


def test_extend_empty_list():
    """Test extending with an empty list."""
    stream = Stream[Message](dom_id="id")

    stream.extend([])

    assert len(stream._inserts) == 0


def test_extend_subsequent_calls_create_operations():
    """Test that extend() after initial load creates stream operations."""
    stream = Stream[Message](dom_id="id")

    # First extend - goes to _initial_items
    initial_messages = [Message(id=1, text="First")]
    stream.extend(initial_messages)
    assert len(stream._initial_items) == 1
    assert len(stream._inserts) == 0

    # Second extend - creates operations
    new_messages = [Message(id=2, text="Second"), Message(id=3, text="Third")]
    stream.extend(new_messages, at=0)
    assert len(stream._inserts) == 2
    assert stream._inserts[0][1] == 0  # at position

    # Initial items unchanged
    assert len(stream._initial_items) == 1


# ============================================================================
# Update Operations Tests
# ============================================================================

def test_update_item():
    """Test updating an item."""
    stream = Stream[Message](dom_id="id")
    msg = Message(id=1, text="Updated")

    result = stream.update(msg)

    assert result is stream
    assert len(stream._inserts) == 1
    assert stream._inserts[0][4] is True  # update_only


def test_update_sets_update_only_flag():
    """Test that update sets the update_only flag."""
    stream = Stream[Message](dom_id="id")
    msg = Message(id=1, text="Updated")

    stream.update(msg)

    dom_id, at, item, limit, update_only = stream._inserts[0]
    assert update_only is True


# ============================================================================
# Delete Operations Tests
# ============================================================================

def test_remove_item_by_object():
    """Test removing an item by passing the object."""
    stream = Stream[Message](dom_id="id")
    msg = Message(id=1, text="Remove me")

    result = stream.remove(msg)

    assert result is stream
    assert len(stream._deletes) == 1
    assert stream._deletes[0] == "1"


def test_remove_by_dom_id():
    """Test removing an item by DOM ID."""
    stream = Stream[Message](dom_id="id")

    result = stream.remove_by_id("msg-42")

    assert result is stream
    assert len(stream._deletes) == 1
    assert stream._deletes[0] == "msg-42"


def test_multiple_removes_tracked():
    """Test that multiple removes are tracked."""
    stream = Stream[Message](dom_id="id")

    stream.remove_by_id("msg-1")
    stream.remove_by_id("msg-2")
    stream.remove_by_id("msg-3")

    assert len(stream._deletes) == 3
    assert "msg-1" in stream._deletes
    assert "msg-2" in stream._deletes
    assert "msg-3" in stream._deletes


def test_remove_method_chaining():
    """Test that remove operations can be chained."""
    stream = Stream[Message](dom_id="id")

    result = stream.remove_by_id("msg-1").remove_by_id("msg-2")

    assert result is stream
    assert len(stream._deletes) == 2


# ============================================================================
# Reset Operations Tests
# ============================================================================

def test_reset_clears_operations():
    """Test that reset clears pending operations."""
    stream = Stream[Message](dom_id="id")
    stream.insert(Message(id=1, text="Test"))
    stream.remove_by_id("msg-2")

    stream.reset()

    assert len(stream._inserts) == 0
    assert len(stream._deletes) == 0
    assert stream._reset is True


def test_reset_with_new_items():
    """Test resetting with new items."""
    stream = Stream[Message](dom_id="id")
    new_messages = [
        Message(id=1, text="New1"),
        Message(id=2, text="New2"),
    ]

    stream.reset(new_messages)

    assert stream._reset is True
    assert len(stream._inserts) == 2


def test_reset_empty():
    """Test resetting to empty."""
    stream = Stream[Message](dom_id="id")
    stream.extend([Message(id=1, text="Test")])

    stream.reset()

    assert stream._reset is True
    assert len(stream._inserts) == 0


def test_reset_flag_set():
    """Test that reset flag is set correctly."""
    stream = Stream[Message](dom_id="id")

    assert stream._reset is False

    stream.reset()

    assert stream._reset is True


# ============================================================================
# Iteration Tests
# ============================================================================

def test_iteration_yields_tuples():
    """Test that iteration yields (dom_id, item) tuples."""
    stream = Stream[Message](dom_id="id")
    msg = Message(id=1, text="Hello")
    stream.insert(msg)

    items = list(stream)

    assert len(items) == 1
    assert isinstance(items[0], tuple)
    assert len(items[0]) == 2
    dom_id, item = items[0]
    assert dom_id == "1"
    assert item == msg


def test_iterate_initial_items():
    """Test iterating over initial items."""
    stream = Stream[Message](dom_id="id")
    stream._initial_items = [
        Message(id=1, text="First"),
        Message(id=2, text="Second"),
    ]

    items = list(stream)

    assert len(items) == 2
    assert items[0][0] == "1"
    assert items[1][0] == "2"


def test_iterate_pending_inserts():
    """Test iterating over pending inserts."""
    stream = Stream[Message](dom_id="id")
    stream.insert(Message(id=1, text="Pending"))

    items = list(stream)

    assert len(items) == 1
    assert items[0][1].text == "Pending"


def test_iterate_initial_and_pending():
    """Test iterating over both initial items and pending inserts."""
    stream = Stream[Message](dom_id="id")
    stream._initial_items = [Message(id=1, text="Initial")]
    stream.insert(Message(id=2, text="Pending"))

    items = list(stream)

    assert len(items) == 2


def test_empty_stream_iteration():
    """Test iterating over an empty stream."""
    stream = Stream[Message](dom_id="id")

    items = list(stream)

    assert len(items) == 0


# ============================================================================
# Operation Consumption Tests
# ============================================================================

def test_has_operations_true_with_inserts():
    """Test has_operations returns True when there are inserts."""
    stream = Stream[Message](dom_id="id")
    stream.insert(Message(id=1, text="Test"))

    assert stream.has_operations() is True


def test_has_operations_true_with_deletes():
    """Test has_operations returns True when there are deletes."""
    stream = Stream[Message](dom_id="id")
    stream.remove_by_id("msg-1")

    assert stream.has_operations() is True


def test_has_operations_true_with_reset():
    """Test has_operations returns True when reset is flagged."""
    stream = Stream[Message](dom_id="id")
    stream.reset()

    assert stream.has_operations() is True


def test_has_operations_false_when_empty():
    """Test has_operations returns False when there are no operations."""
    stream = Stream[Message](dom_id="id")

    assert stream.has_operations() is False


def test_consume_operations_format():
    """Test that consume_operations returns correct format."""
    stream = Stream[Message](dom_id="id")
    stream.insert(Message(id=1, text="Test"))
    stream.remove_by_id("msg-2")
    # Note: reset() clears inserts and deletes, so don't call it here

    inserts, deletes, reset = stream.consume_operations()

    assert isinstance(inserts, list)
    assert isinstance(deletes, list)
    assert isinstance(reset, bool)
    assert len(inserts) == 1
    assert len(deletes) == 1
    assert reset is False


def test_consume_operations_clears_pending():
    """Test that consume_operations clears pending operations."""
    stream = Stream[Message](dom_id="id")
    stream.insert(Message(id=1, text="Test"))
    stream.remove_by_id("msg-2")

    stream.consume_operations()

    assert len(stream._inserts) == 0
    assert len(stream._deletes) == 0
    assert stream._reset is False


def test_consume_operations_order():
    """Test that consumed operations are in correct order."""
    stream = Stream[Message](dom_id="id")
    stream.insert(Message(id=1, text="First"))
    stream.insert(Message(id=2, text="Second"))
    stream.insert(Message(id=3, text="Third"))

    inserts, _, _ = stream.consume_operations()

    # After consume, order should be reversed (FIFO)
    assert inserts[0][2].text == "First"
    assert inserts[1][2].text == "Second"
    assert inserts[2][2].text == "Third"


def test_consume_clears_initial_items():
    """Test that consume_operations clears initial items."""
    stream = Stream[Message](dom_id="id")
    stream._initial_items = [Message(id=1, text="Initial")]

    stream.consume_operations()

    assert len(stream._initial_items) == 0


# ============================================================================
# Edge Cases Tests
# ============================================================================

def test_operations_on_empty_stream():
    """Test performing operations on an empty stream."""
    stream = Stream[Message](dom_id="id")

    # Should not raise errors
    stream.remove_by_id("nonexistent")
    stream.reset()

    assert stream.has_operations() is True


def test_many_operations():
    """Test handling a large number of operations."""
    stream = Stream[Message](dom_id="id")

    for i in range(1000):
        stream.insert(Message(id=i, text=f"Message {i}"))

    assert len(stream._inserts) == 1000
    assert stream.has_operations() is True


def test_duplicate_inserts():
    """Test inserting the same item multiple times."""
    stream = Stream[Message](dom_id="id")
    msg = Message(id=1, text="Same")

    stream.insert(msg)
    stream.insert(msg)
    stream.insert(msg)

    assert len(stream._inserts) == 3


def test_delete_nonexistent_item():
    """Test deleting a non-existent item doesn't raise error."""
    stream = Stream[Message](dom_id="id")

    # Should not raise an error
    stream.remove_by_id("does-not-exist")

    assert "does-not-exist" in stream._deletes


def test_complex_dom_id_function():
    """Test using a complex DOM ID function."""
    stream = Stream[Message](
        dom_id=lambda m: f"message-{m.id}-{m.text.lower().replace(' ', '-')}"
    )
    msg = Message(id=42, text="Hello World")

    dom_id = stream._dom_id_fn(msg)

    assert dom_id == "message-42-hello-world"


def test_repr():
    """Test string representation of stream."""
    stream = Stream[Message](dom_id="id")
    stream.insert(Message(id=1, text="Test"))
    stream.remove_by_id("msg-2")

    repr_str = repr(stream)

    assert "Stream" in repr_str
    assert "phx-" in repr_str
    assert "insert" in repr_str
    assert "delete" in repr_str
