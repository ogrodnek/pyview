---
title: JavaScript Interop
sidebar:
  order: 5
---

# JavaScript Interop

PyView uses the Phoenix LiveView JavaScript client. You can customize its behavior through global configuration.

## Hooks

Hooks let you integrate third-party JavaScript libraries with your LiveView. Use them when you need to:

- Initialize a JS library on an element (maps, charts, rich text editors)
- Handle client-side interactions that need server communication (drag and drop, drawing)
- Manage JS library lifecycle as elements are added/removed from the DOM

### Defining Hooks

Define hooks on `window.Hooks` before pyview's script loads:

```javascript
window.Hooks = window.Hooks ?? {};

window.Hooks.MyMap = {
  mounted() {
    // Element added to DOM - initialize your library
    this.map = new MapLibrary(this.el);
  },
  updated() {
    // Element's attributes changed - refresh if needed
    this.map.refresh();
  },
  destroyed() {
    // Element removed - cleanup
    this.map.cleanup();
  }
};
```

Attach hooks to elements with `phx-hook`. The element must have a unique `id`:

```html
<div id="map" phx-hook="MyMap" data-lat="{{lat}}" data-lng="{{lng}}"></div>
```

### Hook Callbacks

- `mounted()` - Element added to DOM
- `updated()` - Element's attributes/content changed
- `destroyed()` - Element removed from DOM
- `beforeUpdate()` - Before DOM update
- `disconnected()` - Socket disconnected
- `reconnected()` - Socket reconnected

### Communicating with the Server

Push events from JavaScript to your LiveView's `handle_event`:

```javascript
// In your hook
this.pushEvent("marker-clicked", { lat: 45.5, lng: -122.6 });
```

Handle events pushed from the server via `socket.push_event()`:

```javascript
// In your hook's mounted()
this.handleEvent("highlight-marker", ({ id }) => {
  this.map.highlightMarker(id);
});
```

### Accessing Element Data

Read data attributes from `this.el`:

```javascript
mounted() {
  const parks = JSON.parse(this.el.dataset.parks);
  parks.forEach(park => this.map.addMarker(park));
}
```

### Examples

**Maps with Leaflet** - The [maps example](https://github.com/ogrodnek/pyview/tree/main/examples/views/maps) shows bidirectional communication: clicking a marker pushes an event to the server, and selecting from a list pushes an event back to pan the map.

**Drag and Drop with SortableJS** - The [kanban example](https://github.com/ogrodnek/pyview/tree/main/examples/views/kanban) uses hooks to integrate SortableJS, sending task reorder events to the server when cards are dragged between columns.

## LiveSocket Configuration

For advanced customization, define `window.LiveViewConfig` before pyview's script loads.

### Via Root Template

Use the `head_content` parameter of `defaultRootTemplate`:

```python
from pyview.template.root_template import defaultRootTemplate
from markupsafe import Markup

root_template = defaultRootTemplate(
    head_content=Markup("""
        <script>
        window.LiveViewConfig = {
            dom: {
                onBeforeElUpdated(fromEl, toEl) {
                    // Custom logic here
                }
            }
        };
        </script>
    """)
)
```

### Available Options

| Option | Description |
|--------|-------------|
| `hooks` | Additional hooks (merged with `window.Hooks`) |
| `params` | Additional connection params |
| `uploaders` | Custom file upload handlers |
| `dom` | DOM update callbacks |

### Full Attribute Sync for `phx-update="ignore"`

Phoenix's `phx-update="ignore"` preserves content but only syncs `data-*` attributes. For web components that need all attributes synced (like `class`, `aria-*`, etc.) while preserving content, use `LiveViewConfig`:

```javascript
window.LiveViewConfig = {
  dom: {
    onBeforeElUpdated(fromEl, toEl) {
      if (fromEl.getAttribute("phx-update") === "ignore") {
        for (const { name, value } of toEl.attributes) {
          if (fromEl.getAttribute(name) !== value) {
            fromEl.setAttribute(name, value);
          }
        }
        for (const { name } of [...fromEl.attributes]) {
          if (!toEl.hasAttribute(name)) {
            fromEl.removeAttribute(name);
          }
        }
      }
    }
  }
};
```

This syncs all attributes for every `phx-update="ignore"` element. For selective behavior, add a custom attribute check:

```javascript
// Only sync when data-sync-attrs is present
if (fromEl.getAttribute("phx-update") === "ignore" &&
    fromEl.hasAttribute("data-sync-attrs")) {
  // ... sync attributes
}
```

```html
<my-component phx-update="ignore" data-sync-attrs class="{{state}}">
  <!-- Content preserved, all attributes synced -->
</my-component>
```

### Update Mode Comparison

| Mode | Attributes | Content |
|------|------------|---------|
| (default) | All synced | Synced |
| `ignore` | Only `data-*` | Preserved |
| `stream` | Synced | Managed |

## Debugging

The LiveSocket instance is available on `window.liveSocket`:

```javascript
liveSocket.enableDebug()
liveSocket.enableLatencySim(1000)
liveSocket.disableLatencySim()
```
