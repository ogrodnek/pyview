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

### 5. Stream Insert Tuples Gained 4th Element

Stream inserts changed from `[key, streamAt, limit]` to
`[key, streamAt, limit, updateOnly]`. The `updateOnly` flag means "only update
this item if it already exists in the DOM; don't add it."

Old format still works (4th element defaults to `undefined`/falsy), but you
can't use the `update_only` stream feature without it.

**PyView files affected:**
- `pyview/template/live_view_template.py` — stream metadata construction
- `pyview/template/render_diff.py` — stream diff emission

### 6. `data-phx-view` Required on Components

Components now must carry `data-phx-view="<view_id>"` so the client can locate
them via `document.querySelector('[data-phx-view="..."][data-phx-component="..."]')`
instead of walking up ancestors. The old `withinSameLiveView` traversal is gone.

**PyView files affected:**
- Component rendering — must stamp `data-phx-view` on component root elements

### 7. Events Can Fire Before DOM Patch

Server-pushed events can now include a third element to control dispatch timing:
- `[event, payload]` — dispatched **after** the DOM patch (same as before)
- `[event, payload, true]` — dispatched **before** the DOM patch

This is what enables `onDocumentPatch` + view transitions — the server signals
a transition type via a pre-patch event, then the client wraps the patch.

**PyView files affected:**
- `pyview/ws_handler.py` — event dispatch format (optional, only if implementing
  pre-patch events)

### 8. Form Event Payload: `_target` Moved to `meta` Field (CRITICAL)

**This is the second most impactful breaking change**, directly affecting form handling.

In v0.20.17, `_target` and other metadata were mixed into the URL-encoded `value`
string:
```
// Old payload
{
  "type": "form",
  "event": "validate",
  "value": "name=John&_target=name",
  "cid": null
}
```

In v1.1.24, `_target` and metadata are in a **separate `meta` key**:
```json
{
  "type": "form",
  "event": "validate",
  "value": "name=John",
  "meta": {"_target": "name"},
  "cid": null
}
```

**This applies to both `phx-change` and `phx-submit` events.** The `value` field
now contains *only* form data; metadata is never appended to the URL-encoded string.

**PyView code that breaks:**
- `pyview/ws_handler.py:179` — `parse_qs(value)` currently extracts `_target` from
  the URL-encoded form string. After migration, `_target` will no longer be in
  `value`. The server must read `payload["meta"]["_target"]` instead.

**Recommended fix:**
```python
if payload["type"] == "form":
    value = parse_qs(value)
    meta = payload.get("meta", {})
    target = meta.get("_target")
    # _target is no longer in `value` — it's in `meta`
```

### 9. `_unused_` Prefix Replaces `phx-feedback-for`

The client now sends `_unused_` prefixed keys for form fields the user hasn't
interacted with (not focused, not submitted). This replaces the removed
`phx-feedback-for` mechanism.

For example, if a form has fields `user[name]` and `user[email]` but the user
only typed in `name`, the form data will contain:
```
user[name]=John&user[email]=&user[_unused_email]=
```

The `_unused_` prefix tells the server "the user hasn't touched this field yet,
don't show validation errors for it." This is how Phoenix's `used_input?/1`
works on the server side.

**PyView impact:**
- If PyView wants to support "only validate touched fields" (like Phoenix's
  `used_input?/1`), it should strip `_unused_` prefixed keys from the parsed
  form data and use them to track which fields need validation feedback.
