from typing import Optional
import json
from starlette.websockets import WebSocket, WebSocketDisconnect
from urllib.parse import urlparse, parse_qs
from pyview.live_socket import LiveViewSocket
from pyview.live_routes import LiveViewLookup
from pyview.csrf import validate_csrf_token
from pyview.session import deserialize_session
from pyview.auth import AuthProviderFactory


class AuthException(Exception):
    pass


class LiveSocketHandler:
    def __init__(self, routes: LiveViewLookup):
        self.routes = routes
        self.manager = ConnectionManager()
        self.sessions = 0

    async def check_auth(self, websocket: WebSocket, lv):
        if not await AuthProviderFactory.get(lv).has_required_auth(websocket):
            raise AuthException()

    async def handle(self, websocket: WebSocket):
        await self.manager.connect(websocket)

        self.sessions += 1
        topic = None
        socket: Optional[LiveViewSocket] = None

        try:
            data = await websocket.receive_text()
            [joinRef, mesageRef, topic, event, payload] = json.loads(data)
            if event == "phx_join":
                if not validate_csrf_token(payload["params"]["_csrf_token"], topic):
                    raise AuthException("Invalid CSRF token")

                url = urlparse(payload["url"])
                lv = self.routes.get(url.path)
                await self.check_auth(websocket, lv)
                socket = LiveViewSocket(websocket, topic, lv)

                session = {}
                if "session" in payload:
                    session = deserialize_session(payload["session"])

                await lv.mount(socket, session)
                await lv.handle_params(url, parse_qs(url.query), socket)

                rendered = await _render(socket)

                resp = [
                    joinRef,
                    mesageRef,
                    topic,
                    "phx_reply",
                    {"response": {"rendered": rendered}, "status": "ok"},
                ]

                await self.manager.send_personal_message(json.dumps(resp), websocket)
                await self.handle_connected(socket)

        except WebSocketDisconnect:
            if socket:
                await socket.close()
            self.sessions -= 1
        except AuthException:
            await websocket.close()
            self.sessions -= 1

    async def handle_connected(self, socket: LiveViewSocket):
        while True:
            data = await socket.websocket.receive_text()
            [joinRef, mesageRef, topic, event, payload] = json.loads(data)

            if event == "heartbeat":
                resp = [
                    None,
                    mesageRef,
                    "phoenix",
                    "phx_reply",
                    {"response": {}, "status": "ok"},
                ]
                await self.manager.send_personal_message(
                    json.dumps(resp), socket.websocket
                )
                continue

            if event == "event":
                value = payload["value"]
                if payload["type"] == "form":
                    value = parse_qs(value)

                await socket.liveview.handle_event(payload["event"], value, socket)
                rendered = await _render(socket)

                resp = [
                    joinRef,
                    mesageRef,
                    topic,
                    "phx_reply",
                    {"response": {"diff": rendered}, "status": "ok"},
                ]
                await self.manager.send_personal_message(
                    json.dumps(resp), socket.websocket
                )
                continue

            if event == "live_patch":
                lv = socket.liveview
                url = urlparse(payload["url"])

                await lv.handle_params(url, parse_qs(url.query), socket)
                rendered = await _render(socket)

                resp = [
                    joinRef,
                    mesageRef,
                    topic,
                    "phx_reply",
                    {"response": {"diff": rendered}, "status": "ok"},
                ]
                await self.manager.send_personal_message(
                    json.dumps(resp), socket.websocket
                )
                continue


async def _render(socket: LiveViewSocket):
    rendered = (await socket.liveview.render(socket.context)).tree()

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
