"""
Example services for demonstrating dependency injection.
"""
from datetime import datetime
from typing import Optional


class Database:
    """Simulated database service."""

    def __init__(self, connection_string: str = "sqlite://memory"):
        self.connection_string = connection_string
        self.connected = True
        self._data = {
            1: {"id": 1, "name": "Alice", "email": "alice@example.com"},
            2: {"id": 2, "name": "Bob", "email": "bob@example.com"},
            3: {"id": 3, "name": "Charlie", "email": "charlie@example.com"},
        }

    def get_user(self, user_id: int) -> Optional[dict]:
        """Get a user by ID."""
        return self._data.get(user_id)

    def list_users(self) -> list[dict]:
        """List all users."""
        return list(self._data.values())

    async def close(self):
        """Clean up database connection."""
        self.connected = False


class TimeService:
    """Service for getting the current time."""

    def __init__(self, timezone: str = "UTC"):
        self.timezone = timezone

    def get_current_time(self) -> str:
        """Get the current time as a formatted string."""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class MessageService:
    """Service for generating messages."""

    def __init__(self, prefix: str = "Hello"):
        self.prefix = prefix

    def greet(self, name: str) -> str:
        """Generate a greeting message."""
        return f"{self.prefix}, {name}!"


# Factory functions for service creation
def create_database() -> Database:
    """Factory function to create a Database instance."""
    print("Creating Database service...")
    return Database("sqlite://memory")


async def create_database_async() -> Database:
    """Async factory function to create a Database instance."""
    print("Creating Database service (async)...")
    db = Database("sqlite://memory")
    return db


def create_time_service() -> TimeService:
    """Factory function to create a TimeService instance."""
    print("Creating TimeService...")
    return TimeService("UTC")


def create_message_service() -> MessageService:
    """Factory function to create a MessageService instance."""
    print("Creating MessageService...")
    return MessageService("Hello")
