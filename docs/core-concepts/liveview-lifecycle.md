# LiveView Lifecycle

Understanding the LiveView lifecycle is essential for building effective PyView applications. This guide explains each phase, when it occurs, and how to use it effectively.

## Overview

A PyView application follows a predictable lifecycle from initial page load to user interaction:

```
1. HTTP Request    → mount() → handle_params() → render()
2. WebSocket Join  → mount() → handle_params() → render()
3. User Events     → handle_event() → render() → DOM diff
4. Navigation      → handle_params() → render() → DOM diff
5. Real-time       → handle_info() → render() → DOM diff
6. Disconnect      → disconnect() → cleanup
```

## Phase 1: HTTP Request (Initial Load)

When a user first visits your LiveView URL, PyView renders the initial HTML:

1. `mount(socket, session)` is called with an **unconnected socket**
2. `handle_params(url, params, socket)` processes URL and/or path parameters
3. Template is rendered to complete HTML
4. HTML page is returned with LiveView JavaScript client

At this point, the user sees the initial page but real-time features aren't available yet.

## Phase 2: WebSocket Connection

After the page loads, the JavaScript client establishes a WebSocket connection:

1. `mount(socket, session)` is called again with a **connected socket**
2. `handle_params(url, params, socket)` is called again
3. Template is rendered and sent to client for future diffing

This is why `mount()` often checks `is_connected(socket)`—you may want to skip expensive setup during the initial HTTP render and only run it once the WebSocket connects. See [Socket and Context](socket-and-context.md#checking-connection-status) for details on which methods are available in each state.

## Phase 3: Event Handling

When users interact with your UI (clicks, form submissions, etc.):

1. `handle_event(event, payload, socket)` processes the interaction
2. Template is re-rendered
3. PyView calculates the diff from the previous render
4. Only changes in the render tree are sent to the client

## Phase 4: Navigation

When the URL changes within the same LiveView (via `push_patch()` or browser navigation):

1. `handle_params(url, params, socket)` is called with new parameters
2. Template is re-rendered and diffed

**Note:** `mount()` is NOT called again—state persists across navigation within the same LiveView.

## Phase 5: Real-time Updates

For scheduled events (`schedule_info`) or pub/sub messages:

1. `handle_info(event, socket)` processes the event
2. Template is re-rendered and diffed
3. Updates are pushed to the client

This happens without any user interaction—useful for live dashboards, chat, notifications, etc.

## Phase 6: Disconnection

When the WebSocket connection closes (user navigates away, network issues, etc.):

1. Scheduled jobs are automatically cancelled
2. Pub/sub subscriptions are cleaned up
3. File upload resources are released
4. `disconnect(socket)` is called for your custom cleanup (optional)

## Lifecycle Methods in Detail

### `mount(socket, session)`

**Called:** 
- Initially during HTTP request (unconnected socket)
- Again during WebSocket connection (connected socket)
- Again when navigating between different LiveViews

```python
async def mount(self, socket: LiveViewSocket[Context], session):
    # Initialize your state
    socket.context = {"count": 0, "user_id": session.get("user_id")}
    socket.live_title = "My App"    
    
    # Connected-only operations
    if is_connected(socket):
        await socket.subscribe("user_updates")
        socket.schedule_info(InfoEvent("refresh_data"), 30)
```

**Use for:**
- Initializing state
- Setting up subscriptions (connected only)
- Scheduling periodic updates (connected only)
- Loading data from databases

### `handle_params(url, params, socket)`

**Called:**
- After `mount()` during initial load
- When URL parameters change (navigation)
- When using `push_patch()` or `push_navigate()`

```python
async def handle_params(self, url, params, socket: LiveViewSocket[Context]):
    # Handle query parameters: /users?page=2&sort=name
    page = int(params.get("page", ["1"])[0])
    sort = params.get("sort", ["id"])[0]
    
    # Handle path parameters: /users/{user_id}
    user_id = params.get("user_id")
    
    # Update state based on URL
    socket.context.update({
        "current_page": page,
        "sort_by": sort,
        "users": await load_users(page=page, sort=sort)
    })
```

**Use for:**
- Handling URL or path parameters
- Loading data based on URL
- Pagination, filtering, sorting

### `handle_event(event, payload, socket)`

**Called:** When users interact with your UI

```python
async def handle_event(self, event, payload, socket: ConnectedLiveViewSocket[Context]):
    if event == "save_user":
        # payload contains form data
        user_data = {
            "name": payload.get("name", [""])[0],
            "email": payload.get("email", [""])[0]
        }
        
        # Validate and save
        if await save_user(user_data):
            socket.context["message"] = "User saved successfully"
        else:
            socket.context["error"] = "Failed to save user"
    
    elif event == "delete_user":
        user_id = payload["user_id"]
        await delete_user(user_id)
        socket.context["users"] = await load_users()
```

**Use for:**
- Button clicks
- Form submissions
- Custom user interactions
- Real-time features

### `handle_info(event, socket)`

**Called:** For scheduled events and pub/sub messages

```python
async def handle_info(self, event: InfoEvent, socket: ConnectedLiveViewSocket[Context]):
    if event.name == "refresh_data":
        # Scheduled refresh
        socket.context["data"] = await fetch_latest_data()
        socket.context["last_update"] = datetime.now()
        
    elif event.name == "user_updated":
        # Pub/sub message
        updated_user = event.payload["user"]
        # Update user in current list
        for i, user in enumerate(socket.context["users"]):
            if user["id"] == updated_user["id"]:
                socket.context["users"][i] = updated_user
                break
```

**Use for:**
- Scheduled/periodic updates
- Real-time notifications
- External system events
- Background job results

### `disconnect(socket)` (optional)

**Called:** When WebSocket connection closes. Many LiveViews don't need to implement this—PyView automatically cleans up scheduled jobs, subscriptions, and uploads.

```python
async def disconnect(self, socket: ConnectedLiveViewSocket[Context]):
    # Custom cleanup
    user_id = socket.context.get("user_id")
    if user_id:
        await mark_user_offline(user_id)
        await broadcast_user_left(user_id)
    
    # Close database connections, etc.
    await cleanup_resources()
```

**Use for:**
- Custom cleanup logic
- Updating presence/status
- Closing database connections
- Logging user activity
