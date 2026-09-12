# Phoenix LiveView JS client internals for forms (v0.20.17 vs 1.0/1.1) — what pyview inherits — versions researched: phoenix_live_view tag v0.20.17 (`assets/js/phoenix_live_view/*.js`), tag v1.0.0, main @ 7f06d340 (2026-09-11, = 1.2.11, `assets/js/phoenix_live_view/*.ts`) — researched 2026-09-12

All paths below are relative to `/tmp/claude-0/-home-user-pyview/4e51d174-6d71-5bea-a6e4-de1b93546ddb/scratchpad/repos/phoenix_live_view`. `V0 =` `git show v0.20.17:assets/js/phoenix_live_view/…`; `main =` the working tree (TypeScript). Python output below was actually run (`scratchpad/phx_parse_demo.py`).

## TL;DR (5-8 bullets)

- **The wire payload is a plain `application/x-www-form-urlencoded` string**, built with `new FormData(form)` → `URLSearchParams` (V0 `view.js` L60-108). Names are sent *verbatim* (`user[address][city]`, `user[tags][]`), in DOM order, repeated keys preserved, `File` entries stripped, unchecked checkboxes / disabled inputs absent (browser `FormData` semantics). Nothing on the client "understands" brackets; nesting is entirely a server-side convention (`Plug.Conn.Query.decode`). pyview's `parse_qs(value)` is therefore *lossy*: it drops blank values (`name=`) and keeps flat keys.
- **In 0.20.17, metadata rides *inside* the urlencoded string**: `pushInput` appends `_target=<input.name>` and then every `phx-value-*` attribute of the `<form>` as extra query pairs *after* the fields (V0 `view.js` L105, L1011-1016). From 1.0.6 the client sends them as a separate JSON key `meta: {_target, ...}` on the event (main `view.ts` L2110-2119). pyview will have to accept both shapes to upgrade.
- **`_unused_` params do not exist in 0.20.17.** They arrived with 1.0.0-rc.0 (v1.0.0 `CHANGELOG.md` L234-237) together with the removal of `phx-feedback-for`. Exact format: prefix on the *last* path segment — `user[_unused_name]`, `user[_unused_tags][]`, top-level `_unused_name` (main `view.ts` L76-88, L1981); value is always `""`. "Used" = the input got a `phx-has-focused` private flag (set when a change/input event for it was pushed) or `phx-has-submitted` (set on the whole form on submit) (main `view.ts` L1950-1955, L2736-2739; `dom.ts` L498-503).
- **0.20.17's feedback model is client-only CSS**: after each change reply the client removes `phx-no-feedback` from every `[phx-feedback-for="<name>"]` container matching the touched input (V0 `dom.js` L358-384, `view.js` L1031); on submit reply it does that for all inputs (L1342-1352); during every DOM patch it *re-adds* the class to containers whose inputs were never focused/submitted (V0 `dom_patch.js` L312, `dom.js` L314-356). The server never learns what was touched. This is what pyview ships today.
- **DOM patching protects the focused input**: morphdom's `onBeforeElUpdated` skips the focused form input entirely, merging every attribute *except* `value` (V0 `dom_patch.js` L233-241, `dom.js` L465-474), and restores focus + `selectionStart/End` after the patch (L86-87, L314). Consequence: a server that re-renders `value="…"` for the field the user is typing in is harmless; for *other* inputs the server's value wins (checkboxes re-synced from the `checked` attribute via `syncAttrsToProps`, L497).
- **Free client features pyview already gets** (all in 0.20.17): `phx-debounce="blur"|ms` / `phx-throttle` (default 300ms, flushed on blur and on submit; V0 `dom.js` L214-282, `constants.js` L77-80), `phx-disable-with` + `phx-submit-loading`/`phx-change-loading` classes + readonly-ing all inputs while a submit is in flight (`view.js` L1077-1108), `phx-trigger-action` (client calls native `form.submit()` after the patch that added the attribute, `dom_patch.js` L159-161, L321-326), form recovery after reconnect (re-pushes `phx-auto-recover` or `phx-change` with `_target` = first non-hidden input, `view.js` L1235-1262, L1290-1300), submitter `name=value` injected in DOM order (`view.js` L63-79).
- **Upgrade path 0.20.17 → 1.x is mostly server-side parsing**: same channel messages (`event`/`type:"form"`), but (a) `meta` becomes a JSON key, (b) `_unused_*` keys appear and must be stripped/used, (c) `liveview_version` in the join reply must match the JS bundle or the client logs a console error (both versions check it: V0 `view.js` L282-295, main `view.ts` L457-480), (d) inputs with `phx-change` outside a `<form>` now *throw* client-side (main `view.ts` L2065-2067).

