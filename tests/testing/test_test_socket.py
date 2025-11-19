"""Tests for TestSocket test utility."""

import pytest

from pyview.testing import TestSocket
from pyview.uploads import UploadConfig, UploadConstraints


class TestTestSocketInitialization:
    """Tests for TestSocket initialization."""

    def test_default_initialization(self):
        socket = TestSocket()
        assert socket.context == {}
        assert socket.connected is True
        assert socket.live_title is None

    def test_initialization_with_context(self):
        context = {"count": 5}
        socket = TestSocket(context=context)
        assert socket.context == {"count": 5}

    def test_initialization_disconnected(self):
        socket = TestSocket(connected=False)
        assert socket.connected is False

    def test_initialization_with_title(self):
        socket = TestSocket(live_title="Test Page")
        assert socket.live_title == "Test Page"

    def test_initialization_clears_history(self):
        socket = TestSocket()
        assert socket.push_patches == []
        assert socket.push_navigates == []
        assert socket.replace_navigates == []
        assert socket.redirects == []
        assert socket.subscriptions == []
        assert socket.broadcasts == []
        assert socket.scheduled_info == []
        assert socket.scheduled_info_once == []
        assert socket.client_events == []
        assert socket.allowed_uploads == []
        assert socket.pending_events == []


class TestTestSocketNavigation:
    """Tests for navigation method recording."""

    @pytest.mark.asyncio
    async def test_push_patch_records_call(self):
        socket = TestSocket()
        await socket.push_patch("/users")
        assert socket.push_patches == [("/users", None)]

    @pytest.mark.asyncio
    async def test_push_patch_with_params(self):
        socket = TestSocket()
        await socket.push_patch("/users", {"id": "123"})
        assert socket.push_patches == [("/users", {"id": "123"})]

    @pytest.mark.asyncio
    async def test_multiple_push_patches(self):
        socket = TestSocket()
        await socket.push_patch("/users")
        await socket.push_patch("/profile", {"tab": "settings"})
        assert socket.push_patches == [
            ("/users", None),
            ("/profile", {"tab": "settings"}),
        ]

    @pytest.mark.asyncio
    async def test_push_navigate_records_call(self):
        socket = TestSocket()
        await socket.push_navigate("/home")
        assert socket.push_navigates == [("/home", None)]

    @pytest.mark.asyncio
    async def test_push_navigate_with_params(self):
        socket = TestSocket()
        await socket.push_navigate("/search", {"q": "test"})
        assert socket.push_navigates == [("/search", {"q": "test"})]

    @pytest.mark.asyncio
    async def test_replace_navigate_records_call(self):
        socket = TestSocket()
        await socket.replace_navigate("/login")
        assert socket.replace_navigates == [("/login", None)]

    @pytest.mark.asyncio
    async def test_redirect_records_call(self):
        socket = TestSocket()
        await socket.redirect("/external")
        assert socket.redirects == [("/external", None)]

    @pytest.mark.asyncio
    async def test_redirect_with_params(self):
        socket = TestSocket()
        await socket.redirect("/callback", {"code": "abc123"})
        assert socket.redirects == [("/callback", {"code": "abc123"})]


class TestTestSocketPubSub:
    """Tests for pub/sub method recording."""

    @pytest.mark.asyncio
    async def test_subscribe_records_topic(self):
        socket = TestSocket()
        await socket.subscribe("chat:lobby")
        assert socket.subscriptions == ["chat:lobby"]

    @pytest.mark.asyncio
    async def test_multiple_subscriptions(self):
        socket = TestSocket()
        await socket.subscribe("chat:lobby")
        await socket.subscribe("user:123")
        assert socket.subscriptions == ["chat:lobby", "user:123"]

    @pytest.mark.asyncio
    async def test_broadcast_records_message(self):
        socket = TestSocket()
        await socket.broadcast("chat:lobby", {"msg": "Hello"})
        assert socket.broadcasts == [("chat:lobby", {"msg": "Hello"})]

    @pytest.mark.asyncio
    async def test_multiple_broadcasts(self):
        socket = TestSocket()
        await socket.broadcast("chat:lobby", {"msg": "Hello"})
        await socket.broadcast("chat:lobby", {"msg": "Goodbye"})
        assert socket.broadcasts == [
            ("chat:lobby", {"msg": "Hello"}),
            ("chat:lobby", {"msg": "Goodbye"}),
        ]


