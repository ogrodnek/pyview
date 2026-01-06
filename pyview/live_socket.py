from __future__ import annotations

import datetime
import json
import logging
import uuid
from contextlib import suppress
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Generic,
    Optional,
    TypeAlias,
    TypeGuard,
    TypeVar,
    Union,
)
from urllib.parse import urlencode, urlparse

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from starlette.websockets import WebSocket

from pyview.async_stream_runner import AsyncStreamRunner
from pyview.binding.helpers import call_handle_params
from pyview.binding.params import _as_list
from pyview.components.manager import ComponentsManager
from pyview.events import InfoEvent
from pyview.meta import PyViewMeta
from pyview.template.render_diff import calc_diff
from pyview.uploads import UploadConfig, UploadConstraints, UploadManager
from pyview.vendor.flet.pubsub import PubSub, PubSubHub

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from .instrumentation import InstrumentationProvider
    from .live_routes import LiveViewLookup
    from .live_view import LiveView


pub_sub_hub = PubSubHub()

T = TypeVar("T")


def is_connected(socket: LiveViewSocket[T]) -> TypeGuard[ConnectedLiveViewSocket[T]]:
    return socket.connected


class UnconnectedLiveView:
    """Stub liveview that raises if send_parent() is called in unconnected phase."""

    async def handle_event(self, event: str, payload: dict[str, Any], socket: Any) -> None:
        raise RuntimeError(
            "send_parent() is not available during initial HTTP render. "
            "Component events only work after WebSocket connection."
        )


class UnconnectedSocket(Generic[T]):
    context: T
    live_title: Optional[str] = None
    connected: bool = False
    _liveview: UnconnectedLiveView
    components: ComponentsManager

    def __init__(self) -> None:
        self._liveview = UnconnectedLiveView()
        self.components = ComponentsManager(self)

    @property
    def liveview(self) -> UnconnectedLiveView:
        return self._liveview

    def allow_upload(
        self,
        upload_name: str,
        constraints: UploadConstraints,
        auto_upload: bool = False,
        progress: Optional[Callable] = None,
        external: Optional[Callable] = None,
        entry_complete: Optional[Callable] = None,
    ) -> UploadConfig:
        return UploadConfig(
            name=upload_name,
            constraints=constraints,
            autoUpload=auto_upload,
            progress_callback=progress,
            external_callback=external,
            entry_complete_callback=entry_complete,
        )


