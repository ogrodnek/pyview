# Alternative design: `pyview.forms` as an explicit changeset pipeline

Competing proposal, written independently of `report/04-design.md` and compared with it at the end. Angle: Ecto/Conform purist. Two objects, not one: a **`Changeset`** that knows nothing about HTML (cast → validate → action; composable validators; explicit intents; schemaless from a dict of types) and a **`Form`** adapter that only computes names/ids/values/errors for templates. Rendering is *your* HTML plus a handful of helpers; auto-rendering is deliberately out of the core.

Every client claim below is from `research/phoenix_client_js.md` (0.20.17 source) and every pydantic claim from `research/pydantic_core.md` or the spike (`proto/pyview_forms_proto*.py`, run: `ALL OK`).

## 1. Pitch

"Here's my pydantic class, do the rest" is a slogan about *data*, not about markup. What the maintainer's other project actually needs — deeply nested, conditional forms — is decided by three things: how the wire is decoded, how raw strings become typed values and errors, and how add/remove/switch-variant operations are expressed. Those are protocol; get them right once and every template style works. Markup, by contrast, is what users most want to own (the brief: "users may want to provide their own HTML"; Phoenix's decision to *generate* `<.input>` into the app rather than ship it; every schema-UI generator's "escape-hatch cliff" in `research/schema_ui_generators.md`).

So this design spends its complexity budget on the data layer and keeps rendering to ~8 helpers:

- `Changeset.cast(Model | types, data, params, permitted=...)` → `.validate_*()` → `.add_error()` → `.apply_action("save")` → `Ok(model) | Err(changeset)`. A pipeline you can read, test with plain dicts, and reuse outside LiveView.
- `Intent` values (`add`, `remove`, `move`, `switch`) parsed from the wire and applied by an explicit `cs.apply_intent(i)` call — visible in the handler, testable, extensible.
- `to_form(cs, as_="profile", action=cs.action)` → `Form` / `FormField` with `name`, `id`, `value` (always a string), `errors` (gated), `label`, `constraints`, `used`, `key`; `form.inputs_for("addresses")` for rows.
- Helpers that emit attribute strings and tiny fragments, never layouts: `attrs`, `label`, `errors`, `checkbox`, `select`, `inputs_for`, `intent_button`, `hidden_inputs`.

The cost is ~4 more lines per view than an auto-rendered form. The gain: nothing in the library ever has to be fought when the design calls for a layout the library did not anticipate — which, for "complex deeply nested conditional" forms, is immediately.

## 2. Golden path

### 2.1 Ibis (Python 3.11+)

```python
# registration.py
from pydantic import BaseModel, Field, SecretStr
from pyview import LiveView, LiveViewSocket
from pyview.events import BaseEventHandler, event
from pyview.forms import Changeset, Params, to_form, Ok

class Registration(BaseModel):
    name: str = Field(min_length=3, title="Full name")
    email: str = Field(pattern=r".+@.+")
    password: SecretStr = Field(min_length=8)

def registration_changeset(data, params: Params) -> Changeset[Registration]:
    """Form-context rules live here, not on the model (Ecto's `changeset/2`)."""
    return (Changeset.cast(Registration, data, params)
            .validate_confirmation("password")          # reads params["password_confirmation"]
            .validate_acceptance("terms"))              # reads params["terms"]; neither is a model field

class RegistrationView(BaseEventHandler, LiveView):
    async def mount(self, socket: LiveViewSocket, session):
        socket.context = {"form": to_form(registration_changeset(None, Params()), as_="registration")}

    @event("validate")
    async def validate(self, socket, payload: dict):
        cs = registration_changeset(None, Params.decode(payload))     # cast + validate, action "validate"
        socket.context["form"] = to_form(cs, as_="registration", action="validate")

    @event("save")
    async def save(self, socket, payload: dict):
        match registration_changeset(None, Params.decode(payload)).apply_action("save"):
            case Ok(model):
                await users.create(model)
                socket.put_flash("info", "Welcome!")
                await socket.push_navigate("/")
            case Err(cs):
                socket.context["form"] = to_form(cs, as_="registration")   # action already "save"
```

```html
<!-- registration.html -->
<form id="registration" phx-change="validate" phx-submit="save" phx-auto-recover="recover">
  {{ form | errors }}                                   {# form-level summary (visible errors only) #}

  <label for="{{ form.name.id }}">{{ form.name.label }}</label>
  <input type="text" {{ form.name | attrs }} phx-debounce="blur">
  {{ form.name | errors }}

  <label for="{{ form.email.id }}">Email</label>
  <input type="email" {{ form.email | attrs }} phx-debounce="blur">
  {{ form.email | errors }}

  <label for="{{ form.password.id }}">Password</label>
  <input type="password" {{ form.password | attrs }} value="">   {# explicit: never echo a password #}
  {{ form.password | errors }}

  <label for="{{ form.password_confirmation.id }}">Confirm</label>
  <input type="password" {{ form.password_confirmation | attrs }} value="">
  {{ form.password_confirmation | errors }}

  <label>{{ form.terms | checkbox }} I accept the terms</label>
  {{ form.terms | errors }}

  <button type="submit" phx-disable-with="Creating…">Create account</button>
</form>
```

