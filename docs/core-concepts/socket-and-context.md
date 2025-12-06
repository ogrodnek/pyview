# Socket and Context Management

The LiveViewSocket is your connection to the client and the container for your application state.

## Socket Types

PyView uses two types of sockets depending on the connection state:

### UnconnectedSocket

Used during the initial HTTP request before WebSocket connection:

```python
class UnconnectedSocket(Generic[T]):
    context: T                           # Your application state
    live_title: Optional[str] = None     # Page title
    connected: bool = False              # Always False
    
    def allow_upload(self, upload_name: str, constraints: UploadConstraints) -> UploadConfig:
        # File upload configuration
```

**Limitations:**
- No real-time communication
- No pub/sub capabilities
- No scheduled events
- Limited to basic state management

### ConnectedLiveViewSocket

Used after WebSocket connection is established:

```python
class ConnectedLiveViewSocket(Generic[T]):
    context: T                                    # Your application state
    live_title: Optional[str] = None              # Page title
    pending_events: list[tuple[str, Any]]         # Queued client events
    upload_manager: UploadManager                 # File upload handling
    prev_rendered: Optional[dict[str, Any]]       # Previous render for diffing
    
    # Real-time capabilities
    async def subscribe(self, topic: str)         # Subscribe to pub/sub
    async def broadcast(self, topic: str, message: Any)  # Send pub/sub messages
    def schedule_info(self, event, seconds)       # Schedule recurring events
    def schedule_info_once(self, event, seconds)  # Schedule one-time events
    
    # Navigation
    async def push_patch(self, path: str, params: dict = {})     # Same LiveView navigation
    async def push_navigate(self, path: str, params: dict = {})  # Different LiveView navigation
    async def replace_navigate(self, path: str, params: dict = {})  # Replace history entry
    async def redirect(self, path: str, params: dict = {})       # Full page redirect

    # Client events
    async def push_event(self, event: str, value: dict[str, Any])  # Send event to client
    
    # File uploads
    def allow_upload(self, upload_name: str, constraints: UploadConstraints) -> UploadConfig
```

## Checking Connection Status

