# Socket Lifecycle Hooks

PyView provides a generic lifecycle hook system that allows integrations and user code to register cleanup handlers without tight coupling to the framework.

## The Problem

Previously, if you wanted to add resource cleanup for WebSocket connections, you had two options:

1. **Override `disconnect()`** - Works but requires subclassing and manual cleanup code
2. **Hardcode integration logic in socket** - Creates tight coupling (bad design)

```python
# BAD: Tight coupling
async def close(self):
    # ...
    if hasattr(self, '_svcs_container'):  # Socket knows about svcs!
        await self._svcs_container.aclose()
    if hasattr(self, '_db_connection'):  # Socket knows about databases!
        await self._db_connection.close()
```

## The Solution: `socket.register_cleanup()`

PyView now provides a generic hook system where integrations can register cleanup callbacks:

```python
def register_cleanup(callback: Callable):
    """
    Register a cleanup callback to be called when the socket closes.

    Callbacks can be sync or async. Errors are logged but don't prevent
    other cleanups from running.
    """
```

## How It Works

1. **Integration creates a resource** and registers cleanup
2. **Socket calls all cleanup callbacks** automatically in `close()`
3. **No coupling** - socket doesn't need to know about specific integrations

### Example: Custom Integration

```python
class DatabaseIntegration:
    @staticmethod
    async def get_connection(socket):
        if not hasattr(socket, '_db_connection'):
            # Create resource
            connection = await create_database_connection()
            socket._db_connection = connection

            # Register cleanup - that's it!
            async def cleanup():
                await connection.close()
            socket.register_cleanup(cleanup)

        return socket._db_connection
```

### Example: User Code in LiveView

```python
class MyLiveView(LiveView):
    async def mount(self, socket, session):
        # Open a file
        file = open('data.txt', 'r')
        socket.context.file = file

        # Register cleanup
        socket.register_cleanup(file.close)
```

### Example: svcs Integration

The svcs integration uses this same pattern:

```python
# In pyview/integrations/svcs_integration.py
container = svcs.Container(socket.state.svcs_registry)
socket._svcs_container = container

# Register cleanup callback
async def cleanup_container():
    await container.aclose()
socket.register_cleanup(cleanup_container)
```

## Benefits

1. **No Tight Coupling** - Socket doesn't know about specific integrations
2. **Consistent Pattern** - All integrations use the same mechanism
3. **Error Isolation** - Errors in one cleanup don't break others
4. **Sync or Async** - Works with both sync and async cleanup functions
5. **Order Preserved** - Cleanups run in registration order

## Cleanup Order

When `socket.close()` is called, cleanup happens in this order:

1. Mark socket as `connected = False`
2. Remove scheduled jobs (PyView built-in)
3. Unsubscribe from PubSub topics (PyView built-in)
4. Close upload manager (PyView built-in)
5. **Run registered cleanup callbacks** (your code + integrations)
6. Call `disconnect()` hook (your custom code)

## Error Handling

Errors in cleanup callbacks are logged as warnings but don't prevent other cleanups:

```python
socket.register_cleanup(cleanup1)  # This might error
socket.register_cleanup(cleanup2)  # This will still run!

# Later, when socket closes:
# - cleanup1 runs, errors (logged as warning)
# - cleanup2 still runs successfully
# - disconnect() still gets called
```

## When to Use

### Use `register_cleanup()` for:

- ✅ Integration libraries (svcs, database pools, etc.)
- ✅ Per-connection resources (files, connections, etc.)
- ✅ Resources created in `mount()` that need cleanup
- ✅ When you want automatic cleanup without subclassing

### Use `disconnect()` for:

- ✅ Business logic that needs to run on disconnect
- ✅ Cleanup that's part of your LiveView's responsibility
- ✅ When you need the full LiveView instance context

### DON'T use either for:

- ❌ Scheduled jobs - PyView handles automatically
- ❌ PubSub subscriptions - PyView handles automatically
- ❌ Upload manager - PyView handles automatically

