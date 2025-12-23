"""
Tests for AutoEventDispatch functionality.

Tests the descriptor pattern that enables automatic event handler routing
from function references in templates.
"""

import pytest

from pyview.events import AutoEventDispatch, event


class SampleView(AutoEventDispatch):
    """Sample view to verify auto-dispatch functionality."""

    def __init__(self):
        self.call_log = []

    @event
    async def increment(self, event, payload, socket):
        """Handler with @event (no args) - uses method name."""
        self.call_log.append(("increment", payload))
        return "increment called"

    @event()
    async def decrement(self, event, payload, socket):
        """Handler with @event() - uses method name."""
        self.call_log.append(("decrement", payload))
        return "decrement called"

    @event("custom-name")
    async def custom_handler(self, event, payload, socket):
        """Handler with explicit name."""
        self.call_log.append(("custom-name", payload))
        return "custom called"


def test_event_registration():
    """Test that events are registered correctly in the class."""
    view = SampleView()

    # Check that handlers are registered
    assert "increment" in view._event_handlers
    assert "decrement" in view._event_handlers
    assert "custom-name" in view._event_handlers

    # Verify all expected handlers are present
    assert set(view._event_handlers.keys()) == {"increment", "decrement", "custom-name"}


def test_descriptor_stringification():
    """Test that method references stringify to their event names."""
    view = SampleView()

    # Test stringification
    assert str(view.increment) == "increment"
    assert str(view.decrement) == "decrement"
    assert str(view.custom_handler) == "custom-name"


@pytest.mark.asyncio
async def test_event_dispatch():
    """Test that events are dispatched correctly to handler methods."""
    view = SampleView()

    # Test dispatching increment event
    result = await view.handle_event("increment", {"value": 1}, None)
    assert result == "increment called"
    assert view.call_log[-1] == ("increment", {"value": 1})

    # Test dispatching decrement event
    result = await view.handle_event("decrement", {"value": -1}, None)
    assert result == "decrement called"
    assert view.call_log[-1] == ("decrement", {"value": -1})

    # Test dispatching custom-name event
    result = await view.handle_event("custom-name", {"custom": True}, None)
    assert result == "custom called"
    assert view.call_log[-1] == ("custom-name", {"custom": True})


@pytest.mark.asyncio
async def test_method_callable():
    """Test that methods remain directly callable as normal async functions."""
    view = SampleView()

    # Test direct call (note: need to pass event parameter)
    result = await view.increment("increment", {"direct": True}, None)
    assert result == "increment called"
    assert view.call_log[-1] == ("increment", {"direct": True})


def test_string_interpolation():
    """Test that method references work in string interpolation (f-strings)."""
    view = SampleView()

    # Test that the method reference can be used in f-strings
    # This simulates how it would work in t-strings
    button_html = f'<button phx-click="{view.increment}">+</button>'
    assert 'phx-click="increment"' in button_html

    button_html2 = f'<button phx-click="{view.custom_handler}">Custom</button>'
    assert 'phx-click="custom-name"' in button_html2


def test_multiple_instances():
    """Test that each instance has independent state but shares handler registry."""
    view1 = SampleView()
    view2 = SampleView()

    # Instances have separate call logs
    assert view1.call_log is not view2.call_log
    assert view1.call_log == []
    assert view2.call_log == []

    # But share the same event handler registry (class-level)
    assert view1._event_handlers is view2._event_handlers


@pytest.mark.asyncio
async def test_unhandled_event_warning(caplog):
    """Test that unhandled events trigger a warning."""
    view = SampleView()

    # Attempt to handle an event that doesn't exist
    await view.handle_event("nonexistent", {}, None)

    # Should log a warning
    assert "Unhandled event: nonexistent" in caplog.text


class TestEventDecoratorVariants:
    """Test different ways to use the @event decorator."""

    def test_event_without_parens(self):
        """Test @event without parentheses."""

        class View(AutoEventDispatch):
            @event
            async def handler(self, event, payload, socket):
                return "called"

        view = View()
        assert "handler" in view._event_handlers
        assert str(view.handler) == "handler"

    def test_event_with_empty_parens(self):
        """Test @event() with empty parentheses."""

        class View(AutoEventDispatch):
            @event()
            async def handler(self, event, payload, socket):
                return "called"

        view = View()
        assert "handler" in view._event_handlers
        assert str(view.handler) == "handler"

    def test_event_with_single_name(self):
        """Test @event('custom-name') with single explicit name."""

        class View(AutoEventDispatch):
            @event("custom-name")
            async def handler(self, event, payload, socket):
                return "called"

        view = View()
        assert "custom-name" in view._event_handlers
        assert str(view.handler) == "custom-name"

    def test_event_with_multiple_names(self):
        """Test @event('name1', 'name2') with multiple names."""

        class View(AutoEventDispatch):
            @event("name1", "name2")
            async def handler(self, event, payload, socket):
                return "called"

        view = View()
        assert "name1" in view._event_handlers
        assert "name2" in view._event_handlers
        # Both should point to the same underlying function
        handler1 = view._event_handlers["name1"]
        handler2 = view._event_handlers["name2"]
        assert handler1 is handler2  # Same function object


class TestEventBindingErrors:
    """Test error handling when event binding fails."""

    @pytest.mark.asyncio
    async def test_raises_on_missing_required_param(self):
        """Test that missing required typed params raise ValueError."""

        class View(AutoEventDispatch):
            @event
            async def save(self, socket, user_id: int):
                return f"saved {user_id}"

        view = View()

        with pytest.raises(ValueError) as exc_info:
            await view.handle_event("save", {}, None)  # missing user_id

        assert "Event binding failed" in str(exc_info.value)
        assert "save" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_raises_on_conversion_error(self):
        """Test that type conversion errors raise ValueError."""

        class View(AutoEventDispatch):
            @event
            async def update(self, socket, count: int):
                return f"count is {count}"

        view = View()

        with pytest.raises(ValueError) as exc_info:
            await view.handle_event("update", {"count": "not-a-number"}, None)

        assert "Event binding failed" in str(exc_info.value)
