"""Form events arrive decoded; other events pass their value through unchanged."""

from .views import StaticView


def recording_view(received: list):
    class Form(StaticView):
        async def handle_event(self, event, payload, socket):
            received.append((event, payload))

    return Form


async def test_form_event_value_is_decoded(connect):
    # Given a joined view
    received = []
    client = connect({"/": recording_view(received)})
    await client.join("/")

    # When the browser submits a form, which it sends URL-encoded
    await client.event("save", "name=Larry&email=a%40b.com", type="form")

    # Then the view gets the fields decoded, each as a list of values
    assert received == [("save", {"name": ["Larry"], "email": ["a@b.com"]})]


async def test_form_event_collects_repeated_keys(connect):
    # Given a joined view
    received = []
    client = connect({"/": recording_view(received)})
    await client.join("/")

    # When a form with a checkbox group or multi-select is submitted
    await client.event("save", "tags=a&tags=b", type="form")

    # Then every value for the field arrives
    assert received == [("save", {"tags": ["a", "b"]})]


async def test_form_change_event_includes_target(connect):
    # Given a joined view
    received = []
    client = connect({"/": recording_view(received)})
    await client.join("/")

    # When an input changes, which the browser reports with the field it came from
    await client.event("validate", "name=Lar&_target=name", type="form")

    # Then the changed field's name arrives in _target
    assert received == [("validate", {"name": ["Lar"], "_target": ["name"]})]


async def test_non_form_event_value_is_passed_through(connect):
    # Given a joined view
    received = []
    client = connect({"/": recording_view(received)})
    await client.join("/")

    # When a click arrives with phx-value-* values, which the browser sends as JSON
    await client.event("water", {"id": "7"})

    # Then the view gets the value as sent, not parsed as a form
    assert received == [("water", {"id": "7"})]
