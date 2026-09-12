# Django Forms/ModelForms/Formsets/rendering/crispy-forms and WTForms/Flask-WTF — the classic Python form libraries

Versions researched: Django 5.2.17 (installed source + docs/releases 4.0/5.0), WTForms 3.2.2 (installed), Flask-WTF (main), Bootstrap-Flask (main), django-crispy-forms docs (main), django-widget-tweaks (main), django-formset (jrief, README), wtforms-sqlalchemy (main). Date: 2026-09-12. All code below was either read from source or executed (`dj_demo.py`, `wt_demo.py` in the scratchpad; outputs pasted verbatim).

## TL;DR

- Both libraries share one architecture: a **declarative Form class** whose attributes are **Field** objects (validate + coerce string(s) -> Python), each Field owning a **Widget** (Python value -> HTML, and for Django also HTML data -> raw value via `value_from_datadict`). Django adds a third object, **BoundField** = (form, field, name) glue that knows `html_name`, `auto_id`, `id_for_label`, `errors`, `value()`, `css_classes()`, `as_widget(attrs)`. This three-way split is the most reusable idea here.
- **Data flow is flat and stringly**: input is a multidict (`QueryDict`/`getlist`), nesting is encoded in names with dashes (`prefix-field`, `pets-0-name`, `addresses-0-city`), never `a[b][c]`. Each widget/field decides how to read the multidict (checkbox missing => False; `getlist` for multi-select; `""` => `None` for IntegerField).
- **Validation pipeline is fixed and well known**: Django `full_clean` = per-field `field.clean` (to_python -> validate -> run_validators) -> `clean_<name>()` -> form `clean()` -> `_post_clean()` (ModelForm: build instance, `instance.full_clean()`). WTForms: `process` (obj/data/formdata -> `data`, filters) then `validate` = `pre_validate` -> validator chain (`StopValidation` short-circuits) -> `post_validate`, with inline `validate_<name>(form, field)`.
- **Errors are structured**: Django `ValidationError(message, code=, params=)` -> `ErrorDict[str, ErrorList]`, `errors.as_data()` keeps code/params, `errors.as_json()`; i18n via `default_error_messages` merged down the class MRO and overridable per-field with `error_messages={...}`. WTForms errors are plain `dict[name, list[str]]` (nested dicts/lists for FormField/FieldList), no codes.
- **Rendering moved to templates** (Django 4.0: `Form.render/get_context/template_name`; 5.0: `BoundField.as_field_group` + `field_template_name`) precisely because string-built `as_p/as_table` could not be styled; the ecosystem (crispy-forms template packs, widget-tweaks `render_field`, django-formset renderers) exists because default rendering is not customizable enough.
- **Dynamic lists are the weak spot of both**: Django formsets need a hidden `ManagementForm` (`TOTAL_FORMS`, `INITIAL_FORMS`, ...) and an `empty_form` with `__prefix__` for client-side cloning; WTForms `FieldList` extracts indices from submitted key names and `populate_obj` on `FieldList(FormField)` crashes without pre-existing objects (real traceback below).
- "Model -> form" derivation exists in both (`ModelForm` via `fields_for_model`/`formfield_callback`; `wtforms_sqlalchemy.model_form(model, only=, exclude=, field_args=, converter=)`) and is the closest thing to "here's my class, do the rest".

## Mental model & core abstractions

**Django.** `django.forms.Form` uses `DeclarativeFieldsMetaclass` to collect `Field` attributes into `base_fields`; each instance deep-copies them into `self.fields` (so views can mutate per-instance). Signature: `Form(data=None, files=None, auto_id="id_%s", prefix=None, initial=None, error_class=ErrorList, label_suffix=None, empty_permitted=False, field_order=None, use_required_attribute=True, renderer=None)`. `is_bound = data is not None or files is not None`.

`Field(*, required=True, widget=None, label=None, initial=None, help_text="", error_messages=None, show_hidden_initial=False, validators=(), localize=False, disabled=False, label_suffix=None, template_name=None)` (fields.py:15-30). A Field never touches HTML; its `clean(value)` is exactly:

