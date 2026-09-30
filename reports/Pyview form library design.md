# Build pyview forms on a changeset spine

A great pyview form library would have three layers. The first is an Ecto-style changeset whose cast-and-validate step is pydantic. It is fed by a schema-aware decoder for the bracket-named payloads that the Phoenix client already sends. The second is a Phoenix-style `Form`/`FormField` view-model. It owns every attribute that affects correctness: name, id, displayed value, visible errors, ARIA links and HTML constraints. Because the view-model owns those, a developer can move from `{{ form.render() }}` to hand-written HTML without re-implementing any of the wiring. The user's instinct about changesets is right, and for a specific reason. Ecto keeps raw params, original data, typed changes and errors-as-data apart, and it gates error display on an `action` field. pyview's current 67-line `ChangeSet` has none of these pieces.

Nested lists and discriminated unions should be encoded in the submitted params themselves, using Ecto's `sort_param`/`drop_param` or Conform-style intents, not in server-side mutation. The Phoenix client that pyview bundles replays the whole form after a reconnect, and anything not in the params is lost. The third layer, styling, should come from server-rendered state attributes (`aria-invalid`, `data-invalid`), a swappable class provider, and templates that users can eject. It should not come from a Python layout DSL.

The distance from today is large. pyview decodes forms with a bare `parse_qs`, which turns `user[addresses][0][city]` into one literal key and drops fields the user cleared. Its typed binder raises a fatal `ValueError` on half-filled forms, and its `ChangeSet` crashes with `KeyError` on submit. No Python library has shipped this target. FastUI was archived after stalling on arrays of objects, and fh-pydantic-form is the closest prior art. So pyview has an open lane. LiveView's server-held state also means that what JS libraries treat as a "no-JS fallback" is pyview's main path.

The recommended order:
1. Plumbing: a lossless decoder, blank-preserving payloads, and form binding that never crashes.
2. The changeset and a headless field API.
3. Lists, unions and uploads.
4. Themes, auto-render and an eject CLI, last.

## pyview today drops data before validation even starts

