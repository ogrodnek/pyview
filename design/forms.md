# Forms in pyview

Research notes and a proposal. Working document — nothing here is settled.

There is a runnable prototype alongside this doc (`pyview/forms/`, demo at `/forms`
in the examples app). It exists so the ideas can be *used* rather than only read;
the API is a sketch, not a commitment.

---

## The shape of the answer

If it works, it should look like this. This is the whole thing — no form classes,
no field declarations, no HTML:

```python
class Signup(BaseModel):
    email: str = Field(pattern=r"^[^@]+@[^@]+$")
    password: str = Field(min_length=12)


@dataclass
class Context:
    signup: Changeset[Signup] = field(default_factory=lambda: Changeset(Signup))


class SignupView(LiveView[Context]):
    async def mount(self, socket, session):
        socket.context = Context()

    async def handle_event(self, event, payload, socket):
        if event == "validate":
            socket.context.signup.validate(payload)
        elif event == "save":
            if result := socket.context.signup.submit(payload):
                create_user(result.value)          # a real, typed Signup
```

```html
<form phx-change="validate" phx-submit="save" novalidate>
  {{ signup.form.email | input }}
  {{ signup.form.password | input }}
  <button phx-disable-with="Saving...">Sign up</button>
</form>
```

and deep nesting should be the same call, one level down:

```html
{{ signup.form.address.city | input }}

{% for index, pet in signup.form.pets.rows %}
  {{ pet.name | input }}
  <button type="submit" formnovalidate name="_intent" value="drop:pets:{{ index }}">Remove</button>
{% endfor %}
<button type="submit" formnovalidate name="_intent" value="add:pets">Add a pet</button>
```

Everything below is why each of those lines looks the way it does.

---

## 1. Where we are now

`pyview/changesets/changesets.py` is 67 lines and does something real: pydantic
validation wired to `phx-change`. But it has four structural problems, and they
compound.

```python
class ChangeSet(Generic[Base]):
    cls: type[Base]
    changes: dict[str, Any]     # flat
    errors: dict[str, Any]      # flat, one error per field, message only
    valid: bool

    def apply(self, payload):
        k = payload["_target"][0]              # (1) one field at a time
        self.changes[k] = payload.get(k, [""])[0]
        ...
        for error in e.errors():
            loc = str(error["loc"][0])         # (2) loc[0] discards the path
            if loc in self.changes:            # (3) unseen fields never error
                self.errors[loc] = error["msg"]
```

1. **It merges one field per event.** The LiveView client serializes the *entire*
   form on every change; `_target` only names the input that fired. Merging
   field-by-field means an unchecked checkbox can never be cleared (its key
   simply stops arriving), and a browser autofill that populates six fields
   registers as one.
2. **`loc[0]` throws away the path.** `("pets", 0, "age")` becomes `"pets"`. Nesting
   is not partly supported; it is structurally impossible.
3. **`if loc in self.changes`** is a stand-in for "has the user been here yet?"
   It half-works — it does suppress errors on untouched fields — but it also
   permanently hides errors on fields nobody typed in, including on submit.
4. **No HTML.** Every project rewrites `input_tag`/`error_tag`; the
   `registration` example does exactly that, with Tailwind classes baked into
   the filter.

### Three bugs found underneath it

None of these are form-specific. All three block nested forms, and two of them
are quietly wrong for every pyview app today.

**Blank fields were dropped from every form payload.** `ws_handler` decoded form
bodies with `parse_qs(value)`, which defaults to `keep_blank_values=False`:

```python
>>> parse_qs("owner[pets][0][name]=Rex&owner[pets][1][name]=&owner[name]=")
{'owner[pets][0][name]': ['Rex']}          # the other two are simply gone
```

A field the user cleared is indistinguishable from a field that was never on the
form. Today's flat changeset accidentally survives this (`payload.get(k, [""])[0]`
turns a missing key back into `""`), which is why nobody noticed — but an empty
row of a repeated field vanishes entirely. Fixed by passing
`keep_blank_values=True`, which is what `Plug.Conn.Query.decode` does.