`{{ form.name | attrs }}` expands to `name="registration[name]" id="registration_name" value="…" required minlength="3" aria-invalid="true" aria-describedby="registration_name-error"` (the last two only while an error is visible). Fields that are not model fields (`password_confirmation`, `terms`) still get names/ids — Phoenix's "virtual field" rule (`liveview_forms.md`: accessing an unknown field still returns a `FormField`).

### 2.2 t-strings (Python 3.14)

```python
from pyview.forms.html import attrs, errors, checkbox, label

class RegistrationView(AutoEventDispatch, TemplateView, LiveView):
    ...
    def template(self, assigns, meta):
        f = assigns["form"]
        return t"""<form id="registration" phx-change="{self.validate}" phx-submit="{self.save}">
          {errors(f)}
          {label(f.name)} <input type="text" {attrs(f.name)} phx-debounce="blur"> {errors(f.name)}
          {label(f.email)} <input type="email" {attrs(f.email)} phx-debounce="blur"> {errors(f.email)}
          {label(f.password)} <input type="password" {attrs(f.password, value="")}> {errors(f.password)}
          <label>{checkbox(f.terms)} I accept the terms</label> {errors(f.terms)}
          <button type="submit" phx-disable-with="Creating…">Create account</button>
        </form>"""
```

`attrs(...)` returns `Markup` (auto-escape-safe); keyword overrides win over derived attributes. Ibis resolves `form.name` through `__getattr__`→`__getitem__` fallback (spike `exp3_ibis.py` rendered `{{ form.name.id }}` and `{{ form.addresses.1.city.value }}` with only `__getitem__` defined), so both engines see the same `Form`.

## 3. Core objects and signatures

```python
# pyview/forms/params.py
Path = tuple[str | int, ...]

@dataclass(frozen=True)
class Intent:
    op: Literal["add", "remove", "move", "switch", "reset"]
    path: Path                     # list or union field the intent targets, e.g. ("addresses",)
    key: str | None = None         # row key for remove/move
    arg: str | None = None         # "up"/"down"/index for move; variant tag for switch

class Params(Mapping[str, Any]):
    """Nested, string-valued, ordered. Never contains meta keys."""
    target: Path | None            # decoded from _target ("profile[addresses][0][city]" -> ("profile","addresses",0,"city"))
    intents: list[Intent]          # decoded from *[_intent] control keys (see 7)
    meta: dict[str, str]           # phx-value-*, _csrf_token, submitter name=value, 1.x _unused_* keys
    recovered: bool                # True when event came from phx-auto-recover (see 5.3)
    @classmethod
    def decode(cls, payload: dict[str, list[str]] | str | list[tuple[str, str]], *, prefix: str | None = None) -> "Params"
    def under(self, prefix: str) -> "Params"    # params["profile"] as a Params with paths rebased
```

```python
# pyview/forms/changeset.py
M = TypeVar("M", bound=BaseModel)
Types = type[M] | dict[str, Any]            # a pydantic model, or {"q": str, "page": int | None}

@dataclass(frozen=True)
class Error:
    path: Path                     # pydantic loc with union tags stripped; () = form level
    code: str                      # pydantic `type` or your own ("mismatch", "unique")
    ctx: dict[str, Any]            # pydantic ctx (+ label at render time)
    template: str                  # default message template; catalog may override by code
    input: Any = None

@dataclass(frozen=True)
class Changeset(Generic[M]):
    types: Types
    data: M | dict | None          # original values (edit forms); None for "new"
    params: Params                 # what the user sent, verbatim, all of it
    changes: dict[str, Any]        # TYPED, per top-level field, only where cast succeeded and value != data
    errors: tuple[Error, ...]      # all errors, ungated
    action: str | None = None      # None | "validate" | "intent" | "save" | any
    used: frozenset[Path] = frozenset()
    keys: Mapping[Path, list[str]] = ...   # row keys per list path (persistent ids)
    shelf: Mapping[Path, dict[str, dict]] = ...   # union variants' params by tag

    # ---- construction ----
    @classmethod
    def cast(cls, types: Types, data, params: Params | dict, *, permitted: Iterable[str] | None = None,
             empty_values: tuple = ("",), context: Any = None) -> "Changeset[M]": ...
    def cast(self, params, permitted=None) -> "Changeset[M]"        # merge more params (shallow, later wins)

    # ---- validators: run only on non-None changes (Ecto rule); all return a new Changeset ----
    def validate_required(self, *fields: str, message: str | None = None)
    def validate_change(self, field: str, fn: Callable[[str, Any], list[tuple[str, str, dict]]])
    def validate_confirmation(self, field: str, *, required=False)
    def validate_acceptance(self, field: str)
    def validate_model(self)                     # run model_validate on merged data+changes (cross-field validators)
    def add_error(self, path: str | Path, code: str, template: str, **ctx)

    # ---- intents & actions ----
    def apply_intent(self, intent: Intent, *, defaults: dict | None = None) -> "Changeset[M]"
    def apply_intents(self) -> "Changeset[M]"    # all of params.intents, in order; sets action="intent"
    def apply_action(self, action: str) -> "Ok[M] | Err[M]"
    def with_action(self, action: str | None) -> "Changeset[M]"

    # ---- reads ----
    valid: bool                                  # not errors
    model: M | None                              # built when valid, else None
    def get_field(self, path) -> Any             # typed: changes -> data (Ecto get_field)
    def get_change(self, path) -> Any | Missing
    def errors_at(self, path, *, children=False) -> list[Error]
    def error_tree(self) -> dict                 # {"address": {"city": [...]}, "_errors": [...]}
    def used_at(self, path) -> bool              # path, an ancestor, or a descendant is in `used`

@dataclass(frozen=True)
class Ok(Generic[M]): value: M
@dataclass(frozen=True)
class Err(Generic[M]): changeset: Changeset[M]
```

