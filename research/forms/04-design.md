# Part 4 — Proposed design: `pyview.forms`

This part turns the research into a concrete proposal. It is opinionated on purpose; every choice names the library it was taken from and the alternative that was rejected. Everything marked **(verified)** runs in the spike (`prototype/pyview_forms_proto3.py` + `test_proto3.py`, Part 7) against pydantic 2.13 and the payload shapes the 0.20.17 client produces. This is the second revision: an independent counter-design and an adversarial critique (Part 8) changed the wire contract, the merge semantics, the union naming, the template contract and the Ibis syntax.

## 4.0 Design principles

1. **The pydantic model is the schema.** Names, types, defaults, constraints, nesting, lists and unions come from the model; no parallel form class. *(Django ModelForm, simple_form, AshPhoenix auto forms, superforms constraints.)*
2. **One object to pass around.** A `Form` holds attempted params, initial data, the validated model, errors, used paths and an action; a `Field` is a computed view onto it. Templates and widgets only ever touch `Field`. *(Phoenix `FormField`, Conform metadata.)*
3. **Params in, model out, errors as data.** Whole-model validation on every change (≈20 µs); errors are `(path, code, params, message)` records addressed by the same paths as input names. *(Ecto `{msg, opts}`, pydantic `loc`/`type`/`ctx`, Standard Schema issues.)*
4. **Cast like Ecto.** Fields absent from the payload keep their initial data (edit forms render what they want); an empty value becomes the field's default or `None` *and counts as a change*; the attempted string always survives for re-rendering. *(Ecto `cast` + `empty_values`, ASP.NET `AttemptedValue`.)*
5. **Show errors only for inputs the user has used, or after a submit.** Two orthogonal gates, `used` (from `_target`, intents, recovery, submit) and `action` (`None` → `"validate"` → `"submit"`), tracked on the server. *(Phoenix `action` + `used_input?`, Conform `touchedFields`, GOV.UK/Baymard timing research.)*
6. **Rendering is layered and every layer is optional**: auto-render → per-field helpers → attribute helpers → hand-written HTML with `name=` only. *(Conform "helpers are optional", Phoenix escape hatches.)*
7. **Widgets are functions, themes are class maps, and a copyable components module is the exit.** No CSS in the library. *(FormKit sections/classes, simple_form wrappers, Phoenix "generate the component into the app".)*
8. **Lists and unions are protocol, not user code.** Add/remove/move rows and switching union variants go through generated markup that the form object interprets; users never write index arithmetic or management forms. *(Ecto `sort_param`/`drop_param` + LiveView `inputs_for`, Conform intents, AshPhoenix `_add_x`/`_drop_x`.)*
9. **The client is Phoenix's; the server decodes exactly what it sends.** Bracket names verbatim, `_target`, submitter buttons, `JS.dispatch("change")`, debounce, recovery — and nothing that Phoenix has deprecated (`phx-feedback-for`).
10. **Testable without a socket.** `Form(Model).submit({...})` in a unit test; a `wire()` helper produces exactly the pairs the client would send for the rendered inputs.
11. **Human, label-aware messages by default; i18n by design.** A catalog keyed by pydantic error code with `{label}` and `ctx` interpolation, overridable per app/model/field, translated at render time.
12. **Progressive, not magical.** Level 0 is a model plus two three-line handlers; each further level is a small, local delta.

## 4.1 Mental model and vocabulary

```
 browser ── phx-change / phx-submit ──▶ ws_handler: parse_qsl(keep_blank_values=True)
                                              │
                                              ▼
                                      Params.decode(pairs, prefix="profile")
                                      ┌──────────────────────────────────────────────────────┐
                                      │ data     nested dict under the prefix, meta-free      │
                                      │ target   ("addresses", 0, "city") | None on submit    │
                                      │ intents  [Intent(op="add", path=("addresses",))]      │
                                      │ meta     _csrf_token, phx-value-*, submitter pairs …  │
                                      │ unused   1.x client _unused_ paths                    │
                                      │ recovered  True for a phx-auto-recover replay         │
                                      └──────────────────────────────────────────────────────┘
                                              │ form.validate(params) / form.submit(params)
                                              ▼
                 Form[Profile]  ── params (attempted strings, shelved union variants, row keys)
                                ── data (initial instance) · model (typed, when valid)
                                ── errors + external_errors · used · action · flags
                                              │ form.addresses[0].city  /  form["addresses"]["0"]["city"]
                                              ▼
                                      Field(path) ── .html (name, id, value, errors, label, hint, attrs, type, key)
                                                  ── .typed · .used · rows via iteration
                                              │
                          Ibis filters / t-string helpers / auto-render / hand-written HTML
```

