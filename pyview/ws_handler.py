import json
import logging
from contextlib import suppress
from typing import Optional
from urllib.parse import parse_qs, urlparse

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from starlette.websockets import WebSocket, WebSocketDisconnect

from pyview.auth import AuthProviderFactory
from pyview.binding import call_handle_event, call_handle_params
from pyview.csrf import validate_csrf_token
from pyview.instrumentation import InstrumentationProvider
from pyview.live_routes import LiveViewLookup
from pyview.live_socket import ConnectedLiveViewSocket, LiveViewSocket
from pyview.phx_message import parse_message
from pyview.session import deserialize_session

logger = logging.getLogger(__name__)

# Must match phoenix_live_view version in pyview/assets/package.json
PHOENIX_LIVEVIEW_VERSION = "0.20.17"


class AuthException(Exception):
    pass


class LiveSocketMetrics:
    """Container for LiveSocket instrumentation metrics."""

    def __init__(self, instrumentation: InstrumentationProvider):
        self.active_connections = instrumentation.create_updown_counter(
            "pyview.websocket.active_connections", "Number of active WebSocket connections"
        )
        self.mounts = instrumentation.create_counter(
            "pyview.liveview.mounts", "Total number of LiveView mounts"
        )
        self.events_processed = instrumentation.create_counter(
            "pyview.events.processed", "Total number of events processed"
        )
        self.event_duration = instrumentation.create_histogram(
            "pyview.events.duration", "Event processing duration", unit="s"
        )
        self.message_size = instrumentation.create_histogram(
            "pyview.websocket.message_size", "WebSocket message size in bytes", unit="bytes"
        )
        self.render_duration = instrumentation.create_histogram(
            "pyview.render.duration", "Template render duration", unit="s"
        )


