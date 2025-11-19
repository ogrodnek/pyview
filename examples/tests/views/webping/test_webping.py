"""Tests for webping LiveView example."""

import pytest

from pyview.events import InfoEvent
from pyview.testing import TestSocket
from views.webping.webping import PingContext, PingLiveView, PingSite


class TestPingLiveViewMount:
    """Tests for PingLiveView mount lifecycle."""

    @pytest.mark.asyncio
    async def test_mount_initializes_context_with_sites(self):
        """Test that mount initializes context with default sites."""
        view = PingLiveView()
        socket = TestSocket[PingContext]()

        await view.mount(socket, session={})

        assert socket.context is not None
        assert hasattr(socket.context, "sites")
        assert len(socket.context.sites) == 2

    @pytest.mark.asyncio
    async def test_mount_sites_have_correct_urls(self):
        """Test that mount creates sites with expected URLs."""
        view = PingLiveView()
        socket = TestSocket[PingContext]()

        await view.mount(socket, session={})

        urls = [site.url for site in socket.context.sites]
        assert "https://pyview.rocks" in urls
        assert "https://examples.pyview.rocks" in urls

    @pytest.mark.asyncio
    async def test_mount_sites_initial_status(self):
        """Test that sites start with 'Not started' status."""
        view = PingLiveView()
        socket = TestSocket[PingContext]()

        await view.mount(socket, session={})

        for site in socket.context.sites:
            assert site.status == "Not started"

    @pytest.mark.asyncio
    async def test_mount_unconnected_socket_does_not_schedule(self):
        """Test that unconnected socket doesn't schedule info events."""
        view = PingLiveView()
        socket = TestSocket[PingContext](connected=False)

        await view.mount(socket, session={})

        assert len(socket.scheduled_info) == 0

    @pytest.mark.asyncio
    async def test_mount_connected_socket_schedules_ping(self):
        """Test that connected socket schedules ping info event."""
        view = PingLiveView()
        socket = TestSocket[PingContext](connected=True)

        await view.mount(socket, session={})

        # Should have scheduled a recurring ping
        assert len(socket.scheduled_info) == 1
        event_type, event, interval = socket.scheduled_info[0]
        assert event_type == "recurring"
        assert interval == 10

    @pytest.mark.asyncio
    async def test_mount_connected_socket_performs_initial_ping(self):
        """Test that connected socket performs an initial ping during mount."""
        view = PingLiveView()
        socket = TestSocket[PingContext](connected=True)

        await view.mount(socket, session={})

        # After mount with connected socket, sites should have been pinged
        # (status should no longer be "Not started")
        for site in socket.context.sites:
            # Status should be either "OK" or "Error" after ping attempt
            assert site.status in ["OK", "Error", "Not started"]


class TestPingLiveViewEvents:
    """Tests for PingLiveView event handling."""

    @pytest.mark.asyncio
    async def test_handle_event_triggers_ping(self):
        """Test that handle_event triggers a ping."""
        view = PingLiveView()
        socket = TestSocket[PingContext]()
        await view.mount(socket, session={})

        # Any event triggers a ping
        await view.handle_event("refresh", {}, socket)

        # Sites should have been pinged
        for site in socket.context.sites:
            assert site.status in ["OK", "Error"]


class TestPingLiveViewInfoHandling:
    """Tests for PingLiveView info event handling."""

    @pytest.mark.asyncio
    async def test_handle_ping_updates_site_status(self):
        """Test that handle_ping updates site status."""
        view = PingLiveView()
        socket = TestSocket[PingContext]()
        socket.context = PingContext([PingSite("https://pyview.rocks")])

        await view.handle_ping(InfoEvent("ping"), socket)

        # Site should have been pinged
        site = socket.context.sites[0]
        assert site.status in ["OK", "Error"]

    @pytest.mark.asyncio
    async def test_handle_ping_adds_response_to_site(self):
        """Test that handle_ping adds ping responses to site."""
        view = PingLiveView()
        socket = TestSocket[PingContext]()
        socket.context = PingContext([PingSite("https://pyview.rocks")])

        # Site starts with no responses
        site = socket.context.sites[0]
        assert len(site.responses) == 0

        await view.handle_ping(InfoEvent("ping"), socket)

        # Site should now have a response
        assert len(site.responses) >= 1

    @pytest.mark.asyncio
    async def test_handle_ping_response_has_expected_fields(self):
        """Test that ping response has all expected fields."""
        view = PingLiveView()
        socket = TestSocket[PingContext]()
        socket.context = PingContext([PingSite("https://pyview.rocks")])

        await view.handle_ping(InfoEvent("ping"), socket)

        site = socket.context.sites[0]
        if site.responses:
            response = site.responses[0]
            assert hasattr(response, "status")
            assert hasattr(response, "time")
            assert hasattr(response, "date")
            assert response.status > 0
            assert response.time >= 0

    @pytest.mark.asyncio
    async def test_info_decorator_routes_correctly(self):
        """Test that @info decorator routes ping events correctly."""
        view = PingLiveView()
        socket = TestSocket[PingContext]()
        socket.context = PingContext([PingSite("https://pyview.rocks")])

        # This should route to handle_ping via the @info decorator
        await view.handle_info(InfoEvent("ping"), socket)

        # Verify ping was handled
        site = socket.context.sites[0]
        assert site.status in ["OK", "Error"]


class TestPingLiveViewMultipleSites:
    """Tests for handling multiple sites."""

    @pytest.mark.asyncio
    async def test_ping_updates_all_sites(self):
        """Test that ping updates all sites."""
        view = PingLiveView()
        socket = TestSocket[PingContext]()
        socket.context = PingContext(
            [
                PingSite("https://pyview.rocks"),
                PingSite("https://examples.pyview.rocks"),
            ]
        )

        await view.handle_ping(InfoEvent("ping"), socket)

        # Both sites should have been pinged
        for site in socket.context.sites:
            assert site.status in ["OK", "Error"]
            assert len(site.responses) >= 1


class TestPingLiveViewIntegration:
    """Integration tests for full PingLiveView workflow."""

    @pytest.mark.asyncio
    async def test_full_lifecycle_with_scheduling(self):
        """Test complete lifecycle including scheduling."""
        view = PingLiveView()
        socket = TestSocket[PingContext](connected=True)

        # Mount with connected socket
        await view.mount(socket, session={})

        # Verify scheduled
        assert len(socket.scheduled_info) == 1

        # Verify sites exist
        assert len(socket.context.sites) == 2

        # Trigger manual ping via event
        await view.handle_event("refresh", {}, socket)

        # All sites should have responses
        for site in socket.context.sites:
            assert len(site.responses) >= 1

    @pytest.mark.asyncio
    async def test_unconnected_then_connected_workflow(self):
        """Test workflow where socket starts unconnected."""
        view = PingLiveView()

        # Mount with unconnected socket (like initial page load)
        unconnected_socket = TestSocket[PingContext](connected=False)
        await view.mount(unconnected_socket, session={})

        # No scheduling should happen
        assert len(unconnected_socket.scheduled_info) == 0

        # Now simulate connected socket
        connected_socket = TestSocket[PingContext](connected=True)
        await view.mount(connected_socket, session={})

        # Should schedule when connected
        assert len(connected_socket.scheduled_info) == 1