```python
# pyview/forms/form.py
def to_form(cs: Changeset[M], *, as_: str, id: str | None = None, action: str | None = None,
            messages: Messages | None = None, labels: dict[str, str] | None = None) -> Form[M]

class Form(Generic[M]):
    source: Changeset[M]; name: str; id: str; action: str | None; index: int | None; key: str | None
    def __getitem__(self, key: str | int) -> FormField      # form["email"], rows[0]["city"]
    def field(self, path: str | Path) -> FormField           # "addresses.0.city" or "addresses[0][city]"
    def inputs_for(self, field: str) -> list[Form]           # one sub-form per row / one for a nested model
    def hidden_inputs(self, field: str) -> Markup            # row keys (+ pk for edit forms)
    def visible_errors(self) -> list[tuple[FormField | None, str]]
    valid: bool; used: frozenset[Path]; changed: bool; submitted: bool

@dataclass(frozen=True)
class FormField:
    form: Form; field: str; path: Path
    name: str            # "profile[addresses][0][city]"
    id: str              # "profile_addresses_k7f3_city"  (row key, not index)
    value: str | list[str]   # ALWAYS html-ready strings: params -> changes(serialised) -> data(serialised)
    typed: Any           # cs.get_field(path): typed value or None (never a raw string)
    errors: list[str]    # GATED and translated
    all_errors: list[Error]
    used: bool; required: bool; label: str; hint: str | None
    constraints: dict[str, str | bool]   # required/minlength/maxlength/min/max/step/pattern/multiple
    options: list[tuple[str, str]] | None  # Enum/Literal/bool
    key: str | None
```

Why two objects: `Changeset` is reusable for JSON endpoints, CLI, tests and wizards; it has no `as_`, no ids, no HTML. `Form` is a *view* of a changeset: cheap, recomputed on every render, never stored. The socket stores the changeset (or the form, which holds it).

## 4. Data in / data out

### 4.1 Wire → `Params` (what actually happens on the 0.20.17 client)

1. `phx-change`: the client builds `new FormData(form)` → `URLSearchParams`, appends `_target=<input.name>` and every `phx-value-*` of the `<form>` *inside the string* (V0 `view.js` L105, L1011-1016). Names are verbatim (`profile[addresses][0][city]`), document order, repeated keys kept, `File` entries and unchecked boxes absent.
2. `phx-submit`: same, no `_target`; the submit button's `name=value` is injected at its DOM position (L63-79).
3. `ws_handler.py` L188-189: `value = parse_qs(value)` — **drops blank values** (`name=` disappears; `phoenix_client_js.md` "Python parsing" run). Phase 0 changes this to `parse_qs(value, keep_blank_values=True)`; the shape `dict[str, list[str]]` is unchanged so `binding` keeps working, but clearing a field now reaches the server.
4. `Params.decode(payload)`: bracket decoder with Plug rules (`a[b]` → dict, `a[]` → append, digit segments → dict keys then compacted to lists in numeric order, depth ≤ 32, dunder segments rejected), `_target` → path tuple, meta split out; also accepts `payload["meta"]` (1.0.6+) and strips `_unused_*` into `meta` so the same decoder survives a client upgrade.

### 4.2 `cast`: the Ecto algorithm on top of pydantic

Per top-level field of `types` (all of them, or `permitted`):

