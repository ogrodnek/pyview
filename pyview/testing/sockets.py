"""Test socket implementations for testing LiveView applications."""

from __future__ import annotations

from typing import Any, Callable, Generic, Optional, TypeVar

from pyview.uploads import UploadConfig, UploadConstraints

T = TypeVar("T")


class TestSocket(Generic[T]):
    """
    Test double for LiveViewSocket that records interactions for state-based verification.

    TestSocket can act as either a connected or unconnected socket, recording all method
    calls for later assertions. This enables testing LiveView lifecycle methods without
    requiring actual WebSocket connections.

    Example:
        >>> socket = TestSocket(context={"count": 0})
        >>> await view.handle_event("increment", {}, socket)
        >>> assert socket.context["count"] == 1
        >>> assert len(socket.push_patches) == 0

    Example with navigation:
        >>> socket = TestSocket(context=MyContext())
        >>> await view.handle_event("go_home", {}, socket)
        >>> assert socket.push_patches == [("/", None)]

    Example with pub/sub:
        >>> socket = TestSocket()
        >>> await view.mount(socket, {})
        >>> assert "chat:lobby" in socket.subscriptions
    """

    def __init__(
        self,
        context: Optional[T] = None,
        connected: bool = True,
        live_title: Optional[str] = None,
    ) -> None:
        """
        Initialize a test socket.

        Args:
            context: Initial context/state for the LiveView. Defaults to empty dict.
            connected: Whether socket should appear connected. Set to False to test
                      mount() with UnconnectedSocket behavior.
            live_title: Initial page title.
        """
        self.context: T = context if context is not None else {}  # type: ignore
        self.connected = connected
        self.live_title = live_title

        # Recorded interactions for assertions
        self.push_patches: list[tuple[str, Optional[dict[str, Any]]]] = []
        self.push_navigates: list[tuple[str, Optional[dict[str, Any]]]] = []
        self.replace_navigates: list[tuple[str, Optional[dict[str, Any]]]] = []
        self.redirects: list[tuple[str, Optional[dict[str, Any]]]] = []
        self.subscriptions: list[str] = []
        self.broadcasts: list[tuple[str, Any]] = []
        self.scheduled_info: list[tuple[str, Any, float]] = []
        self.scheduled_info_once: list[tuple[Any, Optional[float]]] = []
        self.client_events: list[tuple[str, dict[str, Any]]] = []
        self.allowed_uploads: list[dict[str, Any]] = []

        # Match ConnectedLiveViewSocket interface
        self.pending_events: list[tuple[str, Any]] = []

    async def push_patch(self, path: str, params: Optional[dict[str, Any]] = None) -> None:
        """
        Record a push_patch navigation call.

        Args:
            path: The path to navigate to
            params: Optional query parameters
        """
        self.push_patches.append((path, params))

    async def push_navigate(self, path: str, params: Optional[dict[str, Any]] = None) -> None:
        """
        Record a push_navigate navigation call.

        Args:
            path: The path to navigate to
            params: Optional query parameters
        """
        self.push_navigates.append((path, params))

    async def replace_navigate(
        self, path: str, params: Optional[dict[str, Any]] = None
    ) -> None:
        """
        Record a replace_navigate navigation call.

        Args:
            path: The path to navigate to
            params: Optional query parameters
        """
        self.replace_navigates.append((path, params))

    async def redirect(self, path: str, params: Optional[dict[str, Any]] = None) -> None:
        """
        Record a redirect call.

        Args:
            path: The path to redirect to
            params: Optional query parameters
        """
        self.redirects.append((path, params))

    async def subscribe(self, topic: str) -> None:
        """
        Record a pub/sub subscription.

        Args:
            topic: The topic to subscribe to
        """
        self.subscriptions.append(topic)

    async def broadcast(self, topic: str, message: Any) -> None:
        """
        Record a pub/sub broadcast.

        Args:
            topic: The topic to broadcast to
            message: The message to broadcast
        """
        self.broadcasts.append((topic, message))

    def schedule_info(self, event: Any, seconds: float) -> None:
        """
        Record a recurring scheduled info event.

        Args:
            event: The event to schedule
            seconds: Interval in seconds
        """
        self.scheduled_info.append(("recurring", event, seconds))

    def schedule_info_once(self, event: Any, seconds: Optional[float] = None) -> None:
        """
        Record a one-time scheduled info event.

        Args:
            event: The event to schedule
            seconds: Delay in seconds (None for immediate)
        """
        self.scheduled_info_once.append((event, seconds))

    async def push_event(self, event: str, value: dict[str, Any]) -> None:
        """
        Record a client-side event push.

        Args:
            event: The event name
            value: The event payload
        """
        self.client_events.append((event, value))

    def allow_upload(
        self,
        upload_name: str,
        constraints: UploadConstraints,
        auto_upload: bool = False,
        progress: Optional[Callable] = None,
        external: Optional[Callable] = None,
        entry_complete: Optional[Callable] = None,
    ) -> UploadConfig:
        """
        Record an upload configuration and return a minimal UploadConfig.

        Args:
            upload_name: Name of the upload
            constraints: Upload constraints
            auto_upload: Whether to auto-upload
            progress: Progress callback
            external: External callback
            entry_complete: Entry complete callback

        Returns:
            UploadConfig instance
        """
        self.allowed_uploads.append(
            {
                "name": upload_name,
                "constraints": constraints,
                "auto_upload": auto_upload,
                "progress": progress,
                "external": external,
                "entry_complete": entry_complete,
            }
        )
        return UploadConfig(
            name=upload_name,
            constraints=constraints,
            autoUpload=auto_upload,
            progress_callback=progress,
            external_callback=external,
            entry_complete_callback=entry_complete,
        )

    def assert_push_patch(self, path: str, params: Optional[dict[str, Any]] = None) -> None:
        """
        Assert that push_patch was called with the given arguments.

        Args:
            path: Expected path
            params: Expected params

        Raises:
            AssertionError: If the call was not recorded
        """
        assert (path, params) in self.push_patches, (
            f"Expected push_patch({path!r}, {params!r}) but got: {self.push_patches}"
        )

    def assert_push_navigate(self, path: str, params: Optional[dict[str, Any]] = None) -> None:
        """
        Assert that push_navigate was called with the given arguments.

        Args:
            path: Expected path
            params: Expected params

        Raises:
            AssertionError: If the call was not recorded
        """
        assert (path, params) in self.push_navigates, (
            f"Expected push_navigate({path!r}, {params!r}) but got: {self.push_navigates}"
        )

    def assert_redirect(self, path: str, params: Optional[dict[str, Any]] = None) -> None:
        """
        Assert that redirect was called with the given arguments.

        Args:
            path: Expected path
            params: Expected params

        Raises:
            AssertionError: If the call was not recorded
        """
        assert (path, params) in self.redirects, (
            f"Expected redirect({path!r}, {params!r}) but got: {self.redirects}"
        )

    def assert_subscribed(self, topic: str) -> None:
        """
        Assert that socket subscribed to the given topic.

        Args:
            topic: Expected topic

        Raises:
            AssertionError: If subscription was not recorded
        """
        assert topic in self.subscriptions, (
            f"Expected subscription to {topic!r} but got: {self.subscriptions}"
        )

    def assert_broadcast(self, topic: str, message: Any) -> None:
        """
        Assert that a broadcast was made to the given topic with the given message.

        Args:
            topic: Expected topic
            message: Expected message

        Raises:
            AssertionError: If broadcast was not recorded
        """
        assert (topic, message) in self.broadcasts, (
            f"Expected broadcast({topic!r}, {message!r}) but got: {self.broadcasts}"
        )

    def clear_history(self) -> None:
        """Clear all recorded interactions."""
        self.push_patches.clear()
        self.push_navigates.clear()
        self.replace_navigates.clear()
        self.redirects.clear()
        self.subscriptions.clear()
        self.broadcasts.clear()
        self.scheduled_info.clear()
        self.scheduled_info_once.clear()
        self.client_events.clear()
        self.allowed_uploads.clear()
        self.pending_events.clear()

    def __repr__(self) -> str:
        """Return a helpful representation for debugging."""
        return (
            f"TestSocket(context={self.context!r}, connected={self.connected}, "
            f"live_title={self.live_title!r})"
        )
