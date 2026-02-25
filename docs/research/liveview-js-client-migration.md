# LiveView JS Client Migration: v0.20.17 → v1.1.24

## Overview

PyView currently uses `phoenix_live_view` JS client **v0.20.17** (the last pre-1.0
release). The latest is **v1.1.24**. This document catalogs every breaking change,
new feature, and protocol-level difference between the two versions, and provides
a staged migration plan.

---

## Breaking Changes (Server Must Change)

These are things that **will break** if you simply swap the JS client without
updating the Python server.

### 1. Comprehension Format: `"d"` → `"k"` + `"kc"` (CRITICAL)

The biggest protocol change. Comprehensions (for loops in templates) use an
entirely different wire format.

**Old (v0.20.17) — `"d"` (dynamics), flat array:**
```json
{
  "s": ["<li>", "</li>"],
  "d": [["item 1"], ["item 2"]]
}
```

**New (v1.1.24) — `"k"` (keyed), indexed object with count:**
```json
{
  "s": ["<li>", "</li>"],
  "k": {
    "0": {"0": "item 1"},
    "1": {"0": "item 2"},
    "kc": 2
  }
}
```

The new format also supports **keyed diff operations** for updates:
- **In-place diff**: `"2": {"0": "new_val"}` — item at index 2 changed
- **Move only**: `"3": 1` — item moved from old index 1 to new index 3, no changes
- **Move + diff**: `"3": [1, {"0": "new_val"}]` — moved from index 1 to 3, with changes

**PyView files that need changes:**
- `pyview/template/live_view_template.py:254-268` — `_process_list()` emits `"d"` key
- `pyview/template/live_view_template.py:296-313` — t-string comprehension emits `"d"`
- `pyview/template/render_diff.py:9-51` — diff logic reads/writes `"d"` key
- `pyview/template/template_view.py:55-76` — server-side rendering reads `"d"` key

### 2. `phx-feedback-for` / `phx-feedback-group` Removed

The entire form feedback system was removed:
- `PHX_FEEDBACK_FOR` (`"feedback-for"`) — gone
- `PHX_FEEDBACK_GROUP` (`"feedback-group"`) — gone
- `PHX_NO_FEEDBACK_CLASS` (`"phx-no-feedback"`) — gone

Replaced by server-side `used_input?/1` logic in Phoenix. PyView needs to decide
whether to implement equivalent server-side logic or drop the feature.

**PyView files affected:**
- Any templates using `phx-feedback-for` (e.g., `plants.html`)
- `pyview/static/assets/app.js` — the bundled client references these constants

### 3. `data-phx-ref` Split into Three Attributes

The single `data-phx-ref` attribute was replaced by a three-attribute ref system:

| Old | New | Purpose |
|-----|-----|---------|
| `data-phx-ref` | `data-phx-ref-loading` | Tracks loading state (CSS classes) |
| | `data-phx-ref-lock` | Locks element from DOM patches during round-trip |
| `data-phx-ref-src` | `data-phx-ref-src` | Unchanged — identifies source view |

The new `ElementRef` class manages these independently, allowing visual feedback
(loading indicators) to be separated from DOM mutation locking.

**PyView files affected:**
- `pyview/ws_handler.py` — anywhere refs are set on responses
- `pyview/js.py` — JS commands that set ref attributes

### 4. Upload Config Format Changed

The upload preflight response must now send a config object instead of a bare
chunk size:

**Old:** `chunk_size: 64000`
**New:** `{ chunk_size: 64000, chunk_timeout: 10000 }`

**PyView files affected:**
- `pyview/uploads.py` — preflight response format

### 5. `phx-page-loading` Attribute Removed

Replaced by `page_loading: true` option in `JS.push/2`.

### 6. `phx-capture-click` Removed

Fully removed (deprecated since v0.17.0). Use `phx-click-away` instead.

### 7. JS Command Signatures Changed

Every `exec_*` method gained an `e` (event) parameter as the first argument.
The top-level `JS.exec()` changed from:
```
exec(eventType, phxEvent, view, sourceEl, defaults)
```
to:
```
exec(e, eventType, phxEvent, view, sourceEl, defaults)
```

This is internal to the JS client and doesn't directly affect the Python server's
`js.py`, but any serialized JS commands that depend on execution order may behave
differently.

### 8. `JS.push` Values on Form Events

`JS.push` values are now properly sent on form events (was a bug in 0.20.17).
Code that worked around this bug may need adjustment.

### 9. Component Attrs: `data-phx-view` Added

Components now get a `data-phx-view` attribute stamped on their root:
```js
const attrs = { [PHX_COMPONENT]: cid, [PHX_VIEW_REF]: this.viewId };
```

This is set client-side and shouldn't break the server, but the server should be
aware it exists.

---

## New Features Worth Adopting

### 1. `onDocumentPatch` DOM Callback (View Transitions)

The primary motivation for this migration. Wraps DOM patches so you can integrate
the View Transition API:

```javascript
dom: {
  onDocumentPatch(start) {
    document.startViewTransition(() => start());
  }
}
```