1. Look up `params[field]` (or the alias). Absent → **missing**: no change, no error, `data`'s value stays. This is what makes edit forms work when the template does not render every field (`id`, `created_at`).
2. Empty-value rule: a value in `empty_values` (default `("",)`; whitespace-only strings count) becomes the field's default when it has one, else `None`. Inside `list[...]`, empty elements are dropped first. **(pydantic fact: `""` fails every non-`str` type incl. `Optional[int]` — exp2.)** For `str` fields with data, `""` → `None`/default is a *change* (the user cleared it), unlike the draft's "treat as absent".
3. Type-cast with a cached `TypeAdapter(Annotated[fi.annotation, fi])` (0.3 µs/validate, 25 µs to build once per field — `pydantic_core.md`). Success → `changes[field] = value` if `!= data`; failure → `Error(path=(field,)+loc, code=type, ctx, template=msg, input=raw)`. Nested models and `list[Model]` cast recursively through the same adapter, so `('addresses', 0, 'city')` errors appear here.
4. Discriminated unions: `params[field]` is `{"kind": tag, tag: {...}}` on the wire (variant-named inputs, see 7.3); cast builds `{"kind": tag, **params[field][tag]}` and shelves the other variants. Errors keep pydantic's `('account', 'business', 'company')` loc; the *tag segment is stripped* when mapping to `FormField` names.
5. `bool`: checkbox helper renders hidden `false` + box `true`; `"on"/"true"/"1"/"yes"` → True, `"off"/"false"/"0"/"no"` → False (exp2). Without the helper an absent checkbox is "missing", i.e. keeps `data` (documented).

`validate_model()` then runs `Model.model_validate(merged(data, changes), context=...)` **only if no field errors exist** — matching pydantic's own rule that after-model-validators do not run when a field failed (exp4), so cross-field errors never appear as noise on top of type errors. `apply_action` calls it implicitly.

