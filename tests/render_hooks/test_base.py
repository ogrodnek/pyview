"""
Tests for render hooks base classes.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from pyview.render_hooks.base import HookContext, RenderHookRunner


class TestHookContext:
    """Tests for HookContext."""

    def test_add_prepend_accumulates_content(self):
        """Test that add_prepend accumulates content."""
        mock_view = MagicMock()
        mock_socket = MagicMock()

        ctx = HookContext(view=mock_view, socket=mock_socket, is_connected=True)

        ctx.add_prepend("<link href='a.css'>")
        ctx.add_prepend("<link href='b.css'>")

        assert len(ctx.prepend_content) == 2

    def test_get_prepend_html_joins_content(self):
        """Test that get_prepend_html joins all content."""
        mock_view = MagicMock()
        mock_socket = MagicMock()

        ctx = HookContext(view=mock_view, socket=mock_socket, is_connected=True)

        ctx.add_prepend("<link href='a.css'>")
        ctx.add_prepend("<link href='b.css'>")

        html = ctx.get_prepend_html()
        assert html == "<link href='a.css'><link href='b.css'>"

    def test_get_prepend_html_empty_when_no_content(self):
        """Test that get_prepend_html returns empty string when no content."""
        mock_view = MagicMock()
        mock_socket = MagicMock()

        ctx = HookContext(view=mock_view, socket=mock_socket, is_connected=True)

        assert ctx.get_prepend_html() == ""


class MockHook:
    """Mock hook for testing."""

    def __init__(self):
        self.before_render_called = False
        self.transform_tree_called = False
        self.on_initial_render_called = False

    async def before_render(self, ctx):
        self.before_render_called = True
        ctx.add_prepend("<test>")

    def transform_tree(self, tree, ctx):
        self.transform_tree_called = True
        tree["transformed"] = True
        return tree

    async def on_initial_render(self, ctx, template_context):
        self.on_initial_render_called = True
        template_context["hook_called"] = True


class TestRenderHookRunner:
    """Tests for RenderHookRunner."""

    def test_add_and_remove_hooks(self):
        """Test adding and removing hooks."""
        runner = RenderHookRunner()
        hook = MockHook()

        assert len(runner) == 0

        runner.add(hook)
        assert len(runner) == 1

        runner.remove(hook)
        assert len(runner) == 0

    @pytest.mark.asyncio
    async def test_run_before_render_calls_hooks(self):
        """Test that run_before_render calls all hooks."""
        runner = RenderHookRunner()
        hook1 = MockHook()
        hook2 = MockHook()

        runner.add(hook1)
        runner.add(hook2)

        mock_view = MagicMock()
        mock_socket = MagicMock()
        ctx = HookContext(view=mock_view, socket=mock_socket, is_connected=True)

        await runner.run_before_render(ctx)

        assert hook1.before_render_called
        assert hook2.before_render_called

    def test_run_transform_tree_chains_hooks(self):
        """Test that run_transform_tree chains hook transformations."""
        runner = RenderHookRunner()
        hook = MockHook()
        runner.add(hook)

        mock_view = MagicMock()
        mock_socket = MagicMock()
        ctx = HookContext(view=mock_view, socket=mock_socket, is_connected=True)

        tree = {"s": ["original"]}
        result = runner.run_transform_tree(tree, ctx)

        assert hook.transform_tree_called
        assert result["transformed"] is True

    @pytest.mark.asyncio
    async def test_run_on_initial_render_calls_hooks(self):
        """Test that run_on_initial_render calls all hooks."""
        runner = RenderHookRunner()
        hook = MockHook()
        runner.add(hook)

        mock_view = MagicMock()
        mock_socket = MagicMock()
        ctx = HookContext(view=mock_view, socket=mock_socket, is_connected=False)

        template_context = {"additional_head_elements": []}

        await runner.run_on_initial_render(ctx, template_context)

        assert hook.on_initial_render_called
        assert template_context["hook_called"] is True

    def test_iteration(self):
        """Test that runner can be iterated."""
        runner = RenderHookRunner()
        hook1 = MockHook()
        hook2 = MockHook()

        runner.add(hook1)
        runner.add(hook2)

        hooks = list(runner)
        assert hooks == [hook1, hook2]
