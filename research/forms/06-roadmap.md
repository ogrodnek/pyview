# Part 6 — Roadmap, risks and open decisions

## Phases

| Phase | Scope | Deliverable | Effort |
|---|---|---|---|
| **0. Fix the wire** | `parse_qsl(keep_blank_values=True)`, bracket decoder, `_target` path, meta separation (both client shapes) | `pyview/forms/decode.py` + tests; `ws_handler` uses it; `Params`/binding get nested access | small |
| **1. Core form object** | `Form`, `Field`, `FormError`, empty normalisation, whole-model validation, used/action gating, message catalog + overrides, `field_errors` helper, `data=` initial values, tests without sockets | `pyview/forms/{form,errors}.py`; `ChangeSet` re-implemented on top | medium |
| **2. Rendering** | Ibis filters (`render`, `field`, `input`, `label`, `errors`, `debug`), t-string helpers, widget registry + inference table, `Input(...)` hints, `Theme` class map, unstyled + Tailwind presets, a11y attributes, `phx-debounce` defaults, error summary | `pyview/forms/{widgets,theme,ibis,html}.py`; docs page; examples rewritten | medium–large |
| **3. Lists, unions, wizards** | Row keys, `_intent` add/remove/move via `JS.dispatch("change")`, min/max rows, union variant shelf, `form.step()` | `pyview/forms/intents.py`; examples: addresses, personal/business, wizard | medium |
| **4. Integration** | Uploads bridge, server `checks`, validation context, auto-routed events (`Form(..., on_submit=)`), signature binding of `Form[Model]`, playground/debug panel, i18n hook docs | — | medium |
| **5. Client upgrade (optional)** | Bundle LiveView 1.x, `meta` key, `_unused_` → `used`, drop `phx-feedback-for` markup | coordinated with `PHOENIX_LIVEVIEW_VERSION` | medium |

Phase 0 and 1 are independent of any rendering decision and immediately improve the existing examples; they are the right first PR. Phase 2 is where most of the DX lives and where the theme/widget API deserves a short RFC before coding.

## Risks

- **Two template engines.** Every helper exists twice (filter + function). Mitigation: one widget layer returning `Markup`; both engines wrap it in ~5 lines each.
- **Ibis filter syntax** takes positional args only; keyword-style options need a dict literal or a custom tag. Acceptable for level 1–2; a `{% input %}` tag can come later.
- **Whole-form replace semantics** lose values for inputs the server stopped rendering (union variants); the shelf handles the common case, but arbitrary template-side conditionals can still drop data. Document: "if you hide it, keep a hidden input or use the union pattern".
- **0.20.17 feedback CSS vs server gating.** Rendering errors only when used means the `phx-no-feedback` class is redundant; keep emitting `phx-feedback-for` for recovery until the client is upgraded, then remove.
- **Pydantic behaviour drift** (partial validation, error types) across minors; pin the message catalog to error `type` strings and test them.

## Open decisions for the maintainer (with recommendations)

1. **Name of the object: `Form` vs `ChangeSet`.** Recommend `Form` (one object; changeset semantics inside). Keep `pyview.changesets` as a shim for one release.
2. **Auto-routed form events** (`Form(..., on_submit=)`) vs explicit `@event` handlers. Recommend explicit first; auto-routing as an opt-in in phase 4.
3. **Where UI hints live**: `Annotated[..., Input(...)]` on the model vs a side-car `ui={}` dict on `Form(...)`. Recommend both, model-side first (single source of truth), side-car for models you do not own.
4. **Default theme**: unstyled semantic markup vs Tailwind. Recommend unstyled default + `TAILWIND` preset, because the examples and docs site use Tailwind but the library should not assume it.
5. **Bracket names vs dotted names.** Recommend brackets (client conventions), with dotted *paths* accepted everywhere on the Python side (`form.field("addresses.0.city")`).
6. **List intents via `JS.dispatch("change")` buttons vs plain `phx-click` events.** Recommend the dispatch buttons (lossless, proven in Phoenix); offer `phx-click="form:intent"` as the documented alternative.
7. **Client upgrade to 1.x.** Recommend after phase 3, not before: nothing in the design depends on it, and the server-side `used` model makes the migration mechanical.
