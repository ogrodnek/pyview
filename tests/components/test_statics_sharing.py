"""
Tests for component statics sharing optimization.

These tests verify that multiple instances of the same component type
share their statics array via integer CID references, matching Phoenix
wire format optimization.
"""

from typing import TypedDict
from unittest.mock import AsyncMock, MagicMock

import pytest

from pyview.components.base import ComponentSocket, LiveComponent
from pyview.components.manager import ComponentsManager
from pyview.meta import PyViewMeta


class CounterContext(TypedDict):
    count: int


class MockParentSocket:
    """Mock parent socket for testing."""

    def __init__(self):
        self.liveview = MagicMock()
        self.liveview.handle_event = AsyncMock()
        self.meta = PyViewMeta()


class MockConnectedSocket:
    """Mock ConnectedLiveViewSocket for testing render_with_components."""

    def __init__(self):
        self.liveview = MagicMock()
        self.liveview.render = AsyncMock()
        self.context = {}
        self.meta = PyViewMeta()
        self.components = ComponentsManager(self)

    async def render_with_components(self):
        """
        Simplified version of ConnectedLiveViewSocket.render_with_components for testing.

        Note: Does NOT call begin_render() or prune_stale_components() since those
        would interfere with components registered before this call. In production,
        components are registered DURING the parent render.
        """
        from pyview.template.live_view_template import LiveViewTemplate

        # Fake parent render result (just an empty tree for testing)
        rendered = {"s": ["<div>", "</div>"], "0": "content"}

        # Run pending component lifecycle methods
        await self.components.run_pending_lifecycle()

        # Render all registered components with statics sharing
        if self.components.component_count > 0:
            components_rendered = {}
            statics_cache: dict[tuple[str, ...], int] = {}

            for cid in self.components.get_all_cids():
                template = self.components.render_component(cid, self.meta)
                if template is not None:
                    tree = LiveViewTemplate.process(template, socket=self)
                    tree["r"] = 1

                    # Share statics if we've seen them before
                    statics = tree.get("s")
                    if statics is not None and isinstance(statics, list):
                        statics_key = tuple(statics)
                        if statics_key in statics_cache:
                            tree["s"] = statics_cache[statics_key]
                        else:
                            statics_cache[statics_key] = cid

                    components_rendered[str(cid)] = tree

            if components_rendered:
                rendered["c"] = components_rendered

        return rendered


class SimpleCounter(LiveComponent[CounterContext]):
    """Simple counter component with consistent template for statics testing."""

    async def mount(self, socket: ComponentSocket[CounterContext], assigns: dict):
        socket.context = CounterContext(count=assigns.get("initial", 0))

    def template(self, assigns, meta):
        # Template with statics that will be the same across instances
        # Using t-string for proper LiveViewTemplate processing
        return t"<div class='counter'><span>Count: {assigns['count']}</span></div>"


class DifferentCounter(LiveComponent[CounterContext]):
    """Different counter component with different statics."""

    async def mount(self, socket: ComponentSocket[CounterContext], assigns: dict):
        socket.context = CounterContext(count=assigns.get("initial", 0))

    def template(self, assigns, meta):
        # Different template = different statics
        # Using t-string for proper LiveViewTemplate processing
        return t"<section class='other'><p>{assigns['count']}</p></section>"


