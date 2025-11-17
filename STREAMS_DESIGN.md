# PyView Streams API Design Document

## Overview

This document describes the design and implementation of PyView's Streams API, a Pythonic adaptation of Phoenix LiveView's streams feature for efficient handling of large, dynamic collections.

## Problem Statement

### The Challenge

Traditional LiveView approaches require sending the entire list on every update:

```python
@dataclass
class ChatContext:
    messages: list[Message]  # Full list stored in memory

# Every update re-renders and sends ALL messages
socket.context.messages.append(new_message)
```

**Problems:**
1. **Memory**: Server must keep entire collection in memory
2. **Bandwidth**: Every update sends complete list over WebSocket
3. **Performance**: Re-rendering grows O(n) with list size
4. **Scalability**: Doesn't work for large or infinite lists

### Phoenix LiveView's Solution

Phoenix introduced "streams" - a way to track collections without storing them:

```elixir
# Elixir/Phoenix approach
socket = stream(socket, :messages, [msg1, msg2, msg3])
socket = stream_insert(socket, :messages, new_msg, at: 0)
```

**Benefits:**
- Server doesn't store the collection
- Only insert/delete operations sent over wire
- Client maintains the DOM state
- O(1) updates regardless of list size

## Design Goals

### 1. Pythonic API

**Goal**: Feel natural to Python developers, not like a port of Elixir.

**Approach**: Use Python's rich type system and familiar patterns:
- Generic types for IDE autocomplete
- Dataclass integration
- Method chaining
- Iterator protocol

### 2. Type Safety

**Goal**: Full type checking and IDE support.

**Approach**:
- `Stream[T]` generic type
- Context fields are strongly typed
- No `Any` types or dynamic attributes

### 3. Explicit Over Implicit

**Goal**: Clear, predictable behavior.

**Approach**:
- Streams are explicit objects in context
- Operations have clear names (`prepend`, `append`, not `insert(at=0)`)
- No magic - you see the Stream, you know it's a stream

### 4. Minimal Boilerplate

**Goal**: Easy to use, hard to misuse.

**Approach**:
- One import: `from pyview import Stream`
- Automatic DOM ID generation
- Template integration is transparent

## API Design

### Core Design Decision: Streams in Context

We evaluated two approaches:

#### Option 1: Socket-Based (Rejected)
```python
# Phoenix-like approach
socket.stream("messages", [msg1, msg2])
socket.stream_insert("messages", new_msg)

# Template
{% for id, msg in streams.messages %}
```

**Pros:**
- Similar to Phoenix
- Centralized stream management

**Cons:**
- ❌ No type safety - streams are runtime dictionary
- ❌ IDE can't autocomplete `streams.messages`
- ❌ Disconnect between socket operations and template
- ❌ Not idiomatic Python

#### Option 2: Context-Based (Chosen) ✅
```python
@dataclass
class ChatContext:
    messages: Stream[Message]  # Type-safe!

socket.context = ChatContext(
    messages=Stream[Message](dom_id=lambda m: f"msg-{m.id}")
)

socket.context.messages.prepend(new_msg)  # IDE knows this exists!

# Template
{% for dom_id, msg in context.messages %}
```

**Pros:**
- ✅ Full type safety with generics
- ✅ IDE autocomplete and type checking
- ✅ Natural Python - streams are just objects
- ✅ Same pattern as other context fields
- ✅ Explicit - you see `Stream[Message]` in the dataclass

**Cons:**
- Different from Phoenix (but that's okay - Python isn't Elixir)

**Decision**: Option 2. Type safety and Pythonic design trump API similarity to Phoenix.

### Stream Class Design

#### Generic Type Parameter

```python
class Stream(Generic[T]):
    """A memory-efficient collection that sends only diffs."""
```

**Why Generic?**
- IDE knows `Stream[Message]` yields `Message` objects
- Type checking catches errors at development time
- Self-documenting code

#### DOM ID Strategy

```python
Stream[T](
    dom_id: str | Callable[[T], str] = "id",
    name: Optional[str] = None
)
```

**Design choices:**

