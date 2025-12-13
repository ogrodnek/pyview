# PyView Streams Usage Guide

This guide shows how to use streams in pyview for efficient rendering of large collections.

## Overview

Streams are a feature ported from Phoenix LiveView that allows efficient rendering of large lists without keeping all items in server memory. Key benefits:

- **Efficient memory usage**: Server only tracks operations, not all items
- **Minimal wire traffic**: Only changed items are sent to the client
- **Smooth updates**: Items are inserted/deleted without re-rendering the entire list

## Basic Usage

### 1. Import Stream

```python
from pyview import Stream
```

### 2. Create a Stream in Your LiveView

```python
from dataclasses import dataclass
from pyview import LiveView, Stream

@dataclass
class Message:
    id: int
    text: str
    author: str

@dataclass
class ChatContext:
    messages: Stream[Message]

class ChatLive(LiveView[ChatContext]):
    async def mount(self, socket, session):
        # Load initial messages
        messages = await load_messages()

        # Create stream with initial items
        socket.context = ChatContext(
            messages=Stream(messages, name="messages")
        )
```

### 3. Render the Stream in Your Template (Ibis)

```html
<div id="messages" phx-update="stream">
    {% for dom_id, msg in messages %}
    <div id="{{ dom_id }}" class="message">
        <strong>{{ msg.author }}</strong>: {{ msg.text }}
    </div>
    {% endfor %}
</div>
```

**Important requirements:**
- Container must have `phx-update="stream"` attribute
- Container must have a unique `id`
- Each item must use `dom_id` for its `id` attribute
- Iterate with `for dom_id, item in stream`

### 4. Handle Events to Modify the Stream

```python
async def handle_event(self, event, payload, socket):
    if event == "send_message":
        # Create new message
        msg = Message(
            id=generate_id(),
            text=payload["text"],
            author=payload["author"]
        )
        # Insert at end (append)
        socket.context.messages.insert(msg)

    elif event == "delete_message":
        # Delete by DOM ID
        socket.context.messages.delete_by_id(f"messages-{payload['id']}")
```

## Stream Operations

### Insert (Append)

Add an item to the end of the stream:

```python
stream.insert(item)
# or explicitly
stream.insert(item, at=-1)
```

### Insert (Prepend)

Add an item to the beginning:

```python
stream.insert(item, at=0)
```

### Insert at Index

Add an item at a specific position:

```python
stream.insert(item, at=5)  # Insert at index 5
```

### Insert Many

Add multiple items at once:

```python
stream.insert_many([item1, item2, item3])
stream.insert_many(items, at=0)  # Prepend all
```

### Delete by Item

Remove an item (uses dom_id function to find it):

```python
stream.delete(item)
```

### Delete by DOM ID

Remove an item by its DOM ID:

```python
stream.delete_by_id("messages-123")
```

### Reset

> **Note:** Reset is not yet fully implemented. The API exists but the reset flag is not sent over the wire in the current version.

Clear all items and optionally replace with new ones:

```python
# Clear everything
stream.reset()

# Replace with new items
stream.reset(new_items)
```

### Update Existing Item

To update an item's content, insert it with the same ID - it will update in place:

```python
updated_msg = Message(id=123, text="Updated text", author="Alice")
stream.insert(updated_msg)  # Updates existing item with id=123
```

### Update Only Mode

> **Note:** Update only mode is not yet implemented. The API exists but the flag is not sent over the wire in the current version.

Only update items that already exist (ignore if not present):

```python
stream.insert(item, update_only=True)
```

### With Limit

> **Note:** Limit is not yet implemented. The API exists but the limit value is not sent over the wire in the current version.

Limit the number of items (client enforces this):

```python
# Keep max 100 items, remove from beginning when exceeded
stream.insert(item, limit=100)

# Keep max 100 items, remove from end when exceeded
stream.insert(item, at=0, limit=-100)
```

## DOM ID Generation

By default, streams generate DOM IDs using the item's `id` attribute:

```python
@dataclass
class User:
    id: int
    name: str

stream = Stream([User(1, "Alice")], name="users")
# DOM ID will be "users-1"
```

### Custom DOM ID Function

For items without an `id` attribute or custom ID format:

```python
stream = Stream(
    items,
    name="items",
    dom_id=lambda item: f"item-{item.uuid}"
)
```

### Dict Items

For dict items, the `id` key is used:

```python
items = [{"id": 1, "name": "Item 1"}]
stream = Stream(items, name="items")
# DOM ID will be "items-1"
```

## T-String Templates (Python 3.14+)

For T-string templates, use the `stream_for` helper:

```python
from pyview.template.live_view_template import stream_for

def template(self, assigns, meta):
    return t'''
    <div id="messages" phx-update="stream">
        {stream_for(assigns.messages, lambda dom_id, msg:
            t'<div id="{dom_id}">{msg.text}</div>'
        )}
    </div>
    '''
```

## Complete Example

```python
from dataclasses import dataclass
from pyview import LiveView, Stream

@dataclass
class Todo:
    id: int
    text: str
    completed: bool = False

@dataclass
class TodoContext:
    todos: Stream[Todo]
    next_id: int = 1

class TodoLive(LiveView[TodoContext]):
    async def mount(self, socket, session):
        socket.context = TodoContext(
            todos=Stream(name="todos")
        )

    async def handle_event(self, event, payload, socket):
        ctx = socket.context

        if event == "add":
            todo = Todo(id=ctx.next_id, text=payload["text"])
            ctx.todos.insert(todo, at=0)  # Prepend new todos
            ctx.next_id += 1

        elif event == "toggle":
            todo_id = int(payload["id"])
            # In a real app, you'd fetch and update the todo
            updated = Todo(id=todo_id, text="...", completed=True)
            ctx.todos.insert(updated)  # Updates in place

        elif event == "delete":
            ctx.todos.delete_by_id(f"todos-{payload['id']}")

        elif event == "clear_completed":
            # Reset with only incomplete todos
            incomplete = [t for t in get_all_todos() if not t.completed]
            ctx.todos.reset(incomplete)
```

Template:

```html
<div id="todos" phx-update="stream">
    {% for dom_id, todo in todos %}
    <div id="{{ dom_id }}" class="todo {% if todo.completed %}completed{% endif %}">
        <input type="checkbox"
               {% if todo.completed %}checked{% endif %}
               phx-click="toggle"
               phx-value-id="{{ todo.id }}">
        <span>{{ todo.text }}</span>
        <button phx-click="delete" phx-value-id="{{ todo.id }}">×</button>
    </div>
    {% endfor %}
</div>

<form phx-submit="add">
    <input type="text" name="text" placeholder="New todo...">
    <button type="submit">Add</button>
</form>

<button phx-click="clear_completed">Clear Completed</button>
```

## Important Notes

1. **Stream items don't persist on server**: After rendering, the stream clears its pending items. The client DOM is the source of truth.

2. **Updates are position-independent**: When you insert an item that already exists (same DOM ID), it updates in place regardless of the `at` parameter.

3. **Order matters for multiple operations**: Operations are applied in the order they're called within a single event handler.

4. **phx-update="stream" is required**: The container element must have this attribute for the client to handle stream updates correctly.

5. **Each item needs a unique id**: The DOM ID must be unique within the stream container.

## Troubleshooting

### Items not appearing
- Check that the container has `phx-update="stream"`
- Verify each item element has `id="{{ dom_id }}"`
- Ensure you're iterating with `for dom_id, item in stream`

### Items duplicating
- Make sure DOM IDs are unique
- Check that you're not inserting items with duplicate IDs
