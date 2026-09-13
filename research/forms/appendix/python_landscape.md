# Pydantic-adjacent and Python full-stack form handling: FastUI, streamlit-pydantic, FastAPI Form models, FastHTML, sqladmin/starlette-admin/flask-admin, marshmallow, Colander/Deform, DRF serializers + HTMLFormRenderer

Versions researched (installed from PyPI, 2026-09-12): fastui 0.9.0, streamlit-pydantic 0.6.0, python-fasthtml 0.14.13, fastapi 0.141.1, sqladmin 0.31.1, starlette-admin 1.0.1, flask-admin 2.2.0, marshmallow 4.3.1, colander 2.0, deform 3.0.1, peppercorn 0.6, djangorestframework 3.18.1. All code below was run against these packages unless marked (unverified).

## TL;DR

- Nobody in the Python ecosystem has solved "here is my Pydantic class, do the rest" for *nested* HTML forms. FastUI is the closest (pydantic JSON schema -> fields, `unflatten()` -> `model_validate`, errors returned as pydantic `loc` lists) but explicitly raises `NotImplementedError('Array fields are not fully supported')` for variable-length lists and non-optional unions.
- FastAPI's `Annotated[Model, Form()]` (0.113+) is flat by construction: it does `form[field_name]` per top-level field; a nested model cannot be sent from an HTML form at all (I sent `addr.city`, `addr[city]`, and a JSON string; the first two were silently dropped, the third got 422 `model_attributes_type`).
- Three incompatible name encodings for nesting exist: dotted with integer segments (`items.0.qty` -- FastUI, starlette-admin, DRF `parse_html_dict`), bracket-index (`items[0]qty` -- DRF `parse_html_list`), and marker tokens (`__start__`/`__end__` -- peppercorn/Deform). Rails/Phoenix `user[address][city]` is *not* used by any Python-native library, yet it is what Phoenix's `to_form`/`inputs_for` emit, so pyview needs its own decoder for it.
- Error models converge on "errors keyed by path": marshmallow returns a nested dict `{'items': {1: {'qty': [...]}}}`, Colander flattens to dotted keys `{'people.1.name': 'Required'}`, pydantic gives a `loc` tuple per error, starlette-admin `FormValidationError({"items": {0: {"sku": "msg"}}})`. The winner for templates is *path -> list[str]* with a helper that answers "errors at prefix X".
- Admin frameworks (sqladmin, flask-admin, starlette-admin) still generate forms from *ORM* metadata, not pydantic, and all use a `field.id` prefix plus an index discovered from submitted keys (`_extra_indices`) for dynamic lists; flask-admin's `InlineFieldList` uses `del-<id>` checkbox keys for deletion.
- The reusable recipe: schema -> field list (with loc) -> widget per field type -> HTML with name=loc_to_name(loc) -> submit -> unflatten by name_to_loc -> validate -> errors keyed by loc -> re-render with attempted values. Every library re-implements exactly this; the differences are which step they skip.
- Customization patterns that work: DRF's `style={'base_template': 'radio.html', 'template_pack': 'rest_framework/inline/'}` per field; marshmallow's `error_messages={'required': '...'}` per field; sqladmin's `form_args`/`form_widget_args`/`form_overrides` dicts; FastUI's `Field(json_schema_extra={...})`-style annotations (`Textarea(rows=...)`, `format: 'textarea'`).

## Mental model & core abstractions

**FastUI** (`fastui/forms.py`, `fastui/json_schema.py`): the model *is* the form. `c.ModelForm(model=MyModel, submit_url=...)` calls `model_json_schema_to_fields(model)` which walks pydantic's JSON schema (`json_schema_obj_to_fields` -> `json_schema_any_to_fields` -> `json_schema_field_to_field`), carrying a `loc: SchemeLocation` (list of str|int) and emitting `FormFieldInput|FormFieldBoolean|FormFieldSelect|FormFieldFile|FormFieldTextarea|FormFieldSelectSearch` objects whose `name = loc_to_name(loc)` (`'.'.join`, or JSON-encoded list if a key contains a dot). The server side is a FastAPI dependency, `fastui_form(Model)` / `FastUIForm[Model]`, that reads `request.form()`, `unflatten()`s it, and `model.model_validate()`s. `$ref` and `allOf` are dereferenced; `anyOf` is accepted only as `X | None` (`NotImplementedError` otherwise). `deference_json_schema` line 345.