| pyview | Phoenix / Ecto | Conform | Django |
|---|---|---|---|
| `Form(Model, data=…)` | `to_form(changeset)` + `changeset.data` | `useForm({defaultValue})` | `Form(instance=…)` |
| `form.validate(params)` | `cast … \|> Map.put(:action, :validate)` | `validate` intent | bound `Form(data=…)` |
| `form.submit(params)` | `apply_action(cs, :insert)` | submit → `parseWithZod` | `is_valid()` on POST |
| `form.params` | `changeset.params` | `submission.payload` | `form.data` |
| `form.model` | `apply_changes(cs)` | `submission.value` | `cleaned_data` |
| `form.errors` | `traverse_errors` | `submission.error` | `form.errors` |
| `form.used` | `used_input?` | `touchedFields` | — |
| `form.email` / `form["email"]` | `@form[:email]` | `fields.email` | `form["email"]` (BoundField) |
| `for row in form.addresses` | `<.inputs_for>` | `getFieldList()` | formset |
| intents `add/remove/move` | `sort_param`/`drop_param` | `insert/remove/reorder` | management form |

*Vocabulary.* The counter-design argued for keeping a separate `Changeset` because the maintainer said changesets resonated. The recommendation is one object named `Form`, with the changeset vocabulary — *cast*, *params*, *changes*, *action* — used in the API and docs so the mental model transfers; a second object would hold nothing that `Form` does not.

## 4.2 The golden path (level 0)

```python
from pydantic import BaseModel, EmailStr, Field, SecretStr
from pyview import LiveView, LiveViewSocket
from pyview.events import BaseEventHandler, event
from pyview.forms import Form, Params

class Registration(BaseModel):
    name: str = Field(min_length=3, max_length=40, title="Full name")
    email: EmailStr                                     # needs the `email-validator` extra
    password: SecretStr = Field(min_length=8)

class RegistrationView(BaseEventHandler, LiveView):
    async def mount(self, socket: LiveViewSocket, session):
        socket.context = {"form": Form(Registration)}

    @event("validate")
    async def validate(self, socket, params: Params):
        socket.context["form"].validate(params)

    @event("save")
    async def save(self, socket, params: Params):
        form = socket.context["form"].submit(params)
        if form.valid:
            await users.create(form.model)              # a Registration instance
            socket.put_flash("info", "Welcome!")
            await socket.push_navigate("/")
```

```html
<form id="registration" phx-change="validate" phx-submit="save" phx-auto-recover="validate">
  {{ form | render_form }}
  <button type="submit" phx-disable-with="Creating…">Create account</button>
</form>
```

Labels come from `title`/field names, `type="email"`/`"password"` from `EmailStr`/`SecretStr`, `required`/`minlength`/`maxlength` from the constraints, errors show per field after the user leaves it, values are preserved on re-render (never the password), and success yields a typed `Registration`. The form `id` is mandatory: the client keys form recovery by it. `Params` is injected by pyview's signature binding (`payload: dict` still works).

t-string version (Python 3.14):

```python
from pyview.forms.html import render_form

def template(self, assigns, meta):
    form = assigns["form"]
    return t"""<form id="registration" phx-change="{self.validate}" phx-submit="{self.save}">
        {render_form(form)}
        <button type="submit" phx-disable-with="Creating…">Create account</button>
    </form>"""
```

## 4.3 The progressive-disclosure ladder

| Level | You write | You get |
|---|---|---|
| 0 | `{{ form \| render_form }}` | every field, model order, default widgets, default theme |
| 1 | `{{ form.email \| form_field }}` per field inside your own layout | label + input + hint + errors, themed |
| 2 | `{{ form.email \| form_input({"type": "email", "placeholder": "you@…", "class": "w-full"}) }}` + `form_label` + `form_errors`, or `{% input form.email type="email" class="w-full" %}` | individual pieces with options |
| 3 | `<input name="{{ form.email.html.name }}" id="{{ form.email.html.id }}" value="{{ form.email.html.value }}" {{ form.email.html.attrs }}>` | raw HTML; only names/ids/values/attrs from the form |
| 4 | `Form(Model, messages=…, labels=…)`, `Annotated[str, Input(widget="textarea", rows=6)]`, custom widget functions, a copied `components.py`, a `Theme` | customised auto-render |

**Ibis syntax, decided.** The vendored Ibis splits filter arguments on commas without tracking brackets, so a two-key dict argument is a `TemplateSyntaxError` today **(verified)**. Phase 2 therefore ships two things: a six-line bracket-aware `splitc` in `pyview/vendor/ibis/utils.py` (verified to make `{"type": "email", "class": "w-full"}` and list arguments parse) and a `{% input %}`/`{% field %}` tag for keyword syntax. Filters are prefixed (`render_form`, `form_field`, `form_input`, `form_label`, `form_errors`, `form_debug`) because Ibis has one global filter map. Every example in Parts 4 and 5 uses only syntax that parses after that patch.

