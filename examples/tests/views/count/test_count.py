"""Tests for count LiveView example."""

import pytest
from urllib.parse import urlparse

from pyview.testing import TestSocket
from views.count.count import CountContext, CountLiveView


class TestCountLiveViewMount:
    """Tests for CountLiveView mount lifecycle."""

    @pytest.mark.asyncio
    async def test_mount_initializes_count_to_zero(self):
        """Test that mount initializes the count to 0."""
        view = CountLiveView()
        socket = TestSocket[CountContext]()

        await view.mount(socket, session={})

        assert socket.context == {"count": 0}

    @pytest.mark.asyncio
    async def test_mount_with_session_data(self):
        """Test that mount works with session data."""
        view = CountLiveView()
        socket = TestSocket[CountContext]()
        session = {"user_id": "123"}

        await view.mount(socket, session)

        assert socket.context["count"] == 0


class TestCountLiveViewEvents:
    """Tests for CountLiveView event handling."""

    @pytest.mark.asyncio
    async def test_increment_event_increases_count(self):
        """Test that increment event increases the count by 1."""
        view = CountLiveView()
        socket = TestSocket[CountContext](context={"count": 0})

        await view.handle_event("increment", {}, socket)

        assert socket.context["count"] == 1

    @pytest.mark.asyncio
    async def test_increment_event_from_non_zero(self):
        """Test increment from a non-zero starting point."""
        view = CountLiveView()
        socket = TestSocket[CountContext](context={"count": 5})

        await view.handle_event("increment", {}, socket)

        assert socket.context["count"] == 6

    @pytest.mark.asyncio
    async def test_decrement_event_decreases_count(self):
        """Test that decrement event decreases the count by 1."""
        view = CountLiveView()
        socket = TestSocket[CountContext](context={"count": 5})

        await view.handle_event("decrement", {}, socket)

        assert socket.context["count"] == 4

    @pytest.mark.asyncio
    async def test_decrement_to_negative(self):
        """Test that decrement can go negative."""
        view = CountLiveView()
        socket = TestSocket[CountContext](context={"count": 0})

        await view.handle_event("decrement", {}, socket)

        assert socket.context["count"] == -1

    @pytest.mark.asyncio
    async def test_multiple_increments(self):
        """Test multiple increment operations."""
        view = CountLiveView()
        socket = TestSocket[CountContext](context={"count": 0})

        await view.handle_event("increment", {}, socket)
        await view.handle_event("increment", {}, socket)
        await view.handle_event("increment", {}, socket)

        assert socket.context["count"] == 3

    @pytest.mark.asyncio
    async def test_mixed_increment_and_decrement(self):
        """Test mixed increment and decrement operations."""
        view = CountLiveView()
        socket = TestSocket[CountContext](context={"count": 0})

        await view.handle_event("increment", {}, socket)
        await view.handle_event("increment", {}, socket)
        await view.handle_event("decrement", {}, socket)

        assert socket.context["count"] == 1

    @pytest.mark.asyncio
    async def test_unknown_event_is_ignored(self):
        """Test that unknown events don't change the count."""
        view = CountLiveView()
        socket = TestSocket[CountContext](context={"count": 5})

        await view.handle_event("unknown_event", {}, socket)

        assert socket.context["count"] == 5


class TestCountLiveViewParams:
    """Tests for CountLiveView URL parameter handling."""

    @pytest.mark.asyncio
    async def test_handle_params_sets_count_from_url(self):
        """Test that handle_params sets count from URL parameter 'c'."""
        view = CountLiveView()
        socket = TestSocket[CountContext](context={"count": 0})
        url = urlparse("/?c=42")
        params = {"c": ["42"]}

        await view.handle_params(url, params, socket)

        assert socket.context["count"] == 42

    @pytest.mark.asyncio
    async def test_handle_params_without_c_param(self):
        """Test that handle_params without 'c' parameter doesn't change count."""
        view = CountLiveView()
        socket = TestSocket[CountContext](context={"count": 5})
        url = urlparse("/")
        params = {}

        await view.handle_params(url, params, socket)

        assert socket.context["count"] == 5

    @pytest.mark.asyncio
    async def test_handle_params_with_negative_count(self):
        """Test handle_params with negative count value."""
        view = CountLiveView()
        socket = TestSocket[CountContext](context={"count": 0})
        url = urlparse("/?c=-10")
        params = {"c": ["-10"]}

        await view.handle_params(url, params, socket)

        assert socket.context["count"] == -10


class TestCountLiveViewIntegration:
    """Integration tests for full CountLiveView lifecycle."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        """Test complete lifecycle: mount, events, and params."""
        view = CountLiveView()
        socket = TestSocket[CountContext]()

        # Mount
        await view.mount(socket, session={})
        assert socket.context["count"] == 0

        # Increment
        await view.handle_event("increment", {}, socket)
        assert socket.context["count"] == 1

        # Set via params
        url = urlparse("/?c=100")
        params = {"c": ["100"]}
        await view.handle_params(url, params, socket)
        assert socket.context["count"] == 100

        # Decrement
        await view.handle_event("decrement", {}, socket)
        assert socket.context["count"] == 99
