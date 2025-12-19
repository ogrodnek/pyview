"""Tests for component lifecycle with nested component discovery."""

import sys
import pytest
from typing import TypedDict

# Skip entire module on Python < 3.14 (t-strings not supported)
if sys.version_info < (3, 14):
    pytest.skip("T-string tests require Python 3.14+", allow_module_level=True)

from pyview.live_socket import UnconnectedSocket, UnconnectedLiveView
from pyview.meta import PyViewMeta
from pyview.components import ComponentsManager
from pyview.components.lifecycle import run_nested_component_lifecycle
from pyview.template.live_view_template import (
    LiveViewTemplate,
    LiveComponentPlaceholder,
    ComponentMarker,
    live_component,
)
from pyview.template.template_view import TStringRenderedContent
from pyview.components.base import LiveComponent, ComponentMeta, ComponentSocket


class CounterContext(TypedDict):
    count: int


class Counter(LiveComponent[CounterContext]):
    """Simple counter component for testing."""

    async def mount(self, socket: ComponentSocket[CounterContext], assigns: dict):
        socket.context = CounterContext(count=assigns.get("initial", 0))

    def template(self, assigns: CounterContext, meta: ComponentMeta):
        count = assigns["count"]
        myself = meta.myself
        return t'<div class="counter" data-cid="{myself}">Count: {count}</div>'


class CardContext(TypedDict):
    title: str


class Card(LiveComponent[CardContext]):
    """Card component for testing."""

    async def mount(self, socket: ComponentSocket[CardContext], assigns: dict):
        socket.context = CardContext(title=assigns.get("title", "Default"))

    def template(self, assigns: CardContext, meta: ComponentMeta):
        return t'<div class="card"><h2>{assigns["title"]}</h2></div>'


class TestUnconnectedSocket:
    """Tests for UnconnectedSocket with components."""

    def test_has_components_manager(self):
        socket = UnconnectedSocket()
        assert hasattr(socket, "components")
        assert isinstance(socket.components, ComponentsManager)

    def test_connected_is_false(self):
        socket = UnconnectedSocket()
        assert socket.connected is False

    def test_has_liveview_property(self):
        socket = UnconnectedSocket()
        assert hasattr(socket, "liveview")
        assert isinstance(socket.liveview, UnconnectedLiveView)

    async def test_liveview_raises_on_handle_event(self):
        socket = UnconnectedSocket()
        with pytest.raises(RuntimeError, match="send_parent.*not available"):
            await socket.liveview.handle_event("test", {}, socket)


class TestComponentMarker:
    """Tests for ComponentMarker creation during unconnected phase."""

    def test_marker_created_when_unconnected(self):
        socket = UnconnectedSocket()
        socket.context = {}

        placeholder = LiveComponentPlaceholder(Counter, "counter-1", {"initial": 5})
        template = t"<div>{placeholder}</div>"

        result = LiveViewTemplate.process(template, socket=socket)

        # Should have a ComponentMarker, not a CID integer
        assert "0" in result
        assert isinstance(result["0"], ComponentMarker)
        assert result["0"].cid == 1  # First component gets CID 1

    def test_cid_used_when_connected(self):
        """Verify connected sockets still use integer CIDs."""
        # Create a mock connected socket
        class MockConnectedSocket:
            connected = True
            components = ComponentsManager(None)

        socket = MockConnectedSocket()
        socket.components = ComponentsManager(socket)

        placeholder = LiveComponentPlaceholder(Counter, "counter-1", {"initial": 5})
        template = t"<div>{placeholder}</div>"

        result = LiveViewTemplate.process(template, socket=socket)

        # Should have integer CID, not ComponentMarker
        assert "0" in result
        assert isinstance(result["0"], int)
        assert result["0"] == 1

    def test_marker_in_list(self):
        socket = UnconnectedSocket()
        socket.context = {}

        placeholders = [
            LiveComponentPlaceholder(Counter, f"counter-{i}", {"initial": i})
            for i in range(3)
        ]
        template = t"<div>{placeholders}</div>"

        result = LiveViewTemplate.process(template, socket=socket)

        # Check the comprehension format
        assert "0" in result
        comp_result = result["0"]
        assert "d" in comp_result

        # Each item should contain a ComponentMarker
        for i, item in enumerate(comp_result["d"]):
            assert len(item) == 1
            assert isinstance(item[0], ComponentMarker)
            assert item[0].cid == i + 1


