"""End-to-end tests for the LiveSocketHandler message loop.

These drive the real handler through an in-memory websocket (see
tests/ws_mock.py), scripting inbound Phoenix frames and asserting on what gets
sent back. No server, no real socket.

They're deliberately written against observable wire behavior rather than the
handler's internals, so they keep working as the handler is refactored.
"""

import json
import struct
from typing import Any, Optional

import pytest
from starlette.authentication import AuthCredentials
from starlette.websockets import WebSocketDisconnect

from pyview.auth import requires
from pyview.csrf import generate_csrf_token
from pyview.instrumentation import NoOpInstrumentation
from pyview.live_routes import LiveViewLookup
from pyview.live_socket import ConnectedLiveViewSocket
from pyview.live_view import LiveView
from pyview.uploads import UploadConstraints
from pyview.ws_handler import LiveSocketHandler

from .ws_mock import MemoryWebSocket

TOPIC = "lv:test"


class SimpleRendered:
    """Minimal RenderedContent: a static/dynamic tree plus its text form."""

    def __init__(self, tree: dict[str, Any], html: str = ""):
        self._tree = tree
        self._html = html

    def tree(self) -> dict[str, Any]:
        return dict(self._tree)

    def text(self, socket=None) -> str:
        return self._html


class CounterView(LiveView[dict]):
    """mount sets count=0; the 'increment' event adds one."""

    async def mount(self, socket, session):
        socket.context = {"count": 0, "session": dict(session)}

    async def handle_event(self, event, payload, socket):
        if event == "increment":
            socket.context["count"] += 1
        elif event == "add":
            socket.context["count"] += int(payload["amount"][0])
        elif event == "boom":
            raise RuntimeError("handler exploded")

    async def render(self, assigns, meta):
        count = assigns["count"]
        return SimpleRendered({"s": ["<div>", "</div>"], "0": str(count)}, f"<div>{count}</div>")


class ParamView(LiveView[dict]):
    """Records the params it was last handed, so they can be asserted on."""

    async def mount(self, socket, session):
        socket.context = {"page": "unset"}

    async def handle_params(self, url, params, socket):
        page = params.get("page", "unset")
        socket.context["page"] = page[0] if isinstance(page, list) else page

    async def render(self, assigns, meta):
        page = assigns["page"]
        return SimpleRendered({"s": ["<p>", "</p>"], "0": str(page)}, f"<p>{page}</p>")


class SessionView(LiveView[dict]):
    async def mount(self, socket, session):
        socket.context = {"user": session.get("user", "anonymous")}

    async def render(self, assigns, meta):
        user = assigns["user"]
        return SimpleRendered({"s": ["<p>", "</p>"], "0": user}, f"<p>{user}</p>")


@requires("authenticated")
class SecretView(LiveView[dict]):
    async def mount(self, socket, session):
        socket.context = {}

    async def render(self, assigns, meta):
        return SimpleRendered({"s": ["<p>secret</p>"]}, "<p>secret</p>")


UPLOAD_REF = "avatar-config-ref"
UPLOAD_ENTRY = {"ref": "0", "name": "hello.txt", "size": 5, "type": "text/plain"}


def upload_view(
    progress_seen: list[int], saved: Optional[list[tuple[str, bytes]]] = None
) -> type[LiveView]:
    """A LiveView that allows one small upload, records progress callbacks, and
    consumes the uploaded files on a 'save' event."""

    async def on_progress(entry, socket):
        progress_seen.append(entry.progress)

    class UploadView(CounterView):
        async def mount(self, socket, session):
            await super().mount(socket, session)
            config = socket.allow_upload(
                "avatar", UploadConstraints(max_file_size=1024, chunk_size=8), progress=on_progress
            )
            config.ref = UPLOAD_REF
            socket.context["config"] = config

        async def handle_event(self, event, payload, socket):
            if event == "save" and saved is not None:
                with socket.context["config"].consume_uploads() as uploads:
                    for upload in uploads:
                        with open(upload.file.name, "rb") as f:
                            saved.append((upload.entry.name, f.read()))

    return UploadView


