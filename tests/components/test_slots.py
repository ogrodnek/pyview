"""
Tests for slots functionality.

These tests verify the slots() helper function and slot passing through
component lifecycle.

NOTE: This test file uses t-string literal syntax and can only be run on Python 3.14+.
The pytest.skip call below prevents import errors on earlier Python versions.
"""
import sys

import pytest

# Skip entire module if Python < 3.14 (t-string literals cause SyntaxError)
if sys.version_info < (3, 14):
    pytest.skip("T-string tests require Python 3.14+", allow_module_level=True)

from typing import TypedDict
from unittest.mock import MagicMock

from pyview.components import slots, Slots
from pyview.components.base import ComponentMeta, LiveComponent
from pyview.components.manager import ComponentsManager
from pyview.meta import PyViewMeta


class CardContext(TypedDict):
    title: str


class MockParentSocket:
    """Mock parent socket for testing."""

    def __init__(self):
        self.liveview = MagicMock()
        self.meta = PyViewMeta()


class TestSlotsHelper:
    """Tests for the slots() helper function."""

    def test_empty_slots(self):
        """Test creating empty slots."""
        result = slots()
        assert result == {}
        assert isinstance(result, dict)

    def test_default_slot_only(self):
        """Test creating slots with just a default slot."""
        content = t"<p>Hello</p>"
        result = slots(content)

        assert "default" in result
        assert result["default"] is content
        assert len(result) == 1

    def test_named_slots_only(self):
        """Test creating slots with named slots only."""
        header = t"<h1>Title</h1>"
        footer = t"<button>OK</button>"

        result = slots(header=header, footer=footer)

        assert "header" in result
        assert "footer" in result
        assert result["header"] is header
        assert result["footer"] is footer
        assert "default" not in result
        assert len(result) == 2

    def test_default_and_named_slots(self):
        """Test creating slots with both default and named slots."""
        body = t"<p>Body content</p>"
        header = t"<h1>Title</h1>"
        footer = t"<button>OK</button>"

        result = slots(body, header=header, footer=footer)

        assert result["default"] is body
        assert result["header"] is header
        assert result["footer"] is footer
        assert len(result) == 3

    def test_none_default_not_included(self):
        """Test that None default slot is not included."""
        header = t"<h1>Title</h1>"

        result = slots(None, header=header)

        assert "default" not in result
        assert "header" in result
        assert len(result) == 1


class TestSlotsType:
    """Tests for the Slots type alias."""

    def test_slots_is_dict(self):
        """Test that Slots is a dict type alias."""
        # Slots should be usable as a type hint
        my_slots: Slots = {"default": t"<p>Hello</p>"}
        assert isinstance(my_slots, dict)


class TestComponentMetaSlots:
    """Tests for slots in ComponentMeta."""

    def test_component_meta_default_slots(self):
        """Test that ComponentMeta has empty slots by default."""
        meta = ComponentMeta(cid=1, parent_meta=PyViewMeta())

        assert meta.slots == {}



