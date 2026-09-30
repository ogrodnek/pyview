# Python form-library ecosystem: WTForms, Django Forms, and pydantic/dataclass form & UI libraries (design lessons for a pydantic-first pyview form library)

*Method note: docs.djangoproject.com, wtforms.readthedocs.io, docs.pydantic.dev, fastapi.tiangolo.com, fastht.ml, HN and forum.djangoproject.com were blocked by the egress proxy. I read the same docs from their source files in each project's GitHub repo, plus library source code and PyPI metadata. Findings tagged "verified locally" come from scripts I ran in a scratch venv on 2026-09-30 with pydantic 2.13.5, WTForms 3.2.2, Django 5.2.17 (the newest Django that installs on the venv's Python 3.11; Django 6.1.1 is current), FastAPI 0.142.2, formencode 2.1.1, querystring-parser 1.2.4, marshmallow 4.3.1, cattrs 26.2.1 and msgspec 0.22.0. Version and date facts come from PyPI JSON on 2026-09-30.*

---

## 1. WTForms: data model, validation flow, nesting (FormField/FieldList), rendering, pain points, ecosystem

### Takeaway
WTForms is a declarative, class-per-form library. It keeps three things apart: the Form, the Field (a bound instance that holds data, raw_data, object_data, errors, name and id, and renders itself), and the Widget (a pure renderer). Nesting uses `FormField` and `FieldList` with `-` name prefixing (`addresses-0-street`). The weak spots are well known: dynamic lists (min_entries padding, index gaps, BooleanField can't go in a FieldList), `populate_obj` into non-ORM structures, and no native nested-JSON or model integration, because the form class duplicates the model.

### Cited Findings

**Status / versions**
- WTForms 3.2.2 is the latest stable release (PyPI, 2026-05-03). Flask-WTF is at 1.3.0 (2026-04-23), Starlette-WTF 0.5.0 (2026-05-29), wtforms-alchemy 0.19.1 (2025-08-11) and wtforms-sqlalchemy 0.4.2 (2024-10-25) — [PyPI WTForms](https://pypi.org/project/WTForms/), [PyPI starlette-wtf](https://pypi.org/project/starlette-wtf/), [PyPI wtforms-alchemy](https://pypi.org/project/WTForms-Alchemy/)
- WTForms 3.3 is in beta: 3.3.0b1 came out 2026-05-10, b2 2026-05-24 and b3 2026-06-12. Main changes: `FieldList.insert_entry` and indexed `pop_entry` (closes issue #256), a `SelectChoice`/`Choice` refactor, dict shorthand for choices (`{value: label}`), `post_process` hooks propagated through FormField/FieldList "for cross-field finalization", `Field._form`/`BaseForm._parent_form` so nested fields can reach their enclosing form, `invalid_value_message`/`invalid_choice_message` kwargs, and deprecation of `DateTimeField` (removal in 3.4) — [WTForms CHANGES.rst](https://github.com/pallets-eco/wtforms/blob/main/CHANGES.rst)
- Issue #256 was the long-standing request to delete an arbitrary FieldList entry, since only `pop_entry()` (last entry) existed — [wtforms#256](https://github.com/wtforms/wtforms/issues/256)

**Data model: declarative fields, unbound → bound copy**
- "When a field is defined on a form, the construction parameters are saved until the form is instantiated. At form instantiation time, a copy of the field is made with all the parameters specified in the definition. Each instance of the field keeps its own field data and errors list." — [WTForms fields.rst](https://github.com/pallets-eco/wtforms/blob/main/docs/fields.rst)
```python
class MyForm(Form):
    name    = StringField('Full Name', [validators.required(), validators.length(max=10)])
    address = TextAreaField('Mailing Address', [validators.optional(), validators.length(max=200)])
```
- Each bound field exposes `data` (coerced value), `raw_data` ("the valuelist given from the formdata wrapper", otherwise `None`), `object_data` ("data passed from an object or from kwargs … stored unmodified"), `errors`, `name` (prefixed), `short_name`, `id` and `label`. Hooks: `process_formdata` handles input from outside and `process_data` handles Python-side data — [WTForms fields.rst](https://github.com/pallets-eco/wtforms/blob/main/docs/fields.rst)
- Rendering: "To render a field, simply call it, providing any values the widget expects as keyword arguments", e.g. `form.field(class_="text_blob")`. Fields also implement `__html__`, so template engines can print them without escaping — [WTForms fields.rst](https://github.com/pallets-eco/wtforms/blob/main/docs/fields.rst)

**process(formdata, obj, data, **kwargs): precedence**
- `Form.process` docstring: `formdata` is "usually `request.form` … Should provide a 'multi dict' interface". `obj` supplies existing data from attributes and is "Only used if `formdata` is not passed". For `data`, "`obj` takes precedence if it also has a matching attribute". kwargs are merged with `data`. Per field, the code checks `if obj is not None and hasattr(obj, name)` first, then `kwargs[name]`. `filter_<fieldname>` methods on the form run as the last extra filter — [wtforms/form.py](https://github.com/pallets-eco/wtforms/blob/main/src/wtforms/form.py)
- The docs say "Backing-store objects and kwargs are both expected to be provided with the values being already-coerced datatypes. WTForms does not check the types of incoming object-data or coerce them like it will for formdata" — [WTForms forms.rst](https://github.com/pallets-eco/wtforms/blob/main/docs/forms.rst)

**Validation flow**
- `Field.validate` runs `pre_validate` → the validator chain → `post_validate`. `Form.validate()`: "If the form defines a `validate_<fieldname>` method, it is appended as an extra validator for the field's `validate`", and runs last — [wtforms/form.py](https://github.com/pallets-eco/wtforms/blob/main/src/wtforms/form.py), [WTForms fields.rst](https://github.com/pallets-eco/wtforms/blob/main/docs/fields.rst)
- Form-level errors go in `form_errors` ("often set when overriding `validate`"). `form.errors` is a dict of lists; "If present, the key `None` contains the content of `form_errors`" — [WTForms forms.rst](https://github.com/pallets-eco/wtforms/blob/main/docs/forms.rst)
- `populate_obj(obj)` copies field data onto an object after validation. The canonical example is `form = EditProfileForm(request.POST, obj=user); if request.POST and form.validate(): form.populate_obj(user)` — [WTForms forms.rst](https://github.com/pallets-eco/wtforms/blob/main/docs/forms.rst)

**Nesting: FormField and FieldList**
- `FormField(form_class, …, separator='-')`: "The `data` property … will return the data dict of the enclosed form. Similarly, the `errors` property encapsulate the forms' errors." — [WTForms fields.rst](https://github.com/pallets-eco/wtforms/blob/main/docs/fields.rst)
```python
class TelephoneForm(Form):
    country_code = IntegerField('Country Code', [validators.required()])
    area_code    = IntegerField('Area Code/Exchange', [validators.required()])
    number       = StringField('Number')

class ContactForm(Form):
    first_name   = StringField()
    mobile_phone = FormField(TelephoneForm)
    office_phone = FormField(TelephoneForm)
    im_accounts  = FieldList(FormField(IMForm))   # list of subforms
```
- `FieldList(unbound_field, min_entries=0, max_entries=None, separator='-')`. The docs note: "Due to a limitation in how HTML sends values, FieldList cannot enclose `BooleanField`, `ButtonField`, or `SubmitField` instances." They also say "**Do not** resize the entries list directly, this will result in undefined behavior" — [WTForms fields.rst](https://github.com/pallets-eco/wtforms/blob/main/docs/fields.rst)
- FieldList rebuilds from formdata by scanning keys for the prefix: "if field 'foo' contains keys 'foo-0-bar', 'foo-1-baz', then the numbers 0 and 1 will be yielded". It sorts the indices, truncates to `max_entries`, then pads to `min_entries` with blank entries (`while len(self.entries) < self.min_entries: self._add_entry(formdata)`) — [wtforms/fields/list.py](https://github.com/pallets-eco/wtforms/blob/main/src/wtforms/fields/list.py)
- On main (3.3), "Entries are kept with consecutive indices: `insert_entry`, `pop_entry` and rebuilds from formdata renumber entries so that each entry's `index`, `name` and `id` reflect its position" — [WTForms fields.rst (main)](https://github.com/pallets-eco/wtforms/blob/main/docs/fields.rst)
- Verified locally on WTForms 3.2.2 with `FieldList(FormField(AddressForm), min_entries=1)`:
  - Generated names/ids: `addresses-0-street`; rendered HTML `<input id="addresses-0-street" name="addresses-0-street" required type="text" value="">`.
  - Posting `addresses-0-*` and `addresses-3-street` gives entry names `['addresses-0', 'addresses-3']`, so in 3.2.2 index gaps survive into re-rendered names.
  - The errors structure mirrors the data: `{'name': ['no bobs'], 'age': ['Not a valid integer value.'], 'addresses': [{'street': ['This field is required.']}, {}]}`.
  - Posting zero address keys with `min_entries=1` still yields one blank entry `[{'street': None, 'zip': None}]`, so the user can't delete the last item.
  - `FieldList(BooleanField(), min_entries=3)` with `flags-0=y, flags-2=y` (flags-1 unchecked, so absent) gives `[True, True, False]`, which is misaligned (should be `[True, False, True]`).
  - `populate_obj` onto a plain object whose `addresses` is `[]` raised `TypeError: populate_obj: cannot find a value to populate from the provided obj or input data/defaults`. FormField's populate_obj needs an existing child object.
  
  — [PyPI WTForms 3.2.2](https://pypi.org/project/WTForms/) (verified locally), [wtforms/fields/form.py](https://github.com/pallets-eco/wtforms/blob/main/src/wtforms/fields/form.py)
- `append_entry` data: "accept Python object data for the new entry, not submitted formdata" — [WTForms fields.rst](https://github.com/pallets-eco/wtforms/blob/main/docs/fields.rst)
- A community summary of the dynamic-list pain: you can't delete arbitrary entries (pre-3.3), `append_entry` entries don't receive formdata, and workarounds include custom `ModelFieldList`, the WTForms-Dynamic-Fields package, and JS cloning — [wtforms#256](https://github.com/wtforms/wtforms/issues/256), [gist: Flask-WTF FieldLists with Dynamic Entries](https://gist.github.com/kageurufu/6813878), [PyPI WTForms-Dynamic-Fields](https://pypi.org/project/WTForms-Dynamic-Fields)

**Widgets / customization**
- "Widgets are classes whose purpose are to render a field to its usable representation … When a field is called, the default behaviour is to delegate the rendering to its widget." Built-ins include TextInput, Select, CheckboxInput, ListWidget, TableWidget and others. They return an "HTML-safe" string — [WTForms widgets.rst](https://github.com/pallets-eco/wtforms/blob/main/docs/widgets.rst)
- `class Meta` on a form customizes `locales`, `bind_field`, `wrap_formdata` and `render_field`. `render_field` is the global hook for rendering every field — [WTForms meta.rst](https://github.com/pallets-eco/wtforms/blob/main/docs/meta.rst)
- The 3.3 beta also adds a `DataList` owned by a field (`StringField(datalist=DataList(lambda field: search(field.data)))`), rendered explicitly with `{{ form.country.datalist() }}` "like `Field.errors` or `Field.label` — you decide where each piece appears in the DOM" — [WTForms fields.rst (main)](https://github.com/pallets-eco/wtforms/blob/main/docs/fields.rst)

**i18n**
- "**WTForms does -not- translate any user-provided strings.**" It translates only built-in messages (`Meta.locales = ('fr_FR','fr')`). User messages must be lazy proxies such as `_('Please provide your name')`, which works because WTForms "waits until the last moment (usually validation time)" before interpolating — [WTForms i18n.rst](https://github.com/pallets-eco/wtforms/blob/main/docs/i18n.rst)

**Starlette-WTF (async)**
```python
class MyForm(StarletteForm):
    name = StringField('name', validators=[DataRequired()])

async def index(request):
    form = await MyForm.from_formdata(request)
    if await form.validate_on_submit():
        return PlainTextResponse('SUCCESS')
    return HTMLResponse(template.render(form=form))
```
Templates render `{{ form.csrf_token }}`, `{{ form.name(placeholder='Name') }}` and `form.name.errors[0]`. It supports async custom validators and a `CSRFProtectMiddleware` — [starlette-wtf README](https://github.com/muicss/starlette-wtf)

### Inferences
- WTForms' split between `raw_data` (what the user typed), `data` (coerced value) and `object_data` (original) is the key idea to keep. A pydantic-first library needs the same split, because a failed pydantic validation gives no model instance to re-render from. The raw params must be kept and echoed back.
- `FieldList` index semantics are the #1 footgun. Scanning submitted keys for indices, as WTForms does, avoids Django's management form, but sparse indices, min_entries padding and absent checkboxes all cause misalignment. In a stateful LiveView-style server, add/remove can be server events on authoritative state, so there's no need to infer list length from posted keys.
- A per-subform `errors` structure mirroring the data shape (`{'addresses': [{'street': [...]}, {}]}`) is natural. Pydantic's `loc` tuples give the same thing in flattened form.

### Gaps
- I couldn't fetch GitHub discussions or Reddit threads for WTForms user sentiment. The only pain points cited are from issue #256 and search-result summaries.
- I didn't verify whether WTForms 3.3 final has shipped. PyPI still shows 3.2.2 as latest and CHANGES shows "3.3.0b4 Unreleased".

---

## 2. Django Forms: Form/ModelForm, validation order, BoundField & errors, formsets, rendering API (4.0 → 6.1), crispy-forms / widget-tweaks / formtools

### Takeaway
Django has the most complete server-rendered form model in Python: a `data` → `cleaned_data` pipeline with a well-defined clean order, a BoundField per field, structured errors with codes, formsets for repeated forms, and since 4.0–5.2 a template-based rendering stack (renderers, `as_div`, `as_field_group`, `bound_field_class`) with accessibility wiring (`aria-describedby`, `aria-invalid`). The pain is in repeated and nested data (management forms, JS cloning of `empty_form`, no nested formsets) and in styling (crispy's Python-side layout vs. template-side tweaks).

### Cited Findings

**Versions**
- Django 6.1.1 is current (PyPI, 2026-09-02). Django 6.1 was released 2026-08-05 and 6.0 on 2025-12-03. django-crispy-forms is at 2.7 (2026-07-29), crispy-bootstrap5 2026.9, crispy-tailwind 1.0.3 (last release 2024-02-13), django-widget-tweaks 1.5.1 (2026-01-02), django-formtools 2.7 (2026-07-09) and django-formset 2.2.4 (2026-03-30) — [PyPI Django](https://pypi.org/project/Django/), [Django 6.1 release notes](https://github.com/django/django/blob/main/docs/releases/6.1.txt), [PyPI crispy-tailwind](https://pypi.org/project/crispy-tailwind/), [PyPI django-formset](https://pypi.org/project/django-formset/)

**Validation order (cleaning)**
- `Field.clean()` runs `to_python()` (coercion) → `validate()` → `run_validators()`, stopping at the first `ValidationError`. The form then calls `clean_<fieldname>()`, which must return the value to store in `cleaned_data`. Finally the form's `clean()` handles cross-field rules. "Any errors raised by your Form.clean() override will not be associated with any field in particular. They go into a special 'field' (called `__all__`), which you can access via the `non_field_errors()` method". To target a field from `clean()`, call `add_error(field, msg)` — [Django validation.txt](https://github.com/django/django/blob/main/docs/ref/forms/validation.txt)
- Verified locally (Django 5.2.17) with `clean_name` raising `ValidationError("no bobs", code="bob")` and `clean()` using `add_error("agree", …)` plus raising a form-level error:
  ```
  form.errors.get_json_data() ==
  {'name': [{'message': 'no bobs', 'code': 'bob'}],
   'agree': [{'message': 'minors must agree', 'code': ''}],
   '__all__': [{'message': 'form-level problem', 'code': ''}]}
  cleaned_data == {'age': 12}   # invalid fields are removed from cleaned_data
  ```
  — [PyPI Django](https://pypi.org/project/Django/) (verified locally)
- Empty values are per field: `CharField.empty_value` "Defaults to an empty string", while DateField, DateTimeField and similar have "Empty value: `None`" — [Django fields.txt](https://github.com/django/django/blob/main/docs/ref/forms/fields.txt)
- Checkboxes: `value_omitted_from_data()` for `CheckboxInput`, `CheckboxSelectMultiple` and `SelectMultiple` "always return `False` because an unchecked checkbox and unselected `<select multiple>` don't appear in the data of an HTML form submission, so it's unknown whether or not the user submitted a value." This affects ModelForm default fallback — [Django widgets.txt](https://github.com/django/django/blob/main/docs/ref/forms/widgets.txt), [Django modelforms.txt](https://github.com/django/django/blob/main/docs/topics/forms/modelforms.txt)

**ModelForm (the anti-duplication answer for ORM models)**
```python
class ArticleForm(ModelForm):
    class Meta:
        model = Article
        fields = ["pub_date", "headline", "content", "reporter"]
        field_classes = {"slug": MySlugFormField}   # per-field override
form = ArticleForm(instance=article)
```
- Django 4.2 added `Meta.formfield_callback` for customizing generated fields — [Django modelforms.txt](https://github.com/django/django/blob/main/docs/topics/forms/modelforms.txt), [Django 4.2 release notes](https://github.com/django/django/blob/main/docs/releases/4.2.txt)

**Rendering API timeline**
- **4.0 (Dec 2021)**: "Forms, Formsets, and ErrorList are now rendered using the template engine", with new `Form.render()`, `get_context()` and `template_name` — [Django 4.0 notes](https://github.com/django/django/blob/main/docs/releases/4.0.txt)
- **4.1 (Aug 2022)**: new `div.html` template and `Form.as_div()`, "recommended over the existing `as_table()`, `as_p()` and `as_ul()` styles, as the template implements `<fieldset>` and `<legend>` to group related inputs and is easier for screen reader users to navigate". The project-level default is set via `FORM_RENDERER`'s `form_template_name`/`formset_template_name` — [Django 4.1 notes](https://github.com/django/django/blob/main/docs/releases/4.1.txt)
- **5.0 (Dec 2023)**: div rendering becomes the default. It introduces field groups: `{{ form.name.as_field_group }}` renders label, help text, errors and widget with `django/forms/field.html`, "customized on a per-project, per-field, or per-request basis". Fields get `aria-describedby` for help text and `aria-invalid="true"` when invalid — [Django 5.0 notes](https://github.com/django/django/blob/main/docs/releases/5.0.txt)
  ```django
  {# before: ~15 lines per field of label_tag / help_text / errors / widget #}
  <div>
    {{ form.name.as_field_group }}
    <div class="row">
      <div class="col">{{ form.email.as_field_group }}</div>
      <div class="col">{{ form.password.as_field_group }}</div>
    </div>
  </div>
  ```
- **5.1**: fieldsets get `aria-describedby` — [Django 5.1 notes](https://github.com/django/django/blob/main/docs/releases/5.1.txt)
- **5.2 (Apr 2025)**: `bound_field_class` customizable at project (`BaseRenderer.bound_field_class`), form (`Form.bound_field_class`) or field (`Field.bound_field_class`) level. Also new `ColorInput`/`SearchInput`/`TelInput`, an `ErrorList.field_id`, a `BoundField.aria_describedby` property, and errors linked via `aria-describedby` — [Django 5.2 notes](https://github.com/django/django/blob/main/docs/releases/5.2.txt)
  ```python
  class CustomBoundField(forms.BoundField):
      custom_class = "custom"
      def css_classes(self, extra_classes=None): ...
  class CustomForm(forms.Form):
      bound_field_class = CustomBoundField
  ```
- **6.0 (Dec 2025)**: template partials are built in (`{% partialdef %}`/`{% partial %}`, and `template_name#partial_name` usable with `render()` and `{% include %}`). These are useful for htmx-style fragment re-rendering. The transitional `DjangoDivFormRenderer`/`Jinja2DivFormRenderer` are removed and the default `URLField` scheme changes to https — [Django 6.0 notes](https://github.com/django/django/blob/main/docs/releases/6.0.txt)
- **6.1 (Aug 2026)**: `Stylesheet` form-media asset, an accessible and translatable `BLANK_CHOICE_LABEL` (transitional `USE_BLANK_CHOICE_DASH`), and `FilePathField.set_choices()` — [Django 6.1 notes](https://github.com/django/django/blob/main/docs/releases/6.1.txt)
- Renderer contract: `FORM_RENDERER` (default `DjangoTemplates`). `BaseRenderer` has `form_template_name` (default `django/forms/div.html`), `formset_template_name`, `field_template_name` (`django/forms/field.html`) and `bound_field_class`. A custom renderer must implement `render(template_name, context, request=None)`. Overriding the project renderer "will include forms in the admin site and third-party packages" — [Django renderers.txt](https://github.com/django/django/blob/main/docs/ref/forms/renderers.txt)
- Per-form or per-call override: `class MyForm(forms.Form): template_name = "form_snippet.html"` or `form.render("form_snippet.html")`. Per field: `Field.template_name` controls `as_field_group` — [Django forms/index.txt](https://github.com/django/django/blob/main/docs/topics/forms/index.txt), [Django fields.txt](https://github.com/django/django/blob/main/docs/ref/forms/fields.txt)
- Verified locally: output of `f["name"].as_field_group()` for an invalid field with help text:
  ```html
  <label for="id_name">Name:</label>
  <div class="helptext" id="id_name_helptext">Your name</div>
  <ul class="errorlist" id="id_name_error"><li>no bobs</li></ul>
  <input type="text" name="name" value="bob" required aria-invalid="true"
         aria-describedby="id_name_helptext id_name_error" id="id_name">
  ```
  — [PyPI Django](https://pypi.org/project/Django/) (verified locally, 5.2.17)

**Formsets**
- The management form carries `form-TOTAL_FORMS` and `form-INITIAL_FORMS` (required) plus `MIN_NUM_FORMS`/`MAX_NUM_FORMS` ("only for the convenience of client-side code"). "If you are adding new forms via JavaScript, you should increment the count fields … if you are using JavaScript to allow deletion of existing objects, then you need to ensure the ones being removed are properly marked for deletion by including `form-#-DELETE` in the POST data." `can_order`/`can_delete` add `-ORDER`/`-DELETE` fields. `absolute_max` defaults to `max_num + 1000`. `empty_form` "returns a form instance with a prefix of `__prefix__` for easier use in dynamic forms with JavaScript" — [Django formsets.txt](https://github.com/django/django/blob/main/docs/topics/forms/formsets.txt)
- Verified locally with `formset_factory(AddressForm, extra=1, can_delete=True, can_order=True)` and `prefix="addresses"`:
  - The management form renders 4 hidden inputs (`addresses-TOTAL_FORMS` … `addresses-MAX_NUM_FORMS` value 1000).
  - `empty_form` names are `addresses-__prefix__-street`, `…-zip`, `…-ORDER` and `…-DELETE`.
  - Posting without the management form gives the non-form error "ManagementForm data is missing or has been tampered with. Missing fields: addresses-TOTAL_FORMS, addresses-INITIAL_FORMS…".
  - With 2 forms where form 1 is marked DELETE, `formset.errors` had only one entry (`[{'street': [...]}]`). Deleted forms are skipped in the errors list, so error indices don't necessarily match form indices.
  
  — [PyPI Django](https://pypi.org/project/Django/) (verified locally)
- Django has no built-in nested formsets. The third-party `nested-formset` repo (archived 2019) provided `nestedformset_factory` — [nyergler/nested-formset](https://github.com/nyergler/nested-formset)
- django-formset (jrief) "handles single forms and collections of forms" with a JSON payload, where "collections of forms are represented by nested data structures" and can nest, plus renderers for Bootstrap 5, Bulma, Foundation 6, Tailwind and UIkit (`{% render_form form "tailwind" %}`) — [PyPI django-formset](https://pypi.org/project/django-formset/), [jrief/django-formset](https://github.com/jrief/django-formset)

**django-formtools (wizards)**
- `SessionWizardView`/`CookieWizardView` split forms across pages, store step state in the session or a cookie, and require `done(form_list, form_dict, **kwargs)`. Conditional steps use `condition_dict={'cc': pay_by_credit_card}` (callables receive the wizard) — [django-formtools wizard.rst](https://github.com/jazzband/django-formtools/blob/master/docs/wizard.rst)

**Styling layer: crispy-forms vs widget-tweaks**
- crispy-forms `FormHelper` + `Layout` objects (`Fieldset`, `Div`, `MultiField`, `HTML`, `Field('x', css_class=…, data_name=…)`, `Submit`), rendered with `{% crispy example_form %}`. Template packs are chosen by `CRISPY_TEMPLATE_PACK`, and Bootstrap 5 lives in the separate `crispy-bootstrap5` package — [crispy layouts.rst](https://github.com/django-crispy-forms/django-crispy-forms/blob/main/docs/layouts.rst), [crispy README](https://github.com/django-crispy-forms/django-crispy-forms)
  ```python
  self.helper = FormHelper()
  self.helper.layout = Layout(
      Fieldset('Tell us your favorite stuff {{ username }}',
               'like_website', 'favorite_number', HTML("<p>…</p>"), 'notes'),
      Submit('submit', 'Submit', css_class='button white'),
  )
  ```
- django-widget-tweaks works on the template side: `{% render_field form.title class+="css_class_1 css_class_2" %}`, `{% render_field form.text rows="20" placeholder=form.text.label %}`, plus filters like `add_class` and `attr` — [django-widget-tweaks README](https://github.com/jazzband/django-widget-tweaks)
- Critique (from search-result summaries only; I couldn't fetch the page): crispy layouts put "frontend specific information on *.py files"; crispy-tailwind customization is "not easy and sometimes very tricky", so many developers use widget-tweaks for Tailwind classes instead. The author promotes django-formify as an alternative — [SaaS Hammer: Render Django Form with Tailwind CSS Style](https://saashammer.com/blog/render-django-form-with-tailwind-css-style/), [Django Forum: django-formify](https://forum.djangoproject.com/t/django-formify-a-django-form-rendering-package-for-tailwind-css-enthusiasts/34904)
- A crispy-forms issue reports widget template overrides being ignored under crispy while they work in plain Django — [crispy-forms#806](https://github.com/django-crispy-forms/django-crispy-forms/issues/806)

**Django in reactive contexts**
- django-unicorn reuses Django forms for reactive validation: `class Meta: form_class = BookForm` on a `UnicornView`, inputs bound with `unicorn:model="title"`, and a `$validate` magic action (also callable in Python) — [django-unicorn validation.md](https://github.com/adamghill/django-unicorn/blob/main/docs/source/validation.md)

### Inferences
- Django's error object, with a message plus a machine `code` per error and `__all__` for form-level errors, is the shape pyview should expose. Pydantic's `type` maps to `code` and `loc=()` (or a model_validator error) maps to `__all__`.
- The 5.0 "field group" idea (one call renders label + control + help + errors + ARIA ids) combined with 5.2's override points (project / form / field) is the right granularity for customization. `bound_field_class` shows that users want a per-field presenter object they can subclass rather than more template flags.
- Formsets show what happens when a stateless server has to infer list shape from POST data: a management form, `__prefix__` cloning in JS, and DELETE flags. A LiveView server has persistent state and doesn't need any of that. Add, remove and reorder should be events that mutate the params and data.
- The crispy vs. widget-tweaks split points to a design where default rendering is component and template based and overridable at every level, with an escape hatch to raw attributes (`name`, `id`, `value`, `errors`, ARIA ids) so users can hand-write markup.

### Gaps
- I couldn't access Django Forum threads or HN for first-hand developer opinions (blocked). The crispy critique is from search snippets.
- I didn't check whether Django 6.x added anything specific to nested or JSON forms. The 6.0/6.1 release notes list nothing like that.

---

## 3. Pydantic as the validation engine: error structure, `loc` mapping, partial validation, `model_construct`, discriminated unions, UI hints via `json_schema_extra` / `Annotated`, form-string coercion

### Takeaway
Pydantic v2 already provides most of the engine a form library needs: structured errors (`type`, `loc`, `msg`, `input`, `ctx`) with tuple paths such as `('addresses', 0, 'street')`, message customization by error `type` plus `ctx`, arbitrary `Annotated` metadata kept on `FieldInfo.metadata`, and lax coercion that accepts `"on"` for bools. The gaps a form layer has to fill are HTML-specific: `""` for optional non-string fields fails, absent checkboxes, discriminator tags inside `loc`, no built-in i18n, and partial validation that is experimental and TypeAdapter-only.

### Cited Findings
- Versions: pydantic 2.13.5 (2026-08-28), pydantic-core 2.49.0 (2026-09-09) — [PyPI pydantic](https://pypi.org/project/pydantic/)
- `ValidationError.errors()` returns `ErrorDetails` dicts with `ctx` ("values required to render the error message"), `input`, `loc` ("The error's location as a list"), `msg`, `type` ("computer-readable identifier") and `url`. "The first item in the loc list will be the field where the error occurred, and if the field is a sub-model, subsequent items will be present to indicate the nested location." Validators should raise `ValueError`/`AssertionError`, not `ValidationError` — [pydantic errors.md](https://github.com/pydantic/pydantic/blob/main/docs/errors/errors.md)
  ```python
  {'type': 'greater_than', 'loc': ('gt_int',), 'msg': 'Input should be greater than 42',
   'input': 21, 'ctx': {'gt': 42}, 'url': 'https://errors.pydantic.dev/2/v/greater_than'}
  {'type': 'int_parsing', 'loc': ('list_of_ints', 2), 'msg': 'Input should be a valid integer, …', 'input': 'bad'}
  ```
- Official pattern for custom or translated messages is to map `error['type']` to a template and format it with `ctx` — [pydantic errors.md](https://github.com/pydantic/pydantic/blob/main/docs/errors/errors.md)
  ```python
  CUSTOM_MESSAGES = {
      'int_parsing': 'This is not an integer! 🤦',
      'url_scheme': 'Hey, use the right URL scheme! I wanted {expected_schemes}.',
  }
  for error in e.errors():
      if custom := CUSTOM_MESSAGES.get(error['type']):
          ctx = error.get('ctx')
          error['msg'] = custom.format(**ctx) if ctx else custom
  ```
- i18n: pydantic has no built-in message translation. The third-party `pydantic-i18n` (0.4.5, last release 2024-09-22) is "an extension to support an i18n for the pydantic error messages" — [PyPI pydantic-i18n](https://pypi.org/project/pydantic-i18n/)
- Verified locally (pydantic 2.13.5) with nested list + discriminated union:
  ```
  (('addresses', 0, 'street'), 'string_too_short', 'String should have at least 1 character', {'min_length': 1})
  (('addresses', 1, 'street'), 'missing', 'Field required', None)
  (('payment', 'bank', 'iban'), 'missing', 'Field required', None)   # <- 'bank' is the union TAG, not a field
  ```
  — [PyPI pydantic](https://pypi.org/project/pydantic/) (verified locally)
- Discriminated unions: `pet: Cat | Dog | Lizard = Field(discriminator='pet_type')`, where each member has `pet_type: Literal[...]`. The error path includes the tag (`pet.dog.barks  Field required`). Callable `Discriminator(..., custom_error_type=…, custom_error_message=…)` with `Tag('...')` gives simpler errors than plain unions ("Errors are much simpler with a discriminated union") — [pydantic unions.md](https://github.com/pydantic/pydantic/blob/main/docs/concepts/unions.md)
- Partial validation: added in v2.10 and marked experimental ("should be considered a proof of concept"). `experimental_allow_partial` is accepted only on `TypeAdapter.validate_json/validate_python/validate_strings` ("not yet supported via other Pydantic entry points like BaseModel"). Supported types are `list`, `set`, `frozenset`, `dict` and `TypedDict` (only non-required fields may be missing). It "will ignore ALL errors in the last element of the input". The primary motivation is streaming LLM output — [pydantic experimental.md](https://github.com/pydantic/pydantic/blob/main/docs/concepts/experimental.md)
- `model_construct()` "Creates models without running validation … this includes converting dictionaries to model instances". Pydantic warns to "only ever use `model_construct()` with data which has already been validated". Verified locally: `Person.model_construct(name=5, addresses=[{"street": ""}])` keeps `name=5` and `addresses[0]` as a `dict` — [pydantic models.md](https://github.com/pydantic/pydantic/blob/main/docs/concepts/models.md) (verified locally)
- `json_schema_extra` on `Field(...)` or `model_config` merges arbitrary keys into the JSON schema, e.g. `Field(json_schema_extra={'title': 'Password', 'description': ..., 'examples': [...]})` — [pydantic json_schema.md](https://github.com/pydantic/pydantic/blob/main/docs/concepts/json_schema.md)
- Verified locally: `bio: Annotated[str, Widget("textarea"), Field(max_length=10)]` gives `Person.model_fields['bio'].metadata == [Widget(kind='textarea'), MaxLen(max_length=10)]`, and the custom `Widget` object doesn't appear in `model_json_schema()` (`{'default': '', 'maxLength': 10, 'title': 'Bio', 'type': 'string'}`). Arbitrary UI-hint objects in `Annotated` are kept and introspectable without polluting the schema — [PyPI pydantic](https://pypi.org/project/pydantic/) (verified locally)
- Verified locally, form-string coercion in lax mode:
  - `"on"`, `"yes"`, `"1"` and `"true"` become `True`; `"off"` becomes `False`; `"checked"` gives `bool_parsing`.
  - A required `bool` with the key absent gives `missing`.
  - `age: int | None = None` with `""` gives `int_parsing`, and `when: date | None` with `""` gives `date_from_datetime_parsing`.
  - `nick: str | None` with `""` stays `''` (not `None`).
  - A reusable `BeforeValidator(lambda v: None if v == "" else v)` in `Annotated[int | None, Blank]` fixes this.
  
  — [PyPI pydantic](https://pypi.org/project/pydantic/) (verified locally)

### Inferences
- **Error mapping rule**: `loc` → HTML name is a pure function (`('addresses', 0, 'street')` → `addresses[0][street]` or `addresses.0.street`), except that for discriminated unions the tag segment has to be dropped. The form layer can detect it by walking the model's annotations alongside `loc`, since pydantic doesn't mark which segments are tags.
- **Error i18n / customization**: key messages on `(type, ctx)`, optionally overridden per field or per model. This matches pydantic's own recommended pattern and avoids re-implementing validators.
- **Empty-string policy** has to be a first-class decision in the decoder: `""` → `None` for non-`str` optionals (and maybe for `str | None` too). FastUI chose to drop `""` entirely (Q4). Doing it in the decoder, type-directed from annotations, is cleaner than asking users to write `BeforeValidator`s.
- **"Partial" / live validation**: pydantic's partial mode isn't a fit (TypeAdapter-only, experimental, built for truncated JSON). The practical approach for live (`phx-change`-style) validation is to validate the whole model on every change and hide errors for fields the user hasn't touched yet.
- **UI hints**: `Annotated[str, Textarea(rows=5)]`-style metadata objects are the cleanest channel (typed, kept on `FieldInfo.metadata`, invisible to JSON schema). `json_schema_extra` works too, and FastUI used it, but it leaks UI concerns into API schemas.
- `model_construct` is useful for building a "draft" object to render when validation fails, but nested dicts stay dicts, so templates must handle both.

### Gaps
- I didn't benchmark validation cost of re-validating a whole model on each keystroke, though pydantic v2 is Rust-backed.
- I didn't check whether pydantic has shipped (or plans) a way to flag discriminator tags in `loc`.

---

## 4. Pydantic/dataclass-native form & UI libraries: FastAPI Form models, FastUI, FastHTML, fh-pydantic-form, streamlit-pydantic, NiceGUI, Reflex, pydantic-forms, Litestar

### Takeaway
Many projects have tried "here's my pydantic class, do the rest", but none is both server-rendered HTML and complete for nested lists. FastAPI's `Form()` models are flat-only. FastUI (JSON schema → React) is archived and never supported arrays of objects in forms. FastHTML gives flat `form2dict`/`fill_form` helpers with no error story. **fh-pydantic-form** (FastHTML + HTMX) is the closest prior art to pyview's goal, with nested models, lists with add/delete/reorder, and a custom renderer registry. The rest are app-framework widget generators (Streamlit, NiceGUI add-ons) or JSON-schema/React bridges.

### Cited Findings

**FastAPI Form models**
- "This is supported since FastAPI version `0.113.0`." Forbidding extra fields is "supported since FastAPI version `0.114.0`" via `model_config = {"extra": "forbid"}`, which gives an `extra_forbidden` error with `loc: ["body", "extra"]`. It requires `python-multipart` — [FastAPI request-form-models.md](https://github.com/fastapi/fastapi/blob/master/docs/en/docs/tutorial/request-form-models.md), [FastAPI release notes](https://github.com/fastapi/fastapi/blob/master/docs/en/docs/release-notes.md)
  ```python
  class FormData(BaseModel):
      username: str
      password: str

  @app.post("/login/")
  async def login(data: Annotated[FormData, Form()]):
      return data
  ```
- Verified locally (FastAPI 0.142.2):
  - `tags: list[str]` from repeated keys works (`['x','y']`), and `agree: bool = False` with `"on"` gives `True`.
  - `age: int | None = None` with `""` returns 422 `int_parsing` at `['body','age']`.
  - A nested `addr: Addr | None` sent as `addr.street=s` is silently ignored (`addr: None`), and sending it as a JSON string gives 422 `model_attributes_type`. Nested models aren't supported in form bodies.
  
  — [PyPI fastapi](https://pypi.org/project/fastapi/) (verified locally)

**FastUI (pydantic team) — INACTIVE / ARCHIVED**
- The README says: "NOTE: this project is inactive, see #368". The repo was "archived by the owner on Jun 7, 2026". The last PyPI release is 0.9.0 (2025-10-28) — [pydantic/FastUI](https://github.com/pydantic/FastUI), [PyPI fastui](https://pypi.org/project/fastui/)
- Issue #368 (Samuel Colvin, 2024-11-21): "this project is on hold while the Pydantic team is flat out building logfire and continuing to maintain Pydantic", and "I would really like the rendering of HTML in FastUI to happen exclusively (or mostly) serverside, but that's a big rewrite that I don't have time to work on right now." Other reasons given: Logfire lacked enough CRUD to justify it, the frontend team wasn't convinced, and it needed complex generic-union support — [FastUI#368](https://github.com/pydantic/FastUI/issues/368)
- Architecture: Python endpoints return a JSON component tree and a React frontend renders it. Forms come from `c.ModelForm(model=LoginForm, display_mode='page', submit_url='/api/forms/login')`, and the POST handler validates with the `fastui_form(Model)` dependency — [FastUI demo/forms.py](https://github.com/pydantic/FastUI/blob/main/demo/forms.py)
  ```python
  class BigModel(BaseModel):
      info: Annotated[str | None, Textarea(rows=5)] = Field(None, description='Optional free text…')
      repo: str = Field(json_schema_extra={'placeholder': '{org}/{repo}'}, title='GitHub repository')
      profile_pic: Annotated[UploadFile, FormFile(accept='image/*', max_size=16_000)]
      human: bool | None = Field(None, title='Is human', json_schema_extra={'mode': 'switch'})
      size: SizeModel                       # nested model → inlined fields
      position: tuple[Annotated[int, Field(description='X')], Annotated[int, Field(description='Y')]]

  @router.post('/big')
  async def big_form_post(form: Annotated[BigModel, fastui_form(BigModel)]): ...
  ```
- Its form pipeline: `model.model_json_schema()` → `model_json_schema_to_fields()` → typed `FormField*` components. `Textarea()` is just `pydantic.Field(json_schema_extra={'format': 'textarea', 'rows': rows, 'cols': cols})`. Input names come from `loc_to_name`: dot-joined, or JSON-encoded if any segment contains `.`. For arrays, fixed-length tuples are inlined, and otherwise it does `raise NotImplementedError('Array fields are not fully supported, see https://github.com/pydantic/FastUI/pull/52')` — [FastUI json_schema.py](https://github.com/pydantic/FastUI/blob/main/src/python-fastui/fastui/json_schema.py)
- Submission: `unflatten(form_data)` groups multi-items, splits names on `.` (digits become ints), turns dicts whose keys are all ints into lists, and "Also omit[s] empty strings, this might be a bit controversial, but it helps in many scenarios, e.g. a select which hasn't been updated". On `ValidationError` it raises 422 with `{'form': e.errors(include_input=False, include_url=False, include_context=False)}`. `FormFile` validates uploads through `__get_pydantic_core_schema__` and raises `PydanticCustomError('file_too_big', 'File size was {file_size}, exceeding maximum allowed size of {max_size}', {...})` — [FastUI forms.py](https://github.com/pydantic/FastUI/blob/main/src/python-fastui/fastui/forms.py)

**FastHTML (AnswerDotAI)**
- `python-fasthtml` 0.14.13 (2026-09-03), classified Alpha — [PyPI python-fasthtml](https://pypi.org/project/python-fasthtml/)
- `form2dict(form)` builds `{k: _formitem(form, k)}`, where `_formitem` returns "single item `k` from `form` if len 1, otherwise return list". A handler parameter annotated with a dataclass/class is built as `anno(**cargs)`, with each value cast by the annotation of the same name (`_form_arg`). There is no nested-name decoding — [fasthtml/core.py](https://github.com/AnswerDotAI/fasthtml/blob/main/fasthtml/core.py)
- `fill_form(form, obj)` accepts a dataclass (via `asdict`), a dict or an object's `__dict__`. It walks the FT (HTML component) tree and sets `value` on inputs, `checked` on checkboxes (bool, or membership when the value is a list), `checked` on radios by equality, textarea children, and `selected` on `<option>` (a list for multi-select). `fill_dataclass(src, dest)` copies fields — [fasthtml/components.py](https://github.com/AnswerDotAI/fasthtml/blob/main/fasthtml/components.py)

**fh-pydantic-form (FastHTML + HTMX + MonsterUI)**
- 0.3.18 (2026-01-21), by Marcura. It covers "Automatically render form inputs … based on Pydantic field types", "Support for nested Pydantic models and lists of models/simple types with accordion UI", "Built-in HTMX endpoints and JavaScript for adding, deleting, and reordering items in lists", and custom renderers. Nested prefixes are auto-managed (e.g. `user_address_street`). `SkipJsonSchema[...]` fields are hidden by default, and excluded fields get defaults injected at parse time — [PyPI fh-pydantic-form](https://pypi.org/project/fh-pydantic-form/), [Marcura/fh-pydantic-form](https://github.com/Marcura/fh-pydantic-form)
  ```python
  form_renderer = PydanticForm("my_form", SimpleModel)
  form_renderer.register_routes(app)          # list add/delete routes
  mui.Form(form_renderer.render_inputs(), ..., hx_post="/submit_form", id=f"{form_renderer.name}-form")

  @rt("/submit_form")
  async def post_submit_form(req):
      try:
          validated: SimpleModel = await form_renderer.model_validate_request(req)
      except ValidationError as e:
          return fh.Pre(e.json(indent=2))     # README example just dumps errors
  # custom renderers
  FieldRendererRegistry.register_type_renderer(CustomDetail, CustomDetailFieldRenderer)
  # also: register_type_name_renderer("CustomDetail", ...), register_type_renderer_with_predicate(lambda field: ..., ...)
  ```

**streamlit-pydantic**
- "Auto-generate Streamlit UI from Pydantic Models & Dataclasses" with `data = sp.pydantic_form(key="my_form", model=ExampleModel)`, plus `sp.pydantic_input`/`sp.pydantic_output`. It supports nested models. The last release is 0.6.0 (2023-03-29) — [streamlit-pydantic README](https://github.com/lukasmasuch/streamlit-pydantic), [PyPI streamlit-pydantic](https://pypi.org/project/streamlit-pydantic/)

**NiceGUI**
- NiceGUI 3.17.1 (2026-09-18) has no built-in pydantic form element. The request is tracked in discussion #378 ("Add a jsonschema/pydantic based forms element"). Third-party options are **niceview** ("deriving forms and tables from Pydantic or SqlModel models … validation against the model, shown inline at the field it belongs to and including cross-field rules") and **nicecrud** — [NiceGUI discussion #378](https://github.com/zauberzeug/nicegui/discussions/378), [clausgf/niceview](https://github.com/clausgf/niceview), [Dronakurl/nicecrud](https://github.com/Dronakurl/nicecrud)

**Reflex**
- `rx.form` `on_submit` delivers form data as a dict keyed by control `name` (optionally typed with a TypedDict) — [Reflex form docs](https://reflex.dev/docs/library/forms/form/)
- Bug #7342 (filed 2026-09-28, open): "only the _last_ checked value reaches the `on_submit` handler's `form_data`", because `Object.fromEntries(new FormData($form).entries())` keeps only the last pair for a duplicate key — [reflex#7342](https://github.com/reflex-dev/reflex/issues/7342)

**pydantic-forms (workfloworchestrator)**
- 2.6.0 (2026-08-04): "Forms will respond with a JSON scheme that contains all info needed in a React frontend with uniforms to render the forms and handle all validation tasks. Forms can also consist out of a wizard". Supports FastAPI and Flask — [workfloworchestrator/pydantic-forms](https://github.com/workfloworchestrator/pydantic-forms)

**Litestar**
- `URLEncodedBody[T]` / `MultipartBody[T]` are shorthands for `Annotated[T, Body(media_type=RequestEncodingType.URL_ENCODED|MULTI_PART)]`. The docs caution that "URL encoded data is inherently less versatile than JSON data - for example, it cannot handle complex dictionaries and deeply nested data" — [Litestar requests.rst](https://github.com/litestar-org/litestar/blob/main/docs/usage/requests.rst)

### Inferences
- **No one has shipped the pyview target** (server-rendered, pydantic-first, nested + lists + live validation + good error UX). fh-pydantic-form is the closest and worth studying for renderer registry design and list UX. FastUI's JSON-schema route stalled exactly on lists of objects, which suggests generating from the **Python type annotations / `model_fields`** rather than from JSON schema. JSON schema loses `Annotated` metadata (see Q3) and makes `$ref`/`anyOf` resolution painful.
- A frequent failure mode is the naive `dict(form)` conversion that loses repeated keys (Reflex #7342, and the scalar-vs-list ambiguity in FastHTML's `_formitem`). Decoding has to be **type-directed**: `list[str]` should always yield a list, even with one or zero values.
- FastAPI Form models are only a transport shim (flat, no errors-to-HTML rendering). Pyview can accept the same `Annotated[Model, Form()]`-style ergonomics but has to add nested decoding and rendering itself.

### Gaps
- Gradio and Flet weren't researched in depth. They're component or app frameworks without an established pydantic-model-to-form feature as far as I found, but that's unverified.
- I didn't read fh-pydantic-form's source for its exact list-index naming or error-rendering internals. The README example only dumps `e.json()`.
- I couldn't confirm whether FastAPI has an open plan for nested form models.

---

## 5. Other relevant: marshmallow, attrs/cattrs, msgspec, dataclasses; htmx form patterns

### Takeaway
The alternative validators all produce path-addressable errors, in very different shapes: marshmallow gives nested dicts with int keys, cattrs gives string paths like `$.a[0].b` via `transform_error`, and msgspec gives a single string that stops at the first error. Pydantic's structured, all-errors, tuple-`loc` output is the best fit for per-field form errors. The htmx literature adds UX rules (don't clobber input, don't nag while typing) that apply directly to a LiveView form layer.

### Cited Findings
- Verified locally, same invalid nested payload:
  - **marshmallow 4.3.1** `e.messages`: `{'name': ['Shorter than minimum length 1.'], 'addresses': {0: {'street': ['Missing data for required field.'], 'zip': ['Not a valid integer.']}}}` (nested dict, int keys for list indices).
  - **msgspec 0.22.0** `str(e)`: `'Expected `int`, got `str` - at `$.addresses[0].zip`'` (one error only, the first found, with a JSON-path string).
  - **cattrs 26.2.1** with `Converter(detailed_validation=True)` + `transform_error(e)`: `['invalid value for type, expected int @ $.addresses[0].zip', 'required field missing @ $.addresses[1].street']` (all errors, as strings).
  
  — [PyPI marshmallow](https://pypi.org/project/marshmallow/), [PyPI msgspec](https://pypi.org/project/msgspec/), [PyPI cattrs](https://pypi.org/project/cattrs/) (verified locally)
- htmx + Django form validation (spookylukey's django-htmx-patterns) lists these requirements: "We must never overwrite what the user has inputted with some earlier state or blank state", "We mustn't interrupt the user or start showing validation errors while they are still entering data", don't break keyboard or focus behaviour, handle checkbox-label focus quirks, and handle mobile. "Earlier versions of these docs had subtle bugs with all the above! And this version still has potential bugs!" It also advises: "If you can lean on HTML, do so!" (use `required`, `pattern` and similar via field args and widgets) — [django-htmx-patterns form_validation.rst](https://github.com/spookylukey/django-htmx-patterns/blob/master/form_validation.rst)
- django-htmx 1.29.0 (2026-08-05) and django-template-partials 25.3 (partials were merged into Django 6.0 core). jinja2-fragments 1.12.0 renders Jinja blocks as fragments — [PyPI django-htmx](https://pypi.org/project/django-htmx/), [Django 6.0 notes](https://github.com/django/django/blob/main/docs/releases/6.0.txt), [PyPI jinja2-fragments](https://pypi.org/project/jinja2-fragments/)

### Inferences
- If pyview supports non-pydantic backends (dataclasses via pydantic's dataclass support, attrs via cattrs), it should normalize every backend's errors to one internal `(path tuple, code, message, ctx)` shape. msgspec's fail-fast behaviour makes it a poor form validator.
- LiveView already solves "never overwrite user input" by morphing DOM around focused inputs. The "don't show errors before the user finished" rule should become a built-in "touched/used field" mechanism rather than something users hand-roll.

### Gaps
- I didn't research dataclasses + `field(metadata=...)` form generators specifically. `dataclasses.field(metadata=)` is a standard mapping, but I found no notable form library built on it beyond FastHTML's dataclass binding and streamlit-pydantic's dataclass support.
- I didn't research django-components' form handling.

---

## 6. Parsing nested HTML form data into nested dicts (lists, checkboxes, multi-selects, empty strings)

### Takeaway
Python has no single standard for nested form names. There are four conventions: WTForms/Django `prefix-0-field` (library-specific), formencode's `a.b-3` (with `--repetitions`), Rails/PHP-style brackets `a[b][0][c]` (querystring-parser, old and stale), and FastUI's dot-path (or JSON-encoded) names. All of them have to deal with the same HTML facts: unchecked checkboxes and empty multi-selects are absent, repeated keys mean lists, everything is a string, and `""` is ambiguous.

### Cited Findings
- **formencode `variable_decode`**: "Keys … can have subkeys, with a `.` and can be numbered with `-`, like `a.b-3=something` means that the value `a` is a dictionary with a key `b`, and `b` is a list … Numbers are used to sort, missing numbers are ignored." It "doesn't deal with multiple keys, like in a query string of `id=10&id=20`". `dict_char`/`list_char` are configurable — [formencode variabledecode.py](https://github.com/formencode/formencode/blob/main/src/formencode/variabledecode.py)
  - Verified locally: `{"addresses-0.street":"s0","addresses-0.zip":"z0","addresses-2.street":"s2","tags-0":"x","tags-1":"y"}` gives `{'addresses': [{'street':'s0','zip':'z0'}, {'street':'s2'}], 'tags': ['x','y']}`, so the gap at index 1 is compacted. `variable_encode` emits `person.addresses--repetitions: '1'` counters. formencode 2.1.1 was released 2025-01-31 — [PyPI FormEncode](https://pypi.org/project/FormEncode/) (verified locally)
- **querystring-parser** (Rails/PHP brackets): 1.2.4, last release 2020-10-21. Verified locally, `person[addresses][0][street]=s0&person[addresses][1][street]=s1&tags[]=x&tags[]=y` gives `{'person': {'name': 'a', 'addresses': {0: {...}, 1: {...}}}, 'tags': {'': ['x','y']}}`. Indices become dict int-keys, not lists, and `tags[]` becomes a `''` key — [PyPI querystring-parser](https://pypi.org/project/querystring-parser/) (verified locally)
- **FastUI `unflatten`**: splits names on `.` (or parses a JSON-array name), turns all-int-key dicts into sorted lists, keeps repeated keys as lists, and drops `''` values entirely — [FastUI forms.py](https://github.com/pydantic/FastUI/blob/main/src/python-fastui/fastui/forms.py)
- **WTForms**: `-` separator (`FormField(..., separator='-')`, `FieldList(..., separator='-')`) and index discovery by key scan — [wtforms/fields/list.py](https://github.com/pallets-eco/wtforms/blob/main/src/wtforms/fields/list.py)
- **Django formsets**: `{prefix}-{i}-{field}` plus the management form's `TOTAL_FORMS`/`INITIAL_FORMS` — [Django formsets.txt](https://github.com/django/django/blob/main/docs/topics/forms/formsets.txt)
- **Checkbox and multi-select absence** is documented by Django ("an unchecked checkbox and unselected `<select multiple>` don't appear in the data of an HTML form submission") — [Django widgets.txt](https://github.com/django/django/blob/main/docs/ref/forms/widgets.txt). WTForms disallows `BooleanField` inside `FieldList` for this reason — [WTForms fields.rst](https://github.com/pallets-eco/wtforms/blob/main/docs/fields.rst)
- **Repeated keys**: FastAPI maps repeated keys into `list[str]` by type (verified locally). FastHTML returns a scalar when there's one value and a list otherwise (`_formitem`). Reflex's `Object.fromEntries` drops all but the last — [fasthtml/core.py](https://github.com/AnswerDotAI/fasthtml/blob/main/fasthtml/core.py), [reflex#7342](https://github.com/reflex-dev/reflex/issues/7342)
- **Empty strings**: Django sets per-field `empty_value` (`""` for CharField, `None` for Date/Integer and similar). FastUI drops `""`. Pydantic rejects `""` for `int | None` and `date | None` (verified locally) — [Django fields.txt](https://github.com/django/django/blob/main/docs/ref/forms/fields.txt), [FastUI forms.py](https://github.com/pydantic/FastUI/blob/main/src/python-fastui/fastui/forms.py)

### Inferences
- For pyview (a Phoenix LiveView clone), **Rails/Phoenix-style bracket names** (`person[addresses][0][street]`) are the natural wire format. Phoenix clients and `phx-change` payloads already use them, and they map 1:1 to pydantic `loc` tuples. The decoder should be **schema-aware**: walk `model_fields` so that
  (a) int-keyed dicts become lists when the annotation is `list[...]`, with sparse indices compacted or sorted;
  (b) `list[str]`/`set[...]` fields always yield lists, even with one or zero values;
  (c) an absent `bool` becomes `False` when the field is rendered as a checkbox (or the renderer emits a hidden `name=false` input before the checkbox — a common Rails/Phoenix trick, not verified in the sources here);
  (d) `""` becomes `None` for non-`str` optionals, with a configurable policy for `str | None`;
  (e) discriminated-union tags are handled when mapping errors back.
- Avoid formencode's `--repetitions` and Django's `TOTAL_FORMS` counters. With server-held LiveView state they add nothing.

### Gaps
- I didn't survey every Python bracket parser (e.g. Werkzeug has no nested parser; other small PyPI packages exist). querystring-parser was the only one tested.
- The Phoenix wire-format details (e.g. `_unused_` / `_persistent_id` params, `sort_param`/`drop_param` for inputs_for) belong to the Phoenix researcher and aren't covered here.

---

## 7. Consensus pain points & cross-cutting design lessons (boilerplate duplication, error display, i18n, rendering customization vs. control, dynamic lists)

### Takeaway
The pain points are consistent across ecosystems: (1) the form class duplicates the model (solved only for ORM models by ModelForm or wtforms-alchemy, and only partially by pydantic-first tools); (2) dynamic and nested lists are awkward everywhere (FieldList, formsets, FastUI NotImplemented, Reflex dropping repeated keys); (3) rendering is either too magic to style (crispy) or too manual (widget-tweaks, hand-written templates). Django 5.x's field groups plus overridable renderers is the current best compromise. (4) i18n of messages is left to the user (WTForms, pydantic).

### Cited Findings
- Duplication: ModelForm (`class Meta: model = Article; fields = [...]`) exists to avoid redefining fields. For pydantic, FastUI, fh-pydantic-form and streamlit-pydantic all market "reduce boilerplate" by generating forms from the model — [Django modelforms.txt](https://github.com/django/django/blob/main/docs/topics/forms/modelforms.txt), [PyPI fh-pydantic-form](https://pypi.org/project/fh-pydantic-form/), [streamlit-pydantic README](https://github.com/lukasmasuch/streamlit-pydantic). A blog post (seen via search only) notes it is "not practical to build a new Form object out of every single Pydantic model", which motivated exporting pydantic models as Django forms — [levelup.gitconnected: How to Export Pydantic Models as Django Forms](https://levelup.gitconnected.com/how-to-export-pydantic-models-as-django-forms-c1b59ddca580)
- Dynamic lists: WTForms #256 (arbitrary delete), the FieldList + BooleanField limitation, Django's management-form and `empty_form` JS cloning, FastUI's `NotImplementedError('Array fields are not fully supported')`, and Reflex #7342 — [wtforms#256](https://github.com/wtforms/wtforms/issues/256), [Django formsets.txt](https://github.com/django/django/blob/main/docs/topics/forms/formsets.txt), [FastUI json_schema.py](https://github.com/pydantic/FastUI/blob/main/src/python-fastui/fastui/json_schema.py), [reflex#7342](https://github.com/reflex-dev/reflex/issues/7342)
- Rendering control: crispy's Python-side `Layout` vs widget-tweaks' template-side `render_field`. Django 5.0 answered the "15 lines of boilerplate per field" problem with `as_field_group`, and 5.2 made the BoundField class swappable — [crispy layouts.rst](https://github.com/django-crispy-forms/django-crispy-forms/blob/main/docs/layouts.rst), [django-widget-tweaks](https://github.com/jazzband/django-widget-tweaks), [Django 5.0 notes](https://github.com/django/django/blob/main/docs/releases/5.0.txt), [Django 5.2 notes](https://github.com/django/django/blob/main/docs/releases/5.2.txt)
- Accessibility is now expected: Django 4.1–5.2 changed defaults to div/fieldset/legend, `aria-describedby` (help and errors) and `aria-invalid` — [Django 4.1 notes](https://github.com/django/django/blob/main/docs/releases/4.1.txt), [Django 5.0 notes](https://github.com/django/django/blob/main/docs/releases/5.0.txt), [Django 5.2 notes](https://github.com/django/django/blob/main/docs/releases/5.2.txt)
- i18n: "WTForms does -not- translate any user-provided strings". Pydantic offers a type→message mapping recipe and a third-party pydantic-i18n — [WTForms i18n.rst](https://github.com/pallets-eco/wtforms/blob/main/docs/i18n.rst), [pydantic errors.md](https://github.com/pydantic/pydantic/blob/main/docs/errors/errors.md), [PyPI pydantic-i18n](https://pypi.org/project/pydantic-i18n/)
- Live validation UX is hard to get right (focus, don't nag, don't clobber input) — [django-htmx-patterns form_validation.rst](https://github.com/spookylukey/django-htmx-patterns/blob/master/form_validation.rst)
- JSON-schema-driven generation stalled: FastUI is archived and its author wanted server-side HTML rendering instead of React — [FastUI#368](https://github.com/pydantic/FastUI/issues/368)

### Inferences (design checklist for "here's my pydantic class, do the rest")
1. **Source of truth = the pydantic model**, introspected through `model_fields` and `FieldInfo` (`annotation`, `metadata`, `description`, `title`, `default`, `json_schema_extra`), not via JSON schema. UI hints go in `Annotated` metadata objects (`Annotated[str, Textarea(rows=5)]`, `Annotated[Role, RadioGroup()]`), with a registry keyed by type, name or predicate (fh-pydantic-form's model).
2. **A Form/Changeset object separate from the model**: holds `params` (raw strings as submitted, which is what gets re-rendered), `data`/`initial` (model instance or dict), `errors` (normalized from pydantic `(loc, type, msg, ctx)`), `touched`/used fields, and `valid`. This merges Django's `data`/`cleaned_data`/`errors`, WTForms' `raw_data`/`data`/`object_data`, and pydantic's `ValidationError`.
3. **Per-field accessor (BoundField equivalent)** exposing `name` (bracketed path), `id`, `value` (raw param if present, else the model value), `errors`, `label`, `help`, `required`, `aria` ids, and HTML constraint attrs derived from pydantic constraints (`max_length` → `maxlength`, `ge` → `min`, `pattern` → `pattern`, required → `required`), following "lean on HTML". Nested accessors for sub-models and lists (like Phoenix `inputs_for`, WTForms FormField iteration).
4. **Schema-aware decoder** for bracket names (see Q6), with an explicit policy for `""`, absent checkboxes, repeated keys and sparse indices.
5. **Rendering layers**: (a) raw field props for fully hand-written markup (widget-tweaks-level control); (b) a field-group component (label + input + help + errors + ARIA, Django 5.0-style) overridable per project, form or field (Django 5.2-style); (c) whole-form auto-render for scaffolding. Styling through swappable "themes" or template packs (crispy's one good idea), with Tailwind-friendly class hooks rather than Python-side layout DSLs.
6. **Lists and unions as server events**, not JS cloning or management forms: `add_item(path)`, `remove_item(path, idx)`, `move_item`. Discriminated unions render a selector bound to the discriminator and swap sub-fields. Error `loc` tags are stripped.
7. **Errors and i18n**: message catalog keyed by pydantic `type` + `ctx` (pydantic-recommended), overridable per field. Form-level errors (model validators, `loc == ()`) go in a `__all__`/`form_errors` slot, as in Django and WTForms.
8. **Don't rely on pydantic partial validation.** Validate the whole model on each change and show errors only for touched fields. Offer a "cross-field post-validation" hook (WTForms 3.3 added `post_process` for exactly this).

### Gaps
- Reddit, HN and Django Forum sentiment couldn't be read directly (egress-blocked). Pain-point evidence here is drawn from project docs, issues, source code and search-result summaries rather than broad community surveys.
- I found no quantitative data (surveys, download-trend analyses) comparing developer satisfaction across these libraries.
