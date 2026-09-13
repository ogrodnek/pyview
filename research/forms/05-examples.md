# Part 5 — Worked examples against the proposed API

These are the examples the design must make easy. The data/validation halves run in the spike (Part 7); the rendering helpers are specified in Part 4 and every Ibis line uses only syntax that parses after the phase-2 `splitc` patch (dict and list literals as filter arguments, plus the `{% input %}` tag).

## 5.1 Edit an existing record (initial values, partial template, save, reset)

```python
class Plant(BaseModel):
    name: str = Field(min_length=3, max_length=20, title="Plant name")
    watering_schedule_days: int = Field(ge=1, le=30, title="Watering schedule (days)")
    note: str | None = None
    last_watered: datetime = Field(default_factory=datetime.now)

class PlantEditView(BaseEventHandler, LiveView):
    async def handle_params(self, socket, plant_id: str):
        plant = await plants.get(plant_id)
        socket.context = {"plant": plant, "form": Form(Plant, data=plant)}

    @event("validate")
    async def validate(self, socket, params: Params):
        socket.context["form"].validate(params)

    @event("save")
    async def save(self, socket, params: Params):
        form = socket.context["form"].submit(params)
        if form.valid:
            await plants.update(socket.context["plant"].id, form.model)
            socket.put_flash("info", "Saved")
            socket.context["form"] = Form(Plant, data=form.model)     # reset to the saved state
```

```html
<form id="plant" phx-change="validate" phx-submit="save" phx-auto-recover="validate">
  {{ form.name | form_field }}
  {{ form.watering_schedule_days | form_field }}
  {{ form.note | form_field }}
  <button type="submit" phx-disable-with="Saving…">Save</button>
</form>
```

`last_watered` is not rendered, so it is absent from every payload and keeps its initial value (Ecto cast semantics, verified). Clearing `note` submits `""` and yields `None` — a real change. The schedule input renders `type="number" min="1" max="30" step="1" required`.

## 5.2 Addresses: add, remove, reorder (list of models)

```python
class Address(BaseModel):
    street: str = Field(min_length=3)
    city: str
    primary: bool = False

class Profile(BaseModel):
    name: str = Field(min_length=3)
    addresses: list[Address] = Field(min_length=1, max_length=5)
```

```html
<form id="profile" phx-change="validate" phx-submit="save">
  {{ form.name | form_field }}
  <fieldset>
    <legend>Addresses</legend>
    {% for row in form.addresses %}
      {{ row | form_row_start }}                    {# <fieldset id="profile_addresses_k7f3"> + hidden _key + legend "Address 1" #}
        {{ row.street | form_field }} {{ row.city | form_field }} {{ row.primary | form_field }}
        {{ row | form_intent("move:up", "↑") }} {{ row | form_intent("move:down", "↓") }} {{ row | form_intent("remove", "Remove") }}
      {{ row | form_row_end }}
    {% endfor %}
    {{ form.addresses | form_errors }}              {# "Add at least 1 item to Addresses" / "Addresses can have at most 5 items" #}
    {{ form.addresses | form_intent("add", "Add address") }}
  </fieldset>
  <button type="submit">Save</button>
</form>
```

or, at level 0, `{{ form.addresses | form_field }}` renders that whole fieldset. The handlers are the same two methods as in 5.1: intents arrive inside ordinary `validate` events (`profile[addresses][_intent]=remove:k7f3` is the submitter pair the client injects when the named button dispatches `change`), `Params.decode` turns them into `params.intents`, and `Form.validate()` applies them before validating and records them in `form.applied_intents`. Row DOM ids use the key (`profile_addresses_k7f3`), so removing the first row does not re-id the others; names are renumbered (`profile[addresses][0][street]`), which the client tolerates because it never value-patches the focused input. A freshly added row shows no errors until the user types in it (verified).

## 5.3 Personal or business account (discriminated union, variant-named inputs)

```python
class Personal(BaseModel):
    kind: Literal["personal"] = "personal"
    nickname: str = Field(min_length=2)

class Business(BaseModel):
    kind: Literal["business"] = "business"
    company: str = Field(min_length=2, title="Company name")
    vat_id: str | None = Field(default=None, pattern=r"^[A-Z]{2}\d{8,12}$")

class Signup(BaseModel):
    email: EmailStr
    account: Annotated[Personal | Business, Field(discriminator="kind")] = Personal()
```

```html
{{ form.email | form_field }}
{% input form.account.kind widget="radio" %}              {# name="signup[account][kind]", options from the union tags #}
{% if form.account.kind.typed == "business" %}
  {{ form.account.business.company | form_field }}       {# name="signup[account][business][company]" #}
  {{ form.account.business.vat_id | form_field }}
{% else %}
  {{ form.account.personal.nickname | form_field }}
{% endif %}
```

`{{ form.account | form_field }}` does the branching itself. Changing the radio is a normal `phx-change`; the payload still contains the old variant's inputs (they are in the DOM at that moment), but they arrive under their own tag, so nothing is polluted and switching back restores what was typed (verified with that ordering). Variant errors map 1:1: pydantic's `('account', 'business', 'company')` *is* the input name.

## 5.4 Country → state (dependent select)