class TestComponentsManagerSlots:
    """Tests for slots storage and retrieval in ComponentsManager."""

    def test_register_component_with_slots(self):
        """Test registering a component with slots."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        my_slots = slots(t"<p>Body</p>", header=t"<h1>Title</h1>")
        cid = manager.register(LiveComponent, "card-1", {"slots": my_slots})

        assert cid == 1
        assert manager.component_count == 1

    def test_register_component_without_slots(self):
        """Test registering a component without slots."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        cid = manager.register(LiveComponent, "card-1", {"label": "test"})

        assert cid == 1
        assert manager.component_count == 1

    async def test_slots_not_passed_to_mount(self):
        """Test that slots are extracted and not passed in assigns."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        received_assigns = None

        class SlotCapture(LiveComponent):
            async def mount(self, socket, assigns):
                nonlocal received_assigns
                received_assigns = assigns
                socket.context = {}

            def template(self, assigns, meta):
                return ""

        my_slots = slots(t"<p>Body</p>")
        manager.register(SlotCapture, "card-1", {"label": "test", "slots": my_slots})

        # Run lifecycle to trigger mount
        await manager.run_pending_lifecycle()

        # slots should be extracted from assigns
        assert received_assigns is not None
        assert "slots" not in received_assigns
        assert received_assigns == {"label": "test"}

    async def test_render_component_receives_slots(self):
        """Test that rendered components receive slots in meta."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        received_meta = None

        class SlotReceiver(LiveComponent[CardContext]):
            async def mount(self, socket, assigns):
                socket.context = CardContext(title="Test")

            def template(self, assigns, meta):
                nonlocal received_meta
                received_meta = meta
                return ""

        my_slots = slots(t"<p>Body</p>", header=t"<h1>Title</h1>")
        cid = manager.register(SlotReceiver, "card-1", {"slots": my_slots})
        await manager.run_pending_lifecycle()

        manager.render_component(cid, parent.meta)

        assert received_meta is not None
        assert received_meta.slots == my_slots
        assert "default" in received_meta.slots
        assert "header" in received_meta.slots

    async def test_render_component_without_slots(self):
        """Test that components without slots get empty slots dict."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        received_meta = None

        class NoSlotComponent(LiveComponent):
            async def mount(self, socket, assigns):
                socket.context = {}

            def template(self, assigns, meta):
                nonlocal received_meta
                received_meta = meta
                return ""

        cid = manager.register(NoSlotComponent, "card-1", {"label": "test"})
        await manager.run_pending_lifecycle()

        manager.render_component(cid, parent.meta)

        assert received_meta is not None
        assert received_meta.slots == {}

    async def test_slots_updated_on_re_register(self):
        """Test that slots are updated when component is re-registered."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        received_slots = []

        class SlotTracker(LiveComponent):
            async def mount(self, socket, assigns):
                socket.context = {}

            def template(self, assigns, meta):
                nonlocal received_slots
                received_slots.append(dict(meta.slots))
                return ""

        # First render with initial slots
        initial_slots = slots(t"<p>Initial</p>")
        cid = manager.register(SlotTracker, "card-1", {"slots": initial_slots})
        await manager.run_pending_lifecycle()
        manager.render_component(cid, parent.meta)

        # Re-register with updated slots
        updated_slots = slots(t"<p>Updated</p>", footer=t"<footer>New</footer>")
        manager.register(SlotTracker, "card-1", {"slots": updated_slots})
        await manager.run_pending_lifecycle()
        manager.render_component(cid, parent.meta)

        assert len(received_slots) == 2
        assert received_slots[0] == initial_slots
        assert received_slots[1] == updated_slots

    def test_slots_cleaned_on_unregister(self):
        """Test that slots are cleaned up when component is unregistered."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        my_slots = slots(t"<p>Body</p>")
        cid = manager.register(LiveComponent, "card-1", {"slots": my_slots})

        # Verify slots are stored (internal check)
        assert cid in manager._slots

        manager.unregister(cid)

        # Slots should be cleaned up
        assert cid not in manager._slots

    def test_slots_cleaned_on_clear(self):
        """Test that slots are cleaned up when manager is cleared."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        manager.register(LiveComponent, "card-1", {"slots": slots(t"<p>1</p>")})
        manager.register(LiveComponent, "card-2", {"slots": slots(t"<p>2</p>")})

        assert len(manager._slots) == 2

        manager.clear()

        assert len(manager._slots) == 0