```python
def clean(self, value):
    value = self.to_python(value)
    self.validate(value)
    self.run_validators(value)
    return value
```

`Widget` (widgets.py) is the HTML side: `render(name, value, attrs=None, renderer=None)` -> `get_context` -> template; `value_from_datadict(data, files, name)`; `value_omitted_from_data`; `format_value`; `id_for_label`; `use_required_attribute`. `BoundField` (boundfield.py) is created by `form[name]` and is what templates touch. `ModelForm` is a Form whose metaclass calls `fields_for_model(model, fields, exclude, widgets, formfield_callback, localized_fields, labels, help_texts, error_messages, field_classes, ...)`; every model field has `formfield(**kwargs)` returning the matching form Field, and `formfield_callback(f, **kwargs)` (Meta or factory arg) lets you override the mapping.

**WTForms.** `Form(formdata=None, obj=None, prefix="", data=None, meta=None, **kwargs)` (form.py:242). `FormMeta` collects `UnboundField`s; each instance binds them (`unbound_field.bind(form, name, prefix, id, _meta, translations)`) and immediately calls `process`. There is no BoundField: the bound `Field` itself carries `name`, `id`, `data`, `raw_data`, `object_data`, `errors`, `flags`, `render_kw`, and is callable: `field(**kwargs)` -> `meta.render_field(field, kwargs)` -> `field.widget(field, **kwargs)` -> `Markup`. `class Meta` on the form controls `csrf`, `csrf_class`, `locales`, `wrap_formdata`, `render_field`, `bind_field`.

## Data in (naming, parsing, coercion, nested/lists)

Both consume a **multidict** (`QueryDict`; WTForms needs `.getlist(name)` and `name in formdata`; `Meta.wrap_formdata` adapts Django/WebOb/werkzeug). Django reads per widget: `Form._widget_data_value(widget, html_name)` -> `widget.value_from_datadict(self.data, self.files, html_name)`; `BoundField.data` is that raw value; `Field._clean_bound_field(bf)` cleans `bf.initial if self.disabled else bf.data`.

Naming: `Form.add_prefix(name)` -> `"%s-%s" % (prefix, name)`; `auto_id="id_%s"` -> `id_p-age`. Real output:

```
html_name/auto_id/id_for_label p-age id_p-age id_p-age
```

Coercion specifics verified from source and by running:

- `CheckboxInput.value_from_datadict`: `if name not in data: return False`; strings `"true"/"false"` mapped, else `bool(value)`. `value_omitted_from_data` returns False because an unchecked box is indistinguishable from omitted.
- `ChoiceWidget.value_from_datadict` (SelectMultiple, CheckboxSelectMultiple): `getter = data.getlist` if available else `data.get`. So `QueryDict("p-tags=a&p-tags=b")` -> `['a','b']`.
- `IntegerField.to_python`: `if value in self.empty_values: return None`; strips trailing `.0*`; `int()` failure -> `ValidationError(self.error_messages["invalid"], code="invalid")`. Running: `p-age=` with `required=False` -> `cleaned_data['age'] is None`.
- `Field.empty_values = (None, "", [], (), {})`; `required=True` + empty -> `code="required"`.

WTForms: `Field.process(formdata, data=unset_value, extra_filters=None)` (core.py:284) sets `object_data` from obj/kwargs/default, calls `process_data(data)`, then **only if formdata is not None**: `raw_data = formdata.getlist(self.name)` if `self.name in formdata` else `[]`, then `process_formdata(raw_data)`; `ValueError` from either is stored in `process_errors` and later becomes the first validation error. Running `p-age=x` gave `raw_data ['x']`, `data None`, errors `['Not a valid integer value.', 'Number must be between 0 and 150.']` (note: NumberRange still ran on `None` and produced a second, misleading message). `BooleanField.process_formdata` treats missing key as False (`admin.data: False` with no key submitted). `SelectMultipleField` uses `getlist`.

