"""
T-string stream tests.

These tests verify the StreamList and stream_for functionality that will work
with T-string templates on Python 3.14+. The tests here use mock Template objects
to simulate the T-string behavior.
"""

import sys
from dataclasses import dataclass

import pytest

# We can't import from live_view_template.py on Python < 3.14 because it has
# an import guard. So we test the underlying logic with mock objects.

pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 14), reason="T-string template tests require Python 3.14+"
)


# Skip all tests in this file on Python < 3.14
# The actual T-string syntax tests are in a separate file that gets ignored by conftest


@pytest.fixture
def skip_if_no_tstring():
    """Skip test if T-strings not available."""
    if sys.version_info < (3, 14):
        pytest.skip("T-string support requires Python 3.14+")


class TestStreamListLogic:
    """Test StreamList and stream_for logic without actual T-strings."""

    def test_stream_list_creation(self, skip_if_no_tstring):
        """StreamList can be created with items and stream reference."""
        from pyview.stream import Stream
        from pyview.template.live_view_template import StreamList

        stream = Stream(name="users")
        items = ["item1", "item2"]

        sl = StreamList(items=items, stream=stream)

        assert sl.items == items
        assert sl.stream is stream

    def test_stream_for_function(self, skip_if_no_tstring):
        """stream_for() creates StreamList from stream iteration."""
        from pyview.stream import Stream
        from pyview.template.live_view_template import StreamList, stream_for

        @dataclass
        class User:
            id: int
            name: str

        users = [User(id=1, name="Alice"), User(id=2, name="Bob")]
        stream = Stream(users, name="users")

        # Use actual t-string (only runs on Python 3.14+)
        result = stream_for(stream, lambda dom_id, user: t"<div>{user.name}</div>")

        assert isinstance(result, StreamList)
        assert len(result.items) == 2
        assert result.stream is stream

    def test_process_stream_list_basic(self, skip_if_no_tstring):
        """_process_stream_list produces correct wire format."""
        from pyview.stream import Stream
        from pyview.template.live_view_template import LiveViewTemplate, StreamList

        @dataclass
        class User:
            id: int
            name: str

        users = [User(id=1, name="Alice")]
        stream = Stream(users, name="users")

        # Create StreamList with simple string items (not Template objects)
        sl = StreamList(items=["rendered_item"], stream=stream)

        result = LiveViewTemplate._process_stream_list(sl)

        # Should have stream metadata
        # 0.20 format: [stream_ref, [[dom_id, at, limit], ...], [deletes]]
        assert "stream" in result
        assert result["stream"][0] == "users"  # stream ref
        assert result["stream"][1] == [["users-1", -1, None]]  # inserts
        assert result["stream"][2] == []  # no deletes

    def test_process_stream_list_with_operations(self, skip_if_no_tstring):
        """_process_stream_list includes all stream operations."""
        from pyview.stream import Stream
        from pyview.template.live_view_template import LiveViewTemplate, StreamList

        stream = Stream(name="users")
        stream.insert({"id": 1, "name": "Alice"})
        stream.insert({"id": 2, "name": "Bob"}, at=0)
        stream.delete_by_id("users-old")

        # Items from iteration
        items = ["item1", "item2"]
        sl = StreamList(items=items, stream=stream)

        result = LiveViewTemplate._process_stream_list(sl)

        # 0.20 format: [stream_ref, [[dom_id, at, limit], ...], [deletes]]
        stream_meta = result["stream"]
        assert stream_meta[0] == "users"  # stream ref
        assert len(stream_meta[1]) == 2  # 2 inserts
        assert stream_meta[1] == [["users-1", -1, None], ["users-2", 0, None]]
        assert stream_meta[2] == ["users-old"]  # deletes

    def test_process_stream_list_empty_with_delete(self, skip_if_no_tstring):
        """Empty stream with delete operations."""
        from pyview.stream import Stream
        from pyview.template.live_view_template import LiveViewTemplate, StreamList

        stream = Stream(name="users")
        stream.delete_by_id("users-1")

        sl = StreamList(items=[], stream=stream)
        result = LiveViewTemplate._process_stream_list(sl)

        # 0.20 format: [stream_ref, [[dom_id, at, limit], ...], [deletes]]
        assert "stream" in result
        assert result["stream"][0] == "users"  # stream ref
        assert result["stream"][1] == []  # no inserts
        assert result["stream"][2] == ["users-1"]  # deletes

    def test_process_stream_list_reset(self, skip_if_no_tstring):
        """Stream reset operation - sends items with reset flag true."""
        from pyview.stream import Stream
        from pyview.template.live_view_template import LiveViewTemplate, StreamList

        stream = Stream(name="users")
        stream.reset([{"id": 10, "name": "New"}])

        items = ["new_item"]
        sl = StreamList(items=items, stream=stream)
        result = LiveViewTemplate._process_stream_list(sl)

        # 0.20 format: [stream_ref, [[dom_id, at, limit], ...], [deletes], reset]
        assert len(result["stream"]) == 4
        assert result["stream"][0] == "users"  # stream ref
        assert result["stream"][1] == [["users-10", -1, None]]  # inserts
        assert result["stream"][2] == []  # no deletes
        assert result["stream"][3] is True  # reset flag

    def test_process_stream_list_empty_no_ops(self, skip_if_no_tstring):
        """Empty stream with no operations returns empty string."""
        from pyview.stream import Stream
        from pyview.template.live_view_template import LiveViewTemplate, StreamList

        stream = Stream(name="users")
        sl = StreamList(items=[], stream=stream)
        result = LiveViewTemplate._process_stream_list(sl)

        assert result == ""


