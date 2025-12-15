"""
Tests for ComponentsManager.

These tests verify component registration, lifecycle management,
event routing, and state persistence.
"""

import pytest
from typing import TypedDict
from unittest.mock import AsyncMock, MagicMock, patch

from pyview.components.base import ComponentMeta, ComponentSocket, LiveComponent
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


class SimpleCounter(LiveComponent[CounterContext]):
    """Simple counter component for testing."""

    async def mount(self, socket: ComponentSocket[CounterContext], assigns: dict):
        socket.context = CounterContext(count=assigns.get("initial", 0))

    async def handle_event(self, event, payload, socket):
        if event == "increment":
            socket.context["count"] += 1
        elif event == "set":
            socket.context["count"] = payload.get("value", 0)

    def template(self, assigns, meta):
        return f"Count: {assigns['count']}, target={meta.myself}"


class CounterWithInitial(LiveComponent[CounterContext]):
    """Counter that uses assigns for initial value."""

    async def mount(self, socket: ComponentSocket[CounterContext], assigns: dict):
        socket.context = CounterContext(count=assigns.get("initial", 0))

    async def update(self, assigns, socket):
        # Update handles subsequent changes to initial
        if "initial" in assigns:
            socket.context["count"] = assigns["initial"]

    def template(self, assigns, meta):
        return f"Count: {assigns['count']}"


class TestComponentsManagerRegistration:
    """Tests for component registration."""

    def test_register_new_component(self):
        """Test registering a new component."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        cid = manager.register(SimpleCounter, "counter-1", {})

        assert cid == 1
        assert manager.component_count == 1
        assert cid in manager.get_all_cids()

    def test_register_multiple_components(self):
        """Test registering multiple different components."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        cid1 = manager.register(SimpleCounter, "counter-1", {})
        cid2 = manager.register(SimpleCounter, "counter-2", {})
        cid3 = manager.register(CounterWithInitial, "counter-3", {})

        assert cid1 == 1
        assert cid2 == 2
        assert cid3 == 3
        assert manager.component_count == 3

    def test_register_same_component_returns_same_cid(self):
        """Test that same (class, id) returns same CID."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        cid1 = manager.register(SimpleCounter, "counter-1", {})
        cid2 = manager.register(SimpleCounter, "counter-1", {"new": "assigns"})

        assert cid1 == cid2
        assert manager.component_count == 1

    def test_different_id_gets_different_cid(self):
        """Test that same class with different ID gets different CID."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        cid1 = manager.register(SimpleCounter, "counter-1", {})
        cid2 = manager.register(SimpleCounter, "counter-2", {})

        assert cid1 != cid2

    def test_different_class_same_id_gets_different_cid(self):
        """Test that different class with same ID gets different CID."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        cid1 = manager.register(SimpleCounter, "my-id", {})
        cid2 = manager.register(CounterWithInitial, "my-id", {})

        assert cid1 != cid2


class TestComponentsManagerLifecycle:
    """Tests for component lifecycle methods."""

    @pytest.mark.asyncio
    async def test_mount_called_on_new_component(self):
        """Test that mount is called for new components."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        cid = manager.register(SimpleCounter, "counter-1", {})
        await manager.run_pending_lifecycle()

        # Check context was set by mount
        context = manager.get_context(cid)
        assert context == {"count": 0}

    @pytest.mark.asyncio
    async def test_update_called_with_assigns(self):
        """Test that update is called with assigns."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        cid = manager.register(CounterWithInitial, "counter-1", {"initial": 100})
        await manager.run_pending_lifecycle()

        # Check context was updated by update()
        context = manager.get_context(cid)
        assert context == {"count": 100}

    @pytest.mark.asyncio
    async def test_update_called_on_re_register(self):
        """Test that update is called when component is re-registered."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        # First registration
        cid = manager.register(CounterWithInitial, "counter-1", {"initial": 10})
        await manager.run_pending_lifecycle()
        assert manager.get_context(cid)["count"] == 10

        # Re-register with new assigns
        manager.register(CounterWithInitial, "counter-1", {"initial": 50})
        await manager.run_pending_lifecycle()

        # Context should be updated
        assert manager.get_context(cid)["count"] == 50

    @pytest.mark.asyncio
    async def test_mount_not_called_twice(self):
        """Test that mount is only called once per component."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        mount_count = 0

        class CountingCounter(LiveComponent):
            async def mount(self, socket, assigns):
                nonlocal mount_count
                mount_count += 1
                socket.context = {"count": mount_count}

            def template(self, assigns, meta):
                return ""

        cid = manager.register(CountingCounter, "counter-1", {})
        await manager.run_pending_lifecycle()
        assert mount_count == 1

        # Re-register (simulating re-render)
        manager.register(CountingCounter, "counter-1", {})
        await manager.run_pending_lifecycle()

        # Mount should still be 1, update was called instead
        assert mount_count == 1


class TestComponentsManagerEventHandling:
    """Tests for event routing to components."""

    @pytest.mark.asyncio
    async def test_handle_event_routes_to_component(self):
        """Test that handle_event calls component's handle_event."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        cid = manager.register(SimpleCounter, "counter-1", {})
        await manager.run_pending_lifecycle()

        # Initial count is 0
        assert manager.get_context(cid)["count"] == 0

        # Handle increment event
        await manager.handle_event(cid, "increment", {})
        assert manager.get_context(cid)["count"] == 1

        # Handle another increment
        await manager.handle_event(cid, "increment", {})
        assert manager.get_context(cid)["count"] == 2

    @pytest.mark.asyncio
    async def test_handle_event_with_payload(self):
        """Test that event payload is passed to component."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        cid = manager.register(SimpleCounter, "counter-1", {})
        await manager.run_pending_lifecycle()

        await manager.handle_event(cid, "set", {"value": 42})
        assert manager.get_context(cid)["count"] == 42

    @pytest.mark.asyncio
    async def test_handle_event_unknown_cid(self):
        """Test that handle_event with unknown CID doesn't crash."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        # Should not raise
        await manager.handle_event(999, "increment", {})


