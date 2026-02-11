"""
Unit tests for flash message support.
"""

from pyview.live_socket import ConnectedLiveViewSocket, UnconnectedSocket


class TestUnconnectedSocketFlash:
    def test_initial_flash_is_empty(self):
        socket = UnconnectedSocket()
        assert socket.flash == {}

    def test_put_flash(self):
        socket = UnconnectedSocket()
        socket.put_flash("info", "Saved!")
        assert socket.flash == {"info": "Saved!"}

    def test_put_flash_overwrites(self):
        socket = UnconnectedSocket()
        socket.put_flash("info", "First")
        socket.put_flash("info", "Second")
        assert socket.flash == {"info": "Second"}

    def test_put_flash_multiple_keys(self):
        socket = UnconnectedSocket()
        socket.put_flash("info", "Good")
        socket.put_flash("error", "Bad")
        assert socket.flash == {"info": "Good", "error": "Bad"}

    def test_put_flash_any_value(self):
        socket = UnconnectedSocket()
        socket.put_flash("info", {"title": "Done", "detail": "3 files"})
        assert socket.flash["info"] == {"title": "Done", "detail": "3 files"}

    def test_clear_flash_specific_key(self):
        socket = UnconnectedSocket()
        socket.put_flash("info", "Hello")
        socket.put_flash("error", "Oops")
        socket.clear_flash("info")
        assert socket.flash == {"error": "Oops"}

    def test_clear_flash_all(self):
        socket = UnconnectedSocket()
        socket.put_flash("info", "Hello")
        socket.put_flash("error", "Oops")
        socket.clear_flash()
        assert socket.flash == {}

    def test_clear_flash_missing_key_is_noop(self):
        socket = UnconnectedSocket()
        socket.put_flash("info", "Hello")
        socket.clear_flash("error")
        assert socket.flash == {"info": "Hello"}


class TestFlashContextProcessor:
    def test_flash_injected_into_context(self):
        from pyview.flash import add_flash
        from pyview.meta import PyViewMeta

        socket = UnconnectedSocket()
        socket.put_flash("info", "Test message")
        meta = PyViewMeta(socket=socket)

        result = add_flash(meta)
        assert result == {"flash": {"info": "Test message"}}

    def test_flash_empty_when_no_socket(self):
        from pyview.flash import add_flash
        from pyview.meta import PyViewMeta

        meta = PyViewMeta(socket=None)
        result = add_flash(meta)
        assert result == {"flash": {}}

    def test_flash_returns_live_reference(self):
        """Flash dict in context should be the same object as socket.flash,
        so template always sees latest state."""
        from pyview.flash import add_flash
        from pyview.meta import PyViewMeta

        socket = UnconnectedSocket()
        meta = PyViewMeta(socket=socket)

        result = add_flash(meta)
        # Mutate after context processor ran
        socket.put_flash("info", "After")
        assert result["flash"] == {"info": "After"}