class TestSlotsInComponentTemplate:
    """Tests for using slots in component templates."""

    async def test_component_renders_default_slot(self):
        """Test that a component can render the default slot."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        class Card(LiveComponent):
            async def mount(self, socket, assigns):
                socket.context = {}

            def template(self, assigns, meta):
                slot_content = meta.slots.get("default", t"")
                return t"<div class='card'>{slot_content}</div>"

        body_content = t"<p>Card body</p>"
        cid = manager.register(Card, "card-1", {"slots": slots(body_content)})
        await manager.run_pending_lifecycle()

        result = manager.render_component(cid, parent.meta)

        # Result is a t-string, check its structure
        assert "<div class='card'>" in "".join(result.strings)
        assert "</div>" in "".join(result.strings)

    async def test_component_renders_named_slots(self):
        """Test that a component can render named slots."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        class Card(LiveComponent):
            async def mount(self, socket, assigns):
                socket.context = {}

            def template(self, assigns, meta):
                header = meta.slots.get("header", t"")
                footer = meta.slots.get("footer", t"")
                return t"<header>{header}</header><footer>{footer}</footer>"

        my_slots = slots(
            header=t"<h1>Title</h1>",
            footer=t"<button>OK</button>",
        )
        cid = manager.register(Card, "card-1", {"slots": my_slots})
        await manager.run_pending_lifecycle()

        result = manager.render_component(cid, parent.meta)

        assert "<header>" in "".join(result.strings)
        assert "</header>" in "".join(result.strings)
        assert "<footer>" in "".join(result.strings)
        assert "</footer>" in "".join(result.strings)

    async def test_component_with_missing_slot(self):
        """Test that missing slots return empty when accessed with .get()."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        class Card(LiveComponent):
            async def mount(self, socket, assigns):
                socket.context = {}

            def template(self, assigns, meta):
                # Access a slot that doesn't exist
                optional = meta.slots.get("optional", t"<span>Default</span>")
                return t"<div>{optional}</div>"

        # Register without the 'optional' slot
        cid = manager.register(Card, "card-1", {"slots": slots()})
        await manager.run_pending_lifecycle()

        result = manager.render_component(cid, parent.meta)

        # Should use the fallback
        assert "<div>" in "".join(result.strings)
        assert "</div>" in "".join(result.strings)


class TestNestedComponentsInSlots:
    """Tests for live components nested inside slots (connected flow)."""

    async def test_nested_component_in_slot_connected_flow(self):
        """Test that nested components in slots work in the connected (WebSocket) flow.

        This is a regression test for the bug where nested components were registered
        but their lifecycle never ran and they weren't included in the response.
        """
        from unittest.mock import AsyncMock, MagicMock
        from pyview.live_socket import ConnectedLiveViewSocket
        from pyview.template.live_view_template import live_component

        # Create a mock connected socket
        mock_websocket = MagicMock()
        mock_liveview = MagicMock()
        mock_scheduler = MagicMock()
        mock_instrumentation = MagicMock()

        # We need to test render_with_components, so create a minimal mock
        from pyview.components.manager import ComponentsManager

        class MockConnectedSocket:
            components: ComponentsManager

            def __init__(self):
                self.context: dict = {}
                self.connected = True
                self.liveview = mock_liveview

            @property
            def meta(self):
                return PyViewMeta(socket=self)

        socket = MockConnectedSocket()
        socket.components = ComponentsManager(socket)

        # Define a Counter component
        class Counter(LiveComponent):
            async def mount(self, socket, assigns):
                socket.context = {"count": assigns.get("initial", 0)}

            def template(self, assigns, meta):
                return t"<span>Count: {assigns['count']}</span>"

        # Define a Card component that uses slots
        class Card(LiveComponent):
            async def mount(self, socket, assigns):
                socket.context = {}

            def template(self, assigns, meta):
                body = meta.slots.get("default", t"")
                return t"<div class='card'>{body}</div>"

        # Simulate the parent LiveView rendering a Card with nested Counter
        from pyview.template.live_view_template import LiveViewTemplate
        from pyview.components.lifecycle import run_nested_component_lifecycle

        # Register Card with a slot containing Counter
        socket.components.begin_render()
        card_cid = socket.components.register(
            Card, "card-1",
            {"slots": slots(t"<p>Body with counter: {live_component(Counter, id='nested-counter', initial=42)}</p>")}
        )

        # Run nested component lifecycle (this is what render_with_components does)
        await run_nested_component_lifecycle(socket, socket.meta)

        # Verify both components are registered
        all_cids = socket.components.get_all_cids()
        assert len(all_cids) == 2, f"Expected 2 components (Card + Counter), got {len(all_cids)}"

        # Verify Counter's lifecycle ran (context should be set)
        counter_cid = [c for c in all_cids if c != card_cid][0]
        counter_context = socket.components.get_context(counter_cid)
        assert counter_context == {"count": 42}, f"Counter context not set correctly: {counter_context}"

        # Verify both can be rendered
        from pyview.components.renderer import render_component_tree

        card_tree = render_component_tree(
            socket.components.render_component(card_cid, socket.meta),
            socket=socket
        )
        counter_tree = render_component_tree(
            socket.components.render_component(counter_cid, socket.meta),
            socket=socket
        )

        assert card_tree is not None
        assert counter_tree is not None
        assert "s" in counter_tree  # Has statics
        # Counter should render "Count: 42"


class TestSingleRenderPerCycle:
    """Tests that components are only rendered once per render cycle."""

    async def test_component_template_called_once(self):
        """Verify each component's template() is only called once during lifecycle."""
        from pyview.components.manager import ComponentsManager
        from pyview.template.live_view_template import live_component

        class MockConnectedSocket:
            components: ComponentsManager

            def __init__(self):
                self.context: dict = {}
                self.connected = True
                self.liveview = MagicMock()

            @property
            def meta(self):
                return PyViewMeta(socket=self)

        socket = MockConnectedSocket()
        socket.components = ComponentsManager(socket)

        # Track how many times template() is called
        render_counts: dict[str, int] = {"card": 0, "counter": 0}

        class CountingCounter(LiveComponent):
            async def mount(self, socket, assigns):
                socket.context = {"count": assigns.get("initial", 0)}

            def template(self, assigns, meta):
                render_counts["counter"] += 1
                return t"<span>Count: {assigns['count']}</span>"

        class CountingCard(LiveComponent):
            async def mount(self, socket, assigns):
                socket.context = {}

            def template(self, assigns, meta):
                render_counts["card"] += 1
                body = meta.slots.get("default", t"")
                return t"<div class='card'>{body}</div>"

        from pyview.components.lifecycle import run_nested_component_lifecycle

        # Register Card with nested Counter
        socket.components.begin_render()
        socket.components.register(
            CountingCard, "card-1",
            {"slots": slots(t"<p>{live_component(CountingCounter, id='counter-1', initial=10)}</p>")}
        )

        # Run lifecycle - this should render each component exactly once
        rendered_trees = await run_nested_component_lifecycle(socket, socket.meta)

        # Verify each component was rendered exactly once
        assert render_counts["card"] == 1, f"Card rendered {render_counts['card']} times, expected 1"
        assert render_counts["counter"] == 1, f"Counter rendered {render_counts['counter']} times, expected 1"

        # Verify we got trees for both components
        assert len(rendered_trees) == 2, f"Expected 2 rendered trees, got {len(rendered_trees)}"

    async def test_no_pending_updates_after_lifecycle(self):
        """Verify no spurious updates are queued after lifecycle completes."""
        from pyview.components.manager import ComponentsManager
        from pyview.template.live_view_template import live_component

        class MockConnectedSocket:
            components: ComponentsManager

            def __init__(self):
                self.context: dict = {}
                self.connected = True
                self.liveview = MagicMock()

            @property
            def meta(self):
                return PyViewMeta(socket=self)

        socket = MockConnectedSocket()
        socket.components = ComponentsManager(socket)

        class SimpleCounter(LiveComponent):
            async def mount(self, socket, assigns):
                socket.context = {"count": 0}

            def template(self, assigns, meta):
                return t"<span>{assigns['count']}</span>"

        class SimpleCard(LiveComponent):
            async def mount(self, socket, assigns):
                socket.context = {}

            def template(self, assigns, meta):
                body = meta.slots.get("default", t"")
                return t"<div>{body}</div>"

        from pyview.components.lifecycle import run_nested_component_lifecycle

        # Register Card with nested Counter
        socket.components.begin_render()
        socket.components.register(
            SimpleCard, "card-1",
            {"slots": slots(t"{live_component(SimpleCounter, id='counter-1')}")}
        )

        # Run lifecycle
        await run_nested_component_lifecycle(socket, socket.meta)

        # Verify no pending lifecycle remains
        assert not socket.components.has_pending_lifecycle(), \
            "Expected no pending lifecycle after run_nested_component_lifecycle()"

        # Verify _pending_updates is empty (no spurious updates queued)
        assert len(socket.components._pending_updates) == 0, \
            f"Expected 0 pending updates, got {len(socket.components._pending_updates)}"

    async def test_stale_components_not_rendered(self):
        """Verify stale components from previous renders don't get rendered or resurrect children."""
        from pyview.components.manager import ComponentsManager
        from pyview.template.live_view_template import live_component

        class MockConnectedSocket:
            components: ComponentsManager

            def __init__(self):
                self.context: dict = {}
                self.connected = True
                self.liveview = MagicMock()

            @property
            def meta(self):
                return PyViewMeta(socket=self)

        socket = MockConnectedSocket()
        socket.components = ComponentsManager(socket)

        render_counts: dict[str, int] = {"card": 0, "counter": 0}

        class TrackingCounter(LiveComponent):
            async def mount(self, socket, assigns):
                socket.context = {"count": 0}

            def template(self, assigns, meta):
                render_counts["counter"] += 1
                return t"<span>{assigns['count']}</span>"

        class TrackingCard(LiveComponent):
            async def mount(self, socket, assigns):
                socket.context = {}

            def template(self, assigns, meta):
                render_counts["card"] += 1
                body = meta.slots.get("default", t"")
                return t"<div>{body}</div>"

        from pyview.components.lifecycle import run_nested_component_lifecycle

        # Render 1: Register Card with nested Counter
        socket.components.begin_render()
        socket.components.register(
            TrackingCard, "card-1",
            {"slots": slots(t"{live_component(TrackingCounter, id='counter-1')}")}
        )
        await run_nested_component_lifecycle(socket, socket.meta)

        assert render_counts["card"] == 1
        assert render_counts["counter"] == 1
        assert socket.components.component_count == 2

        # Render 2: Card is no longer in the template (stale)
        # Only register a different component
        socket.components.begin_render()
        # Don't register Card or Counter - they should be stale

        # Reset counts to verify stale components aren't rendered
        render_counts["card"] = 0
        render_counts["counter"] = 0

        rendered_trees = await run_nested_component_lifecycle(socket, socket.meta)

        # Stale components should NOT be rendered
        assert render_counts["card"] == 0, "Stale Card should not be rendered"
        assert render_counts["counter"] == 0, "Stale Counter should not be rendered"

        # No trees should be returned for stale components
        assert len(rendered_trees) == 0, "No trees should be returned for stale components"

        # After pruning, both stale components should be removed
        socket.components.prune_stale_components()
        assert socket.components.component_count == 0, "All stale components should be pruned"
