"""
Tests for CSS render hook.
"""

from unittest.mock import MagicMock, patch

import pytest

from pyview.css import CSSRegistry
from pyview.css.registry import CSSEntry
from pyview.render_hooks.base import HookContext
from pyview.render_hooks.css import CSSRenderHook


class MockSocket:
    """Mock socket for testing."""

    def __init__(self):
        self.loaded_css = set()
        self.components = MagicMock()
        self.components.collect_component_css = MagicMock(return_value=[])


class MockView:
    """Mock view class for testing."""

    pass


class TestCSSRenderHook:
    """Tests for CSSRenderHook."""

    @pytest.fixture
    def mock_entry(self, tmp_path):
        """Create a mock CSS entry."""
        css_file = tmp_path / "mock_view.css"
        css_file.write_text(".mock-view { color: blue; }")
        return CSSEntry.from_file("test.MockView", str(css_file))

    @pytest.fixture
    def registry(self, mock_entry):
        """Create a registry with a test CSS entry."""
        reg = CSSRegistry()
        # Directly add to internal storage to avoid file discovery
        reg._entries["test.MockView"] = mock_entry
        reg._by_url_key[f"test.MockView.{mock_entry.hash}"] = mock_entry
        return reg

    @pytest.fixture
    def hook(self, registry):
        """Create a CSS render hook."""
        return CSSRenderHook(registry)

    @pytest.mark.asyncio
    async def test_before_render_adds_css_for_connected_socket(
        self, hook, registry, mock_entry
    ):
        """Test that before_render adds CSS link for connected socket."""
        mock_view = MagicMock()
        mock_view.__class__.__module__ = "test"
        mock_view.__class__.__name__ = "MockView"

        mock_socket = MockSocket()
        ctx = HookContext(view=mock_view, socket=mock_socket, is_connected=True)

        # Mock register_for_class to return the existing entry
        with patch.object(registry, "register_for_class", return_value=mock_entry):
            await hook.before_render(ctx)

        assert len(ctx.prepend_content) == 1
        assert '<link rel="stylesheet"' in ctx.prepend_content[0]

    @pytest.mark.asyncio
    async def test_before_render_skips_already_loaded_css(
        self, hook, registry, mock_entry
    ):
        """Test that before_render doesn't add CSS that's already loaded."""
        mock_view = MagicMock()
        mock_view.__class__.__module__ = "test"
        mock_view.__class__.__name__ = "MockView"

        mock_socket = MockSocket()
        mock_socket.loaded_css.add(mock_entry.url)  # Already loaded

        ctx = HookContext(view=mock_view, socket=mock_socket, is_connected=True)

        with patch.object(registry, "register_for_class", return_value=mock_entry):
            await hook.before_render(ctx)

        assert len(ctx.prepend_content) == 0

    def test_transform_tree_prepends_css_to_statics(self, hook):
        """Test that transform_tree prepends CSS to first static."""
        mock_view = MagicMock()
        mock_socket = MockSocket()

        ctx = HookContext(view=mock_view, socket=mock_socket, is_connected=True)
        ctx.add_prepend('<link rel="stylesheet" href="/test.css">')

        tree = {"s": ["<div>", "</div>"], "0": "content"}
        result = hook.transform_tree(tree, ctx)

        assert result["s"][0].startswith('<link rel="stylesheet"')
        assert "<div>" in result["s"][0]

    def test_transform_tree_collects_component_css(self, hook, registry, tmp_path):
        """Test that transform_tree collects component CSS."""
        mock_view = MagicMock()
        mock_socket = MockSocket()
        mock_socket.components.collect_component_css.return_value = [
            '<link rel="stylesheet" href="/component.css">'
        ]

        ctx = HookContext(view=mock_view, socket=mock_socket, is_connected=True)

        tree = {"s": ["<div>", "</div>"]}
        result = hook.transform_tree(tree, ctx)

        mock_socket.components.collect_component_css.assert_called_once()
        assert "/component.css" in result["s"][0]

    @pytest.mark.asyncio
    async def test_on_initial_render_adds_css_to_head(
        self, hook, registry, mock_entry
    ):
        """Test that on_initial_render adds CSS to additional_head_elements."""
        mock_view = MagicMock()
        mock_view.__class__.__module__ = "test"
        mock_view.__class__.__name__ = "MockView"

        mock_socket = MockSocket()
        ctx = HookContext(view=mock_view, socket=mock_socket, is_connected=False)

        template_context = {"additional_head_elements": []}

        with patch.object(registry, "register_for_class", return_value=mock_entry):
            await hook.on_initial_render(ctx, template_context)

        assert len(template_context["additional_head_elements"]) == 1

    @pytest.mark.asyncio
    async def test_on_initial_render_includes_component_css(
        self, hook, registry, mock_entry
    ):
        """Test that on_initial_render includes component CSS."""
        mock_view = MagicMock()
        mock_view.__class__.__module__ = "test"
        mock_view.__class__.__name__ = "MockView"

        mock_socket = MockSocket()
        mock_socket.components.collect_component_css.return_value = [
            '<link rel="stylesheet" href="/component.css">'
        ]

        ctx = HookContext(view=mock_view, socket=mock_socket, is_connected=False)

        template_context = {"additional_head_elements": []}

        with patch.object(registry, "register_for_class", return_value=mock_entry):
            await hook.on_initial_render(ctx, template_context)

        # Should have view CSS + component CSS
        assert len(template_context["additional_head_elements"]) == 2

    def test_loaded_css_tracking(self, hook):
        """Test that loaded_css set is created and used correctly."""
        mock_socket = MagicMock(spec=[])  # No loaded_css attribute

        loaded = hook._get_loaded_css(mock_socket)
        assert isinstance(loaded, set)
        assert hasattr(mock_socket, "loaded_css")

        # Add something
        loaded.add("/test.css")

        # Get again - should be same set
        loaded2 = hook._get_loaded_css(mock_socket)
        assert "/test.css" in loaded2
