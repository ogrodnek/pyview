# Part 6 — Roadmap, risks and open decisions

## Phases

| Phase | Scope | Deliverable | Effort |
|---|---|---|---|
| **0. Fix the wire** | `parse_qsl(keep_blank_values=True)`, bracket decoder with limits, `Params` (target with `[]` stripped, intents, meta, `_unused_` on the last segment, recovered), both client shapes | `pyview/forms/params.py` + tests; `ws_handler` produces it; binding injects it by type; the `parse_qs` dict stays for existing consumers | small |
| **1. Core form object** | `Form`, `Field.html`, `FormError`, Ecto cast/merge over initial data, whole-model validation, used/action gating, recovery, message catalog with `{label}` + overrides, `field_errors`, `add_error`, row keys, intents, variant-named unions, `wire()` test helper | `pyview/forms/{form,errors,testing}.py`; `ChangeSet` shim on top | medium |
| **2. Rendering** | bracket-aware `splitc` in the vendored Ibis + `{% input %}` tag; prefixed filters (`render_form`, `form_field`, `form_input`, `form_label`, `form_errors`, `form_debug`, row/intent helpers); t-string helpers; rank-based widget registry + inference table; `Input(...)` hints and side-car `ui=`; `Theme` + copyable `components.py`; GOV.UK markup contract; error summary | `pyview/forms/{components,theme,ibis,html}.py`; docs page; examples rewritten | medium–large |
| **3. Lists, unions, wizards** | Row helpers emitting the `JS.dispatch("change")` buttons, min/max rows, live-region/focus hook, `form.step()` + `form_hidden`, one-model-per-step docs | examples: addresses, personal/business, wizard | medium |
| **4. Integration** | Uploads bridge, server `checks`, validation context, auto-routed events (`Form(..., on_submit=)`), signature binding of `Form[Model]`, playground/debug panel, i18n hook docs | — | medium |
| **5. Client upgrade (optional)** | Bundle LiveView 1.x, `meta` key, `_unused_` → `used`, drop `phx-feedback-for` markup | coordinated with `PHOENIX_LIVEVIEW_VERSION` | medium |

Phase 0 and 1 are independent of any rendering decision and immediately improve the existing examples; they are the right first PR. Phase 2 is where most of the DX lives and where the theme/widget API deserves a short RFC before coding.

## Risks

- **Two template engines.** Every helper exists twice (filter + function). Mitigation: one widget layer returning `Markup`; both engines wrap it in ~5 lines each.
- **Ibis filter syntax** — the vendored splitter breaks on commas inside dict/list arguments; the six-line fix and the `{% input %}` tag are part of phase 2, before any rendering docs are written.
- **Replace semantics** lose values for inputs a template stops rendering; unions are safe (variant-named inputs stay in params) and unrendered fields fall back to initial data, but ad-hoc `{% if %}` sections that hide a field and later show it again lose the typed value — document "hidden ≠ deleted: keep a hidden input or use a union".
- **Recovery replay** re-sends stale values with `_target` = first input; `Params.recovered` marks non-blank paths used, so errors reappear where the user had typed. Side-effecting `phx-change` handlers must check `params.recovered`.
- **Pydantic behaviour drift** (partial validation, error types) across minors; pin the message catalog to error `type` strings and test them.

## Open decisions for the maintainer (with recommendations)

0. **`Field.html` namespace vs renamed attributes.** Recommend `.html` (one token at level 3 only; no shadowing of model fields like `name`/`id`); the alternative is Django-style `html_name`/`dom_id` on the field itself.

1. **Name of the object: `Form` vs `ChangeSet`.** Recommend `Form` (one object; changeset semantics inside). Keep `pyview.changesets` as a shim for one release.
2. **Auto-routed form events** (`Form(..., on_submit=)`) vs explicit `@event` handlers. Recommend explicit first; auto-routing as an opt-in in phase 4.
3. **Where UI hints live**: `Annotated[..., Input(...)]` on the model vs a side-car `ui={}` dict on `Form(...)`. Recommend both, model-side first (single source of truth), side-car for models you do not own.
4. **Default theme**: unstyled semantic markup vs Tailwind. Recommend unstyled default + `TAILWIND` preset, because the examples and docs site use Tailwind but the library should not assume it.
5. **Bracket names vs dotted names.** Recommend brackets (client conventions), with dotted *paths* accepted everywhere on the Python side (`form.field("addresses.0.city")`).
6. **List intents via `JS.dispatch("change")` buttons vs plain `phx-click` events.** Recommend the dispatch buttons (lossless, proven in Phoenix, verified in the spike); the JS-command-free fallback is a submit button after the real one with `formnovalidate`.
7. **Client upgrade to 1.x.** Recommend after phase 3, not before: nothing in the design depends on it, and the server-side `used` model makes the migration mechanical.
