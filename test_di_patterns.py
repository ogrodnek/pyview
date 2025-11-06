"""
Comprehensive testing guide for PyView dependency injection patterns.

This shows how to test LiveViews with different DI approaches, including
how to inject mocks and stubs for testing.
"""
import pytest
from unittest.mock import Mock, AsyncMock
from pyview import PyView, LiveView, LiveViewSocket
from pyview.live_socket import UnconnectedSocket, ConnectedLiveViewSocket
from dataclasses import dataclass


# =============================================================================
# Example Services
# =============================================================================

class Database:
    """Real database service."""
    def __init__(self, connection_string: str):
        self.connection_string = connection_string

    async def get_user(self, user_id: int):
        # In real code, this would query a database
        return {"id": user_id, "name": "Real User"}


class EmailService:
    """Real email service."""
    async def send_email(self, to: str, subject: str, body: str):
        # In real code, this would send an email
        print(f"Sending email to {to}: {subject}")


# =============================================================================
# Example LiveView
# =============================================================================

@dataclass
class UserContext:
    user: dict
    email_sent: bool = False


class UserProfileView(LiveView[UserContext]):
    """Example view that depends on Database and EmailService."""

    async def mount(self, socket: LiveViewSocket[UserContext], session):
        # Get dependencies from socket.state
        db = socket.state.database
        email_service = socket.state.email_service

        # Use the dependencies
        user = await db.get_user(session.get("user_id", 1))
        socket.context = UserContext(user=user)

    async def handle_event(self, event: str, payload, socket):
        if event == "send_welcome_email":
            email_service = socket.state.email_service
            await email_service.send_email(
                socket.context.user["name"] + "@example.com",
                "Welcome!",
                "Welcome to our app!"
            )
            socket.context.email_sent = True

    async def render(self, context: UserContext, meta):
        return f"<div>User: {context.user['name']}</div>"


# =============================================================================
# APPROACH 1: Testing with Direct socket.state (Simplest!)
# =============================================================================

@pytest.mark.asyncio
async def test_user_profile_view_with_socket_state():
    """
    Test using direct socket.state assignment.

    This is the simplest approach - just create a socket and assign mocks
    to socket.state. No app or framework setup needed!
    """
    # Create mock services
    mock_db = Mock()
    mock_db.get_user = AsyncMock(return_value={"id": 1, "name": "Test User"})

    mock_email = Mock()
    mock_email.send_email = AsyncMock()

    # Create a socket without a request (uses fallback state)
    socket = UnconnectedSocket()

    # Inject mocks via socket.state
    socket.state.database = mock_db
    socket.state.email_service = mock_email

    # Test the view
    view = UserProfileView()
    await view.mount(socket, {"user_id": 1})

    # Verify
    assert socket.context.user["name"] == "Test User"
    mock_db.get_user.assert_called_once_with(1)

    # Test event handling
    await view.handle_event("send_welcome_email", {}, socket)
    assert socket.context.email_sent is True
    mock_email.send_email.assert_called_once()


# =============================================================================
# APPROACH 2: Testing with svcs (More realistic)
# =============================================================================

class UserProfileViewWithSvcs(LiveView[UserContext]):
    """Example view that uses svcs get_services()."""

    async def mount(self, socket: LiveViewSocket[UserContext], session):
        from pyview.integrations.svcs_integration import get_services

        # Get dependencies using svcs
        db, email_service = await get_services(socket, Database, EmailService)

        # Use the dependencies
        user = await db.get_user(session.get("user_id", 1))
        socket.context = UserContext(user=user)

    async def render(self, context: UserContext, meta):
        return f"<div>User: {context.user['name']}</div>"


@pytest.mark.asyncio
async def test_user_profile_view_with_svcs():
    """
    Test using svcs integration.

    This approach:
    1. Sets up a real app with svcs
    2. Overrides services with mocks (svcs allows re-registration)
    3. Tests through the full app lifecycle
    """
    from pyview.integrations.svcs_integration import configure_svcs

    # Create the app
    app = PyView()

    # Configure with MOCK services
    @configure_svcs(app)
    def register_test_services(registry):
        # Register mock database
        def create_mock_db():
            mock_db = Mock()
            mock_db.get_user = AsyncMock(return_value={"id": 1, "name": "Test User"})
            return mock_db

        # Register mock email service
        def create_mock_email():
            mock_email = Mock()
            mock_email.send_email = AsyncMock()
            return mock_email

        registry.register_factory(Database, create_mock_db)
        registry.register_factory(EmailService, create_mock_email)

    # Run test within app lifespan
    async with app.router.lifespan_context(app):
        # Create a mock websocket that has access to app.state
        from unittest.mock import Mock
        from starlette.websockets import WebSocket
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from pyview.instrumentation import NoOpInstrumentation

        mock_ws = Mock(spec=WebSocket)
        mock_ws.app = app

        view = UserProfileViewWithSvcs()
        scheduler = AsyncIOScheduler()
        socket = ConnectedLiveViewSocket(
            mock_ws, "test", view, scheduler, NoOpInstrumentation()
        )

        # Now when the view calls get_services, it will get the mocks
        await view.mount(socket, {"user_id": 1})

        # Verify the mock was called
        assert socket.context.user["name"] == "Test User"