Nesting: WTForms `FormField(Address)` binds the subform with `prefix = self.name + self.separator` (default `-`); `FieldList` names entries `f"{self.short_name}{self._separator}{index}"` and on `process` discovers indices with `_extract_indices(prefix, formdata)` by scanning **all formdata keys** (sparse indices allowed: submitted `addresses-0-*` and `addresses-3-*` produced exactly two entries, `['p-addresses-0-city', 'p-addresses-3-city']`; `append_entry` then continued at 4). `min_entries` pads, `max_entries` truncates. Django has no nested Form field at all; nesting = a `FormSet` of Forms with prefix `pets-0-age`, plus `inlineformset_factory(parent_model, model, form=..., fk_name=...)` for FK children.

## Validation & error model

**Django order** (forms.py:324-375): `full_clean` resets `_errors = ErrorDict()`; unbound -> stop; `empty_permitted and not has_changed()` -> skip everything (used by formset extra forms); then `_clean_fields` -> `_clean_form` -> `_post_clean`. `_clean_fields`: for each bound item `cleaned_data[name] = field._clean_bound_field(bf)`, then `clean_<name>()` if present (must return the value); any `ValidationError` -> `add_error(name, e)`. `_clean_form`: `self.clean()` may return a new `cleaned_data` or raise; errors go to `NON_FIELD_ERRORS` (`"__all__"`). `add_error(field, error)` normalises str/list/dict/ValidationError, raises `ValueError` for unknown field names, creates `ErrorList(renderer=..., field_id=self[field].auto_id)` (so error `<ul>` gets `id="id_p-name_error"` for `aria-describedby`), and **deletes the key from `cleaned_data`** so later `clean()` code cannot trust a failed field. `has_error(field, code=None)` checks codes. `ModelForm._post_clean` (models.py:474) runs `construct_instance` then `self.instance.full_clean(exclude=..., validate_unique=False)` and `validate_unique()`, folding model-level errors back into form errors via `_update_errors` — i.e. Django too has a "form validation, then model validation" two-phase pipeline, which is what pyview's Pydantic step corresponds to.

Errors keep structure: `ValidationError("%(value)s is taken", code="taken", params={"value": n})`. Real run:

```
errors {'name': ['rex is taken']} | as_data {'name': [('taken', {'value': 'rex'})]}
errors.as_json {"name": [{"message": "rex is taken", "code": "taken"}]}
```

i18n: each Field class declares `default_error_messages = {"required": _(...), "invalid": _(...)}`; `Field.__init__` walks `reversed(self.__class__.__mro__)` merging them, then `messages.update(error_messages or {})` so `CharField(error_messages={"required": "Give it a name!"})` works (output: `f2 errors {'name': ['Give it a name!'], ...}`). Messages are lazy gettext strings, interpolated with `params` at render time.

**WTForms order**: `Form.validate(extra_validators=None)` collects `validate_<name>` class attributes as extra validators, then for each field `field.validate(form, extra)`: `errors = list(process_errors)`; `pre_validate(form)`; `_run_validation_chain` where a validator raising `StopValidation` ends the chain (`DataRequired`/`InputRequired`/`Optional` all `field.errors[:] = []` first, so "required" replaces coercion errors); `post_validate(form, stop_validation)`. Form-level checks have no dedicated hook: you override `validate()` on the Form and append to `self.form_errors` / some field's `errors`. Differences that matter: `DataRequired` checks coerced `field.data` truthiness (so `0` or `False` fail), `InputRequired` checks `raw_data[0]`, `Optional` checks `raw_data` and *stops* the chain on empty. Validators expose HTML5 hints via `field_flags` (`{"required": True}`, `{"minlength": .., "maxlength": ..}`, `{"min":.., "max":..}`) copied onto `field.flags` and emitted by `Input.__call__` if the name is in `widget.validation_attrs`. Messages: each validator takes `message=None` and falls back to `field.gettext("This field is required.")` (i18n via `Meta.locales`/`wtforms.i18n`). Errors are `form.errors: dict[str, list]`, nested for subforms: `'addresses': [{'city': ['This field is required.'], 'zip': ['5 digits']}, {}]`. No codes, no params.