**A `{# comment #}` desynchronised the diff tree.** Statics and dynamics must
strictly alternate, because the client rebuilds markup as
`s[0] + d[0] + s[1] + d[1] + … + s[-1]`. A comment splits one run of text into two
`TextNode`s, and `PartsTree.add_static` appended both:

```python
>>> Template("A{# comment #}B{{x}}C").tree({"x": "1"})
{'s': ['A', 'B', 'C'], '0': '1'}     # 3 statics, 1 dynamic -> client renders "A1B"
```

Everything after the comment shifts by one slot. The first HTTP render is correct
and the connected render is not, so it looks like a hydration bug. Fixed by
coalescing adjacent statics; regression test in `tests/vendor/test_tree_alignment.py`.

**Dataclass contexts are deep-converted on first render.** `LiveTemplate.tree()`
uses `serialize()` (shallow — objects survive), but `LiveTemplate.render()`, which
is the *unconnected HTTP* path, uses `dataclasses.asdict()` (deep — everything
becomes dicts):

```
serialize() [connected]     -> ChangeSet
asdict()    [first render]  -> dict     # .attrs, .model, every method: gone
```

So `{{ changeset.attrs.name }}` silently renders empty on first paint and starts
working once the socket connects. Invisible on a blank create form, very visible
on a pre-populated edit form. **Not yet fixed** — it is a one-line change
(`render()` should use `serialize()` too) but it is a behaviour change for
existing views, so it wants your call.

---

## 2. What everyone else has learned

I read Ecto/Phoenix, WTForms, Django, Rails, Livewire, React Hook Form, TanStack
Form, Conform, and the JSON-Schema-driven generators. The useful findings cluster
into about ten ideas.

### 2.1 The state object and the render object are two different things

Ecto has `Ecto.Changeset` (the state) and `to_form/1` produces a
`%Phoenix.HTML.Form{}` (the thing templates touch). Django has `Form` and
`BoundField`. This looks like ceremony until you see what happens without it.

WTForms merges them, and pays for it:

> Field names that collide with the Form API silently corrupt the form, with no
> warning. A subform with a field named `data` shadows `BaseForm.data`, so
> `form.data` returns a bound field instead of the form's data.
> `FormField.__getattr__` only fires after normal lookup fails, so any subform
> field named `id`, `name`, `type`, `label`, `widget`, `default`, `flags`, `meta`,
> `process` or `validate` is unreachable.

This is not hypothetical for us: `name` is the single most common field name
there is, and pyview's template engine resolves `a.b` as *getattr first, then
getitem*, so a collision renders the framework's value with no error at all.

The fix that costs nothing: **make namespaces pure.** In the prototype,
`changeset.form` is an object with no public attributes whatsoever — every name
on it is a field, at every depth. Leaves (`FormField`) are free to carry `.value`,
`.errors`, `.label`, because nothing is ever looked up *inside* a leaf. Group-level
metadata that would otherwise need an attribute is reached through a function or
a filter instead:

```python
errors_of(form.address)              # python
{{ form.address | errors }}          # template
```

Zero reserved words, at any nesting depth.

### 2.2 Keep three representations, not two

Colander names them `pstruct` (raw strings off the wire) → `cstruct` (cleaned) →
`appstruct` (Python objects). Ecto keeps `data` (trusted starting point), `params`
(untrusted, verbatim) and `changes` (cast). Django keeps `data` and `cleaned_data`.

The reason is one sentence: **you have to redisplay `"abc"` in a number field after
it fails to parse**, so the model cannot be the source of truth. The current
`ChangeSet` gets this half right — `changes` does hold raw strings — but it has no
`data`, which turns out to matter for a second reason:

Keeping trusted `data` separate from untrusted `params` is what makes a field
whitelist possible at all. Without it there is no such thing as "this field is not
editable here", and any model with an `is_admin` on it is one crafted payload away
from a bad afternoon:

```python
cs = Changeset(Account, data=existing, fields={"email"})
cs.submit({"account": {"email": "a@b.co", "role": "user"}})
# -> role is still "admin": params cannot reach a field outside `fields`
```

Ecto's asymmetry is worth copying exactly: the whitelist filters what reaches
`changes`, but `params` keeps everything — that is what lets sidecar keys
(`_intent`, `_persistent_id`, `_unused_*`) ride along without polluting the model.

### 2.3 One nullable field solves the hardest UX problem

The research put this best:

> `changeset.action == nil` means "don't show errors yet." It is checked in
> exactly one three-line function, and it cascades to nested children
> automatically. No `touched` set, no `submitted` boolean, no per-field dirty
> tracking in the core abstraction.

The principle is GOV.UK's "reward early, punish late": a form that turns red before
you have typed anything is a bug. Everyone implements it eventually — Ecto with
`action`, Phoenix 1.0 with `used_input?`, React Hook Form with `touchedFields` and
`mode: "onTouched"`, Conform with a per-field `validated` record.

Conform's version is the best of them, and the research is explicit about why:

> Conform's per-field `validated: Record<str, bool>` display gate is a strictly
> better model than RHF's global `isSubmitted` latch: it is fine-grained,
> serializable, and gets fieldset/list semantics free via `isPathPrefix`.

RHF's global latch means one failed submit switches *every* field into
complain-on-every-keystroke mode simultaneously — the yelling-at-the-user pattern.

