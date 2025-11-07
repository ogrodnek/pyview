# Phoenix LiveView Streams in PyView

PyView now supports Phoenix LiveView-style **Streams** for efficient handling of large collections.

## What are Streams?

Streams allow you to handle large, dynamic collections without keeping the full list in server memory. Instead of sending the entire list on every update, only the **operations** (inserts, deletes) are sent to the client.

### Benefits

- ✅ **Minimal data over the wire** - Only send what changed
- ✅ **No server memory overhead** - Don't store full collections
- ✅ **Client-side state** - Browser maintains the list
- ✅ **Type-safe** - Full typing support with Python generics
- ✅ **Perfect for**: Infinite scroll, live feeds, chat messages, real-time dashboards

## Quick Start

### 1. Define Your Data Model

```python
from dataclasses import dataclass
from pyview import Stream

@dataclass
class Message:
    id: int
    text: str
    user: str
```

### 2. Add Stream to Context

```python
from pyview import LiveView, LiveViewSocket, Stream

@dataclass
class ChatContext:
    messages: Stream[Message]  # Type-safe!

class ChatView(LiveView[ChatContext]):
    async def mount(self, socket: LiveViewSocket[ChatContext], session):
        socket.context = ChatContext(
            messages=Stream(dom_id=lambda m: f"msg-{m.id}")
        )

        # Load initial messages
        initial_messages = await load_messages()
        socket.context.messages.extend(initial_messages)
```

### 3. Set Up Template

**Important**: Your template must:
1. Add `phx-update="stream"` to the container
2. Add `data-phx-stream="{{ context.messages.ref }}"` to link the stream
3. Iterate with `{% for dom_id, msg in context.messages %}`
4. Add `id="{{ dom_id }}"` to each item

```html
<div id="messages"
     phx-update="stream"
     data-phx-stream="{{ context.messages.ref }}">
  {% for dom_id, msg in context.messages %}
    <div id="{{ dom_id }}" class="message">
      <strong>{{ msg.user }}:</strong> {{ msg.text }}
      <button phx-click="delete" phx-value-id="{{ msg.id }}">×</button>
    </div>
  {% endfor %}
</div>
```

### 4. Perform Stream Operations

```python
async def handle_event(self, event, payload, socket):
    if event == "new_message":
        new_msg = Message(id=gen_id(), text=payload["text"], user="Alice")

        # Prepend to top (most recent first)
        socket.context.messages.prepend(new_msg)

    elif event == "delete":
        msg_id = payload["id"]
        socket.context.messages.remove_by_id(f"msg-{msg_id}")
```

## Stream API Reference

### Creating a Stream

```python
Stream[T](
    dom_id: str | Callable[[T], str] = "id",
    name: Optional[str] = None
)
```

**Parameters:**
- `dom_id`: Either an attribute name (e.g., `"id"`) or a function that generates a unique DOM ID
- `name`: Optional name (automatically set by socket)

**Examples:**
```python
# Using attribute name
Stream[User](dom_id="id")  # Uses user.id

# Using custom function
Stream[User](dom_id=lambda u: f"user-{u.id}")

# Using dict keys
Stream[dict](dom_id="id")  # Uses item["id"]
```

### Stream Operations

#### `prepend(item, limit=None)`
Add item to the beginning.

```python
socket.context.messages.prepend(new_message)
socket.context.messages.prepend(new_message, limit=50)  # Keep max 50
```

#### `append(item, limit=None)`
Add item to the end.

```python
socket.context.messages.append(new_message)
```

#### `insert(item, at=-1, limit=None, update_only=False)`
Insert item at a specific position.

```python
# Append (default)
socket.context.messages.insert(msg, at=-1)

# Prepend
socket.context.messages.insert(msg, at=0)

# Insert at specific index
socket.context.messages.insert(msg, at=5)

# Update existing item only
socket.context.messages.insert(msg, update_only=True)
```

