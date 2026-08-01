import json
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional

from ..presence.avatars import Avatar

MAX_DOCUMENT_BYTES = 64 * 1024
MAX_UPDATES_PER_PUSH = 50
MAX_CHANGE_SECTIONS = 4096
MAX_COLLABORATORS = 8
MAX_ROOMS = 100
MAX_HISTORY_UPDATES = 100
MAX_HISTORY_BYTES = 256 * 1024
ROOM_LIFETIME_SECONDS = 60 * 60
EMPTY_ROOM_LIFETIME_SECONDS = 15 * 60


class InvalidChangeSet(ValueError):
    pass


class DocumentTooLarge(ValueError):
    pass


class RoomCapacityReached(RuntimeError):
    pass


def utf16_len(value: str) -> int:
    """Length in UTF-16 code units, matching CodeMirror's document positions."""
    return len(value.encode("utf-16-le", errors="surrogatepass")) // 2


def utf8_len(value: str) -> int:
    return len(value.encode("utf-8", errors="surrogatepass"))


def apply_changes(doc: str, changes: list) -> str:
    """Validate and apply a serialized CodeMirror 6 ChangeSet."""
    if not isinstance(changes, list) or len(changes) > MAX_CHANGE_SECTIONS:
        raise InvalidChangeSet("changes must be a reasonably-sized list")

    buf = doc.encode("utf-16-le", errors="surrogatepass")
    doc_length = len(buf) // 2
    out = bytearray()
    pos = 0

    for section in changes:
        if type(section) is int:
            if section < 0 or pos + section > doc_length:
                raise InvalidChangeSet("retained range is outside the document")
            out += buf[2 * pos : 2 * (pos + section)]
            pos += section
            continue

        if not isinstance(section, list) or not section or type(section[0]) is not int:
            raise InvalidChangeSet("invalid change section")

        deleted = section[0]
        if deleted < 0 or pos + deleted > doc_length:
            raise InvalidChangeSet("deleted range is outside the document")
        if any(not isinstance(line, str) for line in section[1:]):
            raise InvalidChangeSet("inserted content must contain strings")

        pos += deleted
        inserted = "\n".join(section[1:])
        out += inserted.encode("utf-16-le", errors="surrogatepass")

    out += buf[2 * pos :]
    return out.decode("utf-16-le", errors="surrogatepass")


