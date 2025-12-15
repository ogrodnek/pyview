"""
Tests for LiveComponent base classes.

These tests verify the base class interfaces and default behaviors
without requiring Python 3.14 (no t-strings needed).
"""

import pytest
from typing import TypedDict
from unittest.mock import AsyncMock, MagicMock

from pyview.components.base import ComponentMeta, ComponentSocket, LiveComponent
from pyview.meta import PyViewMeta


class TestComponentMeta:
    """Tests for ComponentMeta dataclass."""

    def test_creation(self):
        """Test ComponentMeta can be created with cid and parent_meta."""
        parent_meta = PyViewMeta()
        meta = ComponentMeta(cid=42, parent_meta=parent_meta)

        assert meta.cid == 42
        assert meta.parent_meta is parent_meta

    def test_myself_property(self):
        """Test myself property returns cid."""
        meta = ComponentMeta(cid=123, parent_meta=PyViewMeta())
        assert meta.myself == 123

    def test_myself_equals_cid(self):
        """Test myself and cid are always equal."""
        for cid in [0, 1, 100, 999]:
            meta = ComponentMeta(cid=cid, parent_meta=PyViewMeta())
            assert meta.myself == meta.cid == cid


class TestComponentSocket:
    """Tests for ComponentSocket dataclass."""

    def test_creation(self):
        """Test ComponentSocket can be created."""
        manager = MagicMock()
        socket = ComponentSocket(
            context={"count": 0},
            cid=1,
            manager=manager,
        )

        assert socket.context == {"count": 0}
        assert socket.cid == 1
        assert socket.manager is manager

    def test_myself_property(self):
        """Test myself property returns cid."""
        socket = ComponentSocket(context={}, cid=42, manager=MagicMock())
        assert socket.myself == 42

    def test_context_modification_tracking(self):
        """Test that context modification is tracked."""
        socket = ComponentSocket(context={"count": 0}, cid=1, manager=MagicMock())

        # Initially not modified
        assert socket._context_modified is False

        # Modifying context dict values doesn't trigger (only replacing context does)
        socket.context["count"] = 5
        assert socket._context_modified is False

        # Replacing context triggers modification flag
        socket.context = {"count": 10}
        assert socket._context_modified is True

    @pytest.mark.asyncio
    async def test_send_parent(self):
        """Test send_parent calls manager.send_to_parent."""
        manager = MagicMock()
        manager.send_to_parent = AsyncMock()

        socket = ComponentSocket(context={}, cid=1, manager=manager)
        await socket.send_parent("my_event", {"key": "value"})

        manager.send_to_parent.assert_called_once_with("my_event", {"key": "value"})

    @pytest.mark.asyncio
    async def test_send_parent_default_payload(self):
        """Test send_parent with no payload uses empty dict."""
        manager = MagicMock()
        manager.send_to_parent = AsyncMock()

        socket = ComponentSocket(context={}, cid=1, manager=manager)
        await socket.send_parent("my_event")

        manager.send_to_parent.assert_called_once_with("my_event", {})


class CounterContext(TypedDict):
    count: int


class TestLiveComponent:
    """Tests for LiveComponent base class."""

    def test_subclass_creation(self):
        """Test creating a LiveComponent subclass."""

        class Counter(LiveComponent[CounterContext]):
            def template(self, assigns, meta):
                return f"Count: {assigns['count']}"

        component = Counter()
        assert isinstance(component, LiveComponent)

    @pytest.mark.asyncio
    async def test_default_mount(self):
        """Test default mount does nothing (doesn't raise)."""

        class Counter(LiveComponent[CounterContext]):
            def template(self, assigns, meta):
                return ""

        component = Counter()
        socket = ComponentSocket(context={}, cid=1, manager=MagicMock())

        # Should not raise - mount now receives assigns
        await component.mount(socket, {"initial": 0})

    @pytest.mark.asyncio
    async def test_default_update_is_noop(self):
        """Test default update does nothing (doesn't pollute context)."""

        class Counter(LiveComponent[CounterContext]):
            def template(self, assigns, meta):
                return ""

        component = Counter()
        socket = ComponentSocket(
            context={"count": 0, "existing": "value"},
            cid=1,
            manager=MagicMock(),
        )

        # Default update should not modify context
        await component.update({"count": 10, "new_key": "new_value"}, socket)

        # Context should be unchanged
        assert socket.context["count"] == 0
        assert socket.context["existing"] == "value"
        assert "new_key" not in socket.context

    @pytest.mark.asyncio
    async def test_default_handle_event(self):
        """Test default handle_event does nothing (doesn't raise)."""

        class Counter(LiveComponent[CounterContext]):
            def template(self, assigns, meta):
                return ""

        component = Counter()
        socket = ComponentSocket(context={}, cid=1, manager=MagicMock())

        # Should not raise
        await component.handle_event("some_event", {"key": "value"}, socket)

    def test_template_not_implemented(self):
        """Test template raises NotImplementedError if not overridden."""

        class NoTemplate(LiveComponent):
            pass

        component = NoTemplate()
        meta = ComponentMeta(cid=1, parent_meta=PyViewMeta())

        with pytest.raises(NotImplementedError):
            component.template({}, meta)

    @pytest.mark.asyncio
    async def test_custom_mount(self):
        """Test custom mount implementation with assigns."""

        class Counter(LiveComponent[CounterContext]):
            async def mount(self, socket, assigns):
                socket.context = CounterContext(count=assigns.get("initial", 100))

            def template(self, assigns, meta):
                return ""

        component = Counter()
        socket = ComponentSocket(context={}, cid=1, manager=MagicMock())

        await component.mount(socket, {"initial": 50})
        assert socket.context["count"] == 50

    @pytest.mark.asyncio
    async def test_custom_handle_event(self):
        """Test custom handle_event implementation."""

        class Counter(LiveComponent[CounterContext]):
            async def handle_event(self, event, payload, socket):
                if event == "increment":
                    socket.context["count"] += 1
                elif event == "set":
                    socket.context["count"] = payload.get("value", 0)

            def template(self, assigns, meta):
                return ""

        component = Counter()
        socket = ComponentSocket(
            context=CounterContext(count=0),
            cid=1,
            manager=MagicMock(),
        )

        await component.handle_event("increment", {}, socket)
        assert socket.context["count"] == 1

        await component.handle_event("increment", {}, socket)
        assert socket.context["count"] == 2

        await component.handle_event("set", {"value": 50}, socket)
        assert socket.context["count"] == 50

    def test_template_receives_meta_with_myself(self):
        """Test that template receives meta with myself for event targeting."""

        received_meta = None

        class Counter(LiveComponent[CounterContext]):
            def template(self, assigns, meta):
                nonlocal received_meta
                received_meta = meta
                return f"phx-target={meta.myself}"

        component = Counter()
        meta = ComponentMeta(cid=42, parent_meta=PyViewMeta())

        result = component.template({"count": 0}, meta)

        assert received_meta is meta
        assert received_meta.myself == 42
        assert "phx-target=42" in result


class TestLiveComponentWithEventDecorators:
    """Tests for LiveComponent with AutoEventDispatch (when available)."""

    def test_component_is_generic(self):
        """Test that LiveComponent accepts type parameter."""
        from typing import get_origin

        # LiveComponent should be generic
        assert get_origin(LiveComponent[CounterContext]) is LiveComponent

    def test_multiple_component_instances(self):
        """Test multiple instances of same component class are independent."""

        class Counter(LiveComponent[CounterContext]):
            def template(self, assigns, meta):
                return ""

        c1 = Counter()
        c2 = Counter()

        # Should be different instances
        assert c1 is not c2