def binary_chunk(join_ref: str, msg_ref: str, data: bytes, topic: str = "lvu:0") -> bytes:
    """Frame a binary upload chunk the way the client does."""
    event = "chunk"
    header = (
        struct.pack("BBBBB", 0, len(join_ref), len(msg_ref), len(topic), len(event))
        + f"{join_ref}{msg_ref}{topic}{event}".encode()
    )
    return header + data


@pytest.fixture
def routes() -> LiveViewLookup:
    lookup = LiveViewLookup()
    lookup.add("/demo", CounterView)
    lookup.add("/params", ParamView)
    lookup.add("/items/{page}", ParamView)
    lookup.add("/session", SessionView)
    lookup.add("/secret", SecretView)
    return lookup


@pytest.fixture
def handler(routes: LiveViewLookup) -> LiveSocketHandler:
    return LiveSocketHandler(routes, NoOpInstrumentation())


@pytest.fixture
def closes(monkeypatch) -> list[int]:
    """Records how many frames had been sent each time a socket was closed.

    Lets a test pin down *when* a socket was torn down -- during the message
    loop, or only at teardown once the connection dropped.
    """
    recorded: list[int] = []
    original_close = ConnectedLiveViewSocket.close

    async def spy(self):
        if self.connected:
            recorded.append(len(self.websocket.sent))
        await original_close(self)

    monkeypatch.setattr(ConnectedLiveViewSocket, "close", spy)
    return recorded


