"""
Phoenix LiveView-style Streams for efficient list operations.

Streams allow you to handle large collections on the client without keeping
the full collection in server memory. Only insert/delete operations are tracked
and sent over the wire.
"""

from typing import Generic, TypeVar, Callable, Optional, Any, Iterator
from dataclasses import dataclass
import uuid

T = TypeVar('T')


class Stream(Generic[T]):
    """
    A LiveView stream for efficient list operations.

    Streams enable you to handle large collections without storing them in server
    memory. Instead of sending the entire list on updates, only the operations
    (inserts, deletes) are sent to the client.

    Example:
        @dataclass
        class Message:
            id: int
            text: str

        @dataclass
        class ChatContext:
            messages: Stream[Message]

        class ChatView(LiveView[ChatContext]):
            async def mount(self, socket, session):
                socket.context = ChatContext(
                    messages=Stream(dom_id=lambda m: f"msg-{m.id}")
                )

                # Load initial messages
                messages = await load_messages()
                socket.context.messages.extend(messages)

            async def handle_event(self, event, payload, socket):
                if event == "new_message":
                    msg = Message(id=gen_id(), text=payload["text"])
                    socket.context.messages.insert(msg, at=0)

    Template Usage:
        <div id="messages"
             phx-update="stream"
             data-phx-stream="{{ context.messages.ref }}">
          {% for dom_id, msg in context.messages %}
            <div id="{{ dom_id }}">
              {{ msg.text }}
            </div>
          {% endfor %}
        </div>
    """

    def __init__(
        self,
        dom_id: str | Callable[[T], str] = "id",
        name: Optional[str] = None
    ):
        """
        Initialize a stream.

        Args:
            dom_id: Either an attribute name (e.g., "id") or a function that
                    generates a unique DOM ID from an item. The DOM ID is used
                    to track items on the client.
            name: Optional stream name (set automatically by socket)
        """
        self.name = name
        self.ref = f"phx-{uuid.uuid4().hex[:8]}"
        self._dom_id = dom_id
        self._dom_id_fn = self._make_dom_id_fn(dom_id)

        # Pending operations (cleared after each diff)
        self._inserts: list[tuple[str, int, T, Optional[int], bool]] = []
        self._deletes: list[str] = []
        self._reset: bool = False

        # Items for initial render
        self._initial_items: list[T] = []

        # Track if we've been rendered (to avoid re-rendering initial items)
        self._rendered = False

    def _make_dom_id_fn(self, dom_id: str | Callable[[T], str]) -> Callable[[T], str]:
        """Create a function that extracts DOM ID from an item."""
        if callable(dom_id):
            return dom_id
        else:
            # Attribute name - extract that attribute
            return lambda item: str(getattr(item, dom_id) if hasattr(item, dom_id) else item.get(dom_id))

    def __iter__(self) -> Iterator[tuple[str, T]]:
        """
        Iterate over stream items as (dom_id, item) tuples.

        Yields items that need to be rendered in the template:
        - On first render: yields _initial_items
        - After first render: yields nothing (unless there are pending inserts)
        - Pending inserts: yielded so their HTML gets rendered, then sent as stream ops

        The template comprehension contains:
        - Initial render: all initial items
        - Subsequent renders with new items: ONLY the new items
        - Subsequent renders without changes: empty
        """
        # Yield initial items only on first render
        if not self._rendered and self._initial_items:
            for item in self._initial_items:
                dom_id = self._dom_id_fn(item)
                yield (dom_id, item)
            # Mark as rendered
            self._rendered = True

        # Yield pending inserts so they get rendered
        # Their HTML goes in the comprehension, and stream ops tell client where to put them
        for dom_id, at, item, limit, update_only in self._inserts:
            yield (dom_id, item)

    def insert(
        self,
        item: T,
        at: int = -1,
        limit: Optional[int] = None,
        update_only: bool = False
    ) -> "Stream[T]":
        """
        Insert or update a single item in the stream.

        Args:
            item: The item to insert
            at: Position to insert (-1 = append, 0 = prepend, or specific index)
            limit: Maximum number of items to keep on client
            update_only: If True, only update existing items (don't insert new)

        Returns:
            Self for method chaining

        Example:
            # Prepend new message
            socket.context.messages.insert(new_msg, at=0)

            # Append with limit
            socket.context.messages.insert(new_msg, at=-1, limit=50)
        """
        dom_id = self._dom_id_fn(item)
        # Prepend to maintain insertion order (Phoenix does this)
        self._inserts.insert(0, (dom_id, at, item, limit, update_only))
        return self

    def append(self, item: T, limit: Optional[int] = None) -> "Stream[T]":
        """
        Append an item to the end of the stream.

        Shorthand for insert(item, at=-1).
        """
        return self.insert(item, at=-1, limit=limit)

    def prepend(self, item: T, limit: Optional[int] = None) -> "Stream[T]":
        """
        Prepend an item to the beginning of the stream.

        Shorthand for insert(item, at=0).
        """
        return self.insert(item, at=0, limit=limit)

    def extend(self, items: list[T], at: int = -1) -> "Stream[T]":
        """
        Bulk insert multiple items.

        For initial loading (before first render), items are added to _initial_items
        to avoid sending them as stream operations. For subsequent calls, items are
        added as insert operations.

        Args:
            items: List of items to insert
            at: Position to insert (-1 = append, 0 = prepend)

        Returns:
            Self for method chaining

        Example:
            # Load initial messages during mount
            messages = await load_messages()
            socket.context.messages.extend(messages)

            # Add more messages later (sent as stream operations)
            new_messages = await load_more()
            socket.context.messages.extend(new_messages, at=0)
        """
        # If no operations have been performed yet, this is initial loading
        # Add to _initial_items instead of creating operations
        if not self.has_operations() and not self._initial_items:
            self._initial_items.extend(items)
        else:
            # Subsequent calls create stream operations
            for item in items:
                self.insert(item, at=at)
        return self

    def update(self, item: T) -> "Stream[T]":
        """
        Update an existing item in the stream.

        Uses update_only=True, so the item must already exist on the client.

        Args:
            item: The item to update

        Returns:
            Self for method chaining
        """
        return self.insert(item, update_only=True)

    def remove(self, item: T) -> "Stream[T]":
        """
        Remove an item from the stream.

        Args:
            item: The item to remove (DOM ID will be extracted)

        Returns:
            Self for method chaining

        Example:
            socket.context.messages.remove(old_message)
        """
        dom_id = self._dom_id_fn(item)
        self._deletes.append(dom_id)
        return self

    def remove_by_id(self, dom_id: str) -> "Stream[T]":
        """
        Remove an item by its DOM ID without needing the full item.

        Args:
            dom_id: The DOM ID of the item to remove

        Returns:
            Self for method chaining

        Example:
            socket.context.messages.remove_by_id("msg-123")
        """
        self._deletes.append(dom_id)
        return self

    def reset(self, items: Optional[list[T]] = None) -> "Stream[T]":
        """
        Clear all items on the client and optionally replace with new items.

        Args:
            items: Optional list of new items to display

        Returns:
            Self for method chaining

        Example:
            # Clear and reload
            new_messages = await load_messages()
            socket.context.messages.reset(new_messages)
        """
        self._reset = True
        self._inserts.clear()
        self._deletes.clear()
        self._initial_items.clear()

        if items:
            self.extend(items)

        return self

    def has_operations(self) -> bool:
        """Check if there are pending operations to send to client."""
        return bool(self._inserts or self._deletes or self._reset)

    def consume_operations(self) -> tuple[list[tuple[str, int, T, Optional[int], bool]], list[str], bool]:
        """
        Get and clear pending operations.

        Used internally by the diff engine.

        Returns:
            Tuple of (inserts, deletes, reset)
        """
        # Reverse inserts to get correct order (we prepended them)
        inserts = list(reversed(self._inserts))
        deletes = list(self._deletes)
        reset = self._reset

        # Clear pending operations
        self._inserts.clear()
        self._deletes.clear()
        self._reset = False

        # After first render, clear initial items
        self._initial_items.clear()

        return inserts, deletes, reset

    def __repr__(self) -> str:
        ops = []
        if self._inserts:
            ops.append(f"{len(self._inserts)} inserts")
        if self._deletes:
            ops.append(f"{len(self._deletes)} deletes")
        if self._reset:
            ops.append("reset")

        ops_str = ", ".join(ops) if ops else "no operations"
        return f"Stream(ref={self.ref}, {ops_str})"