Use `is_connected()` to determine socket type and enable connected-only features. This function is a [TypeGuard](https://docs.python.org/3/library/typing.html#typing.TypeGuard), so after checking, your type checker knows the socket is a `ConnectedLiveViewSocket` and will provide autocomplete for connected-only methods.

```python
from pyview import is_connected

async def mount(self, socket: LiveViewSocket[Context], session):
    # Always initialize state (works on both socket types)
    socket.context = {"users": [], "loading": True}

    # Connected-only operations
    if is_connected(socket):
        # Type checker now knows socket is ConnectedLiveViewSocket
        # IDE autocomplete shows subscribe, broadcast, schedule_info, etc.
        await socket.subscribe("user_updates")
        socket.schedule_info(InfoEvent("refresh_data"), 30)

        # Load data asynchronously
        users = await load_users()
        socket.context.update({"users": users, "loading": False})
```

### LiveView Method Connection State

Your LiveView methods receive different socket types depending on when they're called:

| LiveView Method | Unconnected | Connected | Notes |
|-----------------|:-----------:|:---------:|-------|
| `mount()` | ✓ | ✓ | Called twice: HTTP request, then WebSocket |
| `handle_params()` | ✓ | ✓ | URL changes can happen in either state |
| `handle_event()` | | ✓ | User events only arrive over WebSocket |
| `handle_info()` | | ✓ | Scheduled/pub-sub events require connection |

This is why checking `is_connected(socket)` in `mount()` is common—you may want to skip expensive operations or real-time setup during the initial HTTP render.

### Socket Method Availability

| Method | Unconnected | Connected | Notes |
|--------|:-----------:|:---------:|-------|
| `context` | ✓ | ✓ | State management |
| `live_title` | ✓ | ✓ | Page title |
| `allow_upload()` | ✓ | ✓ | Configure uploads |
| `subscribe()` | | ✓ | Pub/sub |
| `broadcast()` | | ✓ | Pub/sub |
| `schedule_info()` | | ✓ | Recurring events |
| `schedule_info_once()` | | ✓ | One-time events |
| `push_patch()` | | ✓ | Same-view navigation |
| `push_navigate()` | | ✓ | Cross-view navigation |
| `replace_navigate()` | | ✓ | Replace history |
| `redirect()` | | ✓ | Full page redirect |
| `push_event()` | | ✓ | Send to client hooks |

## Context Management

The `socket.context` holds your application state and is typically typed.

### Defining Context Types

Use TypedDict for type safety and autocompletion:

```python
from typing import TypedDict, Optional

class UserListContext(TypedDict):
    users: list[dict]
    current_page: int
    total_pages: int
    loading: bool
    error: Optional[str]
    search_query: str

class UserListLiveView(LiveView[UserListContext]):
    async def mount(self, socket: LiveViewSocket[UserListContext], session):
        socket.context = {
            "users": [],
            "current_page": 1,
            "total_pages": 1,
            "loading": True,
            "error": None,
            "search_query": ""
        }
```

### Dataclass Alternative

For more complex state with methods, use dataclasses:

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class UserListContext:
    users: list[dict] = field(default_factory=list)
    current_page: int = 1
    total_pages: int = 1
    loading: bool = True
    error: Optional[str] = None
    search_query: str = ""
    
    @property
    def has_users(self) -> bool:
        return len(self.users) > 0
    
    @property
    def has_next_page(self) -> bool:
        return self.current_page < self.total_pages

class UserListLiveView(LiveView[UserListContext]):
    async def mount(self, socket: LiveViewSocket[UserListContext], session):
        socket.context = UserListContext()
```


## Real-time Communication

### Pub/Sub Messaging

Subscribe to topics and broadcast messages:

```python
async def mount(self, socket: LiveViewSocket[Context], session):
    socket.context = {"messages": [], "user_id": session["user_id"]}
    
    if is_connected(socket):
        # Subscribe to chat room
        await socket.subscribe("chat_room")
        
        # Subscribe to user-specific updates
        await socket.subscribe(f"user:{session['user_id']}")

async def handle_event(self, event, payload, socket: ConnectedLiveViewSocket[Context]):
    if event == "send_message":
        message = {
            "user_id": socket.context["user_id"],
            "text": payload["text"],
            "timestamp": datetime.now().isoformat()
        }
        
        # Broadcast to all subscribers
        await socket.broadcast("chat_room", message)

async def handle_info(self, event: InfoEvent, socket: ConnectedLiveViewSocket[Context]):
    if event.name == "chat_room":
        # Received message from another user
        socket.context["messages"].append(event.payload)
    elif event.name.startswith("user:"):
        # User-specific update
        socket.context["notification"] = event.payload
```

### Scheduled Events

Schedule recurring or one-time updates:

```python
async def mount(self, socket: LiveViewSocket[Context], session):
    socket.context = {"data": None, "last_update": None}
    
    if is_connected(socket):
        # Refresh data every 30 seconds
        socket.schedule_info(InfoEvent("refresh_data"), 30)
        
        # Show welcome message after 2 seconds
        socket.schedule_info_once(InfoEvent("show_welcome"), 2)

async def handle_info(self, event: InfoEvent, socket: ConnectedLiveViewSocket[Context]):
    if event.name == "refresh_data":
        data = await fetch_latest_data()
        socket.context.update({
            "data": data,
            "last_update": datetime.now()
        })
    elif event.name == "show_welcome":
        socket.context["show_welcome"] = True
```

## Navigation

### Within Same LiveView (`push_patch`)

Navigate within the same LiveView, preserving state:

```python
async def handle_event(self, event, payload, socket: ConnectedLiveViewSocket[Context]):
    if event == "next_page":
        current_page = socket.context["current_page"]
        next_page = current_page + 1
        
        # Navigate to next page - this will trigger handle_params
        await socket.push_patch(f"/users", {"page": next_page})
```

### Between Different LiveViews (`push_navigate`)

Navigate to a different LiveView:

```python
async def handle_event(self, event, payload, socket: ConnectedLiveViewSocket[Context]):
    if event == "view_user":
        user_id = payload["user_id"]
        # Navigate to user detail LiveView
        await socket.push_navigate(f"/users/{user_id}")
```

### Replace History (`replace_navigate`)

Navigate without adding to browser history:

```python
async def handle_event(self, event, payload, socket: ConnectedLiveViewSocket[Context]):
    if event == "login_success":
        # Replace login page with dashboard
        await socket.replace_navigate("/dashboard")
```

### Full Page Redirect (`redirect`)

Perform a full page redirect (useful for external URLs or breaking out of the LiveView):

```python
async def handle_event(self, event, payload, socket: ConnectedLiveViewSocket[Context]):
    if event == "logout":
        # Clear session and redirect to login
        await socket.redirect("/login")

    if event == "external_link":
        # Redirect with query parameters
        await socket.redirect("/oauth/callback", {"provider": "github"})
```

Unlike `push_navigate`, this triggers a full browser navigation rather than a LiveView transition. Use this for:
- Redirecting to non-LiveView pages
- Breaking out of a deeply nested state
- Forcing a fresh page load

## Page Title Management

Set dynamic page titles:

```python
async def mount(self, socket: LiveViewSocket[Context], session):
    socket.live_title = "My App - Loading..."
    socket.context = {"user": None}
    
    if is_connected(socket):
        user = await load_user(session["user_id"])
        socket.context["user"] = user
        socket.live_title = f"My App - {user['name']}"

async def handle_params(self, url, params, socket: LiveViewSocket[Context]):
    page = params.get("page", ["1"])[0]
    socket.live_title = f"Users - Page {page}"
```

## File Upload Management

Configure and handle file uploads:

```python
async def mount(self, socket: LiveViewSocket[Context], session):
    # Configure file uploads
    upload_config = socket.allow_upload(
        "photos",
        constraints=UploadConstraints(
            max_file_size=5 * 1024 * 1024,  # 5MB
            max_files=3,
            accept=[".jpg", ".png", ".gif"]
        ),
        auto_upload=True,
        progress=self.handle_progress
    )
    
    socket.context = {
        "upload_config": upload_config,
        "uploaded_files": []
    }

async def handle_progress(self, entry, socket: LiveViewSocket[Context]):
    """Called during file upload progress"""
    if entry.done:
        # File upload complete
        with socket.context["upload_config"].consume_upload_entry(entry.ref) as upload:
            if upload:
                # Process the uploaded file
                file_path = save_uploaded_file(upload.file)
                socket.context["uploaded_files"].append({
                    "name": entry.name,
                    "path": file_path,
                    "size": entry.size
                })
```

