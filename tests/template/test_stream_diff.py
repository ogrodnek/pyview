"""
Integration tests for Stream + Diff calculation.

Tests the full rendering pipeline: template.tree() -> calc_diff()
"""

from dataclasses import dataclass

from pyview.stream import Stream
from pyview.template.render_diff import calc_diff
from pyview.vendor.ibis import Template


@dataclass
class User:
    id: int
    name: str


class TestStreamDiffBasics:
    """Test basic stream diff scenarios."""

    def test_first_render_includes_full_tree(self):
        """First render should include statics, dynamics, and stream metadata."""
        template = Template(
            """{% for dom_id, user in users %}<div id="{{ dom_id }}">{{ user.name }}</div>{% endfor %}"""
        )

        stream = Stream([User(id=1, name="Alice")], name="users")
        tree = template.tree({"users": stream})

        # First render (no old tree) returns full tree
        diff = calc_diff({}, tree)

        assert "0" in diff
        comp = diff["0"]
        assert "s" in comp
        assert "d" in comp
        assert "stream" in comp

    def test_same_stream_no_ops_empty_diff(self):
        """Second render with no new operations should produce empty diff."""
        template = Template(
            """{% for dom_id, user in users %}<div id="{{ dom_id }}">{{ user.name }}</div>{% endfor %}"""
        )

        # First render
        stream = Stream([User(id=1, name="Alice")], name="users")
        tree1 = template.tree({"users": stream})

        # Second render - stream has no pending operations (they were consumed)
        tree2 = template.tree({"users": stream})

        diff = calc_diff(tree1, tree2)

        # No changes, empty diff
        assert diff == {}

    def test_new_insert_produces_diff(self):
        """New insert operation should appear in diff."""
        template = Template(
            """{% for dom_id, user in users %}<div id="{{ dom_id }}">{{ user.name }}</div>{% endfor %}"""
        )

        # First render
        stream = Stream([User(id=1, name="Alice")], name="users")
        tree1 = template.tree({"users": stream})

        # Add new item
        stream.insert(User(id=2, name="Bob"))
        tree2 = template.tree({"users": stream})

        diff = calc_diff(tree1, tree2)

        assert "0" in diff
        comp = diff["0"]
        assert "stream" in comp
        # 0.18.x format: [{dom_id: at}, [deletes]]
        assert comp["stream"][0] == {"users-2": -1}  # insert for Bob
        assert comp["stream"][1] == []  # no deletes
        # Should have dynamics for Bob
        assert "d" in comp

    def test_delete_operation_in_diff(self):
        """Delete operation should appear in diff."""
        template = Template(
            """{% for dom_id, user in users %}<div id="{{ dom_id }}">{{ user.name }}</div>{% endfor %}"""
        )

        # First render
        stream = Stream([User(id=1, name="Alice")], name="users")
        tree1 = template.tree({"users": stream})

        # Delete the item
        stream.delete_by_id("users-1")
        tree2 = template.tree({"users": stream})

        diff = calc_diff(tree1, tree2)

        assert "0" in diff
        comp = diff["0"]
        assert "stream" in comp
        # 0.18.x format: [{dom_id: at}, [deletes]]
        assert comp["stream"][0] == {}  # no inserts
        assert comp["stream"][1] == ["users-1"]  # delete

    def test_reset_operation_in_diff(self):
        """Reset operation sends items as inserts in 0.18.x."""
        template = Template(
            """{% for dom_id, user in users %}<div id="{{ dom_id }}">{{ user.name }}</div>{% endfor %}"""
        )

        # First render
        stream = Stream([User(id=1, name="Alice")], name="users")
        tree1 = template.tree({"users": stream})

        # Reset with new items
        stream.reset([User(id=10, name="New User")])
        tree2 = template.tree({"users": stream})

        diff = calc_diff(tree1, tree2)

        assert "0" in diff
        comp = diff["0"]
        assert "stream" in comp
        # 0.18.x format: [{dom_id: at}, [deletes]] - no reset flag
        assert len(comp["stream"]) == 2
        assert comp["stream"][0] == {"users-10": -1}  # inserts
        assert comp["stream"][1] == []  # no deletes


class TestStreamDiffMultipleRenders:
    """Test stream diff across multiple render cycles."""

    def test_sequential_inserts(self):
        """Each insert should appear in its own diff."""
        template = Template(
            """{% for dom_id, user in users %}<li id="{{ dom_id }}">{{ user.name }}</li>{% endfor %}"""
        )

        stream = Stream(name="users")

        # First render (empty)
        tree1 = template.tree({"users": stream})
        assert tree1["0"] == ""  # Empty stream

        # Insert first user
        stream.insert(User(id=1, name="Alice"))
        tree2 = template.tree({"users": stream})
        diff1 = calc_diff(tree1, tree2)

        assert "0" in diff1
        # 0.18.x format: [{dom_id: at}, [deletes]]
        assert "users-1" in diff1["0"]["stream"][0]

        # Insert second user
        stream.insert(User(id=2, name="Bob"))
        tree3 = template.tree({"users": stream})
        diff2 = calc_diff(tree2, tree3)

        assert "0" in diff2
        assert "users-2" in diff2["0"]["stream"][0]
        # Only Bob should be in this diff, not Alice
        assert len(diff2["0"]["stream"][0]) == 1

    def test_insert_then_delete_sequence(self):
        """Test insert followed by delete in separate renders."""
        template = Template(
            """{% for dom_id, user in users %}<li id="{{ dom_id }}">{{ user.name }}</li>{% endfor %}"""
        )

        stream = Stream([User(id=1, name="Alice")], name="users")
        tree1 = template.tree({"users": stream})

        # Now delete Alice
        stream.delete_by_id("users-1")
        tree2 = template.tree({"users": stream})
        diff = calc_diff(tree1, tree2)

        assert "0" in diff
        comp = diff["0"]
        assert "stream" in comp
        # 0.18.x format: [{dom_id: at}, [deletes]]
        assert comp["stream"][0] == {}  # no inserts (empty dict)
        assert comp["stream"][1] == ["users-1"]  # delete