# =============================================================================
# APPROACH 3: Fixture-based Testing with socket.state
# =============================================================================

@pytest.fixture
def mock_services():
    """Reusable fixture that provides mock services."""
    mock_db = Mock()
    mock_db.get_user = AsyncMock(return_value={"id": 1, "name": "Fixture User"})

    mock_email = Mock()
    mock_email.send_email = AsyncMock()

    return {
        "database": mock_db,
        "email_service": mock_email
    }


@pytest.fixture
def test_socket(mock_services):
    """Fixture that provides a socket with mock services already injected."""
    socket = UnconnectedSocket()
    socket.state.database = mock_services["database"]
    socket.state.email_service = mock_services["email_service"]
    return socket, mock_services


@pytest.mark.asyncio
async def test_with_fixtures(test_socket):
    """
    Test using pytest fixtures for cleaner test code.

    This is great for testing multiple views that share the same dependencies.
    """
    socket, mocks = test_socket

    view = UserProfileView()
    await view.mount(socket, {"user_id": 1})

    assert socket.context.user["name"] == "Fixture User"
    mocks["database"].get_user.assert_called_once()


# =============================================================================
# APPROACH 4: Testing with different service implementations
# =============================================================================

class InMemoryDatabase:
    """Test double that implements the real interface but uses in-memory storage."""

    def __init__(self):
        self.users = {
            1: {"id": 1, "name": "Test User 1"},
            2: {"id": 2, "name": "Test User 2"},
        }

    async def get_user(self, user_id: int):
        return self.users.get(user_id, {"id": user_id, "name": "Unknown"})


@pytest.mark.asyncio
async def test_with_in_memory_implementation():
    """
    Test using an in-memory implementation instead of mocks.

    This is useful when you want more realistic behavior than mocks provide,
    but don't want to use the real database.
    """
    socket = UnconnectedSocket()
    socket.state.database = InMemoryDatabase()
    socket.state.email_service = Mock(send_email=AsyncMock())

    view = UserProfileView()
    await view.mount(socket, {"user_id": 2})

    assert socket.context.user["name"] == "Test User 2"


# =============================================================================
# APPROACH 5: Testing svcs with override helper
# =============================================================================

@pytest.mark.asyncio
async def test_svcs_with_override_helper():
    """
    Test with a helper that makes svcs overriding easier.

    You can create a helper function to make test setup cleaner.
    """
    from pyview.integrations.svcs_integration import configure_svcs

    def create_test_app_with_mocks(mock_registry):
        """Helper to create an app with mock services."""
        app = PyView()

        @configure_svcs(app)
        def register_services(registry):
            # Apply all the mock registrations
            for svc_type, factory in mock_registry.items():
                registry.register_factory(svc_type, factory)

        return app

    # Define your mocks
    mock_db = Mock()
    mock_db.get_user = AsyncMock(return_value={"id": 1, "name": "Helper Test"})

    # Create app with mocks
    app = create_test_app_with_mocks({
        Database: lambda: mock_db,
        EmailService: lambda: Mock(send_email=AsyncMock())
    })

    async with app.router.lifespan_context(app):
        # Test as before...
        pass


# =============================================================================
# Summary
# =============================================================================

"""
## Testing Recommendations

### For Simple Views (Recommended)
Use **Approach 1** (direct socket.state):
- No app setup needed
- Just create socket, assign mocks, test
- Fastest and simplest

### For Integration Tests
Use **Approach 3** (pytest fixtures):
- Reusable fixtures for common dependencies
- Clean test code
- Easy to share test setup

### For Testing with Real DI Container
Use **Approach 2** (svcs with mocks):
- Tests the actual DI wiring
- Ensures services are registered correctly
- More realistic but more setup

### Key Points

1. **socket.state makes testing trivial**
   - Just assign mocks: `socket.state.db = mock_db`
   - No framework setup needed

2. **svcs supports overriding**
   - Re-register services with test implementations
   - Original pattern: register_factory() overwrites previous registrations

3. **Use the right tool for the job**
   - Unit tests: Direct socket.state
   - Integration tests: Full app with svcs
   - Both are easy!

4. **Mocks vs Fakes**
   - Mocks (unittest.mock): For behavior verification
   - Fakes (InMemory*): For more realistic testing
   - Both work great with socket.state
"""

if __name__ == "__main__":
    # Run with: poetry run pytest test_di_patterns.py -v
    print(__doc__)