The prototype does both: a per-path `touched` set (fine-grained, prefix-aware, so
touching `pets.0.age` marks `pets.0` and `pets` used), plus `action` as the
global override that submit flips. Plus one refinement neither has: errors that
mean *"you haven't filled this in yet"* (pydantic's `missing`) are held back
separately from errors that mean *"what you typed is wrong"*, so tabbing through
a field without typing does not accuse you of anything.

```python
cs = Changeset(Owner)
cs.validate(payload, target="owner[name]")   # user typed "Fe"

cs.form.name.errors          # ["Name must be at least 3 characters."]
cs.form.address.city.errors  # []  — untouched, stays quiet
cs.submit(payload)
cs.form.address.city.errors  # ["City is required."]  — now it's fair game
```

### 2.4 Errors are data, not sentences

Ecto stores `{"should be at least %{count} characters", count: 3}` — the message is
a template and the `3` is still a number. Django keeps `code` and `params`. Once
you flatten to a string, translation and rewording are both off the table forever.

pydantic already hands us exactly this shape (`type`, `msg`, `ctx`), and the
current changeset throws two thirds of it away with `self.errors[loc] = error["msg"]`.
Keeping it costs nothing and buys the entire i18n story:

```python
FormError(msg="String should have at least 3 characters",
          type="string_too_short",
          ctx={"min_length": 3})

# catalog: type -> template, interpolated with ctx + the field's label
"string_too_short": ("{label} is required.",                          # min_length == 1
                     "{label} must be at least {min_length} characters.")
```

which turns `String should have at least 3 characters` into
`Name must be at least 3 characters.`, and `set_messages({...})` with a locale's
dict is the whole translation mechanism. Unknown error types fall back to
pydantic's own message, so an uncatalogued validator degrades to "slightly
technical" rather than "wrong".

Two more details worth stealing:

- **A field can have more than one error.** Ecto uses an ordered keyword list
  specifically to allow duplicates; the current `errors: dict[str, str]` caps it
  at one and loses ordering.
- **Errored fields must not vanish from the output.** Django deletes them from
  `cleaned_data`, which is why every `Form.clean()` in the wild is littered with
  `.get()` guards.

### 2.5 Validate everything, every time; `_target` decides only what to *show*

> LiveView's client serializes the ENTIRE form on every `phx-change`; `_target`
> only names the input that fired. Ecto's model — rebuild the whole changeset from
> `(data, params)` on every event, then filter the display — is simpler, avoids
> stale cross-field validation (a `password_confirmation` check can't work
> per-field), and is what the client protocol actually assumes.

This directly contradicts what the current `apply()` does, and it is the single
highest-leverage change. Rebuild-and-filter is *less* code, not more.

### 2.6 Nesting is a naming convention, and nothing else

No framework in the survey does schema-driven decoding. Rails, Phoenix, PHP and
`qs` all agree on bracket notation, and everything else follows from parsing it:

| wire | decoded |
|---|---|
| `owner[name]=Fern` | `{"owner": {"name": "Fern"}}` |
| `owner[tags][]=a&owner[tags][]=b` | `{"owner": {"tags": ["a", "b"]}}` |
| `owner[pets][0][name]=Rex` | `{"owner": {"pets": {"0": {"name": "Rex"}}}}` |

That last row is the one people get wrong. A numeric subscript decodes to a **map
keyed by digit strings, not a list** — deliberately, in both Plug and Rails. It is
what lets you delete row 1 of 0/1/2 and leave `{"0", "2"}` behind, without
renumbering the surviving inputs.

Django chose positional arrays instead, and the research is blunt about the cost:

> Positional array naming forces client-side renumbering. `lines-0-sku` means
> removing a row requires regex-rewriting `name`/`id`/`for` on every descendant of
> every remaining row.

For a morphdom-based client this is worse than tedious: rewriting the names of
surviving rows makes the diff enormous and makes inputs inherit the DOM state
(focus, selection, IME composition) of whatever used to live at that index.

`_target` needs one extra step that is easy to miss. The client sends it as the
input's `name` attribute — a single string, `"owner[pets][0][age]"` — and Phoenix
decodes it into a path list before handing it to the view. And then a subtle one:

> **paths must be canonicalised.** The browser's path segments are all strings;
> pydantic reports list indexes as *integers* (`("pets", 0, "age")`). If the two
> representations are not normalised to one, touched-tracking silently misses on
> every list row and errors never render next to their input.

I hit that one in the spike before I hit it in the design. Everything in the
prototype is a `tuple[str, ...]`.

### 2.7 The intent protocol beats a click handler

Rails mints a client-side `child_index` (a timestamp) and clones a template row.
Django clones `empty_form` and renumbers. Phoenix uses `sort_param`/`drop_param`
hidden inputs. Conform uses a reserved `__intent__` input carrying an encoded
instruction, and the research flags it as the standout:

> Conform's intent protocol makes dynamic lists work identically with and without
> JavaScript. It is the only design in the survey that is natively server-shaped,
> and it is directly portable to LiveView.

It is portable because it is just a submit button:

```html
<button type="submit" formnovalidate name="_intent" value="add:pets">Add a pet</button>
<button type="submit" formnovalidate name="_intent" value="drop:pets:0">Remove</button>
```

The reason this is better than `phx-click` is not elegance, it is a data-loss bug.
A `phx-click` payload carries only the button's own `phx-value-*`; the form's
contents are not in it. So "add a row" relies on a `phx-change` having already
synced — and with `phx-debounce` set, anything typed inside the debounce window is
silently discarded. As a submit button, the browser sends everything:

```
add #1      : owner[pets][0][name]=""
add #2      : owner[pets][0][name]="", owner[pets][1][name]=""
type+add    : owner[pets][0][name]="Rex", owner[pets][1][name]="", owner[pets][2][name]=""
drop row 0  : owner[pets][1][name]="", owner[pets][2][name]=""
```

(verified in a browser; note the survivors keep their indexes)

Two HTML details fall out, and both bit me:

- **Intent buttons need `formnovalidate`.** The model emits `required`, so the
  browser refuses to submit an incomplete form and the click does nothing at all —
  no event, no error, no clue.
- **The form itself needs `novalidate`.** Same cause: with server-authoritative
  validation, the browser must not be the one to block a submit, or your server
  never sees it and the user gets native bubbles instead of your accessible,
  translatable, consistently-placed errors. GOV.UK and Conform both land here.

The constraint attributes are still worth emitting — screen readers announce
`required`, mobile keyboards follow `type`, and `:user-invalid` styling works —
they just must not be load-bearing.

### 2.8 Inference gets you most of the way, and `Annotated` gets the rest

The JSON-Schema generators (react-jsonschema-form, JSONForms) keep a *second*
document — a `uiSchema` — beside the validation schema. It is the most flexible
design and it is where those libraries lose people: two files, one drifting.

pydantic already carries almost everything needed:

```
field            widget           req   attrs
email            email            True  {'maxlength': 200, 'required': True, 'autocomplete': 'email'}
display_name     text             True  {'minlength': 3, 'maxlength': 20, 'required': True}
password         password         True  {'minlength': 12, 'required': True}
bio              textarea         False {'placeholder': 'Tell us about you', 'rows': 4}
plan             select           False {'choices': ['free', 'pro', 'team']}
seats            number           False {'min': 1, 'max': 500, 'step': 1}
starts_on        date             False {}
accept_terms     checkbox         False {}
```

Widget, label, required-ness, min/max, maxlength, step and the option list all come
from the plain model. `Optional[T]` correctly means not-required. The constraints
double as HTML validation attributes, so there is nothing to restate.

What *cannot* be inferred: which `str` is a textarea, human-readable choice labels,
placeholder and help text, grouping, and field order intent. Those go in
`Annotated[T, ui(...)]` on the same model — pydantic carries unknown metadata
around and ignores it, so validation is untouched and there is no second document
to drift:

```python
class Signup(BaseModel):
    email: Annotated[str, ui(widget="email", autocomplete="email")]
    bio: Annotated[Optional[str], ui(widget="textarea", rows=4)] = None
    seats: int = Field(default=1, ge=1, le=500)
```

**Discriminated unions are the conditional-nesting story.** `form.contact` resolves
to whichever variant the discriminator currently selects, so flipping the select
swaps the sub-form with no wiring in the view:

```html
{{ form.contact.kind | input }}          {# a select over every variant's tag #}
{% if form.contact.kind.value == "phone" %}
  {{ form.contact.number | input }}
{% else %}
  {{ form.contact.address | input }}
{% endif %}
```

Untagged unions must be rejected outright, and loudly, at construction: pydantic
tries every variant and reports the errors from all of them, so an email input
ends up displaying "not a valid phone number". The research found the same class
of failure across the JS libraries —

> Discriminated unions / conditionally-rendered fields are broken or awkward
> everywhere.

— so this is worth being strict about rather than clever about.

### 2.9 The escape-hatch ladder is the whole ballgame

What kills a form library is not the first five minutes, it is month three, when
the design system wants markup the library does not emit. The libraries that
survive let you descend one rung without falling off a cliff:

```
{{ signup | render_form }}                     everything, zero decisions
{{ signup.form.email | input }}                one field, wrapper included
{{ signup.form.email | input({"class": …}) }}  same, overridden
{{ signup.form.email | control }}              bare <input>, you write the wrapper
<input name="{{ signup.form.email.name }}"     nothing of ours at all,
       value="{{ signup.form.email.value }}">  still correctly bound
```

The library owns *correctness* — name generation, value round-tripping, error
placement, and the a11y wiring that is tedious to get right by hand. It does not
own *appearance*: there is not one style class anywhere in `render.py`. They live
in a `Theme` you replace. Hardcoded classes are the trap that crispy-forms,
simple_form and rjsf all had to grow plugin systems to escape.

What the bottom rung emits by default, and why:

```html
<div phx-feedback-for="owner[address][zip]">
  <label for="owner_address_zip">ZIP</label>
  <input id="owner_address_zip" name="owner[address][zip]" type="text"
         aria-invalid="true" aria-describedby="owner_address_zip_error"
         pattern="^\d{5}$" required value="9721" />
  <p id="owner_address_zip_error" role="alert">ZIP is not in the expected format.</p>
</div>
```

`aria-invalid` is the machine-readable half of "this is wrong" — the red border is
only the half sighted users get. `aria-describedby` is what makes a screen reader
read the error when the field takes focus. `role="alert"` announces errors that
arrive after a server round trip. And the `id` is derived from the same path as
the `name`, so `<label for>` cannot drift.

One thing to note about the checkbox, because it is not optional:

```html
<input type="hidden" name="owner[subscribe]" value="false" />
<input type="checkbox" name="owner[subscribe]" value="true" checked />
```

An unchecked box sends *nothing*. Without a false value ahead of it there is no way
to distinguish "unchecked" from "not on this form", and the box can never be
cleared. (This is also the bug behind WTForms' documented inability to put a
`BooleanField` inside a `FieldList`.)

### 2.10 Runtime rendering vs. generating code you own

This is the one genuine fork, and Phoenix chose the opposite of what I built:

> No field registry means no automatic rendering. `to_form(model)` gives you a form
> object but you still hand-write every `<.input field={@form[:x]} />`. There is
> deliberately no `<.form_for_all_fields>`; the *generator* writes them.

`mix phx.gen.live` emits `core_components.ex` **into your project**. You own it, you
edit it, the framework never fights you. shadcn/ui made the same bet. Django went
the other way with runtime template-based rendering, and the research measured the
bill: **10.6ms to render a 21-field form**, per render, which for a diff-per-keystroke
protocol is not a rounding error.

I lean toward both, with the runtime path in Python (not templates, so it is fast)
as the scaffold, and a `pv gen form` that ejects a template you own once you have
opinions. The runtime path is what makes the 3-line version real; the generator is
what stops the library from being a wall at month three. But I would want your read
— see the open questions.

---

## 3. What's in the prototype

`pyview/forms/` — about 900 lines, 40 tests, not exported from `pyview` yet.

| file | what it does |
|---|---|
| `params.py` | bracket-notation decoding with `Plug.Conn.Query` semantics; `_target` → path; an adapter that accepts today's flat `parse_qs` payloads unchanged |
| `paths.py` | canonical string paths; get/put/delete; digit-map → list |
| `schema.py` | pydantic model → `FieldSpec`s; `Annotated[T, ui(...)]`; error-`loc` → form path; the pre-validation pass |
| `form.py` | `Changeset` (state) and `FormView`/`FormField`/`FieldList` (render) |
| `render.py` | the ladder, `Theme`, a11y wiring, template filters |
| `messages.py` | error type + ctx → a sentence; replaceable catalog |

Three things in there took more thought than expected and are worth calling out:

**Empty strings are not values.** HTML cannot express null: a cleared date input
sends `""`, and `Optional[date]` rejects it — but the user meant "nothing". So the
pre-validation pass drops `""` for anything that is not a plain `str`. Ecto has
the identical mechanism (`:empty_values`), which is a good sign it is not a hack.

**Absent nested branches produce a useless error.** If `address` is missing
entirely, pydantic reports one error at `("address",)` instead of leaf errors at
`("address", "city")` — and the template has nowhere sensible to render it. The
pre-validation pass materialises empty dicts for nested models so error paths are
always leaf-level.

**Union variant tags pollute error paths.** pydantic reports
`("contact", "email", "address")` but the input is named `owner[contact][address]`.
Stripping it needs to be schema-aware, not a heuristic — a plain union reports the
*class name* (`"Email"`), a discriminated one reports the *tag* (`"email"`), and a
field could legitimately be named either.

### Verified in a browser, not just in tests

The demo at `/forms` was driven with Playwright:

- typing an invalid name shows an error on that field and nothing else
- flipping the contact select swaps the sub-form's fields
- add/remove rows preserve everything typed, and survivors keep their indexes
- an invalid nested list row shows its error on that row's input, with the bad
  value still in the box
- submit reveals every error at once, humanised

---

## 4. Open questions

Places where I could argue either side, and where your call would change what I'd
build next.

**1. Fix the `asdict` deep-conversion, or work around it?** Making
`LiveTemplate.render()` use `serialize()` (like `tree()` already does) fixes a real
bug — objects in a dataclass context currently disappear on first paint — but it
changes what existing templates see on the HTTP render. My instinct is to fix it,
since the two paths disagreeing is worse than either behaviour.

**2. Runtime rendering, generated code, or both?** Section 2.10. Phoenix
deliberately has no auto-render. Auto-render is what makes "here's my model, do the
rest" real, and it is also the thing people outgrow. If the answer is "both", the
generator is the more important half and should probably come first.

**3. Should `Changeset` be pydantic-only?** Phoenix's `FormData` protocol is a
4-callback seam, and only two are needed for flat forms; `dict`-backed and
dataclass-backed forms then light up for free. It is maybe 80 lines to add now and
awkward to retrofit. But it is also speculative generality if pydantic is the
answer 95% of the time — pyview already depends on it.

**4. How much should the library own the `<form>` tag?** Right now the user writes
`<form phx-change=… phx-submit=… novalidate>` by hand, and `novalidate` is easy to
forget with a consequence (submits blocked, no error) that is hard to diagnose. A
`{{ signup | form_tag }}` could emit it correctly — at the cost of another thing
between you and your markup.

**5. Client-side error gating.** pyview bundles LiveView JS **0.20.17**, which still
supports `phx-feedback-for` — so the client can hide errors for inputs the user has
not touched, complementing the server's `touched` set. LiveView 1.x removed it in
favour of the client sending `_unused_*` sentinel keys, which is a better design
(the server learns what the browser knows about focus). Worth deciding whether the
JS client gets upgraded, because it changes which mechanism is primary.

**6. Cross-field validators fire late.** pydantic's `mode="after"` validators do not
run while *any* field error exists, so "passwords do not match" stays hidden until
everything else is clean:

```python
Reg.model_validate({"email": "a", "password": "short", "confirm": "other"})
# -> email too short, password too short.  No "passwords do not match".
```

Ecto does not have this problem, because its validations are a pipeline that all
run. Options: document it, offer a `@form_check` hook that runs against raw params
regardless of field validity, or both.

---

## 5. Things I'd deliberately avoid

Collected from the failure modes in the research, so they don't get re-invented:

- **Positional renumbering of list rows** (Django formsets) — huge diffs, DOM state
  bleeds between rows.
- **Matching nested rows by primary key** (Rails `accepts_nested_attributes_for`,
  Ecto `cast_assoc`) — every row must round-trip a hidden `id`, a stale tab raises
  `RecordNotFound` instead of showing a validation error, and Ecto's default
  `on_replace: :raise` turns an ordinary list edit into a 20-line crash.
- **Un-indexed nested errors** (Rails' default) — five bad rows produce five errors
  all attributed to `addresses.street`, renderable nowhere in particular.
- **A global "submitted" latch** (RHF) — one failed submit makes every field
  complain on every keystroke.
- **Synthetic row ids merged into row data** (RHF `useFieldArray` injects `id`,
  clobbering real primary keys).
- **Deleting errored fields from the output** (Django `cleaned_data`).
- **A second UI schema** (rjsf, JSONForms) — it drifts.
- **Typed field paths** — RHF's `FieldPath` recursion hits "type instantiation is
  excessively deep" on real models, and Python's type system is in a weaker
  position than TypeScript's here. `form.email` is dynamic and will not autocomplete;
  I think that is the right trade, but it is a trade.
