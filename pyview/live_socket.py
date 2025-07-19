from __future__ import annotations
from starlette.websockets import WebSocket
import json
import logging
from typing import (
    Any,
    TypeVar,
    Generic,
    TYPE_CHECKING,
    Optional,
    Union,
    TypeAlias,
    TypeGuard,
)
from urllib.parse import urlencode
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.base import JobLookupError
from pyview.vendor.flet.pubsub import PubSubHub, PubSub
from pyview.events import InfoEvent
from pyview.uploads import UploadConstraints, UploadConfig, UploadManager
from pyview.meta import PyViewMeta
from pyview.template.render_diff import calc_diff
import datetime
from pyview.async_stream_runner import AsyncStreamRunner

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from .live_view import LiveView
    from .instrumentation import InstrumentationProvider


pub_sub_hub = PubSubHub()

T = TypeVar("T")


def is_connected(socket: LiveViewSocket[T]) -> TypeGuard["ConnectedLiveViewSocket[T]"]:
    return socket.connected


class UnconnectedSocket(Generic[T]):
    context: T
    live_title: Optional[str] = None
    connected: bool = False

    def allow_upload(
        self, upload_name: str, constraints: UploadConstraints
    ) -> UploadConfig:
        return UploadConfig(name=upload_name, constraints=constraints)


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
        instrumentation: "InstrumentationProvider",
    ):
        self.websocket = websocket
        self.topic = topic
        self.liveview = liveview
        self.instrumentation = instrumentation
        self.scheduled_jobs = []
        self.connected = True
        self.pub_sub = PubSub(pub_sub_hub, topic)
        self.pending_events = []
        self.upload_manager = UploadManager()
        self.stream_runner = AsyncStreamRunner(self)
        self.scheduler = scheduler

    @property
    def meta(self) -> PyViewMeta:
        return PyViewMeta()

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
        self.scheduled_jobs.append(id)

    def schedule_info_once(self, event, seconds=None):
        self.scheduler.add_job(
            self.send_info,
            args=[event],
            trigger="date",
            run_date=datetime.datetime.now() + datetime.timedelta(seconds=seconds or 0),
            misfire_grace_time=None,
        )

    def diff(self, render: dict[str, Any]) -> dict[str, Any]:
        if self.prev_rendered:
            diff = calc_diff(self.prev_rendered, render)
        else:
            diff = render

        self.prev_rendered = render
        return diff

    async def send_info(self, event: InfoEvent):
        await self.liveview.handle_info(event, self)
        r = await self.liveview.render(self.context, self.meta)
        resp = [None, None, self.topic, "diff", self.diff(r.tree())]

        try:
            await self.websocket.send_text(json.dumps(resp))
        except Exception:
            for id in self.scheduled_jobs:
                logger.debug("Removing scheduled job %s", id)
                try:
                    self.scheduler.remove_job(id)
                except Exception:
                    logger.warning(
                        "Failed to remove scheduled job %s", id, exc_info=True
                    )

    async def push_patch(self, path: str, params: dict[str, Any] = {}):
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

        # TODO another way to marshall this
        for k in params:
            params[k] = [params[k]]

        await self.liveview.handle_params(to, params, self)
        try:
            await self.websocket.send_text(json.dumps(message))
        except Exception:
            logger.warning("Error sending patch message", exc_info=True)

    async def push_navigate(self, path: str, params: dict[str, Any] = {}):
        """Navigate to a different LiveView without full page reload"""
        await self._navigate(path, params, kind="push")

    async def replace_navigate(self, path: str, params: dict[str, Any] = {}):
        """Navigate to a different LiveView, replacing current history entry"""
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

    async def push_event(self, event: str, value: dict[str, Any]):
        self.pending_events.append((event, value))

    def allow_upload(
        self, upload_name: str, constraints: UploadConstraints
    ) -> UploadConfig:
        return self.upload_manager.allow_upload(upload_name, constraints)

    async def close(self):
        self.connected = False
        for id in self.scheduled_jobs:
            try:
                self.scheduler.remove_job(id)
            except JobLookupError:
                pass
        await self.pub_sub.unsubscribe_all_async()

        try:
            self.upload_manager.close()
        except Exception:
            pass

        try:
            await self.liveview.disconnect(self)
        except Exception:
            pass


LiveViewSocket: TypeAlias = Union[ConnectedLiveViewSocket[T], UnconnectedSocket[T]]