1. **String attribute name** (default: `"id"`):
   ```python
   Stream[Message]()  # Uses msg.id
   ```
   - Simple for common case
   - Works with `@dataclass` that have `id` field

2. **Lambda function** (flexible):
   ```python
   Stream[Message](dom_id=lambda msg: f"msg-{msg.id}")
   ```
   - Full control over DOM ID format
   - Can combine multiple fields
   - Handles complex ID generation

3. **Automatic name detection**:
   ```python
   @dataclass
   class Context:
       messages: Stream[Message]  # name auto-set to "messages"
   ```
   - Reduces boilerplate
   - Used for debugging/logging

#### Operations API

**Principle**: Descriptive method names over position parameters.

```python
# Clear intent
stream.prepend(item)        # Add to beginning
stream.append(item)         # Add to end
stream.insert(item, at=5)   # Add at specific position

# vs Phoenix's generic approach
stream_insert(socket, :messages, item, at: 0)   # Less clear
stream_insert(socket, :messages, item, at: -1)  # What does -1 mean?
```

**Complete API:**
```python
class Stream(Generic[T]):
    # Adding items
    def insert(self, item: T, at: int = -1, limit: Optional[int] = None,
               update_only: bool = False) -> "Stream[T]"
    def prepend(self, item: T) -> "Stream[T]"
    def append(self, item: T) -> "Stream[T]"
    def extend(self, items: list[T], at: int = -1) -> "Stream[T]"

    # Removing items
    def remove_by_id(self, dom_id: str) -> "Stream[T]"
    def reset(self, items: list[T]) -> "Stream[T]"

    # Iteration (for templates)
    def __iter__(self) -> Iterator[tuple[str, T]]
```

**Method chaining** (returns `self`):
```python
stream.prepend(msg1).prepend(msg2).prepend(msg3)
```

### Template Integration

#### Iteration Protocol

**Key insight**: Streams yield `(dom_id, item)` tuples.

```python
def __iter__(self) -> Iterator[tuple[str, T]]:
    """Yield (dom_id, item) tuples for template rendering."""
```

**Benefits:**
1. Template gets both ID and item
2. Natural tuple unpacking in for loop
3. Matches Phoenix's `{id, item}` pattern
4. Clear that this is special (not just items)

#### Template Usage

```html
<div id="messages" phx-update="stream" data-phx-stream="{{ context.messages.ref }}">
  {% for dom_id, msg in context.messages %}
    <div id="{{ dom_id }}">
      {{ msg.text }}
    </div>
  {% endfor %}
</div>
```

**Required attributes:**
- `phx-update="stream"` - Tell client this is a stream
- `data-phx-stream="{{ stream.ref }}"` - Match stream to container
- `id="{{ dom_id }}"` - Each item needs its unique ID

**Stream reference** (`ref`):
```python
self.ref = f"phx-{uuid.uuid4().hex[:8]}"
```
- Unique identifier for this stream instance
- Matches Phoenix's format
- Used to route operations to correct container

## Implementation Details

### Internal State Management

```python
class Stream(Generic[T]):
    def __init__(self, dom_id, name):
        self.ref = f"phx-{uuid.uuid4().hex[:8]}"
        self._inserts: list[tuple[str, int, T, Optional[int], bool]] = []
        self._deletes: list[str] = []
        self._reset: bool = False
        self._initial_items: list[T] = []
        self._rendered = False
```

**Design decisions:**

#### 1. Separate Initial Items from Operations

```python
self._initial_items: list[T] = []  # Items loaded during mount
self._inserts: list[tuple] = []    # Pending insert operations
```

**Why?**
- `extend()` during mount = initial load (not an operation)
- Subsequent operations = actual changes to send
- Prevents sending "insert operations" for initial render

#### 2. Rendered Flag

```python
self._rendered = False
```

**Purpose**: Track if stream has been rendered at least once.

**Behavior**:
- First render: Yield `_initial_items` + `_inserts`, set `_rendered = True`
- Subsequent renders: Yield only `_inserts` (new items)

**Why critical?**
- Phoenix client expects only NEW items in diff
- Re-sending initial items would cause duplicates
- Minimal diff principle