**streamlit-pydantic**: `sp.pydantic_form(key, model, submit_label="Submit", clear_on_submit=False, group_optional_fields="no", lowercase_labels=False, ignore_empty_values=False) -> Optional[T]` and `sp.pydantic_input`. Internally `InputUI.render_ui()` walks `model.schema(by_alias=True)` and `_render_property` dispatches on `schema_utils.is_*` predicates in this order: single enum, multi enum, single file, multi file, datetime, color, boolean, dict, number, string, single object, object list, list, single reference, union; else `st.warning("The type of the following property is currently not supported")` + raise. Widget kwargs can be overridden per field via schema extras prefixed `st_kwargs_` (`_get_overwrite_streamlit_kwargs`). Values are stored in `st.session_state` keyed by dotted path; nested `BaseModel`s are rendered recursively (`_render_single_object_input`), lists get add/clear buttons (`_render_list_add_button`, `_render_list_clear_button`, `_render_list_item`), and unions get a selectbox over the `anyOf` members, using pydantic's `discriminator.propertyName` to pick the initial branch (`_render_union_property`). It still uses pydantic v1 API (`.schema()`, `parse_obj_as`); custom rendering is via a `render_input_ui(st, session_state)` classmethod on the model (`_has_input_ui_renderer`).

**FastAPI form models**: `Annotated[Model, Form()]`, since 0.113.0 (0.114.0 adds `model_config = {"extra": "forbid"}` support producing `{"type": "extra_forbidden"}` errors). Extraction is per top-level field name from Starlette `FormData` (`getlist` for sequence fields) -- there is no unflatten step. Note also that Starlette `FormData` is a `MultiDict` from `python-multipart`; everything is `str | UploadFile`.

**FastHTML** (`fasthtml/core.py`): no form object at all. A route `def create(todo: Todo)` where `Todo` is any class with annotations (dataclass, pydantic, plain class) triggers `_is_body(anno)` -> `_from_body(conn, p, data)`, which does `cargs = {k: _form_arg(k, v, d) for k, v in data.items() if not d or k in d}; return anno(**cargs)`. `_form_arg` -> `_fix_anno(t, o)` casts strings with the table `{bool: str2bool, int: str2int, date: str2date, UploadFile: noop}`, unwraps `X | None`, and turns `list[T]` into a mapped list (`_mk_list`). `form2dict`/`_formitem` collapse `getlist` results to a scalar when length 1. `fill_form(form: FT, obj)` walks an FT tree and sets `value`/`checked`/`selected` on inputs whose `name` matches keys (`_fill_item`); `fill_dataclass(src, dest)` copies attrs. Nested objects: none -- names are flat attribute names. Validation in `examples/adv_app.py` is manual: `def send_login(name:str, pwd:str, sess): if not name or not pwd: return login_redir`; missing required scalar params raise `HTTPException(400, "Missing required field: ...")` from `_find_p`.

**sqladmin** (`sqladmin/forms.py`): `async get_model_form(model, session_maker, only, exclude, column_labels, form_args, form_widget_args, form_class=Form, form_overrides, form_ajax_refs, form_include_pk, form_converter=ModelConverter) -> type[wtforms.Form]`. A `ModelView` sets `ClassVar`s: `form_columns`, `form_excluded_columns`, `form_base_class`, `form_args = {"name": {"validators": [...]}}`, `form_widget_args = {"name": {"readonly": True}}`, `form_overrides = {"name": wtf.FileField}`, `form_ajax_refs`. Relationships become select/multi-select via ajax loaders; no inline nested forms.

**starlette-admin** (`starlette_admin/fields.py`): explicit field objects in `ModelView.fields = [StringField("name"), ListField(CollectionField("items", fields=[StringField("sku"), IntegerField("qty")]))]`. Each `BaseField` has `parse_form_data(request, form_data)`, `parse_obj`, `serialize_value`, plus new pluggable `getter`, `formatter: dict[RequestAction, callable]`, `parser: dict[RequestAction, callable]`. Templates live at `templates/fields/form/<type>.html`.

**flask-admin**: WTForms `model_form` + `inline_models = [(Post, dict(form_columns=['title']))]` producing an `InlineModelFormList(InlineFieldList)` whose entries are subforms named `posts-0-title`, with deletion via a `del-posts-0` key (`InlineFieldList.process`: `f._should_delete = f"del-{f.id}" in formdata`) and a JS-cloned `template` row.