class TestTestSocketScheduling:
    """Tests for scheduling method recording."""

    def test_schedule_info_records_event(self):
        socket = TestSocket()
        socket.schedule_info("ping", 5.0)
        assert socket.scheduled_info == [("recurring", "ping", 5.0)]

    def test_multiple_scheduled_info(self):
        socket = TestSocket()
        socket.schedule_info("ping", 5.0)
        socket.schedule_info("refresh", 10.0)
        assert socket.scheduled_info == [
            ("recurring", "ping", 5.0),
            ("recurring", "refresh", 10.0),
        ]

    def test_schedule_info_once_records_event(self):
        socket = TestSocket()
        socket.schedule_info_once("timeout", 3.0)
        assert socket.scheduled_info_once == [("timeout", 3.0)]

    def test_schedule_info_once_without_seconds(self):
        socket = TestSocket()
        socket.schedule_info_once("immediate")
        assert socket.scheduled_info_once == [("immediate", None)]

    def test_multiple_schedule_info_once(self):
        socket = TestSocket()
        socket.schedule_info_once("timeout", 3.0)
        socket.schedule_info_once("reminder", 10.0)
        assert socket.scheduled_info_once == [
            ("timeout", 3.0),
            ("reminder", 10.0),
        ]


class TestTestSocketClientEvents:
    """Tests for client event recording."""

    @pytest.mark.asyncio
    async def test_push_event_records_call(self):
        socket = TestSocket()
        await socket.push_event("highlight", {"id": "item-1"})
        assert socket.client_events == [("highlight", {"id": "item-1"})]

    @pytest.mark.asyncio
    async def test_multiple_push_events(self):
        socket = TestSocket()
        await socket.push_event("highlight", {"id": "item-1"})
        await socket.push_event("scroll", {"to": "top"})
        assert socket.client_events == [
            ("highlight", {"id": "item-1"}),
            ("scroll", {"to": "top"}),
        ]


class TestTestSocketUploads:
    """Tests for upload configuration recording."""

    def test_allow_upload_records_config(self):
        socket = TestSocket()
        constraints = UploadConstraints(max_file_size=1024, accept=[".txt"])

        config = socket.allow_upload("file", constraints)

        assert len(socket.allowed_uploads) == 1
        assert socket.allowed_uploads[0]["name"] == "file"
        assert socket.allowed_uploads[0]["constraints"] == constraints
        assert socket.allowed_uploads[0]["auto_upload"] is False
        assert isinstance(config, UploadConfig)

    def test_allow_upload_with_options(self):
        socket = TestSocket()
        constraints = UploadConstraints(max_file_size=2048, accept=[".jpg"])

        def progress_cb():
            pass

        config = socket.allow_upload(
            "images",
            constraints,
            auto_upload=True,
            progress=progress_cb,
        )

        assert len(socket.allowed_uploads) == 1
        assert socket.allowed_uploads[0]["auto_upload"] is True
        assert socket.allowed_uploads[0]["progress"] == progress_cb
        assert config.autoUpload is True