## Mental model & core abstractions

The JS client has no form abstraction at all. Its units are: **bindings** (`phx-change`, `phx-submit`, `phx-value-*`, `phx-target`, `phx-debounce`, …, all prefixed via `liveSocket.binding(kind)`), **`View`** (one per LiveView; owns `pushInput`, `pushFormSubmit`, `pushFormRecovery`, `serializeForm`), **`DOM`** (stateless helpers; per-element "private" data stored on the node — `PHX_HAS_FOCUSED`, `PHX_HAS_SUBMITTED`, debounce cycles), and **`DOMPatch`** (morphdom wrapper with the focused-input/feedback rules).

Event flow for typing in an input inside `<form phx-change="validate">`:

1. `LiveSocket.bindForms()` listens to document-level `input` and `change` (V0 `live_socket.js` L858-889). It resolves `phxEvent = input[phx-change] || input.form[phx-change]`, ignores `type=number` inputs whose `validity.badInput` is set (L866), de-duplicates the browser's `input`+`change` pair (L872-877), then runs `debounce(...)`.
2. Inside the debounced callback it marks the element `PHX_HAS_FOCUSED` (L881) and calls `JS.exec("change", phxEvent, view, input, ["push", {_target: e.target.name, dispatcher}])` (L885) — i.e. `_target` is **the input's `name` attribute, as a string**, unchanged (`user[address][city]`). The Elixir channel later splits that string into `["user","address","city"]` (documented in `guides/client/form-bindings.md` L309-320); the client never does.
3. `View.pushInput` (V0 `view.js` L1006-1044) builds `{type:"form", event, value:<urlencoded>, uploads, cid}` and pushes `"event"` on the channel with a loading ref on the input and the form (`putRef([inputEl, inputEl.form], "change")`).
4. On reply it calls `DOM.showError(inputEl, "phx-feedback-for", "phx-feedback-group")` (L1031) and, if the input is an auto-upload file input, starts uploads.

Submit flow: `bindForms` captures `submit` (L845-856), `e.preventDefault()`, then `JS.exec("submit", …, ["push", {submitter: e.submitter}])` → `View.submitForm` (L1342-1352): flags the form and *every* element `PHX_HAS_SUBMITTED`, blurs the active element, `pushFormSubmit` (L1110-1145) which either schedules the submit until uploads finish, or `disableForm` + push `{type:"form", event, value, cid}`; on reply, `showError` for all inputs and refocus. Note the first `submit` listener (L828-843): a form with `phx-change` but **no** `phx-submit` is treated as an external (HTTP) form: the client disables it and calls `e.target.submit()` natively.

## Data in (naming, parsing, coercion, nested/lists)

`serializeForm(form, metadata, onlyNames = [])` (V0 `view.js` L60-108), verbatim core:

```js
const {submitter, ...meta} = metadata
// … inject <input type=hidden name=submitter.name value=submitter.value> before the submitter (L66-79)
const formData = new FormData(form)
formData.forEach((val, key) => { if(val instanceof File){ toRemove.push(key) } })   // L84-89
toRemove.forEach(key => formData.delete(key))
const params = new URLSearchParams()
for(let [key, val] of formData.entries()){
  if(onlyNames.length === 0 || onlyNames.indexOf(key) >= 0){ params.append(key, val) }  // L93-97
}
for(let metaKey in meta){ params.append(metaKey, meta[metaKey]) }                        // L105
return params.toString()
```