## Form state (bound/unbound, touched/used, attempted values)

Django: `is_bound` is the only mode flag; an unbound form renders `initial` (form-level `initial` dict > `field.initial`, callables called, see `get_initial_for_field`); a bound form renders **attempted values**: `BoundField.value()` returns `self.data` when bound (real: `bf.value() 'rex'` after failed validation), formatted through `field.prepare_value`. There is no touched/dirty concept per field; the closest is `changed_data`/`has_changed()` = `[name for name, bf in _bound_items() if bf._has_changed()]` comparing `field.has_changed(initial, data)` (with the `show_hidden_initial` trick: a hidden `initial-<name>` input so dynamic initials survive). `cleaned_data` exists only after `full_clean` (triggered lazily by `.errors`/`is_valid()`); `is_valid()` is `self.is_bound and not self.errors`. WTForms has no bound flag at all; `formdata is None` versus not decides in `process`, `raw_data` is the attempted value, `object_data` is what came from `obj`, `data` is the coerced value, and `field.errors` is `[]` until `validate()` runs. Flask-WTF adds `is_submitted()` (request method is POST/PUT/PATCH/DELETE) and `validate_on_submit()`, plus auto-passing `request.form`/`request.files` and CSRF (`hidden_tag()` renders every `HiddenInput` field including `csrf_token`).

## Rendering & customization & styling

Django's shift to templates: 4.0 release notes: "Forms, Formsets, and ErrorList are now rendered using the template engine to enhance customization. See the new `Form.render`, `Form.get_context`, and `Form.template_name`". `BaseRenderer` (renderers.py:19-24) declares `form_template_name = "django/forms/div.html"`, `formset_template_name = "django/forms/formsets/div.html"`, `field_template_name = "django/forms/field.html"`, `bound_field_class = None`; `Form.get_context` returns `{"form", "fields": [(bf, bf.errors)...], "hidden_fields", "errors": top_errors}`. Widgets already rendered via templates since 1.11 (`django/forms/widgets/input.html` etc.; a project can shadow any of them by putting `FORM_RENDERER = "django.forms.renderers.TemplatesSetting"` and providing its own). 5.0 added "field groups": `{{ form.name.as_field_group }}` renders `field.html`:

```django
{% if field.use_fieldset %}<fieldset ...>{% if field.label %}{{ field.legend_tag }}{% endif %}
{% else %}{% if field.label %}{{ field.label_tag }}{% endif %}{% endif %}
{% if field.help_text %}<div class="helptext" id="{{ field.auto_id }}_helptext">{{ field.help_text|safe }}</div>{% endif %}
{{ field.errors }}
{{ field }}{% if field.use_fieldset %}</fieldset>{% endif %}
```

and can be swapped per project (renderer), per field (`Field(template_name=)`) or per request (`form.fields[...].template_name`). BoundField supplies the accessibility glue automatically (`build_widget_attrs`): `required`, `disabled`, `aria-invalid="true"` when errors, `aria-describedby="<id>_helptext <id>_error"`. Real output of `f["name"].as_widget(attrs={"class": "input"})`:

```html
<input type="text" name="p-name" value="rex" maxlength="10" class="input" required aria-invalid="true" aria-describedby="id_p-name_error" id="id_p-name">
```

Styling hooks: `Form.error_css_class` / `required_css_class` consumed by `BoundField.css_classes(extra_classes)` and `label_tag`; `BoundField.widget_type` (`"text"`, `"select"`, `"checkbox"`) for template branching; `BoundWidget` iteration for radios/checkbox lists (`{% for radio in form.beatles %}{{ radio.tag }} {{ radio.choice_label }}`).