## Complete Example

```python
from pyview import LiveView, LiveViewSocket
from pyview.integrations.svcs_integration import get_services

class DatabaseConnection:
    async def __aenter__(self):
        print("Opening connection...")
        return self

    async def __aexit__(self, *args):
        print("Closing connection...")

class FileHandler:
    def __init__(self):
        self.file = open('log.txt', 'a')

    def close(self):
        self.file.close()

class MyLiveView(LiveView):
    async def mount(self, socket: LiveViewSocket, session):
        # Option 1: Use svcs (automatic cleanup via register_cleanup)
        db = await get_services(socket, DatabaseConnection)

        # Option 2: Manual resource with register_cleanup
        handler = FileHandler()
        socket.context.handler = handler
        socket.register_cleanup(handler.close)

        # Option 3: Lambda for simple cleanup
        socket.register_cleanup(lambda: print("Custom cleanup"))

    async def disconnect(self, socket):
        # Optional: Additional business logic on disconnect
        print("User disconnected")
```

## Implementation Details

The implementation is simple and elegant:

```python
# In ConnectedLiveViewSocket.__init__:
self._cleanup_callbacks: list[Callable] = []

# In ConnectedLiveViewSocket.register_cleanup:
def register_cleanup(self, callback: Callable):
    self._cleanup_callbacks.append(callback)

# In ConnectedLiveViewSocket.close:
for callback in self._cleanup_callbacks:
    try:
        if inspect.iscoroutinefunction(callback):
            await callback()
        else:
            callback()
    except Exception:
        logger.warning(f"Error in cleanup callback", exc_info=True)
```

This follows the same pattern as other lifecycle hooks in PyView:
- `socket.schedule_info()` - Framework manages job cleanup
- `socket.subscribe()` - Framework manages subscription cleanup
- `socket.allow_upload()` - Framework manages upload cleanup
- `socket.register_cleanup()` - Framework manages custom cleanup

## Comparison with Other Frameworks

### Phoenix LiveView
Phoenix has `attach_hook` for lifecycle events, but cleanup is typically done in `terminate/2`:

```elixir
def terminate(_reason, socket) do
  # Manual cleanup
  :ok
end
```

### FastAPI/Starlette
Starlette uses dependencies with `yield` for cleanup:

```python
async def get_db():
    db = Database()
    try:
        yield db
    finally:
        await db.close()
```

### PyView Approach
PyView combines both patterns:

```python
# Explicit cleanup registration (like hooks)
socket.register_cleanup(cleanup_fn)

# Or use svcs which mimics FastAPI's yield pattern
# via context managers
```

## Migration Guide

If you had manual cleanup in `disconnect()`:

**Before:**
```python
async def mount(self, socket, session):
    self.db = await create_connection()

async def disconnect(self, socket):
    await self.db.close()
```

**After (Option 1 - register_cleanup):**
```python
async def mount(self, socket, session):
    db = await create_connection()
    socket.context.db = db
    socket.register_cleanup(lambda: db.close())

# disconnect() not needed anymore!
```

**After (Option 2 - svcs):**
```python
async def mount(self, socket, session):
    db = await get_services(socket, Database)
    # That's it! Cleanup is automatic
```

## Testing

Testing with `register_cleanup` is straightforward:

```python
socket = UnconnectedSocket()

# Create mock resource
mock_resource = Mock()
mock_resource.close = Mock()

# Register cleanup
socket.register_cleanup(mock_resource.close)

# Later in your test...
await socket.close()

# Verify cleanup was called
mock_resource.close.assert_called_once()
```

## Summary

- **`socket.register_cleanup(callback)`** - Generic lifecycle hook
- **Callbacks run before `disconnect()`** - Framework cleanup first, then user code
- **Sync or async** - Both work seamlessly
- **Error isolation** - One error doesn't break others
- **No coupling** - Socket doesn't know about specific integrations
- **Pattern used by svcs** - Proven approach for automatic resource management