```python
class Shipping(BaseModel):
    country: Annotated[str, Input(options=COUNTRIES, autocomplete="country")]
    state: Annotated[str, Input(options=lambda form: STATES.get(form.country.typed, []))]
```

```python
@event("validate")
async def validate(self, socket, params: Params):
    form = socket.context["form"].validate(params)
    if form.target == ("country",):
        form.params["state"] = ""                    # clear the stale dependent value
```

The `options` callable runs at render time with the current form; `form.target` is the decoded `_target` path (`None` on submit).

## 5.5 Three-step wizard — one model per step (recommended), or one model with step gating

```python
class Step1(BaseModel):
    name: str = Field(min_length=2); email: EmailStr
class Step2(BaseModel):
    addresses: list[Address] = Field(min_length=1)
class Step3(BaseModel):
    plan: Literal["free", "pro"] = "free"; accept_terms: bool
class Onboarding(Step1, Step2, Step3): ...

STEPS = [Step1, Step2, Step3]

class OnboardingView(BaseEventHandler, LiveView):
    async def mount(self, socket, session):
        socket.context = {"step": 0, "done": {}, "form": Form(Step1, as_="onboarding")}

    @event("validate")
    async def validate(self, socket, params: Params):
        socket.context["form"].validate(params)

    @event("next")
    async def next(self, socket, params: Params):
        ctx = socket.context
        form = ctx["form"].submit(params)
        if form.valid:
            ctx["done"].update(form.model.model_dump())
            ctx["step"] += 1
            if ctx["step"] < len(STEPS):
                ctx["form"] = Form(STEPS[ctx["step"]], as_="onboarding")
            else:
                await onboard(Onboarding(**ctx["done"]))

    @event("back")
    async def back(self, socket):
        ctx = socket.context
        ctx["step"] -= 1
        ctx["form"] = Form(STEPS[ctx["step"]], data=STEPS[ctx["step"]].model_validate(ctx["done"]), as_="onboarding")
```

```html
<form id="onboarding" phx-change="validate" phx-submit="next">
  {{ form | render_form }}
  {% if step > 0 %}<button type="button" phx-click="back">Back</button>{% endif %}
  <button type="submit">{% if step == 2 %}Finish{% else %}Next{% endif %}</button>
</form>
```

No new API: each step is an ordinary form; Back re-creates the previous step's form from the saved data. The single-model alternative (`form.step(paths)` + `{{ form | form_hidden(exclude=paths) }}`) is specified in 4.8 for wizards where every step shares one model.

## 5.6 Bring your own HTML (level 3) with a Tailwind theme (level 4)

```python
TAILWIND = Theme(
    field="mb-4", label="block text-sm font-medium text-gray-700 mb-1",
    input="w-full rounded-md border-gray-300 shadow-sm focus:ring-blue-500",
    input_error="border-red-300 focus:ring-red-500", error="mt-1 text-sm text-red-600", hint="text-xs text-gray-500")
forms.configure(theme=TAILWIND)
```

```html
<div class="grid grid-cols-2 gap-4">
  <div>
    <label for="{{ form.name.html.id }}" class="label">{{ form.name.html.label }}</label>
    <input name="{{ form.name.html.name }}" id="{{ form.name.html.id }}" value="{{ form.name.html.value }}"
           {{ form.name.html.attrs }} class="input {% if form.name.html.errors %}input-error{% endif %}">
    {{ form.name | form_errors }}
  </div>
  {{ form.email | form_field }}     {# mixing levels in one form is fine #}
</div>
```

`form.name.html.attrs` renders `required minlength="2" maxlength="40" phx-debounce="blur" aria-describedby="profile_name-hint profile_name-error" aria-invalid="true"` (the aria parts only when a hint / a visible error exists, verified).

## 5.7 Custom widget and a server-side uniqueness check

```python
def color_picker(field: Field, theme: Theme, **attrs) -> Markup:
    h = field.html
    return Markup(f'<input type="color" name="{h.name}" id="{h.id}" value="{h.value or "#000000"}" {h.attrs}>')

forms.configure(widgets={"color": color_picker})

class Settings(BaseModel):
    accent: Annotated[str, Input(widget="color")] = "#336699"

@event("save")
async def save(self, socket, params: Params):
    form = socket.context["form"].submit(params)
    if form.valid and await users.exists(email=form.model.email):
        form.add_error("email", "unique", "That email is already registered")   # shown until the next submit
    if form.valid:
        ...
```

## 5.8 Testing without a socket

```python
def test_signup_business_requires_company():
    form = Form(Signup).submit("signup%5Bemail%5D=a%40b.co&signup%5Baccount%5D%5Bkind%5D=business&signup%5Baccount%5D%5Bbusiness%5D%5Bcompany%5D=")
    assert not form.valid
    assert form.account.business.company.html.errors == ["Company name is required"]

def test_add_address_intent():
    form = Form(Profile)
    form.validate(wire(form, {"name": "Larry"}, target="profile[addresses][_intent]", submitter=("profile[addresses][_intent]", "add")))
    assert len(list(form.addresses)) == 1 and form.applied_intents[0].op == "add"
```

`submit()`/`validate()` accept the raw wire string, a `parse_qs` dict, pairs, or a `Params`; `wire()` produces what the client would send for the currently rendered inputs.