Ecosystem: **django-crispy-forms** puts layout in Python: a `FormHelper` with `form_method`, `form_class`, `form_tag`, `form_show_errors`, `render_unmentioned_fields`, `label_class`/`field_class`, `attrs`, and `helper.layout = Layout(Fieldset('legend', 'like_website', 'favorite_number', ...), Submit('submit', 'Submit', css_class='button white'))`; rendered by `{% crispy example_form %}` or the untunable `{{ form|crispy }}` filter ("think of it as the built-in `as_table`... You cannot tune up the output"). A **template pack** (bootstrap3/4/5, tailwind, uni_form, bulma) is a directory of small templates: `whole_uni_form.html`, `field.html`, `div.html`, `baseinput.html`... each layout object has a template. **django-widget-tweaks** goes the other way, in the template: `{% render_field form.title class+="css_class_1" placeholder=form.text.label %}` and filters `|add_class:"x"|attr:"rows:4"`; `WIDGET_ERROR_CLASS`/`WIDGET_REQUIRED_CLASS` context vars. **django-formset** (jrief) builds on the 4.0 renderer ("provides form renderers for all major CSS frameworks"; `{% render_form form "bootstrap" field_css_classes="row mb-3" label_css_classes="col-sm-3" control_css_classes="col-sm-9" %}`) and wraps forms in a `<django-formset endpoint=... csrf-token=...>` web component that validates on blur with "exactly the same" browser constraints as the Python field, posts JSON, shows server `clean()` errors "nearby the rejected fields without having to re-render the complete page", supports nested **FormCollection**s with siblings (add/remove/sort) and `df-show="condition"` / `df-hide` / `df-disable` expressions over current values — the closest Django analogue to LiveView forms.

WTForms renders by calling fields: `Input.__call__(field, **kwargs)` sets `id`, `type`, `value=field._value()`, copies `flags` in `validation_attrs`, then `Markup(f"<input {html_params(name=field.name, **kwargs)}>")`. Real: `f.name(class_="input")` -> `<input class="input" id="p-name" name="p-name" placeholder="Jane" required type="text" value="rex">`, `f.age()` -> `... max="150" min="0" type="number" value="x"` (min/max came from `NumberRange`, `placeholder` from `render_kw`). Layout is entirely the template's job; **Bootstrap-Flask** ships Jinja macros `render_form(form, action="", method="post", extra_classes=None, role="form", form_type="basic", horizontal_columns=('lg', 2, 10), enctype=None, button_map={}, id="", novalidate=False, render_kw={}, ...)`, `render_field(field, form_type=..., horizontal_columns=..., ...)`, `render_form_row(fields, ...)` which branch on `field.type` (`"BooleanField"`, `"FieldList"`, `"FormField"`...) and CSS-framework version.

## Nested / dynamic / conditional

Django formsets (formsets.py): `formset_factory(form, formset=BaseFormSet, extra=1, can_order=False, can_delete=False, max_num=None, validate_max=False, min_num=None, validate_min=False, absolute_max=None, can_delete_extra=True, renderer=None)`; constants `TOTAL_FORMS, INITIAL_FORMS, MIN_NUM_FORMS, MAX_NUM_FORMS, ORDER, DELETE`, `DEFAULT_MAX_NUM = 1000`. The bound formset trusts a hidden `ManagementForm` for the count (missing -> `code="missing_management_form"`); every child gets `prefix=self.add_prefix(i)` -> `pets-0`, `use_required_attribute=False`, and extra forms get `empty_permitted=True` (so an untouched extra row skips validation). `empty_form` is the same form with `prefix="pets-__prefix__"` for JS cloning (`.replace(/__prefix__/g, n)` and bump `TOTAL_FORMS` — Django ships no JS outside admin). Real run:

```
management_form: <input type="hidden" name="pets-TOTAL_FORMS" value="2" ...><input type="hidden" name="pets-INITIAL_FORMS" value="1" ...><input type="hidden" name="pets-MIN_NUM_FORMS" value="1" ...><input type="hidden" name="pets-MAX_NUM_FORMS" value="1000" ...>
form0 age name: pets-0-age | empty_form: pets-__prefix__-name
formset valid True ... deleted [{'age': None, 'adopted': False, 'tags': [], 'DELETE': True}]
```

