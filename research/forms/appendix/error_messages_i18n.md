# Error model & messages across libraries: codes vs messages, params, i18n, labels, nested paths — with a recommended design for pydantic-based forms

Versions researched (2026-09-12): Ecto 3.12/Phoenix 1.7 (reused from `ecto_changeset.md`, `liveview_forms.md`), Rails `main` (activemodel `error.rb`, `errors.rb`, `locale/en.yml`), Django 5.2.17, Laravel 12.x `validation.php`, Spring Framework `main` `DefaultMessageCodesResolver`, Hibernate Validator (search summaries), FluentValidation `docs/configuring.md`, Zod v4 (`packages/zod/src/v4/core/errors.ts`), Standard Schema spec, FormKit (`packages/validation`, `packages/i18n`), vee-validate 4 (search), react-hook-form 7 types, Superforms 2.30, Conform (reused), Rust `validator` (Keats), GOV.UK Design System error-message guidance, pydantic 2.13.4 + pydantic-core (live runs), pydantic-i18n 0.4.x.

## TL;DR

- **Every mature library separates *code* + *params* from *message*, and translates late.** Ecto `{msg, [validation: :length, count: 3]}`, Rails `errors.details → {error: :too_short, count: 3}`, Django `ValidationError(msg, code="min_length", params={...})`, Rust `ValidationError{code, message: Option, params: HashMap}`, Zod v4 issues `{code:"too_small", minimum, origin, inclusive, path, message}`, FluentValidation `{PropertyName}/{MinLength}` placeholders. Message-only libraries (react-hook-form `FieldError{type, message}`, Superforms `string[]`, Conform v1 `string[]`) are the ones whose docs devote pages to i18n workarounds.
- **pydantic-core already emits exactly this shape**: `{"type": "string_too_short", "loc": ("addrs", 0, "zip"), "msg": "...", "input": ..., "ctx": {"min_length": 2}}` — `type` is the code, `ctx` are the params, `msg` is a fallback template. `PydanticCustomError("reserved_name", "Name '{name}' is reserved", {"name": v})` lets user validators produce the same triple. pyview should normalise this, not invent a parallel error type.
- **Labels are the hard part of good messages, not plurals.** GOV.UK: messages must "directly include language from the question or fieldset label" ("Enter your first name", "Date you started the course must be after 31 August 2017"); Rails and Laravel inject `%{attribute}` / `:attribute` via `human_attribute_name` / `attributes => []`; Django deliberately omits the label ("This field is required."). Derive labels from `Field(title=...)` → alias → `pretty_name`, and make `{label}` a guaranteed template param.
- **Plurals belong to gettext, not the catalog**: Rails `too_short: {one:, other:}` in YAML, Django `ngettext_lazy(sing, plur, "limit_value")`, Phoenix `Gettext.dngettext(..., msg, msg, count, opts)`; only Zod hand-rolls (`${adj}${issue.maximum} ${sizing.unit}`).
- **Override precedence is a lookup chain, universally most-specific-first**: Spring `code.object.field → code.field → code.type → code`; Rails `activemodel.errors.models.User.attributes.name.too_short → ...models.User.too_short → errors.messages.too_short`; Laravel `custom.attribute.rule`; Django per-field `error_messages={"required": ...}`. Copy that chain (`field.code` → `Model.code` → `code`).
- **Nested paths**: all path-based libraries strip list indices when *looking up* messages (Rails `attribute.remove(/\[\d+\]/)`, Spring emits both `groups[0].name` and `groups.name` codes) but keep them when *addressing* the field. pydantic `loc` additionally contains union-member tags (`("pet","Cat","lives")`, `("n","int")`) that must be removed before the path becomes an HTML name (`pet[lives]`), and model-level errors have `loc == ()` (form-level, Django's `NON_FIELD_ERRORS = "__all__"`, Superforms `_errors`, Conform `''`).
- **pydantic-i18n is a regex-over-English-strings hack** (`re.escape(msg).replace(r"\{\}", "(.+)")` then `.format(*placeholders)`), falling back to translating the `type` string. Do not depend on it; a `type → template` catalog is strictly better because `ctx` gives the params natively.
- The prototype in `proto/pyview_errors_proto.py` (real output below) produces `first_name → "First name must be at least 2 characters"`, `addrs[0][zip] → "ZIP code is not in the right format"`, `free[lives]` from a smart-union loc, `age → "You must be 18+ to sign up"` via a per-field override, and `"" / id=form → "Ninety-nine is not allowed"` for a `model_validator`.

## Mental model & core abstractions

Three questions each library answers: (1) *what is an error?* (a code with params, or a string), (2) *where is it attached?* (flat field name, dotted/bracket path, tree), (3) *when does the string get made?* (at validation time, at render time, on the client).

| Library | Error record | Attached at | Message made | Label injection | Plurals | Override chain |
|---|---|---|---|---|---|---|
| Ecto/Phoenix | `{field, {"tpl %{count}", [validation: :length, count: 3, kind: :min]}}` | keyword list on changeset; children nested in `changes` | render time, `translate_error/1` (`Gettext.dngettext`) | none built in (`<.input label=>`) | Gettext | `validate_*(message: {"tpl", opts})`, `add_error/4` |
| Rails | `Error(attribute, type=:too_short, options={count:3})`; `details → {error: :too_short, count: 3}` | flat symbol; nested via `"posts.title"`/`posts[0].title` in `full_message` | lazily in `Error#message` via I18n | `%{attribute}` = `human_attribute_name` (`activemodel.attributes.user.name`) | YAML `one/other` | model/attr/type keys (see below) + `errors.format` |
| Django | `ValidationError(message, code, params)`; `error.message % error.params` in `__iter__` | `form.errors[name] → ErrorList`; `"__all__"` non-field | at raise time (lazy `gettext_lazy`) but `code` survives | none (messages are label-free) | `ngettext_lazy(..., "limit_value")` in validators | `Field(error_messages={code: str})` merges over MRO `default_error_messages`; `run_validators` rewrites `e.message = self.error_messages[e.code]` |
| Laravel | rule name + `:attribute :min :max :other :values :date` placeholders, per-type variants `min => [array, file, numeric, string]` | dotted key `users.0.email` (unverified: wildcards `users.*.email`) | at validation, from `lang/en/validation.php` | `'attributes' => []` map; `custom.attribute.rule` | none in file (per-type variants instead) | `custom.attr.rule` → `rule` |
| Spring | `FieldError(objectName, field, rejectedValue, codes[], args[], defaultMessage)` | bean path with indices | `MessageSource` lookup over the codes array | `args` | `MessageFormat` | `code.object.field`, `code.field`, `code.type`, `code` (+ index-stripped variants) |
| Jakarta/Hibernate | constraint annotation `message="{javax...Size.message}"` template; `{min}` attributes, `${validatedValue}` EL, `${formatter.format('%1$.2f', validatedValue)}` | property path `addresses[0].zip` | `MessageInterpolator` at validation; bundles `ValidationMessages.properties` > `ContributorValidationMessages.properties` > built-in | none (path only) | none (EL) | per-annotation `message=`, resource bundle key |
| FluentValidation | `ValidationFailure{PropertyName, ErrorMessage, ErrorCode, AttemptedValue, FormattedMessagePlaceholderValues}` (last unverified) | `PropertyName` path `Addresses[0].Zip` | at validation via `LanguageManager` | `{PropertyName}` (`.WithName("Zip code")` changes display only; `.OverridePropertyName` changes the key) | none | `.WithMessage("{PropertyName} needs {MinLength}")`, `.WithErrorCode` |
| Zod v4 | issue `{code:"too_small", origin:"string", minimum:2, inclusive:true, path:["addrs",0,"zip"], input, message}` | `path: PropertyKey[]`; `treeifyError` → `{errors:[], properties:{...}, items:[...]}`, `flattenError` → `{formErrors, fieldErrors}` | at parse time via `$ZodErrorMap: (issue) => {message} | string | undefined` chain (schema `error:` → per-parse `error:` → global locale) | none (locales say "expected string to have >=2 characters") | locale function computes (`Sizable[origin].unit`) | schema-level `error`, `z.config(locale)` |
| Standard Schema | `Issue{message, path?: (PropertyKey | {key})[]}` — message-only by contract | path | inside the library | – | – | – |
| FormKit / vee-validate | message *functions*: `FormKitValidationMessages = {[rule]: string | ({node, name, args}) => string}`; vee-validate `configure({generateMessage: (ctx:{field, value, form, rule:{name, params}}) => string})`, `localize({en:{messages:{min:"{field} must be 0:{min}"}, names:{}, fields:{}}})` | field name | render time on client | `name`/`field` param | in function | per-locale `messages`, `names`, `fields` |
| react-hook-form | `FieldError{type, message?, types?, ref?, root?}` — message-only | nested `errors.addrs[0].zip` object | at validation | – | – | resolver |
| Superforms / Conform | `ValidationErrors = {_errors?: string[]} & nested` / `Record<path, string[] | null>` with `''` for form | dotted/bracket path | at validation (`parseWithZod({formatError})` can return any shape) | – | – | zod error map |
| Rust `validator` | `ValidationError{code: Cow<str>, message: Option<Cow<str>>, params: HashMap<Cow<str>, serde Value>}`; `ValidationErrorsKind::{Struct(Box), List(BTreeMap<usize, Box>), Field(Vec)}` | tree | never (consumer formats) | – | – | `#[validate(length(min=1, code="...", message="..."))]` |
| pydantic-core | `{type, loc, msg, input, ctx?, url}`; `PydanticCustomError(type, msg_template, ctx)` | `loc` tuple incl. list indices *and* union tags | at validation (English), `ctx` retained | `Field(title=)` unused by messages | none | `PydanticCustomError`, `ValidationError.errors()` post-processing |

**Rails lookup chain, verbatim** (`activemodel/lib/active_model/error.rb`, `generate_message`):

```ruby
options = { model: base.model_name.human, attribute: base.class.human_attribute_name(attribute, { base: base }), value: value, object: base }.merge!(options)
attribute = attribute.to_s.remove(/\[\d+\]/)               # strip list indices for lookup
defaults = base.class.lookup_ancestors.flat_map do |klass|
  [ :"#{i18n_scope}.errors.models.#{klass.model_name.i18n_key}.attributes.#{attribute}.#{type}",
    :"#{i18n_scope}.errors.models.#{klass.model_name.i18n_key}.#{type}" ]
end
defaults << :"#{i18n_scope}.errors.messages.#{type}"
# later: errors.attributes.<attr>.<type>, errors.messages.<type>; full_message uses errors.format "%{attribute} %{message}"
```

and `en.yml`: `too_short: {one: "is too short (minimum is 1 character)", other: "is too short (minimum is %{count} characters)"}`, `confirmation: "doesn't match %{attribute}"`, `format: "%{attribute} %{message}"`. Note `full_message` returns `message` unchanged for `attribute == :base` (form-level).

**Spring code hierarchy** (`DefaultMessageCodesResolver` javadoc): field `name` inside `user.groups[0]` with code `typeMismatch` yields, in order, `typeMismatch.user.groups[0].name`, `typeMismatch.user.groups.name`, `typeMismatch.groups[0].name`, `typeMismatch.groups.name`, `typeMismatch.name`, `typeMismatch.java.lang.String`, `typeMismatch`. That is the most complete "specific → generic, with and without indices" chain in the survey.

## Data in (naming, parsing, coercion, nested/lists)

Only the path aspects matter here. Path grammars per library: Phoenix `user[addresses][0][city]` (indices explicit), Conform `todos[0].content` / `tags[]`, Laravel/Zod dotted `addrs.0.zip`, Rails `posts[0].title` in errors but `post[posts_attributes][0][title]` in HTML names, Spring `groups[0].name`, Hibernate `addresses[0].zip`. All of them agree on one thing: **the error path and the HTML name are two renderings of one canonical tuple**. pydantic's `loc` is that tuple *plus* noise:

```
# real pydantic 2.13.4 output (proto/exp5, exp run 2)
int_parsing   ('pet', 'Cat', 'lives')   # smart union: class name inserted
literal_error ('pet', 'Dog', 'kind')    # one error per union member tried
int_from_float ('n', 'int'); string_type ('n', 'str')   # primitive union: type name inserted
int_parsing   ('items', 1)              # list index
union_tag_invalid ('pet',) ctx={'discriminator': "'kind'", 'tag': 'cow', 'expected_tags': "'cat', 'dog'"}   # discriminated union: no tag segment
value_error   ()                        # model_validator -> form-level
```

Discriminated unions (`Field(discriminator="kind")`) put errors at the *member's* field path with no tag segment, which is what you want; smart unions insert the member class name and produce one error per member — noise that must be collapsed (see design).

## Validation & error model

**Codes vs messages.** Django's design is the clearest statement of why both are needed: `ValidationError.__init__(self, message, code=None, params=None)`; `Field.run_validators` catches `ValidationError` and does `if hasattr(e, "code") and e.code in self.error_messages: e.message = self.error_messages[e.code]` — the *code* is the override key, the *message* is a default, `params` are interpolated in `__iter__` (`message %= error.params`). Validators ship pluralised templates: `MinLengthValidator.message = ngettext_lazy("Ensure this value has at least %(limit_value)d character (it has %(show_value)d).", "... characters ...", "limit_value")`, `code = "min_length"`, raised as `ValidationError(self.message, code=self.code, params={"value": value, "limit_value": ..., "show_value": ...})`. Django's field-level messages never mention the label, which is why every Django project ends up wrapping them.

**Zod v4** formalises the chain of error maps: `$ZodErrorMap = (issue: $ZodRawIssue) => { message: string } | string | undefined | null` — returning `undefined` defers to the next map (schema → parse call → global locale). Issues carry structured params per code (`too_small: {origin, minimum, inclusive}`), and locales are *functions* (`locales/en.ts`: `Too small: expected ${issue.origin} to have ${adj}${issue.minimum} ${sizing.unit}`). `treeifyError(error, mapper?)` and `flattenError(error, mapper?)` accept a mapper so consumers can keep the whole issue rather than the string. `prettifyError(StandardSchemaV1.FailureResult)` proves the Standard Schema issue (`{message, path?}`) is the lowest common denominator, not the ideal.

**FormKit / vee-validate** push the "message is a function of (label, params)" idea to the client: FormKit `between({ name, args }) { return \`${s(name)} must be between ${a} and ${b}.\` }` (`packages/i18n/src/locales/en.ts`), with `FormKitValidationI18NArgs = [{node, name, args, message?}]`; vee-validate `configure({generateMessage: ctx => ...})` receives `{field, value, form, rule: {name, params}}`, and `@vee-validate/i18n`'s `localize` reads `{messages, names, fields}` per locale so a label can be renamed per locale and per form (`fields: {email: {required: "..."}}`).

**Laravel** is the best example of *per-type message variants*: `'between' => ['array' => 'The :attribute field must have between :min and :max items.', 'file' => '... kilobytes.', 'numeric' => '... between :min and :max.', 'string' => '... characters.']` — same rule, four templates keyed by the value's type. pydantic already encodes this distinction in the *type string* (`string_too_short` vs `too_short` with `ctx.field_type = "List"` vs `bytes_too_short`), so a flat catalog suffices.

**Hibernate** shows what full EL costs: `'${validatedValue}' is an invalid name. It must be minimum {min} chars and maximum {max} chars` and `${formatter.format('%1$.2f', validatedValue)}` — powerful, but the interpolator is a mini-language. Python `str.format_map` with a safe dict covers 95% of that.

**GOV.UK content rules** (`src/components/error-message/index.md`, the only *content* standard in the set): include the label's words; "Describe what has happened and tell them how to fix it"; do not use "please", "sorry", "valid"/"invalid"; instructions for empty fields ("Enter your first name") and descriptions for constraint failures ("First name must be 35 characters or less"); use the same text next to the field and in the error summary; prepend a visually hidden "Error:" for screen readers; do not clear fields on error. These rules directly contradict pydantic's defaults ("Input should be a valid integer, unable to parse string as an integer"), so a pyview catalog is not optional polish, it is the difference between usable and unusable defaults.

**Timing.** Every server-side library builds the error record at validation time and stringifies late (Ecto, Rails lazily in `Error#message`, Django lazy strings). Zod/FormKit/vee-validate stringify eagerly but from structured issues. Nobody serialises final strings into state and then tries to re-translate — except pydantic-i18n, whose `_translate` regex-matches the English `msg` against `re.escape(key).replace(r"\{\}", "(.+)")` patterns, then re-`format`s captured groups into the translated string, with `type_search=True` falling back to translating `error["type"]`. It works only while pydantic's English wording is stable, and it cannot add a label.

## Form state (bound/unbound, touched/used, attempted values)

Out of scope here except for one field in the record: **attempted value**. Rails passes `value:` into the template options (`"%{value} is not a valid email"` works), FluentValidation has `{PropertyValue}` and `AttemptedValue`, Hibernate `${validatedValue}`, Zod `issue.input`, pydantic `error["input"]`. Keep `input` on the normalised record; it is also what `value=` should re-render for a field that failed *coercion* (pydantic never returns a partially-built model, so the raw params are the only source of the attempted value — same as Phoenix `FormField.value` precedence "changes → params → data").

## Rendering & customization & styling

Full-message formatting: Rails `errors.format: "%{attribute} %{message}"` with `i18n_customize_full_message` allowing per-model/attribute `format` keys; `full_messages` for the error summary, `messages_for(attribute)` next to the field. GOV.UK requires identical text in both places, so a pyview design should produce **one** string per error and use it in both the inline `<p id="first_name-error">` and the summary `<a href="#first_name">`. Conform names these ids mechanically (`id = \`${formId}-${name}\``, `errorId = \`${id}-error\``), Phoenix `field.id = "user_addresses_0_city"`. The 0.20 client's `phx-feedback-for="<input name>"` needs the *HTML name* (`user[addresses][0][city]`) — one more reason the normalised path must render to that exact string.

## Nested / dynamic / conditional

Rails strips `[\d+]` from the attribute *only for message lookup* (`attribute.remove(/\[\d+\]/)`), keeping `posts[0].title` in `details`. Spring generates both indexed and unindexed codes. Rust `validator` keeps a real tree (`Struct/List/Field`). Zod `treeifyError` gives `{errors, properties, items}`. Ecto stores child changesets with their own `errors` and flattens via `traverse_errors` (shape inconsistency documented in `ecto_changeset.md`). For conditional nesting (pydantic discriminated unions), pydantic's own behaviour is already right: the `union_tag_invalid` error lands on the parent path (`("pet",)`) with `ctx.expected_tags`, and member-field errors land on `("pet","lives")`. Only smart unions need cleanup.

## DX highlights with real code

1. **Ecto custom message keeping params** (`ecto_changeset.md`): `validate_length(cs, :title, min: 6, message: {"needs %{count}+ chars", extra: :info})` — `message/4` merges extra opts so i18n still has `count`.
2. **Rails** `errors.add(:name, :too_short, count: 3)`; `errors.details[:name] → [{error: :too_short, count: 3}]`; `errors.full_messages → ["Name is too short (minimum is 3 characters)"]` (`errors.rb` `add/details/full_messages`).
3. **Django** per-field override without touching the validator: `forms.CharField(min_length=3, error_messages={"min_length": "Use at least %(limit_value)d letters"})` (`fields.py` L169-171 merges `default_error_messages` over the MRO then `error_messages`).
4. **Zod v4** deferring error map: `z.string().min(2, { error: (iss) => iss.code === "too_small" ? \`At least ${iss.minimum}\` : undefined })` (`$ZodErrorMap` contract, `errors.ts` L215-218).
5. **pydantic** structured custom error (run in `proto/exp5_error_catalog.py`): `raise PydanticCustomError("reserved_name", "Name '{name}' is reserved", {"name": v})` → `type='reserved_name' ctx={'name': 'bob'} msg="Name 'bob' is reserved"`.
6. **FormKit** message function with label: `between({ name, args }) => \`${s(name)} must be between ${a} and ${b}.\``.

## Pain points & criticisms

- pydantic-i18n's regex approach breaks when a translated message's placeholder count differs (their own comment: "If we have too few, we have to handle the IndexError and return the un-translated text"), and it cannot inject labels or pluralise.
- Django messages are label-less and inconsistent in voice ("This field is required." vs "Enter a whole number."); Rails messages are fragments that only read well after `%{attribute} %{message}` concatenation, which breaks in languages where the attribute is not sentence-initial (`i18n_customize_full_message` exists because of this).
- Zod's structured issues are excellent but message-only once they cross Standard Schema (`Issue{message, path}`), so Conform/Superforms consumers lose codes unless they use `formatError`/`formatIssues`.
- Ecto's `traverse_errors` shape inconsistency for embeds (list-of-maps vs list-of-tuples) and Rails' flattening of nested attribute names into `"posts.title"` strings are both symptoms of not having a canonical path tuple.
- vee-validate issues #2871/#2898: `{_field_}` placeholder left unrendered when a field has no label; `{length}` params passed wrongly for custom messages — label derivation and param naming are where users hit bugs.
- FluentValidation's `WithName` vs `OverridePropertyName` split (display label vs error key) is a frequent confusion but also the right distinction: label ≠ path.

## Lessons for pyview — steal / adapt / avoid

**Recommended normalised record** (prototype `proto/pyview_errors_proto.py`, real output in TL;DR):

```python
@dataclass(frozen=True)
class FormError:
    path: tuple[str | int, ...]   # pydantic loc minus union-tag segments; () = form-level
    code: str                     # pydantic-core `type` or PydanticCustomError type
    params: dict[str, Any]        # ctx + {"label": ...}; ValueError/AssertionError instances stringified
    message: str                  # pydantic `msg`, used only when the catalog has no entry
    input: Any = None             # attempted value
    @property
    def name(self) -> str: ...    # "addrs[0][zip]"  (Phoenix grammar; "" for form-level)
    @property
    def id(self) -> str: ...      # "addrs_0_zip"    ("form" for form-level)
```

**Default catalog** keyed by verified pydantic-core type strings and `ctx` keys (from the live run): `missing`, `string_type`, `string_too_short{min_length}`, `string_too_long{max_length}`, `string_pattern_mismatch{pattern}`, `int_parsing`, `int_type`, `int_from_float`, `float_parsing`, `float_type`, `finite_number`, `bool_parsing`, `bool_type`, `greater_than{gt}`, `greater_than_equal{ge}`, `less_than{lt}`, `less_than_equal{le}`, `multiple_of{multiple_of}`, `enum{expected}`, `literal_error{expected}`, `date_parsing`/`date_from_datetime_parsing{error}`, `date_past`, `date_future`, `datetime_parsing`/`datetime_from_date_parsing{error}`, `time_parsing`, `decimal_parsing`, `decimal_max_digits{max_digits}`, `decimal_max_places{decimal_places}`, `too_short{field_type,min_length,actual_length}`, `too_long{field_type,max_length,actual_length}`, `list_type`, `extra_forbidden`, `union_tag_invalid{discriminator,tag,expected_tags}`, `union_tag_not_found{discriminator}`, `url_parsing`, `uuid_parsing`, `value_error{error}`, `assertion_error{error}`. Templates follow GOV.UK voice: `"{label} is required"`, `("{label} must be at least {min_length} character", "... characters", "min_length")`, `"Select {label}"` for booleans, `"{label} must be a real date"`. Unknown types fall back to pydantic's `msg` so nothing ever crashes.

**Override hooks, most-specific first** (Spring/Rails chain, Django keys): `overrides["addrs[0][zip].string_pattern_mismatch"]` (exact name) → `overrides["addrs.zip.string_pattern_mismatch"]` (indices stripped, Rails-style) → `overrides["string_pattern_mismatch"]` (app-wide) → catalog. Attach per-model overrides via `model_config["pyview_errors"]` or a `class Form(PyviewForm[Signup]): messages = {...}`; per-request hooks as `list[Callable[[FormError], str | None]]` (Zod's "return None to defer"). Per-rule custom messages inside pydantic stay `PydanticCustomError(code, tpl, ctx)` — never bare `ValueError("string")` for anything that needs translation; document that `ValueError` messages are shown verbatim (`value_error` → `"{error}"`).

**i18n strategy**: templates are `str.format`-style with `{label}`, translate with `gettext(tpl)` / `ngettext(sing, plur, n)` where the catalog entry is a `(sing, plur, count_key)` tuple; ship `errors.pot` extracted from the catalog like Phoenix's `priv/gettext/errors.pot`. Babel's `Translations.ngettext` slots in as the two callables; no framework lock-in. Do not regex-translate English messages (pydantic-i18n).

**Labels**: `Field(title=)` → `alias` → `pretty_name`-style humanise (`"first_name" → "First name"`); nested labels resolved by walking `model_fields` through lists and unions (prototype `label_for`); allow `labels={"addrs.zip": "Postcode"}` overrides per form (vee-validate `names`/`fields`, Laravel `attributes`). Expose `field.label` to templates so the `<label>` text and the error text always match (GOV.UK "match up error messages to labels").

**Full message vs inline**: one string, used in both the inline message and the error summary; render `<p id="{id}-error">` with a visually hidden `Error:` prefix and `aria-describedby` on the input (GOV.UK + Conform `errorId`). Never concatenate `"%{attribute} %{message}"` at runtime — put the label inside the template so word order is translatable.

**loc → name/id mapping**: strip union-member tags (class names for smart unions, `int/str/...` for primitive unions) using the model's type graph, keep list indices, collapse smart-union duplicates to one error on the parent path when *every* member failed at the tag level (prototype leaves them; do the collapse), keep `()` as form-level under key `""` (Conform) and render it in the summary only.

**Avoid**: message-only error dicts (`dict[str, str]`) — the current `ChangeSet.errors[loc[0]] = msg` throws away `type`, `ctx` and nesting; Django-style label-free defaults; Rails-style runtime attribute+message concatenation; Hibernate-style expression language in templates; treating pydantic's `msg` as the user-facing string (it fails every GOV.UK rule).

## Sources

- `research/ecto_changeset.md`, `research/liveview_forms.md`, `research/conform.md` (reused)
- `repos/rails/activemodel/lib/active_model/error.rb` (`full_message`, `generate_message`, `details`), `errors.rb` (`add`, `details`, `full_messages`), `locale/en.yml`
- `pkgs/py/django/core/exceptions.py` (`ValidationError.__init__`, `__iter__`, `NON_FIELD_ERRORS`), `forms/fields.py` (L93-197), `core/validators.py` (`MinLengthValidator`), `forms/utils.py` (`pretty_name`), `forms/forms.py` (`add_error`)
- https://raw.githubusercontent.com/laravel/framework/12.x/src/Illuminate/Translation/lang/en/validation.php
- https://raw.githubusercontent.com/spring-projects/spring-framework/main/spring-context/src/main/java/org/springframework/validation/DefaultMessageCodesResolver.java
- Hibernate Validator message interpolation (search summaries; docs.hibernate.org chapter 4 blocked; `engine/src/main/resources/org/hibernate/validator/ValidationMessages.properties`)
- https://raw.githubusercontent.com/FluentValidation/FluentValidation/main/docs/configuring.md
- https://raw.githubusercontent.com/Keats/validator/master/validator/src/types.rs
- `repos/zod/packages/zod/src/v4/core/errors.ts` (`$ZodIssueBase`, `$ZodErrorMap`, `too_small`, `flattenError`, `treeifyError`, `prettifyError`), `locales/en.ts`
- `repos/standard-schema/packages/spec/src/index.ts` (`Issue`, `PathSegment`)
- `repos/formkit/packages/validation/src/validation.ts` (`FormKitValidationMessages`, `FormKitValidationI18NArgs`), `packages/i18n/src/locales/en.ts`
- vee-validate i18n (search summaries: `configure({generateMessage})`, `localize`, issues #2871, #2898)
- `pkgs/npm-superforms/package/dist/superValidate.d.ts` (`ValidationErrors`), `pkgs/npm-react_hook_form/.../types/errors.d.ts` (`FieldError`)
- `repos/govuk-design-system/src/components/error-message/index.md`
- `repos/pydantic/docs/errors/validation_errors.md` (type list), live runs `proto/exp5_error_catalog.py`, `proto/pyview_errors_proto.py` (pydantic 2.13.4)
- `pkgs/py-error_messages_i18n/pydantic_i18n/main.py` (`PydanticI18n._init_pattern`, `_translate`, `translate`)