### 2. `JS.ignore_attributes` Command

Lets elements opt out of server-driven attribute updates. Critical for
browser-controlled attributes like `open` on `<dialog>` and `<details>`:

```html
<details phx-mounted={JS.ignore_attributes(["open"])}>
```

**PyView server change:** Add `ignore_attrs` to `js.py`.

### 3. Keyed Comprehension Diffs (Per-Item Tracking)

The `"k"`/`"kc"` format enables diffing individual items in a comprehension
instead of re-sending the entire list. This is a **major performance improvement**
for lists — reordering items now sends only move instructions.

### 4. `blocking: false` on Transitions

JS commands with transitions can now run non-blocking, preventing CSS animations
from holding up server-driven DOM patches.

**PyView server change:** Add `blocking` option to transition commands in `js.py`.

### 5. Programmable JS Commands in Hooks (`this.js()`)

Hooks now have `this.js()` returning an object with methods (`show`, `hide`,
`addClass`, `push`, etc.) that integrate with server DOM patching. Previously,
raw DOM manipulation from hooks would be overwritten on next patch.

### 6. `pushEvent` Returns a Promise

```javascript
// Old: callback-based
this.pushEvent("save", payload, (reply) => { ... });

// New: promise-based (callback still works)
const reply = await this.pushEvent("save", payload);
```

### 7. Structured `to` Selectors

JS commands can now target elements via `closest` and `inner` traversal:

```json
{"to": {"closest": ".parent"}}
{"to": {"inner": ".child"}}
```

**PyView server change:** Update `js.py` to support structured `to` args.

### 8. `phx-drop-target-active` CSS Class

Drop targets automatically get a `phx-drop-target-active` class during drag-over.
Free UX improvement for upload zones.

### 9. TypeScript Type Definitions

The JS client ships TypeScript types. Better DX for PyView users writing hooks.

### 10. Portals / Teleportation

`<.portal>` component teleports content to another DOM location. Would require
significant server-side work if PyView wants to support it.

### 11. DOM Patching Performance (3-30x)

Significant morphdom improvements landed in v0.20.2+ and were carried into 1.x.

### 12. Stream Bug Fixes

Fixed exponential memory growth in stream containers with forms (v1.0.15), plus
many form recovery fixes across the 1.0.x series.

---

## Things PyView Can Skip (Don't Need)

- **Colocated Hooks** — deeply tied to Elixir's compilation pipeline
- **Runtime Hooks** (`data-phx-runtime-hook`) — uses `window.phx_hook_*` convention,
  nice but not essential
- **Client/Server Version Mismatch Warning** — PyView has its own version; suppress
  or override this check
- **History Position Tracking** (`phx:nav-history-position`) — only relevant if
  PyView implements forward/backward navigation direction detection
- **Reload Status Cookie** (`__phoenix_reload_status__`) — Phoenix-specific dev
  experience feature

---

## Staged Migration Plan

### Phase 0: Pre-Migration (Do Now, On Current v0.20.17)

These changes make the migration safer by adding test coverage and isolating
protocol concerns.

#### 0a. Add Protocol-Level Tests

Write tests that verify the **wire format** PyView sends for each message type.
These tests should assert on the actual JSON structure, not just the rendered HTML:

```python
def test_comprehension_wire_format():
    """Verify the exact JSON structure sent for a for-loop."""
    template = Template("{% for item in items %}<li>{{ item }}</li>{% endfor %}")
    tree = template.tree_parts({"items": ["a", "b"]})
    # Assert the comprehension key and structure
    assert "d" in tree["0"]  # will change to "k" in migration
    assert tree["0"]["d"] == [["a"], ["b"]]
```

These tests serve as a **contract spec** — when you change the format to `"k"`,
update the assertions and verify the JS client accepts them.

#### 0b. Extract Comprehension Serialization into One Place

Currently, comprehension format `"d"` is emitted in three separate places:
- `live_view_template.py:_process_list()` (lines 254, 267)
- `live_view_template.py` t-string path (line 296)

And read in two places:
- `template_view.py:_value_to_html()` (lines 57-76)
- `render_diff.py:compute_diff()` (lines 9-51)

Refactor so there's a single `ComprehensionFormat` class or module that handles
serialization and deserialization. Then the migration is a one-place change.

#### 0c. Add End-to-End Browser Tests

