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
on a pre-populated edit form.

`asdict` only recurses into *dataclasses*, so what gets destroyed is precisely the
things declared as dataclasses — which today's `ChangeSet` is:

```
old ChangeSet (a dataclass)   -> dict        # .attrs, .model, every method: gone
new Changeset (a plain class) -> Changeset   # deep-copied, but intact
```

The prototype sidesteps it by not being a dataclass, which is a workaround, not a
fix. **Not yet fixed** — it is a one-line change (`render()` should use
`serialize()` too) but it is a behaviour change for existing views, so it wants
your call.

---

## 2. What everyone else has learned

I read Ecto/Phoenix, WTForms, Django, Rails, Livewire, React Hook Form, TanStack
Form, Conform, the JSON-Schema-driven generators, the Python pydantic-form
ecosystem (colander/deform especially), the formlets lineage (digestive-functors,
Yesod, Elm), and the accessibility design systems. The useful findings cluster into
about a dozen ideas.

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
{{ signup | render_form }}                          everything, zero decisions
{{ signup | render_form({"exclude": ["plan"]}) }}   everything but the ones I'll do myself
{{ signup.form.email | input }}                     one field, wrapper included
{{ signup.form.email | input({"class": …}) }}       same, overridden
{{ signup.form.email | control }}                   bare <input>, you write the wrapper
<input name="{{ signup.form.email.name }}"          nothing of ours at all,
       value="{{ signup.form.email.value }}">       still correctly bound
```

That second rung is the one people actually reach for and the one most libraries
skip. uniforms has it (`AutoFields` with omissions) and it is the difference
between "one field needs custom markup" and "so I hand-wrote all twenty".

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

### 2.11 A field error is not an announcement

The accessibility research changed my mind about something I had already built.
I had `role="alert"` on every field error, reasoning that an error appearing after
a server round trip should be announced. That is wrong for *this* architecture:

> In a keystroke-validating, diff-patched form it re-announces on every patch, and
> competing assertive regions cancel each other.

GOV.UK's model is the one that fits: field errors are **silent**, reached through
`aria-describedby` when the control takes focus; a single **error summary** at the
top of the form is the one thing that announces. So the summary is now a component,
with GOV.UK's rules baked in — only after a submit attempt, a fixed heading, one
link per error pointing at the input's id, and link text *byte-identical* to the
inline message (otherwise the user can't tell they're the same problem):

```html
{{ owner | error_summary }}
```
```
There is a problem
  Name must be at least 3 characters.   -> #owner_name
  ZIP is not in the expected format.    -> #owner_address_zip
  Email address is not in the expected format. -> #owner_contact_address
```

Related: `aria-describedby` is now a computed property on the field
(`f.describedby`, hint before error) rather than something the renderer assembles
privately — because on the bottom rung of the ladder you are writing that attribute
by hand, and pointing it at an id that isn't on the page is worse than omitting it.

### 2.12 Silent no-ops are the real DX problem

The DX research measured what my own prototype did when held wrong. Seven ways,
every one of them silent or cryptic:

| you write | you used to get |
|---|---|
| `fields=["emial"]` | that field frozen forever, no signal |
| `add_error("emial", …)` | an error stored where nothing renders it |
| `add_row("email")` on a scalar | `{"0": {}}` written over the value |
| a payload not under the form's name | `validate()` a permanent no-op |
| `Changeset(Signup(...))` | `TypeError: unhashable type: 'Signup'` |
| `Changeset(SomeDataclass)` | `AttributeError: ... has no attribute 'model_fields'` |

Now each raises `FormUsageError` — deliberately a different type from `FormError`,
because one is aimed at a developer and the other at whoever is filling in the
form, and conflating those two audiences is how libraries end up showing stack
traces to users:

```
FormUsageError: fields=: `Signup` has no field `emial` --
                there is a field with a similar name: `email`

FormUsageError: this changeset is named `signup`, so it expects its inputs to be
                named `signup[...]`, but the payload only contains `email`.
                Either render the inputs from this changeset
                (`signup.form.<field> | input`), or construct it with the name
                your inputs already use: Changeset(Signup, name="...")