class TestComponentRenderingUnconnected:
    """Tests for full component rendering in unconnected phase."""

    async def test_component_renders_to_html(self):
        socket = UnconnectedSocket()
        socket.context = {}

        # Register component via template processing
        placeholder = live_component(Counter, id="counter-1", initial=42)
        template = t"<main>{placeholder}</main>"

        tree = LiveViewTemplate.process(template, socket=socket)

        # Run lifecycle
        await socket.components.run_pending_lifecycle()

        # Convert to HTML
        rendered = TStringRenderedContent(tree)
        html = rendered.text(socket=socket)

        assert '<main>' in html
        assert 'class="counter"' in html
        assert 'Count: 42' in html
        assert '</main>' in html

    async def test_component_mount_called(self):
        socket = UnconnectedSocket()
        socket.context = {}

        mount_called = []

        class TrackingComponent(LiveComponent[CounterContext]):
            async def mount(self, sock, assigns):
                mount_called.append(assigns)
                sock.context = CounterContext(count=assigns.get("initial", 0))

            def template(self, assigns, meta):
                return t"<div>{assigns['count']}</div>"

        placeholder = LiveComponentPlaceholder(TrackingComponent, "track-1", {"initial": 99})
        template = t"<div>{placeholder}</div>"

        LiveViewTemplate.process(template, socket=socket)
        await socket.components.run_pending_lifecycle()

        assert len(mount_called) == 1
        assert mount_called[0]["initial"] == 99

    async def test_multiple_components_render(self):
        socket = UnconnectedSocket()
        socket.context = {}

        template = t"""
            <div>
                {live_component(Counter, id="c1", initial=10)}
                {live_component(Counter, id="c2", initial=20)}
                {live_component(Card, id="card1", title="Hello")}
            </div>
        """

        tree = LiveViewTemplate.process(template, socket=socket)
        await socket.components.run_pending_lifecycle()

        rendered = TStringRenderedContent(tree)
        html = rendered.text(socket=socket)

        assert 'Count: 10' in html
        assert 'Count: 20' in html
        assert 'class="card"' in html
        assert 'Hello' in html

    async def test_nested_components_render(self):
        """Test components containing other components."""
        socket = UnconnectedSocket()
        socket.context = {}

        class WrapperContext(TypedDict):
            label: str

        class Wrapper(LiveComponent[WrapperContext]):
            async def mount(self, sock, assigns):
                sock.context = WrapperContext(label=assigns.get("label", "Wrapper"))

            def template(self, assigns, meta):
                # This component contains another component
                inner = live_component(Counter, id=f"inner-{meta.myself}", initial=100)
                return t'<section class="wrapper"><h1>{assigns["label"]}</h1>{inner}</section>'

        placeholder = live_component(Wrapper, id="outer", label="Outer")
        template = t"<div>{placeholder}</div>"

        tree = LiveViewTemplate.process(template, socket=socket)

        # Use the nested lifecycle helper to discover and mount nested components
        meta = PyViewMeta(socket=socket)
        await run_nested_component_lifecycle(socket, meta)

        rendered = TStringRenderedContent(tree)
        html = rendered.text(socket=socket)

        assert 'class="wrapper"' in html
        assert 'Outer' in html
        assert 'Count: 100' in html

    async def test_components_in_list_render(self):
        socket = UnconnectedSocket()
        socket.context = {}

        counters = [
            live_component(Counter, id=f"list-{i}", initial=i * 10)
            for i in range(3)
        ]
        template = t"<ul>{counters}</ul>"

        tree = LiveViewTemplate.process(template, socket=socket)
        await socket.components.run_pending_lifecycle()

        rendered = TStringRenderedContent(tree)
        html = rendered.text(socket=socket)

        assert 'Count: 0' in html
        assert 'Count: 10' in html
        assert 'Count: 20' in html


class TestMaxIterations:
    """Tests for iteration limit safeguard."""

    async def test_no_components_succeeds(self):
        """Test that lifecycle helper works with no components."""
        socket = UnconnectedSocket()
        socket.context = {}

        # No components registered
        meta = PyViewMeta(socket=socket)
        await run_nested_component_lifecycle(socket, meta)

        # Should complete without error
        assert socket.components.component_count == 0

    async def test_max_iterations_exceeded(self):
        """Test that deeply nested components are caught by iteration limit."""
        socket = UnconnectedSocket()
        socket.context = {}

        class RecursiveContext(TypedDict):
            depth: int

        class RecursiveComponent(LiveComponent[RecursiveContext]):
            """Component that creates another component of itself (up to a depth)."""

            async def mount(self, sock, assigns):
                sock.context = RecursiveContext(depth=assigns.get("depth", 0))

            def template(self, assigns, meta):
                depth = assigns["depth"]
                if depth < 20:  # Will exceed max_iterations of 3
                    inner = live_component(
                        RecursiveComponent, id=f"recursive-{depth + 1}", depth=depth + 1
                    )
                    return t'<div class="level-{depth}">{inner}</div>'
                return t'<div class="leaf">Leaf at depth {depth}</div>'

        placeholder = live_component(RecursiveComponent, id="recursive-0", depth=0)
        template = t"<div>{placeholder}</div>"

        LiveViewTemplate.process(template, socket=socket)

        meta = PyViewMeta(socket=socket)
        with pytest.raises(RuntimeError, match="Component lifecycle exceeded"):
            await run_nested_component_lifecycle(socket, meta, max_iterations=3)


class TestEdgeCases:
    """Edge case tests."""

    async def test_empty_socket_returns_empty_string(self):
        """ComponentMarker with no socket returns empty string."""
        marker = ComponentMarker(cid=999)
        tree = {"s": ["<div>", "</div>"], "0": marker}

        rendered = TStringRenderedContent(tree)
        html = rendered.text(socket=None)

        assert html == "<div></div>"

    async def test_missing_component_returns_empty_string(self):
        """ComponentMarker for unknown CID returns empty string."""
        socket = UnconnectedSocket()
        socket.context = {}

        marker = ComponentMarker(cid=999)  # Never registered
        tree = {"s": ["<div>", "</div>"], "0": marker}

        rendered = TStringRenderedContent(tree)
        html = rendered.text(socket=socket)

        assert html == "<div></div>"

    def test_text_without_socket_works_for_simple_templates(self):
        """text() without socket still works for templates without components."""
        tree = {"s": ["<p>", "</p>"], "0": "Hello"}

        rendered = TStringRenderedContent(tree)
        html = rendered.text()  # No socket

        assert html == "<p>Hello</p>"