- If PyView doesn't need this feature, the `_unused_` keys can be ignored
  (they won't cause harm, just extra data in the form payload).

### 10. `phx-page-loading` Attribute Removed

Replaced by `page_loading: true` option in `JS.push/2`.

### 11. `phx-capture-click` Removed

Fully removed (deprecated since v0.17.0). Use `phx-click-away` instead.

### 12. JS Command Signatures Changed

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

### 13. `JS.push` Values on Form Events

`JS.push` values are now properly sent on form events (was a bug in 0.20.17).
Code that worked around this bug may need adjustment.

### 14. DOM Locking During Server Round-Trips

The new `ElementRef` + `PHX_REF_LOCK` system clones the DOM subtree of locked
elements and applies server patches to the **clone** instead of the real DOM.
When the server acknowledges (undo), the clone is morphed back in. This prevents
flickering during animations and race conditions.

The server needs to cooperate with this by using the split ref attributes
(see item #3). The DOMPatch constructor now accepts `opts.undoRef` to signal
which ref is being acknowledged.

### 15. Join Payload Now Includes `sticky` and `_mount_attempts`

The client now sends additional fields in the channel join:
- `sticky: true/false` — whether the LiveView element has `phx-sticky` attribute
- `_mount_attempts` — separate from `_mounts`, tracks total join attempts

The join response also accepts an optional `pid` field (used for debug attributes).

**PyView impact:** These are additive and backwards-compatible. PyView can ignore
`sticky` and `_mount_attempts` safely. Optionally, send `pid` in join responses
for debugging.

### 16. Redirect Payload Supports `reloadToken`

Redirects can now include a `reloadToken` field, and join error responses with
`reason: "reload"` include a `token`. This enables the client to distinguish
server-initiated reloads from user navigations.

**PyView impact:** Low risk — additive feature. Only needed if PyView implements
reload tracking.

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

#### 0c. Add Form Event Parsing Tests

Write tests that verify how PyView parses form event payloads. These should
assert on both the current format (for regression) and document the expected
new format:

```python
def test_form_event_parsing_current():
    """Current v0.20.17: _target is in URL-encoded value."""
    payload = {
        "type": "form",
        "event": "validate",
        "value": "name=John&_target=name",
        "cid": None
    }
    # parse_qs extracts _target from value
    parsed = parse_qs(payload["value"])
    assert "_target" in parsed

def test_form_event_parsing_v1():
    """After migration: _target is in meta, not in value."""
    payload = {
        "type": "form",
        "event": "validate",
        "value": "name=John",
        "meta": {"_target": "name"},
        "cid": None
    }
    parsed = parse_qs(payload["value"])
    assert "_target" not in parsed
    assert payload["meta"]["_target"] == "name"
```

#### 0e. Add End-to-End Browser Tests

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

#### 0f. Add a JS Build Script

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

#### 0g. Remove `phx-feedback-for` Usage

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

#### 1b. Form Event `_target` Extraction

Update `ws_handler.py` to read `_target` from `payload["meta"]` instead of from
the URL-encoded `value` string. Also handle `_unused_` prefixed keys:

```python
# In the "event" handler, after parse_qs:
if payload["type"] == "form":
    value = parse_qs(payload["value"])
    meta = payload.get("meta", {})
    # _target is now in meta, not in the form value string
    target = meta.get("_target")
    # Optionally strip _unused_ keys if not implementing used_input?
    value = {k: v for k, v in value.items() if not k.startswith("_unused_")}
```

This is a small but critical change — without it, all `phx-change` events will
lose their `_target` information.

#### 1d. Update Ref System

Replace `data-phx-ref` with `data-phx-ref-loading` and `data-phx-ref-lock`
wherever the server sets ref attributes. Audit `ws_handler.py` and `js.py`.

#### 1e. Upload Config Format

Change preflight response to include `chunk_timeout` alongside `chunk_size`.

#### 1f. Update Version Constant

Change `PHOENIX_LIVEVIEW_VERSION` in `ws_handler.py` from `"0.20.17"` to match
the new client version.

#### 1g. Rebuild JS Bundle

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
| Form `_target` moved to `meta` field | **HIGH** — breaks all form handling | Fix `parse_qs` in ws_handler.py (Phase 1a-bis) |
| `data-phx-view` on components | **HIGH** — components won't be found without it | Audit component rendering |
| `phx-feedback-for` removal | **MEDIUM** — affects form validation UX | Remove usage pre-migration (Phase 0g) |
| `_unused_` prefix in form data | **MEDIUM** — extra keys in parsed form data | Decide: support `used_input?` or ignore |
| Ref system split | **MEDIUM** — affects loading states | Audit all ref usage in ws_handler.py |
| Stream 4-element tuples | **LOW** — old format still works | Only breaks if using `update_only` |
| Upload config format | **LOW** — small change, isolated | Unit test upload preflight |
| Pre-patch event dispatch | **LOW** — additive, opt-in | No change needed unless using view transitions |
| Join payload (`sticky`, `_mount_attempts`) | **LOW** — additive fields | Ignore or handle gracefully |
| Redirect `reloadToken` | **LOW** — additive field | Ignore safely |
| JS command signature `(e, ...)` | **LOW** — internal to JS client | No server changes needed |
| DOM locking (`PHX_REF_LOCK`) | **LOW** — client-side behavior | Works with split ref attributes |
| Stream memory fix | **POSITIVE** — fixes a bug | Free improvement |
| 3-30x faster DOM patching | **POSITIVE** — perf improvement | Free improvement |

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
- `pyview/ws_handler.py` — version constant, ref attributes, form `_target`/`meta` parsing, message handling
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

---

## Current Test Coverage Assessment

PyView has **402 tests** (pytest, Python 3.11) with strong coverage in some areas
and critical gaps that directly impact migration confidence.

### Well-Tested (Good Migration Confidence)

| Area | Tests | Notes |
|------|-------|-------|
| Template rendering (Ibis) | 14 | `tree()`, `render()`, auto-escaping, loops, conditionals |
| Diff calculation | 14 | `calc_diff()` including comprehension `"d"` key diffs |
| Stream operations | 31 | `Stream` class, wire format, insert/delete/reset |
| Stream + template integration | 29 | Both Ibis and t-string paths |
| LiveView templates (t-string) | 32 | `LiveViewTemplate.process()`, lists, components |
| Components | 70 | Base, manager, lifecycle, slots (statics sharing skipped) |
| Binding / params / DI | 123 | Binder, converters, params, injectables, helpers |
| JS commands | 17 | show/hide/push/dispatch/add_class, chaining |

### Critical Gaps (Must Fix Before Migration)

| Gap | Risk | What to Add |
|-----|------|-------------|
| **WebSocket handler** (`ws_handler.py`) | **CRITICAL** | Zero tests for the 467-line handler that manages join/event/patch/leave/upload flows |
| **Wire protocol envelope** | **CRITICAL** | No tests for complete `[joinRef, msgRef, topic, "phx_reply", {...}]` JSON structure |
| **Form event parsing** | **CRITICAL** | `parse_qs(value)` + `_target` extraction untested; this is exactly what changes in v1.1 |
| **Message parsing** (`phx_message.py`) | **CRITICAL** | `parse_message()` for text and binary frames untested |
| **Uploads** (`uploads.py`) | **HIGH** | 577 lines, zero tests. Upload preflight format changes in v1.1 |
| **Component wire format** (`"c"` key) | **HIGH** | Component rendering inside `rendered["c"]` untested at wire level |
| **`diff()` integration** | **HIGH** | `ConnectedLiveViewSocket.diff()` state management untested |
| **Statics sharing** | **HIGH** | All 8 tests skipped (reverted due to diff bug) |
| **Navigation messages** | **MEDIUM** | `push_navigate`, `replace_navigate`, `redirect` untested |
| **`push_event` wire format** | **MEDIUM** | Hook events (`"e"` key) untested |
| **Changesets** | **LOW** | 67-line module, zero tests |
| **E2E browser tests** | **NONE** | No Playwright/Selenium/browser automation exists |

### Priority Test Plan for Pre-Migration

The most impactful tests to add (in order):

1. **Wire protocol envelope test** — Verify the exact JSON the server sends for
   `phx_join` responses and `diff` responses. This is the single most useful test
   for migration confidence.

2. **Form event parsing test** — Verify `_target` extraction from form events.
   Write tests for both current format (`_target` in URL-encoded value) and new
   format (`_target` in `meta` field).

3. **Comprehension wire format test** — Verify the `"d"` key structure at the
   response level, then update to `"k"`/`"kc"` during migration.

4. **Upload preflight test** — Verify the `allow_upload` response format,
   especially the config object.

5. **Component rendering test** — Verify `"c"` key structure in rendered output,
   including ROOT flag and CID references.

6. **Smoke-test E2E suite** — Even 5-10 Playwright tests covering form submit,
   upload, stream append, and infinite scroll would catch most regressions.
