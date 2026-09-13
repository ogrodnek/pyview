# Developer sentiment across ecosystems: what people love and hate about form libraries — Django 5.x, WTForms 3.x, Ecto 3.14 / LiveView 1.0, Rails 7/8 + cocoon, RHF 7, Formik 2, TanStack Form 1, Conform 1.x, Superforms 2.30, RJSF 5, JSON Forms 3, FormKit 1, Livewire 3 / Filament 3, Blazor (.NET 8/9), Pydantic 2.13, htmx — researched 2026-09-12

Method: WebSearch summaries (most doc sites are egress-blocked, so snippets and GitHub issues/discussions carry the quotes), GitHub issue/discussion fetches, grep of shared clones (`phoenix_live_view`, `ecto`, `django`, `conform`, `superforms`, `rhf`), and real pydantic 2.13.4 runs in the pyview venv. Quotes are short; anything I could not open directly is marked "(unverified)".

## TL;DR

- The single most-hated thing everywhere is **dynamic/nested collections**: Django formsets + `TOTAL_FORMS` bookkeeping, WTForms `FieldList` with no `remove_entry`, Ecto `cast_assoc` + `on_replace` + `sort_param/drop_param`, Rails `accepts_nested_attributes_for` + `_destroy` + strong-params duplication, RHF `useFieldArray` typing/`shouldUnregister` traps, Superforms' "nested data needs JS + `dataType: 'json'`", Blazor's validator that ignores nested objects. Every ecosystem needed a third-party gem/plugin or a tutorial industry to paper over it.
- The most-loved things are **explicitness and composability with zero boilerplate at the call site**: Ecto changesets (pipelines you can read), Filament's fluent `->schema([...])` DSL ("best-in-class"), simple_form / crispy-forms' one-liner rendering, RHF's "uncontrolled, no re-renders, 9 KB", Superforms' "works without JS, `SuperDebug`, defaults generated from the schema", Conform's "any valid HTML form, FormData is the contract".
- **Styling is the perennial complaint in server-rendered stacks**: Django needed three rounds (template widgets in 1.11/#15667, `FORM_RENDERER` in 4.0, `as_field_group()` in 5.0) plus crispy/widget_tweaks; RJSF/JSON Forms users fight testers/templates to escape the "generic look".
- **"Touched/used" semantics are a client-vs-server fight**: LiveView's client-side `phx-feedback-for` generated a stream of bugs (#1166, #1282, #2968) and was replaced in 1.0 by server-side `used_input?/2` + `_unused_` params. pyview is on the 0.20 client so it inherits the old model.
- **Schema-to-form is universally wanted and universally disappointing when it is the only path**: RJSF/JSON Forms/FormKit schema get praised for speed-to-first-form, damned for customization walls. Libraries that win offer "schema does the rest *and* you can hand-write the HTML" (Conform, Superforms, Filament).
- **Pydantic is not a form parser**: `""` for `Optional[int]` fails (`int_parsing`), an unchecked checkbox is *absent*, `bool_parsing` rejects `""`, error `msg`s are developer-grade ("String should match pattern '^[a-z0-9-]+$'"), FastAPI `Form` models are flat. A pyview form layer must own an HTML-to-Python coercion step *before* pydantic.
- Round-trip latency + debounce defaults are the LiveView/Livewire-family pain: Livewire's `wire:model.live` defaults to 150 ms debounce, Filament repeaters with hundreds of rows take 10-30 s per action. pyview must send small diffs and default to sensible debounce.

## Mental model & core abstractions (what people say about them)

- **Django `Form`/`ModelForm`/`formset_factory`**: universally praised as "batteries included" for the *flat* case; the mental model breaks at formsets (a `ManagementForm` with `TOTAL_FORMS`/`INITIAL_FORMS`, error text "ManagementForm data is missing or has been tampered with" — verified in `django/forms/formsets.py:61`). Every "add a row" tutorial (Medium, GeeksforGeeks, brennantymrak.com, django-dynamic-formset) is about cloning an `empty_form` and incrementing `TOTAL_FORMS` by hand.
- **WTForms `Form` + `FieldList(FormField(...))`**: liked for being framework-agnostic and simple; disliked because `FieldList` only had `append_entry()`/`pop_entry()` ("I cannot delete an arbitrary entry. I would like to see a remove_entry(index)" — wtforms#256, later closed via PR #901). No typing, no dataclass/pydantic bridge: people write "declare fields twice" code.
- **Ecto `Changeset`**: the praise is about *explicitness*: "developers can easily provide different changesets for different use cases … `registration_changeset` and `update_changeset`" (Ecto docs), "validations and constraints define an explicit boundary when the check happens". Schemaless changesets (`Ecto.Changeset.cast({%{}, types}, params, keys)`) are recommended to separate web forms from persistence ("an Ecto.Changeset should not have a dependency that influences web forms" — elixirfocus.com).
- **LiveView `to_form/2` + `<.form for={@form}>` + `<.inputs_for :let={f} field={@form[:items]}>`**: praised for being a thin, server-owned model; pain is the number of moving parts for nested data (see Nested section).
- **Rails `form_with` + `accepts_nested_attributes_for` + strong params**: nested attributes have been disliked since 2009 ("While a very nice and 'magical' feature, I've got to admit that I'm really not that crazy about how it works" — smartlogic.io) and `simple_form` is praised precisely because it hides the markup.
- **RHF `useForm()/register/useFieldArray`**: praised for "uncontrolled architecture that eliminates re-renders" and 9-12 KB vs Formik's 44 KB with 7 dependencies; Formik "hasn't had a major release since 2021 and is effectively in maintenance mode" (LogRocket, pkgpulse). Formik's decline is attributed to per-keystroke re-renders on large forms.
- **TanStack Form `form.Field` render props**: praised for granular reactivity and type inference; criticised as "verbose out-of-the-box … not ideal in production" with `form.Field - Field - Label - Input - FieldDescription - FieldError` nesting; TanStack answered with `form.AppField`/`createFormHook` and admits it "doesn't solve the problem of form boilerplate" (TanStack/form discussion #2031).
- **Angular reactive forms**: "it can feel like you're setting up a small electrical grid just to collect a simple username and password"; typed forms add `NonNullableFormBuilder` gymnastics; Angular 21 Signal Forms is the "less boilerplate" answer (dev.to). 
- **Conform**: "does not restrict your form's markup and works with any valid HTML form … captured from the DOM using the FormData Web API" is the love; intents are first-class (`type: 'validate' | 'reset' | 'update' | 'remove' | 'insert' | 'reorder'` in `conform-dom/submission.ts`, verified for the first four).
- **Superforms**: "requires no JavaScript by default but offers full support for progressive enhancement", "generates default form values from validation schemas", `SuperDebug` component (all in README). Its own `AGENTS.md` admits "the codebase is well-structured but complex, especially superForm.ts".
- **Filament**: "form DSL is described as best-in-class in the Laravel ecosystem, with nothing else coming close" (Kirschbaum); "build forms in a single place without jumping between backend controllers, form requests, and frontend views".
- **RJSF / JSON Forms / FormKit schema**: loved for "give me a JSON schema, get a form"; disliked because customisation is a stack of `widgets`, `fields`, `templates`, `uiSchema`, `ui:options` (RJSF) or rank-based `testers` (JSON Forms: "difficulties trying to build testers for custom renderers").

## Data in (naming, parsing, coercion, nested/lists)

Sentiment clusters:

1. **Bracket naming is the de-facto standard and people accept it** (`user[address][city]`, `items[0][name]`, Rails/Rack, Phoenix `Plug.Conn.Query`, Django formsets' `form-0-name` is the *odd one out* and is disliked for needing a prefix scheme). Conform and Superforms both decode dotted/bracketed names into nested objects on the server; Superforms can only do it *with* JS: "Set the dataType option to \"json\" and add use:enhance to use nested data structures" (verified string in `superForm.ts:575`). That limitation is a documented complaint.
2. **HTML sends strings, empties and absences; every library that forgets this generates issues.**
   - Pydantic (real run, 2.13.4): `Prefs(age="", nickname="")` → `int_parsing ('age',) | Input should be a valid integer, unable to parse string as an integer | input=''`; `newsletter=""` → `bool_parsing`; `newsletter="on"` → `True`. Discussion pydantic#2687 ("convert empty string to None") closed with "write a validator": `@validator('*') def empty_str_to_none(cls, v): return None if v == '' else v` (v1) / `Annotated[Optional[int], BeforeValidator(empty_to_none)]` (v2).
   - FastAPI: "Pydantic models in forms are flat with no nested models" (docs); discussion #9409: "Then it just doesn't work when the checkbox is unchecked. There's always 'value error missing'" — the unchecked checkbox is *absent*, so the model must default it. PR fastapi#13537 "Fix support for form values with empty strings interpreted as missing (`None` if that's the default), for compatibility with HTML forms" shows the framework had to special-case it.
   - Conform: the macwright.com gripe (unverified, blocked) is that an empty `<textarea>` becomes `undefined` instead of `""`, so "Zod schemas that are anticipating Conform, FormData, and form elements all working in an awkward way".
   - Django's answer (praised): each `Field.to_python()` knows `empty_values`, `BooleanField` treats missing as `False`, `NullBooleanField` exists, `MultipleChoiceField` uses `getlist`. Nobody complains about Django coercion — it's the model to copy.
3. **Lists need stable identity, not indices.** RHF docs: "field.id (not index) must be used as the component key"; issue rhf#5318 "Nested Field Array Items are not correctly typed"; Ecto needs `:sort_param`/`:drop_param` (verified `ecto/lib/ecto/changeset.ex:1205-1208`: "`:drop_param` - the parameter name which keeps a list of indexes to drop", "`:sort_param` - … indexes to sort") and "when using `:drop_param`, the remaining elements are re-indexed sequentially".

## Validation & error model

- **Error shape**: everyone converges on *per-path lists of messages* plus a form-level bucket. Django `form.errors` (`ErrorDict` of `ErrorList`, `non_field_errors()`), Ecto `changeset.errors :: [{field, {msg, opts}}]` with `traverse_errors/2` for interpolation, Superforms `$errors` (nested object mirroring the data), Conform `fields.name.errors`/`form.errors`, RHF `formState.errors` (nested), RJSF `errorSchema`.
- **Message quality**: Pydantic's `msg` strings are widely described as "very unhelpful and cannot be used to show to users. For example, pattern-based validation errors output technical patterns" (pydantic discussion #8468; my run printed `String should match pattern '^[a-z0-9-]+$'` with `ctx={'pattern': ...}`). Solutions people reach for: map on `err["type"]`, third-party `pydantic-validation-formatter`. Ecto's `{msg, [validation: :length, kind: :min, count: 3]}` tuple is praised because the *params* travel with the message so gettext can pluralise.
- **Timing**: LiveView/Livewire "validate on every change but only *show* for used inputs" is the loved UX; the failure mode is showing all errors on mount (Django users get this when they bind a form with empty POST; LiveView 0.x users got the inverse: errors *not* showing — issue #1166 "errors are not displayed due to the continued presence of the phx-no-feedback class"). Livewire recommends `.live.debounce.500ms` or `.blur` for validation-heavy fields.
- **Server-vs-client duplication** is a recurring gripe in React land (Formik/RHF + separate API validation), and the reason Conform/Superforms/RVF ("progressive enhancement, same schema on both sides") are praised. htmx crowd: "In a hypermedia-driven UI, the form itself is the contract: the server returns HTML that represents the current state of the form" — validation stays server-side, `hx-trigger="blur"` + `hx-select` swaps a single field partial.

## Form state (bound/unbound, touched/used, attempted values)

- Django's bound/unbound split (`form.is_bound`, `initial` vs `data`, `field.value()` returning the *attempted* string on error) is rarely complained about; it is the baseline expectation: the user's bad input must re-render, not be lost.
- LiveView 1.0 moved "touched" to the server. Verified in `phoenix_component.ex:1758-1770`:
  ```elixir
  def used_input?(%Phoenix.HTML.FormField{field: field, form: form}) do
    used_param?(form.params, field)
  end
  defp used_param?(_params, "_unused_" <> _), do: false
  defp used_param?(params, field) do
    field_str = "#{field}"; unused_field_str = "_unused_#{field}"
    case params do
      %{^field_str => _, ^unused_field_str => _} -> false
  ```
  The client sends `"_unused_email" => ""` alongside `"email" => ""` until the input is touched. Changelog: "LiveView 1.0 removes the client-based phx-feedback-for annotation … replaced by Phoenix.Component.used_input?/2, which handles showing and hiding feedback using standard server rendering." Motivating bugs: #1166 (phx-focus errors hidden), #1282 (`phx-no-feedback` lost on live-patch), #2968 ("phx-feedback-for expects you to provide it a single input name, while the custom component houses more than a single input"). Elixir Streams tip title says it all: "LiveView 1.0: ❌ phx-feedback-for | ✅ used_input?".
- RHF's `formState.touchedFields/dirtyFields` are fine; the trap is `shouldUnregister: true` deleting values of unmounted (conditional) fields: docs say "Avoid combining useFieldArray with shouldUnregister: true"; discussion #8092 maintainers: "I don't think conditional `shouldUnregister` is the solution to your problem."
- Superforms' `tainted` store + `SuperDebug` (renders the whole form/errors/tainted state live) is one of the most-cited DX wins in reviews.

## Rendering, customization & styling

- Django's history is the cautionary tale: #15667 "Rendering widgets via templates addresses 90+% of the issues people have with customizing markup in Django forms" (django-developers, 2016); still not enough → 4.0 `FORM_RENDERER`/`form.template_name`; still not enough → 5.0 `{{ field.as_field_group }}` + `field_template_name` ("In the past, to take control of field layout, developers had to render field labels, help text, errors and fields one by one (or resort to use an external library)"). Meanwhile crispy-forms (`FormHelper`, `Layout(Row(Column('a'), Column('b')))`, `|crispy`) and `django-widget-tweaks` (`{% render_field form.name class="input" %}`) stayed popular because "as_table/as_ul/as_p … don't integrate well with modern CSS frameworks".
- Ruby: `simple_form`'s `f.input :email` wrapping label+input+hint+error in a configurable "wrapper" is the pattern people miss elsewhere.
- Phoenix: `core_components.ex` ships an `<.input>` *in the app* (not the library), Tailwind classes inline. Loved because you own it; the meta-complaint is "every project re-implements the same `<.input>`" and generators keep changing it.
- RJSF: layout is the chronic issue — #237 "Support for layout grid", #461, #3261 "How do I adjust the layout of specific form fields using Custom Templates", #3503 "Custom UI Layout", #3840, #4193; v5 added `templates` prop and later `LayoutGridField` (discussion #4658). JSON Forms: `rankWith(3, isControl and scopeEndsWith('x'))` testers "not working as expected" is the common thread (#1595).
- FormKit: "FormKit is not a UI framework or a layout tool … developers are still responsible for most of the form's style and layout"; Pro-tier paywall for autocomplete etc. draws complaints.
- Filament: fluent DSL loved; "DX outside the admin … is whatever you build" (dev.to CMS review).

## Nested / dynamic / conditional

Ranked by how much noise each generates:

1. **Ecto/LiveView**: tutorial proliferation is itself the evidence (LostKobrakai gist, yellowduck.be, arrowsmithlabs "advanced tips and tricks", fullstackphoenix, pearprogramming, Elixir Forum). Issue #2616: "If you remove every association of a collection, any other change to the form will cause all of the associations to be restored, as the absence of data for that field clears out the previous changes." `on_replace: :raise` is the default (`relation.ex:264`), so first-time users hit `"the :on_replace option of this relation is set to :raise"`. The pattern that finally became canonical (LiveView 0.19+/Ecto 3.10):
   ```heex
   <.inputs_for :let={f_line} field={@form[:lines]}>
     <input type="hidden" name="order[lines_sort][]" value={f_line.index} />
     <.input field={f_line[:qty]} type="number" />
     <button name="order[lines_drop][]" value={f_line.index} phx-click={JS.dispatch("change")}>x</button>
   </.inputs_for>
   <input type="hidden" name="order[lines_drop][]" />
   <button name="order[lines_sort][]" value="new" phx-click={JS.dispatch("change")}>add</button>
   ```
   paired with `cast_assoc(:lines, sort_param: :lines_sort, drop_param: :lines_drop)`. Praised once learnt ("no JS, no ids"), but the learning curve (a hidden empty `_drop[]` input; `value="new"` magic; `JS.dispatch("change")`) is the top complaint.
2. **Django formsets**: management form, `empty_form` cloning, `__prefix__` replacement, `can_delete` + `DELETE` checkbox, `inlineformset_factory`; "previously entered data disappears" when JS adds rows without bumping `TOTAL_FORMS`. Newer answers: django-formset (Alpine/htmx based), django-dynamic-formset (jQuery).
3. **Rails**: `accepts_nested_attributes_for :tasks, allow_destroy: true, reject_if: :all_blank` + `fields_for` + cocoon's `link_to_add_association` (jQuery) + permitting `tasks_attributes: [:id, :description, :_destroy]` — "you need to explicitly add both :id and :_destroy … a common source of duplication and confusion"; validation interactions (rails#20676 uniqueness-with-scope broken under nested attributes).
4. **RHF**: `useFieldArray({ control, name: "items" })` is good; nested arrays require `name: \`test.${index}.keyValue\` as 'test.0.keyValue'` casts (docs), appended objects "cannot be an empty object {}", `shouldUnregister` interactions (#4075, #2958, #8092).
5. **Blazor**: `DataAnnotationsValidator` "only validates top-level properties … that aren't collection- or complex-type properties"; you need `[ValidateComplexType]` + experimental `ObjectGraphDataAnnotationsValidator`; aspnetcore#58584 nested `ValidationMessage` not displaying though `ValidationSummary` does.
6. **Superforms/Conform**: nested works only with JS (`dataType: 'json'`); Conform "many issues with Conform (any complex forms)" (bryantbrock, epic-stack #933); Conform does have `form.insert({name: fields.items.name})`/`remove`/`reorder` intents that also work without JS via `serialize()`d buttons — a praised design.
7. **Filament `Repeater`**: fluent and pleasant (`Repeater::make('items')->schema([...])->reorderable()->collapsible()`), but "Repeater actions accompanied by Livewire updates can take over 10 seconds for each action (adding, deleting, moving)" with hundreds of rows because the whole form state round-trips.
8. **Conditional fields**: Filament `->visible(fn (Get $get) => $get('type') === 'x')` + `->live()` is the loved API; Django has nothing (`clean()` if/else); RHF `watch('type')` + `shouldUnregister`; JSON Schema `dependencies`/`if-then-else` in RJSF is described as workable but verbose.

## DX highlights with real code (cited)

1. **Ecto pipeline readability** (Ecto docs):
   ```elixir
   def registration_changeset(user, attrs) do
     user
     |> cast(attrs, [:email, :password])
     |> validate_required([:email, :password])
     |> validate_length(:password, min: 12)
     |> unique_constraint(:email)
   end
   ```
2. **LiveView used-input gating** (`phoenix_component.ex`, verified above): `errors = if Phoenix.Component.used_input?(field), do: field.errors, else: []`.
3. **Filament fluent DSL** (Kirschbaum / Filament docs, API names verified in earlier researchers' notes): `TextInput::make('slug')->required()->unique(ignoreRecord: true)->live(onBlur: true)`.
4. **RHF** (`rhf/src/useFieldArray.ts:57`): `const { fields, append } = useFieldArray({ control, name: "items" });` then `fields.map((f, i) => <input key={f.id} {...register(\`items.${i}.name\`)} />)`.
5. **Superforms** (README): `const form = await superValidate(request, zod(schema)); return { form }` on the server; client `const { form, errors, enhance } = superForm(data.form)` + `<SuperDebug data={$form} />`.
6. **Django 5.0** (docs): `{{ form.email.as_field_group }}` renders label+widget+help+errors from `django/forms/field.html`, overridable via `Form.field_template_name`.
7. **Pydantic coercion glue people write** (pydantic #2687): `EmptyStrToNone = Annotated[Optional[int], BeforeValidator(lambda v: None if v == "" else v)]`.

## Pain points & criticisms — ranked top 15

1. **Dynamic collections need hand-rolled JS or magic params** — Django formsets (`TOTAL_FORMS`), WTForms `FieldList` (#256), Rails cocoon, Ecto `sort_param/drop_param`, Superforms JS-only nesting.
2. **Removed nested items resurrect / replace semantics** — LV #2616, Ecto `on_replace: :raise`, Rails `_destroy` + `id` permit list.
3. **HTML→typed coercion left to the user** — pydantic `""`→`int_parsing`, `bool_parsing` on `""`, absent checkbox = "missing" (fastapi #9409, #13537), Conform empty textarea→`undefined`.
4. **Technical error messages** — pydantic (#8468), Blazor default DataAnnotations text, RJSF ajv messages ("must match pattern").
5. **Styling/markup escape hatches are late and layered** — Django 1.11→4.0→5.0, RJSF templates/widgets/uiSchema, JSON Forms testers, FormKit "not a layout tool".
6. **Touched/feedback state done on the client breaks** — LV `phx-feedback-for` bugs #1166/#1282/#2968 → replaced.
7. **Nested typing** — RHF #5318, #5054, nested `useFieldArray` string casts; Angular typed forms `NonNullableFormBuilder`; WTForms untyped.
8. **Conditional fields + unregister semantics** — RHF `shouldUnregister` (#8092, #4075); Blazor nested validation gap.
9. **Boilerplate per field** — TanStack `form.Field` nesting (#2031), Angular "electrical grid", Django "render label/help/errors one by one".
10. **Round-trip latency / payload size** — Filament repeater 10-30 s, Livewire 150 ms default debounce on `.live`, "every keystroke … full HTTP round-trip".
11. **Validation duplicated client vs server** — Formik/RHF + API; praised fix is one schema (Conform/Superforms/RVF) or server-only (htmx/LiveView).
12. **Schema-driven forms hit a wall at real UIs** — RJSF layout issues #237/#3503/#4193, JSON Forms, FormKit Pro paywall.
13. **Maintenance/abandonment risk** — Formik unmaintained; Conform "numerous unresolved GitHub issues" (epic-stack #933) though Kent: "He's definitely still very committed".
14. **Strong-params/permit duplication** — Rails nested `permit(tasks_attributes: [:id, :_destroy, ...])`; Django `fields = [...]` in ModelForm meta repeated across forms.
15. **Nested forms tutorials diverge from generators** — Phoenix `core_components.ex` changes each release; every LV nested-form article has a different hidden-input recipe.

## Praised patterns — top 10

1. Explicit, composable validation pipelines separate from the schema (Ecto changesets; schemaless changesets for forms).
2. Server as source of truth + progressive enhancement (Superforms, Conform, htmx, LiveView).
3. One-line field rendering that includes label/hint/errors, with a pluggable wrapper (simple_form `f.input`, crispy `|crispy`, Django `as_field_group`, Filament components, Phoenix `<.input>`).
4. Defaults generated from the schema (Superforms `defaults(schema)`, Filament `->default()`, Django `initial`).
5. Debug surface (Superforms `SuperDebug`, RHF DevTools).
6. Stable item identity in lists (RHF `field.id`; Ecto `:sort_param` indexes with `"new"` sentinel).
7. Intents as first-class form actions that work with or without JS (Conform `insert/remove/reorder/update/validate/reset`; LiveView `name="...sort[]" value="new"` buttons).
8. Uncontrolled / minimal-diff updates (RHF no re-render; LiveView diffs; Livewire `.blur`/`.debounce`).
9. Fluent, single-file field definitions with conditional visibility (`->visible(fn (Get $get) ...)`, `->live(onBlur: true)`).
10. Coercion tables per field type that understand HTML (Django `Field.to_python`/`empty_values`, `BooleanField` missing→False, FastAPI #13537).

## Lessons for pyview — steal / adapt / avoid

**Steal**
- Ecto's shape: `Changeset(model_cls).cast(params, fields).validate_*()...` returning a value with `changes`, `errors` (list of `(msg, params)` per path), `valid`, `params`, and `apply_action(:insert)` semantics. Keep changesets *separate* from the pydantic class: a pydantic model is the *type*, the changeset is the *attempt*.
- LiveView 1.0 `used_input?` semantics implemented server-side: track "used" per path from `_target` history (0.20 client) and be ready for `_unused_*` keys (1.0 client). Never rely on a `phx-feedback-for` CSS trick.
- Ecto's `sort_param`/`drop_param` protocol for lists, but generate it: a `form.list("lines")` helper that emits the hidden `lines_drop[]` input, `add`/`remove` buttons with `phx-click` JS dispatch, and decodes `lines_sort`/`lines_drop` before pydantic sees the data.
- Conform-style intents: `_intent=insert:lines`, `remove:lines.2`, `reorder:lines:2:0` handled by the form layer, not by user `handle_event`s.
- Django's `Field.to_python` philosophy as a pre-pydantic **HTML coercion pass**, driven by the pydantic field annotation: `""`→`None` for `Optional[...]`, absent→`False` for `bool`, `getlist` for `list[...]`/multi-select, `"on"`→`True`, strip; then `model_validate(..., strict=False)`.
- Superforms' `SuperDebug`: a `{{ form | debug }}` / `self.form_debug(form)` t-string helper that dumps params/changes/errors/used.

**Adapt**
- Filament-style conditional visibility, but declared on the pydantic side: `Annotated[str, FormField(visible_when=lambda data: data.type == "x")]` or a discriminated `Union` mapped to a `<select>` that swaps the nested sub-form. Discriminated unions are how pydantic already models "conditional nesting"; make that the first-class path.
- Django 5 `as_field_group` + simple_form wrappers: ship one default wrapper (`label + input + hint + errors`) as a **t-string component the user can copy into their project** (Phoenix `core_components` model), plus attribute-level hooks (`class_`, `attrs`) for widget_tweaks-style tweaks in Ibis.
- Pydantic error messages: map `err["type"]` + `ctx` to translatable templates (`"string_pattern_mismatch": "Must match {pattern}"`), and let `Field(json_schema_extra={"error_messages": {...}})` or a per-form dict override. Keep `(msg, params)` tuples so i18n works.
- Debounce defaults: emit `phx-debounce="blur"` on text inputs by default (Livewire's lesson), `phx-change` validates the whole model but only re-renders errors for used paths.

**Avoid**
- Client-side "feedback" CSS hacks (`phx-feedback-for`) as the only touched model.
- Index-keyed lists with no identity: always give list rows a stable key (`index` from server + `_persistent_id`) so removals don't resurrect (LV #2616).
- A schema-only rendering path with no hand-written escape hatch (RJSF/JSON Forms wall). Every auto-rendered field must be replaceable by user HTML that still binds via `form[...]` helpers for `name`/`id`/`value`/errors.
- Passing raw `parse_qs` results into pydantic (today's `ChangeSet.apply` does `payload.get(k, [""])[0]`): flat, scalar, loses multi-select, and produces `int_parsing` on empty inputs.
- Requiring JS for nested data (Superforms `dataType: 'json'`): bracket-name decoding on the server is table stakes.
- Whole-form state round-trips on every keystroke for big repeaters (Filament): keep list rows as LiveComponents or streams where possible.

## Sources (URLs / repo paths actually read)

- https://github.com/phoenixframework/phoenix_live_view/issues/2616 (fetched)
- https://github.com/phoenixframework/phoenix_live_view/issues/2968, /issues/1166, /issues/1282 (search summaries)
- repos/phoenix_live_view/lib/phoenix_component.ex:1700-1770 (`used_input?`, `_unused_`)
- repos/ecto/lib/ecto/changeset.ex:1116-1160, 1205-1208, 1391; repos/ecto/lib/ecto/changeset/relation.ex:260-267
- https://www.elixirstreams.com/tips/liveview-used-input ; https://hexdocs.pm/phoenix_live_view/1.0.0/changelog.html (summary)
- https://gist.github.com/LostKobrakai/ce5385bd118189a24d60893188612de9 ; https://www.yellowduck.be/posts/nested-forms-in-phoenix-liveview-advanced-tips-and-tricks ; https://arrowsmithlabs.com/blog/phoenix-liveview-nested-forms-advanced-tricks ; https://fullstackphoenix.com/tutorials/nested-model-forms-with-phoenix-liveview
- https://elixirfocus.com/posts/ecto-schemaless-changesets/ ; https://hexdocs.pm/ecto/data-mapping-and-validation.html (summary)
- repos/django/django/forms/formsets.py:61 ; https://code.djangoproject.com/ticket/15667 ; https://groups.google.com/g/django-developers/c/fMQnk2fAo_A ; https://www.brennantymrak.com/articles/django-dynamic-formsets-javascript ; https://github.com/elo80ka/django-dynamic-formset ; https://medium.com/@pysquad/django-5-0-forms-faster-development-with-fewer-lines-b7d52c329418 ; https://smithdc.uk/blog/2023/bootstrap_form_in_vanilla_django/ ; https://simpleisbetterthancomplex.com/tutorial/2018/11/28/advanced-form-rendering-with-django-crispy-forms.html
- https://github.com/pallets-eco/wtforms/issues/256 (fetched) ; https://www.rmedgar.com/blog/dynamic-fields-flask-wtf/
- https://github.com/pydantic/pydantic/discussions/2687 (fetched) ; https://github.com/pydantic/pydantic/discussions/8468 ; https://github.com/fastapi/fastapi/discussions/9409 (fetched) ; https://github.com/fastapi/fastapi/pull/13537 ; https://github.com/fastapi/fastapi/discussions/12150 ; pydantic 2.13.4 run output above
- https://smartlogic.io/blog/2009-02-24-rails-23-nested-object-forms-im-not-crazy-about-them/ ; https://github.com/nathanvda/cocoon ; https://github.com/rails/rails/issues/20676 ; https://www.sitepoint.com/better-nested-attributes-in-rails-with-the-cocoon-gem/
- https://github.com/react-hook-form/react-hook-form/discussions/8092 (fetched) ; /issues/4075 ; /issues/5318 ; /issues/5054 ; /issues/4138 ; repos/rhf/src/useFieldArray.ts:57 ; repos/rhf/src/types/form.ts:132
- https://blog.logrocket.com/react-hook-form-vs-formik-comparison/ ; https://www.pkgpulse.com/guides/react-hook-form-vs-formik-2026 ; https://reidburke.com/updates/2025/01/react-hook-form-vs-formik/
- https://blog.logrocket.com/tanstack-form-vs-react-hook-form/ ; https://github.com/TanStack/form/discussions/2031 ; https://makersden.io/blog/composable-form-handling-in-2025-react-hook-form-tanstack-form-and-beyond
- https://www.bitovi.com/blog/rfc-strictly-typed-reactive-forms-gotchas-every-angular-developer-needs-to-know ; https://dev.to/karol_modelski/angular-signal-forms-explained-build-safer-forms-with-less-boilerplate-1mci
- https://github.com/ciscoheat/sveltekit-superforms (README, AGENTS.md summaries) ; repos/superforms/src/lib/client/superForm.ts:107-158, 562-575
- https://github.com/edmundhung/conform (README) ; https://github.com/epicweb-dev/epic-stack/discussions/933 (fetched) ; repos/conform/packages/conform-dom/submission.ts:315-360 ; https://macwright.com/2024/05/28/remix-form-gripes (blocked; via search summary, unverified)
- https://github.com/rjsf-team/react-jsonschema-form/issues/237, /461, /3261, /3503, /3840, /4193, /discussions/4658 ; https://github.com/eclipsesource/jsonforms/issues/1595 ; https://kukshalkanishka.medium.com/customising-json-forms-7fc75f627fff
- https://blog.logrocket.com/powerful-vue-js-form-development-formkit/ ; https://dev.to/jacobandrewsky/building-accessible-forms-in-vue-with-formkit-4n7o
- https://kirschbaumdevelopment.com/insights/why-we-love-filament ; https://dev.to/tonegabes/how-filament-saved-or-complicated-my-admin-panel-an-honest-review-156b ; https://www.answeroverflow.com/m/1227542045644689448 ; https://www.answeroverflow.com/m/1395754080684736512 ; https://laracasts.com/discuss/channels/livewire/painfully-slow-interface-with-filamentlivewire-in-production
- https://laravel-news.com/livewire-wire-model-live ; https://msaied.com/articles/livewire-v3-performance-optimistic-ui-wiremodellive-debouncing-and-dirty-state ; https://dev.to/emongmarcc/laravel-livewire-wiremodel-deep-dive-reactivity-debouncing-and-lazy-binding-explained-17al
- https://github.com/dotnet/aspnetcore/issues/58584 ; https://www.pragimtech.com/blog/blazor/validating-complex-models-in-blazor/ ; https://code-maze.com/complex-model-validation-in-blazor/
- https://blog.openreplay.com/form-validation-simple-htmx/ ; http://hernantz.github.io/inline-form-validation-with-django-and-htmx.html ; https://htmx-workshop.com/ui-examples/inline-validation/
