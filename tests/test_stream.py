"""
Unit tests for the Stream class.
"""

import pytest
from dataclasses import dataclass

from pyview.stream import Stream, StreamOps, StreamInsert


@dataclass
class User:
    id: int
    name: str


@dataclass
class Message:
    uuid: str
    text: str


class TestStreamBasics:
    """Test basic Stream construction and iteration."""

    def test_stream_requires_name(self):
        # Python raises TypeError for missing required keyword-only arguments
        with pytest.raises(TypeError, match="name"):
            Stream([])  # type: ignore

    def test_stream_with_dataclass_items(self):
        users = [User(id=1, name="Alice"), User(id=2, name="Bob")]
        stream = Stream(users, name="users")

        items = list(stream)
        assert len(items) == 2
        assert items[0] == ("users-1", users[0])
        assert items[1] == ("users-2", users[1])

    def test_stream_with_dict_items(self):
        items = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        stream = Stream(items, name="items")

        result = list(stream)
        assert len(result) == 2
        assert result[0] == ("items-1", items[0])
        assert result[1] == ("items-2", items[1])

    def test_stream_with_custom_dom_id(self):
        messages = [Message(uuid="abc", text="Hello"), Message(uuid="def", text="World")]
        stream = Stream(messages, name="messages", dom_id=lambda m: f"msg-{m.uuid}")

        items = list(stream)
        assert items[0][0] == "msg-abc"
        assert items[1][0] == "msg-def"

    def test_stream_empty(self):
        stream = Stream(name="empty")
        assert len(stream) == 0
        assert list(stream) == []

    def test_stream_no_id_raises_error(self):
        items = [{"name": "No ID"}]  # Missing 'id' key
        stream = Stream(name="items")

        with pytest.raises(ValueError, match="Cannot generate DOM ID"):
            stream.insert(items[0])


class TestStreamInsert:
    """Test insert operations."""

    def test_insert_append(self):
        stream = Stream(name="users")
        stream.insert(User(id=1, name="Alice"))

        ops = stream._get_pending_ops()
        assert ops is not None
        assert len(ops.inserts) == 1
        assert ops.inserts[0].dom_id == "users-1"
        assert ops.inserts[0].at == -1
        assert ops.inserts[0].limit is None
        assert ops.inserts[0].update_only is False

    def test_insert_prepend(self):
        stream = Stream(name="users")
        stream.insert(User(id=1, name="Alice"), at=0)

        ops = stream._get_pending_ops()
        assert ops.inserts[0].at == 0

    def test_insert_at_index(self):
        stream = Stream(name="users")
        stream.insert(User(id=1, name="Alice"), at=5)

        ops = stream._get_pending_ops()
        assert ops.inserts[0].at == 5

    def test_insert_with_limit(self):
        stream = Stream(name="messages")
        stream.insert({"id": 1, "text": "Hi"}, limit=100)

        ops = stream._get_pending_ops()
        assert ops.inserts[0].limit == 100

    def test_insert_with_negative_limit(self):
        stream = Stream(name="messages")
        stream.insert({"id": 1, "text": "Hi"}, at=0, limit=-50)

        ops = stream._get_pending_ops()
        assert ops.inserts[0].at == 0
        assert ops.inserts[0].limit == -50

    def test_insert_update_only(self):
        stream = Stream(name="users")
        stream.insert(User(id=1, name="Alice"), update_only=True)

        ops = stream._get_pending_ops()
        assert ops.inserts[0].update_only is True

    def test_insert_returns_dom_id(self):
        stream = Stream(name="users")
        dom_id = stream.insert(User(id=42, name="Alice"))
        assert dom_id == "users-42"

    def test_insert_many(self):
        stream = Stream(name="users")
        users = [User(id=1, name="Alice"), User(id=2, name="Bob")]
        dom_ids = stream.insert_many(users)

        assert dom_ids == ["users-1", "users-2"]
        ops = stream._get_pending_ops()
        assert len(ops.inserts) == 2

    def test_insert_many_with_position(self):
        stream = Stream(name="users")
        users = [User(id=1, name="Alice"), User(id=2, name="Bob")]
        stream.insert_many(users, at=0, limit=10)

        ops = stream._get_pending_ops()
        assert all(ins.at == 0 for ins in ops.inserts)
        assert all(ins.limit == 10 for ins in ops.inserts)


class TestStreamDelete:
    """Test delete operations."""

    def test_delete_by_item(self):
        user = User(id=1, name="Alice")
        stream = Stream(name="users")
        dom_id = stream.delete(user)

        assert dom_id == "users-1"
        ops = stream._get_pending_ops()
        assert ops.deletes == ["users-1"]

    def test_delete_by_id(self):
        stream = Stream(name="users")
        dom_id = stream.delete_by_id("users-42")

        assert dom_id == "users-42"
        ops = stream._get_pending_ops()
        assert ops.deletes == ["users-42"]

    def test_multiple_deletes(self):
        stream = Stream(name="users")
        stream.delete_by_id("users-1")
        stream.delete_by_id("users-2")
        stream.delete_by_id("users-3")

        ops = stream._get_pending_ops()
        assert ops.deletes == ["users-1", "users-2", "users-3"]


