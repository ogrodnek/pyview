# Testing with Dependency Injection in PyView

This guide shows how easy it is to test LiveViews that use dependency injection, with or without external DI libraries.

## TL;DR

**Testing is trivial with `socket.state`:**

```python
# Create a socket and inject mocks - that's it!
socket = UnconnectedSocket()
socket.state.database = mock_db
socket.state.cache = mock_cache

view = MyView()
await view.mount(socket, {})
```

No app setup, no framework magic. Just assign mocks and test.

## Why Testing is Easy

PyView's DI approach makes testing simple because:

1. **`socket.state` is just a dictionary** - assign anything to it
2. **No framework magic** - you control what goes in `socket.state`
3. **Works without HTTP requests** - perfect for unit tests
4. **No special test fixtures required** - though you can use them if you want

## Approach 1: Direct `socket.state` (Recommended for Unit Tests)

The simplest approach - just create a socket and assign your mocks:

```python
from unittest.mock import Mock, AsyncMock
from pyview.live_socket import UnconnectedSocket

@pytest.mark.asyncio
async def test_my_view():
    # Create mock services
    mock_db = Mock()
    mock_db.get_user = AsyncMock(return_value={"id": 1, "name": "Test User"})

    # Create socket and inject mocks
    socket = UnconnectedSocket()
    socket.state.database = mock_db

    # Test your view
    view = MyView()
    await view.mount(socket, {"user_id": 1})

    # Verify
    assert socket.context.user["name"] == "Test User"
    mock_db.get_user.assert_called_once_with(1)
```

**Pros:**
- ✅ Super simple - no app setup
- ✅ Fast - no framework overhead
- ✅ Clear - you see exactly what's being tested
- ✅ Works for 95% of tests

## Approach 2: pytest Fixtures (Recommended for Multiple Tests)

Use fixtures to share mock setup across tests:

```python
@pytest.fixture
def mock_services():
    """Reusable mock services."""
    mock_db = Mock()
    mock_db.get_user = AsyncMock(return_value={"id": 1, "name": "Test User"})

    mock_cache = Mock()
    mock_cache.get = Mock(return_value=None)

    return {
        "database": mock_db,
        "cache": mock_cache
    }

@pytest.fixture
def test_socket(mock_services):
    """Socket with mocks pre-injected."""
    socket = UnconnectedSocket()
    socket.state.database = mock_services["database"]
    socket.state.cache = mock_services["cache"]
    return socket, mock_services

@pytest.mark.asyncio
async def test_user_view(test_socket):
    socket, mocks = test_socket

    view = UserView()
    await view.mount(socket, {"user_id": 1})

    assert socket.context.user["name"] == "Test User"

@pytest.mark.asyncio
async def test_profile_view(test_socket):
    socket, mocks = test_socket

    view = ProfileView()
    await view.mount(socket, {"user_id": 1})

    # Both tests share the same mock setup!
```

**Pros:**
- ✅ DRY - reuse mock setup across tests
- ✅ Clean test code
- ✅ Easy to maintain

## Approach 3: Test Doubles (In-Memory Implementations)

Sometimes mocks are too simple. Use test doubles for more realistic behavior:

```python
class InMemoryDatabase:
    """Test double that behaves like a real database."""

    def __init__(self):
        self.users = {
            1: {"id": 1, "name": "Alice"},
            2: {"id": 2, "name": "Bob"},
        }

    async def get_user(self, user_id: int):
        return self.users.get(user_id)

    async def save_user(self, user):
        self.users[user["id"]] = user

@pytest.mark.asyncio
async def test_with_in_memory_db():
    socket = UnconnectedSocket()
    socket.state.database = InMemoryDatabase()

    view = UserManagementView()
    await view.mount(socket, {})

    # Test creating a user
    await view.handle_event("create_user", {"name": "Charlie"}, socket)

    # Test that it was actually saved
    await view.handle_event("load_user", {"id": 3}, socket)
    assert socket.context.user["name"] == "Charlie"
```

**Pros:**
- ✅ More realistic than mocks
- ✅ Can test complex interactions
- ✅ Still fast (no real DB)

**When to use:**
- Testing multiple operations that depend on state
- When mock setup becomes too complex
- Integration-style tests

## Approach 4: Testing with svcs (For Integration Tests)

If you're using the optional svcs integration, you can test with the actual DI container:

```python
from pyview.integrations.svcs_integration import configure_svcs

@pytest.mark.asyncio
async def test_with_svcs():
    # Create app with MOCK services
    app = PyView()

    @configure_svcs(app)
    def register_test_services(registry):
        # Register mocks instead of real services
        registry.register_factory(Database, lambda: mock_db)
        registry.register_factory(Cache, lambda: mock_cache)

    # Test within app lifecycle
    async with app.router.lifespan_context(app):
        # Create socket connected to app
        socket = create_connected_socket(app)

        # When view calls get_services(), it gets your mocks
        view = MyView()
        await view.mount(socket, {})

        # Verify behavior
        assert socket.context.loaded
```