Level 1 (Ibis):

```html
<form id="profile" phx-change="validate" phx-submit="save" class="space-y-6">
  <div class="grid grid-cols-2 gap-4">
    {{ form.name | form_field }}
    {{ form.email | form_field }}
  </div>
  {{ form.password | form_field({"hint": "At least 8 characters"}) }}
  {{ form | form_errors }}                       {# error summary + form-level errors #}
  <button type="submit" phx-disable-with="Saving…">Save</button>
</form>
```

Level 3 (what `registration.html` does today, minus the hand-rolled filters):

```html
<label for="{{ form.email.html.id }}">Email</label>
<input type="email" name="{{ form.email.html.name }}" id="{{ form.email.html.id }}"
       value="{{ form.email.html.value }}" {{ form.email.html.attrs }}>
{% for msg in form.email.html.errors %}<p class="error" id="{{ form.email.html.id }}-error">{{ msg }}</p>{% endfor %}
```

`html.attrs` already contains `phx-debounce` per the form's timing policy and the `aria-*` wiring, so hand-written inputs get the same behaviour as generated ones.

## 4.4 Core API

```python
Path = tuple[str | int, ...]

@dataclass(frozen=True)
class Intent:
    op: Literal["add", "remove", "move"]; path: Path; key: str | None = None; arg: str | None = None

class Params(Mapping):                   # produced by ws_handler / binding, or by Params.decode in tests
    data: dict                           # nested, string-valued, under the form prefix, meta-free
    target: Path | None                  # trailing [] stripped; None on submit
    intents: list[Intent]
    meta: dict                           # _csrf_token, phx-value-*, submitter pairs outside the prefix
    unused: set[Path]                    # 1.x client only
    recovered: bool
    @classmethod
    def decode(cls, payload: str | dict | list[tuple[str, str]], *, prefix: str, recovered=False) -> Params

class Form(Generic[M]):
    def __init__(self, model: type[M], data: M | None = None, *, as_: str | None = None, id: str | None = None,
                 messages: Messages | None = None, labels: dict[str, str] | None = None,
                 empty_values: tuple = ("",), show_errors: Literal["blur", "live", "submit"] = "blur",
                 context: Any = None)
    # events (return self)
    def validate(self, params: Params | dict | list, *, recovered: bool = False) -> Form[M]
    def submit(self, params) -> Form[M]
    def add_error(self, path: str | Path, code: str, message: str, **params) -> Form[M]
    def reset(self, data: M | None = None) -> Form[M]
    # state
    params: dict; data: M | None; model: M | None; valid: bool; changed: bool
    errors: list[FormError]; external_errors: list[FormError]
    action: None | "validate" | "submit"; used: set[Path]
    submitted_once: bool; just_submitted: bool; applied_intents: list[Intent]; target: Path | None
    def errors_for(self, path, *, gated=True) -> list[FormError]
    def visible(self, path) -> bool
    def label_for(self, path) -> str
    def __getitem__(self, name) -> Field;  def __getattr__(self, name) -> Field   # model field names only
    def debug(self) -> str

@dataclass(frozen=True)
class Field:                             # sub-fields by attribute or item: form.addresses[0].city, form["addresses"]["0"]["city"]
    form: Form; path: Path
    html: Html                           # the template contract (below)
    typed: Any                           # value after cast (data + params), for derived state
    used: bool
    def __iter__(self) -> Iterator[Field] # rows of a list field

@dataclass(frozen=True)
class Html:
    name: str            # "profile[addresses][0][city]"
    id: str              # "profile_addresses_k7f3_city"  (row key, not index)
    value: str | list[str]
    errors: list[str]    # gated, translated
    label: str; hint: str | None; required: bool
    type: str            # inferred input type
    attrs: Markup        # required/minlength/maxlength/min/max/step/pattern/aria-describedby/aria-invalid/phx-debounce
    key: str | None      # row key when this field is a list row
    options: list[tuple[str, str]] | None; checked: bool

@dataclass(frozen=True)
class FormError:
    path: Path; code: str; params: dict; message: str; input: Any = None
```

**Why `.html`.** Ibis resolves `a.b` by attribute first, so a `Field` with attributes `name`, `id`, `value`, `label` would shadow model fields with those names — `{{ row.name }}` on an `Item(name: str)` would silently return the HTML name string. Sub-field navigation is the common case at every level; template-facing metadata therefore lives under one namespace, `field.html`, and Python widget code uses the same. Model fields named `form`, `path`, `html`, `typed`, `used` are reachable via `form["path"]`. Digit strings index rows (`form.addresses.0.city` works in Ibis) **(verified)**.

