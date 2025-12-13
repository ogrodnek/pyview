"""
Integration tests for Stream + Ibis templates.
"""

from dataclasses import dataclass

from pyview.stream import Stream
from pyview.vendor.ibis import Template


@dataclass
class User:
    id: int
    name: str


@dataclass
class Message:
    id: int
    text: str
    author: str


class TestStreamIbisBasic:
    """Test basic Stream rendering with Ibis templates."""

    def test_stream_for_loop_basic(self):
        """Stream for loop produces correct wire format."""
        template = Template("""
<div id="users" phx-update="stream">
{% for dom_id, user in users %}
<div id="{{ dom_id }}">{{ user.name }}</div>
{% endfor %}
</div>
""")
        users = [User(id=1, name="Alice"), User(id=2, name="Bob")]
        stream = Stream(users, name="users")

        tree = template.tree({"users": stream})

        # The comprehension should be at position "0" (first dynamic)
        assert "0" in tree
        comp = tree["0"]

        # Should have static, dynamic, and stream keys
        assert "s" in comp
        assert "d" in comp
        assert "stream" in comp

        # Check stream metadata format: [{dom_id: at_position}, [delete_ids]]
        stream_meta = comp["stream"]
        assert stream_meta[0] == {"users-1": -1, "users-2": -1}  # inserts: {dom_id: at}
        assert stream_meta[1] == []  # no deletes

    def test_stream_dynamics_match_inserts(self):
        """Dynamic content matches stream inserts."""
        template = Template(
            """{% for dom_id, user in users %}<div id="{{ dom_id }}">{{ user.name }}</div>{% endfor %}"""
        )

        users = [User(id=1, name="Alice"), User(id=2, name="Bob")]
        stream = Stream(users, name="users")

        tree = template.tree({"users": stream})

        # Get the comprehension
        comp = tree["0"]

        # Dynamic content should have 2 entries
        assert len(comp["d"]) == 2
        # Each entry should have [dom_id, name]
        assert comp["d"][0] == ["users-1", "Alice"]
        assert comp["d"][1] == ["users-2", "Bob"]

    def test_stream_with_custom_dom_id(self):
        """Stream with custom dom_id function."""
        template = Template(
            """{% for dom_id, msg in messages %}<div id="{{ dom_id }}">{{ msg.text }}</div>{% endfor %}"""
        )

        messages = [Message(id=1, text="Hello", author="Alice")]
        stream = Stream(messages, name="messages", dom_id=lambda m: f"msg-{m.id}")

        tree = template.tree({"messages": stream})
        comp = tree["0"]

        # Check custom dom_id in stream metadata
        assert comp["stream"][0] == {"msg-1": -1}  # inserts: {dom_id: at}
        assert comp["stream"][1] == []  # no deletes
        assert comp["d"][0] == ["msg-1", "Hello"]


class TestStreamOperationsInTemplate:
    """Test various stream operations reflected in template output.

    Phoenix 0.18.x wire format: [{dom_id: at_position}, [delete_ids]]
    """

    def test_stream_append(self):
        """Append operation (at=-1)."""
        template = Template(
            """{% for dom_id, user in users %}<li id="{{ dom_id }}">{{ user.name }}</li>{% endfor %}"""
        )

        stream = Stream(name="users")
        stream.insert(User(id=1, name="Alice"))
        stream.insert(User(id=2, name="Bob"))

        tree = template.tree({"users": stream})
        comp = tree["0"]

        assert comp["stream"][0] == {"users-1": -1, "users-2": -1}  # inserts
        assert comp["stream"][1] == []  # no deletes

    def test_stream_prepend(self):
        """Prepend operation (at=0)."""
        template = Template(
            """{% for dom_id, user in users %}<li id="{{ dom_id }}">{{ user.name }}</li>{% endfor %}"""
        )

        stream = Stream(name="users")
        stream.insert(User(id=1, name="Alice"), at=0)

        tree = template.tree({"users": stream})
        comp = tree["0"]

        assert comp["stream"][0] == {"users-1": 0}  # inserts with at=0
        assert comp["stream"][1] == []  # no deletes

    def test_stream_insert_at_index(self):
        """Insert at specific index."""
        template = Template(
            """{% for dom_id, user in users %}<li id="{{ dom_id }}">{{ user.name }}</li>{% endfor %}"""
        )

        stream = Stream(name="users")
        stream.insert(User(id=1, name="Alice"), at=5)

        tree = template.tree({"users": stream})
        comp = tree["0"]

        assert comp["stream"][0] == {"users-1": 5}  # inserts with at=5
        assert comp["stream"][1] == []  # no deletes

    def test_stream_with_limit(self):
        """Insert with limit - limit stored internally but not in 0.18.x wire format."""
        template = Template(
            """{% for dom_id, user in users %}<li id="{{ dom_id }}">{{ user.name }}</li>{% endfor %}"""
        )

        stream = Stream(name="users")
        stream.insert(User(id=1, name="Alice"), limit=100)

        tree = template.tree({"users": stream})
        comp = tree["0"]

        # 0.18.x wire format does not include limit
        assert comp["stream"][0] == {"users-1": -1}  # inserts
        assert comp["stream"][1] == []  # no deletes

    def test_stream_update_only(self):
        """Insert with update_only - note: not in wire format (client behavior)."""
        template = Template(
            """{% for dom_id, user in users %}<li id="{{ dom_id }}">{{ user.name }}</li>{% endfor %}"""
        )

        stream = Stream(name="users")
        stream.insert(User(id=1, name="Alice"), update_only=True)

        tree = template.tree({"users": stream})
        comp = tree["0"]

        # update_only is stored internally for potential future use
        assert comp["stream"][0] == {"users-1": -1}  # inserts
        assert comp["stream"][1] == []  # no deletes


