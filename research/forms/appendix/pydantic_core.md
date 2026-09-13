# Pydantic v2 as a form-validation engine (facts to build on) — pydantic 2.13.4 / pydantic-core 2.46.4, docs @ pydantic/pydantic main (ba830dc, 2026-09-11); researched 2026-09-12

All snippets below were run with `uv run python` in the pyview venv (experiment files: `scratchpad/proto/exp1_pydantic_errors.py`, `exp2_coercion.py`, `exp4_field_targeted_errors.py`, `exp5_error_catalog.py`, `exp6_pydantic_facts.py`). Outputs are pasted verbatim.

## TL;DR

- Pydantic gives you a **path-addressed error list**: every error is `{type, loc: tuple[str|int,...], msg, input, ctx?, url?}`; `loc` goes through nested models, list indices and discriminated-union branches (`('addresses', 0, 'zip')`, `('account','business','company')`). Model-level validators produce `loc=()`. That is exactly the shape a nested form needs.
- There are **104 built-in error `type`s** (`pydantic_core.core_schema.ErrorType`), each with a message template and a small `ctx` dict (`{'min_length': 3}`, `{'ge': 18}`, `{'expected': "'red' or 'blue'"}` ...). The complete table is below — it is the i18n/message-override key space for pyview.
- **Lax mode is almost form-friendly but not quite**: `' 21 '`, `'21.0'` -> `int` OK; `'on'/'off'/'yes'/'no'/'1'/'0'/'t'/'f'/'y'/'n'/'true'/'false'` -> `bool` OK; ISO `date`/`datetime-local` strings OK; but the **empty string fails every non-`str` type (including `Optional[int]`)**, `'1,5'` decimals/floats fail, `'checked'` is not a bool, a scalar string is not a `list`. pyview must normalise `''` -> missing/None and checkbox absence -> `False` *before* Pydantic.
- **Field-targeted errors from a `model_validator` are supported**: raise `ValidationError.from_exception_data(title, [InitErrorDetails(type=PydanticCustomError(...), loc=('end',), input=...)])`; nested `loc` is prefixed correctly (`('items', 1, 'hi')`). Caveat: after-model-validators do **not run** when any field failed, so cross-field errors appear only once the fields parse.
- `experimental_allow_partial` is for streaming JSON: it only ignores errors in the *last element* of list/dict/`TypedDict`, is `TypeAdapter`-only and **does not work through `BaseModel`**. It does not help "validate what the user has typed so far" — use touched-field filtering of a full validation instead (full revalidation of a 60-field 3-level model is ~14 µs).
- Per-field validation: `validate_assignment=True` on a constructed instance (~1 µs/assignment) or a prebuilt `TypeAdapter(Annotated[fi.annotation, fi])` (0.3 µs; building it costs ~25 µs, so cache per field).
- `model_fields: dict[str, FieldInfo]` carries everything a renderer needs: `annotation`, `title`, `description`, `examples`, `alias`/`validation_alias`, `default`/`default_factory`, `is_required()`, `deprecated`, `json_schema_extra`, and `metadata` (`MinLen`, `Ge`, `Pattern`...). `model_json_schema()` adds `format: email|uri|date|date-time|password`, `enum`, `minimum/maximum/multipleOf/minLength/pattern`.
- **No async validators** in pydantic (verified by absence in `functional_validators.py` and the docs); no built-in i18n; `EmailStr` needs the optional `email-validator` package (not installed in pyview's venv).

## Mental model & core abstractions

- `BaseModel` (schema built at class creation, validation in Rust via `pydantic_core.SchemaValidator`), pydantic `@dataclass`, and `TypeAdapter(T)` for *anything else* (stdlib dataclasses, `TypedDict` (must be `typing_extensions.TypedDict` on Python < 3.12 — `PydanticUserError: typed-dict-version`), `list[Model]`, `Annotated[...]`). `TypeAdapter(DC).core_schema['schema']['fields']` exposes field names for stdlib dataclasses.
- Entry points and their modes (`docs/concepts/models.md` "Validating data"): `Model(**kw)`, `model_validate(obj, *, strict, extra, from_attributes, context, by_alias, by_name)`, `model_validate_json(...)`, `model_validate_strings(dict-of-str, nested OK)` which validates "in JSON mode so that said strings can be coerced". `ValidationInfo.mode` is `'python' | 'json' | 'strings'`.
- Validators: `@field_validator('a','b', mode='before'|'after'|'wrap'|'plain')`, `@model_validator(mode='before'|'after'|'wrap')`, or the annotated forms `BeforeValidator/AfterValidator/WrapValidator/PlainValidator`. Ordering: before & wrap run right-to-left, after run left-to-right; decorator validators are appended last (`validators.md` "Ordering of validators"). Both validator kinds accept an optional `ValidationInfo` with `.context`, `.data` (already-validated fields, `None` for model validators), `.field_name`, `.mode`, `.config`.
- Special escape hatches (`validators.md` "Special types"): `PydanticUseDefault()` raised from a before-validator makes the field take its default (ideal for `''` -> default), `SkipValidation`, `InstanceOf`, `FailFast`.
- `ConfigDict` bits that matter for forms: `validate_assignment`, `extra='ignore'|'forbid'|'allow'` (`forbid` gives `extra_forbidden` errors at `loc=('extra',)` — pyview should strip `_csrf_token`/`_target` first), `str_strip_whitespace`, `revalidate_instances`, `validate_by_alias` (default True) / `validate_by_name` (default False, added v2.11; `alias.md`), `validate_default`, `coerce_numbers_to_str`.
- `model_construct(**values)` builds without validation (docs warn it can create invalid instances and is "narrowly" faster); `model_fields_set` tells which fields were explicitly provided; `model_extra` holds extra data.

## Data in (naming, parsing, coercion, nested/lists)

Runnable evidence (exp2, lax `model_validate` from Python dict of strings):

```
{'age': ''}       -> ERR int_parsing        {'age': ' 21 '} -> 21      {'age': '21.0'} -> 21     {'age': '1e3'} -> ERR
{'price': '1,5'}  -> ERR decimal_parsing    {'price': '1.50'} -> Decimal('1.50')   {'ratio': '1,5'} -> ERR float_parsing
{'flag': ''}      -> ERR bool_parsing       'on'->True 'off'->False 'yes'->True 'true'->True '0'->False 'checked'->ERR
{'tags': 'a'}     -> ERR list_type          {'tags': ['a','b']} -> ok   {'nums': ['1','x']} -> ERR loc ('nums', 1)
{'when': '2024-05-01'} -> date              {'when': ''} -> ERR date_from_datetime_parsing
{'at': '2024-05-01T13:45'} -> datetime      {'at': ''}  -> ERR datetime_from_date_parsing
{'color': ''} -> ERR enum   {'lit': 'c'} -> ERR literal_error   {'opt_s': ''} -> ''   {'opt_i': ''} -> ERR int_parsing
```

Documented bool rule (`docs/api/standard_library_types.md` "Booleans"): a string which lowercased is one of `'0','off','f','false','n','no','1','on','t','true','y','yes'`. HTML's default checkbox value `on` therefore works; an unchecked checkbox is simply absent (-> `missing` unless default).

`model_validate_strings` (exp6) applies JSON-mode rules to a nested dict of strings — `' 21 '`, `'21.0'`, `'on'`, `'2024-05-01'`, `{'sub': {'n': '3'}}` all work — **but a list value fails** (`{'tags': ['1','2']}` -> `('tags',) string_type`), so it is not usable for multi-select/`list[...]` form data; plain `model_validate` on the parsed dict is the right entry point.

Aliases: with `Field(alias='firstName')` the error `loc` is the alias `('firstName',)` and input must use the alias unless `by_name=True` is passed at runtime or set in config. `validation_alias=AliasPath('contact','address')` / `AliasChoices(...)` can pull a field from a nested path (`alias.md`). For HTML `name` generation pyview should use the field name (or `alias` when set) and pass `by_alias=True, by_name=True`.

Nested/lists: Pydantic wants an already-nested dict (`{'addresses': [{'street': ...}]}`). Phoenix-style `user[addresses][0][street]` keys must be decoded by pyview (Plug.Conn.Query semantics: `a[b]`, `a[]` list append, `a[0]` index) before `model_validate`. Pydantic will then validate list items positionally and report `('addresses', 0, 'street')`.

## Validation & error model (structure, codes/messages/params, i18n, timing)

`ValidationError` API (verified): `.errors(*, include_url=True, include_context=True, include_input=True) -> list[ErrorDetails]`, `.json(...)`, `.error_count()`, `.title`, and the classmethod `ValidationError.from_exception_data(title, line_errors, input_type='python', hide_input=False)`. `ErrorDetails` = `{type: str, loc: tuple[int|str,...], msg: str, input: Any, ctx?: dict, url?: str}`; `InitErrorDetails` = `{type: str|PydanticCustomError, loc?: tuple, input: Any, ctx?: dict}`.

Real output, exp1:
```
('name',) | string_too_short | String should have at least 3 characters | {'min_length': 3}
('age',) | greater_than_equal | Input should be greater than or equal to 18 | {'ge': 18}
('addresses', 0, 'street') | string_too_short | ... | {'min_length': 3}
('addresses', 0, 'zip') | string_pattern_mismatch | String should match pattern '^\d{5}$' | {'pattern': '^\\d{5}$'}
('account', 'business', 'company') | string_too_short | ...      # discriminated union: tag value is inserted into loc
() | value_error | Value error, name cannot be admin                  # model_validator(mode='after') raising ValueError
('account',) | union_tag_invalid | Input tag 'other' found using 'kind' does not match any of the expected tags: 'personal', 'business' | {'discriminator': "'kind'", 'tag': 'other', 'expected_tags': "'personal', 'business'"}
```
Note: for `value_error`, `ctx == {'error': ValueError('must be positive')}` (the exception object, not JSON-safe until `.json()`), and `missing` errors carry the whole parent dict as `input`.

Raising errors (`validators.md` "Raising validation errors"): `ValueError` -> `value_error` ("Value error, {error}"), `AssertionError` -> `assertion_error`, `PydanticCustomError(type, message_template, ctx)` -> your own type/message with `{placeholders}` filled from ctx, `PydanticKnownError('string_too_short', {'min_length': 3})` reuses a built-in template (verified: msg "String should have at least 3 characters"). Both `ValidationError` and `PydanticCustomError` are subclassable (2.10 HISTORY). `Discriminator(fn, custom_error_type=..., custom_error_message=..., custom_error_context=...)` replaces the `union_tag_*` errors (verified: `{'type': 'bad_pet', 'loc': ('pet',), 'msg': 'Choose cat or dog', 'ctx': {'x': 1}}`).

**Field-targeted errors from a model validator** (exp4, real output):
```python
@model_validator(mode="after")
def check(self):
    line_errors: list[InitErrorDetails] = []
    if self.password != self.password_confirmation:
        line_errors.append(InitErrorDetails(type=PydanticCustomError("mismatch", "Passwords do not match"),
                                            loc=("password_confirmation",), input=self.password_confirmation))
    if self.end < self.start:
        line_errors.append(InitErrorDetails(type=PydanticCustomError("range", "End must be after start ({start})", {"start": self.start}),
                                            loc=("end",), input=self.end))
    if line_errors:
        raise ValidationError.from_exception_data(self.__class__.__name__, line_errors)
    return self
# -> ('password_confirmation',) mismatch Passwords do not match None
#    ('end',) range End must be after start (5) {'start': 5}
# nested in list[Item]: ('items', 1, 'hi') order hi < lo     (outer path is prefixed automatically)
# with a failing field too: only ('password',) string_too_short  -- the after-validator did not run
```
The docs' idiomatic alternative is a `field_validator('password_repeat')` reading `info.data['password']` (`validators.md` "Validation data"), which only works when the referenced field is declared earlier and validated successfully (`info.data` lacks failed fields).

i18n: none built in. The `type` + `ctx` pair is the stable key; `msg` is English produced from the template. The table below is complete for 2.46.4 (`expected_plural` is filled by core as `'s'`/`''`).

Timing (exp2/exp6): full validation of a 3-level/60-field model ~14 µs; `validate_assignment` ~1 µs; prebuilt `TypeAdapter(int).validate_python` 0.3 µs; **constructing** a `TypeAdapter` ~25 µs (docs/concepts/performance.md: "TypeAdapter instantiated once"). `performance.md` also advises tagged unions over plain unions and `FailFast` for lists.

### Complete error-type table (generated from `pydantic_core.core_schema.ErrorType` + `PydanticKnownError(type, ctx).message_template`)

| type | message template | ctx keys |
|---|---|---|
| `no_such_attribute` | Object has no attribute '{attribute}' | attribute |
| `json_invalid` | Invalid JSON: {error} | error |
| `json_type` | JSON input should be string, bytes or bytearray | — |
| `needs_python_object` | Cannot check `{method_name}` when validating from json, use a JsonOrPython validator instead | method_name |
| `recursion_loop` | Recursion error - cyclic reference detected | — |
| `missing` | Field required | — |
| `frozen_field` | Field is frozen | — |
| `frozen_instance` | Instance is frozen | — |
| `extra_forbidden` | Extra inputs are not permitted | — |
| `invalid_key` | Keys should be strings | — |
| `get_attribute_error` | Error extracting attribute: {error} | error |
| `model_type` | Input should be a valid dictionary or instance of {class_name} | class_name |
| `model_attributes_type` | Input should be a valid dictionary or object to extract fields from | — |
| `dataclass_type` | Input should be a dictionary or an instance of {class_name} | class_name |
| `dataclass_exact_type` | Input should be an instance of {class_name} | class_name |
| `default_factory_not_called` | The default factory uses validated data, but at least one validation error occurred | — |
| `none_required` | Input should be None | — |
| `greater_than` | Input should be greater than {gt} | gt |
| `greater_than_equal` | Input should be greater than or equal to {ge} | ge |
| `less_than` | Input should be less than {lt} | lt |
| `less_than_equal` | Input should be less than or equal to {le} | le |
| `multiple_of` | Input should be a multiple of {multiple_of} | multiple_of |
| `finite_number` | Input should be a finite number | — |
| `too_short` | {field_type} should have at least {min_length} item{expected_plural} after validation, not {actual_length} | actual_length, expected_plural, field_type, min_length |
| `too_long` | {field_type} should have at most {max_length} item{expected_plural} after validation, not {actual_length} | actual_length, expected_plural, field_type, max_length |
| `iterable_type` | Input should be iterable | — |
| `iteration_error` | Error iterating over object, error: {error} | error |
| `string_type` | Input should be a valid string | — |
| `string_sub_type` | Input should be a string, not an instance of a subclass of str | — |
| `string_unicode` | Input should be a valid string, unable to parse raw data as a unicode string | — |
| `string_too_short` | String should have at least {min_length} character{expected_plural} | expected_plural, min_length |
| `string_too_long` | String should have at most {max_length} character{expected_plural} | expected_plural, max_length |
| `string_pattern_mismatch` | String should match pattern '{pattern}' | pattern |
| `string_not_ascii` | String should contain only ASCII characters | — |
| `enum` | Input should be {expected} | expected |
| `dict_type` | Input should be a valid dictionary | — |
| `mapping_type` | Input should be a valid mapping, error: {error} | error |
| `list_type` | Input should be a valid list | — |
| `tuple_type` | Input should be a valid tuple | — |
| `set_type` | Input should be a valid set | — |
| `set_item_not_hashable` | Set items should be hashable | — |
| `bool_type` | Input should be a valid boolean | — |
| `bool_parsing` | Input should be a valid boolean, unable to interpret input | — |
| `int_type` | Input should be a valid integer | — |
| `int_parsing` | Input should be a valid integer, unable to parse string as an integer | — |
| `int_parsing_size` | Unable to parse input string as an integer, exceeded maximum size | — |
| `int_from_float` | Input should be a valid integer, got a number with a fractional part | — |
| `float_type` | Input should be a valid number | — |
| `float_parsing` | Input should be a valid number, unable to parse string as a number | — |
| `bytes_type` | Input should be a valid bytes | — |
| `bytes_too_short` | Data should have at least {min_length} byte{expected_plural} | expected_plural, min_length |
| `bytes_too_long` | Data should have at most {max_length} byte{expected_plural} | expected_plural, max_length |
| `bytes_invalid_encoding` | Data should be valid {encoding}: {encoding_error} | encoding, encoding_error |
| `value_error` | Value error, {error} | error |
| `assertion_error` | Assertion failed, {error} | error |
| `literal_error` | Input should be {expected} | expected |
| `missing_sentinel_error` | Input should be the 'MISSING' sentinel | — |
| `date_type` | Input should be a valid date | — |
| `date_parsing` | Input should be a valid date in the format YYYY-MM-DD, {error} | error |
| `date_from_datetime_parsing` | Input should be a valid date or datetime, {error} | error |
| `date_from_datetime_inexact` | Datetimes provided to dates should have zero time - e.g. be exact dates | — |
| `date_past` | Date should be in the past | — |
| `date_future` | Date should be in the future | — |
| `time_type` | Input should be a valid time | — |
| `time_parsing` | Input should be in a valid time format, {error} | error |
| `datetime_type` | Input should be a valid datetime | — |
| `datetime_parsing` | Input should be a valid datetime, {error} | error |
| `datetime_object_invalid` | Invalid datetime object, got {error} | error |
| `datetime_from_date_parsing` | Input should be a valid datetime or date, {error} | error |
| `datetime_past` | Input should be in the past | — |
| `datetime_future` | Input should be in the future | — |
| `timezone_naive` | Input should not have timezone info | — |
| `timezone_aware` | Input should have timezone info | — |
| `timezone_offset` | Timezone offset of {tz_expected} required, got {tz_actual} | tz_actual, tz_expected |
| `time_delta_type` | Input should be a valid timedelta | — |
| `time_delta_parsing` | Input should be a valid timedelta, {error} | error |
| `frozen_set_type` | Input should be a valid frozenset | — |
| `is_instance_of` | Input should be an instance of {class} | class |
| `is_subclass_of` | Input should be a subclass of {class} | class |
| `callable_type` | Input should be callable | — |
| `union_tag_invalid` | Input tag '{tag}' found using {discriminator} does not match any of the expected tags: {expected_tags} | discriminator, expected_tags, tag |
| `union_tag_not_found` | Unable to extract tag using discriminator {discriminator} | discriminator |
| `arguments_type` | Arguments must be a tuple, list or a dictionary | — |
| `missing_argument` | Missing required argument | — |
| `unexpected_keyword_argument` | Unexpected keyword argument | — |
| `missing_keyword_only_argument` | Missing required keyword only argument | — |
| `unexpected_positional_argument` | Unexpected positional argument | — |
| `missing_positional_only_argument` | Missing required positional only argument | — |
| `multiple_argument_values` | Got multiple values for argument | — |
| `url_type` | URL input should be a string or URL | — |
| `url_parsing` | Input should be a valid URL, {error} | error |
| `url_syntax_violation` | Input violated strict URL syntax rules, {error} | error |
| `url_too_long` | URL should have at most {max_length} character{expected_plural} | expected_plural, max_length |
| `url_scheme` | URL scheme should be {expected_schemes} | expected_schemes |
| `uuid_type` | UUID input should be a string, bytes or UUID object | — |
| `uuid_parsing` | Input should be a valid UUID, {error} | error |
| `uuid_version` | UUID version {expected_version} expected | expected_version |
| `decimal_type` | Decimal input should be an integer, float, string or Decimal object | — |
| `decimal_parsing` | Input should be a valid decimal | — |
| `decimal_max_digits` | Decimal input should have no more than {max_digits} digit{expected_plural} in total | expected_plural, max_digits |
| `decimal_max_places` | Decimal input should have no more than {decimal_places} decimal place{expected_plural} | decimal_places, expected_plural |
| `decimal_whole_digits` | Decimal input should have no more than {whole_digits} digit{expected_plural} before the decimal point | expected_plural, whole_digits |
| `complex_type` | Input should be a valid python complex object, a number, or a valid complex string following the rules at https://docs.python.org/3/library/functions.html#complex | — |
| `complex_str_parsing` | Input should be a valid complex string following the rules at https://docs.python.org/3/library/functions.html#complex | — |

(`too_short`/`too_long` `field_type` is e.g. `'List'`, `'Set'`; `enum`/`literal_error` `expected` is a pre-rendered string like `"'red' or 'blue'"`; `date_*`/`datetime_*`/`url_*`/`uuid_parsing` `error` is a core-generated English fragment.)

## Form state (bound/unbound, touched/used, attempted values)

Pydantic has **no form-state concept**: no touched/dirty, no "attempted raw value" retention beyond `ErrorDetails.input` (per failed leaf) and no unbound form. Relevant primitives you can build on:
- `model_fields_set` (fields explicitly provided) and, since 2.12, the experimental `MISSING` sentinel (`pydantic_core.MISSING`; `name: str | MISSING = MISSING`; `model_dump(exclude_unset=True)` drops it — verified `Patch(name=<MISSING>) {} True`). Useful for PATCH-style "unset vs None", not for touched tracking.
- `experimental_allow_partial` (v2.10, `experimental.md`): values `False|'off'|True|'on'|'trailing-strings'`; `TypeAdapter.validate_json/validate_python/validate_strings` only; ignores ALL errors in the last element of `list/set/frozenset/dict/TypedDict(NotRequired)`; "BaseModel doesn't (yet) support partial validation" so nested models are all-or-nothing. exp1 confirms required `BaseModel` fields still raise `missing`.
- So touched/used must live in pyview: keep the raw `dict` of submitted params, validate the whole model every `phx-change`, and *filter* the error list by touched paths (LiveView 1.0 does exactly this with `_unused_` params / `used_input?`).

## Rendering & customization & styling

Pydantic renders nothing, but exposes the metadata a renderer needs:
- `Model.model_fields['x']` -> `FieldInfo` with slots `annotation, default, default_factory, alias, alias_priority, validation_alias, serialization_alias, title, field_title_generator, description, examples, exclude, exclude_if, discriminator, deprecated, json_schema_extra, frozen, validate_default, repr, init, init_var, kw_only, metadata` plus methods `is_required()`, `get_default(call_default_factory=...)`. `Field(...)` also accepts constraint kwargs `gt/ge/lt/le/multiple_of/min_length/max_length/pattern/max_digits/decimal_places/strict/union_mode/fail_fast` which land in `metadata` as `annotated_types` objects (`MinLen(min_length=3)`, `Ge(ge=18)`) — verified in exp1's introspection block.
- `json_schema_extra` is the sanctioned per-field bag for UI hints (`{'x-widget': 'text'}` round-trips into `fi.json_schema_extra` — verified). `field_title_generator`/`model_title_generator` produce labels.
- `model_json_schema()` output (exp6): `SecretStr` -> `{'format': 'password', 'writeOnly': True}`; `HttpUrl` -> `format: 'uri', maxLength 2083`; `date` -> `'date'`; `datetime` -> `'date-time'`; `EmailStr` -> `format: 'email'` (per `json_schema.md` line 359; needs `email-validator`); `Literal` -> `enum`; numeric/string constraints -> `minimum/maximum/multipleOf/minLength/pattern`. A pyview widget resolver can key on the annotation first and fall back to the JSON-schema `format`.
- Deprecated fields (`fields.md` "Deprecated fields"): `Field(deprecated=True|'msg')` -> `deprecated: true` in JSON schema; a form renderer could hide them.

## Nested / dynamic / conditional

- Nested models and `list[Model]` validate recursively; errors carry the full path. Dynamic list rows = list indices in the submitted keys; deleting a row means re-indexing on the pyview side (Pydantic just sees a list).
- Conditional sections map naturally onto **discriminated unions** (`unions.md`): `account: Personal | Business = Field(discriminator='kind')`, or for non-uniform tag fields a callable `Discriminator(fn)` + `Tag('apple')` per member (`Annotated[Annotated[ApplePie, Tag('apple')] | Annotated[PumpkinPie, Tag('pumpkin')], Discriminator(get_discriminator_value)]`). The docs warn the callable must accept both `dict` and model instances. The chosen branch's tag appears in `loc` (`('account', 'business', 'company')`), which a renderer must strip/skip when mapping to input names. Missing tag -> `union_tag_not_found`, bad tag -> `union_tag_invalid` at the union field's loc; nested discriminated unions are supported (`unions.md` "Nested Discriminated Unions").
- Plain (non-discriminated) unions in smart mode produce one error *per member* with the member name inserted in `loc` — verbose; the docs recommend discriminated unions for clearer errors.
- `Optional[Model]` sections: `''`/absent -> `None` needs the pyview pre-normaliser; an all-empty nested dict will otherwise raise `missing` for each sub-field.

## DX highlights with real code (cite each)

1. One-line reuse of built-in messages with your own trigger (validators.md; verified exp6):
```python
@field_validator("v")
@classmethod
def f(cls, v):
    raise PydanticKnownError("string_too_short", {"min_length": 3})   # -> msg 'String should have at least 3 characters'
```
2. `PydanticUseDefault` to turn HTML empty strings into defaults (validators.md "Special types"):
```python
def empty_to_default(v):
    if v == "": raise PydanticUseDefault()
    return v
class M(BaseModel):
    n: Annotated[int | None, BeforeValidator(empty_to_default)] = None
```
3. Validation context for request-scoped rules (validators.md "Validation context"): `Model.model_validate(data, context={'user': u})` and `info.context.get('user')` inside any validator.
4. Runtime alias control (alias.md, verified): `A.model_validate({'first_name': 'x'}, by_name=True, by_alias=False)`.
5. Custom discriminator errors (unions.md, verified): `Discriminator(disc, custom_error_type='bad_pet', custom_error_message='Choose cat or dog')`.
6. Pipeline API (experimental.md, v2.8): `name: Annotated[str, validate_as(str).str_strip().str_lower()]`, `favorite_number: Annotated[int, (validate_as(int) | validate_as(str).str_strip().validate_as(int)).gt(0)]` — composable parse/transform/constraint chains; subject to change.
7. Any type via `TypeAdapter` (dataclasses.md/type_adapter.md, verified): `TypeAdapter(StdlibDC).validate_python({'x': '5'})` -> `DC(x=5, y='d')`; `TypeAdapter(TD).validate_python({'a': 'z'})` -> loc `('a',)`, title `TD`.

## Pain points & criticisms (cite)

- Empty-string handling: every non-str type rejects `''` (exp2). pydantic issue #11154 (linked from models.md) tracks Python-vs-JSON mode behaviour divergence; forms need a normalisation layer.
- `model_validate_strings` rejects lists (exp6) — unusable for multi-select.
- After-model-validators are skipped when field validation fails (exp4) — users see cross-field errors only on a second pass.
- `info.data` is order-dependent and omits failed fields (validators.md warning) — cross-field `field_validator`s are fragile.
- Union `loc` inserts the member tag (`('account','business','company')`) — extra work to map to input names.
- No async validators, no i18n, `value_error.ctx.error` holds a live exception (non-JSON-serialisable in `.errors()`), `EmailStr` needs an extra package.
- Partial validation is explicitly a "proof of concept", `TypeAdapter`-only, and `BaseModel` opts out; the `MISSING` sentinel is still experimental (2.12/2.13 HISTORY).
- `TypeAdapter` construction cost (~25 µs) and `model_fields` only accessible on the class since 2.11 (`fields.md` deprecation note).

## Lessons for pyview — steal / adapt / avoid

**Steal**
- Use `ErrorDetails` verbatim as the internal error record: keep `type`, `loc`, `ctx`, `input`; render `msg` through an overridable `messages: dict[type, template]` seeded from the 104-entry table (this gives i18n and per-app wording for free, keyed like Ecto's `{msg, opts}` tuples).
- Adopt `loc` tuples as the universal form path; derive HTML `name` (`user[addresses][0][street]`), `id` and error lookup from the same tuple. Strip union tags from `loc` when mapping.
- Support `ValidationError.from_exception_data` + `InitErrorDetails` as the documented way to add field-targeted errors in `model_validator`s, and expose a pyview helper (`errors.add(loc, type, msg, ctx)`) on the changeset for handler-side errors (e.g. "email taken") that don't go through Pydantic at all.
- Read `FieldInfo` (+ `model_json_schema()` `format`) for widget selection, labels (`title`), help text (`description`), placeholders (`examples`), required (`is_required()`), and `json_schema_extra` for explicit widget overrides.
- Discriminated unions (string and callable `Discriminator`/`Tag`) as the conditional-section primitive; the tag field becomes the select that swaps the sub-form.

**Adapt**
- Add a pre-Pydantic normaliser: decode `a[b][0][c]` keys, `''` -> omit (so defaults apply) or `None` for `Optional`, absent checkbox -> `False` for `bool` fields, `list[...]` from repeated keys, strip `_target/_csrf_token/_unused_*`. Consider `str_strip_whitespace=True` recommendation.
- Validate the whole model on every `phx-change` (~14 µs) and filter errors by touched paths; do not use `experimental_allow_partial`. Offer `validate_assignment`/cached per-field `TypeAdapter` for single-field live checks.
- Keep raw submitted values (`params`) separate from `changes` (validated) exactly like Ecto: raw values re-render inputs; validated values are what `model` is built from.

**Avoid**
- Building on `model_validate_strings`, `experimental_allow_partial` or the pipeline API — wrong semantics or unstable.
- Relying on `info.data` for cross-field rules in user models; recommend the after-validator + `from_exception_data` pattern.
- Assuming Pydantic will ever run async checks (uniqueness lookups belong in the LiveView handler, added via the changeset error helper).

## Sources (repo paths / files actually read)

- `repos/pydantic/docs/concepts/validators.md` (Raising validation errors, Validation info/data/context, Ordering, Special types incl. `PydanticUseDefault`)
- `repos/pydantic/docs/concepts/fields.md` (Inspecting model fields, Deprecated fields section list)
- `repos/pydantic/docs/concepts/alias.md` (`validate_by_alias`/`validate_by_name`, `AliasPath`/`AliasChoices`)
- `repos/pydantic/docs/concepts/unions.md` (callable `Discriminator`/`Tag`, Union Validation Errors)
- `repos/pydantic/docs/concepts/experimental.md` (Pipeline API, Partial Validation + limitations)
- `repos/pydantic/docs/concepts/models.md` (Validating data, `model_validate_strings`, `model_construct`, `model_fields_set`)
- `repos/pydantic/docs/concepts/strict_mode.md`, `docs/api/standard_library_types.md` (bool string rules)
- `repos/pydantic/docs/concepts/dataclasses.md`, `type_adapter.md`, `performance.md`, `json_schema.md`, `types.md` (MISSING), `HISTORY.md` (v2.10–v2.13)
- Installed `pydantic 2.13.4` / `pydantic_core 2.46.4` introspection: `FieldInfo.__slots__`, `Field` signature, `ValidationInfo`, `ValidationError`, `InitErrorDetails`/`ErrorDetails`, `core_schema.ErrorType`, `PydanticKnownError.message_template`
- Experiments: `scratchpad/proto/exp1_pydantic_errors.py`, `exp2_coercion.py`, `exp4_field_targeted_errors.py`, `exp5_error_catalog.py`, `exp6_pydantic_facts.py`
