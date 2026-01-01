---
title: Event Handling
sidebar:
  order: 3
---

# Event Handling

Event handling is at the core of PyView's interactivity. This guide covers how to handle user interactions, process form data, and manage different types of events in your LiveView applications.

## Event Types

PyView supports several types of events for different user interactions:

### User Interface Events

Events triggered by user interactions with your HTML elements:

- **`phx-click`** - Button clicks and element interactions
- **`phx-change`** - Input field changes (text, select, checkbox, etc.)
- **`phx-submit`** - Form submissions
- **`phx-blur`** - Element loses focus
- **`phx-focus`** - Element gains focus
- **`phx-keydown`** - Key press events
- **`phx-keyup`** - Key release events

### Server Events

Events generated on the server side:

- **InfoEvent** - Scheduled events, pub/sub messages, and server-side triggers

### JavaScript Hook Events

Events sent from [JavaScript hooks](../features/javascript-hooks.md) using `this.pushEvent()`:

- Custom events with arbitrary payloads from client-side code
- Useful for integrating third-party libraries, drag-and-drop, maps, etc.

## Basic Event Handling

### Standard Method

The basic way to handle events is through the `handle_event()` method. PyView automatically extracts and converts parameters from the event payload based on your method signature:

```python
from pyview import LiveView, LiveViewSocket
from typing import TypedDict

class CounterContext(TypedDict):
    count: int

class CounterLiveView(LiveView[CounterContext]):
    async def mount(self, socket: LiveViewSocket[CounterContext], session):
        socket.context = {"count": 0}

    async def handle_event(self, event: str, socket: LiveViewSocket[CounterContext]):
        if event == "increment":
            socket.context["count"] += 1
        elif event == "decrement":
            socket.context["count"] -= 1
        elif event == "reset":
            socket.context["count"] = 0
```

Template:
```html
<div>
    <h1>Count: {{count}}</h1>
    <button phx-click="increment">+</button>
    <button phx-click="decrement">-</button>
    <button phx-click="reset">Reset</button>
</div>
```

### Decorator-Based Event Handling

For better organization, use the `@event` decorator with `BaseEventHandler`:

```python
from pyview import LiveView, LiveViewSocket
from pyview.events import BaseEventHandler, event

class CounterLiveView(BaseEventHandler, LiveView[CounterContext]):
    async def mount(self, socket: LiveViewSocket[CounterContext], session):
        socket.context = {"count": 0}

    @event("increment")
    async def handle_increment(self, socket: LiveViewSocket[CounterContext], amount: int = 1):
        socket.context["count"] += amount

    @event("decrement")
    async def handle_decrement(self, socket: LiveViewSocket[CounterContext], amount: int = 1):
        socket.context["count"] -= amount

    @event("reset")
    async def handle_reset(self, socket: LiveViewSocket[CounterContext]):
        socket.context["count"] = 0
```

> **Note:** Method names are arbitrary when using `@event("name")`. The `handle_` prefix shown here is a convention for readability, not a requirement.

The `BaseEventHandler` will automatically route events to the correct method.

<details>
<summary>Legacy style (still supported)</summary>

```python
@event("increment")
async def handle_increment(self, event: str, payload: dict, socket: LiveViewSocket[CounterContext]):
    amount = int(payload.get("amount", [1])[0])
    socket.context["count"] += amount
```
</details>

### AutoEventDispatch

`AutoEventDispatch` extends `BaseEventHandler` with an additional feature: methods decorated with `@event` can be referenced directly in templates, automatically converting to their event name string.

This is especially useful with [T-String Templates](../templating/t-string-templates.md), where you can reference methods directly:

