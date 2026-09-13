# Part 8 — Counter-design, adversarial critique, and what changed

Two independent passes were run against the first draft of Part 4: a competing design written from a *changeset-purist* angle (explicit pipeline, minimal helpers, templates in full control) and an adversarial critic instructed to find contradictions with the research corpus, the spike, and pyview's code, and to mentally type every example. Both documents are in `appendix/synthesis/`. This part summarises what they found and how the proposal changed.

## 8.1 The counter-design in one paragraph

Two objects instead of one: a pure, HTML-free `Changeset` (`cast` → composable validators → `apply_action` returning `Ok(model) | Err(changeset)`, with Ecto merge semantics over `data`/`params`/`permitted`, typed per-field changes via cached `TypeAdapter`s, schemaless forms from a dict of types, explicit `Intent` values applied by one visible call) plus a thin `to_form()` adapter yielding `FormField(name, id, value: str, errors, constraints)` and about eight helpers. Auto-render and widget registries are deliberately out of the core in favour of a copyable components module. Lists, unions and wizards use only 0.20.17 client mechanics; reconnect recovery is explicit via `phx-auto-recover`.

Where it disagreed with the draft: a separate changeset is not an empty shell; four public surfaces (auto-render, registry, theme, `Input`) are too many for v1; `Input(visible=…)` dropping values leaks UI into the schema and is wrong; unconditional `""` → absent breaks edit forms; emitting `phx-feedback-for` double-gates on a deprecated mechanism; silent intents hide the operation from handlers and tests; async `checks` on the constructor put I/O inside the data structure; `Form.__getattr__` collides with form attributes; `Field.value: Any` should be `str | list[str]`.

## 8.2 What the critic found (all confirmed)

| # | Finding | Severity |
|---|---|---|
| 1 | Ibis splits filter arguments on commas without bracket tracking (`vendor/ibis/utils.py:splitc`), so every multi-key dict or list argument in the ladder raised `TemplateSyntaxError` — levels 1–2 did not compile as written | blocking |
| 2 | The gating formula text said "prefix *or child* of a used path", the opposite of the spike; it would have shown `missing` on freshly added rows | wrong |
| 3 | `_target` for `name[]` inputs decoded to `("tags", "")` and never matched the field | wrong |
| 4 | `_unused_` was specified as a top-level key; the 1.x client puts the prefix on the *last* bracket segment | wrong |
| 5 | `phx-feedback-for` on error containers contradicts the corpus and is actively harmful after intents/`add_error` (the client re-hides containers after every patch) | wrong |
| 6 | "Hidden-by-rule values dropped before validation so a hidden required field cannot block submission" is false (dropping yields `missing`) | wrong |
| 7 | Golden-path `<form>` had no `id`; recovery only runs for forms with an id and the draft never mentioned `phx-auto-recover` | gap |
| 8 | Union "lossless switching (verified)" was tested against a payload the client cannot send; the real client sends the old fieldset's values with the new tag | wrong evidence |
| 9 | "Params replaced by each payload" left edit forms with unrendered required fields `missing`, and the wizard example leaned on `merge_params`/`hidden_fields` that existed nowhere | gap |
| 10 | Decoder limits (dunder rejection, pair cap, refusing `[][x]`) were marked verified but absent from the spike | over-claim |
| 11 | `raise ValueError` keeps `loc == ()` only in model validators | wording |
| 12 | No specification of the handler-facing payload after phase 0; no `Params`-like object | gap |
| 13 | Hand-written (level 3) inputs got no `phx-debounce`, so errors on the first keystroke | gap |
| 14 | `SecretStr` values were echoed back by the "attempted values survive" rule | gap |
| 15 | Uploads were three lines; the upload manager's flat names and `_target` lookup were not reconciled | gap |
| 16 | Multiple forms, LiveComponents and `phx-target` unaddressed | gap |
| 17 | Dataclass/TypedDict support asserted but every introspection path was `BaseModel`-only | gap |
| 18 | Intents applied silently; no way for a handler to react or a test to assert | gap |
| 19 | `Field` attributes (`name`, `id`, `value`, `label`, …) shadow model fields in Ibis's attribute-first resolution — `{{ row.name }}` on `Item(name)` would return the HTML name string | blocking |
| 20 | Digit-string indices (`form.addresses.1.city`) rendered empty in the first spike | wrong |
| 21 | Testing examples used an undefined `encode()` helper | gap |
| 22 | `ChangeSet` migration shim hand-waved | gap |

