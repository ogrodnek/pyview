#!/usr/bin/env python3
"""
Simple test script to verify AutoEventDispatch functionality.
"""

import asyncio
import sys

from pyview.events import AutoEventDispatch, event


class TestView(AutoEventDispatch):
    """Test view to verify auto-dispatch functionality."""

    def __init__(self):
        self.call_log = []

    @event
    async def increment(self, payload, socket):
        """Handler with @event (no args) - uses method name."""
        self.call_log.append(("increment", payload))
        return "increment called"

    @event()
    async def decrement(self, payload, socket):
        """Handler with @event() - uses method name."""
        self.call_log.append(("decrement", payload))
        return "decrement called"

    @event("custom-name")
    async def custom_handler(self, payload, socket):
        """Handler with explicit name."""
        self.call_log.append(("custom-name", payload))
        return "custom called"


async def test_descriptor_stringification():
    """Test that methods stringify to their event names."""
    print("Testing descriptor stringification...")

    view = TestView()

    # Test stringification
    assert str(view.increment) == "increment", f"Expected 'increment', got '{str(view.increment)}'"
    assert str(view.decrement) == "decrement", f"Expected 'decrement', got '{str(view.decrement)}'"
    assert str(view.custom_handler) == "custom-name", f"Expected 'custom-name', got '{str(view.custom_handler)}'"

    print("✓ Descriptor stringification works correctly")


async def test_event_dispatch():
    """Test that events are dispatched correctly."""
    print("\nTesting event dispatch...")

    view = TestView()

    # Test dispatching
    result = await view.handle_event("increment", {"value": 1}, None)
    assert result == "increment called"
    assert view.call_log[-1] == ("increment", {"value": 1})

    result = await view.handle_event("decrement", {"value": -1}, None)
    assert result == "decrement called"
    assert view.call_log[-1] == ("decrement", {"value": -1})

    result = await view.handle_event("custom-name", {"custom": True}, None)
    assert result == "custom called"
    assert view.call_log[-1] == ("custom-name", {"custom": True})

    print("✓ Event dispatch works correctly")


async def test_method_callable():
    """Test that methods remain callable."""
    print("\nTesting method callability...")

    view = TestView()

    # Test direct calls
    result = await view.increment({"direct": True}, None)
    assert result == "increment called"
    assert view.call_log[-1] == ("increment", {"direct": True})

    print("✓ Methods remain callable")


async def test_string_interpolation():
    """Test that methods work in string interpolation."""
    print("\nTesting string interpolation...")

    view = TestView()

    # Test that the method reference can be used in f-strings
    # (simulates how it would work in t-strings)
    button_html = f"""<button phx-click="{view.increment}">+</button>"""
    assert "phx-click=\"increment\"" in button_html

    button_html2 = f"""<button phx-click="{view.custom_handler}">Custom</button>"""
    assert "phx-click=\"custom-name\"" in button_html2

    print("✓ String interpolation works correctly")


async def test_event_registration():
    """Test that events are registered correctly."""
    print("\nTesting event registration...")

    view = TestView()

    # Check that handlers are registered
    assert "increment" in view._event_handlers
    assert "decrement" in view._event_handlers
    assert "custom-name" in view._event_handlers

    print(f"✓ Registered event handlers: {list(view._event_handlers.keys())}")


async def main():
    """Run all tests."""
    print("=" * 60)
    print("AutoEventDispatch Test Suite")
    print("=" * 60)

    try:
        await test_event_registration()
        await test_descriptor_stringification()
        await test_event_dispatch()
        await test_method_callable()
        await test_string_interpolation()

        print("\n" + "=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