```python
from pyview import LiveView, LiveViewSocket
from pyview.events import AutoEventDispatch, event
from pyview.template import TemplateView

class CounterLiveView(AutoEventDispatch, TemplateView, LiveView[CounterContext]):
    async def mount(self, socket: LiveViewSocket[CounterContext], session):
        socket.context = {"count": 0}

    @event
    async def increment(self, socket):
        socket.context["count"] += 1

    @event
    async def decrement(self, socket):
        socket.context["count"] -= 1

    def template(self, assigns, meta):
        count = assigns["count"]
        return t"""<div>
            <h1>{count}</h1>
            <button phx-click="{self.decrement}">-</button>
            <button phx-click="{self.increment}">+</button>
        </div>"""
```

Notice `phx-click="{self.increment}"` - the method reference automatically converts to the event name string `"increment"`. This eliminates string duplication and enables IDE navigation from template to handler.

**Key features:**
- Methods stringify to their event name when used in templates
- Works with both `@event` (uses method name) and `@event("custom-name")`
- Methods remain callable for direct invocation in tests

**Using custom event names:**

```python
@event("user-clicked-save")
async def handle_save(self, socket):
    # self.handle_save stringifies to "user-clicked-save"
    pass
```

## Event Payloads

Event payloads contain different data depending on the event type and source element.

### Button Click Events

Simple click events typically have minimal payload:

```python
# Template: <button phx-click="save">Save</button>
async def handle_event(self, event: str, socket):
    if event == "save":
        await save_data(socket.context["data"])
```

### Button Click with Values

Use `phx-value-*` attributes to pass data. PyView automatically extracts and converts these values based on your method signature:

```html
<!-- Template -->
<button phx-click="delete_user" phx-value-user-id="{{user.id}}">Delete</button>
<button phx-click="set_status" phx-value-status="active" phx-value-user-id="{{user.id}}">Activate</button>
```

```python
# New style - typed parameters are automatically extracted from phx-value-* attributes
async def handle_event(self, event: str, socket, user_id: str, status: str = "active"):
    if event == "delete_user":
        await delete_user(user_id)
    elif event == "set_status":
        await update_user_status(user_id, status)
```

<details>
<summary>Legacy style (still supported)</summary>

```python
async def handle_event(self, event, payload, socket):
    if event == "delete_user":
        user_id = payload["user_id"]  # From phx-value-user-id
        await delete_user(user_id)
    elif event == "set_status":
        user_id = payload["user_id"]    # From phx-value-user-id
        status = payload["status"]      # From phx-value-status
        await update_user_status(user_id, status)
```
</details>

### Form Change Events

Form inputs send their current value. With typed parameters, values are automatically extracted and converted:

```html
<!-- Template -->
<input type="text" phx-change="search" name="query" value="{{search_query}}">
<select phx-change="filter_category" name="category">
    <option value="all">All Categories</option>
    <option value="books">Books</option>
    <option value="movies">Movies</option>
</select>
```

```python
# New style - typed parameters are automatically extracted from form fields
async def handle_event(self, event: str, socket, query: str = "", category: str = "all"):
    if event == "search":
        socket.context["search_query"] = query
        socket.context["results"] = await search_items(query)
    elif event == "filter_category":
        socket.context["selected_category"] = category
        socket.context["items"] = await filter_by_category(category)
```

<details>
<summary>Legacy style (still supported)</summary>

```python
async def handle_event(self, event, payload, socket):
    if event == "search":
        # payload: {"query": ["user typed text"]}
        query = payload.get("query", [""])[0]
        socket.context["search_query"] = query
        socket.context["results"] = await search_items(query)
    elif event == "filter_category":
        # payload: {"category": ["books"]}
        category = payload.get("category", ["all"])[0]
        socket.context["selected_category"] = category
        socket.context["items"] = await filter_by_category(category)
```

**Note:** Form values in the raw payload are always lists (e.g., `["value"]`) to support multi-select elements. Typed parameter binding handles this automatically.
</details>

### Form Submission Events

Form submissions include all form fields. Use typed parameters or dataclasses to cleanly extract form data:

```html
<!-- Template -->
<form phx-submit="create_user" phx-change="validate">
    <input type="text" name="name" value="{{changeset.attrs.name}}">
    <input type="email" name="email" value="{{changeset.attrs.email}}">
    <select name="role">
        <option value="user">User</option>
        <option value="admin">Admin</option>
    </select>
    <button type="submit">Create User</button>
</form>
```

```python
from dataclasses import dataclass

@dataclass
class UserForm:
    name: str
    email: str
    role: str = "user"

# New style - use a dataclass to group form fields
async def handle_event(self, event: str, socket, user: UserForm):
    if event == "create_user":
        try:
            created = await create_user({"name": user.name, "email": user.email, "role": user.role})
            socket.context["users"].append(created)
            socket.context["success"] = "User created successfully"
        except ValidationError as e:
            socket.context["error"] = str(e)
    elif event == "validate":
        errors = validate_user_data(user)
        socket.context["errors"] = errors
```

Or use individual typed parameters:

```python
async def handle_event(self, event: str, socket, name: str, email: str, role: str = "user"):
    if event == "create_user":
        await create_user({"name": name, "email": email, "role": role})
```

<details>
<summary>Legacy style (still supported)</summary>

```python
async def handle_event(self, event, payload, socket):
    if event == "create_user":
        # payload: {
        #     "name": ["John Doe"],
        #     "email": ["john@example.com"],
        #     "role": ["user"]
        # }
        user_data = {
            "name": payload.get("name", [""])[0],
            "email": payload.get("email", [""])[0],
            "role": payload.get("role", ["user"])[0]
        }
        try:
            user = await create_user(user_data)
            socket.context["users"].append(user)
        except ValidationError as e:
            socket.context["error"] = str(e)
```
</details>

## Advanced Event Handling

### Event Parameters and Values

Extract specific data from events using `phx-value-*` attributes. Typed parameters handle the extraction and conversion automatically:

```html
<!-- Multi-parameter events -->
<button phx-click="move_item"
        phx-value-item-id="{{item.id}}"
        phx-value-from-list="todo"
        phx-value-to-list="done"
        phx-value-position="0">
    Mark Done
</button>
```

```python
@event("move_item")
async def handle_move_item(self, socket, item_id: str, from_list: str, to_list: str, position: int):
    await move_item(item_id, from_list, to_list, position)
    socket.context["items"] = await reload_items()
```

<details>
<summary>Legacy style (still supported)</summary>

```python
@event("move_item")
async def handle_move_item(self, event, payload, socket):
    item_id = payload["item_id"]
    from_list = payload["from_list"]
    to_list = payload["to_list"]
    position = int(payload["position"])
    await move_item(item_id, from_list, to_list, position)
```
</details>

### Custom Event Data

Send complex data using JavaScript hooks (advanced):

```html
<!-- Template with hook -->
<div id="kanban-board" phx-hook="KanbanBoard">
    <!-- Kanban board content -->
</div>
```

```javascript
// JavaScript hook
Hooks.KanbanBoard = {
    mounted() {
        // Setup drag & drop that sends custom events
        this.el.addEventListener('item-moved', (e) => {
            this.pushEvent("task-moved", {
                taskId: e.detail.taskId,
                from: e.detail.from,
                to: e.detail.to,
                order: e.detail.order
            });
        });
    }
}
```

```python
@event("task-moved")
async def handle_task_moved(self, socket, taskId: str, to: str, order: int, payload: dict):
    # Mix typed params with full payload access
    # 'from' is a Python keyword, so access it via payload
    from_list = payload["from"]
    socket.context.task_repository.move_task(taskId, from_list, to, order)
```

> **Note:** The `payload` parameter is injectable—include it in your signature to get the full payload alongside typed parameters. This is useful when payload keys conflict with Python keywords.

<details>
<summary>Legacy style (still supported)</summary>

```python
@event("task-moved")
async def handle_task_moved(self, event, payload, socket):
    task_id = payload["taskId"]
    from_list = payload["from"]
    to_list = payload["to"]
    order = payload["order"]
    socket.context.task_repository.move_task(task_id, from_list, to_list, order)
```
</details>