@pytest.fixture
def sockets(monkeypatch) -> list[ConnectedLiveViewSocket]:
    """Records every ConnectedLiveViewSocket the handler creates, in order."""
    created: list[ConnectedLiveViewSocket] = []
    original_init = ConnectedLiveViewSocket.__init__

    def record(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        created.append(self)

    monkeypatch.setattr(ConnectedLiveViewSocket, "__init__", record)
    return created


def joined(
    topic: str = TOPIC,
    url: str = "http://testserver/demo",
    auth: Any = None,
    **kwargs,
) -> MemoryWebSocket:
    """A websocket already scripted with an initial join."""
    return MemoryWebSocket(auth=auth).push_join(topic=topic, url=url, **kwargs)


def rendered_text(response: dict[str, Any], key: str = "0") -> Optional[str]:
    return response["rendered"].get(key)


class TestJoin:
    async def test_join_replies_with_rendered_view(self, handler):
        ws = joined().push_disconnect()

        await handler.handle(ws)

        assert ws.accepted
        reply = ws.reply_at(0)
        assert reply["status"] == "ok"
        assert rendered_text(reply["response"]) == "0"
        assert reply["response"]["liveview_version"] == "0.20.17"

    async def test_join_echoes_refs_and_topic(self, handler):
        ws = joined().push_disconnect()

        await handler.handle(ws)

        join_ref, msg_ref, topic, event, _ = ws.frame_at(0)
        assert (join_ref, msg_ref, topic, event) == ("1", "1", TOPIC, "phx_reply")

    async def test_invalid_csrf_closes_without_replying(self, handler):
        ws = joined(csrf_token="not-a-real-token").push_disconnect()

        await handler.handle(ws)

        assert ws.closed
        assert ws.sent == []

    async def test_csrf_token_is_bound_to_the_topic(self, handler):
        """A token minted for one topic must not join another."""
        ws = joined(topic="lv:other", csrf_token=generate_csrf_token(TOPIC)).push_disconnect()

        await handler.handle(ws)

        assert ws.closed
        assert ws.sent == []

    async def test_missing_url_closes_connection(self, handler):
        ws = MemoryWebSocket()
        payload = {"params": {"_csrf_token": generate_csrf_token(TOPIC)}}
        ws.push_text(json.dumps(["1", "1", TOPIC, "phx_join", payload]))

        await handler.handle(ws)

        assert ws.closed
        assert ws.sent == []

    async def test_unknown_route_raises(self, handler):
        ws = joined(url="http://testserver/nope").push_disconnect()

        with pytest.raises(ValueError, match="No LiveView found"):
            await handler.handle(ws)

    async def test_session_is_passed_to_mount(self, handler):
        ws = joined(url="http://testserver/session", session={"user": "larry"}).push_disconnect()

        await handler.handle(ws)

        assert rendered_text(ws.response_at(0)) == "larry"

    async def test_query_params_reach_handle_params(self, handler):
        ws = joined(url="http://testserver/params?page=7").push_disconnect()

        await handler.handle(ws)

        assert rendered_text(ws.response_at(0)) == "7"

    async def test_path_params_win_over_query_params(self, handler):
        ws = joined(url="http://testserver/items/42?page=9").push_disconnect()

        await handler.handle(ws)

        assert rendered_text(ws.response_at(0)) == "42"

    async def test_join_via_redirect_field(self, handler):
        """The client sends 'redirect' instead of 'url' when navigating."""
        ws = joined(redirect=True).push_disconnect()

        await handler.handle(ws)

        assert ws.reply_at(0)["status"] == "ok"

    async def test_first_frame_that_is_not_a_join_is_ignored(self, handler):
        ws = MemoryWebSocket().push_text('[null, "1", "phoenix", "heartbeat", {}]')

        await handler.handle(ws)

        assert ws.sent == []
        assert not ws.closed


class TestAuth:
    async def test_unauthorized_join_closes_connection(self, handler):
        ws = joined(url="http://testserver/secret", auth=AuthCredentials([]))

        await handler.handle(ws)

        assert ws.closed
        assert ws.sent == []

    async def test_authorized_join_succeeds(self, handler):
        ws = joined(
            url="http://testserver/secret", auth=AuthCredentials(["authenticated"])
        ).push_disconnect()

        await handler.handle(ws)

        assert ws.reply_at(0)["status"] == "ok"


class TestHeartbeat:
    async def test_heartbeat_replies_on_the_phoenix_topic(self, handler):
        ws = joined().push_phx(None, "5", "phoenix", "heartbeat", {}).push_disconnect()

        await handler.handle(ws)

        join_ref, msg_ref, topic, _, payload = ws.frame_at(1)
        assert (join_ref, msg_ref, topic) == (None, "5", "phoenix")
        assert payload == {"response": {}, "status": "ok"}


class TestEvents:
    async def test_event_replies_with_a_diff(self, handler):
        ws = joined().push_event("increment").push_disconnect()

        await handler.handle(ws)

        assert ws.response_at(1)["diff"] == {"0": "1"}

    async def test_events_accumulate_state(self, handler):
        ws = joined()
        for i in range(3):
            ws.push_event("increment", msg_ref=str(i + 2))
        ws.push_disconnect()

        await handler.handle(ws)

        assert len(ws.sent) == 4
        assert ws.response_at(3)["diff"] == {"0": "3"}

    async def test_form_event_value_is_parsed_as_a_query_string(self, handler):
        ws = joined().push_event("add", value="amount=5", type="form").push_disconnect()

        await handler.handle(ws)

        assert ws.response_at(1)["diff"] == {"0": "5"}

    async def test_clear_flash_event_clears_the_flash(self, handler, sockets):
        class FlashView(CounterView):
            async def mount(self, socket, session):
                await super().mount(socket, session)
                socket.put_flash("info", "saved")
                socket.put_flash("error", "nope")

            async def handle_event(self, event, payload, socket):
                raise AssertionError("lv:clear-flash must not reach handle_event")

        handler.routes.add("/flash", FlashView)
        ws = joined(topic="lv:flash", url="http://testserver/flash")
        ws.push_event("lv:clear-flash", value={"key": "info"}, topic="lv:flash").push_disconnect()

        await handler.handle(ws)

        assert ws.reply_at(1)["status"] == "ok"
        assert sockets[0].flash == {"error": "nope"}

    async def test_pending_events_are_attached_to_the_reply(self, handler):
        class PushingView(CounterView):
            async def handle_event(self, event, payload, socket):
                await socket.push_event("ping", {"n": 1})

        handler.routes.add("/pushing", PushingView)
        ws = joined(topic="lv:push", url="http://testserver/pushing")
        ws.push_event("anything", topic="lv:push").push_disconnect()

        await handler.handle(ws)

        assert ws.response_at(1)["diff"]["e"] == [["ping", {"n": 1}]]

    async def test_event_error_propagates_and_cleans_up(self, handler):
        ws = joined().push_event("boom").push_disconnect()

        with pytest.raises(RuntimeError, match="handler exploded"):
            await handler.handle(ws)

        assert handler.sessions == 0

    async def test_event_for_a_component_with_a_non_integer_cid_is_ignored(self, handler, caplog):
        ws = joined().push_event("increment", cid="not-an-int").push_disconnect()

        await handler.handle(ws)

        assert "Invalid cid type" in caplog.text
        # the view is still rendered and replied to, just not the component
        assert ws.response_at(1)["diff"] == {}

    async def test_live_title_is_sent_with_the_diff(self, handler):
        class TitleView(CounterView):
            async def handle_event(self, event, payload, socket):
                socket.live_title = "new title"

        handler.routes.add("/title", TitleView)
        ws = joined(topic="lv:title", url="http://testserver/title")
        ws.push_event("anything", topic="lv:title").push_disconnect()

        await handler.handle(ws)

        assert ws.response_at(1)["diff"]["t"] == "new title"

    async def test_unknown_frame_is_ignored(self, handler):
        ws = joined().push_phx("1", "2", TOPIC, "no_such_event", {}).push_disconnect()

        await handler.handle(ws)

        assert len(ws.sent) == 1


class TestLivePatch:
    async def test_patch_reruns_handle_params_and_replies_with_a_diff(self, handler):
        ws = joined(topic="lv:params", url="http://testserver/params?page=1")
        ws.push_phx("1", "2", "lv:params", "live_patch", {"url": "http://testserver/params?page=2"})
        ws.push_disconnect()

        await handler.handle(ws)

        assert ws.response_at(1)["diff"] == {"0": "2"}


class TestComponentCids:
    async def test_cids_will_destroy_replies_ok(self, handler):
        ws = joined().push_phx("1", "2", TOPIC, "cids_will_destroy", {"cids": [1, 2]})
        ws.push_disconnect()

        await handler.handle(ws)

        assert ws.reply_at(1) == {"response": {}, "status": "ok"}

    async def test_cids_destroyed_echoes_the_cids_back(self, handler):
        ws = joined().push_phx("1", "2", TOPIC, "cids_destroyed", {"cids": [3, 4]})
        ws.push_disconnect()

        await handler.handle(ws)

        assert ws.response_at(1)["cids"] == [3, 4]


class TestLeaveAndNavigation:
    async def test_leave_replies_ok(self, handler):
        ws = joined().push_phx("1", "2", TOPIC, "phx_leave", {}).push_disconnect()

        await handler.handle(ws)

        assert ws.reply_at(1) == {"response": {}, "status": "ok"}

    async def test_leave_tears_down_the_live_view(self, handler, closes):
        ws = joined().push_phx("1", "2", TOPIC, "phx_leave", {}).push_disconnect()

        await handler.handle(ws)

        # closed with only the join reply sent, i.e. while handling the leave --
        # not later, when the connection dropped
        assert closes == [1]

    async def test_loop_survives_a_leave(self, handler):
        """After leaving, the connection stays open waiting for the next join."""
        ws = joined().push_phx("1", "2", TOPIC, "phx_leave", {})
        ws.push_phx(None, "3", "phoenix", "heartbeat", {}).push_disconnect()

        await handler.handle(ws)

        assert ws.reply_at(2) == {"response": {}, "status": "ok"}

    async def test_navigation_rejoins_on_the_same_topic(self, handler):
        """What the client actually does on live_redirect: leave, then rejoin
        the same topic with the new url."""
        ws = joined().push_phx("1", "2", TOPIC, "phx_leave", {})
        ws.push_join(
            topic=TOPIC,
            url="http://testserver/params?page=3",
            join_ref="2",
            msg_ref="3",
            redirect=True,
            initial=False,
        )
        ws.push_disconnect()

        await handler.handle(ws)

        assert rendered_text(ws.response_at(2)) == "3"

    async def test_navigation_join_passes_its_session_to_mount(self, handler):
        ws = joined().push_phx("1", "2", TOPIC, "phx_leave", {})
        ws.push_join(
            topic=TOPIC,
            url="http://testserver/session",
            join_ref="2",
            msg_ref="3",
            session={"user": "larry"},
            redirect=True,
            initial=False,
        )
        ws.push_disconnect()

        await handler.handle(ws)

        assert rendered_text(ws.response_at(2)) == "larry"

    async def test_navigation_join_serves_events_for_the_new_view(self, handler):
        ws = joined(url="http://testserver/params").push_phx("1", "2", TOPIC, "phx_leave", {})
        ws.push_join(
            topic=TOPIC,
            url="http://testserver/demo",
            join_ref="2",
            msg_ref="3",
            redirect=True,
            initial=False,
        )
        ws.push_event("increment", msg_ref="4").push_disconnect()

        await handler.handle(ws)

        assert ws.response_at(3)["diff"] == {"0": "1"}


class TestUploadChannel:
    """Upload channels ride the same socket under an 'lvu:' topic."""

    async def test_upload_join_for_an_unconfigured_upload_replies_ok(self, handler):
        ws = joined()
        ws.push_phx("2", "2", "lvu:0", "phx_join", {"token": {"path": "unconfigured"}})
        ws.push_disconnect()

        await handler.handle(ws)

        assert ws.reply_at(1) == {"response": {}, "status": "ok"}

    async def test_upload_leave_replies_ok(self, handler):
        ws = joined().push_phx("2", "2", "lvu:0", "phx_leave", {}).push_disconnect()

        await handler.handle(ws)

        assert ws.reply_at(1) == {"response": {}, "status": "ok"}

    async def test_first_empty_chunk_nudges_the_client_with_an_empty_diff(self, handler):
        """Before any bytes land, the handler also sends a diff frame on the
        LiveView's own topic so the client doesn't stall."""
        handler.routes.add("/upload", upload_view([]))

        ws = joined(topic="lv:up", url="http://testserver/upload")
        ws.push_event(
            "validate",
            value="_target=avatar",
            type="form",
            topic="lv:up",
            uploads={UPLOAD_REF: [UPLOAD_ENTRY]},
        )
        ws.push_phx("2", "3", "lvu:0", "phx_join", {"token": {**UPLOAD_ENTRY, "path": "avatar"}})
        ws.push_message({"type": "websocket.receive", "bytes": binary_chunk("2", "4", b"")})
        ws.push_disconnect()

        await handler.handle(ws)

        nudge = ws.frame_at(3)
        assert nudge[2] == "lv:up"
        assert nudge[4] == {"response": {"diff": {}}, "status": "ok"}
        assert ws.reply_at(4) == {"response": {}, "status": "ok"}

    async def test_upload_round_trip(self, handler):
        """validate -> allow_upload -> lvu join -> chunk -> progress -> save."""
        progress_seen: list[int] = []
        saved: list[tuple[str, bytes]] = []
        handler.routes.add("/upload", upload_view(progress_seen, saved))

        ws = joined(topic="lv:up", url="http://testserver/upload")
        # the form's change event carries the proposed entries
        ws.push_event(
            "validate",
            value="_target=avatar",
            type="form",
            topic="lv:up",
            uploads={UPLOAD_REF: [UPLOAD_ENTRY]},
        )
        # the client asks whether it may upload them
        ws.push_phx(
            "1", "3", "lv:up", "allow_upload", {"ref": UPLOAD_REF, "entries": [UPLOAD_ENTRY]}
        )
        # ...then joins a channel per entry and streams the bytes
        ws.push_phx("2", "4", "lvu:0", "phx_join", {"token": {**UPLOAD_ENTRY, "path": "avatar"}})
        ws.push_message({"type": "websocket.receive", "bytes": binary_chunk("2", "5", b"hello")})
        ws.push_phx(
            "2", "6", "lv:up", "progress", {"ref": UPLOAD_REF, "entry_ref": "0", "progress": 100}
        )
        ws.push_event("save", topic="lv:up", msg_ref="7")
        ws.push_disconnect()

        await handler.handle(ws)

        allow = ws.response_at(2)
        assert allow["config"]["max_file_size"] == 1024
        assert list(allow["entries"]) == ["0"]
        assert ws.reply_at(3) == {"response": {}, "status": "ok"}  # lvu join
        assert ws.reply_at(4)["status"] == "ok"  # chunk
        assert ws.reply_at(5)["status"] == "ok"  # progress
        assert progress_seen == [100]
        assert saved == [("hello.txt", b"hello")]


class TestConnectionLifecycle:
    async def test_session_count_returns_to_zero(self, handler):
        ws = joined().push_disconnect()

        await handler.handle(ws)

        assert handler.sessions == 0

    async def test_disconnect_before_join_is_not_an_error(self, handler):
        ws = MemoryWebSocket()

        await handler.handle(ws)

        assert ws.accepted
        assert handler.sessions == 0

    async def test_socket_is_closed_on_disconnect(self, handler, sockets):
        await handler.handle(joined().push_disconnect())

        assert [type(s.liveview).__name__ for s in sockets] == ["CounterView"]
        assert not sockets[0].connected

    @pytest.mark.xfail(
        strict=True,
        reason="known gap: _handle_connected_loop rebinds `socket` in its own scope, so the "
        "socket created by a navigation join is never closed (scheduled jobs and pub/sub "
        "subscriptions leak). Remove this marker once per-connection state is hoisted.",
    )
    async def test_socket_from_a_navigation_join_is_closed(self, handler, sockets):
        ws = joined().push_phx("1", "2", TOPIC, "phx_leave", {})
        ws.push_join(
            topic=TOPIC,
            url="http://testserver/params",
            join_ref="2",
            msg_ref="3",
            redirect=True,
            initial=False,
        )
        ws.push_disconnect()

        await handler.handle(ws)

        assert [type(s.liveview).__name__ for s in sockets] == ["CounterView", "ParamView"]
        assert all(not s.connected for s in sockets)


class TestScheduler:
    async def test_start_and_shutdown_are_idempotent(self, handler):
        """apscheduler raises on a double start/shutdown; the handler guards it."""
        handler.start_scheduler()
        handler.start_scheduler()
        assert handler.scheduler.running

        await handler.shutdown_scheduler()
        await handler.shutdown_scheduler()


class TestMemoryWebSocket:
    async def test_frames_are_consumed_in_order(self):
        ws = MemoryWebSocket().push_text("first").push_phx("1", "1", "t", "e", {})

        assert await ws.receive_text() == "first"
        assert await ws.receive() == {
            "type": "websocket.receive",
            "text": '["1", "1", "t", "e", {}]',
        }

    async def test_empty_inbox_disconnects(self):
        ws = MemoryWebSocket()
        with pytest.raises(WebSocketDisconnect):
            await ws.receive_text()
        with pytest.raises(WebSocketDisconnect):
            await ws.receive()

    async def test_sent_frames_are_recorded_and_parsed(self):
        ws = MemoryWebSocket()
        await ws.send_text('["1", "1", "t", "phx_reply", {"response": {}, "status": "ok"}]')

        assert ws.frame_at(0)[3] == "phx_reply"
        assert ws.reply_at(0)["status"] == "ok"
        assert ws.response_at(0) == {}