**marshmallow**: `Schema` with `fields.Nested(SchemaOrLambda, many=..., only=..., exclude=..., unknown=...)`, `fields.List(fields.Nested(Item))`; `Schema(partial=True|("email",), unknown=RAISE|EXCLUDE|INCLUDE)` (also `class Meta: unknown = EXCLUDE`); hooks `@pre_load`, `@post_load`, `@validates("field")`, `@validates_schema`; per-field `error_messages={"required": "..."}` overriding `Field.default_error_messages`. `load()` raises `ValidationError(message: str|list|dict, field_name=SCHEMA, data=...)` whose `.messages` is a nested dict; `.valid_data` holds the part that passed.

**Colander/Deform/peppercorn**: `colander.SchemaNode(typ, *children, name=, missing=, default=, validator=, preparer=, title=)`; declarative `MappingSchema`, `SequenceSchema`, `TupleSchema`; `schema.bind(**kw)` resolves `colander.deferred` callables (request-dependent choices); `deserialize(cstruct)` raises `Invalid` with `.asdict(translate=None, separator='; ')` giving dotted paths, `.paths()`, `.children`. `deform.Form(schema, action=, method=, buttons=[Button('submit')], formid=, use_ajax=)`; `form.render(appstruct)` and `form.validate(controls)` where `controls = request.POST.items()` (document-ordered pairs); failure raises `deform.ValidationFailure(field, cstruct, error)` and `e.render()` re-renders with errors. Nesting is encoded in the *document order* using hidden inputs `<input type="hidden" name="__start__" value="people:sequence">` ... `__end__`, decoded by `peppercorn.parse(tokens)` (types: `sequence`, `mapping`, `rename`, `ignore`). `SequenceWidget(min_len, max_len, orderable, item_template, add_subitem_text_template)` clones a hidden prototype row client-side.

**DRF**: `Serializer`/`ModelSerializer` with `ItemSerializer(many=True)` for nested lists (becomes `ListSerializer(child=...)`). `Serializer.get_value` calls `html.parse_html_dict(dictionary, prefix=self.field_name)` for dotted keys `profile.username`; `ListSerializer.get_value` calls `parse_html_list(dictionary, prefix)` for `items[0]qty`. `serializer.errors` is a nested dict; `partial=True` skips required checks. `HTMLFormRenderer.template_pack = 'rest_framework/vertical/'` (also `horizontal/`, `inline/`) and `default_style = ClassLookupDict({...})` maps field class -> `{'base_template': 'input.html', 'input_type': 'text'}`, `ListSerializer -> list_fieldset.html`, `Serializer -> fieldset.html`, `ListField -> list_field.html`, `DictField -> dict_field.html`; `render_field(field, parent_style)` merges `field.style` over the default and inherits `template_pack`.

## Data in (naming, parsing, coercion, nested/lists)

Real output of `fastui.forms.unflatten` (run):

```python
FormData([("user.name","Ann"),("user.address.city",""),("tags.0","a"),("tags.1","b"),
          ("items.0.qty","2"),("items.1.qty","3"),("colors","red"),("colors","blue")])
# -> {'user': {'name': 'Ann'}, 'tags': ['a', 'b'], 'items': [{'qty': '2'}, {'qty': '3'}], 'colors': ['red', 'blue']}
name_to_loc('["a.b", 0, "c"]')  # -> ['a.b', 0, 'c']
```

Rules baked in: values equal to `['']` are *dropped* ("might be a bit controversial, but it helps ... a select which hasn't been updated"), repeated names become lists, dicts whose keys are all ints are converted to sorted lists (so `items.0/items.3` compacts to a 2-list -- indices need not be contiguous). Coercion is left entirely to pydantic in lax mode (strings -> int/bool/date). Checkboxes: FastUI's React client sends nothing for unchecked, so `bool` fields must default `False`.

FastAPI form models, real output:

```python
class Addr(BaseModel): city: str
class U(BaseModel): name: str; tags: list[str] = []; addr: Addr | None = None
@app.post("/u")
def u(data: Annotated[U, Form()]): return data
c.post("/u", data={"name":"Ann","tags":["a","b"]}).json()  # {'name': 'Ann', 'tags': ['a', 'b'], 'addr': None}
c.post("/u", data={"name":"Ann","addr.city":"X","addr[city]":"Y"})  # 200 addr None  (silently ignored)
c.post("/u", data={"name":"Ann","addr":'{"city":"Z"}'})   # 422 model_attributes_type "Input should be a valid dictionary or object"
```

