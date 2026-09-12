# Part 5 — Worked examples against the proposed API

These are the examples the design must make easy. They use the API from Part 4; the data/validation halves run today in the spike (Part 7), the rendering helpers are specified but not yet built.

## 5.1 Edit an existing record (initial values, save, reset)

```python
class Plant(BaseModel):
    name: str = Field(min_length=3, max_length=20)
    watering_schedule_days: int = Field(ge=1, le=30, title="Watering schedule (days)")
    last_watered: datetime = Field(default_factory=datetime.now)

class PlantEditView(BaseEventHandler, LiveView):
    async def handle_params(self, socket, plant_id: str):
        plant = await plants.get(plant_id)
        socket.context = {"plant": plant, "form": Form(Plant, data=plant, as_="plant")}

    @event("validate")
    async def validate(self, socket, payload: dict):
        socket.context["form"].validate(payload)

    @event("save")
    async def save(self, socket, payload: dict):
        form = socket.context["form"].submit(payload)
        if form.valid:
            await plants.update(socket.context["plant"].id, form.model)
            socket.put_flash("info", "Saved")
            socket.context["form"] = Form(Plant, data=form.model, as_="plant")   # reset to the saved state
```

```html
<form id="plant-form" phx-change="validate" phx-submit="save">
  {{ form.name | field }}
  {{ form.watering_schedule_days | field }}
  {{ form.last_watered | field }}
  <button type="submit" phx-disable-with="Saving…">Save</button>
</form>
```

What the user sees: initial values from the instance; `type="number" min="1" max="30" step="1" required` on the schedule input; `type="datetime-local"` with the ISO value; errors only after leaving a field or submitting.

## 5.2 Addresses: add, remove, reorder (list of models)

```python
class Address(BaseModel):
    street: str = Field(min_length=3)
    city: str
    primary: bool = False

class Profile(BaseModel):
    name: str
    addresses: list[Address] = Field(min_length=1, max_length=5)
```

```html
<form phx-change="validate" phx-submit="save">
  {{ form.name | field }}
  <fieldset>
    <legend>Addresses</legend>
    {% for row in form.addresses %}
      <div id="{{ row.id }}" class="row">
        {{ row | key_input }}                       {# hidden profile[addresses][0][_key] #}
        {{ row.street | field }} {{ row.city | field }} {{ row.primary | field }}
        {{ row | intent_button("move:up", "↑") }} {{ row | intent_button("move:down", "↓") }}
        {{ row | intent_button("remove", "Remove") }}
      </div>
    {% endfor %}
    {{ form.addresses | errors }}                  {# "Add at least 1 address" / "At most 5" #}
    {{ form.addresses | intent_button("add", "Add address") }}
  </fieldset>
  <button type="submit">Save</button>
</form>
```

or, at level 0, `{{ form.addresses | field }}` renders exactly that fieldset. The handlers are the same two methods as in 5.1: intents arrive as ordinary `validate` events (`profile[addresses][_intent]=remove:k2` is the submitter pair the client injects), and `Form.validate()` applies them before validating. Row DOM ids are `profile_addresses_k2`, so removing the first row does not re-id the others; names are renumbered (`profile[addresses][0][street]`) which the client tolerates because it never value-patches the focused input.

## 5.3 Personal or business account (discriminated union)

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
{{ form.email | field }}
{{ form.account.kind | field({"widget": "radio", "labels": {"personal": "Personal", "business": "Business"}}) }}
{% if form.account.kind.value == "business" %}
  {{ form.account.company | field }} {{ form.account.vat_id | field }}
{% else %}
  {{ form.account.nickname | field }}
{% endif %}
```

`{{ form.account | field }}` does the branching itself. Changing the radio is a normal `phx-change`; the server re-renders the other branch; values typed into the previous branch come back if the user switches again (shelf). Errors inside a variant (`('account', 'business', 'company')` in pydantic) show on `form.account.company`.

## 5.4 Country → state (dependent select)

```python
class Shipping(BaseModel):
    country: Annotated[str, Input(options=COUNTRIES)]
    state: Annotated[str, Input(options=lambda form: STATES.get(form.country.value, []))]