class LiveSocketHandler:
    def __init__(self, routes: LiveViewLookup, instrumentation: InstrumentationProvider):
        self.routes = routes
        self.instrumentation = instrumentation
        self.metrics = LiveSocketMetrics(instrumentation)
        self.manager = ConnectionManager()
        self.sessions = 0
        self.scheduler = AsyncIOScheduler()
        self._scheduler_started = False

    def start_scheduler(self):
        """Start the scheduler. Called during app startup in async context."""
        if not self._scheduler_started:
            self.scheduler.start()
            self._scheduler_started = True

    async def shutdown_scheduler(self):
        """Shutdown the scheduler. Called during app shutdown."""
        if self._scheduler_started:
            self.scheduler.shutdown(wait=False)
            self._scheduler_started = False

    async def check_auth(self, websocket: WebSocket, lv):
        if not await AuthProviderFactory.get(lv).has_required_auth(websocket):
            raise AuthException()

    async def handle(self, websocket: WebSocket):
        await self.manager.connect(websocket)

        # Track active connections
        self.metrics.active_connections.add(1)
        self.sessions += 1
        topic = None
        socket: Optional[LiveViewSocket] = None

        try:
            data = await websocket.receive_text()
            [joinRef, messageRef, topic, event, payload] = json.loads(data)
            if event == "phx_join":
                if not validate_csrf_token(payload["params"]["_csrf_token"], topic):
                    raise AuthException("Invalid CSRF token")

                self.myJoinId = topic

                url = urlparse(payload["url"])
                lv, path_params = self.routes.get(url.path)
                await self.check_auth(websocket, lv)
                socket = ConnectedLiveViewSocket(
                    websocket, topic, lv, self.scheduler, self.instrumentation, self.routes
                )

                session = {}
                if "session" in payload:
                    session = deserialize_session(payload["session"])

                # Track mount
                view_name = lv.__class__.__name__
                self.metrics.mounts.add(1, {"view": view_name})

                await lv.mount(socket, session)

                # Parse query parameters and merge with path parameters
                query_params = parse_qs(url.query)
                merged_params = {**query_params, **path_params}

                # Pass merged parameters to handle_params
                await call_handle_params(lv, url, merged_params, socket)

                rendered = await _render(socket)
                socket.prev_rendered = rendered

                resp = [
                    joinRef,
                    messageRef,
                    topic,
                    "phx_reply",
                    {
                        "response": {
                            "rendered": rendered,
                            "liveview_version": PHOENIX_LIVEVIEW_VERSION,
                        },
                        "status": "ok",
                    },
                ]

                await self.manager.send_personal_message(json.dumps(resp), websocket)
                await self.handle_connected(topic, socket)

        except WebSocketDisconnect:
            if socket:
                await socket.close()
            self.sessions -= 1
            self.metrics.active_connections.add(-1)
        except AuthException:
            await websocket.close()
            self.sessions -= 1
            self.metrics.active_connections.add(-1)
        except Exception:
            logger.exception("Unexpected error in WebSocket handler")
            self.sessions -= 1
            self.metrics.active_connections.add(-1)
            raise

    async def handle_connected(self, myJoinId, socket: ConnectedLiveViewSocket):
        while True:
            message = await socket.websocket.receive()
            [joinRef, messageRef, topic, event, payload] = parse_message(message)

            if event == "heartbeat":
                resp = [
                    None,
                    messageRef,
                    "phoenix",
                    "phx_reply",
                    {"response": {}, "status": "ok"},
                ]
                await self.manager.send_personal_message(json.dumps(resp), socket.websocket)
                continue

            if event == "event":
                value = payload["value"]

                if payload["type"] == "form":
                    value = parse_qs(value)
                    socket.upload_manager.maybe_process_uploads(value, payload)

                # Track event metrics
                event_name = payload["event"]
                view_name = socket.liveview.__class__.__name__

                # Check if event is targeted at a component (via phx-target={cid})
                target_cid = payload.get("cid")

                self.metrics.events_processed.add(1, {"event": event_name, "view": view_name})

                # Time event processing
                with self.instrumentation.time_histogram(
                    "pyview.events.duration", {"event": event_name, "view": view_name}
                ):
                    if target_cid is not None:
                        # Validate CID type - must be an integer
                        if not isinstance(target_cid, int):
                            logger.warning(
                                f"Invalid cid type for event '{event_name}': {type(target_cid).__name__}"
                            )
                        else:
                            # Route event to component
                            await socket.components.handle_event(target_cid, event_name, value)
                    else:
                        # Route event to LiveView (default behavior)
                        await call_handle_event(socket.liveview, event_name, value, socket)

                # Time rendering
                with self.instrumentation.time_histogram(
                    "pyview.render.duration", {"view": view_name}
                ):
                    rendered = await _render(socket)

                hook_events = {} if not socket.pending_events else {"e": socket.pending_events}

                diff = socket.diff(rendered)

                socket.pending_events = []

                resp = [
                    joinRef,
                    messageRef,
                    topic,
                    "phx_reply",
                    {"response": {"diff": diff | hook_events}, "status": "ok"},
                ]
                resp_json = json.dumps(resp)
                self.metrics.message_size.record(len(resp_json))
                await self.manager.send_personal_message(resp_json, socket.websocket)
                continue

            if event == "live_patch":
                lv = socket.liveview
                url = urlparse(payload["url"])

                # Extract and merge parameters
                query_params = parse_qs(url.query)
                path_params = {}

                # We need to get path params for the new URL
                with suppress(ValueError):
                    # TODO: I don't think this is actually going to work...
                    _, path_params = self.routes.get(url.path)

                merged_params = {**query_params, **path_params}

                await call_handle_params(lv, url, merged_params, socket)
                rendered = await _render(socket)
                diff = socket.diff(rendered)

                resp = [
                    joinRef,
                    messageRef,
                    topic,
                    "phx_reply",
                    {"response": {"diff": diff}, "status": "ok"},
                ]
                await self.manager.send_personal_message(json.dumps(resp), socket.websocket)
                continue

            if event == "allow_upload":
                allow_upload_response = await socket.upload_manager.process_allow_upload(
                    payload, socket.context
                )

                rendered = await _render(socket)
                diff = socket.diff(rendered)

                resp = [
                    joinRef,
                    messageRef,
                    topic,
                    "phx_reply",
                    {
                        "response": {"diff": rendered} | allow_upload_response,
                        "status": "ok",
                    },
                ]

                await self.manager.send_personal_message(json.dumps(resp), socket.websocket)
                continue

            # file upload or navigation
            if event == "phx_join":
                # Check if this is a file upload join (topic starts with "lvu:")
                if topic.startswith("lvu:"):
                    # This is a file upload join
                    socket.upload_manager.add_upload(joinRef, payload)

                    resp = [
                        joinRef,
                        messageRef,
                        topic,
                        "phx_reply",
                        {"response": {}, "status": "ok"},
                    ]

                    await self.manager.send_personal_message(json.dumps(resp), socket.websocket)
                else:
                    # This is a navigation join (topic starts with "lv:")
                    # Navigation payload has 'redirect' field instead of 'url'
                    url_str_raw = payload.get("redirect") or payload.get("url")
                    url_str: str = (
                        url_str_raw.decode("utf-8")
                        if isinstance(url_str_raw, bytes)
                        else str(url_str_raw)
                    )
                    url = urlparse(url_str)
                    lv, path_params = self.routes.get(url.path)
                    await self.check_auth(socket.websocket, lv)

                    # Create new socket for new LiveView
                    socket = ConnectedLiveViewSocket(
                        socket.websocket,
                        topic,
                        lv,
                        self.scheduler,
                        self.instrumentation,
                        self.routes,
                    )

                    session = {}
                    if "session" in payload:
                        session = deserialize_session(payload["session"])

                    await lv.mount(socket, session)

                    # Parse query parameters and merge with path parameters
                    query_params = parse_qs(url.query)
                    merged_params = {**query_params, **path_params}

                    await call_handle_params(lv, url, merged_params, socket)

                    rendered = await _render(socket)
                    socket.prev_rendered = rendered

                    resp = [
                        joinRef,
                        messageRef,
                        topic,
                        "phx_reply",
                        {
                            "response": {
                                "rendered": rendered,
                                "liveview_version": PHOENIX_LIVEVIEW_VERSION,
                            },
                            "status": "ok",
                        },
                    ]

                    await self.manager.send_personal_message(json.dumps(resp), socket.websocket)

            if event == "chunk":
                socket.upload_manager.add_chunk(joinRef, payload)  # type: ignore

                resp = [
                    joinRef,
                    messageRef,
                    topic,
                    "phx_reply",
                    {"response": {}, "status": "ok"},
                ]

                if socket.upload_manager.no_progress(joinRef):
                    await self.manager.send_personal_message(
                        json.dumps(
                            [
                                joinRef,
                                None,
                                myJoinId,
                                "phx_reply",
                                {"response": {"diff": {}}, "status": "ok"},
                            ]
                        ),
                        socket.websocket,
                    )

                await self.manager.send_personal_message(json.dumps(resp), socket.websocket)

            if event == "progress":
                # Trigger progress callback BEFORE updating progress (which may consume the entry)
                await socket.upload_manager.trigger_progress_callback_if_exists(payload, socket)

                await socket.upload_manager.update_progress(joinRef, payload, socket)

                rendered = await _render(socket)
                diff = socket.diff(rendered)

                resp = [
                    joinRef,
                    messageRef,
                    topic,
                    "phx_reply",
                    {"response": {"diff": diff}, "status": "ok"},
                ]

                await self.manager.send_personal_message(json.dumps(resp), socket.websocket)

            if event == "phx_leave":
                # Handle LiveView navigation - clean up current LiveView
                await socket.close()

                resp = [
                    joinRef,
                    messageRef,
                    topic,
                    "phx_reply",
                    {"response": {}, "status": "ok"},
                ]
                await self.manager.send_personal_message(json.dumps(resp), socket.websocket)
                # Continue to wait for next phx_join
                continue


async def _render(socket: ConnectedLiveViewSocket):
    rendered = await socket.render_with_components()

    if socket.live_title:
        rendered["t"] = socket.live_title
        socket.live_title = None

    return rendered


class ConnectionManager:
    def __init__(self):
        pass

    async def connect(self, websocket: WebSocket):
        await websocket.accept()

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)
