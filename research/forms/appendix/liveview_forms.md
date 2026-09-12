# Phoenix LiveView forms (server side): to_form, <.form>, <.inputs_for>, FormField, used inputs, validation flow — versions researched: phoenix_live_view 1.2.11 (main @ 2026-09-11) + v1.0.0 changelog + v0.20.17 JS client, phoenix_html 4.3.0, phoenix_ecto 4.7.0, phoenix 1.9.0-dev (main) + v1.7.10/v1.7.14 generated core_components, ecto 3.15.0-dev — researched 2026-09-12

## TL;DR (5-8 bullets)

- **Three separable layers, three libraries.** *Data* (`Ecto.Changeset`: cast → validate → errors with metadata → `action` gate) lives in `ecto`; the *form abstraction* (`%Phoenix.HTML.Form{}`, `%Phoenix.HTML.FormField{}`, the `Phoenix.HTML.FormData` protocol) lives in `phoenix_html`; the *adapter* from changeset to form (`Phoenix.HTML.FormData` impl for `Ecto.Changeset`, incl. `input_validations`) lives in `phoenix_ecto`; *rendering* (`<.form>`, `<.inputs_for>`, `to_form/2`, `used_input?/1`) lives in `phoenix_live_view`; *widgets/styling* (`<.input>`, `translate_error`) are generated **into the user's app** (`core_components.ex`), not shipped as a library.
- **One data structure to rule templates:** `@form[:field]` returns a `FormField{id, name, value, errors, field, form}`; `id`/`name` are derived mechanically (`user_email` / `user[email]`; nested `user[addresses][0][city]`), `value` follows the precedence *changes → params → data*, so the template never chooses between "submitted" and "original" values.
- **Errors are gated by `action`:** `to_form(changeset)` returns `errors: []` when `changeset.action` is `nil` or `:ignore`, otherwise `changeset.errors`. `handle_event("validate")` sets `action: :validate`; `Repo.insert` failing sets `:insert`. This is why a freshly mounted invalid form shows no errors.
- **"Used input" gating moved from client to server in 1.0:** the 1.x JS client appends a sibling `_unused_<name>=` param for every input that was neither changed nor submitted; `Phoenix.Component.used_input?(field)` reads it (recursing into nested maps). The **0.20.x client that pyview ships does *not* send `_unused_`** — it instead toggles a `phx-no-feedback` CSS class on `[phx-feedback-for=<input name>]` containers client-side.
- **Nested/dynamic forms = naming convention + two extra params.** `<.inputs_for>` renders one sub-form per child, injects hidden `_persistent_id` (and primary-key) inputs, and index-names everything; add/remove/reorder is done *without server events* by hidden `parent[children_sort][]` inputs and `parent[children_drop][]` buttons/checkboxes that fire `phx-change` (`JS.dispatch("change")`), interpreted by `Ecto.Changeset.cast_assoc/cast_embed(sort_param:, drop_param:)`.
- **Client features you get for free from the wire protocol:** `_target` key-path, `phx-debounce="blur"|ms`, `phx-throttle`, `phx-disable-with`, `phx-submit-loading`/`phx-change-loading` classes, focused-input protection during DOM patches, automatic form recovery on reconnect (re-sends `phx-change` or `phx-auto-recover` event), `phx-trigger-action` for hand-off to a plain HTTP POST, `type="reset"` handling.
- **Main criticisms:** `to_form(map)` gives you naming but zero validation (`input_validations` → `[]`), so "no Ecto" means "write your own validation"; the sort/drop recipe is clever but must be re-typed per association (hidden sort input, drop button, empty drop input, `on_replace: :delete`); `used_input?`/`action` gating has a long history of confusion (issues #1135, #2968, #3235, #3757; `phx-feedback-group` introduced in 0.20.4 and deprecated in 0.20.5); `field.value` is untyped (struct *or* raw params) so derived values must be computed in `handle_event`.

## Mental model & core abstractions

**The pipeline.** Browser form → JS client serialises `<form>` via `FormData` into a urlencoded string (`view.ts serializeForm/3`) → `Phoenix.LiveView.Channel.decode_event_type("form", ...)` runs `Plug.Conn.Query.decode/1` (bracket names → nested maps, `[]` → lists, max nesting 32), merges `meta` (`phx-value-*` attrs and `JS.push(value:)`), and converts the `_target` string into a key path (`"user[username]"` → `["user", "username"]`, `channel.ex` L910-942) → `handle_event/3` receives `%{"user" => %{...}, "_target" => [...]}` → user code builds a changeset → `to_form/2` → `assign(socket, form: ...)` → template reads `@form[:field]`.

**`%Phoenix.HTML.Form{}`** (`phoenix_html/lib/phoenix_html/form.ex`): fields `source` (the changeset/map), `impl` (protocol module, cached), `id`, `name`, `data` (original struct/map), `params` (raw string-keyed submitted params), `errors` (keyword `[{field, {msg, opts}}]`), `hidden` (keyword of hidden inputs to emit — primary keys, `_persistent_id`), `action`, `options`, `index` (position inside an `inputs_for` list, else nil). It implements `Access`, and `form[:field]` (`Form.fetch/2`) builds:

```elixir
%Phoenix.HTML.FormField{
  errors: field_errors(errors, field),        # all {^field, error} tuples
  field: field,                               # atom or string
  form: form,                                 # back-reference to parent form
  id: input_id(form, field_as_string),        # "#{form.id}_#{field}"  (or "#{field}" if form.id nil)
  name: input_name(form, field_as_string),    # "#{form.name}[#{field}]" (or "#{field}" if name nil)
  value: input_value(form, field)             # impl.input_value(source, form, field)
}
```
(Source: `phoenix_html/lib/phoenix_html/form.ex` L85-115, L130-165.) Accessing a field that doesn't exist in the source still returns a FormField with `id`/`name` populated — the docs call this out as intentional, and it is what lets you render inputs for virtual fields.

**`Phoenix.HTML.FormData` protocol** (`form_data.ex`) — four callbacks: `to_form(data, opts)` (root), `to_form(data, form, field, opts)` (nested: returns a *list* of sub-forms — one for cardinality-one, N for lists), `input_value(data, form, field)`, `input_validations(data, form, field)`. The shared options are `:as`, `:id`, `:default`, `:prepend`, `:append`, `:action`. Everything else is implementation-specific and is stashed in `form.options`.

**Two shipped implementations:**

1. *Map* (`form_data.ex`, `defimpl ... for: Map`): the map *is* the params (must be string-keyed — atom keys produce an `IO.warn`), `data: %{}`, `errors:` taken from the `:errors` option, `input_value` = params first then data, `input_validations` = `[]`. Nested `to_form/4` uses `:default` to decide cardinality (`%{}` → one form; `[]` → many) and, for lists, sorts `params` by key or falls back to `prepend ++ default ++ append`.
2. *Ecto.Changeset* (`phoenix_ecto/lib/phoenix_ecto/html.ex`): `name` derived from the struct module (`MyApp.Users.User` → `"user"`, raising if data is not a struct and no `:as`), `id = opts[:id] || name`, `errors: form_for_errors(changeset, action)` which is `[]` when action is `nil`/`:ignore`, `hidden:` = primary-key values of loaded data, `options: [method: "put" | "post"]` based on `__meta__.state`. `input_value` precedence is `changes[field]` → `params["field"]` → `data.field`. `input_type/3` maps Ecto types to widget kinds; `input_validations/3` maps `changeset.required` and `changeset.validations` to HTML attributes (details below).

**`Phoenix.Component.to_form/2`** (`phoenix_component.ex` L1638-1690) is a thin wrapper: for an existing `%Form{}` it overrides `:as`/`:id`/`:action`/`:errors` and merges the rest into `form.options`; for anything else it calls `Phoenix.HTML.FormData.to_form(data, options)`. Options: `:as`, `:id`, `:errors` (maps only), `:action`.

**`<.form>`** (`phoenix_component.ex` L2498-2560) calls `to_form(assigns.for || %{}, [as:, csrf_token:, errors:, method:, multipart:] ++ rest)`, then: only if an `action` attribute is given does it emit `action`/`method` attrs, a hidden `_method` input for non-get/post, and a hidden `_csrf_token` (via `Plug.CSRFProtection.get_csrf_token_for(action)`) — *in LiveView there is no CSRF input at all; the websocket join carries the token*. `multipart` sets `enctype`. The docs discourage `:let={f}` inside LiveView: use `@form[:field]` so change tracking can diff per field (`Phoenix.HTML.Form.input_changed?/3` compares impl/id/name/action/errors/value).

## Data in: naming conventions, parsing, coercion, nested/list handling

**Names.** `input_name(form, field)` = `"#{form.name}[#{field}]"`; nested sub-forms get `name <> "[#{field}]"` (one) or `name <> "[#{field}][#{index}]"` (many); multi-selects and checkbox groups append `[]` (generated `<.input>`: `if assigns.multiple, do: field.name <> "[]"`). Real rendered output from LiveView's own tests (`test/phoenix_component/components_test.exs` L555-647):

```html
<!-- cardinality one -->
<input type="hidden" name="myform[inner][_persistent_id]" value="0">
<input id="myform_inner_0_foo" name="myform[inner][foo]" type="text">
<!-- cardinality many (default + prepend + append) -->
<input type="hidden" name="myform[inner][0][_persistent_id]" value="0">
<input id="myform_inner_0_foo" name="myform[inner][0][foo]" type="text" value="123">
<input type="hidden" name="myform[inner][1][_persistent_id]" value="1">
<input id="myform_inner_1_foo" name="myform[inner][1][foo]" type="text" value="456">
```
Note the DOM `id` uses the *persistent id*, not the list index (`"#{parent_form.id}_#{field_name}_#{persistent_id}"`, `phoenix_component.ex apply_persistent_id/4`), so reordering does not re-id inputs and the browser keeps focus/state.

**Parsing.** `Plug.Conn.Query.decode/1`: `a[b]=1` → `%{"a" => %{"b" => "1"}}`, `a[]=1&a[]=2` → `["1","2"]`, `a[0][x]=1` → `%{"a" => %{"0" => %{"x" => "1"}}}` — numeric indexes become **string map keys, not list positions** ("nesting inside lists is ambiguous and unspecified behaviour" per the moduledoc); Ecto later converts index-keyed maps to lists (`cast_params/4` sorts by integer key via `key_as_int/1`). Last duplicate wins for scalars; keys without values are `""`. Max nesting 32.

**Coercion is Ecto's job, not the form's.** `cast(data, params, permitted)` casts strings to the schema types (`:integer`, `:boolean` accepts `"true"/"false"/"on"`, `:date`, etc.), turning `""` into `nil` by default (`empty_values`), and produces `{field, {"is invalid", [type: :integer, validation: :cast]}}` on failure. The form layer stores *both* `params` (strings) and `changes` (typed); `input_value` prefers `changes`, so after a valid cast the template sees typed values (and `normalize_value/2` re-stringifies `datetime-local`, `checkbox`, `textarea`). The docs warn explicitly: "an `:integer` field may either contain integer values, but it may also hold a string, if the form has been submitted" — `field.value` is deliberately untyped.

**Checkbox trick** (generated `<.input type="checkbox">`, `core_components.ex.eex` L209-240): a hidden `<input type="hidden" name={@name} value="false" disabled={@rest[:disabled]} form={@rest[:form]}/>` precedes the real `<input type="checkbox" name={@name} value="true" checked={@checked}>`; because last value wins in the decoder, unchecked → `"false"`, checked → `"true"`. `Phoenix.HTML.Form.normalize_value("checkbox", value)` → `html_escape(value) == {:safe, "true"}` decides `checked`.

**Selects**: `Phoenix.HTML.Form.options_for_select(options, selected)` accepts keyword lists (`["Admin": "admin"]`), 2-tuples, plain values, `:hr` separators, and nested lists/maps for `<optgroup>`; `selected` may be a list for `multiple`. **Textarea**: `normalize_value("textarea", v)` prefixes `"\n"` so a leading newline survives (`<textarea>{...}</textarea>` must have no whitespace). **Number inputs**: the client suppresses change events while `input.validity.badInput` is true (`live_socket.ts` ~L1885), so the server never sees a half-typed invalid number. **Password**: the form-bindings guide says values are "not reused" — but in phoenix_html 4.3 `normalize_value/2` has no password clause; the special-casing lived in the removed `password_input/3` helper (helpers moved to `phoenix_html_helpers` in phoenix_html v4.0.0, 2023-12-19). With the generated `<.input type="password">` the value *is* re-rendered unless you pass `value=` explicitly (guide's snippet does exactly that). Treat the guide sentence as stale (verified against source).

**Submitter & phx-value.** `serializeForm` injects a hidden input for the clicked submit button's `name`/`value` at its DOM position (so `<button name="user[addresses_drop][]" value="1">` participates like any field); `phx-value-*` attributes on the form and `JS.push(..., value: ...)` maps are merged into the top-level params (test: `payload.meta == {_target: "increment", attribute_value: "attribute", nested: {...}}`, `assets/test/view_test.ts` L503-545). File inputs are stripped from the serialised payload (uploads go through a separate channel).

## Validation & error model (structure, codes vs messages, params, i18n, cross-field, when validation runs)

**Structure.** `changeset.errors :: [{atom, {String.t, Keyword.t}}]`, e.g. `[age: {"is invalid", [type: :integer, validation: :cast]}, name: {"can't be blank", [validation: :required]}]`. The message is a *template* with `%{count}`-style placeholders and the keyword carries machine-readable metadata: `validation: :required | :length | :number | :format | :inclusion | :cast | ...`, plus `count:`, `min:`, `max:`, `kind:`, `enum:`, `type:` as applicable, e.g. `{"should be at least %{count} characters", [count: 3, validation: :length, min: 3]}` (`ecto/lib/ecto/changeset.ex` `traverse_errors` doc, `validate_length` L3141). Every validator takes `:message` to override the template. Nested errors are *not* flattened: child changesets carry their own `errors`; `Ecto.Changeset.traverse_errors/2` walks embeds/assocs producing `%{title: ["..."], addresses: [%{city: ["can't be blank"]}, %{}]}`.

**Message rendering / i18n** is the app's concern: the generated `translate_error({msg, opts})` either interpolates `%{key}` from `opts` or, when Gettext is on, calls `Gettext.dngettext(MyAppWeb.Gettext, "errors", msg, msg, count, opts)` / `dgettext("errors", msg, opts)` — the untranslated template string is the msgid. So Ecto ships *codes + templates*, never final strings.

**Cross-field / custom.** `validate_change(changeset, field, fn field, value -> [{field, "msg"}] end)`, `validate_confirmation(:password)` (reads `params["password_confirmation"]`), `add_error(changeset, field, msg, keys)`, `unique_constraint` (errors surfaced only at `Repo.insert`). Form-level errors are just errors on a field the template chooses to render (elixirforum thread "Patterns for handling form-level errors in LiveView 1.0", 2025, notes that `used_input?` makes base/form-level errors awkward because there is no input for them).

**HTML5 attribute mapping** (`phoenix_ecto/lib/phoenix_ecto/html.ex` `input_validations/3`, L165-215):

```elixir
def input_validations(%{required: required, validations: validations} = changeset, _, field) do
  [required: field in required] ++
    for {key, validation} <- validations, key == field,
        attr <- validation_to_attrs(validation, field, changeset), do: attr
end
# {:length, min:/max:}  -> minlength:/maxlength:
# {:number, ...}        -> step: 1 (integer) | "any"; greater_than -> min: n+1 (integers only),
#                          greater_than_or_equal_to -> min:, less_than -> max: n-1, less_than_or_equal_to -> max:
```
Important nuance: **the generated `<.input>` never calls `input_validations`** (0 occurrences in `core_components.ex.eex` and the phx.gen.live template); the generators emit `required`/`step="any"` by hand. So this mapping exists in the library but the mainstream path does not exploit it.

**When validation runs.** Always on the server, on every `phx-change` (whole form, debounced per input) and on `phx-submit`. There is no client-side validation beyond native HTML attributes. The generated flow (`phoenix/priv/templates/phx.gen.live/form.ex.eex`):

```elixir
def mount(params, _session, socket) do
  {:ok, socket |> assign(:return_to, ...) |> apply_action(socket.assigns.live_action, params)}
end
defp apply_action(socket, :new, _params) do
  post = %Post{}
  socket |> assign(:page_title, "New Post") |> assign(:post, post)
         |> assign(:form, to_form(Blog.change_post(post)))          # action nil -> no errors shown
end
def handle_event("validate", %{"post" => post_params}, socket) do
  changeset = Blog.change_post(socket.assigns.post, post_params)
  {:noreply, assign(socket, form: to_form(changeset, action: :validate))}   # errors now visible (subject to used_input?)
end
def handle_event("save", %{"post" => post_params}, socket) do
  case Blog.create_post(post_params) do                             # Repo.insert -> {:error, cs} has action: :insert
    {:ok, post} -> {:noreply, socket |> put_flash(:info, "Post created successfully") |> push_navigate(to: ...)}
    {:error, %Ecto.Changeset{} = changeset} -> {:noreply, assign(socket, form: to_form(changeset))}
  end
end
```
**Why the action gate exists** (from `form/1` docs, "A note on :errors"): "Even if `changeset.errors` is non-empty, errors will not be displayed in a form if the changeset `:action` is `nil` or `:ignore`. This is useful for things like validation hints on form fields, e.g. an empty changeset for a new form. That changeset isn't valid, but we don't want to show errors until an actual user action has been performed." `Repo.insert/update/delete` set `:insert/:update/:delete`; `to_form(cs, action: :validate)` (phoenix_ecto ≥ 4.5.0 honours `to_form`'s `:action`; 4.6.4 "Do not override changeset actions") or `Ecto.Changeset.apply_action/2` set it manually. Nested forms inherit the parent's action, and `apply_action(child, nil)` strips child actions when the parent has none (`html.ex` L285-290).

## Form state: bound/unbound, touched/dirty/used, initial vs submitted, attempted values, reset

LiveView has **no client-side form state object** — state is (a) the `%Form{}` in assigns (server) and (b) a few private flags on DOM nodes (client). Concepts map as:

- *Unbound/bound*: a changeset with `params: %{}` and `action: nil` (mount) vs one built from params with an action. `form.data` is the original struct; `form.params` the raw strings; `form.source.changes` the typed diff (Ecto's "dirty" = `changes`; `Ecto.Changeset.get_change/get_field`).
- *Attempted values*: `input_value` precedence `changes → params → data` means an invalid submission re-renders what the user typed (`params`), a valid cast shows the typed value, and untouched fields show original data.
- *Used/touched* (1.x client): `DOM.putPrivate(input, PHX_HAS_FOCUSED, true)` is set in the input/change event path (`live_socket.ts` L1913-1916, after debounce — despite the name, merely focusing does not set it); `submitForm` sets `PHX_HAS_SUBMITTED` on the form and every element (`view.ts` L2736-2739). `serializeForm` then appends `_unused_<name>=` for every name whose inputs are all neither focused nor submitted, unless the name is the submitter, all its inputs are hidden, or the input/form carries `phx-no-unused-field` (added v1.2.0-rc.0, issue #3577, because of `user[addresses]` vs `user[addresses][]` mismatches marking selects unused). `prependFormDataKey` inserts the prefix on the *last* bracket segment, so `user[address][city]` becomes `user[address][_unused_city]`. Server side:

```elixir
def used_input?(%Phoenix.HTML.FormField{field: field, form: form}), do: used_param?(form.params, field)
defp used_param?(_params, "_unused_" <> _), do: false
defp used_param?(params, field) do
  field_str = "#{field}"; unused_field_str = "_unused_#{field}"
  case params do
    %{^field_str => _, ^unused_field_str => _} -> false
    %{^field_str => %{} = nested} when not is_struct(nested) -> Enum.any?(Map.keys(nested), &used_param?(nested, &1))
    %{^field_str => _val} -> true
    %{} -> false
  end
end
```
(`phoenix_component.ex` L1758-1780.) Consequences: a field absent from params is *unused*; a nested map is used if *any* leaf is used (so `inputs_for` parents count as used once one child input is touched — the "Checking used_input? on inputs_for" forum thread); the `not is_struct` guard is the fix for #3757 (a `DateTime` value matched `%{}`). Outside LiveView (plain HTTP) nothing is `_unused_`, so everything is used.

- *Used/touched* (0.20.x client — **what pyview ships**): no `_unused_` params. The client itself tracks the same `PHX_HAS_FOCUSED`/`PHX_HAS_SUBMITTED` privates and, after every DOM patch, adds the `phx-no-feedback` class to every element whose `phx-feedback-for="<input name>"` (or `phx-feedback-group`) matches an input that is neither focused nor submitted (`dom.js` v0.20.17 `maybeHideFeedback/shouldHideFeedback/feedbackSelector` L310-385; `feedbackSelector` also matches the name with a trailing `[]` stripped). CSS (`phx-no-feedback:hidden` Tailwind variant) hides the error. The server renders errors unconditionally. This is purely presentational: errors are in the DOM, just hidden.
- *Reset*: `<button type="reset">` clears the privates (`DOM.resetForm`), re-hides feedback (0.20) and then emits a `phx-change` with `"_target" => ["reset"]` (name of the reset button) so the server can rebuild the form.
- *Submit lifecycle*: inputs set `readonly`, submit buttons `disabled`, form gets `phx-submit-loading`; on ack, restored and last focused input re-focused (e2e `forms.spec.js` asserts exact attribute mutations incl. `data-phx-readonly`/`data-phx-disabled` bookkeeping so pre-existing readonly/disabled states are preserved).
- *Recovery*: `getFormsForRecovery` collects `form[phx-change]` elements that have an `id`, ≥1 element and `phx-auto-recover != "ignore"`, deep-cloning them (with morphdom copying privates so "touched" survives); after rejoin `pushFormRecovery` pushes the `phx-auto-recover` event or else the `phx-change` event, with `_target` = first non-hidden input's name, dispatching a `phx:form-recovery` CustomEvent; inputs with their own `phx-change` are excluded (`view.ts` L2490-2545, L2600-2640).

## Rendering: HTML generation, customization layers, escape hatches for hand-written HTML

Layers, from library to app:

1. **`<.form>`** — only the `<form>` tag, hidden `_method`/`_csrf_token` when `action` is set, and `render_slot(@inner_block, @form)`. Global attrs `autocomplete name rel enctype novalidate target` plus all `phx-*`.
2. **`<.inputs_for :let={f} field={@form[:children]}>`** — calls `impl.to_form(source, parent_form, field, opts)`, applies persistent ids, renders `<input type="hidden">` for each `finner.hidden` entry (`skip_hidden` / `skip_persistent_id` to opt out), yields each sub-form. Attrs: `id`, `as`, `default`, `prepend`, `append`, `options` (passed to the FormData impl).
3. **`<.input>`** — *generated into the app* by `mix phx.new` (`installer/templates/phx_web/components/core_components.ex.eex`). Signature: `attr :id, :name, :label, :value, :type (values: checkbox color date datetime-local email file month number password search select tel text textarea time url week hidden), :field (Phoenix.HTML.FormField), :errors, :checked, :prompt, :options, :multiple, :class, :error_class, :rest (global, include: accept autocomplete capture cols disabled form list max maxlength min minlength multiple pattern placeholder readonly required rows size step)`. The first clause unpacks the FormField:

```elixir
def input(%{field: %Phoenix.HTML.FormField{} = field} = assigns) do
  errors = if Phoenix.Component.used_input?(field), do: field.errors, else: []
  assigns
  |> assign(field: nil, id: assigns.id || field.id)
  |> assign(:errors, Enum.map(errors, &translate_error(&1)))
  |> assign_new(:name, fn -> if assigns.multiple, do: field.name <> "[]", else: field.name end)
  |> assign_new(:value, fn -> field.value end)
  |> input()
end
```
then dispatches on `type` (`"hidden"`, `"checkbox"`, `"select"`, `"textarea"`, default `<input type={@type}>`), each wrapping label + control + `<.error :for={msg <- @errors}>`. Because it is app code, customisation = edit the file. `phx.gen.html/live` picks the `type` from the Ecto field type (`phx.gen.html.ex inputs/1`: integer→number, float/decimal→number step="any", boolean→checkbox, text→textarea, date/time/datetime→date/time/datetime-local, enum→select with `Ecto.Enum.values/2`, else text).
4. **Escape hatch = raw HTML with FormField accessors.** Since `field.id/name/value/errors` are plain strings/lists, any hand-written tag works: `<input id={@form[:title].id} name={@form[:title].name} value={@form[:title].value}/>` (this is exactly how the e2e `FormDynamicInputsLive` is written). Custom widgets (date pickers, hidden-input-backed selects) integrate by dispatching `new Event("input", {bubbles: true})` on the hidden input; `phx-hook` on the form can `stopPropagation()` a submit to add client-side gating.

Change tracking: `<.form>`/`<.input>` are function components, so LiveView diffs per-attribute; `Phoenix.HTML.Form.input_changed?/3` is the hook change tracking uses to decide whether `@form[:field]` changed (value, errors, action, impl, id or name).

## Styling / theming

Nothing in the libraries carries CSS. Styling lives in the generated `core_components.ex` (Tailwind + daisyUI in phoenix 1.8/1.9 main: `class={@class || "w-full input"}`, `@errors != [] && (@error_class || "input-error")`, `fieldset mb-2`, `label`; Tailwind + heroicons in 1.7: `border-zinc-300 ... phx-no-feedback:border-zinc-300`). Each `<.input>` exposes `class`/`error_class` overrides and `rest` pass-through; anything beyond that means editing the component. Loading-state classes (`phx-submit-loading`, `phx-change-loading`, `phx-click-loading`) are applied by the client and are meant to be styled by the app (guide example: `.phx-submit-loading .while-submitting { display:block }`). In 0.20, `phx-no-feedback` is likewise a styling hook (Tailwind variant `addVariant("phx-no-feedback", [".phx-no-feedback&", ".phx-no-feedback &"])`).

## Nested, dynamic (add/remove/reorder) and conditional forms

**Static nesting** is automatic once the schema declares `embeds_one/embeds_many/has_one/has_many/belongs_to/many_to_many` and the changeset calls `cast_embed/cast_assoc`. `find_inputs_for_type!/2` raises if the field is not a relation ("Check the field exists and it is one of embeds_one, embeds_many, has_one, has_many, belongs_to or many_to_many"); unloaded assocs on persisted structs raise "Please preload your associations". For `cardinality: :one` the child form is built from `changes[field]`, else `data.field`, else `module.__struct__()` (so an empty child form always renders). For `:many`, when `form.params[field]` is present, children come from the changeset (params win); otherwise `prepend ++ children ++ append`. Children with `action: :replace` are skipped (`skip_replaced/1`) — the source of issue #2616 ("if you remove every association of a collection, any other change to the form will cause all of the associations to be restored", 2023) which the sort/drop design addresses via the always-present empty `*_drop[]` hidden input.

**Dynamic add/remove/reorder — the canonical recipe** (from `inputs_for/1` docs, LiveView ≥ 0.19.0 + Ecto ≥ 3.10):

```elixir
# schema + changeset
embeds_many :emails, EmailNotification, on_replace: :delete do   # on_replace: :delete is REQUIRED
  field :email, :string
  field :name, :string
end
def changeset(list, attrs) do
  list |> cast(attrs, [:title])
       |> cast_embed(:emails, with: &email_changeset/2, sort_param: :emails_sort, drop_param: :emails_drop)
end
```
```heex
<.inputs_for :let={ef} field={@form[:emails]}>
  <input type="hidden" name="mailing_list[emails_sort][]" value={ef.index} />
  <.input type="text" field={ef[:email]} placeholder="email" />
  <.input type="text" field={ef[:name]} placeholder="name" />
  <button type="button" name="mailing_list[emails_drop][]" value={ef.index} phx-click={JS.dispatch("change")}>
    <.icon name="hero-x-mark" class="w-6 h-6 relative top-2" />
  </button>
</.inputs_for>
<input type="hidden" name="mailing_list[emails_drop][]" />
<button type="button" name="mailing_list[emails_sort][]" value="new" phx-click={JS.dispatch("change")}>add more</button>
```
Mechanics: every existing row emits its index into `emails_sort[]` (so the server learns the current order); the remove button, when clicked, is the *submitter* and is serialised as `emails_drop[] = idx`; `JS.dispatch("change")` makes the click fire the form's `phx-change` (not a submit); the "add" button submits `emails_sort[] = "new"` and Ecto treats any unknown sort index as a new child (`cast_params(:many, ...)`: `Enum.map_reduce(sort -- drop, value, &Map.pop(&2, &1, %{}))` — a missing key pops `%{}`); the trailing empty hidden `emails_drop[]` guarantees the key is present even when zero rows remain, so "delete all" sticks. Remaining rows are re-indexed from 0. The `:with` function may have arity 3 to receive the final position (needed to persist ordering for real associations via a `position` field — for embeds order is implicit). **Checkbox variant** (`test/e2e/support/form_dynamic_inputs_live.ex`, also the fly.io/dockyard posts): replace the buttons with `<label><input type="checkbox" name="my_form[users_drop][]" value={ef.index}/> Remove</label>` and `<label><input type="checkbox" name="my_form[users_sort][]"/> add more</label>` — checking is itself a change event, no JS command required. The e2e example also shows the same recipe against a **plain map** form: `to_form(params, as: :my_form, id: "my-form", default: [])` with a hand-written `build_users(value, sort, drop)` that re-implements Ecto's `cast_params` logic in ~15 lines.

**Older recipe (pre-0.19)**: `:append`/`:prepend` on `inputs_for` plus `phx-click` handlers that `put_embed(changeset, :cities, existing ++ [%{}])` / `List.delete_at` (LostKobrakai gist) — requires storing the changeset in assigns and a round-trip per add/remove; superseded but `:append`/`:prepend` still exist ("only applies if the field value is a list and no parameters were sent").

**Reordering**: because `_persistent_id` is stored in each child's params and used for DOM ids, rows keep identity across sorts; drag-and-drop hooks set the `*_sort[]` hidden values then dispatch an `input` event. Numbering rows: `ef.index` (Arrowsmith "Numbering nested inputs").

**Conditional forms**: no dedicated API. Templates use `:if={@form[:kind].value == "company"}` (value is the raw param or typed change) and the changeset conditionally `cast`s/`validate_required`s. Wizards are the motivating case for `phx-auto-recover` (server holds the step state; recovery event rebuilds it). The docs' explicit guidance is to compute derived state (e.g. "remaining time" from nested `activities`) in `handle_event` from the changeset, never from `form[:field].value`, because that value "may either return a struct, a changeset, or raw parameters sent by the client".

## DX highlights — with real code (copied/adapted from primary sources; cite each example)

1. **Minimal own `<.input>` (form-bindings guide):**
```elixir
attr :field, Phoenix.HTML.FormField
attr :rest, :global, include: ~w(type)
def input(assigns) do
  ~H"""
  <input id={@field.id} name={@field.name} value={@field.value} {@rest} />
  """
end
```
Everything a widget needs is three strings on the FormField.

2. **Plain-map form with manual errors (`to_form/2` docs):**
```elixir
to_form(%{"search" => nil}, errors: [search: {"Can't be blank", []}])
# and in handle_event: {:noreply, assign(socket, form: to_form(user_params, as: :user))}
```

3. **Individual-input change routed to a component (form-bindings guide):**
```heex
<.form for={@form} id="my-form" phx-change="validate" phx-submit="save">
  <.input field={@form[:email]} phx-change="email_changed" phx-target={@myself} />
</.form>
```
```elixir
def handle_event("email_changed", %{"user" => %{"email" => email}}, socket), do: ...
```
Only that input is serialised (`pushInput` passes `onlyNames = [input.name]`, `view.ts` L2091).

4. **Debounce per input (bindings guide):**
```heex
<input type="text" name="user[email]" phx-debounce="blur"/>
<input type="text" name="user[username]" phx-debounce="2000"/>
<button type="submit" phx-disable-with="Saving...">Save</button>
```

5. **Hand-off to a controller after LiveView validation (form-bindings guide, `phx-trigger-action`):**
```heex
<.form :let={f} for={@changeset} action={~p"/users/reset_password"} phx-submit="save" phx-trigger-action={@trigger_submit}>
```
```elixir
{:ok, changeset} -> {:noreply, assign(socket, changeset: changeset, trigger_submit: true)}
```
On the next patch the client calls `liveSocket.unload()` and submits the form natively, re-injecting the stored submitter (`dom_patch.ts` L605-615).

6. **Reset handling (form-bindings guide):**
```elixir
def handle_event("changed", %{"_target" => ["reset"]} = params, socket), do: # rebuild form
def handle_event("changed", params, socket), do: # regular change
```

7. **Testing (`Phoenix.LiveViewTest`, phx.gen.live test template):**
```elixir
assert form_live |> form("#post-form", post: @invalid_attrs) |> render_change() =~ "can't be blank"
assert {:ok, index_live, _html} = form_live |> form("#post-form", post: @create_attrs) |> render_submit() |> follow_redirect(conn, ~p"/posts")
```
`form/3` "is meant to mimic what the user can actually do, so you cannot set hidden input values" — the test client validates that the fields exist in the rendered HTML.

8. **`used_input?` without any component (its docs):**
```heex
<input type="text" name={@form[:email].name} value={@form[:email].value} />
<div :if={used_input?(@form[:email])}><p :for={error <- @form[:email].errors}>{error}</p></div>
```

## Known pain points & criticisms (cite)

- **Feedback gating churn.** Issue #1135 (2020, LV 0.13): errors hidden after a partial submit until another change — the client-side `phx-no-feedback` approach was fragile. Issue #2968 (Dec 2023): composite inputs (money, datetime parts) can't express "one of my N inputs was touched" with a single `phx-feedback-for` name → `phx-feedback-group` shipped in 0.20.4 (2024-02-01) and was *deprecated one week later* in 0.20.5 ("the goal is to move feedback handling into Elixir and out of the DOM"), culminating in 1.0.0's removal of `phx-feedback-for` and the `_unused_` design. Post-1.0: #3235 (phx.gen.auth current-password error invisible because the field was never `cast` — migration notes require adding a virtual field), #3757 (`DateTime` values matched the nested-map clause), #3577 (`user[addresses]` hidden input vs `user[addresses][]` select marked unused → `phx-no-unused-field` in 1.2.0-rc.0), elixirforum "Patterns for handling form-level errors in LiveView 1.0" (form-level errors have no input to be "used"), "Checking used_input?/1 on inputs_for/1" (parent-level gating for nested lists is unclear).
- **`_unused_` protocol quirks**: the sibling key is injected into the *params namespace* (`user[address][_unused_city]`), so any code that iterates params (e.g. dynamic keys, external APIs, schemaless `cast` with `Map.keys`) sees noise; `phx-no-unused-field` exists precisely because of this (#3577).
- **`to_form(map)` is naming-only**: `input_validations` returns `[]`, errors must be supplied by hand, no coercion — every "schemaless" tutorial (AppSignal 2021, dev.to "Using Ecto without DB", Medium "Schemaless validation") ends up recommending `Ecto.Changeset.cast({data, types}, params, ...)`, i.e. you need Ecto anyway.
- **Nested-form ceremony**: the sort/drop recipe needs five coordinated pieces (hidden sort input per row, drop button per row, empty drop hidden input, add button, `on_replace: :delete` + `sort_param`/`drop_param` in the changeset). Getting one wrong fails silently (rows reappear — #2616 — or "delete all" doesn't stick). The Arrowsmith/Dockyard/fly.io posts exist because "finding good examples online can be difficult" (search summary). Streams are sometimes used instead for very large dynamic forms (fly.io "Dynamic forms with LiveView Streams").
- **Untyped `field.value`**: docs devote a long warning to it; computing anything from nested values in templates is officially discouraged.
- **`:let={f}` vs `@form` confusion**: two ways to reach the form; the docs discourage `:let` for change-tracking reasons and because "Ecto changesets are meant to be single use", but older tutorials use it, and `<.simple_form :let={f}>` (1.7 generator) still did.
- **Password/`input_validations` docs drift**: the guide's password claim no longer matches phoenix_html 4.x; `input_validations` is implemented but unused by generated code — evidence that the layered design has seams users fall through.
- **Generated, not shipped, components**: `<.input>` styling lives in app code — great for customisation, but every app re-derives fixes (the 1.0 migration was a hand-applied diff to core_components), and there is no "theme" concept.

## Lessons for pyview — steal / adapt / avoid (opinionated and concrete; tie to the brief; where useful sketch what the pyview-equivalent could look like in Python)

**Steal**

1. **The `FormField` triple as the template contract.** Make `form["email"]` / `form.email` return an object with `id`, `name`, `value`, `errors`, `field`, `form` — computed, never stored — so hand-written HTML (`value="{{ form.email.value }}"`) and generated widgets share one source of truth. This directly serves "users may want to provide their own HTML". Sketch:
```python
@dataclass(frozen=True)
class FormField:
    id: str; name: str; value: Any; errors: list[FieldError]; field: str; form: "Form"
    @property
    def used(self) -> bool: ...
class Form:
    def __getitem__(self, key: str) -> FormField:  # "addresses.0.city" or ["addresses", 0, "city"]
        return FormField(id=f"{self.id}_{key}", name=f"{self.name}[{key}]", value=self.value_for(key), errors=self.errors_for(key), field=key, form=self)
```
2. **Value precedence `changes → params → data`** with `params` kept as the raw strings. It gives "attempted values" for free and lets the widget layer stringify (`normalize_value`) instead of the model. In Python: keep `raw: dict` (decoded from the wire) and `model: Optional[BaseModel]` or per-field validated values from `pydantic`'s `ValidationError` (which reports `loc`, `type`, `msg`, `input`, `ctx` — a near-perfect analogue of Ecto's `{msg, [validation: ..., count: ...]}`).
3. **The action gate + used-input gate as two orthogonal booleans.** `Form(action=None)` on mount → no errors; `action="validate"` on change; `action="save"` on submit. Show an error iff `action is not None and (field.used or action == "save")`. This is exactly the phx.gen.live behaviour and avoids pyview's current "errors only for keys already in changes" hack.
4. **Name grammar + decoder.** Adopt `user[addresses][0][city]` / `user[tags][]` verbatim (the JS client, `_target`, `phx-feedback-for` matching and `_unused_` prefixing all assume it) and write a `decode_nested(parse_qs(...))` that mirrors `Plug.Conn.Query`: brackets → dicts, `[]` → lists, numeric keys stay *strings* until the pydantic layer sorts them into a list. Also decode `_target` into a path list as `channel.ex` does.
5. **Sort/drop params as the dynamic-list protocol**, but generate them. pyview can emit, for any `list[Model]` field, the hidden `*_sort[]` per row, the empty `*_drop[]`, and `add`/`remove` buttons with `phx-click={JS.dispatch("change")}` from one helper (`{{ form.addresses | inputs_for }}` / `form.inputs_for("addresses")`), and apply Ecto's `cast_params` algorithm (`sorted = [pop(idx, default={}) for idx in sort - drop] + remaining sorted by int key`) before handing the list to pydantic. Nobody has to know the protocol.
6. **`_persistent_id`** for row identity/DOM ids, so reorders don't re-id inputs and focus survives.
7. **Client conventions as documented features**: `phx-debounce="blur"`, `phx-disable-with`, `phx-submit-loading`, reset via `_target == ["reset"]`, `phx-auto-recover` for wizards, `phx-trigger-action` for "validate live, then POST to a real endpoint" — all already work with pyview's client; document them alongside the form API.
8. **Errors as (code, template, ctx), rendered late.** Keep pydantic's `type` (`string_too_short`), `msg`, `ctx` (`{"min_length": 3}`) and translate/interpolate in the widget (`translate_error` hook), enabling i18n and custom copy without touching validation.

**Adapt**

- **Pydantic replaces Ecto, but keep the changeset *shape*.** A `ChangeSet[Model]` should expose `data` (original instance or None), `params` (raw nested dict of strings), `changes` (validated, typed, per-field — obtainable by validating field-by-field with `TypeAdapter`/`model_validate` on partial input or `validate_assignment`), `errors: dict[path, list[FieldError]]`, `action`, `valid`. Nested errors keyed by `loc` tuples (`("addresses", 0, "city")`) rather than "first loc element" as today.
- **`input_validations` → derive HTML attrs from pydantic `FieldInfo`/JSON schema** (`min_length`→`minlength`, `ge/gt/le/lt`→`min/max`, `Literal`/`Enum`→`<select>`, `bool`→checkbox-with-hidden-false, `date/datetime`→date/datetime-local, `Optional`/default → not required). Phoenix built this mapping and then didn't wire it into the generated component; pyview can make it the default and let `required` etc. be overridden per widget.
- **Used-input tracking must work with the 0.20.17 client.** Two options: (a) stay on 0.20 and emit `phx-feedback-for={{ field.name }}` on the error container (client hides untouched errors with `phx-no-feedback`); errors are still in the DOM, which is fine for LiveView but leaks messages to screen readers unless hidden properly; or (b) upgrade the bundled client to 1.x and implement `used_input?` from `_unused_*` keys. Option (b) is the direction Phoenix chose ("move feedback handling into Elixir and out of the DOM") and is strictly more powerful (nested/any-leaf semantics, no CSS coupling). Until then, a server-side fallback is to accumulate the `_target` paths seen on `phx-change` plus "all fields used on submit" — equivalent to what the client does with `PHX_HAS_FOCUSED`/`PHX_HAS_SUBMITTED`.
- **Generated vs shipped widgets.** Phoenix generates `core_components.ex` into the app; pyview should ship a default widget set (Ibis filters *and* t-string helpers) but make it a plain Python module users can copy/override per type (`widgets = {"checkbox": my_checkbox}`), with `class`/`error_class` overrides like the generated `<.input>`. Keep CSS out of the library except an optional Tailwind/daisyUI default.
- **Conditional nesting**: the brief's key need. Phoenix has no API for it; pyview can do better by letting `Union`/discriminated-union pydantic fields drive which sub-form is rendered (`form.kind.value` chooses the variant model) and by re-validating the whole model on each change so the server decides visibility. Keep the "compute derived state in `handle_event`, not from `field.value`" advice.

**Avoid**

- Don't make `field.value` polymorphic (struct | changeset | raw params) as Phoenix does; always expose *display strings* on the FormField and typed values on the changeset.
- Don't depend on the client-side `phx-no-feedback` CSS mechanism long-term (deprecated/removed upstream; composite-input and `[]` edge cases).
- Don't require users to hand-write the five-piece sort/drop markup; generate it.
- Don't emit `_unused_*` into the user-visible params dict if you adopt the 1.x client — strip them into a `used: set[path]` before handing params to pydantic (Phoenix leaves them in and needed `phx-no-unused-field` as a bail-out).
- Don't tie CSRF to the form (LiveView doesn't: the socket join carries it); only generate `_csrf_token` for `action=`/`phx-trigger-action` forms.
- Don't offer two ways to reach the form (`:let` vs assign) — one `form` object in context.

## Sources (every URL / repo path you actually read)

Local clones (shared cache `.../scratchpad/repos/`):
- `phoenix_live_view` (main, 1.2.11, commit 7f06d34, 2026-09-11): `guides/client/form-bindings.md`; `guides/client/bindings.md` (L174-240 debounce/throttle, L318-360 phx-update/phx-patch-focused); `lib/phoenix_component.ex` (L1540-1790 to_form/used_input?, L2300-2900 form/1 + inputs_for/1); `lib/phoenix_live_component.ex` L270-330; `lib/phoenix_live_view/js.ex` (dispatch/push); `lib/phoenix_live_view/channel.ex` L910-942; `lib/phoenix_live_view/test/live_view_test.ex` (form/3, render_change/submit); `CHANGELOG.md` (phx-no-unused-field, v1.2.0-rc.0); `assets/js/phoenix_live_view/view.ts` (serializeForm L1889-1994, pushInput L2064-2115, pushFormSubmit L2251-2330, pushFormRecovery L2490-2545, getFormsForRecovery L2600-2640, submitForm L2736-2742); `dom.ts` L495-510; `dom_patch.ts` L164-180, L465-483, L594-615; `live_socket.ts` L1880-1918; `constants.ts`; `assets/test/view_test.ts` L480-592; `test/phoenix_component/components_test.exs` L555-694; `test/e2e/support/form_dynamic_inputs_live.ex`; `test/e2e/tests/forms.spec.js` L1-80.
- `phoenix_html` (4.3.0, commit 7cbed82): `lib/phoenix_html/form.ex` (L1-400), `lib/phoenix_html/form_data.ex`, `lib/phoenix_html/form_field.ex`, `CHANGELOG.md` (v4.0.0, v3.3.x).
- `phoenix_ecto` (4.7.0, commit d0b0206): `lib/phoenix_ecto/html.ex` (full), `CHANGELOG.md` (v4.5.0, v4.6.4, v4.7.0).
- `phoenix` (1.9.0-dev, commit 1e6183e): `installer/templates/phx_web/components/core_components.ex.eex` (L160-345, L470-520), `priv/templates/phx.gen.live/form.ex.eex`, `priv/templates/phx.gen.live/live_test.exs.eex`, `lib/mix/tasks/phx.gen.html.ex` L260-314.
- `ecto` (3.15.0-dev, commit e1d536a): `lib/ecto/changeset.ex` L1100-1260 (cast_assoc docs), L1380-1470 (cast_relation/cast_params), L4236-4300 (traverse_errors), error message sites L1487, L2620, L2935, L2964, L3141.

Raw GitHub files fetched:
- https://raw.githubusercontent.com/phoenixframework/phoenix/v1.7.10/installer/templates/phx_web/components/core_components.ex (phx-feedback-for era `<.input>`, `<.error>`, `<.simple_form>`)
- https://raw.githubusercontent.com/phoenixframework/phoenix/v1.7.14/installer/templates/phx_web/components/core_components.ex (already `used_input?`)
- https://raw.githubusercontent.com/phoenixframework/phoenix_live_view/v1.0.0/CHANGELOG.md (1.0 migration notes; 0.19.0/0.20.x entries)
- https://raw.githubusercontent.com/phoenixframework/phoenix_live_view/v0.20.17/assets/js/phoenix_live_view/dom.js and view.js (pyview's client: feedback mechanism, no `_unused_`)
- https://raw.githubusercontent.com/elixir-plug/plug/main/lib/plug/conn/query.ex (via WebFetch summary)

GitHub issues/gists (WebFetch):
- https://github.com/phoenixframework/phoenix_live_view/issues/1135
- https://github.com/phoenixframework/phoenix_live_view/issues/2616
- https://github.com/phoenixframework/phoenix_live_view/issues/2968
- https://github.com/phoenixframework/phoenix_live_view/issues/3577
- https://github.com/phoenixframework/phoenix_live_view/issues/3757
- https://gist.github.com/LostKobrakai/ce5385bd118189a24d60893188612de9

WebSearch result summaries (pages themselves blocked): dockyard.com/blog/2024/03/12/dynamically-add-and-remove-embedded-item-inputs-without-javascript; arrowsmithlabs.com/blog/phoenix-liveview-nested-forms-advanced-tricks and /numbering-nested-inputs-in-phoenix-liveview; fly.io/phoenix-files/cast-assoc-sort-and-delete-options/ and /dynamic-forms-with-streams/; elixirforum.com threads 67623 (used_input? on inputs_for), 67271 (form-level errors in 1.0), 57717, 60815, 67092; johnelmlabs.com/posts/top-3-liveview-form-mistakes; elixirstreams.com/tips/liveview-used-input; sergiovp.dev "forms without changeset"; blog.appsignal.com 2021 real-time form validation; phoenixframework.org LiveView 0.19 release post; github.com/phoenixframework/phoenix_live_view/issues/3235.