#### 3. Operation Accumulation

```python
def prepend(self, item: T) -> "Stream[T]":
    dom_id = self._dom_id_fn(item)
    self._inserts.insert(0, (dom_id, 0, item, None, False))
    return self
```

**Pattern**: Operations accumulate until consumed by diff engine.

**Flow**:
1. User calls `stream.prepend(item)` → Added to `_inserts`
2. Render triggered → Template iterates stream
3. Diff calculated → Operations extracted via `consume_operations()`
4. Operations cleared → Ready for next update

### Socket Integration

The socket automatically detects and processes streams:

```python
# In ConnectedLiveViewSocket
def _find_streams_in_context(self) -> list[tuple[str, Stream]]:
    """Walk the context and find all Stream instances."""
    streams = []
    if is_dataclass(self.context):
        for field in fields(self.context):
            value = getattr(self.context, field.name)
            if isinstance(value, Stream):
                streams.append((field.name, value))
    return streams

def diff(self, render: dict[str, Any]) -> dict[str, Any]:
    diff = calc_diff(self.prev_rendered, render)

    # Add stream operations if any exist
    stream_ops = self._extract_stream_operations(render)
    if stream_ops:
        diff["stream"] = stream_ops

    return diff
```

**Key features:**
1. **Automatic discovery**: No manual registration needed
2. **Dataclass-aware**: Works with `@dataclass` fields
3. **Dict support**: Also works with dict-based contexts
4. **Name inference**: Auto-sets stream name from field name

## Type Safety Benefits

### Before: Phoenix Pattern (Elixir)

```elixir
# No compile-time checking
socket = stream(socket, :messages, messages)
socket = stream_insert(socket, :messagez, msg)  # Typo! Runtime error

# In template
<%= for {id, msg} <- @streams.messges do %>  # Typo! Runtime error
```

### After: PyView Pattern (Python)

```python
@dataclass
class ChatContext:
    messages: Stream[Message]
    message_count: int

socket.context = ChatContext(
    messages=Stream[Message](),
    message_count=0
)

# IDE autocomplete and type checking
socket.context.messages.prepend(msg)  # ✅ IDE knows this method exists
socket.context.messges.prepend(msg)   # ❌ IDE catches typo
socket.context.messages.prepend(123)  # ❌ Type checker catches wrong type

# Template
{% for dom_id, msg in context.messages %}
  {{ msg.text }}  {# IDE knows msg is Message type #}
{% endfor %}
```

