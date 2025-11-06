"""Pytest fixtures for stream tests."""

from dataclasses import dataclass
from pyview import Stream
import pytest


@dataclass
class Message:
    """Test message model."""
    id: int
    text: str
    user: str


@dataclass
class User:
    """Test user model."""
    id: int
    name: str
    email: str


@pytest.fixture
def sample_messages():
    """Sample messages for testing."""
    return [
        Message(id=1, text="Hello", user="Alice"),
        Message(id=2, text="World", user="Bob"),
        Message(id=3, text="Test", user="Charlie"),
    ]


@pytest.fixture
def sample_users():
    """Sample users for testing."""
    return [
        User(id=1, name="Alice", email="alice@example.com"),
        User(id=2, name="Bob", email="bob@example.com"),
    ]


@pytest.fixture
def empty_stream():
    """Empty message stream."""
    return Stream[Message](dom_id=lambda m: f"msg-{m.id}")


@pytest.fixture
def populated_stream(sample_messages):
    """Stream populated with sample messages."""
    stream = Stream[Message](dom_id=lambda m: f"msg-{m.id}")
    stream.extend(sample_messages)
    return stream
