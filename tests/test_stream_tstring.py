"""
T-string stream tests.

These tests verify the StreamList and stream_for functionality that will work
with T-string templates on Python 3.14+. The tests here use mock Template objects
to simulate the T-string behavior.
"""

import sys
import pytest
from dataclasses import dataclass

# We can't import from live_view_template.py on Python < 3.14 because it has
# an import guard. So we test the underlying logic with mock objects.

pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 14),
    reason="T-string template tests require Python 3.14+"
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
        from pyview.template.live_view_template import StreamList
        from pyview.stream import Stream

        stream = Stream(name="users")
        items = ["item1", "item2"]

        sl = StreamList(items=items, stream=stream)

        assert sl.items == items
        assert sl.stream is stream

    def test_stream_for_function(self, skip_if_no_tstring):
        """stream_for() creates StreamList from stream iteration."""
        from pyview.template.live_view_template import StreamList, stream_for
        from pyview.stream import Stream

        @dataclass
        class User:
            id: int
            name: str

        users = [User(id=1, name="Alice"), User(id=2, name="Bob")]
        stream = Stream(users, name="users")

        # Use a simple render function (not a t-string)
        result = stream_for(stream, lambda dom_id, user: f"<div>{user.name}</div>")

        assert isinstance(result, StreamList)
        assert len(result.items) == 2
        assert result.stream is stream

    def test_process_stream_list_basic(self, skip_if_no_tstring):
        """_process_stream_list produces correct wire format."""
        from pyview.template.live_view_template import StreamList, LiveViewTemplate
        from pyview.stream import Stream

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
        # 0.18.x format: [{dom_id: at}, [deletes]]
        assert "stream" in result
        assert result["stream"][0] == {"users-1": -1}  # inserts
        assert result["stream"][1] == []  # no deletes

    def test_process_stream_list_with_operations(self, skip_if_no_tstring):
        """_process_stream_list includes all stream operations."""
        from pyview.template.live_view_template import StreamList, LiveViewTemplate
        from pyview.stream import Stream

        stream = Stream(name="users")
        stream.insert({"id": 1, "name": "Alice"})
        stream.insert({"id": 2, "name": "Bob"}, at=0)
        stream.delete_by_id("users-old")

        # Items from iteration
        items = ["item1", "item2"]
        sl = StreamList(items=items, stream=stream)

        result = LiveViewTemplate._process_stream_list(sl)

        # 0.18.x format: [{dom_id: at}, [deletes]]
        stream_meta = result["stream"]
        assert len(stream_meta[0]) == 2  # 2 inserts
        assert stream_meta[0] == {"users-1": -1, "users-2": 0}
        assert stream_meta[1] == ["users-old"]  # deletes

    def test_process_stream_list_empty_with_delete(self, skip_if_no_tstring):
        """Empty stream with delete operations."""
        from pyview.template.live_view_template import StreamList, LiveViewTemplate
        from pyview.stream import Stream

        stream = Stream(name="users")
        stream.delete_by_id("users-1")

        sl = StreamList(items=[], stream=stream)
        result = LiveViewTemplate._process_stream_list(sl)

        # 0.18.x format: [{dom_id: at}, [deletes]]
        assert "stream" in result
        assert result["stream"][0] == {}  # no inserts
        assert result["stream"][1] == ["users-1"]  # deletes

    def test_process_stream_list_reset(self, skip_if_no_tstring):
        """Stream reset operation - sends items as inserts in 0.18.x."""
        from pyview.template.live_view_template import StreamList, LiveViewTemplate
        from pyview.stream import Stream

        stream = Stream(name="users")
        stream.reset([{"id": 10, "name": "New"}])

        items = ["new_item"]
        sl = StreamList(items=items, stream=stream)
        result = LiveViewTemplate._process_stream_list(sl)

        # 0.18.x format: [{dom_id: at}, [deletes]] - no reset flag
        assert len(result["stream"]) == 2
        assert result["stream"][0] == {"users-10": -1}  # inserts
        assert result["stream"][1] == []  # no deletes

    def test_process_stream_list_empty_no_ops(self, skip_if_no_tstring):
        """Empty stream with no operations returns empty string."""
        from pyview.template.live_view_template import StreamList, LiveViewTemplate
        from pyview.stream import Stream

        stream = Stream(name="users")
        sl = StreamList(items=[], stream=stream)
        result = LiveViewTemplate._process_stream_list(sl)

        assert result == ""