Formset-level rules go in `BaseFormSet.clean()` (errors to `non_form_errors()`), `add_fields(form, index)` injects `ORDER`/`DELETE`. Conditional fields: nothing declarative; you mutate `self.fields` in `__init__` or use `clean()` — "Dynamic Form Composition" is also the WTForms docs' answer (specific_problems.rst: `class F(MyBaseForm): pass; setattr(F, name, StringField(...))` inside the view). Conditional visibility in Django land lives in django-formset's `df-show` expressions or hand-written JS.

WTForms `FieldList(FormField(Address), min_entries=1, max_entries=None, separator="-")` handles nesting recursively and `append_entry(data)` / `pop_entry()` mutate the bound field, but the object round-trip is brittle: `populate_obj` on `FieldList` iterates `getattr(obj, name)` and builds `fake_obj`s; `FormField.populate_obj` raises when neither a candidate object nor `_obj` exists. Verified:

```
TypeError: populate_obj: cannot find a value to populate from the provided obj or input data/defaults
```

(triggered by `f.populate_obj(Obj())` where `Obj` has no `addresses`). Nested errors and `data` do round-trip cleanly though (`'addresses': [{'city': '', 'zip': '123'}, {'city': 'Oslo', 'zip': None}]`).

## DX highlights with real code (cite each)

1. **Declarative + inline hooks** (forms.py `_clean_fields`): `clean_<name>()` returns the replacement value, `clean()` cross-field, `add_error("age", "...")` targeted at another field from `clean()` — worked in the demo (`'age': ['Adopted pets need an age']`). WTForms: `def validate_name(form, field): raise ValidationError(...)` auto-registered by `Form.validate` (form.py:308).
2. **Model derivation**: `class PetForm(ModelForm): class Meta: model = Pet; fields = ["name", "age"]; widgets = {...}; labels = {...}; error_messages = {...}; formfield_callback = ...` (models.py `ModelFormOptions` attributes); `model_to_dict(instance)` -> initial; `form.save(commit=False)`; `modelform_factory(model, form=ModelForm, fields=None, exclude=None, formfield_callback=None, widgets=None, ...)`. WTForms: `model_form(model, db_session=None, base_class=Form, only=None, exclude=None, field_args=None, converter=None, exclude_pk=True, exclude_fk=True)` (wtforms_sqlalchemy/orm.py:285).
3. **Structured errors with a11y ids for free** (`add_error` creating `ErrorList(field_id=self[field].auto_id)`; `BoundField.aria_describedby`).
4. **Validator -> HTML attribute sync** (WTForms `field_flags`; Django `Field.widget_attrs(widget)` gives `maxlength`, `min`, `max`, `step`; `use_required_attribute`), so server rules become browser constraints without duplication.
5. **`empty_permitted and not has_changed()` short-circuit** (forms.py:334) — the mechanism that makes "extra" rows optional; a clean idea for optional nested sub-forms.
6. **`errors.as_data()` / `as_json(escape_html=False)`** for pushing errors to a JS client; `has_error(field, code)` for tests.
7. **Flask-WTF `validate_on_submit()`** = one-liner GET/POST split; Bootstrap-Flask `{{ render_form(form) }}` = zero-template forms with a `form_type="horizontal"` switch.

## Pain points & criticisms (cite)

