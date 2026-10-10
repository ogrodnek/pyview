"""Events targeted at a component (phx-target) go to that component, not the view."""

from string.templatelib import Template

from pyview.components import ComponentMeta, ComponentSocket, LiveComponent
from pyview.live_view import LiveView
from pyview.meta import PyViewMeta
from pyview.template.live_view_template import live_component
from pyview.template.template_view import TemplateView


def counter_page(view_events: list):
    """A view rendering one Counter component; records events the view itself handles."""

    class Counter(LiveComponent[dict]):
        async def mount(self, socket: ComponentSocket[dict], assigns: dict):
            socket.context = {"count": 0}

        async def handle_event(self, event: str, payload: dict, socket: ComponentSocket[dict]):
            if event == "increment":
                socket.context["count"] += 1

        def template(self, assigns: dict, meta: ComponentMeta) -> Template:
            count = assigns["count"]
            return t"<span>{count}</span>"

    class Page(TemplateView, LiveView[dict]):
        async def mount(self, socket, session):
            socket.context = {}

        async def handle_event(self, event, payload, socket):
            view_events.append(event)

        def template(self, assigns: dict, meta: PyViewMeta) -> Template:
            counter = live_component(Counter, id="counter")
            return t"<div>{counter}</div>"

    return Page


def component_cid(join_reply: dict) -> int:
    """The cid of the one component in a join reply's rendered tree."""
    [cid] = join_reply["response"]["rendered"]["c"]
    return int(cid)


async def test_event_with_a_cid_reaches_that_component_not_the_view(connect):
    # Given a view rendering a counter component
    view_events = []
    client = connect({"/": counter_page(view_events)})
    cid = component_cid(await client.join("/"))

    # When the client sends an event targeted at the component
    reply = await client.event("increment", cid=cid)

    # Then the component handles it and its new render is in the reply; the view never sees it
    assert reply["status"] == "ok"
    assert view_events == []
    assert "1" in str(reply["response"]["diff"]["c"][str(cid)])


async def test_event_for_an_unknown_cid_is_ignored(connect):
    # Given a view rendering a counter component
    view_events = []
    client = connect({"/": counter_page(view_events)})
    cid = component_cid(await client.join("/"))

    # When an event arrives for a component that no longer exists
    reply = await client.event("increment", cid=cid + 100)

    # Then it is answered without error, reaches neither the view nor the component,
    # and the connection stays up
    assert reply["status"] == "ok"
    assert view_events == []
    assert "c" not in reply["response"]["diff"]
    assert (await client.heartbeat())["status"] == "ok"


async def test_event_with_a_non_integer_cid_is_ignored(connect):
    # Given a view rendering a counter component
    view_events = []
    client = connect({"/": counter_page(view_events)})
    cid = component_cid(await client.join("/"))

    # When an event arrives with a cid that is not an integer
    reply = await client.event("increment", cid=str(cid))

    # Then it is answered without error and reaches neither the view nor the component
    assert reply["status"] == "ok"
    assert view_events == []
    assert "c" not in reply["response"]["diff"]
