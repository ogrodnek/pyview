---
title: Flash Messages
sidebar:
  order: 4
---

# Flash Messages

Flash messages provide temporary feedback to users — save confirmations, validation errors, status updates. They live on the socket and are automatically available in your templates.

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

Users expect to dismiss notifications. The built-in `lv:clear-flash` event handles this — just use `phx-click` with `phx-value-key`:

```html
<div class="flash-info"
     phx-click="lv:clear-flash" phx-value-key="info">
  {{ flash.info }}
</div>
```

That's it. The click sends `lv:clear-flash` to the server with `{"key": "info"}`, the framework clears it, and the next render removes the element.

To clear all flash messages at once from the server side, omit the key:

```python
socket.clear_flash()        # clear everything
socket.clear_flash("info")  # clear just one key
```

<details>
<summary>Adding a client-side transition</summary>

If you want an instant hide before the server round-trip, chain a JS command:

```html
<div class="flash-info" id="flash-info"
     phx-click='{{ js.push("lv:clear-flash", {"key": "info"}) | js.hide("#flash-info") }}'>
  {{ flash.info }}
</div>
```

This hides the element immediately on the client and clears the flash on the server. In practice the websocket round-trip is fast enough that the simple `phx-value-key` approach works well.

</details>

## Complete Example

A form with success and error feedback using t-string templates:

```python
from dataclasses import dataclass
from string.templatelib import Template

from pyview import LiveView, LiveViewSocket
from pyview.events import AutoEventDispatch, event
from pyview.meta import PyViewMeta
from pyview.template.template_view import TemplateView
from typing import Optional


@dataclass
class Context:
    name: str = ""


class SettingsLiveView(AutoEventDispatch, TemplateView, LiveView[Context]):
    async def mount(self, socket: LiveViewSocket[Context], _session):
        socket.context = Context()

    @event
    async def save(self, name: Optional[str], socket: LiveViewSocket[Context]):
        if not name:
            socket.put_flash("error", "Name cannot be blank.")
            return

        socket.context.name = name
        socket.clear_flash()
        socket.put_flash("info", f"Saved — welcome, {name}!")


    def template(self, assigns: Context, meta: PyViewMeta) -> Template:
        name = assigns.name

        banners = [
            t'<p class="{key}" phx-click="lv:clear-flash" phx-value-key="{key}">{msg}</p>'
            for key, msg in meta.flash.items()
        ]

        return t"""
        {banners}

        <form phx-submit="save">
          <input type="text" name="name" value="{name}" />
          <button type="submit">Save</button>
        </form>
        """
```
