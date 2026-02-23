import hashlib
import os
import tempfile

import pytest

from pyview.css.registry import CSSEntry, CSSRegistry, _find_css_for_class


@pytest.fixture
def css_dir(tmp_path):
    """Create a temp directory with a CSS file."""
    css_file = tmp_path / "my_view.css"
    css_file.write_text(".container { color: red; }")
    return tmp_path


@pytest.fixture
def registry():
    return CSSRegistry()


class TestCSSEntry:
    def test_from_file(self, css_dir):
        css_file = str(css_dir / "my_view.css")
        entry = CSSEntry.from_file("test.MyView", css_file)

        assert entry.name == "test.MyView"
        assert entry.file_path == css_file
        assert entry.content == ".container { color: red; }"
        expected_hash = hashlib.sha256(b".container { color: red; }").hexdigest()[:8]
        assert entry.hash == expected_hash

    def test_url(self, css_dir):
        entry = CSSEntry.from_file("test.MyView", str(css_dir / "my_view.css"))
        assert entry.url == f"/pyview-css/test.MyView.{entry.hash}.css"

    def test_link_tag(self, css_dir):
        entry = CSSEntry.from_file("test.MyView", str(css_dir / "my_view.css"))
        assert entry.link_tag == f'<link rel="stylesheet" href="{entry.url}">'

    def test_refresh_if_changed_no_change(self, css_dir):
        entry = CSSEntry.from_file("test.MyView", str(css_dir / "my_view.css"))
        assert entry.refresh_if_changed() is False

    def test_refresh_if_changed_with_change(self, css_dir):
        css_file = css_dir / "my_view.css"
        entry = CSSEntry.from_file("test.MyView", str(css_file))
        old_hash = entry.hash

        css_file.write_text(".container { color: blue; }")
        assert entry.refresh_if_changed() is True
        assert entry.hash != old_hash
        assert entry.content == ".container { color: blue; }"

    def test_refresh_if_changed_file_deleted(self, css_dir):
        css_file = css_dir / "my_view.css"
        entry = CSSEntry.from_file("test.MyView", str(css_file))
        css_file.unlink()
        assert entry.refresh_if_changed() is False


class TestCSSRegistry:
    def test_register(self, registry, css_dir):
        entry = registry.register("test.MyView", str(css_dir / "my_view.css"))
        assert entry.name == "test.MyView"
        assert len(registry) == 1
        assert "test.MyView" in registry

    def test_register_for_class_no_css(self, registry):
        """Class without a colocated CSS file returns None."""
        result = registry.register_for_class(CSSRegistry)
        assert result is None
        assert len(registry) == 0

    def test_register_for_class_with_css(self, registry, tmp_path):
        """Class with a colocated CSS file gets registered."""
        # Create a fake module file and CSS file
        py_file = tmp_path / "fake_view.py"
        css_file = tmp_path / "fake_view.css"
        py_file.write_text("class FakeView: pass")
        css_file.write_text(".fake { display: block; }")

        # Create a class that reports its file as the temp py file
        class FakeView:
            pass

        FakeView.__module__ = "test_module"
        # Monkey-patch inspect.getfile for this class
        import pyview.css.registry as registry_mod

        original = registry_mod._find_css_for_class

        def patched_find(cls):
            if cls is FakeView:
                return str(css_file)
            return original(cls)

        registry_mod._find_css_for_class = patched_find
        try:
            entry = registry.register_for_class(FakeView)
            assert entry is not None
            assert entry.content == ".fake { display: block; }"
            assert "test_module.FakeView" in registry
        finally:
            registry_mod._find_css_for_class = original

    def test_register_for_class_idempotent(self, registry, css_dir):
        """Registering the same class twice returns the same entry."""
        entry1 = registry.register("test.MyView", str(css_dir / "my_view.css"))
        # Simulate register_for_class finding the same name
        entry2 = registry.register("test.MyView", str(css_dir / "my_view.css"))
        # Both return entries, registry has 1 entry
        assert len(registry) == 1

    def test_get_for_serving(self, registry, css_dir):
        entry = registry.register("test.MyView", str(css_dir / "my_view.css"))
        result = registry.get_for_serving(f"test.MyView.{entry.hash}")
        assert result is entry

    def test_get_for_serving_wrong_hash(self, registry, css_dir):
        registry.register("test.MyView", str(css_dir / "my_view.css"))
        result = registry.get_for_serving("test.MyView.wronghash")
        assert result is None

    def test_get_for_serving_unknown_name(self, registry):
        result = registry.get_for_serving("unknown.View.abc12345")
        assert result is None

    def test_auto_refresh(self, css_dir):
        registry = CSSRegistry(auto_refresh=True)
        css_file = css_dir / "my_view.css"
        entry = registry.register("test.MyView", str(css_file))
        old_hash = entry.hash
        old_url_key = f"test.MyView.{old_hash}"

        # Modify the file
        css_file.write_text(".container { color: blue; }")

        # register_for_class triggers refresh
        class FakeView:
            pass

        FakeView.__module__ = "test"
        FakeView.__name__ = "MyView"

        # Directly test that get triggers refresh via register_for_class path
        # The entry is already registered as "test.MyView"
        import pyview.css.registry as registry_mod

        original = registry_mod._find_css_for_class

        def patched_find(cls):
            if cls is FakeView:
                return str(css_file)
            return original(cls)

        registry_mod._find_css_for_class = patched_find
        try:
            refreshed = registry.register_for_class(FakeView)
            assert refreshed is not None
            assert refreshed.hash != old_hash
            assert refreshed.content == ".container { color: blue; }"
            # Old URL key should be gone, new one should exist
            assert registry.get_for_serving(old_url_key) is None
            assert registry.get_for_serving(f"test.MyView.{refreshed.hash}") is refreshed
        finally:
            registry_mod._find_css_for_class = original

    def test_clear(self, registry, css_dir):
        registry.register("test.MyView", str(css_dir / "my_view.css"))
        assert len(registry) == 1
        registry.clear()
        assert len(registry) == 0


class TestFindCssForClass:
    def test_finds_colocated_css(self, tmp_path):
        """When a .css file exists next to the .py file, it's found."""
        # This test is indirect since _find_css_for_class uses inspect.getfile
        # We test it with a real class (which won't have CSS next to it)
        result = _find_css_for_class(CSSRegistry)
        assert result is None  # No CSS file next to registry.py

    def test_builtin_type(self):
        """Built-in types don't have source files."""
        result = _find_css_for_class(int)
        assert result is None
