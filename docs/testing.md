# Testing pyview Applications

This guide covers testing LiveView applications using pyview's built-in testing utilities.

## Table of Contents

- [Quick Start](#quick-start)
- [TestSocket Overview](#testsocket-overview)
- [Testing LiveView Lifecycle Methods](#testing-liveview-lifecycle-methods)
- [Testing Patterns](#testing-patterns)
- [Best Practices](#best-practices)
- [API Reference](#api-reference)

## Quick Start

pyview provides `TestSocket` - a test double that mimics LiveViewSocket behavior for testing.

**Installation:**

No extra installation needed! Testing utilities are included with pyview-web.

**Basic Example:**

```python
import pytest
from pyview.testing import TestSocket
from your_app.views import CountLiveView, CountContext

@pytest.mark.asyncio
async def test_increment_increases_count():
    view = CountLiveView()
    socket = TestSocket[CountContext](context={"count": 5})

    await view.handle_event("increment", {}, socket)

    assert socket.context["count"] == 6
```

## TestSocket Overview

`TestSocket` is a test double that:
- ✅ Mimics both connected and unconnected socket behavior
- ✅ Records all method calls for assertions
- ✅ Supports generic types for IDE autocomplete
- ✅ Requires no WebSocket connections or network setup
- ✅ Enables fast, isolated unit tests

### Creating a TestSocket

```python
from pyview.testing import TestSocket

# Basic initialization
socket = TestSocket()

# With initial context
socket = TestSocket(context={"count": 0})

# As unconnected (for testing mount)
socket = TestSocket(connected=False)

# With page title
socket = TestSocket(live_title="My Page")

# With type hints for IDE support
from typing import TypedDict

class MyContext(TypedDict):
    count: int

socket = TestSocket[MyContext](context={"count": 0})
# Now IDE knows socket.context["count"] is an int!
```

## Testing LiveView Lifecycle Methods

### Testing `mount()`

```python
@pytest.mark.asyncio
async def test_mount_initializes_context():
    view = MyLiveView()
    socket = TestSocket()

    await view.mount(socket, session={})

    assert socket.context is not None
    assert socket.context["initialized"] is True
```

### Testing `handle_event()`

```python
@pytest.mark.asyncio
async def test_button_click_increments():
    view = CounterView()
    socket = TestSocket(context={"count": 0})

    await view.handle_event("increment", {}, socket)

    assert socket.context["count"] == 1
```

**With event payload:**

```python
@pytest.mark.asyncio
async def test_form_submit_with_data():
    view = FormView()
    socket = TestSocket(context={"name": ""})

    payload = {"name": "Alice"}
    await view.handle_event("submit", payload, socket)

    assert socket.context["name"] == "Alice"
```

### Testing `handle_info()`

```python
from pyview.events import InfoEvent

@pytest.mark.asyncio
async def test_scheduled_event_updates_state():
    view = TimerView()
    socket = TestSocket(context={"elapsed": 0})

    await view.handle_info(InfoEvent("tick"), socket)

    assert socket.context["elapsed"] == 1
```

### Testing `handle_params()`

```python
from urllib.parse import urlparse

@pytest.mark.asyncio
async def test_url_params_set_context():
    view = UserView()
    socket = TestSocket(context={})
    url = urlparse("/?user_id=123")
    params = {"user_id": ["123"]}

    await view.handle_params(url, params, socket)

    assert socket.context["user_id"] == "123"
```

## Testing Patterns

### Pattern 1: TypedDict Context

```python
from typing import TypedDict

class CountContext(TypedDict):
    count: int

@pytest.mark.asyncio
async def test_with_typeddict():
    view = CountLiveView()
    socket = TestSocket[CountContext](context={"count": 0})

    await view.handle_event("increment", {}, socket)

    assert socket.context["count"] == 1
```

### Pattern 2: Dataclass Context

```python
from dataclasses import dataclass

@dataclass
class UserContext:
    username: str
    age: int

@pytest.mark.asyncio
async def test_with_dataclass():
    view = UserLiveView()
    socket = TestSocket[UserContext](
        context=UserContext(username="alice", age=30)
    )

    await view.handle_event("birthday", {}, socket)

    assert socket.context.age == 31
```

### Pattern 3: Testing Navigation

```python
@pytest.mark.asyncio
async def test_navigation():
    view = NavigationView()
    socket = TestSocket()

    await view.handle_event("go_home", {}, socket)

    # Assert navigation was called
    assert socket.push_patches == [("/", None)]

    # Or use helper method
    socket.assert_push_patch("/")
```

**Navigation types:**

```python
# push_patch - same LiveView, calls handle_params
assert socket.push_patches == [("/users", {"tab": "profile"})]

# push_navigate - different LiveView, no reload
assert socket.push_navigates == [("/login", None)]

# replace_navigate - different LiveView, replaces history
assert socket.replace_navigates == [("/dashboard", None)]

# redirect - full page reload
assert socket.redirects == [("/external", None)]
```

### Pattern 4: Testing Pub/Sub

```python
@pytest.mark.asyncio
async def test_chat_subscription():
    view = ChatView()
    socket = TestSocket()

    await view.mount(socket, session={})

    # Verify subscription
    assert "chat:lobby" in socket.subscriptions
    # Or
    socket.assert_subscribed("chat:lobby")

@pytest.mark.asyncio
async def test_broadcast():
    view = ChatView()
    socket = TestSocket()

    await view.handle_event("send_message", {"msg": "Hello"}, socket)

    # Verify broadcast
    assert ("chat:lobby", {"msg": "Hello"}) in socket.broadcasts
    # Or
    socket.assert_broadcast("chat:lobby", {"msg": "Hello"})
```

### Pattern 5: Testing Scheduled Events

```python
@pytest.mark.asyncio
async def test_recurring_schedule():
    view = PingView()
    socket = TestSocket(connected=True)

    await view.mount(socket, session={})

    # Verify scheduled
    assert len(socket.scheduled_info) == 1
    event_type, event, interval = socket.scheduled_info[0]
    assert event_type == "recurring"
    assert interval == 10  # every 10 seconds

@pytest.mark.asyncio
async def test_one_time_schedule():
    view = TimeoutView()
    socket = TestSocket(connected=True)

    await view.mount(socket, session={})

    # Verify one-time schedule
    assert len(socket.scheduled_info_once) == 1
    event, delay = socket.scheduled_info_once[0]
    assert delay == 5.0  # 5 seconds
```

### Pattern 6: Testing with BaseEventHandler

```python
from pyview.events import BaseEventHandler, event

class KanbanView(BaseEventHandler, LiveView):
    @event("task-moved")
    async def handle_task_moved(self, event, payload, socket):
        # ... handle task move

@pytest.mark.asyncio
async def test_event_decorator():
    view = KanbanView()
    socket = TestSocket()
    await view.mount(socket, session={})

    # Event routing works through decorator
    await view.handle_event("task-moved", {"task_id": "123"}, socket)

    # Verify changes occurred
    assert socket.context.task_moved is True
```

### Pattern 7: Testing Client-side Events

```python
@pytest.mark.asyncio
async def test_client_side_event():
    view = HighlightView()
    socket = TestSocket()

    await view.handle_event("highlight_item", {"id": "item-1"}, socket)

    # Verify JS hook event was pushed to client
    assert ("highlight", {"id": "item-1"}) in socket.client_events
```

### Pattern 8: Integration Tests

```python
@pytest.mark.asyncio
async def test_full_lifecycle():
    """Test complete workflow through multiple lifecycle methods."""
    view = TodoView()
    socket = TestSocket()

    # Mount
    await view.mount(socket, session={})
    assert len(socket.context["todos"]) == 0

    # Add todo
    await view.handle_event("add", {"text": "Buy milk"}, socket)
    assert len(socket.context["todos"]) == 1

    # Complete todo
    todo_id = socket.context["todos"][0]["id"]
    await view.handle_event("complete", {"id": todo_id}, socket)
    assert socket.context["todos"][0]["completed"] is True

    # Navigate to archive
    await view.handle_event("view_archive", {}, socket)
    socket.assert_push_patch("/todos/archive")
```

## Best Practices

### 1. Test Business Logic, Not Framework

✅ **Good:** Test your LiveView's business logic

```python
@pytest.mark.asyncio
async def test_discount_calculation():
    view = CheckoutView()
    socket = TestSocket(context={"total": 100, "discount_code": ""})

    await view.handle_event("apply_discount", {"code": "SAVE10"}, socket)

    assert socket.context["total"] == 90
```

❌ **Bad:** Test framework behavior

```python
# Don't test that push_patch adds to push_patches list -
# that's testing TestSocket itself!
```

### 2. Use Type Hints

```python
# Better IDE support and catches errors
socket = TestSocket[MyContext](context=...)
```

### 3. Use Descriptive Test Names

```python
# Good
async def test_increment_event_increases_count_by_one()

# Bad
async def test_increment()
```

### 4. Arrange-Act-Assert Pattern

```python
@pytest.mark.asyncio
async def test_user_registration():
    # Arrange
    view = RegistrationView()
    socket = TestSocket(context={})
    payload = {"email": "test@example.com", "password": "secret"}

    # Act
    await view.handle_event("register", payload, socket)

    # Assert
    assert socket.context["user"] is not None
    assert socket.context["user"]["email"] == "test@example.com"
```

### 5. Test Edge Cases

```python
@pytest.mark.asyncio
async def test_decrement_below_zero():
    """Test that count can go negative."""
    view = CountView()
    socket = TestSocket(context={"count": 0})

    await view.handle_event("decrement", {}, socket)

    assert socket.context["count"] == -1
```

### 6. Clear History Between Tests

If reusing a socket across multiple operations:

```python
@pytest.mark.asyncio
async def test_multiple_operations():
    view = MyView()
    socket = TestSocket()

    await view.handle_event("action1", {}, socket)
    socket.clear_history()  # Clear recorded calls

    await view.handle_event("action2", {}, socket)
    assert len(socket.push_patches) == 1  # Only action2's navigation
```

### 7. Use Fixtures for Common Setup

```python
import pytest
from pyview.testing import TestSocket

@pytest.fixture
def count_socket():
    """Fixture providing initialized count socket."""
    return TestSocket(context={"count": 0})

@pytest.mark.asyncio
async def test_with_fixture(count_socket):
    view = CountView()
    await view.handle_event("increment", {}, count_socket)
    assert count_socket.context["count"] == 1
```

## Limitations & Mocking External Dependencies

TestSocket tests your LiveView business logic in isolation. For code that makes external calls (HTTP, database, etc.), you'll need to mock those dependencies:

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
@patch('your_app.api.fetch_user')
async def test_with_external_api(mock_fetch):
    mock_fetch.return_value = {"name": "Alice", "age": 30}

    view = UserView()
    socket = TestSocket()

    await view.handle_event("load_user", {"id": "123"}, socket)

    assert socket.context["user"]["name"] == "Alice"
    mock_fetch.assert_called_once_with("123")
```

## API Reference

### TestSocket Class

```python
class TestSocket(Generic[T]):
    def __init__(
        self,
        context: Optional[T] = None,
        connected: bool = True,
        live_title: Optional[str] = None,
    )
```

#### Attributes

- `context: T` - LiveView state/context
- `connected: bool` - Whether socket appears connected
- `live_title: Optional[str]` - Page title
- `push_patches: list[tuple[str, Optional[dict]]]` - Recorded push_patch calls
- `push_navigates: list[tuple[str, Optional[dict]]]` - Recorded push_navigate calls
- `replace_navigates: list[tuple[str, Optional[dict]]]` - Recorded replace_navigate calls
- `redirects: list[tuple[str, Optional[dict]]]` - Recorded redirect calls
- `subscriptions: list[str]` - Recorded subscribe calls
- `broadcasts: list[tuple[str, Any]]` - Recorded broadcast calls
- `scheduled_info: list[tuple[str, Any, float]]` - Recorded recurring schedules
- `scheduled_info_once: list[tuple[Any, Optional[float]]]` - Recorded one-time schedules
- `client_events: list[tuple[str, dict]]` - Recorded push_event calls
- `allowed_uploads: list[dict]` - Recorded allow_upload calls
- `pending_events: list[tuple[str, Any]]` - Pending client events

#### Methods

**Navigation:**
- `async push_patch(path, params=None)` - Record push_patch
- `async push_navigate(path, params=None)` - Record push_navigate
- `async replace_navigate(path, params=None)` - Record replace_navigate
- `async redirect(path, params=None)` - Record redirect

**Pub/Sub:**
- `async subscribe(topic)` - Record subscription
- `async broadcast(topic, message)` - Record broadcast

**Scheduling:**
- `schedule_info(event, seconds)` - Record recurring schedule
- `schedule_info_once(event, seconds=None)` - Record one-time schedule

**Client Events:**
- `async push_event(event, value)` - Record client event

**Uploads:**
- `allow_upload(name, constraints, ...)` - Record upload config

**Assertions:**
- `assert_push_patch(path, params=None)` - Assert push_patch was called
- `assert_push_navigate(path, params=None)` - Assert push_navigate was called
- `assert_redirect(path, params=None)` - Assert redirect was called
- `assert_subscribed(topic)` - Assert subscription exists
- `assert_broadcast(topic, message)` - Assert broadcast was made

**Utilities:**
- `clear_history()` - Clear all recorded interactions
- `__repr__()` - Helpful debug representation

## Examples

See the [examples/tests/](../examples/tests/) directory for complete working examples:

- `examples/tests/views/count/` - Basic counter with events and params
- `examples/tests/views/kanban/` - Task board with BaseEventHandler
- `examples/tests/views/webping/` - Scheduled events and info handling

## Running Tests

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=your_app

# Run specific test file
poetry run pytest tests/test_my_view.py

# Run with verbose output
poetry run pytest -v

# Run only tests matching pattern
poetry run pytest -k "test_increment"
```

## Getting Help

- [pyview Documentation](https://pyview.rocks)
- [GitHub Issues](https://github.com/ogrodnek/pyview/issues)
- [Examples](https://examples.pyview.rocks)

## Next Steps

- Try writing tests for your existing LiveViews
- Use TDD (Test-Driven Development) for new features
- Add tests to your CI/CD pipeline
- Aim for high test coverage of business logic

Happy testing! 🎉
