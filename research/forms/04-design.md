# Part 4 — Proposed design: `pyview.forms`

This part turns the research into a concrete proposal. It is opinionated on purpose; every choice names the library it was taken from and the alternative that was rejected. Everything marked **(verified)** was exercised against pydantic 2.13 / the Phoenix 0.20.17 client source in the prototype spike (see Part 7).

## 4.0 Design principles

1. **The pydantic model is the schema.** Names, types, defaults, constraints, nesting, lists and unions all come from the model. No parallel form class (Django/WTForms) unless the user wants one. *(Django ModelForm, simple_form, AshPhoenix auto forms, superforms constraints.)*
2. **One object to pass around.** A `Form` holds raw params, typed data, errors, "used" state and an action; a `Field` is a computed view onto it (`name`, `id`, `value`, `errors`, `attrs`). Templates and widgets only ever touch `Field`. *(Phoenix `FormField`, Conform metadata.)*
3. **Params in, model out, errors as data.** Whole-model validation on every change (it costs ~20 µs); errors are `(path, code, params, message)` records addressed by the same paths as input names. *(Ecto `{msg, opts}`, pydantic `loc`/`type`/`ctx`, Standard Schema issues.)*
4. **Show errors only for inputs the user has used, or after a submit.** Two orthogonal gates: `used` paths (from `_target`) and `action` (`None` → `"validate"` → `"submit"`). *(Phoenix `action` + `used_input?`, Conform `touchedFields`, RHF `onTouched`, GOV.UK/Baymard timing research.)*
5. **Attempted values always survive.** Re-render from raw params, never from the model. *(Ecto `params`, ASP.NET `ModelState.AttemptedValue`, Conform `initialValue`.)*
6. **Rendering is layered and every layer is optional**: auto-render → per-field helpers → attribute helpers → hand-written HTML with `name=` only. *(Conform's "helpers are optional", Phoenix escape hatches, RJSF templates.)*
7. **Widgets are functions, themes are class maps.** No CSS in the library; a theme is a dict of class strings; markup is overridable per widget. *(FormKit `rootClasses`/sections, simple_form wrappers, Phoenix "generate the component into the app".)*
8. **Lists and conditionals are protocol, not user code.** Add/remove/reorder rows and switching union variants are handled by the form object through generated markup; users never write index arithmetic or management forms. *(Ecto `sort_param`/`drop_param` + LiveView `inputs_for`, Conform intents, AshPhoenix `add_form`.)*
9. **Server state is the truth, the client is Phoenix's.** We keep the accumulated params on the socket, decode the client's bracket names exactly like `Plug.Conn.Query`, and use only client features that exist in 0.20.17 (`_target`, submitter buttons, `JS.dispatch`, `phx-debounce`, `phx-feedback-for`), with a clear upgrade path to the 1.x `_unused_` protocol.
10. **Testable without a socket.** `Form(Model).submit({...})` in a unit test, no websocket, no template.
11. **Human messages by default, i18n by design.** A catalog maps pydantic error codes to plain-language templates; apps override per app/model/field; gettext plugs in at render time. *(Rails/Ecto/Laravel/Django all separate code from message; GOV.UK content rules.)*
12. **Progressive, not magical.** Level 0 is two lines; each further level is a small, local delta; nothing at a lower level breaks when you go up a level.

## 4.1 Mental model and vocabulary

```
                 phx-change / phx-submit (urlencoded, names like profile[addresses][0][city])
   browser ───────────────────────────────────────────────────────────────────────▶ ws_handler
                                                                                     │ parse_qsl (ordered)
                                                                                     ▼
                                                                              decode_form()      ← Plug.Conn.Query rules
                                                                                     │ {"profile": {...}}, meta {_target: path}
                                                                                     ▼
              ┌───────────────────────────────  Form[Profile]  ─────────────────────────────────┐
              │ params  : dict   raw strings, nested, exactly what the user typed (attempted values)│
              │ data    : Profile | None   the instance the form was opened with (edit forms)       │
              │ model   : Profile | None   the validated instance, when valid                        │
              │ errors  : list[FormError]  (path, code, params, message, input)                      │
              │ used    : set[path]        inputs the user interacted with (_target, intents, submit)│
              │ action  : None | "validate" | "submit"                                              │
              │ keys    : row identity per list path (persistent ids for DOM ids)                   │
              └────────────────────────────────────────────────────────────────────────────────────┘
                                                                                     │ form["addresses"][0]["city"]
                                                                                     ▼
                                       Field(name, id, value, errors, label, hint, attrs, type, options, rows…)
                                                                                     │
                                            Ibis filters  /  t-string helpers  /  auto-render  /  raw HTML
```

| pyview | Phoenix / Ecto | Conform | Django |
|---|---|---|---|
| `Form(Model, data=…)` | `to_form(changeset)` + `changeset.data` | `useForm({defaultValue})` | `Form(instance=…)` (unbound) |
| `form.validate(payload)` | `changeset \|> Map.put(:action, :validate)` | `validate` intent | `Form(data=…)` + `is_valid()` |
| `form.submit(payload)` | `apply_action(cs, :insert)` | submit → `parseWithZod` | `is_valid()` on POST |
| `form.params` | `changeset.params` | `submission.payload` | `form.data` |
| `form.model` | `apply_changes(cs)` | `submission.value` | `cleaned_data` (as object) |
| `form.errors` | `traverse_errors` | `submission.error` | `form.errors` |
| `form.used` | `used_input?` / `phx-feedback-for` | `touchedFields` | — |
| `form["email"]` | `@form[:email]` (FormField) | `fields.email` | `form["email"]` (BoundField) |
| `form["addresses"]` rows | `<.inputs_for>` | `getFieldList()` | formset |
| intents `add/remove/move` | `sort_param`/`drop_param` | `insert/remove/reorder` | management form |

Vocabulary note: the research suggested keeping the word *changeset* for the data layer. Since pydantic already owns casting and validation, a separate changeset object would be an empty shell; we therefore use **Form** for the stateful object and keep `pyview.changesets.ChangeSet` as a compatibility wrapper (see 4.11).

## 4.2 The golden path (level 0)

Ibis (`registration.py` + `registration.html`):

```python
from pydantic import BaseModel, EmailStr, Field, SecretStr
from pyview import LiveView, LiveViewSocket
from pyview.events import BaseEventHandler, event
from pyview.forms import Form

class Registration(BaseModel):
    name: str = Field(min_length=3, max_length=40, title="Full name")
    email: EmailStr
    password: SecretStr = Field(min_length=8)

class RegistrationView(BaseEventHandler, LiveView):
    async def mount(self, socket: LiveViewSocket, session):
        socket.context = {"form": Form(Registration)}

    @event("validate")
    async def validate(self, socket, payload: dict):
        socket.context["form"].validate(payload)

    @event("save")
    async def save(self, socket, payload: dict):
        form = socket.context["form"].submit(payload)
        if form.valid:
            await users.create(form.model)          # a Registration instance
            socket.put_flash("info", "Welcome!")
            await socket.push_navigate("/")
```

```html
<form phx-change="validate" phx-submit="save">
  {{ form | render }}
  <button type="submit" phx-disable-with="Creating…">Create account</button>
</form>
```

That is the whole thing: labels from `title`/field names, `type="email"`/`"password"` inferred from `EmailStr`/`SecretStr`, `required`/`minlength`/`maxlength` from the constraints, errors shown per field after the user touches it, all values preserved on re-render, and a typed `Registration` on success.

t-string version (Python 3.14):

```python
from pyview.forms.html import render

class RegistrationView(AutoEventDispatch, TemplateView, LiveView):
    ...
    def template(self, assigns, meta):
        form = assigns["form"]
        return t"""<form phx-change="{self.validate}" phx-submit="{self.save}">
            {render(form)}
            <button type="submit" phx-disable-with="Creating…">Create account</button>
        </form>"""
```

**Open decision (recommendation: later phase).** An even shorter path is possible by letting the form route its own events: `socket.context["form"] = Form(Registration, on_submit=self.register)` renders `phx-change="form:registration:validate"` and the LiveView base class dispatches those events to the form before `handle_event`. It removes the two three-line handlers but adds a hidden dispatch rule. Ship the explicit handlers first; add auto-routing once the core is stable.

## 4.3 The progressive-disclosure ladder

| Level | You write | You get |
|---|---|---|
| 0 | `{{ form \| render }}` | every field, in model order, default widgets, default theme |
| 1 | `{{ form.email \| field }}` per field, your own layout HTML around them | label + input + hint + errors per field, still themed |
| 2 | `{{ form.email \| input({"type": "email", "placeholder": "you@…", "class": "…"}) }}` + `{{ form.email \| label }}` + `{{ form.email \| errors }}` | individual pieces |
| 3 | `<input name="{{ form.email.name }}" id="{{ form.email.id }}" value="{{ form.email.value }}" {{ form.email.attrs }}>` | raw HTML; only names/ids/values/attrs come from the form |
| 4 | `Form(Model, widgets={...}, theme=MyTheme, messages={...})`, `Annotated[str, Input(widget="textarea", rows=6, hint="…")]`, custom widget functions, custom intents | customised auto-render |

Level 1 example (Ibis), a typical hand-laid-out form:

```html
<form phx-change="validate" phx-submit="save" class="space-y-6">
  <div class="grid grid-cols-2 gap-4">
    {{ form.name | field }}
    {{ form.email | field }}
  </div>
  {{ form.password | field({"hint": "At least 8 characters"}) }}
  {{ form | errors }}                       {# form-level errors (model validators) #}
  <button type="submit" phx-disable-with="Saving…">Save</button>
</form>
```

Level 3 example (exactly what the existing `registration.html` does today, minus the hand-rolled filters):

```html
<label for="{{ form.email.id }}">Email</label>
<input type="email" name="{{ form.email.name }}" id="{{ form.email.id }}"
       value="{{ form.email.value }}" phx-debounce="blur" {{ form.email.attrs }}>
{% for msg in form.email.errors %}<p class="text-red-600">{{ msg }}</p>{% endfor %}
```

## 4.4 Core API

```python
class Form(Generic[M]):
    def __init__(self, model: type[M] | TypeAdapter, data: M | dict | None = None, *,
                 as_: str | None = None,            # name prefix; default = snake_case(Model)  ("registration")
                 id: str | None = None,             # DOM id prefix; default = as_
                 widgets: dict | None = None, theme: Theme | None = None,
                 messages: Messages | None = None,  # catalog overrides
                 context: Any = None,               # pydantic validation context (current user, db)
                 checks: list[Check] = ())          # post-validation server checks (uniqueness, ...)

    # ---- events (all return self so they chain) ----
    def validate(self, payload: dict | list[tuple[str, str]]) -> Form[M]   # phx-change
    def submit(self, payload) -> Form[M]                                     # phx-submit
    def reset(self, data: M | dict | None = None) -> Form[M]
    def apply(self, intent: Intent) -> Form[M]                              # add/remove/move rows, set a value

    # ---- state ----
    params: dict            # attempted values (nested, strings/lists)
    data: M | None          # initial instance
    model: M | None         # validated instance, when valid
    valid: bool
    errors: list[FormError] # ALL errors (ungated)
    action: Literal[None, "validate", "submit"]
    used: set[Path]
    def errors_for(self, path: Path, *, gated=True) -> list[FormError]
    def visible_errors(self) -> list[FormError]           # for an error summary
    def field(self, path: str | Path) -> Field            # "addresses.0.city" or ("addresses", 0, "city")
    def __getitem__(self, name) -> Field                  # form["email"], form["addresses"][0]["city"]
    def __getattr__(self, name) -> Field                  # form.email  (only for model field names)
    def rows(self, path) -> list[Field]                   # list field rows
    def debug(self) -> str                                # params/errors/used dump for a <details> panel

class Field:
    name: str          # "registration[email]" / "profile[addresses][0][city]"
    id: str            # "registration_email" / "profile_addresses_k7f3_city"  (row key, not index)
    path: Path
    value: Any         # attempted value (string), else initial value serialised for HTML
    errors: list[str]  # GATED, translated messages
    all_errors: list[FormError]
    used: bool
    label: str         # Field(title=) or humanised name
    hint: str | None   # Field(description=) or Input(hint=)
    required: bool
    attrs: Attrs       # required/minlength/maxlength/min/max/step/pattern/aria-* (renders as HTML attrs)
    input_type: str    # inferred: text/email/password/number/checkbox/select/date/datetime-local/textarea/file/…
    options: list[Option] | None   # for Enum/Literal/bool selects
    checked: bool                  # for checkboxes
    key: str | None    # stable row key when this field is a list row
    def __getitem__(self, key) -> Field      # nested / row access
    def __iter__(self) -> Iterator[Field]    # rows of a list field
    def intent(self, op: str, **kw) -> Attrs # attributes for add/remove/move buttons (see 4.8)

@dataclass(frozen=True)
class FormError:
    path: Path              # ("addresses", 0, "city"); () = form level
    code: str               # pydantic error type or custom code ("string_too_short", "unique")
    params: dict            # ctx: {"min_length": 3}
    message: str            # translated, human
    input: Any = None
```

`Form` is a plain object stored in `socket.context` like any other assign. It is not tied to a socket, so tests construct it directly.

**Binding integration (nice-to-have).** pyview's signature binding can inject the payload already; a follow-up could let handlers declare `form: Form[Registration]` to receive the context's form with the payload applied. Not required for v1.

## 4.5 Data in

**Name grammar** — Phoenix bracket syntax, verbatim, because the JS client, `_target`, `phx-feedback-for` and the future `_unused_` protocol all assume it:

| name | decoded |
|---|---|
| `profile[name]` | `{"profile": {"name": v}}` |
| `profile[tags][]` (multi-select, checkbox group) | `{"profile": {"tags": [v1, v2]}}` |
| `profile[addresses][0][city]` | `{"profile": {"addresses": [{"city": v}]}}` |
| `profile[addresses][2][city]` after row 1 was removed | index maps are compacted in numeric order → `[..., {"city": v}]` |
| `profile[account][kind]` + `profile[account][company]` | `{"profile": {"account": {"kind": …, "company": …}}}` |
| `a=1&a=2` (plain repeated key) | last wins (Plug/Rack semantics); use `[]` for lists |

The decoder is ~60 lines **(verified, prototype `decode_form`)**: split on brackets, `[]` appends, digit segments become dict keys first and are converted to ordered lists afterwards (so sparse indices after a client-side removal still work), depth limit 32, `__proto__`/dunder segments rejected, plain repeated keys last-wins. `_target` (sent by the client as the input *name string*) is decoded into a path tuple the same way, e.g. `("profile", "addresses", 0, "city")` — which is exactly what LiveView's channel does server-side.

**What the client actually sends (verified against the 0.20.17 and 1.x sources, see Appendix `phoenix_client_js.md`).** The payload is `new FormData(form)` → `URLSearchParams`: names verbatim, document order, repeated keys kept, `File` entries removed, unchecked checkboxes and disabled inputs absent. In 0.20.17 the metadata rides *inside* the string, appended after the fields: `_target=<input name>` on change (absent on submit; the first non-hidden input's name on form recovery) and each `phx-value-*` of the `<form>`; from 1.0.6 the same data moves to a `meta` JSON key on the event, and 1.x adds `_unused_<name>=` siblings (`user[addresses][0][_unused_city]=`) for inputs never used. The decoder therefore (a) must use `parse_qsl(keep_blank_values=True)` — pyview's current `parse_qs(value)` **silently drops `name=` pairs, so clearing a field never reaches the changeset today** — and (b) reads meta from the tail of the string *or* from `payload["meta"]`, so a client upgrade is a one-line switch.

**Meta keys** stripped from the form namespace: `_target`, `_csrf_token`, `_method`, `_unused_*` (1.x client), and top-level `phx-value-*` keys, which arrive outside the `as_` prefix anyway.

**Empty values (the Ecto rule).** Before validation the payload is normalised: strings are stripped, and `""` is treated as *absent*. pydantic then reports `missing` for required fields and applies defaults for optional ones, instead of `int_parsing` on `""` **(verified: `""` fails for int, float, Decimal, bool, date, datetime, Enum and even `Optional[int]` in lax mode)**. A `str` field with `min_length` gets `missing`, not `string_too_short`, which reads better ("This field is required"). Opt-out per form: `Form(..., empty_values=())`.

**Coercion table** (lax mode does the rest; only the gaps are handled by the form layer):

| HTML input | wire value | form layer | pydantic (lax) |
|---|---|---|---|
| text / email / url / tel / search / password | `"abc"` | strip | str |
| number | `" 21 "`, `"21.0"`, `"1e3"` | strip | `int` accepts `"21"`, `"21.0"`; rejects `"1e3"` (`int_parsing`) **(verified)** |
| number with `,` decimal (locale) | `"1,5"` | optional locale hook | `decimal_parsing` **(verified)** |
| checkbox (single `bool`) | absent / `"on"` | rendered with hidden `false` + checkbox `true` (Phoenix trick) so absence never happens; `"on"`,`"true"`,`"1"`,`"yes"` → True, `"off"`,`"false"`,`"0"`,`"no"` → False **(verified)** | bool |
| checkbox group → `list[str]`/`list[Enum]` | repeated `name[]` | `[]` decoding | list |
| select | `""` for the prompt option | absent → default/missing | Enum/Literal |
| select multiple | repeated `name[]` | list; a single value is still a list because of `[]` | list |
| date / datetime-local / time | ISO strings | pass through | `date`, `datetime`, `time` **(verified for date & datetime-local)** |
| textarea | `"line1\r\nline2"` | keep newlines; strip only ends | str |
| file | excluded by the client | uploads API (4.9) | — |
| hidden `_key` | row key | identity only | — |

**Attempted values.** `form.params` is replaced by each decoded payload (Phoenix semantics: the client always serialises the whole form). `Field.value` reads params first, then the initial `data`, serialised for HTML (`bool` → `"true"`, `datetime` → ISO without `Z`, `Enum` → `.value`). This is why an invalid `"abc"` in an `int` field is re-rendered as typed.

**Initial data.** `Form(Profile, data=profile_instance)` (edit) or `data={"name": "…"}` (partial defaults). Nested lists render one row per element; `Form(Profile)` renders `min_length` empty rows for lists with a minimum, otherwise none plus an add button.

## 4.6 Validation and errors

**When.** `validate()` runs `Model.model_validate(normalised_params, context=…)` on every `phx-change`. Cost ≈ 20 µs for a 60-field nested model **(verified)**; per-keystroke traffic is controlled by `phx-debounce` (default emitted by the widgets: `phx-debounce="blur"` for text-like inputs — the timing GOV.UK/Baymard research supports: validate when the user leaves the field, re-validate live once a field has an error). `submit()` runs the same validation, then the `checks` (server checks that need I/O), and sets `action="submit"`.

**Gating (what the user sees).**

```
visible(field) = action is not None and (action == "submit" or field.path (or a prefix/child of it) ∈ used)
```

A per-field/per-form **`show_errors` knob** (FormKit's `validation-visibility`) tunes this: `"blur"` (default: the widget emits `phx-debounce="blur"`, so the first event for a field arrives when the user leaves it), `"live"` (`phx-debounce="300"`), `"submit"` (never before submit — the GOV.UK policy), `"dirty"` (as soon as the value differs from the initial one). `Input(show_errors="live")` on a field, `Form(show_errors=...)` for the whole form.

`used` grows by: the `_target` path of every `phx-change`; the list path of every intent; all present paths on submit. A parent path counts as used when any child is (LiveView `used_input?` semantics). Form-level errors (path `()`) show only after submit, or when *every* field they name is used — model validators should therefore attach errors to fields (next paragraph). This server-side tracking works with the 0.20.17 client as is; the widgets additionally emit `phx-feedback-for="{name}"` on error containers so the client-side hiding still applies during form recovery. When pyview upgrades the client to 1.x, `used` is simply seeded from the `_unused_*` keys instead.

**Cross-field errors on specific fields (the Ecto `add_error` ergonomics).** Two idioms, both **(verified)**:

```python
class Registration(BaseModel):
    password: SecretStr = Field(min_length=8)
    password_confirmation: SecretStr

    # idiom 1: field_validator with info.data → error lands on password_confirmation
    @field_validator("password_confirmation")
    @classmethod
    def match(cls, v, info: ValidationInfo):
        if "password" in info.data and v != info.data["password"]:
            raise PydanticCustomError("mismatch", "Passwords do not match")
        return v

class Booking(BaseModel):
    start: date
    end: date
    # idiom 2: model_validator raising field-targeted errors via a tiny helper
    @model_validator(mode="after")
    def order(self):
        if self.end < self.start:
            raise field_errors(end=("after_start", "Must be after {start}", {"start": self.start}))
        return self
```

`field_errors(**{field: (code, template, ctx)})` builds `ValidationError.from_exception_data(...)` with the right `loc`; the paths compose correctly inside nested lists (`("items", 1, "hi")`). Errors from a plain `raise ValueError("…")` keep loc `()` and become form-level errors.

**Error records and messages.** Every pydantic error becomes `FormError(path=loc, code=type, params=ctx, message=…)`. The message comes from a catalog keyed by code, with `str.format`-style templates over `ctx`; the default catalog is human ("Must be at least {min_length} characters", "Enter a whole number", "This field is required") and covers the ~30 codes forms actually hit; unknown codes fall back to pydantic's `msg`. Overrides, most specific wins:

```python
Form(Profile, messages={
    "string_too_short": "Use at least {min_length} characters",         # per form, per code
    ("name", "string_too_short"): "Your name needs {min_length}+ letters",  # per field
})
forms.configure(messages={...}, translate=gettext.gettext)            # app-wide + i18n hook
```

`translate(template) -> template` is applied before formatting so `.po` files contain the templates; plural forms go through `ngettext` when `params` has a `count`-like key. Labels: `Field(title=)` → `Input(label=)` → humanised name; `Field(description=)` becomes the hint.

**Server checks** (uniqueness, remote lookups — things pydantic cannot do): `Form(..., checks=[unique_email])` where `async def unique_email(model, form) -> list[FormError]` runs on submit after pydantic passes, mirroring Ecto constraints ("after the fact") and Conform's server-only validation. `form.add_error("email", "unique", "Already registered")` covers the post-save `IntegrityError` case.

**External errors survive re-validation.** Errors added by `checks` or `form.add_error(...)` are kept in a separate `external_errors` list (Superforms' `setError` caveat: schema re-validation on the next keystroke must not silently wipe "email already taken"). They are cleared when the field they name changes (`_target`), on the next submit, or explicitly.

**Errors as a tree, too.** `form.errors` is a flat list of records (easy to iterate for a summary); `form.error_tree` exposes the Superforms/Zod-v4 shape (`{"address": {"city": [...]}, "items": [{"qty": [...]}], "_errors": [...]}`) for templates and JSON APIs.

**Validation context.** `Form(..., context={"user": user, "db": db})` is passed to `model_validate(context=)` so validators can read it through `ValidationInfo.context`.

## 4.7 Rendering

**The `Field` object is the contract** (4.4). All rendering helpers are functions of a `Field` plus optional overrides; the same helpers are exposed as Ibis filters and as t-string functions, and all of them are ~5-line wrappers over the widget registry, so users can copy them.

Ibis (filters take positional args; a dict literal carries options):

```html
{{ form | render }}                                     {# whole form, level 0 #}
{{ form | render(["name", "email"]) }}                  {# subset, in this order #}
{{ form.email | field }}                                {# label + input + hint + errors #}
{{ form.email | field({"hint": "We never share it"}) }}
{{ form.email | input({"type": "email", "placeholder": "you@example.com", "class": "w-full"}) }}
{{ form.email | label }} {{ form.email | errors }}
{{ form.bio | input({"widget": "textarea", "rows": 6}) }}
{{ form.role | input({"options": roles}) }}             {# override options for a select #}
{{ form | errors }}                                     {# form-level errors / summary #}
{% for row in form.addresses %} … {{ row.city | field }} … {% endfor %}
```

(An optional `{% input form.email type="email" %}` tag would give keyword syntax; deferred.)

t-strings (`pyview.forms.html`):

```python
render(form); render(form, only=["name"]); field(form.email, hint="…"); input(form.email, type="email", **attrs)
label(form.email); errors(form.email); errors(form); rows(form.addresses)  # -> list[Field]
```

**Auto-render inference** (type → widget), overridable by `Annotated[..., Input(...)]` or `Field(json_schema_extra={"widget": ...})`:

| annotation | widget | notes |
|---|---|---|
| `str` | text | `SecretStr` → password, `EmailStr` → email, `HttpUrl`/`AnyUrl` → url, `constr(max_length>256)` or `Input(widget="textarea")` → textarea |
| `int`, `float`, `Decimal` | number | `step="1"` for int, `"any"` otherwise; `ge/le/gt/lt` → `min`/`max`; `multiple_of` → `step` |
| `bool` | checkbox | hidden `false` + checkbox `true` |
| `Enum`, `Literal[...]` | select | prompt option when optional; `Input(widget="radio")` for radios |
| `list[Enum]`, `list[Literal]` | select multiple / checkbox group | name gets `[]` |
| `list[str]`, `list[int]` | repeatable input rows | add/remove intents |
| `date`, `datetime`, `time` | date / datetime-local / time | |
| `Optional[T]`, default present | same widget, not `required` | |
| `BaseModel` | fieldset with legend | nested names |
| `list[BaseModel]` | fieldset per row + add/remove/move buttons | 4.8 |
| discriminated `Union` | select for the tag + the active variant's fieldset | 4.8 |
| `Annotated[..., Upload("avatar")]` | `live_file_input` | 4.9 |

UI hints live next to the type so the model stays the single source of truth:

```python
class Profile(BaseModel):
    bio: Annotated[str, Input(widget="textarea", rows=5, hint="Markdown is fine")] = ""
    country: Annotated[str, Input(options=COUNTRIES, placeholder="Choose…")]
    secret: Annotated[str, Input(exclude=True)]      # never auto-rendered
```

Conditional visibility is a closure, resolved with pyview's signature-driven binding (Filament's `fn (Get $get)` idea): `Input(visible=lambda form: form.kind.value == "business")` or `Input(visible=lambda account: account.kind == "business")` (typed access via the partially validated model when available). A field hidden by a rule is not rendered **and its value is dropped before validation** (JSON Forms `HIDE` and RJSF stale-`oneOf` data are the cautionary tales), so a hidden required field cannot block submission.

`Input(...)` is a plain dataclass marker (like `annotated_types` constraints); it is ignored by pydantic and read by the renderer. `model_config["form"] = {"order": [...], "fieldsets": {...}}` covers model-level layout hints.

**Widget registry.** Resolution is by tester rank (JSON Forms): each registered widget declares `matches(field) -> int` (0 = no, higher wins), so `is_enum` (2) beats `is_str` (1) and an app-registered `is_country_code` (5) beats both without touching the defaults; `Input(widget=...)` is rank ∞. A widget is `def textarea(field: Field, theme: Theme, **attrs) -> Markup`. `Form(widgets={"textarea": my_textarea})` or `forms.configure(widgets={...})` replaces one; `Input(widget=callable)` uses a one-off. Default widgets emit accessible markup: `<label for>`, `aria-describedby` pointing at hint and error ids, `aria-invalid="true"` when errors are visible, `required`/`minlength`/… from `attrs`, `phx-debounce="blur"` on text-like inputs, `phx-feedback-for` on the error container.

**Theme = class map + wrappers.**

```python
@dataclass(frozen=True)
class Theme:
    field: str = "field"          # wrapper div
    label: str = "label"
    input: str = "input"
    input_error: str = "input-error"
    hint: str = "hint"
    error: str = "error"
    fieldset: str = "fieldset"; legend: str = "legend"
    row: str = "row"; row_actions: str = "row-actions"; button: str = "button"

TAILWIND = Theme(input="w-full rounded-md border-gray-300 …", input_error="border-red-300 …", error="text-sm text-red-600 mt-1", …)
Form(Profile, theme=TAILWIND)   /   forms.configure(theme=TAILWIND)
```

Wrapper templates (`field` = label + control + hint + errors) are replaceable independently of the control widgets, and every default widget accepts the standard `attrs`, so most customisations *wrap* a default rather than reimplement it (RJSF's "wrapping BaseInputTemplate" lesson). Unstyled semantic markup is the default (works with Pico/water.css out of the box); `pyview.forms.themes` ships `TAILWIND` and `DAISY`. Anything beyond class names is done by overriding the widget function — the same escape Phoenix offers by generating `core_components.ex` into the app, without the copy step.

**Escape hatch.** Hand-written HTML needs only `field.name`, `field.id`, `field.value`, `field.attrs` and `field.errors`; auto-render is never required, and mixing levels in one form is fine.

## 4.8 Nested, dynamic and conditional forms

**Nested models** need nothing: `form.address.city` is a `Field` with name `profile[address][city]`, and `{{ form.address | field }}` renders a `<fieldset>`.

**List rows.** `{% for row in form.addresses %}` yields one `Field` per current row (from `params` or `data`); `row.city.name` is `profile[addresses][0][city]` and `row.id` is `profile_addresses_k7f3` — the DOM id uses a **stable row key**, not the index, so reordering or removing rows does not re-id inputs and the browser keeps focus and scroll (LiveView's `_persistent_id` lesson). The key travels in a hidden `profile[addresses][0][_key]` input.

**Intents: add / remove / move.** The Phoenix client only serialises the form on `phx-change`/`phx-submit`; a `phx-click` on a button carries no form data. Phoenix's recipe (named `type="button"` + `JS.dispatch("change")`) makes the click *become* a change event whose submitter is the button, so its `name`/`value` ride along with all current values. pyview already exposes `js.dispatch("change")`, so the helper generates:

```html
<button type="button" name="profile[addresses][_intent]" value="add"
        phx-click='[["dispatch",{"event":"change"}]]'>Add address</button>
<button type="button" name="profile[addresses][_intent]" value="remove:k7f3" phx-click='[["dispatch",{"event":"change"}]]'>Remove</button>
<button type="button" name="profile[addresses][_intent]" value="move:k7f3:up"  …>↑</button>
```

`Form.validate()` sees `_intent` under a list path, applies it to `params` (append a blank row, drop the row with that key, swap) *before* validation, marks the list path used, and re-renders. No management form, no index arithmetic, no JS beyond what the client already ships **(verified in the 0.20.17 source: `pushInput` sets `meta.submitter = inputEl` when the dispatching element is a `<button>`, and `serializeForm` injects the submitter's `name`/`value` as a hidden pair at the button's DOM position — the exact mechanic behind LiveView's own add/remove-row recipe)**. Fallback for apps that prefer plain events: `phx-click="form:intent" phx-value-path=… phx-value-op=…` applies the same intent to the *last known* params (which the server keeps), at the cost of possibly missing keystrokes typed since the last change event.

Two client facts shape the details: pending `phx-debounce` timers are flushed on blur and on submit, so clicking an add/remove button (which blurs the input) does not lose the last keystrokes; and the *focused* input is never value-patched during a DOM update, so a server-side reformat of the field being typed in (e.g. `" 1,000 "` → `1000`) only appears after blur — display normalisation must be designed for blur/submit re-renders, not keystrokes.

Minimum/maximum rows come from `Field(min_length=, max_length=)`; the add button is omitted at the max and remove buttons at the min. An empty list with a minimum renders that many blank rows.

**Discriminated unions (conditional nesting).**

```python
class Personal(BaseModel):
    kind: Literal["personal"] = "personal"
    nickname: str = Field(min_length=2)

class Business(BaseModel):
    kind: Literal["business"] = "business"
    company: str = Field(min_length=2)
    vat: str | None = None

class Profile(BaseModel):
    account: Annotated[Personal | Business, Field(discriminator="kind")]
```

Auto-render emits a select for `kind` and the fieldset of the *selected* variant only; changing the select is an ordinary `phx-change`, the server re-validates and re-renders the other fieldset. Errors inside a variant carry the tag in their pydantic `loc` (`("account", "business", "company")`) and are mapped back onto `form.account.company` by skipping the tag segment **(verified)**. Values typed into the previously selected variant are kept on a per-tag shelf inside the form (`form.params` only holds the active variant; `form.shelf["account"]["personal"]`) so switching back and forth is lossless — the one thing Conform cannot do because it trusts the DOM only. Manual templates branch on `form.account.kind.value`.

**Dependent fields (country → state).** Nothing special: the state select's `options` are computed in the handler from `form.country.value` (or a callable `Input(options=lambda form: states_for(form.country.value))`), and `_target` tells the handler which field changed.

**Wizards.** Whole-model validation makes steps a *view* concern: `form.step(["name", "email"])` returns a proxy whose visible errors are limited to those paths and whose `valid` means "no errors under these paths"; "Next" is enabled when the step is valid, "Back" keeps params. Alternatively use one model per step and compose at the end; both are documented.

## 4.9 Uploads, CSRF, security

- **Uploads**: a field annotated `Annotated[list[UploadEntry], Upload("avatar", accept=[".png"], max_entries=1)]` renders `live_file_input` and binds to `socket.allow_upload`; `form.model` exposes consumed entries in `submit()` via the existing `consume_uploads()` API.
- **CSRF**: the socket join already validates the token; forms rendered with `action=` (for `phx-trigger-action`) get a hidden `_csrf_token`.
- **Mass assignment**: only model fields are read; unknown keys are ignored (pydantic `extra="ignore"` default) and `extra="forbid"` models produce a form-level error; `_intent`/`_key` are consumed by the form and never reach the model.
- **Limits**: decoder depth 32, max 10 000 pairs, list index ≤ 10 000, dunder segments rejected; row intents validate against `max_length`.

## 4.10 Testing and debugging

```python
def test_registration_rejects_short_password():
    form = Form(Registration).submit({"registration": {"name": "Larry", "email": "l@x.io", "password": "short"}})
    assert not form.valid
    assert form.errors_for(("password",))[0].code == "string_too_short"
    assert form["password"].errors == ["Must be at least 8 characters"]

form.validate(encode({"registration": {"name": "ab"}}, target="registration[name]"))   # helper builds the wire format
```

`{{ form | debug }}` renders a `<details>` panel with params, errors, used paths and the model (superforms' `SuperDebug`); in dev mode, widgets warn when an `id` collides or a `name` is not under the form prefix.

## 4.11 Migration and module layout

`pyview/forms/` — `decode.py` (bracket decoder, `_target`), `form.py` (`Form`, `Field`, intents), `errors.py` (`FormError`, catalog, `field_errors`), `widgets.py` (default widgets), `theme.py`, `ibis.py` (filters), `html.py` (t-string helpers), `uploads.py` bridge. `pyview.changesets.ChangeSet` becomes a thin wrapper around `Form` (`changeset.attrs.name` → `form.params.get("name")`, `changeset.errors.get("name")` → first gated message) so the two shipped examples keep working; new docs use `Form`.