class TestStreamDiffCombinedOps:
    """Test combined operations in a single diff."""

    def test_insert_and_delete_same_render(self):
        """Insert and delete in same render cycle."""
        template = Template(
            """{% for dom_id, user in users %}<li id="{{ dom_id }}">{{ user.name }}</li>{% endfor %}"""
        )

        stream = Stream([User(id=1, name="Alice")], name="users")
        tree1 = template.tree({"users": stream})

        # Same render: insert new user and delete old one
        stream.insert(User(id=2, name="Bob"))
        stream.delete_by_id("users-1")
        tree2 = template.tree({"users": stream})

        diff = calc_diff(tree1, tree2)

        assert "0" in diff
        comp = diff["0"]
        assert "stream" in comp
        # 0.18.x format: [{dom_id: at}, [deletes]]
        assert comp["stream"][0] == {"users-2": -1}  # Insert Bob
        # Delete Alice
        assert comp["stream"][1] == ["users-1"]


class TestStreamDiffEdgeCases:
    """Test edge cases in stream diff calculation."""

    def test_empty_to_populated(self):
        """Diff from empty stream to populated."""
        template = Template(
            """{% for dom_id, user in users %}<li id="{{ dom_id }}">{{ user.name }}</li>{% endfor %}"""
        )

        # Empty stream first
        stream = Stream(name="users")
        tree1 = template.tree({"users": stream})

        # Then populate
        stream.insert(User(id=1, name="Alice"))
        stream.insert(User(id=2, name="Bob"))
        tree2 = template.tree({"users": stream})

        diff = calc_diff(tree1, tree2)

        assert "0" in diff
        comp = diff["0"]
        assert "stream" in comp
        # 0.18.x format: [{dom_id: at}, [deletes]]
        assert len(comp["stream"][0]) == 2
        # Should include statics since it's first time with content
        assert "s" in comp

    def test_populated_to_empty_via_reset(self):
        """Diff from populated stream to empty via reset."""
        template = Template(
            """{% for dom_id, user in users %}<li id="{{ dom_id }}">{{ user.name }}</li>{% endfor %}"""
        )

        stream = Stream([User(id=1, name="Alice")], name="users")
        tree1 = template.tree({"users": stream})

        # Reset to empty
        stream.reset()
        tree2 = template.tree({"users": stream})

        diff = calc_diff(tree1, tree2)

        assert "0" in diff
        comp = diff["0"]
        assert "stream" in comp
        # 0.18.x format: [{dom_id: at}, [deletes]] - no reset flag
        assert comp["stream"][0] == {}  # no inserts (empty dict)
        assert len(comp["stream"]) == 2
        assert comp["stream"][1] == []  # no deletes

    def test_stream_with_surrounding_content(self):
        """Stream with other dynamic content should diff correctly."""
        template = Template(
            """<h1>{{ title }}</h1><ul>{% for dom_id, user in users %}<li id="{{ dom_id }}">{{ user.name }}</li>{% endfor %}</ul>"""
        )

        stream = Stream([User(id=1, name="Alice")], name="users")
        tree1 = template.tree({"title": "Users", "users": stream})

        # Change title and add user
        stream.insert(User(id=2, name="Bob"))
        tree2 = template.tree({"title": "Active Users", "users": stream})

        diff = calc_diff(tree1, tree2)

        # Should have both title change and stream update
        assert "0" in diff  # title
        assert diff["0"] == "Active Users"
        assert "1" in diff  # stream
        assert "stream" in diff["1"]

    def test_nested_template_with_stream(self):
        """Stream inside nested template structure."""
        template = Template(
            """{% if show %}<div>{% for dom_id, user in users %}<span id="{{ dom_id }}">{{ user.name }}</span>{% endfor %}</div>{% endif %}"""
        )

        stream = Stream([User(id=1, name="Alice")], name="users")
        tree1 = template.tree({"show": True, "users": stream})

        # Add user
        stream.insert(User(id=2, name="Bob"))
        tree2 = template.tree({"show": True, "users": stream})

        diff = calc_diff(tree1, tree2)

        # Stream is nested: "0" is the if block, "0" inside that is the for loop
        assert "0" in diff
        assert "0" in diff["0"]
        assert "stream" in diff["0"]["0"]


class TestStreamDiffPreservesRegularLoops:
    """Ensure regular (non-stream) loops still work correctly."""

    def test_regular_loop_no_stream_key(self):
        """Regular list loop should not have stream key in diff."""
        template = Template("""{% for user in users %}<li>{{ user.name }}</li>{% endfor %}""")

        users1 = [User(id=1, name="Alice")]
        tree1 = template.tree({"users": users1})

        users2 = [User(id=1, name="Alice"), User(id=2, name="Bob")]
        tree2 = template.tree({"users": users2})

        diff = calc_diff(tree1, tree2)

        assert "0" in diff
        # Should NOT have stream key
        assert "stream" not in diff["0"]
        # Should have dynamics
        assert "d" in diff["0"]