```

```python
@event("validate")
async def validate(self, socket, payload: dict):
    form = socket.context["form"].validate(payload)
    if form.target == ("country",):                # the _target path of this change
        form.set("state", "")                      # clear the dependent value
```

The `options` callable is evaluated at render time with the current form, so the state list follows the country; the handler only resets the stale selection.

## 5.5 Three-step wizard on one model

```python
class Onboarding(BaseModel):
    # step 1
    name: str = Field(min_length=2)
    email: EmailStr
    # step 2
    addresses: list[Address] = Field(min_length=1)
    # step 3
    plan: Literal["free", "pro"] = "free"
    accept_terms: bool

STEPS = [["name", "email"], ["addresses"], ["plan", "accept_terms"]]

class OnboardingView(BaseEventHandler, LiveView):
    async def mount(self, socket, session):
        socket.context = {"form": Form(Onboarding, as_="onboarding"), "step": 0}

    @event("validate")
    async def validate(self, socket, payload: dict):
        socket.context["form"].validate(payload)

    @event("next")
    async def next(self, socket, payload: dict):
        ctx = socket.context
        step = ctx["form"].submit(payload).step(STEPS[ctx["step"]])   # gate errors to this step's paths
        if step.valid:
            ctx["step"] += 1

    @event("back")
    async def back(self, socket):
        socket.context["step"] -= 1

    @event("finish")
    async def finish(self, socket, payload: dict):
        form = socket.context["form"].submit(payload)
        if form.valid:
            await onboard(form.model)
```

```html
<form phx-change="validate" phx-submit="{% if step == 2 %}finish{% else %}next{% endif %}">
  {{ form | render(steps[step]) }}
  {% for name in form.hidden_fields(exclude=steps[step]) %}{{ name | hidden_input }}{% endfor %}
  {% if step > 0 %}<button type="button" phx-click="back">Back</button>{% endif %}
  <button type="submit">{% if step == 2 %}Finish{% else %}Next{% endif %}</button>
</form>
```

Whole-model validation runs every time; `form.step(paths)` only changes what is *visible* and what "valid" means for the Next button. Values from other steps are carried as hidden inputs (or kept server-side with `Form(..., merge_params=True)`), so Back never loses data and recovery after a reconnect restores the whole form.

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
    <label for="{{ form.name.id }}" class="label">Name</label>
    <input name="{{ form.name.name }}" id="{{ form.name.id }}" value="{{ form.name.value }}"
           {{ form.name.attrs }} phx-debounce="blur" class="input {% if form.name.errors %}input-error{% endif %}">
    {{ form.name | errors }}
  </div>
  {{ form.email | field }}     {# mixing levels in one form is fine #}
</div>
```

`form.name.attrs` renders `required minlength="2" maxlength="40" aria-describedby="profile_name-hint profile_name-error" aria-invalid="true"` (the aria parts only when there is a hint / a visible error).

## 5.7 Custom widget and server-side uniqueness check

```python
def color_picker(field: Field, theme: Theme, **attrs) -> Markup:
    return Markup(f'<input type="color" name="{field.name}" id="{field.id}" value="{field.value or "#000000"}" {field.attrs}>')

async def unique_email(model: Signup, form: Form) -> list[FormError]:
    if await users.exists(email=model.email):
        return [FormError(("email",), "unique", {}, "That email is already registered")]
    return []

Form(Signup, widgets={"color": color_picker}, checks=[unique_email])
```

The check runs on submit after pydantic passes; the error is displayed on `email` and survives re-validation until the email changes.

## 5.8 Testing without a socket

```python
def test_signup_business_requires_company():
    form = Form(Signup, as_="signup").submit({"signup": {"email": "a@b.co", "account": {"kind": "business", "company": ""}}})
    assert not form.valid
    assert form["account"]["company"].errors == ["This field is required"]

def test_add_address_intent():
    form = Form(Profile, as_="profile").validate(encode({"profile": {"name": "L", "addresses": [{}]}}, intent="profile[addresses][_intent]=add"))
    assert len(form.rows("addresses")) == 2
```
