# Form handling for pyview — research and a design proposal

*Branch: `claude/pyview-form-handling-research-y24uuy` · September 2026 · pydantic 2.13 · Phoenix LiveView JS client 0.20.17*

This is a research report, not an implementation. It answers three questions: **what do the best form libraries do**, **which patterns transfer to a server-driven, pydantic-based LiveView**, and **what would a great `pyview.forms` look like** — concretely enough to start building. A runnable spike backs the load-bearing claims.

## TL;DR

1. **Keep the concerns apart, exactly as the maintainer suspected.** Wire decoding, schema, coercion, validation, error model, messages, form state, identity, rendering, widgets, layout hints, theming, dynamic structure. The libraries that age well (Ecto+Phoenix, Conform, Django 4+, FormKit, simple_form) separate them; the ones people fight (WTForms widgets-on-fields, Django formsets, RJSF's generic UI) fuse them.
2. **Pydantic already solves the two hardest concerns** (schema + validation, with nested `loc` paths, discriminated unions and typed output). A pyview form layer should *not* re-declare fields; it should add what pydantic lacks for forms: empty-string handling, attempted values, used-state, human messages, HTML attribute derivation, list/union protocols, server-side checks.
3. **Adopt the changeset state model, keep the name `Form`.** Ecto cast semantics over initial data (absent keeps data; empty becomes default/`None` and is a change), `params` always kept for re-rendering, `model` typed when valid, `errors` as `(path, code, params, message)` records, an explicit `action` and a `used` set of paths.
4. **Show errors only for used inputs or after submit**, tracked server-side from `_target`. It works with today's client, reproduces LiveView 1.0's `used_input?` semantics (parents count as used when a child is; children never inherit), and makes the deprecated `phx-feedback-for` CSS trick unnecessary.
5. **The wire format is already right; the server side is not.** Phoenix bracket names, `_target`, submitter buttons, debounce, recovery — all present. pyview's `parse_qs` drops blank values (a real bug: clearing a field never reaches the changeset) and keeps flat keys. A `Params` object (decoded data, `_target` path, intents, meta, `_unused_` paths, recovery flag) produced by a `Plug.Conn.Query`-compatible decoder fixes both and absorbs the 1.x client upgrade.
6. **A `Field` object is the template contract**, with metadata under `field.html` (`name`, `id`, `value`, `errors`, `label`, `hint`, `attrs`, `type`, `key`) so it never shadows model fields, and rows by iteration. Every rendering layer — auto-render, `field`, `input`/`label`/`errors`, raw HTML — is a function of it and is optional. Both Ibis filters and t-string helpers wrap the same widget layer.
7. **HTML constraints derive from the model** (`required minlength maxlength min max step pattern`) — free browser hints and a11y semantics, as Phoenix's `input_validations`, superforms' `constraints` and Conform's `getZodConstraint` do.
8. **Lists, unions and wizards are protocol, not user code.** Named buttons + `JS.dispatch("change")` carry add/remove/move intents with the whole form (the mechanic behind LiveView's own recipe, verified in the 0.20.17 client); stable row keys give DOM ids that survive reorders; discriminated unions use variant-named inputs (`profile[account][business][company]`) so pydantic's error paths *are* the input names and switching never loses data; wizards are one form per step.
9. **Messages are a catalog keyed by pydantic error code with `ctx` interpolation**, overridable per app/model/field and translated at render time (the Ecto/Rails/Django/Laravel consensus). Default copy follows GOV.UK rules ("Enter a whole number", not "unable to parse string as an integer").
10. **Theme = class map + replaceable wrapper/widget functions; no CSS in the library.** Unstyled semantic markup by default, a Tailwind preset, and hand-written HTML always possible.

**Golden path** (the whole thing):

```python
class Registration(BaseModel):
    name: str = Field(min_length=3, title="Full name")
    email: EmailStr
    password: SecretStr = Field(min_length=8)

class RegistrationView(BaseEventHandler, LiveView):
    async def mount(self, socket, session):
        socket.context = {"form": Form(Registration)}

    @event("validate")
    async def validate(self, socket, payload: dict):
        socket.context["form"].validate(payload)

    @event("save")
    async def save(self, socket, payload: dict):
        form = socket.context["form"].submit(payload)
        if form.valid:
            await users.create(form.model)
```

```html
<form phx-change="validate" phx-submit="save">
  {{ form | render }}
  <button type="submit" phx-disable-with="Creating…">Create account</button>
</form>
```

## How to read this

| Part | What it is |
|---|---|
| [1 — pyview today](01-pyview-today.md) | What exists, what the shipped examples reveal, two latent bugs |
| [2 — The concerns](02-concerns.md) | The 14 concerns a form system must separate, and who does each best |
| [3 — The landscape](03-landscape.md) | Digests of every library studied: what to take, what to leave |
| [4 — Proposed design](04-design.md) | `pyview.forms`: principles, vocabulary, golden path, ladder, API, data-in, validation, rendering, nested/dynamic, security, testing, migration |
| [5 — Worked examples](05-examples.md) | Edit form, address list, personal/business union, dependent select, wizard, BYO HTML + theme, custom widget, tests |
| [6 — Roadmap](06-roadmap.md) | Phases, risks, open decisions with recommendations |
| [7 — Prototype evidence](07-prototype-evidence.md) | What the spike proved (pydantic behaviours, decoder, cast/merge, gating, intents, union switching, recovery) |
| [8 — Critique and alternatives](08-critique.md) | An independent changeset-purist counter-design and an adversarial review of Part 4, with what changed as a result |
| `appendix/` | The per-library research write-ups (sources, code, verification notes) and `appendix/synthesis/` (the counter-design and the critique) |
| `prototype/` | The runnable spike and its scenario tests |

## Method and caveats

Twenty-eight topics were planned; the corpus in `appendix/` covers the ones that matter most for the decision in depth (Ecto changesets, Phoenix LiveView server and client internals, Conform, Superforms and the client-state libraries, Django/WTForms, schema-driven builders, Rails/dry-rb/Reform, Python's pydantic-adjacent landscape, pydantic internals, error messages/i18n, nested/dynamic patterns, form UX/a11y, community sentiment) and a lighter survey of .NET, JVM, Go/Rust, functional formlets and other LiveView ports. Most vendor documentation sites were unreachable from the research sandbox, so the write-ups were built from cloned repositories, package sources and tests, then cross-checked; anything not verifiable is marked "(unverified)" in the appendix. All pydantic and client claims in Part 4 marked **(verified)** were executed in the spike.