**Key insight:** `registry.register_factory()` **overwrites** previous registrations, so you can:
1. Register real services in your app
2. Re-register with mocks in tests
3. Test the actual DI wiring

**Pros:**
- ✅ Tests actual DI configuration
- ✅ Catches DI registration issues
- ✅ More realistic

**Cons:**
- ❌ More setup than direct `socket.state`
- ❌ Slower (full app lifecycle)

**When to use:**
- Integration tests
- Testing DI configuration itself
- End-to-end test scenarios

## Comparing Approaches

| Approach | Speed | Setup | Realism | Use Case |
|----------|-------|-------|---------|----------|
| Direct `socket.state` | ⚡⚡⚡ | ✅ Minimal | ⭐⭐ | Unit tests |
| pytest Fixtures | ⚡⚡⚡ | ✅ Medium | ⭐⭐ | Multiple tests |
| Test Doubles | ⚡⚡ | ⚠️ More | ⭐⭐⭐ | Complex logic |
| svcs Integration | ⚡ | ⚠️ Most | ⭐⭐⭐⭐ | Integration tests |

## Best Practices

### 1. Start Simple
```python
# ✅ Good - simple and clear
socket = UnconnectedSocket()
socket.state.db = mock_db
```

### 2. Use Fixtures for Shared Setup
```python
# ✅ Good - DRY
@pytest.fixture
def test_socket():
    socket = UnconnectedSocket()
    socket.state.db = InMemoryDatabase()
    return socket
```

### 3. Test Behavior, Not Implementation
```python
# ❌ Bad - testing mocks
mock_db.get_user.assert_called()

# ✅ Good - testing behavior
assert socket.context.user["name"] == "Expected Name"
assert socket.context.loaded == True
```

### 4. Use Test Doubles for State
```python
# ✅ Good for testing state changes
db = InMemoryDatabase()
socket.state.database = db

await view.handle_event("create_user", {...}, socket)
await view.handle_event("update_user", {...}, socket)

# Can verify state changes
assert len(db.users) == 1
```

### 5. Mock External Services
```python
# ✅ Good - mock things that leave your system
socket.state.email_service = Mock(send_email=AsyncMock())
socket.state.payment_gateway = Mock(charge=AsyncMock())

# ✅ Good - use test doubles for internal state
socket.state.database = InMemoryDatabase()
```

## Testing Patterns by Scenario

### Testing Database Interactions
```python
# Use in-memory implementation
socket.state.database = InMemoryDatabase()
```

### Testing External APIs
```python
# Use mocks with canned responses
mock_api = Mock()
mock_api.fetch_data = AsyncMock(return_value={"data": "..."})
socket.state.api_client = mock_api
```

### Testing Email/Notifications
```python
# Use mock to verify it was called
mock_email = Mock()
mock_email.send = AsyncMock()
socket.state.email_service = mock_email

# After test
mock_email.send.assert_called_with(to="user@example.com", ...)
```

### Testing Authentication
```python
# Inject fake auth service
class FakeAuth:
    def __init__(self, user=None):
        self.current_user = user

    async def authenticate(self, token):
        return self.current_user

socket.state.auth = FakeAuth(user={"id": 1, "role": "admin"})
```

## Common Pitfalls

### ❌ Don't: Create Real Services in Tests
```python
# ❌ Bad - uses real database
socket.state.database = Database(connection_string="...")
```

### ✅ Do: Use Mocks or Test Doubles
```python
# ✅ Good
socket.state.database = InMemoryDatabase()
```

### ❌ Don't: Over-mock
```python
# ❌ Bad - mocking everything makes tests brittle
mock_user = Mock()
mock_user.name = "Test"
mock_user.email = "test@example.com"
mock_user.get_name = Mock(return_value="Test")
```

### ✅ Do: Use Real Objects When Possible
```python
# ✅ Good - use real value objects
user = User(id=1, name="Test", email="test@example.com")
socket.context.user = user
```

## Summary

**For 95% of your tests:** Use direct `socket.state` injection

```python
socket = UnconnectedSocket()
socket.state.service = mock_service
```

**It's that simple!**

- No framework setup
- No special test fixtures (unless you want them)
- No messing with HTTP requests
- Just assign mocks and test

The `socket.state` design makes testing trivial, which is exactly what you want in a framework.

## See Also

- `test_di_patterns.py` - Complete working examples of all approaches
- `pyview/di.py` - Documentation on DI patterns
- `pyview/integrations/svcs_integration.py` - Optional svcs integration