class TestStreamDeletesAndReset:
    """Test delete and reset operations in templates."""

    def test_stream_with_deletes_only(self):
        """Stream with only delete operations."""
        template = Template(
            """{% for dom_id, user in users %}<li id="{{ dom_id }}">{{ user.name }}</li>{% endfor %}"""
        )

        stream = Stream(name="users")
        stream.delete_by_id("users-1")
        stream.delete_by_id("users-2")

        tree = template.tree({"users": stream})
        comp = tree["0"]

        # Should have stream metadata with deletes
        # Phoenix 0.18.x format: [{inserts}, [deletes]]
        assert "stream" in comp
        assert comp["stream"][0] == {}  # no inserts
        assert comp["stream"][1] == ["users-1", "users-2"]  # deletes

    def test_stream_reset(self):
        """Stream reset operation - sends items as inserts in 0.18.x."""
        template = Template(
            """{% for dom_id, user in users %}<li id="{{ dom_id }}">{{ user.name }}</li>{% endfor %}"""
        )

        stream = Stream(name="users")
        stream.reset([User(id=10, name="New")])

        tree = template.tree({"users": stream})
        comp = tree["0"]

        # 0.18.x format: [{inserts}, [deletes]] - reset handled client-side
        assert len(comp["stream"]) == 2
        assert comp["stream"][0] == {"users-10": -1}  # inserts
        assert comp["stream"][1] == []  # no deletes

    def test_stream_reset_empty(self):
        """Stream reset to empty - just clears in 0.18.x."""
        template = Template(
            """{% for dom_id, user in users %}<li id="{{ dom_id }}">{{ user.name }}</li>{% endfor %}"""
        )

        stream = Stream(name="users")
        stream.reset()

        tree = template.tree({"users": stream})
        comp = tree["0"]

        # 0.18.x format: [{inserts}, [deletes]]
        assert comp["stream"][0] == {}  # no inserts
        assert comp["stream"][1] == []  # no deletes


class TestStreamCombinedOperations:
    """Test combined operations (insert + delete + reset)."""

    def test_insert_and_delete(self):
        """Combine insert and delete operations."""
        template = Template(
            """{% for dom_id, user in users %}<li id="{{ dom_id }}">{{ user.name }}</li>{% endfor %}"""
        )

        stream = Stream(name="users")
        stream.insert(User(id=10, name="New User"))
        stream.delete_by_id("users-5")

        tree = template.tree({"users": stream})
        comp = tree["0"]

        # 0.18.x format: [{inserts}, [deletes]]
        assert comp["stream"][0] == {"users-10": -1}  # inserts
        assert comp["stream"][1] == ["users-5"]  # deletes

    def test_multiple_operations(self):
        """Multiple inserts and deletes."""
        template = Template(
            """{% for dom_id, user in users %}<li id="{{ dom_id }}">{{ user.name }}</li>{% endfor %}"""
        )

        stream = Stream(name="users")
        stream.insert(User(id=10, name="Append"))
        stream.insert(User(id=11, name="Prepend"), at=0)
        stream.delete_by_id("users-1")
        stream.delete_by_id("users-2")

        tree = template.tree({"users": stream})
        comp = tree["0"]

        # 0.18.x format: [{inserts}, [deletes]]
        assert len(comp["stream"][0]) == 2  # 2 inserts
        assert comp["stream"][0] == {"users-10": -1, "users-11": 0}
        assert len(comp["stream"][1]) == 2  # 2 deletes


class TestStreamEmpty:
    """Test empty stream scenarios."""

    def test_empty_stream_no_ops(self):
        """Empty stream with no operations."""
        template = Template(
            """{% for dom_id, user in users %}<li id="{{ dom_id }}">{{ user.name }}</li>{% endfor %}"""
        )

        stream = Stream(name="users")

        tree = template.tree({"users": stream})

        # Empty stream with no ops should result in empty string
        assert tree["0"] == ""

    def test_empty_stream_with_delete(self):
        """Empty stream but has delete operation."""
        template = Template(
            """{% for dom_id, user in users %}<li id="{{ dom_id }}">{{ user.name }}</li>{% endfor %}"""
        )

        stream = Stream(name="users")
        stream.delete_by_id("users-1")

        tree = template.tree({"users": stream})
        comp = tree["0"]

        # Should have stream metadata with delete
        # 0.18.x format: [{inserts}, [deletes]]
        assert "stream" in comp
        assert comp["stream"][0] == {}  # no inserts
        assert comp["stream"][1] == ["users-1"]  # deletes


class TestRegularForLoopUnchanged:
    """Ensure regular for loops still work correctly."""

    def test_regular_list_unchanged(self):
        """Regular list iteration produces standard format (no stream key)."""
        template = Template("""{% for user in users %}<li>{{ user.name }}</li>{% endfor %}""")

        users = [User(id=1, name="Alice"), User(id=2, name="Bob")]

        tree = template.tree({"users": users})
        comp = tree["0"]

        # Should NOT have stream key
        assert "stream" not in comp
        assert "s" in comp
        assert "d" in comp

    def test_regular_dict_list(self):
        """Regular dict list iteration."""
        template = Template("""{% for item in items %}<li>{{ item.name }}</li>{% endfor %}""")

        items = [{"name": "One"}, {"name": "Two"}]

        tree = template.tree({"items": items})
        comp = tree["0"]

        assert "stream" not in comp
        assert comp["d"] == [["One"], ["Two"]]