**Benefits:**
- Catch typos at development time
- IDE autocomplete for all operations
- Refactoring is safe (rename field = all references update)
- Self-documenting (type annotations show what's expected)

## Comparison with Phoenix

### Phoenix LiveView (Elixir)

```elixir
defmodule ChatLive do
  def mount(_params, _session, socket) do
    socket = stream(socket, :messages, list_messages())
    {:ok, socket}
  end

  def handle_event("new_message", %{"text" => text}, socket) do
    msg = %{id: generate_id(), text: text}
    {:noreply, stream_insert(socket, :messages, msg, at: 0)}
  end
end

# Template
<div id="messages" phx-update="stream">
  <%= for {id, msg} <- @streams.messages do %>
    <div id={id}><%= msg.text %></div>
  <% end %>
</div>
```

### PyView (Python)

```python
class ChatLiveView(LiveView[ChatContext]):
    async def mount(self, socket: LiveViewSocket[ChatContext], session):
        messages_stream = Stream[Message](dom_id=lambda m: f"msg-{m.id}")
        messages_stream.extend(await list_messages())

        socket.context = ChatContext(messages=messages_stream)

    async def handle_event(self, event, payload, socket):
        if event == "new_message":
            msg = Message(id=generate_id(), text=payload["text"])
            socket.context.messages.prepend(msg)

# Template
<div id="messages" phx-update="stream" data-phx-stream="{{ context.messages.ref }}">
  {% for dom_id, msg in context.messages %}
    <div id="{{ dom_id }}">{{ msg.text }}</div>
  {% endfor %}
</div>
```

### Key Differences

| Aspect | Phoenix | PyView | Rationale |
|--------|---------|--------|-----------|
| **Stream location** | `socket.assigns.streams` | `socket.context.messages` | Python: explicit better than implicit |
| **Type safety** | Runtime | Compile-time | Python has static typing, Elixir doesn't |
| **Operations** | `stream_insert(socket, :name, item)` | `stream.prepend(item)` | OOP vs functional |
| **Stream creation** | `stream(socket, :name, items)` | `Stream[T]()` then `extend()` | Explicit object creation |
| **DOM ID** | Via `:dom_id` option | Via constructor param | Same concept, different syntax |

### Design Philosophy Differences

**Phoenix (Functional):**
- Data transformations on socket
- Functions operate on assigns
- Pattern matching and immutability

**PyView (Object-Oriented):**
- Objects with methods
- State encapsulation
- Classes and inheritance

**Both valid approaches** - each idiomatic to its language!

## Usage Examples

### Basic Chat Application

```python
from dataclasses import dataclass
from pyview import LiveView, LiveViewSocket, Stream

@dataclass
class Message:
    id: int
    user: str
    text: str
    timestamp: datetime

@dataclass
class ChatContext:
    messages: Stream[Message]
    online_count: int

class ChatLiveView(LiveView[ChatContext]):
    async def mount(self, socket: LiveViewSocket[ChatContext], session):
        # Create stream with custom DOM ID
        messages = Stream[Message](
            dom_id=lambda msg: f"msg-{msg.id}"
        )

        # Load recent messages (not sent as operations)
        recent = await db.get_recent_messages(limit=50)
        messages.extend(recent)

        socket.context = ChatContext(
            messages=messages,
            online_count=await get_online_count()
        )

    async def handle_event(self, event, payload, socket):
        if event == "send_message":
            msg = Message(
                id=generate_id(),
                user=socket.session["user"],
                text=payload["text"],
                timestamp=datetime.now()
            )

            # Add to top of chat (sent as operation)
            socket.context.messages.prepend(msg)

            # Broadcast to other users
            await self.broadcast("new_message", msg)

    async def handle_info(self, event, socket):
        if event["type"] == "new_message":
            socket.context.messages.prepend(event["message"])
```

### Infinite Scroll Feed

```python
@dataclass
class FeedContext:
    posts: Stream[Post]
    has_more: bool

class FeedLiveView(LiveView[FeedContext]):
    async def mount(self, socket, session):
        posts = Stream[Post](dom_id=lambda p: f"post-{p.id}")

        # Initial page
        initial_posts = await load_posts(limit=20)
        posts.extend(initial_posts)

        socket.context = FeedContext(
            posts=posts,
            has_more=len(initial_posts) == 20
        )

    async def handle_event(self, event, payload, socket):
        if event == "load_more":
            # Load older posts
            older = await load_posts(
                before_id=payload["last_id"],
                limit=20
            )

            # Add to bottom (at: -1)
            socket.context.messages.extend(older, at=-1)
            socket.context.has_more = len(older) == 20
```

### Real-time Notifications

```python
@dataclass
class NotificationContext:
    notifications: Stream[Notification]
    unread_count: int

class NotificationsLiveView(LiveView[NotificationContext]):
    async def mount(self, socket, session):
        notifs = Stream[Notification](
            dom_id=lambda n: f"notif-{n.id}"
        )

        # Load unread only (don't store read notifications)
        unread = await get_unread_notifications(socket.session["user_id"])
        notifs.extend(unread)

        socket.context = NotificationContext(
            notifications=notifs,
            unread_count=len(unread)
        )

        # Subscribe to user's notification channel
        await socket.subscribe(f"user:{socket.session['user_id']}")

    async def handle_info(self, event, socket):
        if event["type"] == "new_notification":
            # Real-time notification appears at top
            socket.context.notifications.prepend(event["notification"])
            socket.context.unread_count += 1

    async def handle_event(self, event, payload, socket):
        if event == "mark_read":
            # Remove from stream
            socket.context.notifications.remove_by_id(
                f"notif-{payload['id']}"
            )
            socket.context.unread_count -= 1
```

## Advanced Features

### Stream Limits

Control maximum items displayed:

```python
# Keep last 100 messages
stream.insert(new_msg, at=0, limit=100)

# Client automatically removes oldest items
```

**Use cases:**
- Chat history (keep last N messages)
- Activity feeds (show recent only)
- Leaderboards (top 10)

### Update-Only Mode

Prevent new items from being added:

```python
stream.insert(updated_item, update_only=True)

# If item exists: update it
# If item doesn't exist: ignore (don't insert)
```

**Use cases:**
- Live score updates
- Status indicators
- Presence tracking

### Stream Reset

Replace entire stream:

```python
socket.context.messages.reset([msg1, msg2, msg3])

# Client clears container and shows new items
```

**Use cases:**
- Switching channels
- Clearing search results
- Filtering changes

## Testing Considerations

### Unit Testing Streams

```python
def test_stream_operations():
    stream = Stream[Message](dom_id=lambda m: f"msg-{m.id}")

    # Test prepend
    msg1 = Message(id=1, text="Hello")
    stream.prepend(msg1)

    items = list(stream)
    assert items == [("msg-1", msg1)]

    # Test operations accumulation
    inserts, deletes, reset = stream.consume_operations()
    assert len(inserts) == 1
    assert inserts[0][0] == "msg-1"  # dom_id
    assert inserts[0][1] == 0         # at position
```

### Integration Testing

```python
async def test_chat_flow():
    socket = await mount_view(ChatLiveView)

    # Initial render has messages
    render = await socket.render()
    assert len(socket.context.messages._initial_items) == 50

    # Send new message
    await socket.handle_event("send_message", {"text": "Hi"})

    # Check diff only has new message
    diff = socket.diff(render)
    assert "stream" in diff
    operations = diff["stream"][0]
    assert len(operations[1]) == 1  # One insert operation
```

## Performance Characteristics

### Memory Usage

**Traditional list:**
```python
messages: list[Message]  # O(n) - stores all items
```

**Stream:**
```python
messages: Stream[Message]  # O(k) - only pending operations
```

Where `k` = number of operations since last render (typically 1-10)

### Bandwidth Usage

**Adding 1 item to 1000-item list:**

| Approach | Data Sent | Size |
|----------|-----------|------|
| Traditional list | 1000 items × ~200 bytes | ~200 KB |
| Stream | 1 item × 200 bytes + metadata | ~0.3 KB |

**667x reduction** for incremental updates!

### CPU/Rendering

**Traditional:**
- Server: Re-render 1000 items = O(n)
- Client: Parse 1000 items = O(n)
- DOM: Update 1000 elements = O(n)

**Streams:**
- Server: Render 1 item = O(1)
- Client: Parse 1 item = O(1)
- DOM: Insert 1 element = O(1)

## Future Enhancements

### Potential Improvements

1. **Pagination helpers**
   ```python
   stream.paginate(page=2, per_page=20)
   ```

2. **Ordering support**
   ```python
   stream.insert(item, order_by=lambda m: m.timestamp)
   ```

3. **Filtering**
   ```python
   stream.filter(lambda m: m.user_id == current_user)
   ```

4. **Temporary items**
   ```python
   stream.insert_temporary(item, duration=5.0)  # Auto-remove after 5s
   ```

5. **Optimistic updates**
   ```python
   stream.insert_optimistic(item, ref="temp-123")
   # Later: confirm or rollback
   ```

## Conclusion

The PyView Streams API demonstrates how to adapt Phoenix LiveView concepts to Python while:
- Maintaining the core benefits (memory efficiency, minimal diffs)
- Embracing Python idioms (type safety, OOP, explicit is better than implicit)
- Providing excellent developer experience (IDE support, clear APIs)

The result is an API that feels natural to Python developers while delivering the same performance characteristics as Phoenix LiveView streams.

## References

- Phoenix LiveView Streams Documentation: https://hexdocs.pm/phoenix_live_view/Phoenix.LiveView.html#stream/4
- PyView Implementation: `/pyview/stream.py`
- Example Application: `/examples/views/streams/`