class TestComponentsManagerRendering:
    """Tests for component rendering."""

    @pytest.mark.asyncio
    async def test_render_component(self):
        """Test rendering a component."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        cid = manager.register(SimpleCounter, "counter-1", {})
        await manager.run_pending_lifecycle()

        result = manager.render_component(cid, parent.meta)

        assert "Count: 0" in result
        assert f"target={cid}" in result

    @pytest.mark.asyncio
    async def test_render_component_after_event(self):
        """Test rendering reflects state changes."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        cid = manager.register(SimpleCounter, "counter-1", {})
        await manager.run_pending_lifecycle()

        await manager.handle_event(cid, "increment", {})
        await manager.handle_event(cid, "increment", {})

        result = manager.render_component(cid, parent.meta)
        assert "Count: 2" in result

    def test_render_unknown_cid(self):
        """Test rendering unknown CID returns None."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        result = manager.render_component(999, parent.meta)
        assert result is None


class TestComponentsManagerParentCommunication:
    """Tests for component-to-parent communication."""

    @pytest.mark.asyncio
    async def test_send_to_parent(self):
        """Test sending event to parent LiveView."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        await manager.send_to_parent("my_event", {"key": "value"})

        parent.liveview.handle_event.assert_called_once_with(
            "my_event", {"key": "value"}, parent
        )

    @pytest.mark.asyncio
    async def test_send_parent_from_component_event_handler(self):
        """Test that a component can send events to parent via socket.send_parent()."""

        class NotifyingCounter(LiveComponent[CounterContext]):
            async def mount(self, socket, assigns):
                socket.context = CounterContext(count=0)

            async def handle_event(self, event, payload, socket):
                if event == "notify":
                    await socket.send_parent("component_notification", {"from_cid": socket.cid})

            def template(self, assigns, meta):
                return ""

        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        cid = manager.register(NotifyingCounter, "notifier-1", {})
        await manager.run_pending_lifecycle()

        # Trigger the notify event on the component
        await manager.handle_event(cid, "notify", {})

        # Verify parent's handle_event was called with the notification
        parent.liveview.handle_event.assert_called_once_with(
            "component_notification", {"from_cid": cid}, parent
        )


class TestComponentsManagerCleanup:
    """Tests for component cleanup."""

    def test_unregister_component(self):
        """Test unregistering a component."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        cid = manager.register(SimpleCounter, "counter-1", {})
        assert manager.component_count == 1

        manager.unregister(cid)
        assert manager.component_count == 0
        assert manager.get_component(cid) is None

    def test_unregister_allows_reuse_of_id(self):
        """Test that unregistered ID can be reused (gets new CID)."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        cid1 = manager.register(SimpleCounter, "counter-1", {})
        manager.unregister(cid1)

        # Same class+id should get a new CID now
        cid2 = manager.register(SimpleCounter, "counter-1", {})
        assert cid2 != cid1

    def test_clear_removes_all(self):
        """Test clear removes all components."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        manager.register(SimpleCounter, "counter-1", {})
        manager.register(SimpleCounter, "counter-2", {})
        manager.register(CounterWithInitial, "counter-3", {})

        assert manager.component_count == 3

        manager.clear()

        assert manager.component_count == 0


class TestComponentsManagerGetters:
    """Tests for getter methods."""

    @pytest.mark.asyncio
    async def test_get_component(self):
        """Test getting component and context."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        cid = manager.register(SimpleCounter, "counter-1", {})
        await manager.run_pending_lifecycle()

        result = manager.get_component(cid)
        assert result is not None

        component, context = result
        assert isinstance(component, SimpleCounter)
        assert context == {"count": 0}

    def test_get_component_unknown_cid(self):
        """Test getting unknown CID returns None."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        result = manager.get_component(999)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_context(self):
        """Test getting just the context."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        cid = manager.register(SimpleCounter, "counter-1", {})
        await manager.run_pending_lifecycle()

        context = manager.get_context(cid)
        assert context == {"count": 0}

    @pytest.mark.asyncio
    async def test_set_context(self):
        """Test setting context directly."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        cid = manager.register(SimpleCounter, "counter-1", {})
        await manager.run_pending_lifecycle()

        manager.set_context(cid, {"count": 999})
        assert manager.get_context(cid) == {"count": 999}

    def test_get_all_cids(self):
        """Test getting all CIDs."""
        parent = MockParentSocket()
        manager = ComponentsManager(parent)

        cid1 = manager.register(SimpleCounter, "counter-1", {})
        cid2 = manager.register(SimpleCounter, "counter-2", {})

        cids = manager.get_all_cids()
        assert set(cids) == {cid1, cid2}