**`Params` is the wire→handler contract.** After phase 0, `ws_handler` decodes with `parse_qsl(keep_blank_values=True)` and hands handlers a `Params` (the raw `dict[str, list[str]]` stays available as `payload` for the existing binding, uploads and the `ChangeSet` shim). It accepts both client generations: metadata at the tail of the urlencoded string (0.20.17) and the `meta` JSON key (1.0.6+), and detects the 1.x `_unused_` prefix on the *last* bracket segment (`user[addresses][0][_unused_city]`) **(verified)**.

## 4.5 Data in

**Name grammar.** Phoenix bracket syntax, verbatim:

| name | decoded |
|---|---|
| `profile[name]` | `{"name": v}` |
| `profile[tags][]` (multi-select, checkbox group) | `{"tags": [v1, v2]}` |
| `profile[addresses][0][city]`, `…[2][city]` (row 1 removed client-side) | `[{"city": …}, {"city": …}]` — digit keys are collected then ordered numerically |
| `profile[account][kind]` + `profile[account][business][company]` | `{"account": {"kind": "business", "business": {"company": …}}}` (variant-named, 4.8) |
| `profile[addresses][_intent]=remove:k7f3` | popped into `params.intents` |
| `a=1&a=2` (plain repeated key) | last wins; use `[]` for lists |
| `profile[items][][name]` | rejected: `[]` may only be the last segment (Plug calls this ambiguous) |
| `profile[__class__]`, `…[__proto__]…` | rejected |