## Form Handling Patterns

### Input Validation

Validate on change and submission:

```python
from pyview.changesets import change_set, ChangeSet

class UserContext(TypedDict):
    changeset: ChangeSet
    users: list[dict]

class UserLiveView(LiveView[UserContext]):
    async def mount(self, socket: LiveViewSocket[UserContext], session):
        socket.context = {
            "changeset": change_set(User),
            "users": []
        }

    @event("validate")
    async def handle_validate(self, socket, payload: dict):
        # Changesets use the raw payload dict
        socket.context["changeset"].apply(payload)
        # Validation happens automatically

    @event("save_user")
    async def handle_save(self, socket, payload: dict):
        socket.context["changeset"].apply(payload)
        
        if socket.context["changeset"].valid:
            user = socket.context["changeset"].model
            await save_user(user)
            socket.context["users"].append(user)
            # Reset form
            socket.context["changeset"] = change_set(User)
        # Errors are automatically displayed in template
```

## Server-Side Events (InfoEvent)

Handle scheduled events and pub/sub messages:

```python
from pyview.events import InfoEvent, info

class ChatLiveView(BaseEventHandler, LiveView[ChatContext]):
    async def mount(self, socket: LiveViewSocket[ChatContext], session):
        socket.context = {"messages": [], "user_id": session["user_id"]}
        
        if is_connected(socket):
            # Subscribe to chat updates
            await socket.subscribe("chat_room")
            # Schedule periodic cleanup
            socket.schedule_info(InfoEvent("cleanup"), 300)  # Every 5 minutes

    @info("chat_room")
    async def handle_chat_message(self, event: InfoEvent, socket):
        # Received message from another user
        message = event.payload
        socket.context["messages"].append(message)

    @info("cleanup")
    async def handle_cleanup(self, event: InfoEvent, socket):
        # Remove old messages
        cutoff_time = datetime.now() - timedelta(hours=24)
        socket.context["messages"] = [
            msg for msg in socket.context["messages"] 
            if msg["timestamp"] > cutoff_time
        ]

    @event("send_message")
    async def handle_send_message(self, socket, text: str):
        message = {
            "user_id": socket.context["user_id"],
            "text": text,
            "timestamp": datetime.now()
        }
        # Broadcast to all chat subscribers
        await socket.broadcast("chat_room", message)
```

### Async Streams

For long-running async operations that yield multiple values (like streaming LLM responses), use `socket.stream_runner`:

```python
class ChatLiveView(BaseEventHandler, LiveView[ChatContext]):
    async def mount(self, socket, session):
        socket.context = {"response": "", "streaming": False}

    @event("ask")
    async def handle_ask(self, socket, question: str):
        socket.context["streaming"] = True
        socket.context["response"] = ""

        # Start streaming in background
        socket.stream_runner.start_stream(
            self.stream_response(question),
            on_yield=lambda chunk: InfoEvent("chunk", chunk),
            on_done=InfoEvent("done"),
            on_error=lambda e: InfoEvent("error", str(e)),
        )

    async def stream_response(self, question: str):
        """Async generator that yields response chunks."""
        async for chunk in some_llm_api.stream(question):
            yield chunk

    @info("chunk")
    async def handle_chunk(self, event: InfoEvent, socket):
        socket.context["response"] += event.payload

    @info("done")
    async def handle_done(self, event: InfoEvent, socket):
        socket.context["streaming"] = False
```

The `start_stream` method returns a task ID that can be used to cancel the stream:

```python
@event("ask")
async def handle_ask(self, socket, question: str):
    task_id = socket.stream_runner.start_stream(...)
    socket.context["current_task"] = task_id

@event("cancel")
async def handle_cancel(self, socket):
    socket.stream_runner.cancel_stream(socket.context["current_task"])
```