**Parameters:**
- `at`: Position to insert (`-1` = end, `0` = beginning, or specific index)
- `limit`: Max items to keep on client (`-10` = first 10, `10` = last 10)
- `update_only`: If `True`, only updates existing items (doesn't insert new)

#### `extend(items, at=-1)`
Bulk insert multiple items.

```python
messages = await load_messages()
socket.context.messages.extend(messages)

# Prepend multiple
socket.context.messages.extend(new_messages, at=0)
```

#### `update(item)`
Update an existing item.

```python
updated_msg = Message(id=123, text="Updated!", user="Bob")
socket.context.messages.update(updated_msg)
```

Equivalent to `insert(item, update_only=True)`.

#### `remove(item)`
Remove an item.

```python
socket.context.messages.remove(old_message)
```

#### `remove_by_id(dom_id)`
Remove by DOM ID without needing the full item.

```python
socket.context.messages.remove_by_id("msg-123")
```

#### `reset(items=None)`
Clear all items and optionally replace with new ones.

```python
# Clear everything
socket.context.messages.reset()

# Clear and replace
new_messages = await reload_messages()
socket.context.messages.reset(new_messages)
```

### Method Chaining

All operations return `self` for chaining:

```python
socket.context.messages \
    .remove_by_id("msg-1") \
    .prepend(new_msg) \
    .prepend(another_msg)
```

## Complete Example

See `examples/views/streams/` for a full working example with:
- Prepend/append operations
- Bulk inserts
- Individual deletes
- Stream reset
- UI demonstrating minimal diffs

To run the example:
```bash
cd examples
python app.py
# Visit http://localhost:8000/streams
```

Open browser DevTools → Network → WS to see the minimal diffs being sent!

## How It Works

### Wire Protocol

When you perform stream operations, PyView sends a minimal diff using **keyed comprehensions**:

```json
{
  "2": {
    "s": ["<div id=\"", "\" class=\"message\">...</div>"],
    "k": [
      ["msg-6", ["6", "Hello!", "Alice"]]
    ]
  },
  "stream": [
    [
      "phx-FmgPyOA",              // Stream ref (matches data-phx-stream)
      [
        ["msg-6", 0, -1, false]   // [dom_id, at, limit, update_only]
      ],
      [],                         // deleteIds
      false                       // reset
    ]
  ]
}
```

**Key points:**
1. Stream items use **keyed comprehensions** with the `"k"` key
2. Format: `["key", [dynamic_values]]` - key is the DOM ID
3. Stream metadata goes in `"stream"` key with positioning info
4. Only new/changed items are sent in the comprehension
5. Client uses keys (DOM IDs) to identify and position items

**Keyed vs Regular Comprehensions:**
- **Regular** (non-streams): `{"d": [[val1, val2], ...]}` - indexed by position
- **Keyed** (streams): `{"k": [["key1", [val1]], ["key2", [val2]]]}` - indexed by key
- Keyed comprehensions allow the client to track items by ID, not position

### JavaScript Client Support

PyView uses the official Phoenix LiveView JavaScript client (`phoenix_live_view`).

**Version requirement:** `>= 0.18.3` (streams introduced in 0.18.3)

Your current `package.json` has:
```json
"phoenix_live_view": "^0.18.11"  ✅ Streams supported!
```

No JavaScript changes needed - the client already supports streams!

## Comparison: Regular Lists vs Streams

### Regular List (Full Re-send)

```python
# Context
@dataclass
class Context:
    messages: list[Message]  # Regular list

# On update - entire list re-rendered and sent
socket.context.messages.append(new_msg)
# Wire: Sends ALL messages' HTML
```

### Stream (Minimal Diff)

```python
# Context
@dataclass
class Context:
    messages: Stream[Message]  # Stream

# On update - only the operation sent
socket.context.messages.append(new_msg)
# Wire: Sends ONLY new message HTML + operation metadata
```

### When to Use Streams

Use streams when:
- ✅ List can grow large (>50 items)
- ✅ Frequent insertions/deletions
- ✅ Real-time updates (chat, feeds, notifications)
- ✅ Infinite scroll / pagination
- ✅ Don't need the full list on the server

Use regular lists when:
- ✅ Small, static lists (<20 items)
- ✅ Need to iterate/filter server-side
- ✅ Simpler mental model needed

## Advanced Patterns

### Infinite Scroll

```python
async def handle_event(self, event, payload, socket):
    if event == "load_more":
        older_messages = await load_messages(before=payload["before_id"])
        socket.context.messages.extend(older_messages, at=-1)
```

### Real-time Updates

```python
async def handle_info(self, event, socket):
    if event.topic == "new_message":
        socket.context.messages.prepend(event.message)
```

### Update and Move

To update an item AND change its position:

```python
# Delete then re-insert at new position
socket.context.messages.remove(item)
socket.context.messages.insert(item, at=0)
```

### Limit Collection Size

```python
# Keep only last 50 messages
socket.context.messages.prepend(new_msg, limit=50)

# Keep only first 20 messages
socket.context.messages.prepend(new_msg, limit=-20)
```

## Type Safety

Streams are fully typed using Python generics:

```python
@dataclass
class User:
    id: int
    name: str

@dataclass
class Context:
    users: Stream[User]  # Type checker knows this is Stream[User]

# IDE autocomplete works!
async def handle_event(self, event, payload, socket):
    new_user = User(id=1, name="Alice")
    socket.context.users.prepend(new_user)  # ✅ Type-safe

    # IDE knows 'users' is Stream[User] and has .prepend() method
    # IDE knows 'new_user' must be a User instance
```

## Troubleshooting

### Items not appearing

**Check:**
1. Container has `phx-update="stream"`
2. Container has `data-phx-stream="{{ context.messages.ref }}"`
3. Each item has `id="{{ dom_id }}"`
4. Template iterates with `{% for dom_id, item in context.messages %}`

### Items appearing but not updating

**Check:**
- DOM IDs are unique and stable (don't change between renders)
- Using `update()` or `insert(..., update_only=True)` for updates

### Items duplicating

**Check:**
- Not calling both `extend()` in mount and insert operations
- DOM IDs are truly unique

### Stream not in context error

**Check:**
- Stream initialized in `mount()` before any operations
- Stream assigned to `socket.context` field

## Migration from Regular Lists

```python
# Before
@dataclass
class Context:
    messages: list[Message]

socket.context.messages.append(new_msg)

# Template
{% for msg in context.messages %}
  <div>{{ msg.text }}</div>
{% endfor %}

# After
@dataclass
class Context:
    messages: Stream[Message]

socket.context = Context(
    messages=Stream(dom_id=lambda m: f"msg-{m.id}")
)
socket.context.messages.append(new_msg)

# Template
<div id="messages" phx-update="stream" data-phx-stream="{{ context.messages.ref }}">
  {% for dom_id, msg in context.messages %}
    <div id="{{ dom_id }}">{{ msg.text }}</div>
  {% endfor %}
</div>
```

## Credits

Streams implementation inspired by [Phoenix LiveView Streams](https://hexdocs.pm/phoenix_live_view/Phoenix.LiveView.html#stream/4) by Chris McCord and the Phoenix team.