Every form event in pyview passes through one branch of the websocket handler, `value = parse_qs(value)` ([ws_handler.py L186-191](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/ws_handler.py#L186-L191)). That call returns a **flat `dict[str, list[str]]`**, which has three effects:
- `user[addresses][0][city]` survives only as a literal key.
- `tags[]` keeps its brackets.
- `keep_blank_values` is not set, so **a field the user just cleared disappears**. "Cleared" then looks the same as "never rendered".

The research team confirmed this empirically against HEAD `9b32095`: `email=` was absent from the decoded dict, and nested keys stayed flat ([ws_handler.py L190](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/ws_handler.py#L190)). `_target` arrives as an ordinary key mixed in with user fields. Click, key and hook events arrive as JSON dicts of plain strings instead, so handlers see two payload shapes ([event-handling.md L255](https://github.com/ogrodnek/pyview/blob/9b32095/docs/core-concepts/event-handling.md#L255)).

The typed binder added in December 2025 sits on top of that lossy dict. It resolves injectables, builds stdlib dataclasses field-by-field from the payload root, and converts scalars. It has **no pydantic model binding**: `ConverterRegistry.convert` returns pydantic models, enums, dates and Decimals unchanged. Every `ParamError` is escalated to `ValueError`, which ends the event ([binder.py L121-166](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/binding/binder.py#L121-L166), [converters.py](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/binding/converters.py#L24-L191), [helpers.py L136-144](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/binding/helpers.py#L136-L144)).

In a probe, a dataclass `F(name: str, email: str)` bound from a phx-change with a blank email raised "Missing required fields for F: email", because `parse_qs` had already dropped the blank ([binder.py L143-160](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/binding/binder.py#L143-L160)). Fatal binding is correct for a malformed click payload. It is wrong for a form the user is halfway through typing. LiveComponent `handle_event` skips the binder entirely; open [PR #126](https://github.com/ogrodnek/pyview/pull/126) targets that ([manager.py L211-240](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/components/manager.py#L211-L240)).

The existing `ChangeSet` is the seed of the right idea, but its behaviour doesn't hold up ([changesets.py](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/changesets/changesets.py#L1-L67)):
- **Change tracking:** `apply()` copies only the first value of the field named in `payload["_target"][0]`.
- **Error paths:** errors collapse to `str(loc[0])`, so `("addresses", 0, "city")` becomes `"addresses"`.
- **Error content:** errors are bare English strings.
- **State:** there is no initial data, no action, and no tests.
- **Submit crashes:** `apply()` raises `KeyError` on submit payloads, because the client sends no `_target` on submit. The docs' "Input Validation" pattern nevertheless calls `apply()` inside the submit handler ([event-handling.md L421-457](https://github.com/ogrodnek/pyview/blob/9b32095/docs/core-concepts/event-handling.md#L421-L457)).
- **`save()` fails on raw payloads:** the values are lists, so pydantic rejects them.

The two examples that validate both hand-write `name`, `id`, `value`, `phx-feedback-for` and an error lookup for every field, copy an SVG error block per field, and reset the form by rebuilding the whole context. The registration example never handles its own submit event ([plants.py L22-48](https://github.com/ogrodnek/pyview/blob/9b32095/examples/views/form_validation/plants.py#L22-L48), [registration.py L14-81](https://github.com/ogrodnek/pyview/blob/9b32095/examples/views/registration/registration.py#L14-L81)).

### Client constraints

The client imposes its own constraints. pyview bundles **phoenix_live_view 0.20.17**, which predates the `_unused_` params that LiveView 1.0 introduced ([package.json](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/assets/package.json), [LV v1.0 CHANGELOG](https://github.com/phoenixframework/phoenix_live_view/blob/v1.0/CHANGELOG.md)). The 0.20 client does implement `phx-feedback-for` by toggling a `phx-no-feedback` class, but pyview ships no CSS for that class, so the attributes in the examples do nothing ([app.js L1844-1876](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/static/assets/app.js#L1844-L1876)).

Form recovery after a reconnect is purely client-driven. It re-sends each `phx-change` form that has an `id`, and it sets `_target` to the first non-hidden input ([app.js L5760-5781](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/static/assets/app.js#L5760-L5781)). Two consequences follow:
- Handlers must rebuild state from the full payload, which `ChangeSet.apply` does not do.
- Every generated form needs a stable `id`.

The client also skips change events entirely for `type="number"` inputs whose value is invalid ([app.js L6600-6622](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/static/assets/app.js#L6600-L6622)). LiveView routes are GET-only, so `phx-trigger-action` would get a 405 ([pyview.py L74-80](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/pyview.py#L74-L80)).

### Rendering constraints

The two template engines constrain the rendering API differently:
- **Ibis** accepts method calls only with **positional Python-literal arguments**, parsed by `ast.literal_eval` and applied as `obj(*args)`. It has no macros. It resolves `a.b.c` by trying `getattr`, then `[key]`, then `[int(key)]` ([nodes.py L55-141](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/vendor/ibis/nodes.py#L55-L141), [context.py L75-94](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/vendor/ibis/context.py#L75-L94)).
- **t-strings** escape every interpolated value except `__html__` objects and nested `Template`s. They render `True` as the string `"True"`, and they have no attribute-spreading ([live_view_template.py L101-195](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/template/live_view_template.py#L101-L195)).

I confirmed one more trap directly in the code; the notes did not flag it. The first HTTP render of an Ibis view goes through `LiveTemplate.render`, which calls **`dataclasses.asdict(assigns)`**. That recursively turns any dataclass in the context into a plain dict. The connected websocket render uses the shallow `serialize()` instead ([live_template.py L32-36](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/template/live_template.py#L32-L36), [pyview.py L119](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/pyview.py#L119), [serializer.py](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/template/serializer.py)). A form object that is a dataclass, as `ChangeSet` is today, therefore loses its methods and properties on first paint. The dead render should switch to `serialize()` either way.

Finally, uploads are matched to their config by `qs["_target"][0]`, which must exactly equal the file input's name. A library that prefixes names as `signup[avatar]` would break that lookup unless it goes through the `data-phx-upload-ref` keys already present in `payload["uploads"]` ([uploads.py L466-477](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/uploads.py#L466-L477)).

| Gap today | What breaks | Where it gets fixed |
|---|---|---|
| Flat `parse_qs`, blanks dropped | Nested forms impossible; "cleared" equals "absent" | Keep the raw string at [ws_handler.py L189-191](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/ws_handler.py#L189-L191); new decoder |
| Fatal binding | phx-change on a half-filled form raises | New `FormParams` injectable via `BindContext.extra`; no validation inside the binder |
| Flat, `_target`-only `ChangeSet` | No nesting, `KeyError` on submit, recovery restores one field | New `pyview.forms.Form`; one-release compatibility shim |
| No markup helpers | Name repeated 3-4 times per input; bespoke error markup | `FormField` view-model plus Ibis and t-string adapters |
| 0.20.17 feedback model | `phx-feedback-for` inert; no `_unused_` | Server-side "used" tracking behind one function |
| `asdict` in the dead render | Dataclass view-models flattened on first paint | Use `serialize()` in `LiveTemplate.render` |
| Uploads keyed by `_target` | Prefixed file inputs miss their config | Look up by upload ref |

## The best libraries agree on five ideas and stumble in three places

Across Elixir, Python, JavaScript, Ruby, PHP, .NET and the functional tradition, the libraries that hold up converge on five ideas:
1. Keep what the user typed separate from the parsed value.
2. Treat errors as structured data keyed by path.
3. Gate error *visibility* separately from error *existence*.
4. Express structural edits (add, remove, reorder rows; switch variants) as data, with stable row identity.
5. Keep wiring in the library and markup in code the app owns.

They fail in the same three places:
- dynamic lists;
- what happens to the data of hidden or conditional fields;
- how much layout and styling to generate.

### Ecto changesets resonate because they separate four jobs and one flag

An Ecto changeset is an immutable value holding `data` (the original struct), `params` (raw external input), `changes` (only the cast fields that differ from `data`), `errors`, `valid?` and `action` ([Ecto.Changeset](https://github.com/elixir-ecto/ecto/blob/master/lib/ecto/changeset.ex)). It is built by a pipeline of plain functions:
- `cast` is the trust boundary. It is an allow-list: "you must explicitly list which data you accept".
- The `validate_*` steps append errors.
- `apply_action` commits only if the changeset is valid, and otherwise stamps an action onto it.

Errors are tuples such as `{"should be at least %{count} characters", [count: 3, validation: :length, min: 3]}`. Translation happens only at render time, which is how one error list serves Gettext, JSON APIs and the UI ([Phoenix 1.8 core_components](https://github.com/phoenixframework/phoenix/blob/v1.8/installer/templates/phx_web/components/core_components.ex.eex)).

The design's quiet masterstroke is the `action` field. Phoenix hides all errors while the action is `nil` or `:ignore`, so an empty "new" form is invalid but not covered in red. Setting `action: :validate` on the first change reveals them ([phoenix_ecto html.ex](https://github.com/phoenixframework/phoenix_ecto/blob/main/lib/phoenix_ecto/html.ex), [Phoenix.Component](https://github.com/phoenixframework/phoenix_live_view/blob/main/lib/phoenix_component.ex)).

On the render side, Phoenix defines a `FormData` protocol that turns any source into a `Form`, and `form[:field]` returns a `FormField{id, name, value, errors}`. Nesting is pure name and id concatenation: `user[addresses][0][street]` and `user_addresses_0_street`. The value precedence is **changes, then raw params, then data**, so an uncastable "12abc" is redisplayed from params. The protocol also derives HTML5 `required`, `minlength` and `min`/`max` from validations ([phoenix_html form.ex](https://github.com/phoenixframework/phoenix_html/blob/main/lib/phoenix_html/form.ex), [phoenix_ecto html.ex](https://github.com/phoenixframework/phoenix_ecto/blob/main/lib/phoenix_ecto/html.ex)).

Phoenix recommends rebuilding a fresh changeset from `(original data, all params)` on every `phx-change` rather than storing it: "changesets are meant to be single use" ([Phoenix.Component](https://github.com/phoenixframework/phoenix_live_view/blob/main/lib/phoenix_component.ex)). That habit is also what makes form recovery correct for free.

The downsides are worth porting deliberately rather than by accident. Meaning is spread across three maps. The cast permit-list duplicates the schema. Error timing needs two mechanisms, `action` and `used_input?`. Phoenix itself warns that `form[:field].value` "may either return a struct, a changeset, or raw parameters", which makes it "impractical for deriving or computing other properties" ([Phoenix.Component inputs_for docs](https://github.com/phoenixframework/phoenix_live_view/blob/main/lib/phoenix_component.ex)).

The mapping to pydantic is unusually clean:
- Cast and type validation collapse into one `TypeAdapter.validate_python` call.
- pydantic's `ValidationError.errors()` already yields a `loc` path tuple, a machine `type` and a `ctx` dict. That is Ecto's `{msg, opts}` with a nested path ([pydantic errors docs](https://github.com/pydantic/pydantic/blob/main/docs/errors/errors.md)).

### AshPhoenix.Form shows what a stateful tree buys and what it costs

Ash went the other way. `AshPhoenix.Form` is a **stateful, recursive form tree** that is meant to live in assigns and be updated in place with `validate/3`, `add_form/3`, `remove_form/3`, `sort_forms/3` and `submit/2`. It tracks `submitted_once?`, `touched_forms` and `changed?`, and it addresses subforms by path, either `[:locations, 0]` or the HTML name `form[locations][0]` ([AshPhoenix.Form](https://github.com/ash-project/ash_phoenix/blob/main/lib/ash_phoenix/form/form.ex)). Nested forms are inferred automatically by introspecting the action's `manage_relationship` arguments ([ash_phoenix nested-forms guide](https://github.com/ash-project/ash_phoenix/blob/main/documentation/topics/nested-forms.md)).

The pydantic analogue is obvious: introspect `list[SubModel]`, `SubModel | None` and discriminated-union fields to get auto-nested forms. The costs are a very large API surface and silent failure modes. For example, nested forms are not built unless `manage_relationship` is declared on the action itself ([ash_phoenix #382](https://github.com/ash-project/ash_phoenix/issues/382)). Two Ash ideas are worth copying even in an Ecto-shaped core: **path-addressed operations** and `errors(for_path: :all)`.

### Python libraries each solved one piece and none solved the whole

Each major Python library contributes one piece:
- **WTForms** gives every bound field `data`, `raw_data` and `object_data`, which is the right three-way split ([WTForms fields.rst](https://github.com/pallets-eco/wtforms/blob/main/docs/fields.rst)).
- **Django** gives errors with machine `code`s and an `__all__` bucket for form-level errors ([Django validation.txt](https://github.com/django/django/blob/main/docs/ref/forms/validation.txt)).
- **Django 5.0** added `as_field_group` (label, help, errors and widget in one call, with `aria-describedby` and `aria-invalid`) ([Django 5.0 notes](https://github.com/django/django/blob/main/docs/releases/5.0.txt)).
- **Django 5.2** made the `BoundField` class swappable at the project, form or field level ([Django 5.2 notes](https://github.com/django/django/blob/main/docs/releases/5.2.txt)).

The failures are equally instructive. The team verified these WTForms 3.2.2 behaviours locally ([wtforms list.py](https://github.com/pallets-eco/wtforms/blob/main/src/wtforms/fields/list.py)):
- index gaps survive into re-rendered names;
- `min_entries=1` means the user cannot delete the last row;
- a `FieldList` of `BooleanField`s with the middle box unchecked yields `[True, True, False]` instead of `[True, False, True]`.

Django formsets need a management form with `TOTAL_FORMS`/`INITIAL_FORMS` and JS cloning of an `empty_form` with a `__prefix__` placeholder. Errors of deleted forms are skipped, so error indices drift from form indices ([Django formsets.txt](https://github.com/django/django/blob/main/docs/topics/forms/formsets.txt)). This is the tax a stateless server pays to infer list shape from a POST. A LiveView server doesn't have to pay it.

Pydantic is nearly the whole engine, with HTML-specific gaps the team verified locally on 2.13.5 ([PyPI pydantic](https://pypi.org/project/pydantic/)):
- Lax mode accepts `"on"` for `bool`.
- `Annotated` metadata such as a custom `Widget("textarea")` is kept on `FieldInfo.metadata` and does not leak into `model_json_schema()`.
- `""` fails for `int | None` (`int_parsing`) and `date | None`.
- `""` stays `""` for `str | None`.
- Discriminated-union errors carry the **tag** in `loc`: `('payment', 'bank', 'iban')` points at a field whose HTML name has no `bank` segment ([pydantic unions docs](https://github.com/pydantic/pydantic/blob/main/docs/concepts/unions.md)).
- Partial validation is experimental, available only on `TypeAdapter`, and built for truncated JSON streams, so it is no answer for live forms ([pydantic experimental](https://github.com/pydantic/pydantic/blob/main/docs/concepts/experimental.md)).

The "here's my model, do the rest" attempts mostly stall on lists:
- **FastAPI** form models are flat. In a local test, a nested `addr.street` was silently ignored ([FastAPI form models](https://github.com/fastapi/fastapi/blob/master/docs/en/docs/tutorial/request-form-models.md)).
- **FastUI** generated forms from JSON Schema and raised `NotImplementedError('Array fields are not fully supported')` for arrays of objects ([FastUI json_schema.py](https://github.com/pydantic/FastUI/blob/main/src/python-fastui/fastui/json_schema.py)). It was archived in June 2026. Its author had written that he wanted rendering "to happen exclusively (or mostly) serverside, but that's a big rewrite" ([FastUI #368](https://github.com/pydantic/FastUI/issues/368), [FastUI repo](https://github.com/pydantic/FastUI)).
- **fh-pydantic-form**, built on FastHTML and HTMX, is the nearest prior art. It has nested models, lists with add, delete and reorder, and a renderer registry keyed by type, type name or predicate ([fh-pydantic-form](https://github.com/Marcura/fh-pydantic-form)).
- **Reflex**'s `Object.fromEntries(new FormData(...))` keeps only the last checked checkbox ([reflex #7342](https://github.com/reflex-dev/reflex/issues/7342)). The same class of bug appears in FastHTML's scalar-or-list `_formitem` ([fasthtml core.py](https://github.com/AnswerDotAI/fasthtml/blob/main/fasthtml/core.py)).

Together these show that decoding must be type-directed.

### JavaScript libraries rebuilt LiveView's loop and added intents and timing policies

The JS ecosystem has spent 2024 to 2026 moving toward what LiveView already has: the server returns `{values, errors}` and the client re-renders ([React useActionState](https://react.dev/reference/react/useActionState), [TanStack Form SSR](https://tanstack.com/form/latest/docs/framework/react/guides/ssr)).

**Conform** is the most transferable library:
- Every structural operation (validate, reset, update, insert, remove, reorder) is an **intent**, a string such as `insert({"name":"tasks"})` placed on a reserved submit-button name ([Conform intent button](https://github.com/edmundhung/conform/blob/main/docs/intent-button.md)).
- The server resolves the intent into a new target value, validates it, and reports back ([Conform resolveSubmission](https://github.com/edmundhung/conform/blob/main/docs/api/react/future/resolveSubmission.md)).
- The report can **`hideFields`**, so passwords are never echoed, and it drops files by default because a file input cannot be repopulated ([Conform report](https://github.com/edmundhung/conform/blob/main/docs/api/react/future/report.md)).
- Custom intents can implement "copy billing to shipping" ([Conform defineIntent](https://github.com/edmundhung/conform/blob/main/docs/api/react/future/defineIntent.md)).

**Superforms** contributes:
- A server-produced `SuperValidated {id, valid, posted, data, errors, constraints, message}`.
- The rule that a form which was never posted returns **no errors** ([Superforms API](https://superforms.rocks/api), [Superforms error handling](https://superforms.rocks/concepts/error-handling)).
- `_errors` for container-level errors on arrays ([Superforms nested data](https://superforms.rocks/concepts/nested-data)).

**Timing.** React Hook Form, TanStack Form, Conform and Superforms all converged on a **two-phase timing policy**:
- React Hook Form: `mode` plus `reValidateMode`, including `onTouched` ([RHF useForm](https://react-hook-form.com/docs/useform)).
- TanStack Form: `revalidateLogic({mode, modeAfterSubmission})` ([TanStack dynamic validation](https://tanstack.com/form/latest/docs/framework/react/guides/dynamic-validation)).
- Conform: `shouldValidate`/`shouldRevalidate`.
- Superforms: an `'auto'` mode described as "reward early, validate late" ([Superforms client validation](https://superforms.rocks/concepts/client-validation)).

**Row identity.** RHF requires `field.id`, not the index, as the key of a field-array row ([RHF useFieldArray](https://react-hook-form.com/docs/usefieldarray)).

**Hidden-field policy.** RHF's `shouldUnregister`, Formily's `x-visible` versus `x-hidden`, Conform's `PreserveBoundary` and RJSF's `omitExtraData` each answer "what happens to hidden data" explicitly, and differently ([RJSF form props](https://rjsf-team.github.io/react-jsonschema-form/docs/api-reference/form-props), [Conform PreserveBoundary](https://github.com/edmundhung/conform/blob/main/docs/api/react/future/PreserveBoundary.md)).

**Auto-generators.** The auto-generators split into a data schema, a UI schema and a renderer registry:
- JSON Forms selects renderers by **ranked tester functions**, such as `rankWith(3, scopeEndsWith('rating'))`, and expresses show/hide rules whose condition is itself a schema ([JSON Forms custom renderers](https://jsonforms.io/docs/tutorial/custom-renderers), [JSON Forms rules](https://jsonforms.io/docs/uischema/rules)).
- RJSF documents its limits: `oneOf`/`anyOf` properties "should not overlap" with outer properties, and `allOf` is dropped when incompatible ([RJSF internals](https://rjsf-team.github.io/react-jsonschema-form/docs/advanced-customization/internals)).
- AutoForm scopes itself honestly as "mostly meant as a drop-in form builder for your internal tools and simple forms" ([AutoForm](https://github.com/vantezzen/autoform)).

**Headless field components.** shadcn/ui now builds forms from a few copy-pasteable `Field`, `FieldLabel`, `FieldDescription` and `FieldError` primitives driven by `data-invalid`/`aria-invalid`, whatever the form library ([shadcn RHF guide](https://github.com/shadcn-ui/ui/blob/main/apps/v4/content/docs/forms/react-hook-form.mdx)).

### Server frameworks show where live forms hurt: arrays, lag and layout DSLs

**Rails** gives the canonical wire format: `person[address][city]`, `phone[]`, and "only one level of 'arrayness'". It also gives the hidden-input twin that makes unchecked checkboxes submit a value, `fields_for ..., index: address.id` for stable row identity, and `_destroy`/`reject_if: :all_blank` for list editing ([Rails form helpers guide](https://github.com/rails/rails/blob/main/guides/source/form_helpers.md)).

**simple_form** infers inputs from column type and name (`/email/` becomes `type=email`). It composes each field from a named **wrapper** pipeline of label, input, hint and error, and it overrides per field with `as:`, `wrapper:` and `input_html:` ([simple_form](https://github.com/heartcombo/simple_form)).

**Livewire** is the closest runtime analogue to pyview: public server properties, dot-path binding (`form.items.0.name`), form objects with `#[Validate]`, and per-field `.live`/`.blur`/`.debounce` ([Livewire forms.md](https://github.com/livewire/livewire/blob/main/docs/forms.md)). Its weak spots are the lesson:
- Real-time validation of nested array sub-keys was reported broken and stayed largely unresolved ([Livewire discussion #7839](https://github.com/livewire/livewire/discussions/7839)).
- When real-time validation fails, "the property won't be updated on the server", which loses the invalid input on the server side ([Livewire forms.md](https://github.com/livewire/livewire/blob/main/docs/forms.md)).

**Filament** is the richest model for conditional nesting:
- Every setting takes a closure with an injected `Get $get`.
- `->live()` re-evaluates the schema.
- A closure-valued `schema()` with `match` implements a polymorphic sub-form that is re-`fill()`ed when the type changes.
- `Repeater` keys items by UUID, and `$get('../x')` gives relative paths inside rows.
- `Builder` is a list of heterogeneous typed blocks ([Filament forms overview](https://github.com/filamentphp/filament/blob/4.x/packages/forms/docs/01-overview.md), [Filament repeater](https://github.com/filamentphp/filament/blob/4.x/packages/forms/docs/12-repeater.md), [Filament builder](https://github.com/filamentphp/filament/blob/4.x/packages/forms/docs/13-builder.md)).

It also documents the cost. "Each time a reactive field is updated, the HTML of the entire Livewire component … is re-generated", and users report typing lag with live fields and slow large repeaters ([Filament overview](https://github.com/filamentphp/filament/blob/4.x/packages/forms/docs/01-overview.md), [AnswerOverflow report](https://www.answeroverflow.com/m/1158305853301071926)).

**Blazor** offers the best theming hook in the survey: a swappable `FieldCssClassProvider` that returns an empty class until the field is modified. It also treats **unparseable input as a validation error** while keeping the typed string ([Blazor validation](https://github.com/dotnet/AspNetCore.Docs/blob/main/aspnetcore/blazor/forms/validation.md), [Blazor input components](https://github.com/dotnet/AspNetCore.Docs/blob/main/aspnetcore/blazor/forms/input-components.md)).

**The functional tradition** supplies the cleanest conceptual model: a form is one composable value that yields both a view with generated names and a parser for the submitted data ([formlets source](https://github.com/chriseidhof/formlets/blob/master/Text/Formlets.hs)). Its descendants add further pieces:
- elm-form adds a raw-value model with `FieldStatus` and `Form.dynamic`, which selects a sub-form from a parsed discriminator ([elm-form Form.elm](https://github.com/dillonkearns/elm-form/blob/main/src/Form.elm)).
- digestive-functors adds `subView` and `childErrorList` for reusable nested views ([digestive-functors tutorial](https://github.com/jaspervdj/digestive-functors/blob/master/examples/tutorial.lhs)).
- Play adds an implicit `FieldConstructor` that re-themes every field, and `_label`-style per-call options ([Play field constructors](https://github.com/playframework/playframework/blob/main/documentation/manual/working/scalaGuide/main/forms/ScalaCustomFieldConstructors.md)).

Streamlit states the counter-lesson bluntly. In a batched form, "interdependent widgets within a form are unlikely to be particularly useful" ([Streamlit forms](https://github.com/streamlit/docs/blob/main/content/develop/concepts/architecture/forms.md)). pyview's replay-the-whole-form model is the opposite trade, and a strength.

### Side by side: the same validate and save loop

The core loop looks almost identical everywhere. What differs is where raw input lives and who decides error visibility.

```elixir
# Phoenix + Ecto: rebuild from (data, params) every event; action gates errors
def handle_event("validate", %{"user" => params}, socket) do
  form = %User{} |> Accounts.change_user(params) |> to_form(action: :validate)
  {:noreply, assign(socket, form: form)}
end
def handle_event("save", %{"user" => user_params}, socket) do
  case Accounts.create_user(user_params) do
    {:ok, user} -> {:noreply, socket |> put_flash(:info, "user created") |> redirect(to: ~p"/users/#{user}")}
    {:error, %Ecto.Changeset{} = changeset} -> {:noreply, assign(socket, form: to_form(changeset))}
  end
end
```
([Phoenix.Component form docs](https://github.com/phoenixframework/phoenix_live_view/blob/main/lib/phoenix_component.ex), [form-bindings guide](https://github.com/phoenixframework/phoenix_live_view/blob/main/guides/client/form-bindings.md))

```elixir
# AshPhoenix: one long-lived form object, updated in place
def handle_event("validate", %{"form" => params}, socket) do
  {:noreply, assign(socket, :form, AshPhoenix.Form.validate(socket.assigns.form, params))}
end
def handle_event("submit", %{"form" => params}, socket) do
  case AshPhoenix.Form.submit(socket.assigns.form, params: params) do
    {:ok, _user} -> {:noreply, push_navigate(socket, to: ~p"/")}
    {:error, form} -> {:noreply, assign(socket, :form, form)}
  end
end
```
([AshPhoenix.Form moduledoc](https://github.com/ash-project/ash_phoenix/blob/main/lib/ash_phoenix/form/form.ex))

```ts
// Conform (Remix action): parse -> validate -> reply with errors + last payload
const submission = parseWithZod(await request.formData(), { schema });
if (submission.status !== 'success') return submission.reply();
if (!(await sendMessage(submission.value)).sent)
  return submission.reply({ formErrors: ['Failed to send the message. Please try again later.'] });
return redirect('/messages');

// Superforms (SvelteKit): server-produced form object, setError for server rules
const form = await superValidate(request, zod(schema));
if (!form.valid) return fail(400, { form });
if (db.users.find({ where: { email: form.data.email } })) return setError(form, 'email', 'E-mail already exists.');
```
([Conform tutorial](https://github.com/edmundhung/conform/blob/main/docs/tutorial.md), [Superforms error handling](https://superforms.rocks/concepts/error-handling))

```php
// Livewire form object: state lives in server properties; validate() on submit
class PostForm extends Form {
    #[Validate('required|min:5')] public $title = '';
    public function store() { $this->validate(); Post::create($this->only(['title', 'content'])); $this->reset(); }
}
```
([Livewire forms.md](https://github.com/livewire/livewire/blob/main/docs/forms.md))

```python
# Proposed pyview: Ecto's shape, pydantic's engine, stored in context, rebuilt from full params
@event
async def validate(self, socket: LiveViewSocket[SignupContext], params: FormParams):
    socket.context.form = socket.context.form.change(params)

@event
async def save(self, socket: LiveViewSocket[SignupContext], params: FormParams):
    form = socket.context.form.submit(params)
    if form.valid:
        await users.create(form.value)          # form.value: Signup
        await socket.push_navigate("/welcome")
    else:
        socket.context.form = form              # action="submit": every error now visible
```

| Library | Raw input kept? | Error shape | Visibility gate | Dynamic lists | Polymorphic sub-forms | Styling hook |
|---|---|---|---|---|---|---|
| Ecto + Phoenix | `params`; value = changes → params → data | `{msg, opts}` per field, nested via `traverse_errors` | `action` × `used_input?` | `sort_param`/`drop_param` in params | Community `polymorphic_embed` | Generated `core_components` you own |
| AshPhoenix.Form | `raw_params`, `touched_forms` | Errors by path, `for_path: :all` | `submitted_once?`, `only_touched?` | `_add_`/`_drop_`/`_sort_` params or path ops | `_union_type` hidden param | Reuses Phoenix `FormData` |
| WTForms | `raw_data` per field | Dict of lists mirroring data | None built in | `FieldList` key scan (fragile) | None | Widgets, `Meta.render_field` |
| Django | `data` vs `cleaned_data` | Message + `code`, `__all__` | Bound vs unbound form | Formsets + management form | None built in | Renderers, `as_field_group`, `bound_field_class` |
| Conform | Submission payload | Standard Schema issues by path | `shouldValidate`/`shouldRevalidate` | Intents with list keys | Schema unions + `PreserveBoundary` | Headless props |
| Superforms | Posted data | Tree mirroring data, `_errors` | "No errors unless posted", `'auto'` | JSON mode or repeated names | Schema unions | Constraint spreading |
| Rails + simple_form | Params hash | `errors.full_messages` | Re-render after POST | `fields_for` + `_destroy` | None built in | Wrappers pipeline |
| Livewire/Filament | Public properties | Error bag by dot path | Per-property on update | `Repeater` with UUID keys | Closure `schema()` + `fill()`, `Builder` | Blade views, `configureUsing` |
| Blazor | `CurrentValueAsString` | `ValidationMessageStore` by `FieldIdentifier` | `IsModified` | Weak until .NET 10 | None built in | `FieldCssClassProvider` |
| elm-form | Raw `Form.Model` | Errors by field name | `FieldStatus` + `submitAttempted` | Manual | `Form.dynamic` | View functions |

### Patterns that work, and patterns that fail

| Pattern | Verdict | Evidence |
|---|---|---|
| Rebuild the form from `(data, full params)` every event | Works: idempotent, survives recovery | Phoenix's "single use" guidance ([Phoenix.Component](https://github.com/phoenixframework/phoenix_live_view/blob/main/lib/phoenix_component.ex)) |
| Apply only the `_target` field each event | Fails on submit, recovery and nesting | pyview `ChangeSet` `KeyError` ([changesets.py](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/changesets/changesets.py#L1-L67)) |
| List edits encoded in params (`sort[]`, `drop[]`, intents) | Works with no server handlers and no JS | Ecto 3.10 + LV 0.19 ([Ecto CHANGELOG](https://github.com/elixir-ecto/ecto/blob/master/CHANGELOG.md)) |
| Server events that mutate the changeset (`put_embed`) | Fails: the next `phx-change` rebuilds from params and loses the edit | [LostKobrakai gist](https://gist.github.com/LostKobrakai/ce5385bd118189a24d60893188612de9) |
| Management forms, `__prefix__` cloning, `[]`-appended arrays of objects | Fails: tamper errors, JS cloning, Rack's heuristic merges neighbouring rows | [Django formsets](https://github.com/django/django/blob/main/docs/topics/forms/formsets.txt), [Rack query_parser](https://raw.githubusercontent.com/rack/rack/main/lib/rack/query_parser.rb) |
| Raw string kept beside parsed value; parse failure becomes a field error | Works | Blazor `InputNumber` ([Blazor input components](https://github.com/dotnet/AspNetCore.Docs/blob/main/aspnetcore/blazor/forms/input-components.md)) |
| Refuse to store invalid input | Fails: what the user typed is lost | Livewire real-time validation ([Livewire forms.md](https://github.com/livewire/livewire/blob/main/docs/forms.md)) |
| Client-side feedback toggles keyed by one input name | Fails for composite inputs; removed in LV 1.0 | [LV issue #2968](https://github.com/phoenixframework/phoenix_live_view/issues/2968) |
| Schema-driven generation via JSON Schema | Stalls on arrays, `anyOf` overlap and lost metadata | [FastUI](https://github.com/pydantic/FastUI/blob/main/src/python-fastui/fastui/json_schema.py), [RJSF internals](https://rjsf-team.github.io/react-jsonschema-form/docs/advanced-customization/internals) |
| Python-side layout DSL for styling | Friction with utility CSS; overrides ignored | [SaaS Hammer](https://saashammer.com/blog/render-django-form-with-tailwind-css-style/), [crispy #806](https://github.com/django-crispy-forms/django-crispy-forms/issues/806) |
| Polymorphism bolted on outside the core | Generic tooling misses it | `polymorphic_embed` `traverse_errors` caveat ([README](https://github.com/mathieuprog/polymorphic_embed/blob/master/README.md)) |
| Headless wiring plus owned markup | Works | Phoenix `core_components`, shadcn `Field` ([core_components](https://github.com/phoenixframework/phoenix/blob/v1.8/installer/templates/phx_web/components/core_components.ex.eex)) |

## Concern one: data in and out through a decoder and an immutable changeset

The data layer should be three small, separately testable pieces:
1. A **decoder** that is purely syntactic: urlencoded string to nested tree.
2. A **cast** step that is schema-directed: nested strings to a pydantic-ready structure plus an allow-list.
3. A **changeset** that is purely a value: data, params, typed changes, errors, action, and a set of used fields.

Keeping them apart is what lets the same machinery serve phx-change, phx-submit, form recovery, a future non-websocket POST fallback, and unit tests that never touch a socket.

### A lossless decoder must replace parse_qs

The decoder has to start from the raw URL-encoded string. `parse_qs` has already lost blank values, and its dict has lost the relative order of repeated keys by the time the handler sees it ([ws_handler.py L186-191](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/ws_handler.py#L186-L191)). It should turn bracket names into nested dicts and keep list indices as string keys. The index keys become real lists only in the cast step, when the schema says a field is a list. That is how Ecto receives nested lists, as index-keyed maps ([Ecto.Changeset](https://github.com/elixir-ecto/ecto/blob/master/lib/ecto/changeset.ex)).

Its other rules:
- **Order.** Preserve submission order everywhere. The order of hidden `sort[]` inputs *is* the new row order.
- **Duplicates.** Let the last value win for duplicate scalar keys, so a hidden `false` followed by a checked checkbox reads as `true`. `FormData` iterates in tree order.
- **Scalar lists.** Build a list for `name[]`.
- **Reserved keys.** Parse `_target` into a path tuple and strip it from the user namespace, along with `_csrf_token` and any future `_unused_*` keys.

Bracket notation is the right grammar because the Phoenix client already produces it, `_target` is a bracket-derived keyspace, and pydantic `loc` tuples map to it one-to-one ([form-bindings guide](https://github.com/phoenixframework/phoenix_live_view/blob/main/guides/client/form-bindings.md)).

```python
# pyview/forms/params.py (proposed)
from dataclasses import dataclass
from urllib.parse import parse_qsl

Path = tuple[str, ...]

@dataclass(frozen=True)
class Limits:
    max_fields: int = 2_000          # Rack defaults to 4,096 params; forms rarely need half that
    max_depth: int = 16
    max_index: int = 1_000           # never allocate by index: indices stay dict keys until cast

@dataclass(frozen=True)
class FormParams:
    data: dict                       # {"signup": {"name": "Al", "addresses": {"0": {"city": ""}}}}
    target: Path | None              # ("signup", "addresses", "0", "city"); None on submit
    submitter: tuple[str, str] | None
    unused: frozenset[Path]          # from `_unused_*` keys once the client is LiveView >= 1.0
    raw: str

def decode_form(raw: str, limits: Limits = Limits()) -> FormParams:
    pairs = parse_qsl(raw, keep_blank_values=True, max_num_fields=limits.max_fields)
    ...  # split "a[b][0][c]" into ("a","b","0","c"); enforce depth/index caps; keep order

decode_form("signup%5Bname%5D=Al&signup%5Bemail%5D=&signup%5Bnewsletter%5D=false"
            "&signup%5Bnewsletter%5D=true&signup%5Btags%5D%5B%5D=a&_target=signup%5Bemail%5D")
# FormParams(data={"signup": {"name": "Al", "email": "", "newsletter": "true", "tags": ["a"]}},
#            target=("signup", "email"), submitter=None, unused=frozenset(), raw=...)
```

Wiring it in takes two small changes:
1. **Keep the raw payload.** `ws_handler` keeps the raw string before decoding.
2. **Inject it by type.** `call_handle_event` places a `FormParams` in `BindContext.extra`, and `InjectableRegistry` resolves any parameter annotated `FormParams` by type. That extends the existing type-based `params` rules, under which `params: Params` and `params: dict` already mean different things ([injectables.py L28-135](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/binding/injectables.py#L28-L135), [context.py](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/binding/context.py#L15-L35)).

The binder must *not* validate the model. Validation belongs to the changeset, which never raises on user input.

The legacy `payload` dict could also move to `parse_qsl(..., keep_blank_values=True)`. That would be a visible behaviour change for existing apps, so it belongs in the release notes. The existing converters already treat `[""]` as `None` for `Optional` parameters, which softens the impact ([converters.py](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/binding/converters.py#L24-L191)).

### Casting is the schema-directed step pydantic will not do for you

Between the decoder and pydantic sits a cast that walks the model's fields. It does for HTML what pydantic won't:
- **Lists:** index-keyed dicts become lists, sorted numerically and compacted, when the annotation is `list[...]`.
- **Scalar lists:** `list[str]` and `set[...]` always yield a list, even with one value or none.
- **Checkboxes:** an absent `bool` rendered as a checkbox becomes `False`.
- **Empty strings on optionals:** `""` becomes `None` for non-`str` optionals, with a configurable policy for `str | None`.
- **Empty strings on required fields:** `""` on a required non-`str` field is reported as *required* ("Enter your age"), not as pydantic's `int_parsing`.
- **Trimming:** whitespace is trimmed before the emptiness check, following Ecto 3.14's `:trim_values` ([Ecto CHANGELOG](https://github.com/elixir-ecto/ecto/blob/master/CHANGELOG.md)).
- **Empty entries in arrays** are removed.
- **Allow-list:** keys the schema doesn't declare are dropped. That makes the model the allow-list, just as `cast`'s permit list is in Ecto.

None of this is exotic; FastUI and Conform both do a version of it. Conform "strip[s] empty value and coerce[s] form value to the correct type by introspecting the schema", and FastUI drops `""` wholesale ([Conform parseWithZod](https://github.com/edmundhung/conform/blob/main/docs/api/zod/parseWithZod.md), [FastUI forms.py](https://github.com/pydantic/FastUI/blob/main/src/python-fastui/fastui/forms.py)). FastUI's blanket drop is too blunt: it makes "cleared this optional string" impossible to express. The type-directed version is better.

Dataclasses come along almost for free. `pydantic.TypeAdapter(MyDataclass)` validates stdlib dataclasses. Introspection uses `dataclasses.fields` plus `get_type_hints(include_extras=True)`, so the same `Annotated` UI hints work on both. This also unifies the split the notes found today, where the binder handles dataclasses and the changeset handles pydantic ([binder.py](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/binding/binder.py#L168-L179)).

### The changeset keeps data, params, value, errors and action apart

```python
# pyview/forms/form.py (proposed) — a plain immutable class, deliberately not a dataclass,
# so the dead render's `asdict()` cannot flatten it (see live_template.py L32-36)
class Form(Generic[M]):
    schema: type[M]
    data: M | None                    # original instance for edit forms (Ecto `data`)
    params: dict                      # raw nested strings as submitted, under this form's prefix
    value: M | None                   # validated model when valid
    errors: tuple[FormError, ...]     # every error, visible or not
    action: Literal[None, "validate", "submit"]
    used: frozenset[Path]             # fields the user interacted with
    name: str | None                  # "signup" -> inputs named signup[...]; None = flat
    id: str                           # stable DOM id, so form recovery always works

    def __init__(self, schema: type[M], *, data: M | Mapping | None = None,
                 as_: str | None = ..., id: str | None = None, messages: Mapping | None = None): ...
    def change(self, params: FormParams) -> "Form[M]": ...   # action="validate"; used |= {target}
    def submit(self, params: FormParams) -> "Form[M]": ...   # action="submit"; every error visible
    def add_error(self, path: str, message: str, *, code: str = "custom", **ctx) -> "Form[M]": ...
    def reset(self) -> "Form[M]": ...
    @property
    def valid(self) -> bool: ...
    @property
    def changes(self) -> dict: ...                           # typed diff vs data (PATCH-style saves)
    @property
    def changed(self) -> bool: ...                           # dirty flag for "unsaved changes"
    def __getitem__(self, name: str) -> "FormField": ...     # form["email"], form["addresses"][0]["city"]

@dataclass(frozen=True)
class FormError:
    path: Path                        # ("addresses", 0, "city"); () = form-level ("__all__")
    code: str                         # pydantic `type`, e.g. "string_too_short", or "custom"/"upload"
    template: str                     # untranslated message template
    ctx: Mapping[str, Any]            # {"min_length": 3}
    source: Literal["validation", "server", "upload"]
```

`change()` and `submit()` are pure functions of the original data, the full params and the prior `used` set. They never touch the old form's value, so a reconnect that replays the whole form recomputes exactly the same state. That is Ecto's single-use idea, applied to a value that pyview stores in `socket.context` as it stores everything else.

Every displayed value follows Phoenix's precedence: **raw param if present, else the data value serialized for display, else the field default**. So "12abc" stays in the age box beside its error ([phoenix_html form.ex](https://github.com/phoenixframework/phoenix_html/blob/main/lib/phoenix_html/form.ex)).

Each `FormField` exposes two properties instead of Phoenix's one leaky `.value`:
- `value` is always the display string.
- `typed` is the parsed value or `None`.

`typed` comes from cached per-field `TypeAdapter`s run against the cast input. That also yields Ecto-style `changes` when the whole model is invalid, for instance when only a cross-field validator failed. Pydantic's own partial mode can't do this ([pydantic experimental](https://github.com/pydantic/pydantic/blob/main/docs/concepts/experimental.md)).

### Errors are data keyed by path, not English strings keyed by field

Mapping pydantic errors onto fields is a pure function with one exception:
- A `loc` of `("addresses", 0, "city")` becomes the path of `signup[addresses][0][city]`.
- `loc=()` from a `model_validator` goes to a form-level bucket, like Django's `__all__` or Play's `globalErrors`.
- **Discriminated-union tag segments must be stripped** by walking the model's annotations alongside `loc`, because pydantic doesn't mark which segments are tags ([pydantic unions docs](https://github.com/pydantic/pydantic/blob/main/docs/concepts/unions.md)).

Cross-field rules need to land on a specific field, as elm-form's `Validation.fail msg field` and Blazor's `messages.Add(editContext.Field(...))` do ([elm-form](https://github.com/dillonkearns/elm-form), [Blazor validation](https://github.com/dotnet/AspNetCore.Docs/blob/main/aspnetcore/blazor/forms/validation.md)). The simplest API is `form.add_error("payment.po_number", ...)` in the handler. A `FieldError(path, message)` exception that the form layer recognizes inside validators is a nicer but unverified second option.

Messages should follow pydantic's own recommendation: map `error["type"]` to a template and format it with `ctx` ([pydantic errors docs](https://github.com/pydantic/pydantic/blob/main/docs/errors/errors.md)). Ship a GOV.UK-flavoured English catalog, allow overrides per form and per field, and expose one `translate(error) -> str` hook for Gettext or Babel. This is exactly how Phoenix routes `{msg, opts}` through `dngettext` ([Phoenix core_components](https://github.com/phoenixframework/phoenix/blob/v1.8/installer/templates/phx_web/components/core_components.ex.eex)).

```python
MESSAGES = {
    "missing": "Enter {label}",
    "string_too_short": "{label} must be {min_length} characters or more",
    "int_parsing": "Enter a whole number, like 12",
    "greater_than_equal": "{label} must be {ge} or more",
    "literal_error": "Select {label}",
}
form = Form(Signup, messages=MESSAGES | {"email:value_error": "Enter an email address like name@example.com"})
```

The GOV.UK wording rules make good defaults. Say what happened and how to fix it. Avoid "invalid", "please" and "sorry", and never clear the user's answers ([GOV.UK error message](https://raw.githubusercontent.com/alphagov/govuk-design-system/main/src/components/error-message/index.md)).

### Edit forms, dirty state, server errors and submit results

**Edit forms.** `Form(Signup, data=user)` builds an edit form from any model instance, dataclass or mapping. It serializes typed values into display strings the way Play's `fill` "unbinds" a value into fields ([Play ScalaForms](https://github.com/playframework/playframework/blob/main/documentation/manual/working/scalaGuide/main/forms/code/ScalaForms.scala)).

**ORM objects.** The docs should say loudly that the form schema is a DTO, not the ORM class. This is the Ecto guide's advice to split "Database <-> Ecto schema <-> Forms" when UI shape differs from storage, and OWASP's first defence against mass assignment ([Ecto data mapping guide](https://github.com/elixir-ecto/ecto/blob/master/guides/howtos/Data%20mapping%20and%20validation.md), [OWASP Mass Assignment](https://raw.githubusercontent.com/OWASP/CheatSheetSeries/master/cheatsheets/Mass_Assignment_Cheat_Sheet.md)).

**Dirty state.** `form.changes` gives the typed diff for partial updates, and `form.changed` drives an "unsaved changes" warning. I would pick TanStack's *persistent* dirty model for `changed` and name the other concept `is_default` ([TanStack basic concepts](https://tanstack.com/form/latest/docs/framework/react/guides/basic-concepts)).

**Server errors.** Errors added with `add_error(..., source="server")`, such as "email already registered", are cleared the next time that field changes. That is what React Aria and Superforms do ([React Aria forms](https://github.com/adobe/react-spectrum/blob/main/packages/dev/s2-docs/pages/react-aria/forms.mdx)).

**Submit result.** `submit()` returns the same `Form` type with `valid`, `value` and `action="submit"`. That is closer to Superforms' `SuperValidated` than to a Result sum type, and it keeps the handler to one `if`.

A candid note on stateful versus stateless: I would not port Ash's long-lived mutable tree. Its main benefit is path-addressed operations. Those can be provided as pure functions that return a new `Form` whose *params* already contain the edit. That last detail is the fix for the old `put_embed` bug class ([LostKobrakai gist](https://gist.github.com/LostKobrakai/ce5385bd118189a24d60893188612de9)).

## Nested lists, unions and uploads belong in the submitted params

### Lists use Ecto's sort and drop params plus stable row keys

For `list[Address]`, the recommended default is Ecto's params-level protocol, generated by helpers so nobody types these names by hand:
- Each row carries a hidden `signup[addresses_sort][]` with its index.
- Each remove control is a `type="button"` named `signup[addresses_drop][]`, with the index as its value.
- An always-present empty `signup[addresses_drop][]` lets "the user removed every row" survive.
- An add control named `signup[addresses_sort][]` with value `new` appends a blank row, because "Ecto will treat unknown sort params as new children" ([Phoenix.Component inputs_for docs](https://github.com/phoenixframework/phoenix_live_view/blob/main/lib/phoenix_component.ex)).

The buttons use `phx-click={JS.dispatch("change")}`, which turns a click into a form change. I checked the bundled 0.20.17 client for this: `pushInput` sets `meta.submitter = inputEl` when the element is an `HTMLButtonElement`, and `serializeForm` injects the submitter's name and value. So the button recipe works on pyview's client today with no JS additions ([app.js L5548-5576](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/static/assets/app.js#L5548-L5576), [app.js L4667-4703](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/static/assets/app.js#L4667-L4703)). Drag-to-reorder needs only a hook that moves DOM rows, because the hidden sort inputs then serialize in the new order, as in Chris McCord's todo_trek ([todo_trek form_component](https://github.com/chrismccord/todo_trek/blob/main/lib/todo_trek_web/live/list_live/form_component.ex)).

Why params rather than `@event` handlers? Everything that defines the form's shape then travels in every payload. Recovery after a reconnect restores rows, validation sees the post-edit list, and no server event has to be mirrored back into params. The generated markup looks like this:

```html
<fieldset id="signup_addresses_k7" aria-describedby="signup_addresses_k7-error">
  <legend>Address 1 of 2</legend>
  <input type="hidden" name="signup[addresses_sort][]" value="0">
  <input type="hidden" name="signup[addresses][0][_key]" value="k7">
  <label for="signup_addresses_k7_street">Street</label>
  <input id="signup_addresses_k7_street" name="signup[addresses][0][street]" autocomplete="address-line1">
  <button type="button" name="signup[addresses_drop][]" value="0"
          phx-click='[["dispatch",{"event":"change"}]]'>Remove address 1</button>
</fieldset>
<input type="hidden" name="signup[addresses_drop][]">
<button type="button" name="signup[addresses_sort][]" value="new"
        phx-click='[["dispatch",{"event":"change"}]]'>Add address</button>
```

The `_key` field is the pyview counterpart of Phoenix's `_persistent_id`. The index in the name is for transport. The key is for **DOM ids and identity**; note that the ids above use `k7` while the name uses `0`. Focus and client state then survive when a row above is deleted and the indices shift. Phoenix appears to have introduced `_persistent_id` for this reason but never documented its purpose. It later had to add `skip_persistent_id` after the field collided with third-party `FormData` implementations ([LV issue #3673](https://github.com/phoenixframework/phoenix_live_view/issues/3673), [LV issue #2626](https://github.com/phoenixframework/phoenix_live_view/issues/2626)). pyview should document its key field from day one and make it collision-proof by reserving `_`-prefixed names in the form namespace.

Persisted child rows need a stricter policy. A hidden `id` coming back from the client must be checked against the parent's children loaded on the server. Ideally the server keeps a `key → id` map in socket state and never trusts the submitted id ([LiveView security model](https://raw.githubusercontent.com/phoenixframework/phoenix_live_view/main/guides/server/security-model.md)).

The protocol doesn't cover everything; "duplicate this row" and "copy billing to shipping" are examples. For those, the `Form` offers path-addressed pure operations in the style of Ash and Conform's custom intents: `form.insert("addresses", at=0, value={...})`, `form.remove("addresses", 2)`, `form.move("addresses", 2, 0)` and `form.copy("billing", "shipping")`. Each returns a new form whose params reflect the edit. "Copy billing to shipping" doubles as a WCAG 3.3.7 Redundant Entry feature ([WCAG 3.3.7](https://raw.githubusercontent.com/w3c/wcag/main/understanding/22/redundant-entry.html)).

Two ordering rules make the protocol safe:
- **Sort order.** The cast iterates `sort[]` in submission order, and unknown values create rows.
- **Caps.** Sort and drop arrays are capped at the current row count plus a small allowance, and the model's `Field(max_length=5)` on the list is enforced both as validation and as an `onInvalid: 'revert'`-style guard on add ([Conform useIntent](https://github.com/edmundhung/conform/blob/main/docs/api/react/future/useIntent.md)).

### Discriminated unions get one tag, one active variant and stripped error paths

Pydantic already has the right model for polymorphic sub-forms. Each member declares a `Literal` tag, and the union uses `Field(discriminator="kind")`. Errors are reported only for the matched member, which is "much simpler" than plain unions ([pydantic unions docs](https://github.com/pydantic/pydantic/blob/main/docs/concepts/unions.md)).

A `UnionField` renders the tag as radios or a select named `signup[payment][kind]`. It renders only the active variant's fields under the same parent namespace, and exposes `variant` and `form` for template `if` and `match`. Because inactive variants aren't in the DOM, they aren't submitted and aren't validated. The server derives the active variant from the cast tag, not from anything the client claims is visible, and rejects tags outside the declared members.

When `_target` shows the tag itself changed, the sub-form is re-initialized with the new variant's defaults. That is the step Filament performs with `getChildSchema()->fill()` and Ash with `remove_form` plus `add_form` ([Filament overview](https://github.com/filamentphp/filament/blob/4.x/packages/forms/docs/01-overview.md), [ash_phoenix union forms](https://github.com/ash-project/ash_phoenix/blob/main/documentation/topics/union-forms.md)). This is also why `FormParams.target` must be a parsed path: one generic handler can then rebuild a subform at any depth.

The one real policy choice is what happens to the old variant's values:
- `"discard"` should be the default. It matches what is submitted, and stale hidden data can never leak.
- `"stash"` is opt-in. It keeps the last raw params per variant in server state so switching back restores them.

A list of discriminated unions, `list[Heading | Paragraph | Image]`, is Filament's `Builder` for free: the same list protocol, with `default_type_on_sort_create` semantics for the add button ([Filament builder](https://github.com/filamentphp/filament/blob/4.x/packages/forms/docs/13-builder.md), [polymorphic_embed](https://github.com/mathieuprog/polymorphic_embed/blob/master/README.md)).

### Conditional fields use one predicate for rendering and validation

Not every condition deserves a union. "Other, please specify" and "VAT number only for business accounts" are simple show/hide rules. They should be declared once and evaluated on the server against the cast value, so UI and validation can't drift:

```python
class Signup(BaseModel):
    account_type: Literal["personal", "business"] = "personal"
    vat_number: Annotated[str | None, ShowWhen("account_type", equals="business")] = None
```

The semantics borrow Laravel's `exclude_if`: a hidden field is not rendered, not submitted, and **removed before validation**, so the model must allow its absence ([Laravel validation](https://github.com/laravel/docs/blob/13.x/validation.md)). "Required when shown" belongs in a `model_validator`, which the predicate can generate. JSON Forms' idea that a rule's condition is a schema applied to another field's value is a good design reference, but plain Python predicates are more idiomatic here ([JSON Forms rules](https://jsonforms.io/docs/uischema/rules)).

Filament documents the cost. A live field re-renders the whole component on each change ([Filament overview](https://github.com/filamentphp/filament/blob/4.x/packages/forms/docs/01-overview.md)). pyview's diff engine helps, but fields that drive conditions should still use `phx-debounce`.

### Uploads stay on their own channel as field references

The Phoenix client strips `File` values from form payloads and uploads them over a dedicated channel. pyview implements the full protocol: preflight, chunks, progress and `consume_uploads()` ([app.js L4667-4703](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/static/assets/app.js#L4667-L4703), [uploads.py](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/uploads.py#L88-L423)).

The form library should model an upload field as a **reference to an `UploadConfig`**:
- It renders `live_file_input` inside the field group.
- It merges `UploadConfig.errors` and entry errors into the field's visible errors as `source="upload"`.
- It fills the model field with consumed-file metadata only after `consume_uploads()` on submit. It never fills it with bytes.

Two fixes are prerequisites. `maybe_process_uploads` should find configs through the refs in `payload["uploads"]` instead of `_target`, so prefixed names work ([uploads.py L466-477](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/uploads.py#L466-L477)). And file inputs should be excluded from recovery expectations, since recovery clears them ([app.js L5760-5781](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/static/assets/app.js#L5760-L5781)). Conform's `keepFiles=False` default reflects the same fact from the other side: file inputs can't be repopulated ([Conform report](https://github.com/edmundhung/conform/blob/main/docs/api/react/future/report.md)).

### Security: the model is the allow-list, and the parser has budgets

Every part of a form payload is attacker-controlled: hidden fields, ids, `_target`, sort and drop indices, discriminator tags. "An attacker can use browser developer tools or custom scripts to send any payload to your LiveView" ([LiveView security model](https://raw.githubusercontent.com/phoenixframework/phoenix_live_view/main/guides/server/security-model.md)). The defences are structural:
- **The model is the allow-list.** The pydantic form model is a DTO; `extra="ignore"` by default, or `"forbid"` to log tampering. Never bind params onto ORM objects ([OWASP Mass Assignment](https://raw.githubusercontent.com/OWASP/CheatSheetSeries/master/cheatsheets/Mass_Assignment_Cheat_Sheet.md)).
- **Parse-time budgets.** Cap fields, depth and indices before pydantic runs, and never allocate by index. Rack caps params at 4,096 and nesting depth, and `qs` turns indices above 20 into object keys specifically because of `a[999999999]` ([Rack query_parser](https://raw.githubusercontent.com/rack/rack/main/lib/rack/query_parser.rb), [ljharb/qs](https://github.com/ljharb/qs)).
- **List sizes.** `Field(max_length=...)` bounds lists, in the spirit of Django's `absolute_max` ([Django formsets](https://github.com/django/django/blob/main/docs/topics/forms/formsets.txt)).
- **Re-authorize every event.**
- **Never echo passwords.** Phoenix already declines to re-render password values, and Conform's `hideFields` exists for the same reason ([form-bindings guide](https://github.com/phoenixframework/phoenix_live_view/blob/main/guides/client/form-bindings.md)).
- **Debounce expensive checks.** Uniqueness checks should run on blur or submit, which also limits "username taken" probing.

CSRF for the socket join is already the transport's job. pyview passes `_csrf_token` in the LiveSocket params and generates a per-view token, so the form library should not add another layer. This research did not audit the server-side check on join ([app.js L59-75](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/assets/js/app.js#L59-L75), [pyview.py L117-122](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/pyview.py#L117-L122)).

## Concerns two and three: eight rendering rungs share one wiring layer

Rendering should follow Chollet's "progressive disclosure of complexity": "Make it easy to get started, yet make it possible to handle arbitrarily flexible use cases, only requiring incremental learning at each step" ([Chollet](https://x.com/fchollet/status/1231285340335267840?lang=en)).

The important architectural decision is where correctness lives. Names, ids, displayed values, visible errors, `aria-invalid`, `aria-describedby`, `autocomplete`, constraint attributes and debounce policy all belong to the **lowest** layer, a `FormField` view-model. Every rung, including fully hand-written HTML, calls into it. Only markup and classes live in templates that users override or eject.

That is the compromise between Phoenix's "generated code you own" and a traditional widget library: ejecting templates does not eject correctness. Accessibility fixes still reach apps that customized their markup, which is the weakness of pure copy-paste distribution ([Phoenix core_components](https://github.com/phoenixframework/phoenix/blob/v1.8/installer/templates/phx_web/components/core_components.ex.eex)).

### The FormField view-model owns every attribute that affects correctness

A `FormField` exposes:
- **Identity:** `name`, `id`.
- **Values:** `value` (display string), `typed`.
- **Errors:** `errors` (visible, translated), `all_errors`.
- **State:** `used`, `required`.
- **Text:** `label`, `hint`, `hint_id`, `error_id`.
- **Input description:** `input_type`, `choices`, `constraints`.
- **Two Markup attribute bundles:**
  - `attrs`, for the control: name, id, value or checked, `aria-invalid`, `aria-describedby`, `autocomplete`, constraints, `phx-debounce`;
  - `state_attrs`, for the wrapper: `data-invalid`, `data-used`, `data-required`, `data-dirty`.
- **Renderers:** `group()`, `input()`, `label_tag()`, `hint_tag()` and `error_tag()`.

The derivation from pydantic follows simple_form's inference and the "lean on HTML" advice from django-htmx-patterns ([simple_form](https://github.com/heartcombo/simple_form), [django-htmx-patterns](https://github.com/spookylukey/django-htmx-patterns/blob/master/form_validation.rst)):

| Pydantic declaration | Default control and attributes |
|---|---|
| `str`, `Field(min_length, max_length)` | `<input type=text minlength maxlength>` |
| `EmailStr`; field named `email` | `type=email autocomplete=email` |
| `SecretStr`; field named `password` | `type=password`, value never echoed |
| `int`, `Field(ge, le)` | `type=text inputmode=numeric pattern=[0-9]*` (see note below); bounds enforced on the server |
| `Decimal`, `float` | `type=text inputmode=decimal` |
| `date` / `datetime` / `time` | `type=date` / `datetime-local` / `time` |
| `bool` | Hidden `false` twin plus `type=checkbox value=true` |
| `Literal[...]` / `Enum` | Radios for up to about 5 options, else `<select>`; hidden empty twin so absence is explicit |
| `list[Literal]` / `set[Enum]` | Checkbox group or `<select multiple>` with hidden `x[]=""` sentinel |
| `SubModel` | `<fieldset><legend>` with nested names |
| `list[SubModel]` | Repeater with sort/drop controls and row keys |
| `A \| B` with `discriminator` | Tag switcher plus active-variant fieldset |
| Not optional, no default | `required`, and an "(optional)" marker on the others as a theme choice |

The `int` row deliberately avoids `type=number`. Phoenix recommends `type="text" inputmode="numeric" pattern="[0-9]*"`, and pyview's bundled client silently drops change events for number inputs with `badInput`. The server would never see "12abc" to report it ([form-bindings guide](https://github.com/phoenixframework/phoenix_live_view/blob/main/guides/client/form-bindings.md), [app.js L6600-6622](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/static/assets/app.js#L6600-L6622)).

The `pattern` attribute should be emitted only when a Python regex translates cleanly to a JS `RegExp`. Constraint attributes should be paired with `novalidate` on the form by default. Browsers then don't block submit or show their own bubbles, but mobile keyboards and `:user-invalid` styling still work. The server stays the authority, and GOV.UK's full opt-out remains a theme option ([GOV.UK validation](https://raw.githubusercontent.com/alphagov/govuk-design-system/main/src/patterns/validation/index.md)).

### Ibis and t-strings need different surfaces over the same objects

Ibis's rules dictate the template surface:
- **No keyword arguments.** Calls take only positional literals, so `field.input(class_="x")` is impossible. The accepted form is `field.input({"class": "w-full"})`, a dict literal.
- **No variable arguments.** A layout object can't be passed from the template (`form.render(layout)` fails literal parsing). Configuration therefore lives in Python, on the `Form` constructor or the model.
- **Attribute lookup tries `getattr` first.** `form.email` would collide with any `Form` attribute of the same name, such as a model field called `name`, `id` or `errors`. Ibis templates should therefore reach fields through a collision-free namespace, `form.fields.email`. Integer path segments resolve too: `form.fields.addresses.0.city`.
- **User-supplied field partials** work through `{% include "forms/money.html" with field = form.fields.price %}`.
- **Helpers can be global filters.** They are registered in `filters.filtermap` like the existing `live_file_input` ([nodes.py](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/vendor/ibis/nodes.py#L55-L141), [context.py](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/vendor/ibis/context.py#L75-L94), [uploads.py L715-749](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/uploads.py#L715-L749)).

t-strings get the richer surface:
- `form["email"]` indexing and real keyword arguments.
- Helpers that return nested `Template`s, so diffs stay granular.
- `AutoEventDispatch`'s trick where `str(self.validate)` is the event name, so `form.render(change=self.validate, submit=self.save)` is type-checked ([AutoEventDispatch](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/events/AutoEventDispatch.py#L6-L98)).

The library must render boolean and spread attributes itself, because the t-string processor has no notion of attributes ([live_view_template.py](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/template/live_view_template.py#L101-L195)). Its helpers must stay importable on Python 3.11 to 3.13. In practice, core code builds `Template` objects programmatically or returns `Markup`, and literal t-string syntax stays in lint-excluded files, as the project already does ([pyproject.toml](https://github.com/ogrodnek/pyview/blob/9b32095/pyproject.toml)).

### Styling uses state attributes first, class providers second and owned templates third

Styling needs three layers, in order of how often people should reach for them:
1. **State as server-rendered attributes.** `aria-invalid="true"` on the control and `data-invalid`, `data-used`, `data-dirty` on the wrapper. Plain CSS, design tokens and Tailwind's built-in `aria-invalid:` and `data-[invalid]:` variants can all style state without the library knowing any class names ([Tailwind states](https://tailwindcss.com/docs/hover-focus-and-other-states), [React Aria styling](https://react-aria.adobe.com/styling)). Styling off `aria-invalid` also guarantees that the visual state and the assistive-technology state can't diverge.
2. **A class provider,** for utility-class users who want classes rather than selectors. `field_class(state)`, `input_class(state)` and `error_class(state)` are modelled on Blazor's `FieldCssClassProvider`, including its "return nothing until the field is modified" behaviour ([Blazor validation](https://github.com/dotnet/AspNetCore.Docs/blob/main/aspnetcore/blazor/forms/validation.md)).
3. **Wrapper templates** per theme: field group, fieldset, repeater, union switcher, error summary. These are simple_form wrappers and Play's `FieldConstructor` in template form. Select them globally, per form or per field, and let a CLI eject them into the project, as Phoenix and shadcn do ([Play field constructors](https://github.com/playframework/playframework/blob/main/documentation/manual/working/scalaGuide/main/forms/ScalaCustomFieldConstructors.md)).

Ship a `plain` theme (semantic class names and a small CSS file of custom properties) and a `tailwind` theme first. More packs can follow if people ask; crispy-tailwind, whose last release was in February 2024, shows how costly packs are to maintain ([PyPI crispy-tailwind](https://pypi.org/project/crispy-tailwind/)).

I would not ship a crispy-style Python `Layout` DSL beyond `Row` and `Fieldset` for auto-render. Layout is exactly where users want to write HTML.

### Validation timing rewards early and punishes late, on the server

The UX evidence converges:
- Don't show errors on pristine fields.
- Flag a previously valid field only after the user leaves it ("punish late").
- Update or clear an existing error on every keystroke ("reward early").
- Reveal everything on submit, with a summary.

Wroblewski's 2009 study, as summarized, found the best inline-validation variant produced a 22% increase in success rates and a 42% decrease in completion times compared with submit-only validation ([LukeW](https://www.lukew.com/ff/entry.asp?883=), [Konjević](https://medium.com/wdstack/inline-validation-in-forms-designing-the-experience-123fb34088ce), [Baymard](https://baymard.com/blog/inline-form-validation)). GOV.UK dissents for transactional services: "Do not validate when the user moves away from a field". So the policy must be configurable ([GOV.UK validation](https://raw.githubusercontent.com/alphagov/govuk-design-system/main/src/patterns/validation/index.md)).

On LiveView 1.x, `_unused_` params mark fields "used" on **focus**, not blur. A pure `used_input?` policy would therefore still show errors mid-typing unless inputs are debounced ([view.ts](https://github.com/phoenixframework/phoenix_live_view/blob/v1.2/assets/js/phoenix_live_view/view.ts)). It also misses unselected selects and radios, which are absent from `FormData` ([LV issue #3580](https://github.com/phoenixframework/phoenix_live_view/issues/3580)).

On the bundled 0.20.17 client the answer is server-side, in three parts:
1. **Used tracking.** Record each `_target` in `used`.
2. **Punish late.** Render text inputs with `phx-debounce="blur"` while they have no visible error, so the first change event arrives when the user leaves the field.
3. **Reward early.** Render `phx-debounce="300"` once an error is visible.

The client re-reads `phx-debounce` on every event, and the blur listener is installed once and kept ([app.js L2550-2571](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/static/assets/app.js#L2550-L2571)). That makes a server-flipped debounce plausible. Whether attribute patches reach a focused input mid-typing needs a browser test before it becomes the default.

```python
def visible_errors(field: FormField, form: Form) -> list[str]:
    if form.action is None:           # untouched new/edit form: never nag (Ecto's nil action)
        return []
    if form.action == "submit":       # after a submit attempt: everything (Formik "touch all")
        return field.all_errors
    if form.policy == "submit":       # GOV.UK mode: inline errors only after submit
        return []
    return field.all_errors if field.used else []   # "blur" (default) and "live" policies
```

### Accessibility is part of the wiring, not the theme

Every generated field should meet the baseline that Django 5.x, GOV.UK and WCAG 2.2 converge on ([WCAG 3.3.1](https://raw.githubusercontent.com/w3c/wcag/main/understanding/20/error-identification.html), [GOV.UK error message](https://raw.githubusercontent.com/alphagov/govuk-design-system/main/src/components/error-message/index.md), [Django 5.0 notes](https://github.com/django/django/blob/main/docs/releases/5.0.txt)):
- a `<label for>`;
- hint and error text linked through `aria-describedby`;
- `aria-invalid="true"` only when an error is visible;
- error text rather than colour alone, with a visually hidden "Error:" prefix;
- `<fieldset>`/`<legend>` for radios, checkbox groups, nested models and every repeated row.

`aria-describedby` is the robust mechanism, since `aria-errormessage` support is uneven and its deprecation has been proposed ([Roselli](http://adrianroselli.com/2023/04/exposing-field-errors.html), [w3c/aria #2048](https://github.com/w3c/aria/issues/2048)).

After a failed submit, render an error summary above the form. Its entries must use the same wording as the inline messages and link to the first control of each group, and it must receive focus ([GOV.UK error summary](https://raw.githubusercontent.com/alphagov/govuk-design-system/main/src/components/error-summary/index.md)). There is no page load in LiveView, so the submit path should move focus explicitly, via a small hook or `JS.focus` on the summary, mimicking govuk-frontend's "scroll the legend into view, then focus the input" behaviour ([govuk-frontend error-summary.mjs](https://raw.githubusercontent.com/alphagov/govuk-frontend/main/packages/govuk-frontend/src/govuk/components/error-summary/error-summary.mjs)).

Adding or removing rows should follow MOJ's "Add another" component ([moj-frontend add-another](https://raw.githubusercontent.com/ministryofjustice/moj-frontend/main/src/moj/components/add-another/add-another.mjs)):
- After adding, focus the new row.
- After removing, focus the next row or the add button.
- Keep "Address N of M" legends current.
- Give remove buttons contextual names such as "Remove address 2".

Map field names to `autocomplete` tokens, and never block paste. WCAG 3.3.8 passes username and password fields precisely because password managers can fill them ([WCAG 3.3.8](https://raw.githubusercontent.com/w3c/wcag/main/understanding/22/accessible-authentication-minimum.html)).

## The proposed API, from one model class to hand-written HTML

Everything below is a proposal grounded in pyview's current idioms: `LiveView[Context]`, `AutoEventDispatch` with `@event`, `socket.context`, `TemplateView.template()`, Ibis files next to the view, and `pyview.js`. Names are illustrative.

### The model and the eight-rung ladder

```python
from datetime import date
from typing import Annotated, Literal
from pydantic import BaseModel, EmailStr, Field
from pyview.forms import Input, Textarea, ShowWhen

class Address(BaseModel):
    street: Annotated[str, Input(autocomplete="address-line1")] = Field(min_length=1)
    city: str = Field(min_length=1)
    postcode: Annotated[str, Input(autocomplete="postal-code")]

class Card(BaseModel):
    kind: Literal["card"] = "card"
    number: Annotated[str, Input(autocomplete="cc-number", inputmode="numeric")]
    expiry: Annotated[str, Input(placeholder="MM/YY", autocomplete="cc-exp")]

class Invoice(BaseModel):
    kind: Literal["invoice"] = "invoice"
    po_number: str | None = None

class Signup(BaseModel):
    name: str = Field(min_length=2, max_length=60, title="Full name")
    email: EmailStr
    birthday: date | None = None
    bio: Annotated[str, Textarea(rows=4)] = Field("", description="Shown on your profile")
    account_type: Literal["personal", "business"] = "personal"
    vat_number: Annotated[str | None, ShowWhen("account_type", equals="business")] = None
    newsletter: bool = False
    addresses: list[Address] = Field(default_factory=list, max_length=5)
    payment: Card | Invoice = Field(default_factory=Invoice, discriminator="kind")
```

| Rung | What you write | What the library still does |
|---|---|---|
| 0 | Model plus `on_submit` (`FormView`) | View, events, template, validation, errors, accessibility |
| 1 | Your own LiveView; `form.render()` in the template | All markup and wiring |
| 2 | `Annotated` hints, `title`, `description` on the model | Markup driven by hints |
| 3 | Partial auto-render plus your own layout HTML | Field groups for the rest |
| 4 | Field groups or pieces placed in your template | Label, input, hint and error markup plus wiring |
| 5 | Your own HTML using `field.attrs` | Wiring only: names, ids, values, ARIA, constraints, visibility |
| 6 | Widget and theme registration | Your widgets used everywhere, including auto-render |
| 7 | `pyview forms eject` | Wiring; you own every template |

### Rung 0: "here is my class, do the rest"

```python
from pyview.forms import FormView

class SignupView(FormView[Signup]):
    """Sign up"""
    async def on_submit(self, socket, signup: Signup):
        await users.create(signup)
        socket.put_flash("info", f"Welcome, {signup.name}!")
        await socket.push_navigate("/welcome")

class EditProfileView(FormView[Profile]):
    async def load(self, socket, session) -> Profile:          # edit form: initial data
        return await profiles.get(session["user_id"])
    async def on_submit(self, socket, profile: Profile):
        await profiles.update(profile)                           # or form.changes for a PATCH

app.add_live_view("/signup", SignupView)
```

`FormView` is a thin `LiveView` subclass. It mounts `Form(schema, data=await self.load(...))` and registers `validate` and `save` events. If no `.html` file sits next to the view, it renders the active theme's full-form template. Business-rule failures stay one line: `raise FormRejected("email", "is already registered")` inside `on_submit` becomes a server error on that field. This rung is deliberately a scaffold for internal tools and simple forms, the scope AutoForm claims for itself ([AutoForm](https://github.com/vantezzen/autoform)). Everything it does is available unbundled on the rungs below.

### Rung 1: an explicit Form in any LiveView, auto-rendered

```python
from dataclasses import dataclass, field
from pyview import LiveView, LiveViewSocket
from pyview.events import AutoEventDispatch, event
from pyview.forms import Form, FormParams

@dataclass
class SignupContext:
    form: Form[Signup] = field(default_factory=lambda: Form(Signup))   # name "signup", id "signup-form"

class SignupView(AutoEventDispatch, LiveView[SignupContext]):
    async def mount(self, socket: LiveViewSocket[SignupContext], session):
        socket.context = SignupContext()

    @event
    async def validate(self, socket: LiveViewSocket[SignupContext], params: FormParams):
        socket.context.form = socket.context.form.change(params)

    @event
    async def save(self, socket: LiveViewSocket[SignupContext], params: FormParams):
        form = socket.context.form.submit(params)
        if form.valid and await users.email_taken(form.value.email):
            form = form.add_error("email", "{label} is already registered", code="taken")
        if not form.valid:
            socket.context.form = form
            return
        await users.create(form.value)
        socket.context.form = Form(Signup)
        socket.put_flash("info", "Account created")
```

```html
<!-- signup.html (Ibis) -->
{{ form.render() }}
```

```python
# t-string version (Python 3.14+)
def template(self, assigns: SignupContext, meta: PyViewMeta) -> Template:
    return t"""{assigns.form.render(change=self.validate, submit=self.save)}"""
```

`render()` emits:
- `<form id=... phx-change phx-submit novalidate>`;
- the error summary when the action is `"submit"`;
- a field group per field;
- the repeater and union widgets;
- a submit button with `phx-disable-with`.

### Rungs 2 and 3: model metadata, then partial auto-render

Rung 2 is already visible in the model: `title` becomes the label, `description` becomes the hint, and `Annotated` carries widget hints that stay out of the JSON schema ([PyPI pydantic](https://pypi.org/project/pydantic/)). Rung 3 lets you own the layout and auto-render everything else. Because Ibis can't take variables as arguments, field lists are literals:

```html
<form id="{{ form.id }}" phx-change="validate" phx-submit="save" novalidate class="space-y-6">
  {{ form.error_summary() }}
  <div class="grid grid-cols-2 gap-4">
    {{ form.fields.name.group() }}
    {{ form.fields.email.group() }}
  </div>
  {{ form.render_fields(["account_type", "vat_number", "addresses", "payment"]) }}
  <button type="submit" phx-disable-with="Saving…">Create account</button>
</form>
```

### Rung 4: field groups and pieces inside your own template

```html
<!-- Ibis: attrs passed as a dict literal, the only argument form Ibis accepts -->
{{ form.fields.bio.group({"class": "textarea textarea-bordered w-full"}) }}

{% with f = form.fields.email %}
  <div class="field" {{ f.state_attrs }}>
    {{ f.label_tag() }}
    {{ f.hint_tag() }}
    {{ f.input({"class": "input w-full"}) }}
    {{ f.error_tag() }}
  </div>
{% endwith %}
```

```python
# t-strings: real keyword arguments and nested Templates for granular diffs
def template(self, assigns: SignupContext, meta: PyViewMeta) -> Template:
    f = assigns.form
    return t"""<form {f.form_attrs(change=self.validate, submit=self.save)} class="space-y-6">
      {f.error_summary()}
      {f["bio"].group(class_="textarea textarea-bordered w-full")}
      <div class="field" {f["email"].state_attrs}>
        {f["email"].label_tag()}{f["email"].hint_tag()}
        {f["email"].input(class_="input w-full", phx_debounce="blur")}
        {f["email"].error_tag()}
      </div>
      <button type="submit" phx-disable-with="Saving…">Create account</button>
    </form>"""
```

Nested lists and unions use the same pieces. In Ibis:

```html
<fieldset>
  <legend>Addresses</legend>
  {% for row in form.fields.addresses %}
    <fieldset id="{{ row.dom_id }}" {{ row.group_attrs }}>
      <legend>Address {{ row.number }} of {{ form.fields.addresses.count }}</legend>
      {{ row.hidden_inputs }}                                  {# sort index + _key #}
      {{ row.fields.street.group() }}
      <div class="grid grid-cols-2 gap-4">{{ row.fields.city.group() }}{{ row.fields.postcode.group() }}</div>
      {{ row.drop_button("Remove address") }}                  {# renders "Remove address 2" #}
    </fieldset>
  {% endfor %}
  {{ form.fields.addresses.drop_sentinel }}
  {{ form.fields.addresses.add_button("Add address") }}
</fieldset>

{% with p = form.fields.payment %}
  {{ p.switcher() }}                                           {# radios named signup[payment][kind] #}
  {% if p.variant == "card" %}
    {{ p.fields.number.group() }}{{ p.fields.expiry.group() }}
  {% elif p.variant == "invoice" %}
    {{ p.fields.po_number.group() }}
  {% endif %}
{% endwith %}
```

And with t-strings:

```python
def addresses(f: Form[Signup]) -> Template:
    rows = f["addresses"]
    items = [t"""<fieldset id="{row.dom_id}" {row.group_attrs}>
        <legend>Address {row.number} of {len(rows)}</legend>
        {row.hidden_inputs}{row["street"].group()}{row["city"].group()}{row["postcode"].group()}
        {row.drop_button("Remove address")}
      </fieldset>""" for row in rows]
    return t"""<fieldset><legend>Addresses</legend>{items}{rows.drop_sentinel}{rows.add_button("Add address")}</fieldset>"""

def payment(f: Form[Signup]) -> Template:
    p = f["payment"]
    match p.variant:
        case "card":    body = t"{p['number'].group()}{p['expiry'].group()}"
        case "invoice": body = t"{p['po_number'].group()}"
    return t"{p.switcher()}{body}"
```

### Rung 5: your own HTML, with the library supplying only the wiring

```html
<!-- Ibis -->
{% with f = form.fields.email %}
<div class="mb-4 group" {{ f.state_attrs }}>
  <label for="{{ f.id }}" class="block text-sm font-medium">Work email</label>
  <input type="email" {{ f.attrs }}
         class="w-full rounded border-gray-300 aria-invalid:border-red-600">
  {% if f.errors %}
    <p id="{{ f.error_id }}" class="mt-1 text-sm text-red-700">
      <span class="sr-only">Error:</span> {{ f.errors.0 }}
    </p>
  {% endif %}
</div>
{% endwith %}
```

```python
# t-string: the same, with the attribute bundle spread as Markup
def email_field(f: FormField) -> Template:
    error = t"""<p id="{f.error_id}" class="mt-1 text-sm text-red-700"><span class="sr-only">Error:</span> {f.errors[0]}</p>""" if f.errors else None
    return t"""<div class="mb-4" {f.state_attrs}>
      <label for="{f.id}">Work email</label>
      <input type="email" {f.attrs} class="w-full rounded border-gray-300 aria-invalid:border-red-600">
      {error}
    </div>"""
```

`f.attrs` renders `name="signup[email]" id="signup_email" value="bob@" autocomplete="email" required aria-invalid="true" aria-describedby="signup_email-error" phx-debounce="300"`. A hand-written field is therefore exactly as correct as a generated one.

### Rungs 6 and 7: widgets, themes and ejecting

```python
from pyview.forms import widgets, themes, rank_with, path_endswith, FieldState

@widgets.register(Money)                                         # by type
def money_input(field: FormField) -> Markup: ...                 # or template="forms/money.html"

@widgets.register(rank_with(3, path_endswith("rating")))         # JSON Forms-style ranked tester
def star_rating(field: FormField) -> Markup: ...

class Brand(themes.Tailwind):                                    # class provider (Blazor-style)
    def input_class(self, s: FieldState) -> str:
        if not s.show_errors:
            return "input input-bordered w-full"
        return "input input-bordered input-error w-full" if s.errors else "input input-bordered input-success w-full"

themes.use(Brand())                                              # global; Form(..., theme=...) per form
```

```text
$ pyview forms eject --theme tailwind --to templates/forms/
  wrote field_group.html, fieldset.html, repeater.html, union.html, error_summary.html, checkbox.html …
```

Widgets registered by type, name or ranked tester apply everywhere, including `form.render()`. That is fh-pydantic-form's registry combined with JSON Forms' ranking ([fh-pydantic-form](https://github.com/Marcura/fh-pydantic-form), [JSON Forms custom renderers](https://jsonforms.io/docs/tutorial/custom-renderers)). Ejected templates receive `FormField` objects, so wiring stays in the library.

### A sub-form component rung, later

A LiveComponent could host a self-contained sub-form (an address lookup, for example) with its own events via `phx-target`. Components still receive unbound `handle_event(event, payload, socket)` calls, though. That rung should wait for component binding ([PR #126](https://github.com/ogrodnek/pyview/pull/126), [components base.py](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/components/base.py#L30-L212)).

## Ship the decoder first: a four-phase roadmap and open questions

The order matters more than the feature list. Every rung depends on correct names, paths and raw values. Auto-generation built before the wiring layer is how FastUI ended up with a pretty demo and a `NotImplementedError` for arrays ([FastUI json_schema.py](https://github.com/pydantic/FastUI/blob/main/src/python-fastui/fastui/json_schema.py)).

| Phase | Scope | Why at this point | Done when |
|---|---|---|---|
| 0 Plumbing | Keep the raw form string in `ws_handler`; `decode_form` with limits; `FormParams` injectable; dead render uses `serialize()`; upload lookup by ref; fix docs (`apply()` on submit, `phx-value-user-id`, `params` for events); ship `.phx-no-feedback` CSS or remove the attributes | Every later phase depends on lossless params, and these are small, testable PRs | Probe payloads decode losslessly; existing examples unchanged |
| 1 Core | `Form` changeset (pydantic plus dataclasses via `TypeAdapter`); cast rules; `FormError` with type/ctx; message catalog and translate hook; `FormField` with `attrs`/`state_attrs`; Ibis and t-string adapters; `plain` theme with `form.render()`; `pyview.changesets` shim; rewrite the plants and registration examples; new Forms docs page | Delivers the zero-to-working path early, on a correct base | Flat forms work at rungs 1, 4 and 5 in both engines; recovery test passes |
| 2 Structure | Nested models; `list[Model]` with sort/drop and row keys; path-addressed ops; discriminated unions with discard/stash; `ShowWhen`; upload fields; error summary with focus; timing policies including the debounce flip | The user's hardest cases, built on Phase 1's paths | Deep nested plus list plus union form round-trips through reconnect; accessibility checks pass |
| 3 Presentation | `tailwind` theme; widget registry with ranked testers; `FormView`; `pyview forms eject`; layout helpers `Row`/`Fieldset` | Polish once the wiring is stable | Rung 0 demo; ejected theme renders identically |
| 4 Platform | Evaluate upgrading the bundled client to LiveView 1.x (`_unused_`, `phx-no-unused-field`, keyed comprehensions); LiveComponent binding (PR #126) for sub-form components; async validators with a pending state; wizards; opt-in autosave | Larger cross-cutting changes | Tracked separately |

Some questions remain open, and a few deserve an explicit decision before code is written.

| Question | Options | Current lean |
|---|---|---|
| Stateless rebuild or stateful tree? | Ecto single-use; Ash in-place tree; hybrid | Hybrid: store `Form` in context, but make `change()` a pure function of data, full params and `used` |
| Upgrade the bundled Phoenix client? | Stay on 0.20.17; move to 1.x | Design behind a `used()` abstraction now; decide separately, since 1.x brings `_unused_` and `phx-patch-focused` ([LV v1.2 CHANGELOG](https://github.com/phoenixframework/phoenix_live_view/blob/v1.2/CHANGELOG.md)) |
| Prefixed names by default? | `signup[email]`; flat `email` | Prefixed: multiple forms per view, no collision with binder-reserved names (`event`, `payload`, `socket`, `url`, `params`, `session`), Phoenix-compatible; `as_=None` opts out |
| Row identity | Index plus `_key`; UUID-keyed dicts (Filament) | Index plus `_key`: matches Ecto's protocol and keeps names short |
| Hidden variant data | Discard; stash | Discard by default, stash opt-in |
| Schema backends | pydantic only; a Standard Schema-like bridge | pydantic plus dataclasses now; keep `FormError` backend-neutral so a bridge ([uniforms Bridge](https://github.com/vazco/uniforms/blob/master/packages/uniforms/src/Bridge.ts)) can come later |
| Ibis ergonomics | Live with literal args; add kwargs or macros to the vendored Ibis | Live with it for v1: dict-literal args, `form.fields.*`, `include ... with` |
| Native constraints | Emit with `novalidate`; native blocking; none | Emit with `novalidate` |
| Error timing default | `blur`; `submit`; `live` | `blur`, pending a browser test of the debounce flip |
| Where does `used` come from on 0.20.17? | `_target` history; `phx-blur` events; client hook | `_target` history plus blur-debounce; accept the minor false positive on recovery |
| Legacy `payload` blanks | Keep dropping; switch to `keep_blank_values=True` | Switch with a changelog note |
| i18n | Built-in catalog; Gettext/Babel hook | English catalog plus `translate(error)` hook |

## Conclusion

The most useful reframing from this research is that pyview's form problem is a **protocol and wiring problem, not a widget problem**. The Phoenix client already speaks a sufficient wire language: bracket names, `_target` paths, submitter buttons that work as change inputs, and whole-form replay on reconnect. Ecto already showed how to turn that language into an immutable value with action-gated errors. What pyview lacks is the two layers in between: a lossless, type-directed decoder and a view-model that owns every attribute affecting correctness. Build those, and zero-boilerplate auto-rendering becomes a thin, almost cosmetic layer, and every customization rung inherits correct names, ARIA and error timing instead of re-implementing them. Build auto-rendering first, and you get FastUI.

The less obvious implication is strategic. The JavaScript world spent 2024 to 2026 rebuilding "server returns values and errors, client re-renders" with intents, server actions and state merging. pyview gets that loop for free, and its server-held state makes Conform's "no-JS fallback" path the default. So pyview can credibly offer something no Python library has shipped: a pydantic class that yields a deeply nested, polymorphic, accessible live form with no client code. The main risk to that promise is not missing features. It is the discipline to ship the unglamorous Phase 0 first.