@dataclass
class DocAuthority:
    """Materialized document plus a small history for stale-client recovery."""

    doc: str = ""
    version: int = 0
    recent_updates: deque[dict] = field(default_factory=deque)
    recent_update_bytes: int = 0

    @property
    def history_start_version(self) -> int:
        return self.version - len(self.recent_updates)

    def receive(
        self, version: int, updates: object, client_id: str
    ) -> tuple[int, list[dict]] | None:
        if type(version) is not int or version < 0:
            raise InvalidChangeSet("invalid document version")
        if version != self.version:
            return None
        if not isinstance(updates, list) or not 1 <= len(updates) <= MAX_UPDATES_PER_PUSH:
            raise InvalidChangeSet("invalid update batch")

        candidate = self.doc
        normalized: list[dict] = []
        for update in updates:
            if not isinstance(update, dict) or "changes" not in update:
                raise InvalidChangeSet("invalid update")
            changes = update["changes"]
            candidate = apply_changes(candidate, changes)
            if utf8_len(candidate) > MAX_DOCUMENT_BYTES:
                raise DocumentTooLarge()
            normalized.append({"clientID": client_id, "changes": changes})

        from_version = self.version
        self.doc = candidate
        for update in normalized:
            self.version += 1
            update_size = len(
                json.dumps(update, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
            )
            self.recent_updates.append(update)
            self.recent_update_bytes += update_size
            while self.recent_updates and (
                len(self.recent_updates) > MAX_HISTORY_UPDATES
                or self.recent_update_bytes > MAX_HISTORY_BYTES
            ):
                removed = self.recent_updates.popleft()
                self.recent_update_bytes -= len(
                    json.dumps(removed, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
                )

        return from_version, normalized

    def updates_since(self, version: int) -> Optional[list[dict]]:
        if type(version) is not int or version < self.history_start_version:
            return None
        if version > self.version:
            return None
        offset = version - self.history_start_version
        return list(self.recent_updates)[offset:]

    def clear(self) -> None:
        self.doc = ""
        self.recent_updates.clear()
        self.recent_update_bytes = 0


@dataclass
class Editor:
    client_id: str
    user: Avatar
    event_times: dict[str, deque[float]] = field(default_factory=dict)

    def allow_event(self, kind: str, now: float, limit_per_second: int = 30) -> bool:
        times = self.event_times.setdefault(kind, deque())
        while times and times[0] <= now - 1:
            times.popleft()
        if len(times) >= limit_per_second:
            return False
        times.append(now)
        return True


@dataclass
class CollabRoom:
    room_id: str
    created_at: float
    empty_since: Optional[float]
    authority: DocAuthority = field(default_factory=DocAuthority)
    editors: dict[str, Editor] = field(default_factory=dict)

    @property
    def topic(self) -> str:
        return f"collab_editor:doc:{self.room_id}"

    def is_expired(self, now: float, room_lifetime: float, empty_lifetime: float) -> bool:
        if now - self.created_at >= room_lifetime:
            return True
        return self.empty_since is not None and now - self.empty_since >= empty_lifetime

    def join(self, editor: Editor) -> bool:
        if len(self.editors) >= MAX_COLLABORATORS:
            return False
        self.editors[editor.client_id] = editor
        self.empty_since = None
        return True

    def clear(self) -> None:
        self.authority.clear()
        self.editors.clear()


class RoomStore:
    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_rooms: int = MAX_ROOMS,
        room_lifetime: float = ROOM_LIFETIME_SECONDS,
        empty_lifetime: float = EMPTY_ROOM_LIFETIME_SECONDS,
        authority_factory: Callable[[], DocAuthority] = DocAuthority,
    ):
        self.clock = clock
        self.max_rooms = max_rooms
        self.room_lifetime = room_lifetime
        self.empty_lifetime = empty_lifetime
        self.authority_factory = authority_factory
        self.rooms: dict[str, CollabRoom] = {}
        self._expired_topics: set[str] = set()

    def create(self) -> CollabRoom:
        self.delete_expired()
        if len(self.rooms) >= self.max_rooms:
            empty_rooms = [room for room in self.rooms.values() if not room.editors]
            if not empty_rooms:
                raise RoomCapacityReached()
            oldest = min(empty_rooms, key=lambda room: room.empty_since or room.created_at)
            self._delete(oldest.room_id)

        now = self.clock()
        room = CollabRoom(
            room_id=str(uuid.uuid4()),
            created_at=now,
            empty_since=now,
            authority=self.authority_factory(),
        )
        self.rooms[room.room_id] = room
        return room

    def get(self, room_id: str) -> Optional[CollabRoom]:
        room = self.rooms.get(room_id)
        if room is None:
            return None
        if room.is_expired(self.clock(), self.room_lifetime, self.empty_lifetime):
            self._delete(room_id)
            return None
        return room

    def leave(self, room_id: str, client_id: str) -> Optional[CollabRoom]:
        room = self.get(room_id)
        if room is None:
            return None
        room.editors.pop(client_id, None)
        if not room.editors:
            room.empty_since = self.clock()
        return room

    def delete_expired(self) -> None:
        now = self.clock()
        for room_id, room in list(self.rooms.items()):
            if room.is_expired(now, self.room_lifetime, self.empty_lifetime):
                self._delete(room_id)

    def drain_expired_topics(self) -> list[str]:
        topics = list(self._expired_topics)
        self._expired_topics.clear()
        return topics

    def _delete(self, room_id: str) -> None:
        room = self.rooms.pop(room_id, None)
        if room is None:
            return
        self._expired_topics.add(room.topic)
        room.clear()
