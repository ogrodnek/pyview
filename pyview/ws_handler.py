from typing import Optional
from fastapi import WebSocket, WebSocketDisconnect
import json
from urllib.parse import urlparse, parse_qs
from pyview.live_socket import LiveViewSocket
from pyview.live_routes import LiveViewLookup
from pyview.csrf import validate_csrf_token


class LiveSocketHandler:
    def __init__(self, routes: LiveViewLookup):
        self.routes = routes
        self.manager = ConnectionManager()
        self.sessions = 0

    async def handle(self, websocket: WebSocket):
        await self.manager.connect(websocket)

        self.sessions += 1
        topic = None
        socket: Optional[LiveViewSocket] = None

        try:
            data = await websocket.receive_text()
            [joinRef, mesageRef, topic, event, payload] = json.loads(data)
            if event == "phx_join":
                url = urlparse(payload["url"])
                lv = self.routes.get(url.path)
                socket = LiveViewSocket(websocket, topic, lv)

                if not validate_csrf_token(payload["params"]["_csrf_token"], topic):
                    raise Exception("Invalid CSRF token")

                await lv.mount(socket)
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
            self.manager.disconnect(websocket)
            if socket:
                await socket.close()
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
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)
