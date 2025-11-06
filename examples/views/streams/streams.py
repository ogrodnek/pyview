"""
Example LiveView demonstrating Phoenix LiveView-style Streams.

Streams enable efficient handling of large collections by only sending
insert/delete operations over the wire instead of the entire list.
"""

from dataclasses import dataclass
from typing import Optional
from pyview import LiveView, LiveViewSocket, ConnectedLiveViewSocket, Stream
import random
import time


@dataclass
class Message:
    """A chat message."""
    id: int
    text: str
    user: str
    timestamp: float


@dataclass
class StreamsContext:
    """Context for the streams demo."""
    messages: Stream[Message]
    message_count: int
    next_id: int


class StreamsLiveView(LiveView[StreamsContext]):
    """
    Demonstrates stream operations:
    - Insert at beginning (prepend)
    - Insert at end (append)
    - Delete individual items
    - Bulk operations
    - Reset stream
    """

    async def mount(self, socket: LiveViewSocket[StreamsContext], session):
        """Initialize the stream with some sample messages."""

        # Initialize the stream with a dom_id function
        messages_stream = Stream[Message](
            dom_id=lambda msg: f"msg-{msg.id}"
        )

        # Create initial messages
        initial_messages = [
            Message(
                id=i,
                text=self._random_message(),
                user=random.choice(["Alice", "Bob", "Charlie"]),
                timestamp=time.time() - (10 - i) * 60
            )
            for i in range(1, 6)
        ]

        # Bulk load initial messages
        messages_stream.extend(initial_messages)

        socket.context = StreamsContext(
            messages=messages_stream,
            message_count=len(initial_messages),
            next_id=len(initial_messages) + 1
        )

    async def handle_event(
        self,
        event: str,
        payload: dict,
        socket: ConnectedLiveViewSocket[StreamsContext]
    ):
        """Handle user interactions."""

        if event == "add_top":
            # Prepend a new message to the beginning
            new_msg = Message(
                id=socket.context.next_id,
                text=self._random_message(),
                user=random.choice(["Alice", "Bob", "Charlie"]),
                timestamp=time.time()
            )
            socket.context.messages.prepend(new_msg)
            socket.context.next_id += 1
            socket.context.message_count += 1

        elif event == "add_bottom":
            # Append a new message to the end
            new_msg = Message(
                id=socket.context.next_id,
                text=self._random_message(),
                user=random.choice(["Alice", "Bob", "Charlie"]),
                timestamp=time.time()
            )
            socket.context.messages.append(new_msg)
            socket.context.next_id += 1
            socket.context.message_count += 1

        elif event == "add_bulk":
            # Add multiple messages at once
            new_messages = [
                Message(
                    id=socket.context.next_id + i,
                    text=self._random_message(),
                    user=random.choice(["Alice", "Bob", "Charlie"]),
                    timestamp=time.time()
                )
                for i in range(5)
            ]
            socket.context.messages.extend(new_messages, at=0)
            socket.context.next_id += len(new_messages)
            socket.context.message_count += len(new_messages)

        elif event == "delete":
            # Delete a specific message
            msg_id = int(payload["id"])
            socket.context.messages.remove_by_id(f"msg-{msg_id}")
            socket.context.message_count -= 1

        elif event == "reset":
            # Reset the stream with new messages
            new_messages = [
                Message(
                    id=i,
                    text=self._random_message(),
                    user=random.choice(["Alice", "Bob", "Charlie"]),
                    timestamp=time.time()
                )
                for i in range(1, 4)
            ]
            socket.context.messages.reset(new_messages)
            socket.context.message_count = len(new_messages)
            socket.context.next_id = len(new_messages) + 1

    def _random_message(self) -> str:
        """Generate a random message text."""
        messages = [
            "Hello, how are you?",
            "Great weather today!",
            "Did you see the game last night?",
            "I love using Phoenix LiveView!",
            "Streams make handling lists so efficient!",
            "Python + LiveView = ❤️",
            "This is a test message",
            "Real-time updates are awesome",
            "Minimal data over the wire!",
            "No more full page reloads!"
        ]
        return random.choice(messages)

    def _format_timestamp(self, timestamp: float) -> str:
        """Format timestamp as relative time."""
        seconds_ago = int(time.time() - timestamp)
        if seconds_ago < 60:
            return f"{seconds_ago}s ago"
        elif seconds_ago < 3600:
            return f"{seconds_ago // 60}m ago"
        else:
            return f"{seconds_ago // 3600}h ago"