class TestComponentStaticsSharing:
    """Tests for component statics sharing optimization."""

    @pytest.mark.asyncio
    async def test_multiple_same_components_share_statics(self):
        """Test that multiple instances of same component share statics via CID reference."""
        parent = MockConnectedSocket()
        manager = parent.components

        # Register 3 instances of the same component
        cid1 = manager.register(SimpleCounter, "counter-1", {"initial": 1})
        cid2 = manager.register(SimpleCounter, "counter-2", {"initial": 2})
        cid3 = manager.register(SimpleCounter, "counter-3", {"initial": 3})

        rendered = await parent.render_with_components()

        # Verify components dict exists
        assert "c" in rendered
        components = rendered["c"]

        # First component should have full statics array
        first_comp = components[str(cid1)]
        assert isinstance(first_comp["s"], list), "First component should have statics array"

        # Second and third components should reference first CID
        second_comp = components[str(cid2)]
        third_comp = components[str(cid3)]

        assert second_comp["s"] == cid1, f"Second component should reference CID {cid1}"
        assert third_comp["s"] == cid1, f"Third component should reference CID {cid1}"

    @pytest.mark.asyncio
    async def test_different_components_no_sharing(self):
        """Test that different component types don't share statics."""
        parent = MockConnectedSocket()
        manager = parent.components

        cid1 = manager.register(SimpleCounter, "counter-1", {"initial": 1})
        cid2 = manager.register(DifferentCounter, "different-1", {"initial": 2})

        rendered = await parent.render_with_components()

        components = rendered["c"]

        # Both components should have full statics arrays (different templates)
        first_comp = components[str(cid1)]
        second_comp = components[str(cid2)]

        assert isinstance(first_comp["s"], list), "First component should have statics array"
        assert isinstance(second_comp["s"], list), (
            "Different component should have its own statics array"
        )

    @pytest.mark.asyncio
    async def test_all_components_have_root_flag(self):
        """Test that all components have ROOT flag set to 1."""
        parent = MockConnectedSocket()
        manager = parent.components

        manager.register(SimpleCounter, "counter-1", {})
        manager.register(SimpleCounter, "counter-2", {})
        manager.register(DifferentCounter, "different-1", {})

        rendered = await parent.render_with_components()

        for cid_str, comp_data in rendered["c"].items():
            assert comp_data.get("r") == 1, f"Component {cid_str} missing ROOT flag"

    @pytest.mark.asyncio
    async def test_component_cid_keys_are_strings(self):
        """Test that component keys in 'c' dict are strings (Phoenix wire format)."""
        parent = MockConnectedSocket()
        manager = parent.components

        manager.register(SimpleCounter, "counter-1", {})
        manager.register(SimpleCounter, "counter-2", {})

        rendered = await parent.render_with_components()

        for key in rendered["c"]:
            assert isinstance(key, str), f"CID key should be string, got {type(key)}"

    @pytest.mark.asyncio
    async def test_statics_reference_is_integer(self):
        """Test that shared statics reference is an integer CID, not string."""
        parent = MockConnectedSocket()
        manager = parent.components

        cid1 = manager.register(SimpleCounter, "counter-1", {})
        cid2 = manager.register(SimpleCounter, "counter-2", {})

        rendered = await parent.render_with_components()

        second_comp = rendered["c"][str(cid2)]

        # The "s" reference should be integer, not string
        assert isinstance(second_comp["s"], int), (
            f"Statics reference should be int, got {type(second_comp['s'])}"
        )
        assert second_comp["s"] == cid1

    @pytest.mark.asyncio
    async def test_single_component_no_sharing(self):
        """Test that a single component has full statics array."""
        parent = MockConnectedSocket()
        manager = parent.components

        cid = manager.register(SimpleCounter, "counter-1", {})

        rendered = await parent.render_with_components()

        comp = rendered["c"][str(cid)]
        assert isinstance(comp["s"], list), "Single component should have statics array"

    @pytest.mark.asyncio
    async def test_mixed_components_correct_sharing(self):
        """Test correct sharing with a mix of same and different components."""
        parent = MockConnectedSocket()
        manager = parent.components

        # 2 SimpleCounter, 2 DifferentCounter
        simple1 = manager.register(SimpleCounter, "simple-1", {})
        diff1 = manager.register(DifferentCounter, "diff-1", {})
        simple2 = manager.register(SimpleCounter, "simple-2", {})
        diff2 = manager.register(DifferentCounter, "diff-2", {})

        rendered = await parent.render_with_components()
        components = rendered["c"]

        # simple1 should have full statics (first of its type)
        assert isinstance(components[str(simple1)]["s"], list)

        # diff1 should have full statics (first of its type)
        assert isinstance(components[str(diff1)]["s"], list)

        # simple2 should reference simple1
        assert components[str(simple2)]["s"] == simple1

        # diff2 should reference diff1
        assert components[str(diff2)]["s"] == diff1