class TestStreamReset:
    """Test reset operations."""

    def test_reset_empty(self):
        stream = Stream([User(id=1, name="Alice")], name="users")
        stream._get_pending_ops()  # Clear initial ops

        stream.reset()

        ops = stream._get_pending_ops()
        assert ops.reset is True
        assert ops.inserts == []
        assert ops.deletes == []

    def test_reset_with_new_items(self):
        stream = Stream([User(id=1, name="Alice")], name="users")
        stream._get_pending_ops()  # Clear initial ops

        new_users = [User(id=10, name="New1"), User(id=11, name="New2")]
        stream.reset(new_users)

        ops = stream._get_pending_ops()
        assert ops.reset is True
        assert len(ops.inserts) == 2
        assert ops.inserts[0].dom_id == "users-10"
        assert ops.inserts[1].dom_id == "users-11"

    def test_reset_clears_pending_inserts(self):
        stream = Stream(name="users")
        stream.insert(User(id=1, name="Alice"))
        stream.insert(User(id=2, name="Bob"))

        stream.reset([User(id=99, name="Only")])

        ops = stream._get_pending_ops()
        assert ops.reset is True
        assert len(ops.inserts) == 1
        assert ops.inserts[0].dom_id == "users-99"


class TestStreamCombinedOperations:
    """Test multiple operations together."""

    def test_insert_and_delete(self):
        stream = Stream(name="users")
        stream.insert(User(id=1, name="New"))
        stream.delete_by_id("users-old")

        ops = stream._get_pending_ops()
        assert len(ops.inserts) == 1
        assert len(ops.deletes) == 1

    def test_multiple_inserts_different_positions(self):
        stream = Stream(name="users")
        stream.insert(User(id=1, name="Append"), at=-1)
        stream.insert(User(id=2, name="Prepend"), at=0)
        stream.insert(User(id=3, name="Middle"), at=1)

        ops = stream._get_pending_ops()
        assert ops.inserts[0].at == -1
        assert ops.inserts[1].at == 0
        assert ops.inserts[2].at == 1

    def test_move_item(self):
        """Move = delete + insert at new position."""
        user = User(id=1, name="Alice")
        stream = Stream(name="users")
        stream.delete(user)
        stream.insert(user, at=0)

        ops = stream._get_pending_ops()
        assert "users-1" in ops.deletes
        assert ops.inserts[0].dom_id == "users-1"
        assert ops.inserts[0].at == 0


class TestStreamWireFormat:
    """Test wire format generation.

    Phoenix LiveView 0.18.x format: [{dom_id: at_position}, [delete_ids]]
    """

    def test_basic_insert_wire_format(self):
        stream = Stream([User(id=1, name="Alice")], name="users")
        wire = stream._get_wire_format()

        assert wire is not None
        assert wire[0] == {"users-1": -1}  # inserts: {dom_id: at}
        assert wire[1] == []  # deletes

    def test_delete_wire_format(self):
        stream = Stream(name="users")
        stream.delete_by_id("users-1")
        wire = stream._get_wire_format()

        assert wire[0] == {}  # no inserts
        assert wire[1] == ["users-1"]  # deletes

    def test_reset_wire_format(self):
        """Reset sends inserts for new items (client clears on phx-update=stream)."""
        stream = Stream(name="users")
        stream.reset([User(id=1, name="Alice")])
        wire = stream._get_wire_format()

        assert wire[0] == {"users-1": -1}  # inserts
        assert wire[1] == []  # deletes

    def test_reset_empty_wire_format(self):
        """Empty reset - client clears container, no new inserts."""
        stream = Stream(name="users")
        stream.reset()
        wire = stream._get_wire_format()

        assert wire[0] == {}  # no inserts
        assert wire[1] == []  # no deletes

    def test_combined_operations_wire_format(self):
        stream = Stream(name="users")
        stream.insert(User(id=10, name="New"), at=-1)
        stream.insert(User(id=11, name="Prepended"), at=0)
        stream.delete_by_id("users-5")
        wire = stream._get_wire_format()

        assert wire[0] == {"users-10": -1, "users-11": 0}  # inserts
        assert wire[1] == ["users-5"]  # deletes

    def test_insert_with_position_wire_format(self):
        """Position (at) is preserved in wire format."""
        stream = Stream(name="users")
        stream.insert(User(id=1, name="Alice"), at=2)
        wire = stream._get_wire_format()

        assert wire[0] == {"users-1": 2}  # at=2 preserved

    def test_no_ops_returns_none(self):
        stream = Stream(name="users")
        wire = stream._get_wire_format()
        assert wire is None

    def test_ops_cleared_after_get(self):
        stream = Stream(name="users")
        stream.insert(User(id=1, name="Alice"))

        # First get
        wire1 = stream._get_wire_format()
        assert wire1 is not None

        # Second get should return None (ops cleared)
        wire2 = stream._get_wire_format()
        assert wire2 is None


class TestStreamIteration:
    """Test iteration behavior."""

    def test_iteration_yields_tuples(self):
        users = [User(id=1, name="Alice"), User(id=2, name="Bob")]
        stream = Stream(users, name="users")

        for dom_id, user in stream:
            assert dom_id.startswith("users-")
            assert isinstance(user, User)

    def test_iteration_cleared_after_get_ops(self):
        stream = Stream([User(id=1, name="Alice")], name="users")
        assert len(stream) == 1

        stream._get_pending_ops()

        assert len(stream) == 0
        assert list(stream) == []

    def test_len_reflects_pending_items(self):
        stream = Stream(name="users")
        assert len(stream) == 0

        stream.insert(User(id=1, name="Alice"))
        assert len(stream) == 1

        stream.insert(User(id=2, name="Bob"))
        assert len(stream) == 2

    def test_bool_with_items(self):
        stream = Stream([User(id=1, name="Alice")], name="users")
        assert bool(stream) is True

    def test_bool_empty_no_ops(self):
        stream = Stream(name="users")
        assert bool(stream) is False

    def test_bool_with_delete_only(self):
        stream = Stream(name="users")
        stream.delete_by_id("users-1")
        assert bool(stream) is True  # Has operations
