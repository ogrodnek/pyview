"""Upload channels for the test client: one per file, as the Phoenix JS client opens them."""

from __future__ import annotations

import itertools
import struct
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .fake_client import FakeClient

PUSH = 0  # phoenix.js binary message kinds: push, reply, broadcast


def encode_binary_push(join_ref: str, ref: str, topic: str, event: str, data: bytes) -> bytes:
    """Encode a push the way phoenix.js's `binaryEncode` does, for binary payloads.

    Header: kind, then the lengths of join_ref, ref, topic and event (one byte each),
    then those four strings, then the raw payload.
    """
    meta = [join_ref, ref, topic, event]
    header = struct.pack("B" * 5, PUSH, *(len(part) for part in meta))
    return header + "".join(meta).encode() + data


class FakeUpload:
    """An upload channel (`lvu:N`) with its own join ref, joined with an entry's token."""

    def __init__(self, client: FakeClient, topic: str, join_ref: str, join_reply: dict[str, Any]):
        self.client = client
        self.topic = topic
        self.join_ref = join_ref
        self.join_reply = join_reply

    async def chunk(self, data: bytes) -> dict[str, Any]:
        """Send file bytes as a binary frame, as the browser does."""
        ref = self.client._next_ref()
        frame = encode_binary_push(self.join_ref, ref, self.topic, "chunk", data)
        return await self.client._send_bytes(frame, ref)

    async def leave(self) -> dict[str, Any]:
        return await self.client._push(
            self.client._next_ref(), "phx_leave", {}, self.topic, self.join_ref
        )


class FakeUploadClient:
    """The upload side of a FakeClient, sent on that client's connection.

    File selection, allow_upload and progress go on the view's topic; each file then
    gets its own upload channel (`lvu:N`), returned as a FakeUpload.
    """

    def __init__(self, client: FakeClient):
        self.client = client
        self._topics = itertools.count(0)

    async def select(
        self, upload_name: str, upload_ref: str, files: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """The form change the browser sends when files are chosen in a file input."""
        payload = {
            "type": "form",
            "event": "validate",
            "value": f"_target={upload_name}",
            "uploads": {upload_ref: files},
        }
        return await self.client._push(self.client._next_ref(), "event", payload)

    async def allow(self, upload_ref: str, files: list[dict[str, Any]]) -> dict[str, Any]:
        """Ask to upload the selected files; the reply has the config and an entry token per file."""
        payload = {"ref": upload_ref, "entries": files}
        return await self.client._push(self.client._next_ref(), "allow_upload", payload)

    async def progress(
        self, upload_ref: str, entry_ref: str, progress: int | dict[str, Any]
    ) -> dict[str, Any]:
        """Report a file's progress: a percentage, or a dict when a cloud upload completes or fails."""
        payload = {"event": None, "ref": upload_ref, "entry_ref": entry_ref, "progress": progress}
        return await self.client._push(self.client._next_ref(), "progress", payload)

    async def join(self, token: Any) -> FakeUpload:
        """Join an upload channel with an entry's token; it has its own join ref."""
        topic = f"lvu:{next(self._topics)}"
        ref = self.client._next_ref()
        reply = await self.client._push(ref, "phx_join", {"token": token}, topic, join_ref=ref)
        return FakeUpload(self.client, topic, ref, reply)
