"""
Phoenix LiveView Streams implementation for pyview.

Streams provide efficient rendering of large collections by:
- Not keeping items in server memory (only operations are tracked)
- Sending only changed items over the wire
- Letting the client manage DOM state

Example usage:
    @dataclass
    class ChatContext:
        messages: Stream[Message]

    class ChatLive(LiveView[ChatContext]):
        async def mount(self, socket, session):
            messages = await load_messages()
            socket.context = ChatContext(
                messages=Stream(messages, name="messages")
            )

        async def handle_event(self, event, payload, socket):
            if event == "send":
                msg = await create_message(payload["text"])
                socket.context.messages.insert(msg)
            elif event == "delete":
                socket.context.messages.delete_by_id(f"messages-{payload['id']}")
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Generic, Iterator, TypeVar

T = TypeVar("T")


@dataclass
class StreamInsert:
    """Represents a pending insert operation."""

    dom_id: str
    item: Any
    at: int
    limit: int | None
    update_only: bool


@dataclass
class StreamOps:
    """Pending stream operations to be sent to the client."""

    ref: str
    inserts: list[StreamInsert] = field(default_factory=list)
    deletes: list[str] = field(default_factory=list)
    reset: bool = False

    def has_operations(self) -> bool:
        """Check if there are any pending operations."""
        return bool(self.inserts or self.deletes or self.reset)


class Stream(Generic[T]):
    """
    A stream collection for efficient list rendering.

    Streams track operations (inserts, deletes) rather than keeping all items
    in memory. This matches Phoenix LiveView's design where the server doesn't
    maintain the full list - only the client does.

    Args:
        items: Initial items to populate the stream (optional)
        name: Stream reference name (required) - used in wire format and DOM IDs
        dom_id: Function to generate DOM ID from an item (optional)
                Defaults to using item.id or item["id"]

    Example:
        # With dataclass items
        stream = Stream(users, name="users")  # Uses user.id -> "users-{id}"

        # With dict items
        stream = Stream(items, name="items", dom_id=lambda x: f"item-{x['uuid']}")

        # Operations
        stream.insert(new_user)                    # Append
        stream.insert(new_user, at=0)              # Prepend
        stream.insert(user, at=2)                  # Insert at index
        stream.delete(user)                        # Delete by item
        stream.delete_by_id("users-123")           # Delete by DOM ID
        stream.reset(new_users)                    # Clear and replace all
    """

    def __init__(
        self,
        items: list[T] | None = None,
        *,
        name: str,
        dom_id: Callable[[T], str] | None = None,
    ):
        if not name:
            raise ValueError("Stream 'name' is required")

        self.name = name
        self._dom_id_fn = dom_id or self._default_dom_id

        # Pending operations (cleared after each render)
        self._ops = StreamOps(ref=name)

        # Track items for iteration (only pending inserts, not full history)
        # This is used by templates to render the items
        self._pending_items: list[tuple[str, T]] = []

        # Initialize with items if provided
        if items:
            for item in items:
                self._do_insert(item, at=-1, limit=None, update_only=False)

    def _default_dom_id(self, item: T) -> str:
        """Default DOM ID generator - uses item.id or item['id']."""
        if hasattr(item, "id"):
            return f"{self.name}-{item.id}"  # type: ignore[union-attr]
        if isinstance(item, dict) and "id" in item:
            return f"{self.name}-{item['id']}"
        raise ValueError(
            f"Cannot generate DOM ID for item {item!r}. "
            f"Item must have an 'id' attribute/key, or provide a dom_id function."
        )

    def _do_insert(self, item: T, at: int, limit: int | None, update_only: bool) -> str:
        """Internal insert implementation."""
        dom_id = self._dom_id_fn(item)
        self._ops.inserts.append(
            StreamInsert(
                dom_id=dom_id,
                item=item,
                at=at,
                limit=limit,
                update_only=update_only,
            )
        )
        self._pending_items.append((dom_id, item))
        return dom_id

    def insert(
        self,
        item: T,
        *,
        at: int = -1,
        limit: int | None = None,
        update_only: bool = False,
    ) -> str:
        """
        Insert or update an item in the stream.

        Args:
            item: The item to insert
            at: Position to insert at
                -1 = append (end)
                 0 = prepend (beginning)
                 N = specific index
            limit: Maximum items to keep (client-side enforcement)
                   Positive = keep first N (removes from end)
                   Negative = keep last N (removes from beginning)
            update_only: If True, only update existing items (don't add new)

        Returns:
            The DOM ID of the inserted item

        Note:
            If an item with the same DOM ID already exists in the client DOM,
            it will be updated in place (not moved) regardless of the 'at' value.
        """
        return self._do_insert(item, at, limit, update_only)

    def insert_many(
        self,
        items: list[T],
        *,
        at: int = -1,
        limit: int | None = None,
    ) -> list[str]:
        """
        Insert multiple items.

        Args:
            items: List of items to insert
            at: Position for all items (-1=append, 0=prepend, N=index)
            limit: Maximum items to keep

        Returns:
            List of DOM IDs for inserted items
        """
        return [self._do_insert(item, at, limit, False) for item in items]

    def delete(self, item: T) -> str:
        """
        Delete an item from the stream.

        Args:
            item: The item to delete (used to compute DOM ID)

        Returns:
            The DOM ID of the deleted item
        """
        dom_id = self._dom_id_fn(item)
        self._ops.deletes.append(dom_id)
        return dom_id

    def delete_by_id(self, dom_id: str) -> str:
        """
        Delete an item by its DOM ID.

        Args:
            dom_id: The DOM ID to delete (e.g., "users-123")

        Returns:
            The DOM ID that was deleted
        """
        self._ops.deletes.append(dom_id)
        return dom_id

    def reset(self, items: list[T] | None = None) -> None:
        """
        Clear all items and optionally replace with new ones.

        This sends a reset signal to the client, which removes all existing
        stream items from the DOM before applying any new inserts.

        Args:
            items: New items to populate after clearing (optional)
        """
        self._ops.reset = True
        self._ops.inserts.clear()
        self._pending_items.clear()

        if items:
            for item in items:
                self._do_insert(item, at=-1, limit=None, update_only=False)

    def __iter__(self) -> Iterator[tuple[str, T]]:
        """
        Iterate over pending items as (dom_id, item) tuples.

        This is used by templates to render stream items:

            {% for dom_id, user in users %}
            <div id="{{ dom_id }}">{{ user.name }}</div>
            {% endfor %}
        """
        return iter(self._pending_items)

    def __len__(self) -> int:
        """Return the number of pending items."""
        return len(self._pending_items)

    def __bool__(self) -> bool:
        """Stream is truthy if it has pending operations or items."""
        return bool(self._pending_items) or self._ops.has_operations()

    # --- Internal methods for rendering ---

    def _get_pending_ops(self) -> StreamOps | None:
        """
        Get pending operations and clear them.

        Called by the renderer after processing the stream.
        Returns None if there are no pending operations.
        """
        if not self._ops.has_operations():
            return None

        ops = self._ops
        self._ops = StreamOps(ref=self.name)
        self._pending_items.clear()
        return ops

    def _to_wire_format(self, ops: StreamOps) -> list:
        """
        Convert operations to Phoenix LiveView 0.19+/0.20 wire format.

        Format: [stream_ref, [[dom_id, at, limit], ...], [delete_ids], reset?]

        The Phoenix JS client expects:
        - stream_ref: the stream name/reference
        - inserts: array of [dom_id, at, limit] tuples
          - dom_id: string identifier for the DOM element
          - at: position (-1=append, 0=prepend, N=specific index)
          - limit: max items to keep (positive=remove from start, negative=remove from end, null=no limit)
        - deletes: array of dom_ids to remove
        - reset: ONLY included if true (omitted = no reset, because JS checks `reset !== undefined`)

        Note: update_only is stored internally but not sent over wire in 0.20 format.
        """
        inserts = [[ins.dom_id, ins.at, ins.limit] for ins in ops.inserts]

        # Only include reset if true - JS checks `reset !== undefined` to trigger reset
        if ops.reset:
            return [ops.ref, inserts, ops.deletes, True]
        else:
            return [ops.ref, inserts, ops.deletes]

    def _get_wire_format(self) -> list | None:
        """
        Convenience method to get wire format directly.

        Returns None if no pending operations.
        """
        ops = self._get_pending_ops()
        if ops is None:
            return None
        return self._to_wire_format(ops)
