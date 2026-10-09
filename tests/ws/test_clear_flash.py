"""The built-in lv:clear-flash event clears flash messages without reaching the view."""

from .views import StaticView, TextRendered


class FlashView(StaticView):
    """Puts two flash messages on mount and renders them, in key order."""

    async def mount(self, socket, session):
        await super().mount(socket, session)
        socket.put_flash("error", "Oops")
        socket.put_flash("info", "Saved")

    async def render(self, assigns, meta):
        return TextRendered(", ".join(f"{k}={v}" for k, v in sorted(meta.flash.items())))


async def test_clear_flash_with_key_clears_only_that_message(connect):
    # Given a joined view showing two flash messages
    client = connect({"/": FlashView})
    reply = await client.join("/")
    assert reply["response"]["rendered"]["0"] == "error=Oops, info=Saved"

    # When the client clears the "info" flash
    reply = await client.event("lv:clear-flash", {"key": "info"})

    # Then only that message is removed from the page
    assert reply == {"status": "ok", "response": {"diff": {"0": "error=Oops"}}}


async def test_clear_flash_without_key_clears_all_messages(connect):
    # Given a joined view showing two flash messages
    client = connect({"/": FlashView})
    await client.join("/")

    # When the client clears the flash without naming a key
    reply = await client.event("lv:clear-flash")

    # Then every message is removed from the page
    assert reply == {"status": "ok", "response": {"diff": {"0": ""}}}


async def test_clear_flash_does_not_reach_view(connect):
    # Given a joined view that records the events it handles
    handled = []

    class Home(FlashView):
        async def handle_event(self, event, payload, socket):
            handled.append(event)

    client = connect({"/": Home})
    await client.join("/")

    # When the client clears the flash
    await client.event("lv:clear-flash", {"key": "info"})

    # Then the view's handle_event is not called
    assert handled == []
