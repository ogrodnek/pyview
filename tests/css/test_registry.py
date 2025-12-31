"""
Tests for CSSRegistry.

Verifies CSS file discovery, content hashing, and registration.
"""

import tempfile
from pathlib import Path

import pytest

from pyview.css.registry import CSSEntry, CSSRegistry


class TestCSSEntry:
    """Tests for CSSEntry dataclass."""

    def test_from_file_creates_entry_with_hash(self, tmp_path):
        """Test that from_file creates an entry with correct hash."""
        css_file = tmp_path / "test.css"
        css_file.write_text(".test { color: blue; }")

        entry = CSSEntry.from_file("test", str(css_file))

        assert entry.name == "test"
        assert entry.file_path == str(css_file)
        assert entry.content == ".test { color: blue; }"
        assert len(entry.hash) == 8  # First 8 chars of sha256

    def test_hash_changes_with_content(self, tmp_path):
        """Test that hash changes when content changes."""
        css_file = tmp_path / "test.css"

        css_file.write_text(".test { color: blue; }")
        entry1 = CSSEntry.from_file("test", str(css_file))

        css_file.write_text(".test { color: red; }")
        entry2 = CSSEntry.from_file("test", str(css_file))

        assert entry1.hash != entry2.hash

    def test_url_includes_name_and_hash(self, tmp_path):
        """Test that URL is correctly formatted."""
        css_file = tmp_path / "test.css"
        css_file.write_text(".test {}")

        entry = CSSEntry.from_file("views.MyView", str(css_file))

        assert entry.url == f"/pyview-css/views.MyView.{entry.hash}.css"

    def test_link_tag_is_correct_html(self, tmp_path):
        """Test that link_tag produces valid HTML."""
        css_file = tmp_path / "test.css"
        css_file.write_text(".test {}")

        entry = CSSEntry.from_file("test", str(css_file))

        assert entry.link_tag == f'<link rel="stylesheet" href="{entry.url}">'

    def test_refresh_if_changed_detects_changes(self, tmp_path):
        """Test that refresh_if_changed updates content when file changes."""
        css_file = tmp_path / "test.css"
        css_file.write_text(".test { color: blue; }")

        entry = CSSEntry.from_file("test", str(css_file))
        original_hash = entry.hash

        # Modify the file
        css_file.write_text(".test { color: red; }")

        assert entry.refresh_if_changed() is True
        assert entry.hash != original_hash
        assert entry.content == ".test { color: red; }"

    def test_refresh_if_changed_returns_false_when_unchanged(self, tmp_path):
        """Test that refresh_if_changed returns False when file hasn't changed."""
        css_file = tmp_path / "test.css"
        css_file.write_text(".test { color: blue; }")

        entry = CSSEntry.from_file("test", str(css_file))

        assert entry.refresh_if_changed() is False


class TestCSSRegistry:
    """Tests for CSSRegistry."""

    def test_register_creates_entry(self, tmp_path):
        """Test that register creates and stores an entry."""
        css_file = tmp_path / "test.css"
        css_file.write_text(".test {}")

        registry = CSSRegistry()
        entry = registry.register("test", str(css_file))

        assert entry.name == "test"
        assert registry.get("test") == entry

    def test_get_for_serving_finds_by_hash(self, tmp_path):
        """Test that get_for_serving finds entry by name.hash."""
        css_file = tmp_path / "test.css"
        css_file.write_text(".test {}")

        registry = CSSRegistry()
        entry = registry.register("test", str(css_file))

        found = registry.get_for_serving(f"test.{entry.hash}")
        assert found == entry

    def test_get_for_serving_returns_none_for_wrong_hash(self, tmp_path):
        """Test that get_for_serving returns None for wrong hash."""
        css_file = tmp_path / "test.css"
        css_file.write_text(".test {}")

        registry = CSSRegistry()
        registry.register("test", str(css_file))

        assert registry.get_for_serving("test.wronghash") is None

    def test_has_checks_existence(self, tmp_path):
        """Test that has() checks if entry exists."""
        css_file = tmp_path / "test.css"
        css_file.write_text(".test {}")

        registry = CSSRegistry()
        assert registry.has("test") is False

        registry.register("test", str(css_file))
        assert registry.has("test") is True

    def test_register_for_class_discovers_css_file(self, tmp_path):
        """Test that register_for_class discovers colocated CSS."""
        # Create a module structure
        module_dir = tmp_path / "views"
        module_dir.mkdir()
        (module_dir / "__init__.py").write_text("")

        # Create a view file and CSS
        view_file = module_dir / "my_view.py"
        view_file.write_text(
            """
class MyView:
    pass
"""
        )
        css_file = module_dir / "my_view.css"
        css_file.write_text(".my-view {}")

        # Import the class
        import sys

        sys.path.insert(0, str(tmp_path))
        try:
            from views.my_view import MyView

            registry = CSSRegistry()
            entry = registry.register_for_class(MyView)

            assert entry is not None
            assert "my_view" in entry.file_path
            assert entry.content == ".my-view {}"
        finally:
            sys.path.remove(str(tmp_path))
            # Clean up imported module
            if "views" in sys.modules:
                del sys.modules["views"]
            if "views.my_view" in sys.modules:
                del sys.modules["views.my_view"]

    def test_register_for_class_returns_none_without_css(self, tmp_path):
        """Test that register_for_class returns None when no CSS exists."""
        # Create a module structure without CSS
        module_dir = tmp_path / "views2"
        module_dir.mkdir()
        (module_dir / "__init__.py").write_text("")

        view_file = module_dir / "no_css_view.py"
        view_file.write_text(
            """
class NoCSSView:
    pass
"""
        )

        import sys

        sys.path.insert(0, str(tmp_path))
        try:
            from views2.no_css_view import NoCSSView

            registry = CSSRegistry()
            entry = registry.register_for_class(NoCSSView)

            assert entry is None
        finally:
            sys.path.remove(str(tmp_path))
            if "views2" in sys.modules:
                del sys.modules["views2"]
            if "views2.no_css_view" in sys.modules:
                del sys.modules["views2.no_css_view"]

    def test_auto_refresh_updates_on_get(self, tmp_path):
        """Test that auto_refresh=True updates entries on get()."""
        css_file = tmp_path / "test.css"
        css_file.write_text(".test { color: blue; }")

        registry = CSSRegistry(auto_refresh=True)
        entry = registry.register("test", str(css_file))
        original_hash = entry.hash

        # Modify file
        css_file.write_text(".test { color: red; }")

        # Get should refresh
        refreshed = registry.get("test")
        assert refreshed.hash != original_hash
        assert refreshed.content == ".test { color: red; }"

    def test_clear_removes_all_entries(self, tmp_path):
        """Test that clear() removes all entries."""
        css_file = tmp_path / "test.css"
        css_file.write_text(".test {}")

        registry = CSSRegistry()
        registry.register("test1", str(css_file))
        registry.register("test2", str(css_file))

        assert len(registry) == 2

        registry.clear()

        assert len(registry) == 0
        assert registry.get("test1") is None
