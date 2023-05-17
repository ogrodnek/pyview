from __future__ import annotations
from fastapi import WebSocket
import json
from typing import Any, TypeVar, Generic, TYPE_CHECKING, Optional
from urllib.parse import urlencode
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pyview.vendor.flet.pubsub import PubSubHub, PubSub
from pyview.events import InfoEvent
import datetime


if TYPE_CHECKING:
    from .live_view import LiveView

scheduler = AsyncIOScheduler()
scheduler.start()

pub_sub_hub = PubSubHub()

T = TypeVar("T")


class UnconnectedSocket(Generic[T]):
    context: T
    connected: bool = False
    live_title: Optional[str] = None


class LiveViewSocket(Generic[T]):
    context: T
    live_title: Optional[str] = None

    def __init__(self, websocket: WebSocket, topic: str, liveview: LiveView):
        self.websocket = websocket
        self.topic = topic
        self.liveview = liveview
        self.scheduled_jobs = []
        self.connected = True
        self.pub_sub = PubSub(pub_sub_hub, topic)

    async def subscribe(self, topic: str):
        await self.pub_sub.subscribe_topic_async(topic, self._topic_callback_internal)

    async def broadcast(self, topic: str, message: Any):
        await self.pub_sub.send_all_on_topic_async(topic, message)

    async def _topic_callback_internal(self, topic, message):
        await self.send_info(InfoEvent(topic, message))

    def schedule_info(self, event, seconds):
        id = f"{self.topic}:{event}"
        scheduler.add_job(self.send_info, args=[event], id=id, trigger="interval", seconds=seconds)
        self.scheduled_jobs.append(id)

    def schedule_info_once(self, event):
        scheduler.add_job(
            self.send_info, args=[event], trigger="date", run_date=datetime.datetime.now(), misfire_grace_time=None
        )

    def diff(self, render: dict[str, Any]) -> dict[str, Any]:
        # TODO: not a real diff
        del render["s"]
        return render

    async def send_info(self, event: InfoEvent):
        await self.liveview.handle_info(event, self)
        r = await self.liveview.render(self.context)
        resp = [None, None, self.topic, "diff", self.diff(r.tree())]

        try:
            await self.websocket.send_text(json.dumps(resp))
        except Exception as e:
            for id in self.scheduled_jobs:
                print("Removing job", id)
                scheduler.remove_job(id)

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
        except Exception as e:
            print("Error sending message", e)

    async def close(self):
        self.connected = False
        for id in self.scheduled_jobs:
            scheduler.remove_job(id)
        await self.pub_sub.unsubscribe_all_async()