class TestTestSocketAssertions:
    """Tests for assertion helper methods."""

    @pytest.mark.asyncio
    async def test_assert_push_patch_success(self):
        socket = TestSocket()
        await socket.push_patch("/users")
        socket.assert_push_patch("/users")  # Should not raise

    @pytest.mark.asyncio
    async def test_assert_push_patch_with_params(self):
        socket = TestSocket()
        await socket.push_patch("/users", {"id": "123"})
        socket.assert_push_patch("/users", {"id": "123"})  # Should not raise

    @pytest.mark.asyncio
    async def test_assert_push_patch_failure(self):
        socket = TestSocket()
        with pytest.raises(AssertionError, match="Expected push_patch"):
            socket.assert_push_patch("/users")

    @pytest.mark.asyncio
    async def test_assert_push_navigate_success(self):
        socket = TestSocket()
        await socket.push_navigate("/home")
        socket.assert_push_navigate("/home")  # Should not raise

    @pytest.mark.asyncio
    async def test_assert_push_navigate_failure(self):
        socket = TestSocket()
        with pytest.raises(AssertionError, match="Expected push_navigate"):
            socket.assert_push_navigate("/home")

    @pytest.mark.asyncio
    async def test_assert_redirect_success(self):
        socket = TestSocket()
        await socket.redirect("/login")
        socket.assert_redirect("/login")  # Should not raise

    @pytest.mark.asyncio
    async def test_assert_redirect_failure(self):
        socket = TestSocket()
        with pytest.raises(AssertionError, match="Expected redirect"):
            socket.assert_redirect("/login")

    @pytest.mark.asyncio
    async def test_assert_subscribed_success(self):
        socket = TestSocket()
        await socket.subscribe("chat:lobby")
        socket.assert_subscribed("chat:lobby")  # Should not raise

    @pytest.mark.asyncio
    async def test_assert_subscribed_failure(self):
        socket = TestSocket()
        with pytest.raises(AssertionError, match="Expected subscription"):
            socket.assert_subscribed("chat:lobby")

    @pytest.mark.asyncio
    async def test_assert_broadcast_success(self):
        socket = TestSocket()
        await socket.broadcast("chat:lobby", {"msg": "Hello"})
        socket.assert_broadcast("chat:lobby", {"msg": "Hello"})  # Should not raise

    @pytest.mark.asyncio
    async def test_assert_broadcast_failure(self):
        socket = TestSocket()
        with pytest.raises(AssertionError, match="Expected broadcast"):
            socket.assert_broadcast("chat:lobby", {"msg": "Hello"})


class TestTestSocketUtilities:
    """Tests for utility methods."""

    @pytest.mark.asyncio
    async def test_clear_history(self):
        socket = TestSocket()

        # Add various interactions
        await socket.push_patch("/users")
        await socket.push_navigate("/home")
        await socket.subscribe("chat:lobby")
        await socket.broadcast("chat:lobby", {"msg": "Hi"})
        socket.schedule_info("ping", 5.0)
        socket.schedule_info_once("timeout", 3.0)
        await socket.push_event("highlight", {"id": "1"})

        # Clear everything
        socket.clear_history()

        # Verify all lists are empty
        assert socket.push_patches == []
        assert socket.push_navigates == []
        assert socket.replace_navigates == []
        assert socket.redirects == []
        assert socket.subscriptions == []
        assert socket.broadcasts == []
        assert socket.scheduled_info == []
        assert socket.scheduled_info_once == []
        assert socket.client_events == []
        assert socket.allowed_uploads == []
        assert socket.pending_events == []

    def test_repr(self):
        socket = TestSocket(context={"count": 5}, live_title="Test")
        repr_str = repr(socket)
        assert "TestSocket" in repr_str
        assert "count" in repr_str
        assert "connected=True" in repr_str
        assert "Test" in repr_str


class TestTestSocketTypeHints:
    """Tests for generic type support."""

    def test_generic_type_with_dict(self):
        from typing import TypedDict

        class CountContext(TypedDict):
            count: int

        context: CountContext = {"count": 0}
        socket = TestSocket[CountContext](context=context)

        # Type checkers should understand socket.context is CountContext
        assert socket.context["count"] == 0

    def test_generic_type_with_dataclass(self):
        from dataclasses import dataclass

        @dataclass
        class UserContext:
            username: str
            age: int

        context = UserContext(username="alice", age=30)
        socket = TestSocket[UserContext](context=context)

        # Type checkers should understand socket.context is UserContext
        assert socket.context.username == "alice"
        assert socket.context.age == 30