class ConnectedLiveViewSocket(Generic[T]):
    context: T
    live_title: Optional[str] = None
    pending_events: list[tuple[str, Any]]
    upload_manager: UploadManager
    prev_rendered: Optional[dict[str, Any]] = None

    def __init__(
        self,
        websocket: WebSocket,
        topic: str,
        liveview: LiveView,
        scheduler: AsyncIOScheduler,
        instrumentation: InstrumentationProvider,
        routes: Optional[LiveViewLookup] = None,
    ):
        self.websocket = websocket
        self.topic = topic
        self.liveview = liveview
        self.instrumentation = instrumentation
        self.routes = routes
        self.scheduled_jobs = set()
        self.connected = True
        self.pub_sub = PubSub(pub_sub_hub, topic)
        self.pending_events = []
        self.upload_manager = UploadManager()
        self.stream_runner = AsyncStreamRunner(self)
        self.scheduler = scheduler
        self.components = ComponentsManager(self)

    @property
    def meta(self) -> PyViewMeta:
        return PyViewMeta(socket=self)

    async def render_with_components(self) -> dict[str, Any]:
        """
        Render the LiveView and all its components.

        Handles the full component lifecycle:
        1. Begin render cycle (track seen components)
        2. Render parent LiveView template
        3. Run pending component lifecycle (mount/update)
        4. Prune stale components not in this render
        5. Render all component templates with ROOT flag

        Returns:
            Rendered tree in Phoenix wire format
        """
        import sys

        # Start new render cycle - track which components are seen during parent render
        self.components.begin_render()

        rendered = (await self.liveview.render(self.context, self.meta)).tree()

        # Component rendering requires Python 3.14+ (t-string support)
        if sys.version_info < (3, 14):
            return rendered

        from pyview.components.lifecycle import run_nested_component_lifecycle

        # Run component lifecycle and get rendered trees in one pass
        rendered_trees = await run_nested_component_lifecycle(self, self.meta)

        # Clean up components that were removed from the DOM
        self.components.prune_stale_components()

        # Include rendered component trees in response
        if rendered_trees:
            rendered["c"] = {str(cid): tree for cid, tree in rendered_trees.items()}

        return rendered

    async def subscribe(self, topic: str):
        await self.pub_sub.subscribe_topic_async(topic, self._topic_callback_internal)

    async def broadcast(self, topic: str, message: Any):
        await self.pub_sub.send_all_on_topic_async(topic, message)

    async def _topic_callback_internal(self, topic, message):
        await self.send_info(InfoEvent(topic, message))

    def schedule_info(self, event, seconds):
        id = f"{self.topic}:{event}"
        self.scheduler.add_job(
            self.send_info, args=[event], id=id, trigger="interval", seconds=seconds
        )
        self.scheduled_jobs.add(id)

    def schedule_info_once(self, event, seconds=None):
        job_id = f"{self.topic}:once:{uuid.uuid4().hex}"
        self.scheduler.add_job(
            self._send_info_once,
            args=[job_id, event],
            id=job_id,
            trigger="date",
            run_date=datetime.datetime.now() + datetime.timedelta(seconds=seconds or 0),
            misfire_grace_time=None,
        )
        self.scheduled_jobs.add(job_id)

    def diff(self, render: dict[str, Any]) -> dict[str, Any]:
        if self.prev_rendered:
            diff = calc_diff(self.prev_rendered, render)
        else:
            diff = render

        self.prev_rendered = render
        return diff

    async def _send_info_once(self, job_id: str, event: InfoEvent):
        """Wrapper for one-time info sends that cleans up the job ID after execution"""
        await self.send_info(event)
        self.scheduled_jobs.discard(job_id)

    async def send_info(self, event: InfoEvent):
        await self.liveview.handle_info(event, self)

        rendered = await self.render_with_components()
        resp = [None, None, self.topic, "diff", self.diff(rendered)]

        try:
            await self.websocket.send_text(json.dumps(resp))
        except Exception:
            for id in list(self.scheduled_jobs):
                logger.debug("Removing scheduled job %s", id)
                try:
                    self.scheduler.remove_job(id)
                except Exception:
                    logger.warning("Failed to remove scheduled job %s", id, exc_info=True)

    async def push_patch(self, path: str, params: Optional[dict[str, Any]] = None):
        if params is None:
            params = {}

        # or "replace"
        kind = "push"

        to = path
        if params:
            to = to + "?" + urlencode(params)

        message = [
            None,
            None,
            self.topic,
            "live_patch",  # or "live_redirect"
            {
                "kind": kind,
                "to": to,
            },
        ]

        # Parse string to ParseResult for type consistency
        parsed_url = urlparse(to)

        # Extract path params from route pattern
        path_params: dict[str, Any] = {}
        if self.routes:
            with suppress(ValueError):
                _, path_params = self.routes.get(parsed_url.path)

        # Convert explicit params to list format (matching query param format)
        # and merge with path params (path params take precedence)
        params_for_handler = {k: _as_list(v) for k, v in params.items()}
        merged_params = {**params_for_handler, **path_params}

        await call_handle_params(self.liveview, parsed_url, merged_params, self)
        try:
            await self.websocket.send_text(json.dumps(message))
        except Exception:
            logger.warning("Error sending patch message", exc_info=True)

    async def push_navigate(self, path: str, params: Optional[dict[str, Any]] = None):
        """Navigate to a different LiveView without full page reload"""
        if params is None:
            params = {}
        await self._navigate(path, params, kind="push")

    async def replace_navigate(self, path: str, params: Optional[dict[str, Any]] = None):
        """Navigate to a different LiveView, replacing current history entry"""
        if params is None:
            params = {}
        await self._navigate(path, params, kind="replace")

    async def _navigate(self, path: str, params: dict[str, Any], kind: str):
        """Internal navigation helper"""
        to = path
        if params:
            to = to + "?" + urlencode(params)

        message = [
            None,
            None,
            self.topic,
            "live_redirect",
            {
                "kind": kind,
                "to": to,
            },
        ]

        try:
            await self.websocket.send_text(json.dumps(message))
        except Exception:
            logger.warning("Error sending navigation message", exc_info=True)

    async def redirect(self, path: str, params: Optional[dict[str, Any]] = None):
        """Redirect to a new location with full page reload"""
        if params is None:
            params = {}
        to = path
        if params:
            to = to + "?" + urlencode(params)

        message = [
            None,
            None,
            self.topic,
            "redirect",
            {"to": to},
        ]

        try:
            await self.websocket.send_text(json.dumps(message))
        except Exception:
            logger.warning("Error sending redirect message", exc_info=True)

    async def push_event(self, event: str, value: dict[str, Any]):
        self.pending_events.append((event, value))

    def allow_upload(
        self,
        upload_name: str,
        constraints: UploadConstraints,
        auto_upload: bool = False,
        progress: Optional[Callable] = None,
        external: Optional[Callable] = None,
        entry_complete: Optional[Callable] = None,
    ) -> UploadConfig:
        return self.upload_manager.allow_upload(
            upload_name, constraints, auto_upload, progress, external, entry_complete
        )

    async def close(self):
        self.connected = False
        for id in list(self.scheduled_jobs):
            with suppress(JobLookupError):
                self.scheduler.remove_job(id)
        await self.pub_sub.unsubscribe_all_async()

        with suppress(Exception):
            self.upload_manager.close()

        with suppress(Exception):
            self.components.clear()

        with suppress(Exception):
            await self.liveview.disconnect(self)


LiveViewSocket: TypeAlias = Union[ConnectedLiveViewSocket[T], UnconnectedSocket[T]]