So: repeated keys -> list works; nesting is impossible without a custom dependency. FastHTML is the same shape (flat `anno(**cargs)`) but coerces itself (`str2bool`, `str2int`, `str2date`) and takes the *last* value of a repeated key for scalar annotations (`res(o[-1])`).

peppercorn, real output:

```python
peppercorn.parse([("__start__","people:sequence"),("__start__","p:mapping"),("name","a"),("__end__","p:mapping"),
                  ("__start__","p:mapping"),("name","b"),("__end__","p:mapping"),("__end__","people:sequence"),("title","t")])
# -> {'people': [{'name': 'a'}, {'name': 'b'}], 'title': 't'}
```

Field `name`s inside a sequence are all the same (`name`) -- position, not naming, carries structure. Elegant for arbitrarily deep nesting and needs no index bookkeeping, but requires the client to preserve document order (Phoenix's client serializes with `FormData` order, so it would actually work) and is unreadable in `_target`.

DRF, real output: `parse_html_list(QueryDict("items[0]qty=2&items[1]qty=3"), prefix="items")` -> `[MultiValueDict{'qty':['2']}, MultiValueDict{'qty':['3']}]`; `parse_html_dict(q, prefix="profile")` for `profile.username=ann` -> `{'username': ['ann'], 'email': ['e']}`. Each nested serializer pulls only its own prefix lazily via `get_value`, so the top-level dict is never fully unflattened -- nice property for partial validation.

starlette-admin: `ListField.parse_form_data` calls `self._extra_indices(form_data)` -- scans all keys starting with `field.id`, takes the segment after the dot if it `isdigit()`, collecting e.g. `[0,1,3,8]` -- then sets `self.field.id = f"{self.id}.{index}"`, `CollectionField._propagate_id()` (child ids become `items.0.sku`), and re-parses the child. `IntegerField.parse_form_data` turns `""` into `None`; `BooleanField` reads the checkbox presence. (Running it stand-alone fails: `CollectionField 'items' has no _view; it must be used inside a BaseModelView` -- the fields are coupled to the view for i18n/request.)

## Validation & error model

- pydantic (FastUI/FastAPI/streamlit): list of `{'type','loc','msg','input','ctx'}`; FastUI returns `HTTPException(422, detail={'form': e.errors(include_input=False, include_url=False, include_context=False)})` and the React client matches `loc` to field names (`loc_to_name`). streamlit-pydantic just renders one `st.error` with `".".join(loc) + msg` lines -- no per-field placement.
- marshmallow, real output for `Order().load({"email":"bad","items":[{"qty":"1"},{"qty":"x"},{}],"zzz":1})` with `Meta.unknown = EXCLUDE`:
  `{'email': ['Not a valid email address.'], 'items': {1: {'qty': ['Not a valid integer.']}, 2: {'qty': ['qty missing']}}}` -- lists are keyed by *index as int* inside a dict (sparse), messages are lists, custom `error_messages={"required": "qty missing"}` honoured. `Order(partial=True).load({"items":[{"qty":"1"}]})` -> `{'items': [{'qty': 1}]}`; `partial=("email",)` works per field and propagates to nested schemas as `sub_partial` (schema.py ~line 663). Messages are plain strings; i18n is DIY. Timing: all fields validated then `@validates_schema` (with `skip_on_field_errors=True` default).
- Colander, real output: `Doc().deserialize({"title":"t","people":[{"name":"ok"},{"name":"x"},{}]})` -> `Invalid.asdict()` = `{'people.1.name': 'Shorter than minimum length 2', 'people.2.name': 'Required'}`. Messages are `translationstring`s with `${min}` interpolation and `asdict(translate=...)` hooks in gettext; the `Invalid` tree (`.children`, `.paths()`) is what Deform walks to put `error` on each `Field`. Validation is two-phase: `SchemaType.deserialize` (type coercion) then `validator` per node; `missing=colander.required|drop|value`, `null` sentinel distinguishes "absent" from "empty".
- Deform: `Form.validate(controls)` -> `peppercorn.parse` -> `schema.deserialize` -> on `Invalid`, `ValidationFailure(field, cstruct, error)`; `e.render()` re-renders with `field.error` set on every node in the path and `field.errormsg`; `Field.validate_pstruct(pstruct)` exists for already-decoded data.
- DRF: `serializer.is_valid(raise_exception=False)`; `serializer.errors` nested dict, list children as list-of-dicts (`[{}, {'qty': [...]}]`) (unverified for this version but standard); `ErrorDetail(str)` carries `.code` (`'required'`, `'invalid'`, `'blank'`); `default_error_messages` per field; `partial=True` on the serializer.
- starlette-admin: `raise FormValidationError({"name": "Ensure this value has at least 3 characters", "items": {0: {"sku": "required"}}})` from `ModelView.validate(request, data)`; templates do `error.get(loop.index0) if (error | is_dict)` for list items, `{% if error | is_str %}` to render. sqladmin/flask-admin: WTForms `form.errors` (`{'posts': [{'title': ['This field is required.']}]}`).

## Form state (bound/unbound, touched, attempted values)

Only WTForms-based (sqladmin/flask-admin) and Deform have a real "bound form" object: Deform `Field` holds `cstruct` (attempted raw values) and `error`, and `ValidationFailure.render()` re-renders from the *raw* cstruct, not the appstruct, so bad input survives round trips. DRF's `BoundField` (`serializer['name']` -> `.value`, `.errors`, `.name`) plus `serializer.data` after a failed `is_valid` gives attempted values (`initial_data`). FastUI has no server form state at all -- state lives in the React client which shows `loc` errors next to inputs; the server is stateless request/response. streamlit-pydantic keeps state in `st.session_state[key]` per dotted path and re-renders every rerun; `ignore_empty_values=True` drops `""`/`0`. FastHTML has `fill_form(form, obj)` to write values back into an FT tree (edit forms), nothing for errors or touched-ness. No library here has a touched/used concept -- validation is all-or-nothing on submit; only pydantic's `loc` and marshmallow's `partial` allow partial checking.

## Rendering & customization & styling

- FastUI: rendering is done by the bundled React components; server chooses only field *types* (`FormFieldInput.html_type` from `input_html_type(schema)`: `'date'|'datetime-local'|'time'|'email'|'url'|'number'|'password'|'text'`), `Textarea(rows, cols)` annotation, `Field(json_schema_extra={'search_url': ...})` -> `FormFieldSelectSearch`. Styling: `class_name` on components; otherwise you cannot change the markup -- the main criticism of FastUI, and the repo has been quiet (unverified: maintenance status).
- streamlit-pydantic: `st_kwargs_*` schema extras and `render_input_ui` classmethod override; no HTML.
- sqladmin: WTForms + Bootstrap/Tabler templates; `form_widget_args` to add attrs; override Jinja templates by name. flask-admin: Bootstrap 3/4 templates, `form_widget_args`, `form_extra_fields`, `form_rules` (`rules.FieldSet(('a','b'), 'Header')`) for layout.
- starlette-admin: every field has `form_template = "forms/<type>.html"`, `display_template`, `class_` defaults, `form_alt` slots; `ListField` template renders a `.template.d-none` prototype row and a `-next-index` hidden input, JS clones it on "add".
- Deform: Chameleon templates per widget (`template`, `readonly_template`, `item_template`), overridable via `deform.Form.set_zpt_renderer(search_path)`; `widget=deform.widget.SelectWidget(values=...)`, `field.set_widgets({'people.*.name': TextInputWidget()})` with glob paths (`set_widgets(values, separator=".")`, field.py 505).
- DRF: `style={'base_template': 'textarea.html', 'rows': 4}` per field (documented), `template_pack` inheritance, `{% render_form serializer template_pack='rest_framework/inline/' %}` template tag; templates are Bootstrap 3 in `rest_framework/templates/rest_framework/{vertical,horizontal,inline}/`. This "style dict overrides a class-keyed default" is the cleanest customisation mechanism in the set.

## Nested / dynamic / conditional

- Deep nesting: FastUI (objects yes, via loc; lists no), streamlit-pydantic (objects, lists of objects with add/clear, unions via selectbox -- the *only* one with conditional/union UI), starlette-admin (CollectionField in ListField, arbitrary depth via `_propagate_id`), Deform (arbitrary, `MappingWidget`/`SequenceWidget`, `min_len/max_len`, `orderable`), DRF (nested serializers + `many=True`, one level of list-of-dict parse; deeper list-in-list via `[0]items[1]qty` (unverified)), marshmallow (arbitrary, data only), flask-admin (one level inline), FastAPI/FastHTML/sqladmin (none).
- Dynamic add/remove is always client JS cloning a prototype row and bumping an index (starlette-admin `-next-index`, flask-admin `inline-field-list` JS, Deform `SequenceWidget` `add_subitem` with `deform.addSequenceItem`). In a LiveView world this is instead a server round-trip that re-renders with N+1 items -- simpler, but the *parser must tolerate gaps* (FastUI sorts int keys; starlette-admin collects any digit indices; DRF sorts) because removing item 1 of 3 leaves `0,2`.
- Conditional: only streamlit-pydantic (discriminated `anyOf`) and Colander `deferred` (bind-time schema shaping) handle it; FastUI explicitly refuses non-Optional `anyOf`.

## DX highlights with real code

1. FastUI whole loop (forms.py 36-48): `fastui_form(Model)` dependency + `unflatten` -- ~50 lines cover schema->fields->unflatten->errors-by-loc. Field decoration by annotation, e.g. `notes: Annotated[str, Textarea(rows=5)]`, `avatar: Annotated[UploadFile, FormFile(accept='image/*', max_size=16_000)]` (forms.py 52-142 implements `__get_pydantic_core_schema__` + `__get_pydantic_json_schema__` so the same annotation both validates and drives the widget).
2. streamlit-pydantic: `if data := sp.pydantic_form(key="my_form", model=ExampleModel): st.json(data.json())` -- a whole editor for nested models, lists and discriminated unions in one line.
3. FastHTML: `@rt def create(todo: Todo): return todos.insert(todo), new_inp` plus `return fill_form(res, todos[id])` -- zero ceremony because the type annotation is the schema and `_fix_anno` does the coercion.
4. marshmallow: nested error dict above, `Order(partial=("email",))`, `error_messages={"required": "qty missing"}`.
5. Colander/Deform: `Invalid.asdict()` dotted paths; `form.set_widgets({'people.*.name': ...})`; `SchemaNode(String(), missing=colander.drop)`; peppercorn's order-based nesting.
6. DRF: `class OrderSerializer(Serializer): items = ItemSerializer(many=True); profile = ProfileSerializer()` + `{% render_form serializer %}` renders nested fieldsets (`fieldset.html`, `list_fieldset.html`) from `template_pack`.
7. starlette-admin: `ListField(CollectionField("items", fields=[...]))` + `raise FormValidationError({"items": {0: {"sku": "msg"}}})` -- errors by nested path with ints for indices.

## Pain points & criticisms (cite)

- FastUI: `NotImplementedError('Array fields are not fully supported, see https://github.com/pydantic/FastUI/pull/52')` and `'anyOf schemas which are not simply X | None are not yet supported'` (json_schema.py 345, 247); `unflatten` dropping `''` means you cannot distinguish "cleared" from "untouched"; class docstring "TODO mypy, pyright and pycharm don't understand the model type" for `FastUIForm[Model]`.
- FastAPI: nested form models silently ignore nested keys (run above); everything is `str | UploadFile`; error `loc` starts with `'body'`.
- FastHTML: last-value-wins for repeated keys, `int` cast failure becomes a 404 (`HTTPException(404, f"{path}: {e}")` in `_find_p`), no validation framework at all -- adv_app validates by `if not name or not pwd`.
- streamlit-pydantic: pydantic v1 API surface (`.schema()`, `parse_obj_as`, `.dict()`), errors as one blob, `raise Exception("Unsupported property")` for unknown types.
- Deform/peppercorn: order-dependent protocol is fragile with any client that reorders fields; Chameleon templates; heavy.
- marshmallow: dict-of-lists errors need a walker to render per input; no widgets.
- DRF HTMLFormRenderer: Bootstrap-3 templates, browsable-API oriented, nested list editing has no add/remove UI.
- Admin frameworks: ORM-driven, so a pydantic model needs a parallel SQLAlchemy model.

## Lessons for pyview -- steal / adapt / avoid

**Steal**
1. FastUI's `loc` pair: `loc_to_name(loc)`/`name_to_loc(name)` as the single source of truth for `id`, `name`, error lookup and `_target` mapping. pyview should implement it for Phoenix bracket names (`user[items][0][qty]` <-> `('user','items',0,'qty')`) since that is what `inputs_for` and the Phoenix JS form recovery expect; keep the "all-int keys -> list, sorted, gaps allowed" compaction and keep the dotted variant as an internal canonical string for `phx-feedback-for`.
2. FastUI's annotation trick (`Annotated[str, Textarea(rows=5)]` implementing `__get_pydantic_json_schema__`) so widget hints live in the model without a parallel form class; read them back from `model_json_schema()`/`FieldInfo.json_schema_extra`.
3. marshmallow's `partial=("email",)` semantics for phx-change: validate the full model but *report* only errors whose `loc` prefix is in the used/changed set (this generalises the current `keys in changes` rule to nested paths); and per-field `error_messages` overrides.
4. DRF's `style` dict merged over a class-keyed `default_style` + `template_pack` inheritance: `Field(json_schema_extra={"style": {"widget": "radio"}})` plus a renderer that maps pydantic core-schema type -> widget template, overridable per field, per form, or globally.
5. starlette-admin/Deform's prototype-row idea adapted to LiveView: a server-side `add_item(path)`/`remove_item(path, idx)` on the changeset that edits the *raw params tree* and re-renders; no client JS needed.

**Adapt**
- Two-phase validation as in Colander (`deserialize` then `validator`): run pydantic in lax mode on the unflattened tree, but pre-normalise HTML quirks first (`""` -> `None` for Optional/int/date, missing checkbox -> `False`, `getlist` for `list[str]`/multi-select) -- FastUI's global "drop empty strings" is too blunt. Keep the raw string tree for re-rendering attempted values (Deform's `cstruct`).
- streamlit-pydantic's discriminated-union handling is the only prior art for conditional nesting: render the discriminator as a select and, on `_target == discriminator`, swap the sub-form; errors from the non-selected branch must be dropped.
- Errors: normalise pydantic's `errors()` into `dict[tuple, list[Error]]` with `type`, `msg`, `ctx` kept (needed for i18n later, like Colander's translationstring), plus helpers `errors_at(prefix)` and `errors_for_list(path) -> {index: ...}` (the shape starlette-admin templates consume).

