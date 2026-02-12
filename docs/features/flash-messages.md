---
title: Flash Messages
sidebar:
  order: 4
---

# Flash Messages

Flash messages give your users immediate feedback. A save confirmation, a validation error, a heads-up that something happened — flash handles all of it.

## Setting Flash Messages

Call `put_flash` on the socket with a string key and any value:

```python
async def handle_event(self, event, payload, socket):
    if event == "save":
        await save_record(payload)
        socket.put_flash("info", "Record saved.")
```

The key is a convention you choose. Most apps use `info` and `error`, but you can use whatever makes sense:

```python
socket.put_flash("info", "Settings updated.")
socket.put_flash("error", "Could not connect to server.")
socket.put_flash("warning", "Your session expires in 5 minutes.")
```

Values can be anything — strings, dicts, dataclasses. The framework stores them; your template decides how to render them.

```python
socket.put_flash("error", {
    "title": "Validation failed",
    "fields": ["email", "name"]
})
```

Each key holds one value. Setting the same key again replaces the previous message:

```python
socket.put_flash("info", "First")
socket.put_flash("info", "Second")  # "First" is gone
```

## Rendering Flash Messages

Flash is automatically available in every template as `flash`:

```html
{% if flash.info %}
<div class="flash-info" id="flash-info">
  {{ flash.info }}
</div>
{% endif %}

{% if flash.error %}
<div class="flash-error" id="flash-error">
  {{ flash.error }}
</div>
{% endif %}
```

## Dismissing Flash Messages

Users expect to dismiss notifications. The built-in `lv:clear-flash` event handles this cleanly.

Push the event with the key to clear, and chain a JS command for an instant visual response:

```html
<div
  class="flash-info"
  id="flash-info"
  phx-click="{{ js|js.push:'lv:clear-flash', {'key': 'info'}|js.hide:'#flash-info' }}"
>
  {{ flash.info }}
</div>
```

This does two things in one click: hides the element immediately on the client (no round-trip flicker) and tells the server to clear the flash so it stays gone on the next render.

To clear all flash messages at once, omit the key:

```python
socket.clear_flash()        # clear everything
socket.clear_flash("info")  # clear just one key
```

## Complete Example

A form with success and error feedback:

```python
from dataclasses import dataclass
from pyview import LiveView, LiveViewSocket

@dataclass
class Context:
    name: str = ""

class SettingsLiveView(LiveView[Context]):
    async def mount(self, socket: LiveViewSocket[Context], _session):
        socket.context = Context()

    async def handle_event(self, event, payload, socket):
        if event == "save":
            name = payload.get("name", "").strip()
            if not name:
                socket.put_flash("error", "Name cannot be blank.")
                return
            socket.context.name = name
            socket.put_flash("info", "Settings saved.")
```

```html
{% if flash.error %}
<p class="error"
   id="flash-error"
   phx-click="{{ js|js.push:'lv:clear-flash', {'key': 'error'}|js.hide:'#flash-error' }}">
  {{ flash.error }}
</p>
{% endif %}

{% if flash.info %}
<p class="success"
   id="flash-info"
   phx-click="{{ js|js.push:'lv:clear-flash', {'key': 'info'}|js.hide:'#flash-info' }}">
  {{ flash.info }}
</p>
{% endif %}

<form phx-submit="save">
  <input type="text" name="name" value="{{ name }}" />
  <button type="submit">Save</button>
</form>
```
