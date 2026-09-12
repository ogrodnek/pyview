# Part 1 — Where pyview is today

pyview already has the raw materials for a good form story; it is missing the middle layer that turns them into one.

## What exists

| Piece | Where | What it does today |
|---|---|---|
| Wire decoding | `pyview/ws_handler.py` | `parse_qs(value)` on the urlencoded string the Phoenix client sends for `type: "form"` events → `dict[str, list[str]]` with *flat* keys (`"user[address][city]"` stays a literal key). |
| `ChangeSet[Model]` | `pyview/changesets/changesets.py` | Pydantic-backed, scalar-only, flat: `apply(payload)` copies `payload[_target][0]` into `changes`, validates the whole model, keeps errors only for keys already in `changes` (a proxy for "touched"). `model` re-validates on access. `errors[str(loc[0])]` truncates nested paths. |
| Signature binding | `pyview/binding/` | Converts payload values to `int/float/str/bool`, `Optional`, unions, `list/set/tuple` and *flat* dataclasses; no nesting, no pydantic models, no error surface for templates. |
| Templates | Ibis filters (`@filters.register`) and PEP 750 t-strings | Both can render whatever object the view puts in the context; the registration example registers ad-hoc `input_tag`/`error_tag` filters with hard-coded Tailwind classes. |
| Client features | vendored `phoenix_live_view` 0.20.17 | `phx-change`/`phx-submit`/`_target`, `phx-debounce`, `phx-disable-with`, `phx-feedback-for`/`phx-no-feedback` (client-side hiding of untouched errors), `JS.dispatch`, form recovery, `phx-trigger-action`, uploads. `pyview.js` already exposes `dispatch`. |
| Uploads | `pyview/uploads.py` | `socket.allow_upload`, `live_file_input` filter, `consume_uploads()` — separate from forms. |

## What the two shipped form examples reveal

`examples/views/registration` and `examples/views/form_validation` are the current "best practice", and they show the seams:

- Every template hand-writes `value="{{changeset.attrs.name}}"`, `name="name"`, `id="input_name"`, the `phx-feedback-for` wrapper and the error SVG — roughly 25 lines of HTML per field, none of it derived from the model.
- `changeset.attrs` is a `SimpleNamespace` of *changes*, so untouched fields render `""`, and a model with defaults never shows them.
- `apply()` reads `payload[k][0]`: multi-selects, checkbox groups and nested names cannot work.
- Model-level validator errors are pinned to whichever field changed last ("show on current field") because there is no form-level error slot.
- `save` re-validates via `changeset.model` and, on failure, silently does nothing — there is no `action`/submitted state to make errors visible after a submit.
- Error messages are pydantic's ("String should have at least 3 characters"); the plants example tries to override them through a `Config.error_msg_templates` dict that pydantic v2 ignores.

## Two latent bugs worth fixing regardless of the redesign

1. **Blank values are dropped.** `parse_qs` defaults to `keep_blank_values=False`, so when a user clears a field the client sends `name=` and pyview never sees it; the changeset keeps the old value. Fix: `parse_qsl(value, keep_blank_values=True)` (verified against the 0.20.17 client serialiser, Appendix `phoenix_client_js.md`).
2. **Metadata leaks into data.** `_target` (0.20.17 appends it to the urlencoded string) and `phx-value-*` pairs arrive as ordinary keys; anything iterating the payload (dataclass binding, `dict[str, Any]` injection) sees them.

## Why this matters for the design

Everything the research recommends — nested decoding, a form object with attempted values and used-state, error records with paths, derived HTML attributes, generated widgets, list/union protocols — slots in *between* `ws_handler` and the templates without changing pyview's programming model (`socket.context`, `handle_event`, `@event`, both template engines). The Phoenix client already speaks every convention we need; the server side is the missing half.