```

`tests/forms/test_misuse.py` is the corpus, which is the point: it makes "good
error messages" a property CI enforces rather than an aspiration. Elm keeps an
error-message catalog for the same reason.

One more DX finding worth acting on immediately: the demo used to open with
`register_filters()` and `set_theme(TAILWIND)` before a single field was declared.
A form library whose first two lines are setup has spent its budget before it
starts. Filters now register on import.

## 3. What's in the prototype

`pyview/forms/` — about 2,000 lines, 60 tests, not exported from `pyview` yet.

| file | what it does |
|---|---|
| `params.py` | bracket-notation decoding with `Plug.Conn.Query` semantics; `_target` → path; an adapter that accepts today's flat `parse_qs` payloads unchanged |
| `paths.py` | canonical string paths; get/put/delete; digit-map → list |
| `schema.py` | pydantic model → `FieldSpec`s; `Annotated[T, ui(...)]`; error-`loc` → form path; the pre-validation pass |
| `form.py` | `Changeset` (state) and `FormView`/`FormField`/`FieldList` (render) |
| `render.py` | the ladder, `Theme`, a11y wiring, template filters |
| `messages.py` | error type + ctx → a sentence; replaceable catalog |

Six things in there took more thought than expected and are worth calling out.
The last three were bugs *in the prototype* that the research turned up after I'd
written it, which is a decent argument for having done the reading:

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

**Stable row keys and positional indexes disagree.** This one was a real bug, and
it is the kind that hides: rows are keyed by a *stable* index on the wire
(`pets[1]`, `pets[2]`), but the pre-validation pass compacts them into a list, so
pydantic reports `("pets", 0, "name")` for what the DOM calls `pets[1]`. Delete any
row but the last and every subsequent error is filed against the wrong input,
where it renders nowhere at all:

```
raw params : {'1': {'name': 'x'}, '2': {'name': 'also ok'}}
error paths: [('pets', '0', 'name')]        # <- nothing is named pets[0] any more
  row 1: owner[pets][1][name]   errors=[]   # the invalid row shows nothing
  row 2: owner[pets][2][name]   errors=[]