class TestTreeToHtml:
    """Test TStringRenderedContent._tree_to_html method."""

    def test_tree_to_html_comprehension_with_statics_and_dynamics(self, skip_if_no_tstring):
        """Comprehension with statics and dynamics renders correctly.

        This tests the bug fix where stream items were being rendered as
        Python list representations like ['tasks-1', 'Learn...', 'tasks-1']
        instead of properly interleaving statics and dynamics.
        """
        from pyview.template.template_view import TStringRenderedContent

        # Simulate a comprehension tree for:
        # {% for dom_id, task in tasks %}
        #   <div id="{dom_id}">{task.text}</div>
        # {% endfor %}
        tree = {
            "s": ['<div id="', '">', "</div>"],
            "d": [
                ["tasks-1", "Learn about streams"],
                ["tasks-2", "Try append"],
            ],
        }

        content = TStringRenderedContent(tree)
        html = content.text()

        # Should properly interleave statics and dynamics
        assert '<div id="tasks-1">Learn about streams</div>' in html
        assert '<div id="tasks-2">Try append</div>' in html
        # Should NOT have Python list representation
        assert "['tasks-1'" not in html
        assert "['tasks-2'" not in html

    def test_tree_to_html_comprehension_multiple_dynamics(self, skip_if_no_tstring):
        """Comprehension with multiple dynamics per item renders correctly."""
        from pyview.template.template_view import TStringRenderedContent

        # Template with 3 interpolations per item:
        # <div id="{dom_id}" class="item"><span>{text}</span><button data-id="{dom_id}">X</button></div>
        tree = {
            "s": ['<div id="', '" class="item"><span>', '</span><button data-id="', '">X</button></div>'],
            "d": [
                ["item-1", "First item", "item-1"],
                ["item-2", "Second item", "item-2"],
            ],
        }

        content = TStringRenderedContent(tree)
        html = content.text()

        expected1 = '<div id="item-1" class="item"><span>First item</span><button data-id="item-1">X</button></div>'
        expected2 = '<div id="item-2" class="item"><span>Second item</span><button data-id="item-2">X</button></div>'

        assert expected1 in html
        assert expected2 in html

    def test_tree_to_html_nested_dict_in_dynamics(self, skip_if_no_tstring):
        """Nested dict structures in dynamics are recursively processed."""
        from pyview.template.template_view import TStringRenderedContent

        tree = {
            "s": ["<ul>", "</ul>"],
            "d": [
                [{"s": ["<li>", "</li>"], "0": "Item A"}],
                [{"s": ["<li>", "</li>"], "0": "Item B"}],
            ],
        }

        content = TStringRenderedContent(tree)
        html = content.text()

        assert "<ul><li>Item A</li></ul>" in html or "<li>Item A</li>" in html

    def test_tree_to_html_simple_template(self, skip_if_no_tstring):
        """Simple template without comprehension renders correctly."""
        from pyview.template.template_view import TStringRenderedContent

        tree = {
            "s": ["<h1>", "</h1>"],
            "0": "Hello World",
        }

        content = TStringRenderedContent(tree)
        html = content.text()

        assert html == "<h1>Hello World</h1>"

    def test_tree_to_html_empty_comprehension(self, skip_if_no_tstring):
        """Empty comprehension renders empty string."""
        from pyview.template.template_view import TStringRenderedContent

        tree = {
            "s": ["<div>", "</div>"],
            "d": [],
        }

        content = TStringRenderedContent(tree)
        html = content.text()

        assert html == ""


class TestStreamForIntegration:
    """Integration tests for stream_for with actual t-string templates."""

    def test_stream_for_renders_to_html_correctly(self, skip_if_no_tstring):
        """stream_for() result renders to proper HTML via text()."""
        from pyview.stream import Stream
        from pyview.template.live_view_template import LiveViewTemplate, stream_for
        from pyview.template.template_view import TStringRenderedContent

        @dataclass
        class Task:
            id: int
            text: str

        tasks = [Task(id=1, text="First"), Task(id=2, text="Second")]
        stream = Stream(tasks, name="tasks")

        # Process a t-string template with stream_for
        template = t"""<div id="tasks" phx-update="stream">{
            stream_for(stream, lambda dom_id, task: t'<div id="{dom_id}">{task.text}</div>')
        }</div>"""

        tree = LiveViewTemplate.process(template)
        content = TStringRenderedContent(tree)
        html = content.text()

        # Verify correct HTML output
        assert '<div id="tasks-1">First</div>' in html
        assert '<div id="tasks-2">Second</div>' in html
        # Should NOT contain Python list repr
        assert "['tasks-1'" not in html