- **Formsets are the most disliked part of Django**: management-form 400s (`missing_management_form`), `__prefix__` cloning JS you write yourself, `TOTAL_FORMS` tampering caps via `absolute_max`, no nesting of formsets inside forms (inline formsets are one level). django-formset's README exists largely to replace them ("allows an infinite number of nesting levels").
- **String-based rendering was unstylable** — the 4.0/5.0 release notes show the before/after: 10 lines of `label_tag`/`help_text`/`errors`/`{{ field }}` per field collapsing into `as_field_group`. Even now, per-widget CSS classes require `widgets={"name": TextInput(attrs={"class": ...})}` in Python or widget-tweaks in templates; hence crispy-forms' entire raison d'être ("|crispy ... You cannot tune up the output").
- **Untyped access**: `cleaned_data` is a dict, templates use `form.name` by attribute lookup on a `BoundField`; no static typing of values; `Form.__getitem__` raises `KeyError` late.
- **QueryDict-only mental model**: `data` must be flat; JSON bodies need conversion; `CheckboxInput.value_omitted_from_data` returning False shows how the HTML checkbox quirk leaks into `construct_instance` (unchecked box vs omitted field are indistinguishable, so a partial update cannot tell "not sent" from "false").
- **WTForms `DataRequired` vs `InputRequired` confusion** is documented in-source ("this validator used to be called `Required` but the way it behaved ... was not symmetric to the `Optional` validator"). `NumberRange` running on `None` after a failed coercion double-reports (see `age` errors above).
- **WTForms `FieldList` + `populate_obj`** TypeError above; sparse indices come straight from client key names; `Meta.csrf` requires app glue (Flask-WTF); no codes/params on errors; `FormField` refuses filters; unbound `Form(obj=...)` and bound `Form(formdata)` ignore `obj` when formdata present, so partial patches need `MultiDict` merging by hand.
- Neither library has a notion of "touched"/"used" inputs; both validate the entire form on every bind, which is fine for POST but exactly the wrong default for per-keystroke `phx-change`.

## Lessons for pyview — steal / adapt / avoid