Consequences you can rely on (browser `FormData` spec, not LiveView code):
- **Order** = document order of form-associated elements; the submitter button's `name=value` is inserted at the button's position (that is why they inject a hidden input instead of appending, L63-64). Entries after the fields, in this order: `_target` (only for change), then each `phx-value-*` of the **form element** (`extractMeta(inputEl.form)`, L1011; for a `<form>` `el.value` is `undefined` so no `value` key is added, L968). For submit, `meta` is `extractMeta(formEl)` (L1126, L1136) and `_target` is absent.
- **Repeats**: `select multiple` and `name="x[]"` checkboxes produce repeated keys; `parse_qs`/`parse_qsl` keep them.
- **Unchecked checkbox, `disabled` input, inputs without `name`**: absent. (Phoenix's `<.input type="checkbox">` therefore emits a hidden `name=… value="false"` before the box — server-side concern.)
- **Files**: any `File` entry is deleted *by key* (`formData.delete(key)` removes every value with that name, so a file input named `docs[]` disappears entirely); files go through the separate upload protocol (`uploads:` key, `LiveUploader.serializeUploads`, L1021).
- **`phx-change` on an individual input** (`inputEl.getAttribute(phx-change)` truthy): `onlyNames = [inputEl.name]` → only that input's pairs plus `_target`/meta (L1013-1014). Guide (main `guides/client/form-bindings.md` L104-107) warns such inputs must still be inside a form; main throws `"form events require the input to be inside a form"` (`view.ts` L2065-2067) whereas 0.20.17 would fail on `new FormData(null)` (unverified exact error).
- **Buttons as `_target`**: if the dispatching element is a `<button>` with `phx-change`? No — but `pushInput` sets `meta.submitter = inputEl` when the source is an `HTMLButtonElement` (L1012), which is how `JS.dispatch("change")` from a `<button name="user[drop][]" value="0">` (the `inputs_for` drop pattern) gets its name/value into the change payload. That is the only client mechanic behind LiveView's add/remove-row recipe.
- **`type="number"`** with a non-parsable value is silently not pushed (L866).

Nesting: the client is naming-agnostic. `id`/`name` generation (`user_addresses_0_city` / `user[addresses][0][city]`) is purely server-side (phoenix_html), covered in `research/liveview_forms.md`.

**1.0.6+ change**: `pushInput` no longer appends `_target`/`phx-value-*` to the string. The event becomes `{type:"form", event, value, meta:{_target: opts._target || "undefined", ...phxValues}, uploads, cid}` (main `view.ts` L2107-2119, with the comment explaining that LV ≤1.0.5 sent `_target=undefined` when missing). `pushFormSubmit` likewise sends `meta: meta` (L2315-2322). `serializeForm` in main only takes `{submitter}` (L1889-1895).

## Validation & error model (structure, codes/messages/params, i18n, timing)

The client has **no validation**. Its only "error model" is *feedback gating* — deciding which server-rendered error markup is visible:

**0.20.17 (`phx-feedback-for`)** — the version pyview runs:
- Selector logic `DOM.feedbackSelector(input)` (V0 `dom.js` L358-365): a container matches if `phx-feedback-for` equals `input.name`, or `input.name` with a trailing `[]` stripped, or the input's `phx-feedback-group` value. So nested names work by exact string equality (`phx-feedback-for="user[address][city]"`), and array inputs match `user[tags]`.
- `showError` (L378-384): remove `phx-no-feedback` from all matching containers in `document`. Called after every change reply for the changed input (`view.js` L1031) and after a submit reply for all inputs (L1350).
- `maybeHideFeedback` (L314-337) runs after **every** DOM patch (`dom_patch.js` L96, L151, L190-194, L312): for each container carrying `phx-feedback-for`, `shouldHideFeedback` (L343-356) queries `[name="X"],[name="X[]"],[phx-feedback-group="X"]` and hides (adds `phx-no-feedback`) unless one of those inputs has `PHX_HAS_FOCUSED`/`PHX_HAS_SUBMITTED`. Because private flags are copied from old to new nodes (`DOM.copyPrivates(toEl, fromEl)`, `dom_patch.js` L230), the state survives re-renders but **not** a full page reload or a LiveView remount.
- `resetForm` (L367-376) on the native `reset` event clears both flags and re-hides everything (`live_socket.js` L890-899), then re-dispatches `input` on the reset button so the server gets a `phx-change` with `_target=<reset button name>` (guide L275-290).
- `phx-feedback-group` (constants L41) was added in 0.20.4 and deprecated in 0.20.5 (v1.0.0 `CHANGELOG.md` L360, L395); it still works in 0.20.17.
- Pain: the server cannot tell "touched" from "untouched", so it must render *all* errors and let CSS hide them (`phx-no-feedback:hidden` Tailwind variant, v1.0.0 CHANGELOG L84-88). Errors are therefore in the DOM (and screen-reader-visible unless styled) for untouched fields.

**1.0+ (`_unused_` + `used_input?`)**:
- `serializeForm` (main `view.ts` L1927-1987) walks `form.elements`, and for every `name` computes `inputsUnused[name] = all elements with that name are not (PHX_HAS_FOCUSED || PHX_HAS_SUBMITTED || has phx-no-unused-field)` and `onlyHiddenInputs[name]`. Then, per FormData entry: if the form lacks `phx-no-unused-field`, the name is unused, is not the submitter's name, and is not hidden-only, it appends `prependFormDataKey(key, "_unused_") = ""` **immediately before** the real pair (L1974-1985). So a submit marks everything used (no `_unused_` at all) and a change event marks every not-yet-touched field.
- `prependFormDataKey` (L76-88) is the exact key rule; my Python port (run) gives: `name → _unused_name`, `user[name] → user[_unused_name]`, `user[tags][] → user[_unused_tags][]`, `user[addresses][0][city] → user[addresses][0][_unused_city]`.
- The Elixir side: `Phoenix.Component.used_input?/1` looks for `"_unused_#{field}"` in `form.params` at the field's nesting level (guide L108-131). Timing: `PHX_HAS_FOCUSED` is set in the debounced callback (main `live_socket.ts` L1913-1919), i.e. *after* debounce fires, so with `phx-debounce="blur"` a field is "used" only once its first event actually pushes.
- 1.2.0-rc.0 added `phx-no-unused-field` on inputs or the form (main `CHANGELOG.md` L288; `constants.ts` L90).

## Form state (bound/unbound, touched/used, attempted values)

Client-held state is minimal and per-DOM-node (`DOM.putPrivate`):
- `phx-has-focused` (set on first pushed change for that input), `phx-has-submitted` (set on all elements at submit), debounce cycle counters, `prev-iteration`, `THROTTLED` timer.
- `formsForRecovery` (V0 `view.js` L1290-1300): on every join the view clones each `form[phx-change]` that has an `id`, has elements, and isn't `phx-auto-recover="ignore"`; keyed by form id. After a reconnect the *new* HTML is parsed into a `<template>` (`maybeRecoverForms`, L495-512), and for each old form whose id still exists `pushFormRecovery` (L1235-1262) pushes **one** change event with the *old* form's full serialised values, `_target` = first non-hidden named input (L1249), event = `phx-auto-recover` attr or `phx-change`. The mount patch is delayed until the replies arrive, to avoid flicker (comment L497-503). Since 1.2.10 the client warns when a `phx-change` form has no `id` (main CHANGELOG L103).
- "Attempted values" (what the user typed) live only in the DOM; the server sees them only through the pushed payload. There is no client-side model, no dirty tracking beyond the two flags, and no persistence across navigation.

## Rendering & customization & styling

The client renders nothing form-specific; it exposes CSS hooks and attribute conventions:
- Loading classes on the ref'd elements: `phx-change-loading` on the input and its form, `phx-submit-loading` on the form + all disabled buttons/inputs (`constants.js` L6-10; `putRef` in `view.js` L838-850 (unverified exact lines)).
- `phx-disable-with="Saving…"`: on submit, buttons with the attribute get `data-phx-disable-with-restore=<innerText>` and their text swapped (`view.js` L894-912); `disableForm` (L1077-1108) sets every input `readOnly`, file inputs `disabled`, buttons `disabled`, and `phx-page-loading` on the form, all undone by `undoRefs` (L852-892) when the reply's patch arrives. Elements under `phx-update="ignore"` are exempt (L1079-1081).
- `phx-trigger-action`: when a patch *adds* the attribute to a form (`isNowTriggerFormExternal`, `dom_patch.js` L159-161, L182-184), inputs of that form are not morphed (L203) and after the patch the client calls `liveSocket.unload()` then the prototype's `form.submit()` (L321-326) — i.e. a real HTTP POST with the current DOM values (used for login/session forms).
- `phx-update="ignore"` on a container keeps its subtree unpatched (only `data-*` attributes sync, `dom.js` L428-462 `isIgnored` branch) — the escape hatch for JS-controlled widgets (date pickers, rich editors).

## Nested / dynamic / conditional

Nothing client-side beyond: verbatim names, submitter injection, and the `JS.dispatch("change")` + button-`name/value` path (`pushInput` L1012). Server-driven conditional sections just work: a patch that adds inputs adds them to the next `FormData`; a patch that removes them removes their keys from the next payload (and, in 1.x, their `_unused_` keys). The one client rule that matters for dynamic rows: because the focused input is never value-patched (`dom_patch.js` L236-241), renumbering rows (`addresses[1]` → `addresses[0]`) while the user is focused in one of them will *rename* the focused element's `name` attribute (attributes other than `value` are merged, `dom.js` L467) but keep its typed value — which is what you want. Selects whose `<option>` set changed are re-morphed and blurred (L235, L245; `isChangedSelect`).

## DX highlights with real code (cite each)

1. Debounce with submit flush — typing in a field with `phx-debounce="500"` and pressing Enter does not lose the pending change: on `submit` the client bumps every input's debounce cycle so pending timers are dropped, and the submit carries the final values (V0 `dom.js` L256-264):
```js
form.addEventListener("submit", () => {
  Array.from((new FormData(form)).entries(), ([name]) => {
    let input = form.querySelector(`[name="${name}"]`)
    this.incCycle(input, DEBOUNCE_TRIGGER)
    this.deletePrivate(input, THROTTLED)
  })
})
```
2. `phx-debounce="blur"` binds a one-time blur listener that pushes the *latest* value (L224-230); numeric debounce also flushes on blur (L265-273). Throttle re-fires immediately on a *new* key (L237-244) so arrow-key navigation is snappy.
3. Focus preservation during a server re-render (V0 `dom_patch.js` L233-241):
```js
let isFocusedFormEl = focused && fromEl.isSameNode(focused) && DOM.isFormInput(fromEl)
let focusedSelectChanged = isFocusedFormEl && this.isChangedSelect(fromEl, toEl)
if(isFocusedFormEl && fromEl.type !== "hidden" && !focusedSelectChanged){
  this.trackBefore("updated", fromEl, toEl)
  DOM.mergeFocusedInput(fromEl, toEl)   // all attrs except value; readonly synced
  DOM.syncAttrsToProps(fromEl)          // checkbox/radio .checked from attribute
  updates.push(fromEl)
  return false                          // morphdom does not touch children/value
}
```
   and `mergeAttrs` still re-sets the `value` *attribute* when property and attribute already agree, so hooks' `updated` fire (L441-451, issue #2163).
4. Form recovery event (V0 `view.js` L1238, L1255): `phxEvent = form[phx-auto-recover] || form[phx-change]`; `targetView.pushInput(input, targetCtx, cid, phxEvent, {_target: input.name}, cb)`. Server-side you distinguish it only by the `_target` (first input) — 1.x additionally dispatches a `phx:form-recovery` CustomEvent on the DOM (main `view.ts` L2524-2526).
5. Submitter handling (V0 `view.js` L63-79) means `<button name="action" value="save_and_new">` inside `phx-submit` is visible to the server as `action=save_and_new` in DOM position; 1.x also exempts the submitter's key from `_unused_` (main L1978).
6. Python parsing of the actual 0.20.17 payload (run):
```
parse_qs default (drops blanks!): {'user[address][city]': ['Ber'], 'user[tags][]': ['a', 'b'], '_target': ['user[address][city]'], 'step': ['2']}
parse_qsl keep_blank_values: [('user[_unused_name]', ''), ('user[name]', ''), ('user[address][city]', 'Ber'), ('user[_unused_tags][]', ''), ('user[tags][]', 'a'), …]
decoded 1.1: {'user': {'_unused_name': '', 'name': '', 'address': {'city': 'Ber'}, '_unused_tags': ['', ''], 'tags': ['a', 'b']}}
_target path: ['user', 'address', 'city']
```
   `user[name]=` (the user cleared the field) is **silently dropped** by pyview's current `parse_qs(value)`; the changeset then never sees the clear.

## Pain points & criticisms (cite)

- Feedback gating churned three times in 18 months: `phx-feedback-for` (client CSS) → `phx-feedback-group` added 0.20.4, deprecated 0.20.5 "to move feedback handling into Elixir and out of the DOM" (v1.0.0 `CHANGELOG.md` L360, L395) → removed in 1.0.0-rc.0 with a JS shim gist for legacy apps (L5-30). Multiple bug entries: "phx-feedback-for failing to be properly updated" (#3122, L348), "reapplied when multiple inputs with the same name" (L388), "classes not applied in some cases" (L367).
- `_unused_` is a stringly protocol inside the params (a field literally named `_unused_email` collides), needs `phx-no-unused-field` opt-outs (#3577, main CHANGELOG L288), and the 1.0 migration notes call out password-confirmation fields that were never "used" (v1.0.0 CHANGELOG L96).
- `_target` semantics differ between events: absent on submit, `"undefined"` string when missing in ≤1.0.5 (main `view.ts` L2111-2115), first-input name on recovery — server code that keys on `_target` needs guards.
- `formData.delete(key)` for files removes *all* values under that name, and the urlencoded channel means no binary at all — uploads are a completely separate protocol (`uploads`, `allow_upload`, preflight).
- Recovery replays a `phx-change` with *stale* values into the *new* LiveView with no signal that it's a recovery (0.20.17); if `phx-change` does side effects (e.g. autosave), they fire again.
- A `phx-change` form without `phx-submit` silently becomes a native HTTP submit (V0 `live_socket.js` L828-843) — surprising when you forget `phx-submit`.
- Console error on `liveview_version` mismatch (V0 `view.js` L294-295) means pyview must keep declaring `PHOENIX_LIVEVIEW_VERSION` exactly equal to the bundled JS (pyview `ws_handler.py` L138, L389 already do).

## Lessons for pyview — steal / adapt / avoid (opinionated, concrete)

**Steal**
1. Replace `parse_qs(value)` with `parse_qsl(value, keep_blank_values=True)` + a bracket decoder (Plug-style: `a[b][c]=v` → nested dicts, trailing `[]` → list append, numeric segments → keep as string keys but ordered; cap depth ~32). Blank strings are *data* ("the user cleared it") and, in 1.x, the whole `_unused_` mechanism is blank-valued.
2. Make `_target` a key path on the server exactly like Phoenix: `"user[address][city]"` → `["user","address","city"]` (split on `[`/`]`), expose it on the event as `target: tuple[str, ...]`; and give the form layer a `used_input?`-equivalent computed from `_unused_*` siblings (1.x) **or**, for the 0.20.17 client, track "used" server-side yourself: on change, mark `_target` path used; on submit, mark all used. That gives pyview *today* what Phoenix only got in 1.0, without the CSS trick.
3. Keep the Phoenix wire conventions verbatim so all client features keep working: names `form[field]`, ids `form_field`, hidden `"false"` before checkboxes, `parent[children_sort][]` / `parent[children_drop][]` + `JS.dispatch("change")` buttons for dynamic rows (the client supports this via submitter injection, `view.js` L1012, L63-79).
4. Bake `phx-debounce="blur"` defaults into generated text inputs and `phx-submit-loading`/`phx-disable-with` into generated submit buttons — they're free and hard for users to discover.
5. Treat `phx-auto-recover` as a first-class option of the form helper (`recover="event"` / `recover=False` emitting `phx-auto-recover="ignore"`), and always render a stable `id` on `phx-change` forms (recovery is keyed by id, `view.js` L1294).

**Adapt**
6. Write the payload decoder to accept *both* client generations: metadata at the tail of the urlencoded string (0.20.17: strip trailing `_target` and any `phx-value-*` keys — they are ordinary keys, so parse them all and then pop `_target`; treat anything not under the form's `as:` prefix as meta) **and** `payload["meta"]` (1.0.6+). Plan the `liveview_version` bump as a coordinated change: bundle 1.1 JS, update `PHOENIX_LIVEVIEW_VERSION`, switch decoding, add `_unused_` stripping. Rendering-side, the 1.x client no longer touches `phx-no-feedback`, so error visibility must become server-side (which a Pydantic-based "used" model gives you anyway).
7. Because the focused input is never value-patched, server-side coercion/normalisation (`"  1,000 "` → `1000`) will *not* visually apply to the field being typed in until blur — design the "display value" API so re-formatting happens on blur/submit re-render, not on every keystroke.

**Avoid**
8. Don't reintroduce a `phx-feedback-for`-style client class toggle in pyview templates; Phoenix abandoned it (rc.0 note) and the 0.20.17 mechanics need exact-name matching that breaks on renamed dynamic rows.
9. Don't key server logic on `_target` being present or a single string: it is absent on submit and is a *path*; and never assume the parsed dict has one value per key (multi-selects, `[]` names, and 1.x `_unused_` repeats).
10. Don't validate/coerce on the raw flat dict (`payload[k][0]`); decode to nested first, then hand the whole nested dict to Pydantic with `_unused_*` stripped and remembered separately.

## Sources (URLs / repo paths actually read)

Repo `/tmp/claude-0/-home-user-pyview/4e51d174-6d71-5bea-a6e4-de1b93546ddb/scratchpad/repos/phoenix_live_view` (https://github.com/phoenixframework/phoenix_live_view):
1. `v0.20.17:assets/js/phoenix_live_view/view.js` L60-108 (serializeForm), L281-295 (onJoin/liveview_version), L495-512 (maybeRecoverForms), L838-912 (undoRefs/disable-with), L962-1075 (extractMeta, pushEvent, pushInput), L1077-1145 (disableForm, pushFormSubmit), L1235-1262 (pushFormRecovery), L1290-1300 (getFormsForRecovery), L1342-1352 (submitForm)
2. `v0.20.17:assets/js/phoenix_live_view/dom.js` L214-290 (debounce), L310-384 (feedback), L428-520 (mergeAttrs, mergeFocusedInput, restoreFocus, isFormInput, syncAttrsToProps)
3. `v0.20.17:assets/js/phoenix_live_view/live_socket.js` L823-900 (bindForms), L903-915 (debounce wrapper)
4. `v0.20.17:assets/js/phoenix_live_view/dom_patch.js` L86-100, L151-194, L226-256, L312-326
5. `v0.20.17:assets/js/phoenix_live_view/constants.js` L6-10, L30-62, L74-80
6. `v0.20.17:guides/client/form-bindings.md` L106-147 (phx-feedback-for docs)
7. `v1.0.0:assets/js/phoenix_live_view/view.js` L76-88, L109, L308-325; `v1.0.0:CHANGELOG.md` L1-100 (feedback-for removal + shim), L234-237, L348-395
8. main `assets/js/phoenix_live_view/view.ts` L76-88 (prependFormDataKey), L457-480, L1853-1995 (extractMeta, serializeForm), L2064-2125 (pushInput), L2251-2332 (pushFormSubmit), L2490-2545 (pushFormRecovery), L2736-2741 (submitForm)
9. main `assets/js/phoenix_live_view/dom.ts` L498-510; `dom_patch.ts` L462-486; `live_socket.ts` L1890-1922; `constants.ts` L49-90
10. main `guides/client/form-bindings.md` L100-135, L196-320; main `CHANGELOG.md` L103, L235-298
11. `/home/user/pyview/pyview/ws_handler.py` L5, L138, L188-189, L389 (current parse_qs / liveview_version)
12. `/tmp/claude-0/-home-user-pyview/4e51d174-6d71-5bea-a6e4-de1b93546ddb/scratchpad/research/liveview_forms.md` (TL;DR, server-side companion)
13. `/tmp/claude-0/-home-user-pyview/4e51d174-6d71-5bea-a6e4-de1b93546ddb/scratchpad/phx_parse_demo.py` (executed; output pasted above)