Schemaless: `Changeset.cast({"q": str, "page": int | None, "sort": Literal["asc", "desc"]}, {}, params)` builds (and caches by the dict's identity) a `create_model` model. Everything else is identical — Ecto's `{data, types}`.

### 4.3 Data out

- `cs.model` (typed instance) only when valid; `cs.get_field(("addresses", 0, "city"))` typed at any time (changes → data); `cs.changes` for PATCH-style updates.
- `FormField.value` is *always* an HTML string: params first (attempted value survives — the ASP.NET `AttemptedValue` lesson), then serialised changes, then serialised data (`bool` → `"true"/"false"`, `date` → ISO, `datetime` → `YYYY-MM-DDTHH:MM` for `datetime-local`, `Enum` → `.value`, `SecretStr` → `""`).

## 5. Validation, errors, messages, used-gating

### 5.1 Two gates, explicit

```
visible(field) = form.action is not None and (form.action == "save" or cs.used_at(field.path))
```

`used` grows from `params.target` on every change (the path and nothing else), from every intent's list path, and from *all present paths* on `apply_action("save")`. Ancestors count as used when a descendant is (Phoenix `used_input?` recursion); a new blank row is not used until typed in (spike proto2: "visible errors row2: []" right after `add`). A per-form policy can widen it: `to_form(cs, show_errors="submit")` (GOV.UK) or `"all"`.

### 5.2 Error records and the catalog

`Error(path, code, ctx, template, input)` is pydantic's `ErrorDetails` with the loc cleaned. Messages are rendered by `to_form` through:

```python
Messages = dict[str | tuple[str, str], str | tuple[str, str, str]]   # code | (field, code) -> template | (singular, plural, count_key)
forms.configure(messages={...}, translate=gettext.gettext, ntranslate=gettext.ngettext, labels=humanize)
```

Lookup most-specific-first with list indices stripped: `("addresses.zip", code)` → `(Model.__name__, code)` → `code` → catalog → pydantic `msg`. `{label}` is always available in templates (GOV.UK: reuse the label's words). Default catalog ≈ 30 codes (`missing`, `string_too_short{min_length}`, `int_parsing`, `greater_than_equal{ge}`, `too_short{min_length}`, `enum{expected}`, `union_tag_invalid`, …) from the verified table in `pydantic_core.md`; unknown codes fall back to pydantic's `msg`, so nothing crashes.

### 5.3 The recovery gap (0.20.17-specific)

After a reconnect the client re-pushes **one** `phx-change` with the old form's values and `_target` = first non-hidden input (`view.js` L1235-1262); the server's `used` set is gone with the remount. With `phx-auto-recover="recover"` on the form, `Params.decode` sets `recovered=True` for that event and `cast` marks every *non-blank* path used — the closest server-side approximation of the client's copied `phx-has-focused` privates. Without the attribute the form just re-renders with errors hidden until the next interaction; both behaviours are documented, neither relies on the deprecated `phx-feedback-for` CSS mechanism.

### 5.4 Example: model, form-context rules, server error

```python
class Address(BaseModel):
    street: str = Field(min_length=3)
    city: str
    zip: str = Field(pattern=r"^\d{5}$", title="ZIP code")

class Profile(BaseModel):
    name: str = Field(min_length=3)
    age: int = Field(ge=18)
    addresses: list[Address] = Field(min_length=1, max_length=3)

def profile_changeset(profile: Profile | None, params: Params, *, for_admin=False) -> Changeset[Profile]:
    cs = Changeset.cast(Profile, profile, params, permitted=("name", "age", "addresses"))
    if not for_admin:
        cs = cs.validate_change("age", lambda f, v: [("age", "too_old", "{label} must be under {max}", {"max": 120})] if v > 120 else [])
    return cs

@event("save")
async def save(self, socket, payload: dict):
    cs = profile_changeset(socket.context["profile"], Params.decode(payload))
    match cs.apply_action("save"):
        case Ok(profile):
            try:
                await repo.save(profile)
            except UniqueViolation:                       # constraints are "after the fact", never inside the changeset
                cs = cs.add_error("name", "unique", "{label} is already taken").with_action("save")
                socket.context["form"] = to_form(cs, as_="profile")
                return
            await socket.push_navigate(f"/profiles/{profile.id}")
        case Err(cs):
            socket.context["form"] = to_form(cs, as_="profile")
```

Test, no socket:

```python
def test_zip_error_is_addressed_by_path():
    cs = profile_changeset(None, Params({"name": "Larry", "age": "17",
                                        "addresses": [{"street": "Main St", "city": "Rome", "zip": "12"}]}))
    assert [ (e.path, e.code) for e in cs.errors ] == [(("age",), "greater_than_equal"), (("addresses", 0, "zip"), "string_pattern_mismatch")]
    assert cs.get_field(("addresses", 0, "city")) == "Rome"         # typed access despite errors elsewhere
    form = to_form(cs, as_="profile", action="save")
    assert form.inputs_for("addresses")[0]["zip"].errors == ["ZIP code is not in the right format"]
    assert form.inputs_for("addresses")[0]["zip"].name == "profile[addresses][0][zip]"
```

## 6. Rendering helpers and the escape hatch

The whole helper surface, exposed identically as Ibis filters and `pyview.forms.html` functions:

| helper | emits |
|---|---|
| `attrs(field, **over)` | `name id value` + constraints + `aria-invalid`/`aria-describedby` when an error is visible; `value=""` override for passwords |
| `label(field, text=None)` | `<label for="{id}">{text or field.label}</label>` |
| `errors(field \| form)` | `<p id="{id}-error" class="error">…</p>` per visible error; for a form: `<div role="alert">` summary linking `#{id}` |
| `checkbox(field)` | hidden `false` + `<input type="checkbox" value="true" checked?>` |
| `select(field, options=None, prompt=None, multiple=False)` | `<select name=…[]?>` with `<option selected>` from `field.value`; options from `Enum`/`Literal` by default |
| `inputs_for(form, field)` | rows as sub-`Form`s (Ibis: `{% for row in form | inputs_for("addresses") %}`) |
| `hidden_inputs(row)` | `<input type="hidden" name="…[_key]" value="k7f3">` (+ `[id]` for persisted children) |
| `intent_button(field, op, label, key=None, arg=None, **attrs)` | the `type="button" name=… value=… phx-click='[["dispatch",{"event":"change"}]]'` recipe (7.1) |

No `render(form)`, no widget registry, no theme object in core. Classes are passed as ordinary attributes (`{{ form.name | attrs({"class": "input"}) }}`); an app that wants one-liners writes a 15-line `components.py` (or Ibis filter file) on top of `FormField` — the Phoenix `core_components.ex` stance, minus the generator. An optional `pyview.forms.contrib.render` (schema → default fieldsets) can come later *on top of* this contract, but nothing in the core depends on it. **Escape hatch = the default**: any `<input name="{{ form.email.name }}">` works; `attrs` is sugar.

## 7. Nested, list, conditional, wizard — with the exact event flow

### 7.1 Lists (`list[Address]`)

Markup (Ibis):

```html
<form id="profile" phx-change="validate" phx-submit="save" phx-auto-recover="recover">
  {% for row in form | inputs_for("addresses") %}
    <fieldset id="{{ row.id }}"><legend>Address {{ row.index + 1 }}</legend>
      {{ row | hidden_inputs }}
      {{ row.street | label }} <input {{ row.street | attrs }} phx-debounce="blur"> {{ row.street | errors }}
      {{ row.city   | label }} <input {{ row.city   | attrs }} phx-debounce="blur"> {{ row.city   | errors }}
      {{ row | intent_button("remove", "Remove") }}
      {{ row | intent_button("move", "↑", {"arg": "up"}) }}
    </fieldset>
  {% endfor %}
  {{ form.addresses | errors }}                              {# list-level: too_short / too_long #}
  {% if not form.addresses.full %}{{ form.addresses | intent_button("add", "Add address") }}{% endif %}
  <button type="submit" phx-disable-with="Saving…">Save</button>
</form>
```

Handler:

```python
@event("validate")
async def validate(self, socket, payload: dict):
    params = Params.decode(payload)
    cs = profile_changeset(socket.context["profile"], params)
    if params.intents:                                       # explicit: the handler sees the operation
        cs = cs.apply_intents()                              # action becomes "intent" (never a save)
        socket.push_event("focus", {"id": to_form(cs, as_="profile").last_added_id})   # optional a11y hook
    socket.context["form"] = to_form(cs, as_="profile", action=cs.action or "validate")
```

Exact client flow for "Add address" (verified mechanics, `phoenix_client_js.md` §Data in / `nested_dynamic_patterns.md` §What pyview's client actually does):

1. `intent_button` renders `<button type="button" name="profile[addresses][_intent]" value="add" phx-click='[["dispatch",{"event":"change"}]]'>`.
2. Click → `JS.dispatch("change")` fires a `change` event with the button as source → `bindForms` resolves the form's `phx-change="validate"` → `pushInput` sets `meta.submitter = inputEl` because the source is an `HTMLButtonElement` (V0 `view.js` L1012).
3. `serializeForm` injects a hidden `profile[addresses][_intent]=add` at the button's DOM position, serialises **every current input value** (live DOM — keystrokes inside a pending debounce window are included), appends `_target=profile[addresses][_intent]`.
4. No form disabling, no HTML5 validation gate, no Enter-key implicit submission (the button is `type="button"`).
5. Server: `Params.decode` pops the `_intent` control key into `params.intents = [Intent("add", ("addresses",))]`, `cast` runs, `apply_intents` appends `{"_key": new_key()}` (refused at `max_length`), renumbers names `0..n-1`, marks `("addresses",)` used; the new row's `missing` errors exist but are not visible (proto2: `visible errors row2: []`).
6. Re-render: names are index-based and renumbered; **ids are key-based** (`profile_addresses_k7f3_street`), so morphdom matches by id, the focused input is never value-patched (`dom_patch.js` L233-241) and only its `name` attribute is merged — exactly what you want when row 0 is removed under the cursor (proto2 "after remove": key `k2`, value kept, name renumbered).

`remove:<key>` and `move:<key>:up` follow the same path. A submit that carries an intent (user pressed Enter on a submit button named as an intent — only possible if they hand-wrote one) is treated as `action="intent"`, never as a save (Conform's `status: undefined` rule). Phoenix's `_sort[]`/`_drop[]` protocol is accepted as an alternative encoding (`Intent.from_sort_drop`) so a drag-and-drop hook can rewrite hidden sort inputs.

### 7.2 Nested model (`address: Address`)

`form.inputs_for("address")` returns one sub-form; names `profile[address][city]`; nothing else to do.

### 7.3 Conditional nesting (discriminated union)

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

```html
{% with acct = form | inputs_for("account") %}
  {{ acct.kind | select({"prompt": "Account type"}) }}          {# name="profile[account][kind]" #}
  {% if acct.tag == "business" %}
    {% with b = acct | variant("business") %}                   {# inputs named profile[account][business][company] #}
      {{ b.company | label }} <input {{ b.company | attrs }}> {{ b.company | errors }}
      {{ b.vat     | label }} <input {{ b.vat     | attrs }}> {{ b.vat     | errors }}
    {% endwith %}
  {% else %}
    {% with p = acct | variant("personal") %}
      {{ p.nickname | label }} <input {{ p.nickname | attrs }}> {{ p.nickname | errors }}
    {% endwith %}
  {% endif %}
{% endwith %}
```

Flow: changing the `<select>` is an ordinary `phx-change` with `_target=("account","kind")`. `cast` reads `params["account"]["kind"]`, builds the active variant from `params["account"][tag]`, and shelves the others (`cs.shelf[("account",)]["business"]`), so switching back restores typed values even though the client only ever sends the rendered variant (proto2: "switched back; company restored: ACME"). Errors on the tag (`union_tag_invalid`, `missing`) render at `acct.kind`; variant errors map `('account','business','company')` → `profile[account][business][company]` 1:1, no tag stripping needed because the inputs are variant-named (`nested_dynamic_patterns.md` §Discriminated-union subforms). Because the `<select>`'s option set does not change it is not re-morphed; the client will re-morph and blur a select only when options changed (`dom_patch.js` L235/L245).

Non-union conditionals (`{% if form.plan.value == "pro" %}`) are plain template logic; hidden ≠ deleted — params are kept, and requiredness is the model's business (make it a union if a branch is truly required).

### 7.4 Wizard

One changeset per step, dicts on the socket, a composed model at the end — validation groups do not exist in pydantic and `experimental_allow_partial` is not that (`pydantic_core.md`).

```python
class Step1(BaseModel): name: str = Field(min_length=3); email: str
class Step2(BaseModel): addresses: list[Address] = Field(min_length=1)
class Step3(BaseModel): plan: Literal["free", "pro"]
class Signup(Step1, Step2, Step3): pass
STEPS = [Step1, Step2, Step3]

class WizardView(BaseEventHandler, LiveView):
    async def mount(self, socket, session):
        socket.context = {"step": 0, "data": {}, "form": self._form(0, {}, Params())}

    def _form(self, step, data, params, action=None):
        cs = Changeset.cast(STEPS[step], data.get(step), params)
        return to_form(cs, as_=f"step{step}", action=action)

    @event("validate")
    async def validate(self, socket, payload: dict):
        c = socket.context
        cs = Changeset.cast(STEPS[c["step"]], c["data"].get(c["step"]), Params.decode(payload)).apply_intents()
        c["form"] = to_form(cs, as_=f"step{c['step']}", action=cs.action or "validate")

    @event("next")                                            # phx-submit of the step form
    async def next(self, socket, payload: dict):
        c = socket.context
        match Changeset.cast(STEPS[c["step"]], c["data"].get(c["step"]), Params.decode(payload)).apply_action("save"):
            case Ok(model):
                c["data"][c["step"]] = model                   # typed, per step
                if c["step"] + 1 == len(STEPS):
                    signup = Signup.model_validate({k: v for m in c["data"].values() for k, v in m.model_dump().items()})
                    await signups.create(signup); await socket.push_navigate("/done"); return
                c["step"] += 1
                c["form"] = self._form(c["step"], c["data"], Params())
            case Err(cs):
                c["form"] = to_form(cs, as_=f"step{c['step']}")

    @event("back")
    async def back(self, socket):
        c = socket.context; c["step"] -= 1
        c["form"] = self._form(c["step"], c["data"], Params())   # rendered from the typed step data
```

Each step form has its own `id` (`step1`), so the client's per-form recovery (keyed by form id, `view.js` L1290-1300) re-validates the current step after a reconnect; `push_patch("?step=2")` gives deep links if wanted.

## 8. Testing

- `Changeset` is a frozen dataclass built from dicts: unit tests need neither socket nor template (§5.4).
- `Params.decode` accepts the exact wire string, a `parse_qs` dict, or pairs, so a test can replay a captured `phx-change`: `Params.decode("profile%5Bname%5D=ab&_target=profile%5Bname%5D")`.
- `pyview.forms.testing.wire(form, {"name": "ab"}, target="name")` produces the pairs the 0.20.17 client would send for the *rendered* inputs (the spike's `serialize()` generalised), including intent submitter pairs — the equivalent of `Phoenix.LiveViewTest.form/3 |> render_change()`.
- Golden tests for the message catalog keyed by pydantic error `type` strings (pinned; drift across pydantic minors shows up as a failing test, not a wrong message in production).

## 9. Migration from `pyview.changesets.ChangeSet`

`ChangeSet.apply(payload)` ≈ `Changeset.cast(cls, None, Params.decode(payload))` with the old "errors only for keys in changes" replaced by `used`. Compatibility layer, one release:

```python
# pyview/changesets/changesets.py (shim)
class ChangeSet(Generic[Base]):
    def __init__(self, cls, changes=None, errors=None, valid=False):
        self._cs = Changeset.cast(cls, None, Params(changes or {}))
    def apply(self, payload):                    # phx-change
        self._cs = Changeset.cast(self._cs.types, None, self._cs.params.merged(Params.decode(payload))).with_action("validate")
    def save(self, payload):                     # phx-submit
        match Changeset.cast(self._cs.types, None, Params.decode(payload)).apply_action("save"):
            case Ok(m): return m
            case Err(cs): self._cs = cs; return None
    @property
    def attrs(self):  return SimpleNamespace(**{k: to_form(self._cs, as_="").field(k).value for k in self._cs.model_fields})
    @property
    def errors(self): return {e.path[0]: render(e) for e in self._cs.errors if e.path and self._cs.used_at(e.path)}
    model = property(lambda self: self._cs.model); valid = property(lambda self: self._cs.valid)
```

The two shipped examples keep rendering (`changeset.attrs.name`, `changeset.errors.get("name")`); `ws_handler` switches to `keep_blank_values=True` (the only behavioural change: clearing a field now validates as empty, which is the fix). New docs use `Changeset`/`to_form`; the shim is deleted after one minor.

Module layout: `pyview/forms/{params.py, changeset.py, form.py, messages.py, ibis.py, html.py, testing.py}`; `contrib/render.py` later.

## 10. Where I disagree with the draft and why

1. **"A separate changeset would be an empty shell" (draft 4.1).** It is not: per-field typed `changes` (cached `TypeAdapter`s — the draft's whole-model `model_validate` yields *nothing typed* until everything is valid, so derived state like Phoenix's `calculate_remaining` must be recomputed from raw strings), `data`/`params` merge with a `permitted` list (edit forms with unrendered fields — `id`, `created_at` — become `missing` under the draft's "params replace everything" rule; mass assignment is left to `extra="ignore"`), form-context validators (`validate_confirmation`/`validate_acceptance`/`validate_change` keep `password_confirmation` and `terms` off the domain model — the Ecto "Data mapping and validation" argument, which the research flagged as the right split), and schemaless `types=` forms (search/filter forms without a class). Merging everything into one `Form` also makes the object unusable outside LiveView (JSON API validation reuse).
2. **Auto-render + widget registry with tester ranks + `Theme` class map + `Input(...)` annotations as the level-0 story.** That is four new public surfaces (registry, theme, hints, wrappers) before a single hand-written form works well, and every one of them is where schema-UI generators get "damned for customization walls" (`schema_ui_generators.md`, `pain_points_praise.md`). Phoenix's answer — generate the component into the app — is the honest one: ship a copyable `components.py`, not a registry. Auto-render can be a contrib layer on the same `FormField` contract later; it should not shape v1.
3. **`Input(visible=lambda ...)` drops hidden fields' values before validation.** UI visibility in the *data schema* is exactly the leak JSON Forms/RJSF regret, and "drop before validation" makes a hidden-but-required field silently pass. Discriminated unions already express "required only in this branch" in the type system; plain conditionals should keep params (the draft's own shelf argument) and leave requiredness to the model.
4. **Unconditional `"" → absent`.** For an edit form, "the user cleared the field" must become a change to `None`/default, not "keep the old value"; absent and empty are different things (Ecto: empty → default → a change if it differs from data).
5. **Widgets emit `phx-feedback-for` "for recovery".** Two gating mechanisms at once (server `used` + client CSS) on a mechanism upstream deprecated in 0.20.5 and removed in 1.0. Recovery is one event with a known shape (`_target` = first input, `phx-auto-recover`); handle it explicitly (§5.3).
6. **Intents applied silently inside `validate()`.** The handler cannot react (move focus, announce the new row, refuse an add for business reasons), and tests cannot assert what happened. Decode them into `Params.intents`, apply with one explicit call.
7. **`checks=[async fn]` on the Form constructor.** Putting I/O inside the form object mixes persistence into the data structure (the "SOLID Ecto Changesets" critique in `ecto_changeset.md`). Run I/O in the handler; `add_error` after the fact.
8. **`Form.__getattr__` for model field names.** A model with a field named `valid`, `errors`, `model`, `action` or `data` collides with the form's own attributes; Ibis already resolves `form.name` through `__getitem__`, so attribute access buys nothing in Ibis and only the collision in t-strings. Use `form["x"]` / `form.f.x` if you want dots in Python.
9. **`FormField.value: Any`.** The draft says "attempted value (string), else initial value serialised", which is right, but the type should be `str | list[str]` and enforced; the polymorphic-value warning in Phoenix's docs exists because it was not.
10. **Vocabulary.** The maintainer said changesets "resonated"; the draft renames the concept away. The name carries the mental model (cast/validate/action), which is the part worth keeping.

Where I agree and would not fight: the bracket grammar and Plug-compatible decoder; `parse_qsl`/`keep_blank_values`; `_target` as a path; used + action gating; `Error(path, code, ctx, template)` with a human catalog and `{label}`; row keys for ids; `JS.dispatch("change")` intent buttons; the union shelf; per-step wizards; whole-model validation being cheap; the GOV.UK markup contract.

## 11. Ideas the draft should steal from this design

1. `cast(types, data, params, permitted=)` with Ecto merge semantics (missing keeps `data`; empty becomes default/`None` and *is* a change) — it fixes edit forms and gives mass-assignment control for free.
2. Typed per-field `changes` via cached `TypeAdapter(Annotated[ann, fi])`, plus `get_field(path)` — derived state from partially valid forms without re-parsing strings.
3. Schemaless `types={"q": str, "page": int | None}`.
4. Form-context validators (`validate_required`, `validate_change`, `validate_confirmation`, `validate_acceptance`, `add_error`) so confirmation/terms fields never touch the domain model.
5. `Params` as a first-class decoded object (`target`, `intents`, `meta`, `recovered`) that `binding` can inject by type (`async def validate(self, socket, params: Params)`).
6. Explicit `Intent` values and `apply_intent(s)` in the handler; `_sort[]/_drop[]` accepted as an alternative encoding for drag-and-drop hooks.
7. `apply_action("save") -> Ok(model) | Err(changeset)` with `match` — the two-branch handler reads like Phoenix's generator and cannot forget to set the action.
8. Explicit recovery handling via `phx-auto-recover="recover"` + `Params.recovered` instead of `phx-feedback-for`.
9. Variant-named union inputs (`profile[account][business][company]`) so loc → name is 1:1 and no tag stripping is needed.
10. A copyable `components.py`/filter module as the styling story, with contrib auto-render layered on top later.
11. `FormField.value: str | list[str]` and `FormField.typed` as two separate, honestly typed properties.
12. `pyview.forms.testing.wire(form, values, target=)` that emits what the 0.20.17 client would send for the *rendered* inputs, including intent submitter pairs.