**Steal**
1. **The Field / Widget / BoundField split, mapped onto Pydantic.** Pydantic already *is* the Field layer (types, coercion, validators, `ValidationError` with `loc`/`type`/`ctx`/`msg` = Django's `code`/`params`/message). pyview needs the other two: a *Widget* registry keyed by annotation (`bool -> checkbox`, `Literal/Enum -> select`, `list[Enum] -> multi-select`, `int -> number` with `ge/le` -> `min/max`, `Field(max_length=) -> maxlength`) that owns both `value_from_payload` and rendering, and a *BoundField* object handed to templates with `name`, `id`, `value` (attempted raw string), `errors`, `required`, `attrs()` (`aria-invalid`, `aria-describedby`), `label`, `help_text`, `widget_type`. This is the concrete answer to "here's my Pydantic class, do the rest" while keeping "users may want to provide their own HTML".
2. **Validator -> HTML-attribute sync** (WTForms `field_flags`, Django `widget_attrs`) derived from `FieldInfo`/`annotated_types` constraints, so `required`, `min`, `max`, `maxlength`, `pattern`, `step` are emitted automatically.
3. **`errors.as_data()`-style structured errors**: keep Pydantic's `type`, `loc`, `ctx` and format via an overridable message table (Django's `default_error_messages` merge + per-field `error_messages={}` override) — this gives i18n and custom wording without touching validators.
4. **Two-phase validation like `full_clean` -> `_post_clean`**: field-level coercion/`clean_<name>` first (partial, per-target on `phx-change`), whole-model Pydantic validation second, errors merged into one ErrorDict; `add_error(field, ...)` from cross-field validators (map `model_validator` errors to a chosen field, as Django's `add_error("age", ...)` does).
5. **Renderer + template-pack architecture**: default `field group` template (label/help/errors/widget order like `field.html`) swappable per project (`renderer`), per field (`template_name`), per call (`as_widget(attrs)`); ship Tailwind/Bootstrap/bare packs as Ibis/t-string partials, and a `render_field(bf, **attrs)`/`class+=` style escape hatch (widget-tweaks) for hand-written HTML.
6. **`empty_permitted and not has_changed()`** for optional nested sub-models: an untouched optional branch validates as `None` instead of erroring.

**Adapt**
- Nested naming: keep Phoenix/Rack bracket names (`user[addresses][0][city]`) on the wire (the JS client and `phx-feedback-for`/`_unused_` already speak them) and decode into nested dicts/lists before Pydantic; but internally give each BoundField Django-style stable `id`s (`user_addresses_0_city`) and WTForms-style sparse-index tolerance (`_extract_indices`) so rows can be removed client-side without renumbering.
- ModelForm-style `Meta`-free derivation: `Form.from_model(Address, only=..., exclude=..., widgets={...}, labels={...})` mirroring `fields_for_model` args and a `formfield_callback`-like hook `(field_name, FieldInfo) -> Widget`.
- Flask-WTF's `validate_on_submit` becomes: on `phx-change` validate only touched/`_target` (+ dependents), on `phx-submit` full validate; Django's `changed_data` becomes the "used" set.

**Avoid**
- **Management forms and `__prefix__` cloning** — LiveView re-renders server-side, so the server owns the list length; expose `changeset.append("addresses")`/`remove(i)` actions on the form object (like WTForms `append_entry`/`pop_entry`, but naming stays index-based on the server) and never trust a client count.
- **Flat-only, stringly `cleaned_data` dicts**: return typed Pydantic instances (`changeset.model`) and typed access in t-strings.
- **Untyped error lists without codes** (WTForms) and mutating `self.fields` in `__init__` as the conditional-form story — conditional nesting should be declarative from the model (`Optional[...]`, discriminated `Union`, `Literal` switches) with the widget layer rendering only the active branch.
- **`DataRequired` semantics that reject `0`/`False`** — required-ness must be "input present", not "value truthy".

## Sources (actually read)

- Django 5.2.17 source: `pkgs/py/django/forms/forms.py` (lines 204-400: `is_valid`, `add_prefix`, `get_context`, `add_error`, `full_clean`, `_clean_fields`, `_clean_form`, `has_changed`), `boundfield.py` (`as_widget`, `css_classes`, `build_widget_attrs`, `_has_changed`, `label_tag`, `auto_id`, `id_for_label`, `aria_describedby`, `BoundWidget`), `fields.py` (`Field.__init__`, `clean`, `_clean_bound_field`, `IntegerField`, `MultipleChoiceField`), `widgets.py` (`Widget.get_context/render/value_from_datadict`, `CheckboxInput`, `ChoiceWidget`), `formsets.py` (constants, `management_form`, `empty_form`, `full_clean`, `formset_factory`), `models.py` (`fields_for_model`, `ModelFormOptions`, `_post_clean`, `modelform_factory`, `model_form` list), `renderers.py`, `templates/django/forms/field.html`.
- Django docs: `repos/django/docs/releases/4.0.txt` ("Template based form rendering"), `5.0.txt` (field groups / `as_field_group`).
- WTForms 3.2.2 source: `pkgs/py/wtforms/form.py` (`BaseForm.process`, `Form.__init__`, `Form.validate`), `fields/core.py` (`Field.process`, `validate`, `__call__`, `Flags`), `fields/list.py` (`_extract_indices`, `_add_entry`, `append_entry`), `fields/form.py` (`FormField.process/populate_obj`), `validators.py` (`DataRequired`, `InputRequired`, `Optional`, `field_flags`), `widgets/core.py` (`Input.__call__`, `html_params`).
- `repos/wtforms/docs/specific_problems.rst` (Dynamic Form Composition, Specialty Field Tricks).
- `repos/flask-wtf/src/flask_wtf/form.py` (`is_submitted`, `validate_on_submit`, `hidden_tag`).
- `repos/wtforms-sqlalchemy/src/wtforms_sqlalchemy/orm.py` (`model_form` signature).
- `repos/bootstrap-flask/flask_bootstrap/templates/bootstrap5/form.html` (`render_field`, `render_form`, `render_form_row` macros).
- `repos/crispy-forms/docs/{layouts,template_packs,form_helper,filters}.rst`.
- `repos/widget-tweaks/README.rst`.
- `repos/django-formset/README.md` (Immediate Form Validation, Grouping Forms, Conditional hiding/disabling, How does this all work).
- Executed: `scratchpad/dj_demo.py`, `scratchpad/wt_demo.py` (outputs quoted above).
