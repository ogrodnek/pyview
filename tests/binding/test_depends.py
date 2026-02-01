"""Tests for Depends() dependency injection.

These tests verify that Depends() works end-to-end through call_mount
and create_view, including dependency chains, caching, and Session
type injection.
"""

from unittest.mock import MagicMock

import pytest

from pyview import Depends, Session
from pyview.binding.helpers import call_mount, create_view
from pyview.live_view import LiveView


class TestDependsInMount:
    """Integration tests for Depends() in mount()."""

    async def test_depends_resolves_in_mount(self):
        """Verify basic dependency injection works in mount."""

        async def get_config():
            return {"theme": "dark"}

        class MyView(LiveView):
            async def mount(self, socket, session, config=Depends(get_config)):
                self.received_config = config

        lv = MyView()
        socket = MagicMock()

        await call_mount(lv, socket, session={})

        assert lv.received_config == {"theme": "dark"}

    async def test_depends_chain_resolution(self):
        """Verify dependencies that depend on other dependencies resolve correctly."""

        class FakeDB:
            pass

        class UserRepo:
            def __init__(self, db):
                self.db = db

        async def get_db():
            return FakeDB()

        async def get_repo(db=Depends(get_db)):
            return UserRepo(db)

        class MyView(LiveView):
            async def mount(self, socket, session, repo=Depends(get_repo)):
                self.received_repo = repo

        lv = MyView()
        socket = MagicMock()

        await call_mount(lv, socket, session={})

        assert isinstance(lv.received_repo, UserRepo)
        assert isinstance(lv.received_repo.db, FakeDB)

    async def test_depends_caching(self):
        """Verify same dependency called twice only executes once (per-request caching)."""
        call_count = 0

        async def get_expensive():
            nonlocal call_count
            call_count += 1
            return "result"

        async def get_a(val=Depends(get_expensive)):
            return f"a:{val}"

        async def get_b(val=Depends(get_expensive)):
            return f"b:{val}"

        class MyView(LiveView):
            async def mount(self, socket, session, a=Depends(get_a), b=Depends(get_b)):
                self.a = a
                self.b = b

        lv = MyView()
        socket = MagicMock()

        await call_mount(lv, socket, session={})

        assert lv.a == "a:result"
        assert lv.b == "b:result"
        assert call_count == 1  # get_expensive only called once, not twice

    async def test_session_type_injection_in_depends(self):
        """Verify Session type annotation injects session dict into dependency functions."""

        async def get_user_id(session: Session):
            return session.get("user_id")

        class MyView(LiveView):
            async def mount(self, socket, session, user_id=Depends(get_user_id)):
                self.received_user_id = user_id

        lv = MyView()
        socket = MagicMock()

        await call_mount(lv, socket, session={"user_id": "123"})

        assert lv.received_user_id == "123"


class TestDependsInInit:
    """Integration tests for Depends() in __init__()."""

    def test_depends_in_init_with_session(self):
        """Verify sync dependency with Session access works in __init__."""

        def get_user_prefs(session: Session):
            return session.get("prefs", {"theme": "light"})

        class MyView(LiveView):
            def __init__(self, prefs=Depends(get_user_prefs)):
                self.prefs = prefs

        lv = create_view(MyView, session={"prefs": {"theme": "dark"}})

        assert lv.prefs == {"theme": "dark"}

    def test_depends_in_init_rejects_async(self):
        """Verify async dependency in __init__ raises clear error."""

        async def get_async_config():
            return {"async": True}

        class MyView(LiveView):
            def __init__(self, config=Depends(get_async_config)):
                self.config = config

        with pytest.raises(ValueError) as exc_info:
            create_view(MyView, session={})

        assert "get_async_config" in str(exc_info.value)
        assert "async" in str(exc_info.value).lower()


class TestSessionTypeInjection:
    """Tests for Session type annotation injection."""

    async def test_session_type_preserves_annotated_metadata(self):
        """Verify Session type annotation works (requires include_extras=True).

        This test fails if get_type_hints() doesn't use include_extras=True,
        because the Annotated metadata would be stripped and Session wouldn't
        be recognized.
        """

        async def get_user_from_session(sess: Session):
            return {"user_id": sess.get("user_id")}

        class MyView(LiveView):
            async def mount(self, socket, session, user=Depends(get_user_from_session)):
                self.user = user

        lv = MyView()
        socket = MagicMock()

        await call_mount(lv, socket, session={"user_id": "abc123"})

        assert lv.user == {"user_id": "abc123"}