```

The fix is to walk the raw params alongside the model when translating an error
location, so a positional index resolves back to the key the row is rendered under.
It is the direct cost of choosing stable keys over renumbering — worth paying, but
it needs to be paid deliberately.

**Aliases move the wire name.** pydantic reports error locations by
*validation alias* and validates by alias, so a field declared
`email_address: str = Field(alias="email")` errors at `("email",)`. Name the input
after the Python attribute and params, errors and markup all disagree — silently.
The alias now wins everywhere on the wire, while the Python attribute stays how you
look the field up (`form.email_address` renders `name="contact[email]"`). Alias
forms that do not reduce to a single name — `AliasChoices`, `AliasPath` — are
rejected at construction, because a form has exactly one input per field and
quietly picking one of several would mis-key every error on it.

**"You haven't chosen yet" is not an error.** A blank discriminated union produces
`union_tag_not_found` — *"Unable to extract tag using discriminator 'kind'"* — which
by the rules above belongs with the absence errors that are held back until submit,
not with the ones that turn the form red on the first keystroke.

**A rejected submit must stay rejected.** `submit()` set `action = "submit"` to
reveal everything; the next keystroke called `validate()`, set it back, and quietly
un-revealed every error the user had not personally touched. The form appeared to
forget it had been rejected. Fixed with a sticky `submitted` latch — the same shape
as React Hook Form's `isSubmitted`, though RHF makes it *global* (one failed submit
puts every field into complain-on-keystroke mode), which is the part not to copy.

**A dropped row's index must never come back.** `add_row` computed `max(keys) + 1`,
so adding 0/1/2, dropping 2, and adding again produced another `2` — and under
morphdom the new row inherits the dropped row's DOM state and aria wiring. Indexes
are now monotonic per field: `0, 1, 3`.

**`{"class": …}` has to merge.** It replaced the theme's classes, so adding one
utility class to one field silently turned off its error styling — a cliff in the
middle of a ladder that is supposed to be steps.

**HTML bounds are inclusive; `gt`/`lt` are not.** `Field(gt=0, lt=10)` emitted
`min="0" max="10"`, so the browser accepted values the server would reject. On an
integer the neighbouring value is exact, so it now narrows to `min="1" max="9"`.
On a float it is left alone and the server stays the authority — the safe direction
to be wrong in. (simple_form does exactly this, and it is the kind of detail you
only find by reading someone else's fifteen years of bug reports.)

**Error records need cleaning at ingest.** pydantic prefixes anything raised from a
validator with `"Value error, "`, which is framework vocabulary leaking into
user-facing copy, and it puts the live exception object in `ctx` — unserializable,
and it pins a traceback in the socket's state for as long as the form is open.

### Verified in a browser, not just in tests

The demo at `/forms` was driven with Playwright:

- typing an invalid name shows an error on that field and nothing else
- flipping the contact select swaps the sub-form's fields
- add/remove rows preserve everything typed, and survivors keep their indexes
- an invalid nested list row shows its error on that row's input, with the bad
  value still in the box — including after deleting an earlier row, which is the
  case that was broken
- submit reveals every error at once, humanised
- the server-rendered HTML and the connected DOM are byte-identical on load, which
  is the check that would have caught the statics/dynamics bug in §1

Some of it only shows up in a browser. `type="number"` inferred from `age: int`
means Chromium physically refuses to accept `"abc"` — the inference is doing
client-side validation for free. And the two `novalidate` findings in §2.7 are
invisible to a test suite: the symptom is a button that does nothing at all.

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
- **A string expression language for conditions** — Formily compiles `{{ aa > bb }}`
  with `new Function`; ngx-formly has string `expressionProperties`. Both trade
  typeability, testability and safety for authoring brevity we do not need. A
  Python callable is right here.
- **Expressing "hide this field" by mutating the data contract** — JSON Schema
  `if/then/else` conflates validity with visibility. They are different questions
  (and layout is a third), and the schema-form pain people report mostly traces
  back to that conflation.
- **`experimental_allow_partial`** — it looks like the answer to "validate a
  half-filled form" and is not: it does not suppress `missing`, it only truncates a
  trailing incomplete element of a sequence. It is a streaming-JSON feature.
  Validate everything and filter the display by error *type* instead.

## 6. What I read

Twelve deep-dives and three cross-cutting syntheses, all against primary sources —
docs, source, changelogs and issue threads rather than blog summaries:

| | |
|---|---|
| Ecto.Changeset | the `data`/`params`/`changes` split, `action`, `cast_assoc`, `sort_param`/`drop_param` |
| Phoenix LiveView forms | `FormData`, `to_form`, `inputs_for`, `used_input?`, the generated `core_components.ex` |
| WTForms | the reserved-word trap, `FieldList` limits, the widget/validator seams |
| Django forms | `BoundField`, the clean pipeline, formsets, the renderer/template-pack layer |
| Rails + Livewire | `accepts_nested_attributes_for`, strong params, simple_form; `wire:model`, Form Objects |
| RHF / TanStack / Formik / Conform | validation-timing state machines, field arrays, the intent protocol |
| Schema-driven UI | rjsf, JSONForms, Formily, uniforms, AutoForm — and why they get a bad name |
| Python pydantic-forms | colander/deform's pstruct/cstruct/appstruct, FastUI, Ludic, pydantic v2 mechanics |
| Formlets | Cooper/Lindley/Wadler, digestive-functors, Yesod, Elm — composability and name scoping |
| Param encoding | Plug/Rack/PHP/qs semantics, `_persistent_id`, DoS limits, the checkbox trick |
| Validation UX & a11y | GOV.UK, USWDS, NN/g, WAI-ARIA APG, WHATWG constraint validation |
| Developer UX | FastAPI, pydantic, Django admin, phx.gen, shadcn, rustc's diagnostics guide |

Two factual corrections worth recording, because a secondary source would have led
me wrong on both:

- **`phx-feedback-for` vs `_unused_`.** LiveView 1.x removed `phx-feedback-for` in
  favour of the client sending `_unused_<field>` sentinel params, consumed by
  `used_input?/1`. pyview pins `phoenix_live_view ^0.20.17`, and I checked the
  bundled `app.js` directly: it has `PHX_FEEDBACK_FOR` and zero occurrences of
  `_unused_`. So the server-side touched set is not a stopgap for something the
  client already sends — today it is the only mechanism available.
- **`_target`'s location.** On the pinned client it rides inside the urlencoded
  body. LiveView >= 1.0.6 moved it to `payload["meta"]`. Whoever upgrades the JS
  client has to change the decode site too.

## 7. Next, if this direction is right

Roughly in order of value:

0. **Decide the `<form>` tag question and the timing policy**, since both are
   currently the user's problem and both fail quietly (§4).
1. **A ranked widget-selection registry**, JSONForms-style, instead of a flat
   `widget: str` dispatch. Today, "textarea whenever `max_length > 500`" or "this
   type always renders with my component" means forking `render.py`. A list of
   `(tester, renderer)` pairs where the highest-scoring tester wins makes widget
   *choice* extensible, not just widget implementations.
2. **A `pv gen form` generator** that ejects the renderer into your project, per
   §2.10. This is the answer to "I have outgrown the library" that does not involve
   leaving it.
3. **Visibility as its own layer** — a Python predicate over the current values,
   kept separate from validity (pydantic) and layout (your template).
4. **Async/server-side errors as a first-class step.** `add_error()` exists, but
   the uniqueness-check shape — debounce, check, merge into the same error set,
   render in the same place — deserves a worked example.
5. **Multi-input widgets.** Colander's pstruct/cstruct split exists so a date widget
   can take three inputs and produce one value. The prototype collapses that step,
   which is fine until someone wants a split date or a currency field.
6. **Normalize `choices` to `{value, label, disabled}`** rather than tuples, so no
   widget ever re-derives them.
