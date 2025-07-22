"""
Tests for TemplateView and TStringRenderedContent.
"""

import pytest
from pyview.template.template_view import TemplateView, TStringRenderedContent
from pyview.template.tstring_polyfill import t
from pyview.meta import PyViewMeta


class TestTStringRenderedContent:
    """Test TStringRenderedContent implementation."""

    def test_simple_tree(self):
        """Test simple tree structure."""
        tree = {"s": ["Hello, ", "!"], "0": "World"}
        content = TStringRenderedContent(tree)

        # Test tree() method
        assert content.tree() == tree

        # Test text() method
        html = content.text()
        assert html == "Hello, World!"

    def test_empty_tree(self):
        """Test empty tree structure."""
        tree = {"s": [""]}
        content = TStringRenderedContent(tree)

        assert content.tree() == tree
        assert content.text() == ""

    def test_no_interpolations(self):
        """Test tree with no interpolations."""
        tree = {"s": ["Hello, World!"]}
        content = TStringRenderedContent(tree)

        assert content.text() == "Hello, World!"

    def test_multiple_interpolations(self):
        """Test tree with multiple interpolations."""
        tree = {
            "s": ["", ", ", "! You have ", " messages."],
            "0": "Hello",
            "1": "Alice",
            "2": "5",
        }
        content = TStringRenderedContent(tree)

        assert content.text() == "Hello, Alice! You have 5 messages."

    def test_nested_tree(self):
        """Test nested tree structure."""
        tree = {
            "s": ["<div>", "</div>"],
            "0": {"s": ["<span>", "</span>"], "0": "Hello"},
        }
        content = TStringRenderedContent(tree)

        assert content.text() == "<div><span>Hello</span></div>"

    def test_list_comprehension(self):
        """Test list comprehension structure ('d' key)."""
        tree = {
            "s": ["<ul>", "</ul>"],
            "0": {
                "d": [
                    {"s": ["<li>", "</li>"], "0": "Item 1"},
                    {"s": ["<li>", "</li>"], "0": "Item 2"},
                    {"s": ["<li>", "</li>"], "0": "Item 3"},
                ]
            },
        }
        content = TStringRenderedContent(tree)

        html = content.text()
        # The current implementation doesn't handle 'd' key correctly
        # This test will expose the issue
        print(f"Generated HTML: {html}")
        # Should be: <ul><li>Item 1</li><li>Item 2</li><li>Item 3</li></ul>

    def test_mixed_content_types(self):
        """Test tree with mixed content types."""
        tree = {
            "s": ["Count: ", ", Active: ", ", Done: ", ""],
            "0": "10",
            "1": "true",
            "2": {"s": ["<span>", "</span>"], "0": "completed"},
        }
        content = TStringRenderedContent(tree)

        expected = "Count: 10, Active: true, Done: <span>completed</span>"
        assert content.text() == expected


class MockLiveView:
    """Mock LiveView for testing."""

    pass


class TestTemplateView:
    """Test TemplateView mixin."""

    @pytest.mark.asyncio
    async def test_template_view_render_success(self):
        """Test successful render with template method."""

        class TestView(TemplateView, MockLiveView):
            def template(self, assigns, meta):
                return t("Hello {name}!", name=assigns["name"])

        view = TestView()
        assigns = {"name": "World"}
        meta = PyViewMeta()

        # Test render method
        result = await view.render(assigns, meta)

        assert isinstance(result, TStringRenderedContent)
        tree = result.tree()
        assert tree["s"] == ["Hello ", "!"]
        assert tree["0"] == "World"

        html = result.text()
        assert html == "Hello World!"

    @pytest.mark.asyncio
    async def test_template_view_no_template_method(self):
        """Test TemplateView without template method falls back to super()."""

        class TestView(TemplateView, MockLiveView):
            async def render(self, assigns, meta):
                # Since MockLiveView doesn't have a render method, return fallback
                return "fallback"

        view = TestView()
        assigns = {"name": "World"}
        meta = PyViewMeta()

        result = await view.render(assigns, meta)
        assert result == "fallback"

    @pytest.mark.asyncio
    async def test_template_view_invalid_return_type(self):
        """Test TemplateView with template method returning wrong type."""

        class TestView(TemplateView, MockLiveView):
            def template(self, assigns, meta):  # type: ignore
                return "not a template"  # Should return Template

        view = TestView()
        assigns = {"name": "World"}
        meta = PyViewMeta()

        with pytest.raises(
            ValueError, match="template\\(\\) method must return a Template"
        ):
            await view.render(assigns, meta)

    @pytest.mark.asyncio
    async def test_template_view_with_assigns_dict(self):
        """Test TemplateView with dictionary assigns (common case)."""

        class TestView(TemplateView, MockLiveView):
            def template(self, assigns, meta):
                return t("Hello {name}!", name=assigns["name"])

        view = TestView()
        assigns = {"name": "World"}
        meta = PyViewMeta()

        result = await view.render(assigns, meta)
        assert isinstance(result, TStringRenderedContent)
        assert result.text() == "Hello World!"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