Limits: depth 32, 10 000 pairs; anything outside the form prefix (`_csrf_token`, `phx-value-*` pairs, another form's inputs) is `meta`, so `phx-value-*` can never collide with a field **(verified)**.

**What the client sends (verified against the 0.20.17 and 1.x sources; appendix `phoenix_client_js.md`).** `new FormData(form)` → `URLSearchParams`: names verbatim, document order, repeated keys kept, `File` entries removed, unchecked checkboxes and disabled inputs absent. In 0.20.17 `_target=<input name>` and each `phx-value-*` of the `<form>` are appended *inside* the string; from 1.0.6 they move to a `meta` key. `_target` is absent on submit and is the first non-hidden input's name on a recovery replay. pyview's current `parse_qs(value)` **silently drops `name=` pairs, so clearing a field never reaches the changeset today**; `parse_qsl(keep_blank_values=True)` fixes it.

**Cast (Ecto semantics) (verified).** The validation input is built per model field:

- absent from the payload → keep the initial `data` value (so an edit template may omit `id`, `created_at`, `last_watered`); no data → pydantic reports `missing` if required;
- present and empty (`""` after stripping, configurable `empty_values`) → the field's default, else `None` for `Optional`, else removed so pydantic reports `missing`. This *is* a change: clearing `note` on an edit form yields `None`, not the old text;
- present otherwise → the stripped string, handed to pydantic in lax mode;
- inside `list[...]`, empty elements are dropped; a list in the payload replaces the whole list;
- control keys (`_key`, `_intent`) never reach the model.

| HTML input | wire value | outcome |
|---|---|---|
| text-like | `"abc"` / `""` | str / default-or-None-or-missing |
| number | `" 21 "`, `"21.0"` → 21; `"1e3"` → `int_parsing`; `"1,5"` → `decimal_parsing` | lax pydantic **(verified)** |
| checkbox (`bool`) | absent / `"on"` | widgets render hidden `false` + checkbox `true` (Phoenix trick), so absence never happens; `"on"/"true"/"1"/"yes"` → True, `"off"/"false"/"0"/"no"` → False **(verified)**; a hand-written checkbox without the hidden twin keeps `data` when unchecked (documented) |
| checkbox group / select multiple → `list[...]` | repeated `name[]` | list; a single selection is still a list because of `[]` |
| select with prompt | `""` | default / None / missing |
| date / datetime-local / time | ISO strings | `date`, `datetime`, `time` **(verified)** |
| textarea | `"line1\r\nline2"` | newlines kept, ends stripped |
| password (`SecretStr`) | `"…"` | validated, **never re-rendered** (`html.value == ""`) **(verified)** |
| file | excluded by the client | uploads (4.9) |

**Attempted values.** `form.params` holds each decoded payload (Phoenix replace semantics — the client always serialises the whole form) plus two things the client cannot send: shelved union variants and row keys. `Field.html.value` reads params first, then the serialised initial data (`bool` → `"true"`, `datetime` → `YYYY-MM-DDTHH:MM`, `Enum` → `.value`, `SecretStr` → `""`), so an invalid `"abc"` in an `int` field is re-rendered as typed **(verified)**.

## 4.6 Validation and errors

**When.** `validate()` runs `Model.model_validate(cast(...), context=…)` on every `phx-change` (≈20 µs). Traffic is shaped by the `show_errors` policy the widgets encode as `phx-debounce`: `"blur"` (default; the first event for a field arrives when the user leaves it — the Wroblewski/Baymard result), `"live"` (`phx-debounce="300"`), `"submit"` (GOV.UK: no change-time errors at all). Hand-written inputs get the same behaviour from `html.attrs`. `submit()` validates, sets `action="submit"`, `submitted_once` and `just_submitted`, and clears `external_errors`.

**Gating (verified).**

```
visible(path) ⇔ action == "submit"  or  ∃ u ∈ used : u[:len(path)] == path
```

A path is visible when it was itself used or when it is an *ancestor* of a used path (Phoenix `used_input?` recursion: a list shows its "add at least one" error once any row was touched); children never inherit used-ness, so a freshly added row shows nothing until typed in. `used` grows by: the `_target` path of every change; the list path of every intent; every non-blank path on a recovery replay; everything on submit. On a 1.x client the `_unused_` paths are authoritative and simply remove entries. Errors the server added deliberately (`add_error`) are never gated.

**No `phx-feedback-for`.** The first draft emitted it "for recovery"; the client research shows the client re-adds `phx-no-feedback` after *every* patch to containers whose input was never focused — which would hide list-level errors after an intent and server errors after `add_error`. Phoenix deprecated the mechanism for the same reasons. Recovery is handled explicitly instead: `phx-auto-recover="validate"` on the form makes the client replay one `phx-change` after a reconnect; `Params.recovered` marks every non-blank path used, the closest server-side equivalent of the client's copied focus flags **(verified)**.

**Cross-field errors on specific fields.** Two idioms, both **(verified)**:

```python
class Registration(BaseModel):
    password: SecretStr = Field(min_length=8)
    password_confirmation: SecretStr

    @field_validator("password_confirmation")           # idiom 1: error lands on the confirmation field
    @classmethod
    def match(cls, v, info: ValidationInfo):
        if "password" in info.data and v.get_secret_value() != info.data["password"].get_secret_value():
            raise PydanticCustomError("mismatch", "Passwords do not match")
        return v

class Booking(BaseModel):
    start: date
    end: date
    @model_validator(mode="after")                        # idiom 2: model-level rule, field-targeted error
    def order(self):
        if self.end < self.start:
            raise field_errors(end=("after_start", "{label} must be after {start}", {"start": self.start}))
        return self
```

`field_errors(**{field: (code, template, ctx)})` wraps `ValidationError.from_exception_data(...)`; paths compose inside lists (`("items", 1, "hi")`). A plain `raise ValueError("…")` keeps `loc == ()` in a `model_validator` (form-level, shown in the summary after submit) but gets the field's loc in a `field_validator`. After-validators do not run while field errors exist, so cross-field messages appear once the fields parse.

**Error records and messages.** Every pydantic error becomes `FormError(path, code, params, message)`; smart-union member names are stripped from `loc`, discriminated-union tags are kept (they are part of the name, 4.8). The message comes from a catalog keyed by code, with `str.format` templates over `ctx` plus a guaranteed `{label}` (GOV.UK: a message reuses the words of the question): "Full name is required", "Watering schedule (days) must be at least 1", "Company name must be at least 2 characters" **(verified)**. Plural entries are `(singular, plural, count_key)` routed through `ngettext`. Lookup is most-specific-first with list indices stripped: `("addresses.zip", code)` → `(Model, code)` → `code` → catalog → pydantic's `msg`, so nothing crashes on an unknown code. A `ValueError` from a user validator is shown verbatim; anything that needs translation raises `PydanticCustomError(code, template, ctx)`.

```python
Form(Profile, messages={"string_too_short": "Use at least {min_length} characters",
                        ("name", "string_too_short"): "{label} needs {min_length}+ letters"},
              labels={"addresses.zip": "Postcode"})
forms.configure(messages={...}, translate=gettext.gettext, ntranslate=gettext.ngettext)   # app-wide; per-Form wins
```

Labels: `Field(title=)` → `labels=` override → humanised name; `Field(description=)` is the hint; `Field(examples=)` the placeholder. An `errors.pot` is extractable from the catalog (Phoenix's `priv/gettext/errors.pot`).

**Server-side checks** (uniqueness, remote lookups) live in the handler, not in the form object — I/O stays out of the data structure (the SOLID critique of Ecto changesets):

```python
@event("save")
async def save(self, socket, params: Params):
    form = socket.context["form"].submit(params)
    if form.valid and await users.exists(email=form.model.email):
        form.add_error("email", "unique", "That email is already registered")
    if form.valid:
        ...
```

External errors survive re-validation until the next submit (Superforms' `setError` caveat) and are always visible **(verified)**.

**Error summary and flags.** `{{ form | form_errors }}` renders the GOV.UK error-summary pattern (`role="alert"`, one link per visible error to `{id}`, focus moved there when `just_submitted`), and the same message strings appear inline. `submitted_once`, `just_submitted` and `changed` are the flags templates keep needing (AshPhoenix, elm-form). `form.error_tree` exposes the Superforms/Zod-v4 nested shape for JSON APIs.

**Validation context.** `Form(..., context={"user": user})` is passed to `model_validate(context=)` for validators that read `ValidationInfo.context`.

## 4.7 Rendering

**The `Field.html` object is the contract.** All helpers are functions of a `Field` plus options; Ibis filters and t-string functions wrap the same widget layer (≈5 lines each).

Ibis (after the phase-2 `splitc` patch; keyword syntax via the tag):

```html
{{ form | render_form }}                                  {# level 0 #}
{{ form | render_form(["name", "email"]) }}               {# subset, in this order #}
{{ form.email | form_field }}                             {# label + input + hint + errors #}
{{ form.email | form_field({"hint": "We never share it"}) }}
{{ form.email | form_input({"type": "email", "placeholder": "you@example.com", "class": "w-full"}) }}
{% input form.email type="email" class="w-full" %}        {# same, keyword syntax #}
{{ form.email | form_label }} {{ form.email | form_errors }}
{{ form.bio | form_input({"widget": "textarea", "rows": 6}) }}
{{ form.role | form_input({"options": roles}) }}          {# a context variable as option list (works after the patch) #}
{{ form | form_errors }}                                  {# summary + form-level errors #}
{% for row in form.addresses %} … {{ row.city | form_field }} … {% endfor %}
{{ form | form_debug }}
```

t-strings (`pyview.forms.html`): `render_form(form, only=[...])`, `field(form.email, hint=…)`, `input(form.email, type="email", **attrs)`, `label(...)`, `errors(field_or_form)`, `debug(form)`; rows by iterating the field.

**Inference (type → widget)**, overridable by `Annotated[..., Input(...)]` or `Field(json_schema_extra={"widget": ...})`:

| annotation | widget | notes |
|---|---|---|
| `str` | text | `SecretStr` → password (never re-rendered), `EmailStr` → email, `HttpUrl` → url, `Input(widget="textarea")` → textarea |
| `int`, `float`, `Decimal` | number | `step="1"` for int; `ge/le` → `min/max`; `multiple_of` → `step` |
| `bool` | checkbox | hidden `false` + checkbox `true` |
| `Enum`, `Literal[...]` | select | prompt option when optional; `Input(widget="radio")` for radios |
| `list[Enum]`, `list[Literal]` | checkbox group / select multiple | name gets `[]` |
| `list[str]`, `list[int]` | repeatable input rows | add/remove intents |
| `date`, `datetime`, `time` | date / datetime-local / time | |
| `Optional[T]` / default | same widget, not required, label gets "(optional)" | |
| `BaseModel` | fieldset with legend | nested names |
| `list[BaseModel]` | fieldset per row + add/remove/move buttons | 4.8 |
| discriminated `Union` | select for the tag + the active variant's fieldset | 4.8 |
| `Annotated[..., Upload("avatar")]` | `live_file_input` | 4.9 |

UI hints next to the type keep the model the single source of truth; a side-car `Form(Model, ui={"bio": Input(widget="textarea")})` serves models you do not own:

```python
class Profile(BaseModel):
    bio: Annotated[str, Input(widget="textarea", rows=5, hint="Markdown is fine")] = ""
    country: Annotated[str, Input(options=COUNTRIES, autocomplete="country")]
    state: Annotated[str, Input(options=lambda form: STATES.get(form.country.typed, []))]
    api_key: Annotated[str, Input(exclude=True)]          # never auto-rendered
```

`Input(...)` is a plain marker (like `annotated_types`), ignored by pydantic. Conditional *visibility* is template logic or a discriminated union — **hidden is not deleted**: a field hidden by an `{% if %}` keeps its params and is validated as usual; if a branch is truly optional, model it as `Optional`/a union (the first draft's "drop hidden values" rule would have produced `missing` errors and was withdrawn).

**Widget registry.** Resolution by tester rank (JSON Forms): each widget declares `matches(field) -> int`; `is_enum` (2) beats `is_str` (1); an app-registered `is_country_code` (5) beats both; `Input(widget=…)` wins outright. A widget is `def textarea(field: Field, theme: Theme, **attrs) -> Markup`. Wrapper templates (`form_field` = label + control + hint + errors) are replaceable independently of controls, and every default widget accepts `attrs`, so most customisations *wrap* a default rather than reimplement it.

**Default markup = the GOV.UK form-group contract**: `<label for="{id}">`, hint at `{id}-hint`, error at `{id}-error` with a visually hidden "Error:" prefix, `aria-describedby="{id}-hint {id}-error"` (only the parts that exist), `aria-invalid="true"` while an error is visible, error class on wrapper and control, `required`/`minlength`/… (a `novalidate` option for submit-only policies), "(optional)" on optional labels, `autocomplete`/`inputmode` from hints, `phx-debounce` per policy. List rows are `<fieldset>` + `<legend>` ("Address 2"); a polite live region announces add/remove and focus moves to the new row's first input via `push_event` + the shipped hook. Submit buttons are never disabled until valid, only during submission (`phx-disable-with`).

**Theme = class map; `components.py` = the exit.**

```python
@dataclass(frozen=True)
class Theme:
    field: str = "field"; label: str = "label"; input: str = "input"; input_error: str = "input-error"
    hint: str = "hint"; error: str = "error"; fieldset: str = "fieldset"; legend: str = "legend"
    row: str = "row"; row_actions: str = "row-actions"; button: str = "button"; summary: str = "error-summary"

forms.configure(theme=TAILWIND)      # or Form(Profile, theme=…)
```

Unstyled semantic markup is the default; `pyview.forms.themes` ships `TAILWIND` and `DAISY`. Beyond class names, users copy `pyview/forms/components.py` (the default widgets, ~150 lines) into their project and register their versions — Phoenix's `core_components.ex` stance, so the "customisation wall" of schema-driven UIs has a documented door.

## 4.8 Nested, dynamic and conditional forms

**Nested models** need nothing: `form.address.city.html.name` is `profile[address][city]`; `{{ form.address | form_field }}` renders a `<fieldset>`.

**List rows.** Iterating `form.addresses` yields one `Field` per current row; `row.city.html.name` is `profile[addresses][0][city]` and `row.html.id` is `profile_addresses_k7f3` — a **stable row key** in the DOM id, so removing or reordering rows does not re-id inputs and the browser keeps focus and scroll (LiveView's `_persistent_id`). The key travels in a hidden `profile[addresses][0][_key]` input **(verified)**.

**Intents (verified against the client mechanics).** A `phx-click` carries no form values; only `phx-change`/`phx-submit` serialise the form, and a named `<button>` that dispatches a `change` event is treated as the submitter, so its `name`/`value` ride along with every current value. The row helpers emit exactly that:

```html
<button type="button" name="profile[addresses][_intent]" value="add" phx-click='[["dispatch",{"event":"change"}]]'>Add address</button>
<button type="button" name="profile[addresses][_intent]" value="remove:k7f3" phx-click='[["dispatch",{"event":"change"}]]'>Remove</button>
<button type="button" name="profile[addresses][_intent]" value="move:k7f3:up" …>↑</button>
```

`Params.decode` pops the control key into `params.intents`; `Form.validate()` applies them to `params` before validation, marks the list path used and records them in `form.applied_intents`, so a handler can react (refuse an add, focus the new row, announce it) and a test can assert what happened. An intent event is a `validate`, never a save. Pending debounce timers flush on blur and submit, so clicking a button after typing loses nothing; the focused input is never value-patched, so renumbering names under a focused row is safe. Fallback without JS commands: a `<button type="submit" name="profile[addresses][_intent]" formnovalidate>` placed *after* the real submit button (Enter-key implicit submission picks the first submit button). Minimum/maximum rows come from `Field(min_length=, max_length=)`; an empty list with a minimum renders that many blank rows; very large repeaters belong in LiveComponents or streams.

**Discriminated unions with variant-named inputs (verified with the real client ordering).**

```python
class Personal(BaseModel):
    kind: Literal["personal"] = "personal"; nickname: str = Field(min_length=2)
class Business(BaseModel):
    kind: Literal["business"] = "business"; company: str = Field(min_length=2, title="Company name"); vat_id: str | None = None
class Profile(BaseModel):
    account: Annotated[Personal | Business, Field(discriminator="kind")]
```

The tag select is `profile[account][kind]`; the variant inputs are **namespaced by tag**: `profile[account][business][company]`, `profile[account][personal][nickname]`. Cast lifts the active variant (`{"kind": tag, **params["account"][tag]}`) and keeps the other variants in `params` untouched. Consequences: pydantic's `loc` `('account', 'business', 'company')` *is* the input name — no tag stripping; when the user switches the select, the client sends the old fieldset's values together with the new tag (the old inputs are still in the DOM at that moment) and nothing is polluted, because they arrive under their own tag; switching back restores the typed values; `extra="forbid"` models are safe. The first draft's same-named inputs plus a "shelf" was tested against an ordering the client cannot produce and was withdrawn (Part 8). Errors on the tag (`union_tag_invalid`, `missing`) render at `form.account.kind`.

**Dependent fields (country → state).** `Input(options=lambda form: …)` is evaluated at render time; the handler resets the stale value when `form.target == ("country",)`.

**Wizards.** (a) One model per step, composed at the end — the nested-forms research's recommendation when steps differ; each step is an ordinary `Form`, validated dicts accumulate in `socket.context`, zero new API. (b) One model for all steps: whole-model validation with per-step visibility via `form.step(paths)` (errors and `valid` restricted to those paths), and hidden inputs for the other steps' values emitted by `{{ form | form_hidden(exclude=paths) }}` so Back and recovery never lose data. Both are documented; neither needs merged params.

## 4.9 Uploads, CSRF, security

- **Uploads.** `live_file_input` renders a flat name outside the form prefix and the upload manager looks configs up by `_target`, so file inputs are correctly classified as `meta` and never reach the model. A model field `Annotated[list[UploadedFile], Upload("avatar", accept=[".png"], max_entries=1)]` is *skipped* during `validate()` and filled at submit time from `consume_uploads()` in the handler (`form.submit(params, uploads={"avatar": entries})`), which is where the async consumption already lives. Phase 4.
- **CSRF.** The socket join validates the token; forms with `action=` (for `phx-trigger-action`) get a hidden `_csrf_token`.
- **Mass assignment.** Only model fields are cast; unknown keys are ignored (`extra="forbid"` models produce a form-level error); `_intent`/`_key` never reach the model.
- **Limits.** Decoder depth 32, 10 000 pairs, dunder segments rejected, `[]` only as the last segment **(verified)**; row intents respect `max_length`.

## 4.10 Multiple forms, LiveComponents, testing, debugging

Two forms in one view need distinct `as_` prefixes (and DOM ids); inputs outside a form's prefix are `meta` to it. Inside a `LiveComponent`, `phx-target={meta.myself}` routes `validate`/`save` to the component's `handle_event`, where the form lives in the component's context; recovery needs the form's DOM `id` either way.

```python
def test_registration_rejects_short_password():
    form = Form(Registration).submit({"registration[name]": ["Larry"], "registration[email]": ["l@x.io"], "registration[password]": ["short"]})
    assert not form.valid and form.password.html.errors == ["Password must be at least 8 characters"]

def test_add_address_intent():
    form = Form(Profile).validate(wire(form := Form(Profile), target="profile[addresses][_intent]",
                                       submitter=("profile[addresses][_intent]", "add")))
    assert len(list(form.addresses)) == 1 and form.applied_intents[0].op == "add"
```

`wire(form, values, target=, submitter=)` (verified) serialises the *rendered* inputs the way the 0.20.17 client does — hidden `_key`, active union variant only, submitter pair, `_target` — the equivalent of `Phoenix.LiveViewTest.form/3 |> render_change()`. `{{ form | form_debug }}` renders params, used paths, action, errors and the model (superforms' `SuperDebug`); dev mode warns when two fields resolve to the same DOM id.

## 4.11 Migration, module layout, auto-routing

`pyview/forms/`: `params.py` (decoder, `Params`, intents), `form.py` (`Form`, `Field`, cast), `errors.py` (`FormError`, catalog, `field_errors`), `components.py` (default widgets, copyable), `theme.py`, `ibis.py` (filters + tag), `html.py` (t-string helpers), `testing.py` (`wire`), `uploads.py` bridge.

`pyview.changesets.ChangeSet` becomes a shim for one release: `apply(payload)` → `Form.validate(Params.decode(payload))`, `save(payload)` → `submit`, `attrs` → `SimpleNamespace` of `html.value`s (untouched fields now render their initial values instead of `""`), `errors` → `{first path segment: message}` for visible errors (model-level errors move to the form level). The two shipped examples keep rendering; the one behavioural change is that clearing a field now validates as empty — the bug fix.

**Auto-routed events (`Form(Registration, on_submit=…)`)** stay deferred, now with the analysis the critique asked for: with `BaseEventHandler` the form would register `form.change_event`/`form.submit_event` names in the dispatch table; t-strings render `{form.change_event}`; components dispatch by `cid` first, so a form registered on a component routes there. Feasible, but it adds a hidden dispatch rule to the golden path; the explicit handlers are two three-line methods.