The highest-confidence way to verify the migration works. Use Playwright or
similar to test:
- Form submission + validation (the #1 risk area)
- File uploads (internal and S3)
- Streams (append, prepend, delete, reset)
- Infinite scroll
- LiveComponents
- JS hooks (InfiniteScroll, KanbanBoard, ParksMap)

Even a small smoke test suite that connects a real browser to a running PyView
instance and clicks through the example views would catch most regressions.

#### 0d. Add a JS Build Script

Currently the bundle at `pyview/static/assets/app.js` appears to be a pre-built
artifact with no documented build process. Set up an explicit build step:

```json
// package.json scripts
{
  "scripts": {
    "build": "esbuild js/app.js --bundle --outdir=../static/assets"
  }
}
```

This makes it reproducible to rebuild the bundle after changing the
`phoenix_live_view` dependency version.

#### 0e. Remove `phx-feedback-for` Usage

Since it's removed in 1.x, migrate away from it now while still on 0.20.17.
Replace with explicit CSS class management or a PyView-specific validation
attribute.

### Phase 1: Protocol Changes (Server-Side Only)

Make the Python server emit the new wire format, then swap the JS client.
Do these together in a single branch.

#### 1a. Comprehension Format: `"d"` → `"k"` + `"kc"`

Update `ComprehensionFormat` (from Phase 0b) to emit:

```python
# Old
{"s": statics, "d": [[v1, v2], [v3, v4]]}

# New
{"s": statics, "k": {"0": {"0": v1, "1": v2}, "1": {"0": v3, "1": v4}, "kc": 2}}
```

Update `render_diff.py` to diff keyed comprehensions properly. For the first pass,
don't implement move tracking — just emit in-place diffs.

#### 1b. Update Ref System

Replace `data-phx-ref` with `data-phx-ref-loading` and `data-phx-ref-lock`
wherever the server sets ref attributes. Audit `ws_handler.py` and `js.py`.

#### 1c. Upload Config Format

Change preflight response to include `chunk_timeout` alongside `chunk_size`.

#### 1d. Update Version Constant

Change `PHOENIX_LIVEVIEW_VERSION` in `ws_handler.py` from `"0.20.17"` to match
the new client version.

#### 1e. Rebuild JS Bundle

Update `package.json` to `"phoenix_live_view": "^1.1.24"`, install, and rebuild
the `app.js` bundle.

### Phase 2: New Features (Incremental)

After Phase 1 lands and is stable, adopt new features one at a time:

1. **View Transition API** — now just `onDocumentPatch` in the LiveSocket config
2. **`JS.ignore_attributes`** — add to `js.py`
3. **Structured `to` selectors** — add `closest`/`inner` to `js.py`
4. **`blocking: false`** — add to transition commands in `js.py`
5. **Keyed move tracking** — implement move detection in `render_diff.py` for
   efficient list reordering

### Phase 3: Optional Advanced Features

- **Portals** — significant server-side work
- **TypeScript types** — no server work, just DX improvement
- **`jsQuerySelectorAll` callback** — useful for shadow DOM support

---

## Risk Assessment

| Change | Risk | Mitigation |
|--------|------|------------|
| Comprehension format `"d"` → `"k"` | **HIGH** — breaks all loops | Protocol tests (Phase 0a), extract format (Phase 0b) |
| `phx-feedback-for` removal | **MEDIUM** — affects form validation UX | Remove usage pre-migration (Phase 0e) |
| Ref system split | **MEDIUM** — affects loading states | Audit all ref usage in ws_handler.py |
| Upload config format | **LOW** — small change, isolated | Unit test upload preflight |
| Form submission changes | **LOW-MEDIUM** — many 1.0.x bugfixes | E2E browser tests (Phase 0c) |
| JS command signature `(e, ...)` | **LOW** — internal to JS client | No server changes needed |
| Stream memory fix | **POSITIVE** — fixes a bug | Free improvement |

---

## What You Get

After migration, PyView gains:

1. **View Transition API support** via `onDocumentPatch` (the original motivation)
2. **3-30x faster DOM patching** (landed in 0.20.2+, carried to 1.x)
3. **Per-item comprehension diffs** — lists only send changed items, not the whole list
4. **Stream memory leak fix** — exponential growth in stream containers with forms
5. **Better form recovery** — 10+ bugfixes across the 1.0.x series
6. **`JS.ignore_attributes`** — critical for `<dialog>`, `<details>`, and other
   browser-controlled elements
7. **Promise-based `pushEvent`** — cleaner async hook code
8. **TypeScript types** — better IDE support for hook authors
9. **Non-blocking transitions** — CSS animations don't hold up DOM patches
10. **Structured selectors** — `closest`/`inner` targeting in JS commands

---

## Files to Change (Complete List)

### Python Server
- `pyview/template/live_view_template.py` — comprehension format
- `pyview/template/render_diff.py` — diff computation for comprehensions
- `pyview/template/template_view.py` — server-side rendering of comprehensions
- `pyview/ws_handler.py` — version constant, ref attributes, message handling
- `pyview/uploads.py` — preflight config format
- `pyview/js.py` — new commands, structured selectors, blocking option

### JavaScript
- `pyview/assets/package.json` — bump `phoenix_live_view` version
- `pyview/assets/js/app.js` — update LiveSocket config (add `onDocumentPatch`, etc.)
- `pyview/static/assets/app.js` — rebuilt bundle

### Templates
- Any template using `phx-feedback-for` or `phx-feedback-group`
- Any template using `phx-capture-click` (use `phx-click-away` instead)

### Tests
- Add protocol-level wire format tests
- Add E2E browser tests for forms, uploads, streams, hooks