**Avoid**
- FastAPI-style flat extraction with silent drops of unknown nested keys -- surface an error or at least log.
- FastHTML's last-value-wins and coercion-failure-as-404; keep repeated keys as lists always and let the type decide.
- Deform/peppercorn order-based encoding; and FastUI's "server renders JSON for a React client" split -- pyview's value is server HTML.
- Coupling fields to the view/request (starlette-admin's `_view` requirement made stand-alone parsing impossible in the demo).

## Sources (read)
- pkgs/py-python_landscape/fastui/forms.py (27-48, 176-230), fastui/json_schema.py (151-247, 304-346)
- streamlit_pydantic/ui_renderer.py (123-137, 207-216, 575-600, 964-1000, 1014-1066, 1301-1356)
- fasthtml/core.py (140-160, 188-303), fasthtml/components.py (178-203); https://raw.githubusercontent.com/AnswerDotAI/fasthtml/main/examples/adv_app.py
- https://raw.githubusercontent.com/fastapi/fastapi/master/docs/en/docs/tutorial/request-form-models.md; live TestClient run above
- sqladmin/forms.py (681-703), sqladmin/models.py (578-660)
- starlette_admin/fields.py (83-110, 2283-2300, 2374-2400, 2476-2600, 2669-2681), starlette_admin/exceptions.py (8-20), templates/fields/form/list.html
- flask_admin/contrib/sqla/view.py (209-303), flask_admin/model/fields.py (InlineFieldList)
- marshmallow/schema.py (220, 265-269, 416-434, 604-666), fields.py (161-190, 490), decorators.py, exceptions.py (27-33)
- colander/__init__.py (85-230, 2400-2670); deform/form.py, deform/field.py (505, 598-763), deform/widget.py (SequenceWidget ~1580-1620), deform/exception.py; peppercorn/__init__.py (1-30)
- rest_framework/utils/html.py (1-90), rest_framework/renderers.py (254-337), rest_framework/serializers.py (439-443, 602-635, 674)
- Demo script with real output: scratchpad/pl_demo.py