## 8.3 What changed in Part 4 as a result

- **Ibis syntax**: phase 2 ships a bracket-aware `splitc` (six lines, verified to make dict/list arguments parse) and a `{% input %}`/`{% field %}` tag; filters are prefixed (`render_form`, `form_field`, `form_input`, …); every example was rewritten to parse.
- **Template contract**: metadata moved under `Field.html` (`name`, `id`, `value: str | list[str]`, `errors`, `label`, `hint`, `attrs`, `type`, `key`); sub-fields by attribute or item, digit strings accepted; `Field.typed` for derived state.
- **Wire contract**: a first-class `Params` (`data`, `target` with trailing `[]` stripped, `intents`, `meta`, `unused` from last-segment `_unused_` keys, `recovered`), produced by `ws_handler` and injectable by type; accepts both client generations; decoder rejects `[][x]` and dunder segments and caps size (now actually implemented and tested).
- **Cast semantics**: Ecto merge — absent keeps `data`, empty becomes default/`None` and is a change; `merge_params`/`hidden_fields` deleted; edit forms and wizards documented on top of it.
- **Gating**: formula corrected to the ancestor-of-used rule; `phx-feedback-for` removed everywhere; recovery handled via `phx-auto-recover` + `Params.recovered`; form `id` made mandatory in every example; `show_errors` policy now also reaches hand-written inputs through `html.attrs`.
- **Unions**: variant-named inputs (`profile[account][business][company]`) adopted from the counter-design; the shelf became an implementation detail; re-verified with the real client ordering.
- **Intents**: decoded into `params.intents`, applied by `validate()` but recorded in `form.applied_intents` for handlers and tests; the JS-command-free fallback specified (submit button after the real one, `formnovalidate`).
- **Server checks**: `checks=` removed from the constructor; handler-side `add_error` after `submit` is the one idiom; external errors are ungated and survive re-validation until the next submit.
- **Passwords**: `SecretStr` never re-rendered; **uploads**, **multiple forms/LiveComponents**, **dataclasses** (v1: pydantic models; `TypeAdapter`-based introspection later), **auto-routing analysis** and the **`ChangeSet` shim** each got a real section.
- **Testing**: `wire(form, values, target=, submitter=)` replaces the undefined `encode()`.
- **Hidden ≠ deleted**: the visibility-rule paragraph now says values stay and requiredness is the model's business.

## 8.4 What was kept against the counter-design, and why

- **One object, named `Form`, with changeset vocabulary.** The counter-design's `Changeset` + `to_form` split mirrors Ecto/Phoenix because Ecto is also a persistence layer; in pyview both halves are the same object's state. The docs use *cast / params / changes / action* so the mental model the maintainer liked transfers.
- **Auto-render stays in the core.** "Here's my pydantic class, do the rest" is the stated goal; the counter-design's copyable components module is adopted *as the exit*, not as a replacement.
- **Widget registry and `Theme` stay, `Input` hints stay.** They are what make level 4 a small delta; the registry is rank-based so defaults are never edited.
- **`Ok/Err` from `submit()`** is offered as an additional accessor (`form.result()`) rather than the only return, so `if form.valid:` remains the golden path.
- **Schemaless forms from a dict of types** and **form-context validators** (`validate_confirmation`, `validate_acceptance`) are noted as v2 candidates; pydantic idioms cover them in v1.
