"""Tests for @typed_params compatibility with @event decorator."""

import pytest
from pyview.params import typed_params
from pyview.events import event


class TestEventDecoratorCompatibility:
    """Test that @typed_params works with @event decorator."""

    @pytest.mark.asyncio
    async def test_event_then_typed_params(self):
        """@event applied before @typed_params should work."""

        class MyView:
            @event("increment")
            @typed_params
            async def on_increment(self, event, amount: int = 1, socket=None):
                return {"event": event, "amount": amount}

        view = MyView()

        # Check that _event_names is preserved
        assert hasattr(view.on_increment, "_event_names")
        assert view.on_increment._event_names == ("increment",)

        # Test that conversion works
        result = await view.on_increment("increment", amount=["5"], socket=None)
        assert result == {"event": "increment", "amount": 5}

    @pytest.mark.asyncio
    async def test_typed_params_then_event(self):
        """@typed_params applied before @event should work."""

        class MyView:
            @typed_params
            @event("decrement")
            async def on_decrement(self, event, amount: int = 1, socket=None):
                return {"event": event, "amount": amount}

        view = MyView()

        # Check that _event_names is preserved
        assert hasattr(view.on_decrement, "_event_names")
        assert view.on_decrement._event_names == ("decrement",)

        # Test that conversion works
        result = await view.on_decrement("decrement", amount=["3"], socket=None)
        assert result == {"event": "decrement", "amount": 3}

    @pytest.mark.asyncio
    async def test_multiple_events(self):
        """@event with multiple event names should work."""

        class MyView:
            @event("click", "tap")
            @typed_params
            async def on_click(self, event, x: int, y: int, socket=None):
                return {"event": event, "x": x, "y": y}

        view = MyView()

        # Check that multiple event names are preserved
        assert hasattr(view.on_click, "_event_names")
        assert view.on_click._event_names == ("click", "tap")

        # Test that conversion works
        result = await view.on_click("click", x=["10"], y=["20"], socket=None)
        assert result == {"event": "click", "x": 10, "y": 20}

    @pytest.mark.asyncio
    async def test_with_optional_params(self):
        """@event with optional typed params should work."""

        class MyView:
            @event("update")
            @typed_params
            async def on_update(
                self,
                event,
                item_id: int,
                name: str = None,
                enabled: bool = True,
                socket=None,
            ):
                return {
                    "event": event,
                    "item_id": item_id,
                    "name": name,
                    "enabled": enabled,
                }

        view = MyView()

        # All params provided
        result = await view.on_update(
            "update", item_id=["123"], name=["test"], enabled=["false"], socket=None
        )
        assert result == {
            "event": "update",
            "item_id": 123,
            "name": "test",
            "enabled": False,
        }

        # Some params omitted (use defaults)
        result = await view.on_update("update", item_id=["456"], socket=None)
        assert result == {
            "event": "update",
            "item_id": 456,
            "name": None,
            "enabled": True,
        }

    @pytest.mark.asyncio
    async def test_traditional_event_handler_no_conversion(self):
        """Traditional @event handler without type hints should not convert."""

        class MyView:
            @event("save")
            @typed_params
            async def on_save(self, event, payload, socket):
                # payload should NOT be converted
                return {"event": event, "payload": payload}

        view = MyView()

        raw_payload = {"data": ["raw", "values"]}
        result = await view.on_save("save", raw_payload, None)

        # Payload should pass through unchanged
        assert result == {"event": "save", "payload": raw_payload}

    @pytest.mark.asyncio
    async def test_list_params_with_event(self):
        """List parameters should work with @event."""

        class MyView:
            @event("bulk_update")
            @typed_params
            async def on_bulk_update(self, event, ids: list[int], socket=None):
                return {"event": event, "ids": ids}

        view = MyView()

        result = await view.on_bulk_update(
            "bulk_update", ids=["1", "2", "3", "4"], socket=None
        )
        assert result == {"event": "bulk_update", "ids": [1, 2, 3, 4]}
