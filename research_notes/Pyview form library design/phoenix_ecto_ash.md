# Forms in the Elixir/Phoenix ecosystem: Phoenix LiveView forms, Ecto Changesets, AshPhoenix.Form (state as of Sept 2026)

Research-method note: hexdocs.pm, elixirforum.com, fly.io, dashbit.co, dockyard.com, arrowsmithlabs.com and phoenixframework.org were blocked by this session's egress proxy. Nearly everything below was therefore read from **primary source code and docs in the GitHub repos** (the same text hexdocs renders from `@moduledoc`/`@doc` and `guides/`), plus GitHub issue bodies. Versions read: Ecto `master` (v3.14.x line), phoenix_live_view `main`/`v1.2` (v1.2.12, 2026-09-16), phoenix_html `main` (4.x), phoenix_ecto `main`, Phoenix `v1.8` branch, ash_phoenix `main`, polymorphic_embed `master`. GitHub issue *comment threads* could not be loaded, so for issues only the reporter's description (and any fix in a changelog) is cited.

Useful context for the synthesizer: pyview already ships a minimal `ChangeSet` (`pyview/changesets/changesets.py`, 67 lines): it wraps a pydantic model class, keeps a flat `changes` dict, applies only the field named by `_target[0]` on each change event, stores errors as `{field: msg}` strings, and only keeps errors for keys already in `changes`. There's no `data` vs `changes` split, no nesting, no action, no error metadata. The Ecto/Phoenix design below is the "full" version of that idea.

---

## 1. Ecto.Changeset: data model, lifecycle, and why the abstraction works

### Takeaway
A changeset is an **immutable value** holding `data` (the original struct), `params` (raw external input), `changes` (only the cast fields that differ from `data`), `errors` (a keyword list of `{field, {msg, opts}}`), `valid?`, and `action`. You build it with a pipeline: `cast` (filter + type-coerce untrusted input) → `validate_*` (pure functions that append errors) → `apply_action`/`Repo.insert` (commit only if valid). Because errors are data with metadata, and because `action` records "has a real operation been attempted?", the same value can drive validation, i18n, HTML5 attributes, and when to show errors. The costs: it's tied to Ecto types and struct schemas, you have to understand `data`/`changes`/`params` precedence, and it's easy to misuse in templates.

### Cited Findings

**Purpose and the four jobs.** The moduledoc frames changesets around **filtering** ("you must explicitly list which data you accept … you most likely don't want to allow a user to set its own `is_admin` field"), **type casting** ("a web form sends most of its data as strings"), **validations**, and **constraints** (database-backed checks such as uniqueness) — [Ecto.Changeset source/moduledoc](https://github.com/elixir-ecto/ecto/blob/master/lib/ecto/changeset.ex)

**External vs internal data (`cast` vs `change`).** "`cast/4` is used to receive external parameters from a form, API or command line, and convert them to the types defined in your `Ecto.Schema`. `change/2` is used to modify data directly from your application, assuming the data given is valid." External data "is typically provided as maps with string keys"; internal data uses atom keys/structs: "if you have structs or maps with atom keys, it means the data has been parsed/validated." `change/2` stores values "with no validation whatsoever" — [Ecto.Changeset](https://github.com/elixir-ecto/ecto/blob/master/lib/ecto/changeset.ex)

**Struct fields (public).** `valid?`, `data` ("The changeset source data, for example, a struct"), `params` ("The parameters as given on changeset creation"), `changes` ("The `changes` from parameters that were approved in casting"), `errors`, `required`, `action`, `types`, `empty_values`, `repo`, `repo_opts`. Private: `validations`, `constraints`, `filters`, `prepare`. Type spec: `@type error :: {String.t(), Keyword.t()}` and `@type action :: nil | :insert | :update | :delete | :replace | :ignore | atom` — [Ecto.Changeset](https://github.com/elixir-ecto/ecto/blob/master/lib/ecto/changeset.ex)

**`cast/4` semantics.** Only `permitted` keys are kept; "If the cast value matches the current value for the field, it will not be included in `:changes` unless the `force_changes: true` option is provided. All parameters that are not explicitly permitted are ignored." Mixed string/atom keys aren't allowed. Values are trimmed, then compared with `empty_values` (default `[""]`); empty values become the field default (nil for schemaless). Options include `:empty_values`, `:trim_values` (added in 3.14), `:force_changes`, `:message` (a `fn field, meta -> msg end` for custom cast errors). Casting into an existing changeset merges params **shallowly** ("Parameters are merged (**not deep-merged**)") — [Ecto.Changeset](https://github.com/elixir-ecto/ecto/blob/master/lib/ecto/changeset.ex); `:trim_values`/`Ecto.Type.trim/2` added in v3.14.0 (2026-05-19) — [Ecto CHANGELOG](https://github.com/elixir-ecto/ecto/blob/master/CHANGELOG.md)

**The canonical pipeline:**
```elixir
def changeset(user, params \\ %{}) do
  user
  |> cast(params, [:name, :email, :age])
  |> validate_required([:name, :email])
  |> validate_format(:email, ~r/@/)
  |> validate_inclusion(:age, 18..100)
  |> unique_constraint(:email)
end

changeset = User.changeset(%User{}, %{age: 0, email: "mary@example.com"})
{:error, changeset} = Repo.insert(changeset)
changeset.errors #=> [age: {"is invalid", []}, name: {"can't be blank", []}]
```
Validations run immediately when called; constraints run only at the DB, and "Constraints won't even be checked in case validations failed" — [Ecto.Changeset](https://github.com/elixir-ecto/ecto/blob/master/lib/ecto/changeset.ex)

**Errors are data, with interpolation metadata.** `add_error(changeset, :tags, "tag '%{val}' is too short", val: "x")` yields `[tags: {"tag '%{val}' is too short", [val: "x"]}]` and sets `valid?: false`. Built-in validators attach metadata, e.g. `{"should be at least %{count} characters", [count: 3, validation: :length, min: 3]}` and `{"can't be blank", [validation: :required]}`. `traverse_errors/2` walks nested assocs/embeds and returns nested maps, e.g. `%{title: ["should be at least 3 characters"]}` — [Ecto.Changeset](https://github.com/elixir-ecto/ecto/blob/master/lib/ecto/changeset.ex)

**The message stays untranslated until render time.** Generated apps translate `{msg, opts}` with Gettext, using `opts[:count]` for plurals:
```elixir
def translate_error({msg, opts}) do
  if count = opts[:count] do
    Gettext.dngettext(MyAppWeb.Gettext, "errors", msg, msg, count, opts)
  else
    Gettext.dgettext(MyAppWeb.Gettext, "errors", msg, opts)
  end
end
# without gettext:
#   Enum.reduce(opts, msg, fn {key, value}, acc ->
#     String.replace(acc, "%{#{key}}", fn _ -> to_string(value) end) end)
```
— [Phoenix 1.8 core_components template](https://github.com/phoenixframework/phoenix/blob/v1.8/installer/templates/phx_web/components/core_components.ex.eex)

**`apply_changes` vs `apply_action`.** `apply_changes/1` merges changes into data "regardless if the changeset is valid or not". `apply_action/2` is the "commit": 
```elixir
def apply_action(%Changeset{} = changeset, action) when is_atom(action) do
  if changeset.valid? do
    {:ok, apply_changes(changeset)}
  else
    {:error, %{changeset | action: action}}
  end
end
```
— [Ecto.Changeset](https://github.com/elixir-ecto/ecto/blob/master/lib/ecto/changeset.ex)

**The `:action` field and why errors hide until it's set.** Ecto: "Changesets have an action field which is usually set by `Ecto.Repo` … Frameworks such as Phoenix use the action value to define how HTML forms should act." — [Ecto.Changeset](https://github.com/elixir-ecto/ecto/blob/master/lib/ecto/changeset.ex). Phoenix: "Even if `changeset.errors` is non-empty, errors will not be displayed in a form if the changeset `:action` is `nil` or `:ignore`. This is useful for things like validation hints on form fields, e.g. an empty changeset for a new form. That changeset isn't valid, but we don't want to show errors until an actual user action has been performed. … Since the action can be arbitrary, you can set it to `:validate` or anything else to avoid giving the impression that a database operation has actually been attempted." — [Phoenix.Component.form/1 docs](https://github.com/phoenixframework/phoenix_live_view/blob/main/lib/phoenix_component.ex). This is enforced in the Ecto `FormData` impl:
```elixir
defp form_for_errors(_changeset, nil = _action), do: []
defp form_for_errors(_changeset, :ignore = _action), do: []
defp form_for_errors(%Ecto.Changeset{errors: errors}, _action), do: errors
```
— [phoenix_ecto html.ex](https://github.com/phoenixframework/phoenix_ecto/blob/main/lib/phoenix_ecto/html.ex)

**Schemaless changesets (`{data, types}`).** Changesets work on plain structs or maps given a type map:
```elixir
data  = %{}
types = %{name: :string, email: :string, age: :integer,
          role: Ecto.ParameterizedType.init(Ecto.Enum, values: [:reader, :editor, :admin])}
changeset =
  {data, types}
  |> Ecto.Changeset.cast(params, Map.keys(types))
  |> Ecto.Changeset.validate_required(...)
```
"Schemaless changesets make Ecto extremely useful to cast, validate and prune data even if it is not meant to be persisted to the database." — [Ecto.Changeset](https://github.com/elixir-ecto/ecto/blob/master/lib/ecto/changeset.ex)

**Form-specific schemas via `embedded_schema`.** The official guide recommends splitting "Database <-> Ecto schema <-> Forms / API" when UI shape ≠ storage shape: define a `Registration` `embedded_schema` with `first_name/last_name/email`, cast/validate it, then `apply_changes` and map it to `Account`/`Profile` rows. Adding virtual UI-only fields to the DB schema instead "is polluting our Profile schema with UI requirements" — [Ecto guide: Data mapping and validation](https://github.com/elixir-ecto/ecto/blob/master/guides/howtos/Data%20mapping%20and%20validation.md)

**Introspection helpers added for forms.** Ecto 3.10.0 (2023-04-10): "functions like `Ecto.Changeset.changed?/2` and `field_missing?/2` will help make your code more expressive. Improvements to association and embed handling will also make it easier to manage more complex forms, especially those embedded within Phoenix.LiveView applications"; added `get_assoc`/`get_embed`, `field_missing?/2`, and `:sort_param`/`:drop_param` — [Ecto CHANGELOG](https://github.com/elixir-ecto/ecto/blob/master/CHANGELOG.md). `get_field/3` reads changes first, then data; `get_change/3` reads only changes; `fetch_field/2` reports whether the value came from `:changes` or `:data` — [Ecto.Changeset](https://github.com/elixir-ecto/ecto/blob/master/lib/ecto/changeset.ex)

**Validations become HTML5 attributes.** The Ecto FormData impl derives `required`, `maxlength`/`minlength` (from `validate_length`), and `min`/`max`/`step` (from `validate_number`) from `changeset.required`/`changeset.validations` via `input_validations/3` — [phoenix_ecto html.ex](https://github.com/phoenixframework/phoenix_ecto/blob/main/lib/phoenix_ecto/html.ex)

**"Changesets are single use."** Phoenix discourages keeping a changeset in assigns: "Ecto changesets are meant to be single use. By never storing the changeset in the assign, you will be less tempted to use it across operations." The recommended LiveView flow rebuilds a fresh changeset from `(original_data, all_params)` on every `phx-change`:
```elixir
def handle_event("validate", %{"user" => params}, socket) do
  form = %User{} |> Accounts.change_user(params) |> to_form(action: :validate)
  {:noreply, assign(socket, form: form)}
end
```
— [Phoenix.Component.form/1 docs](https://github.com/phoenixframework/phoenix_live_view/blob/main/lib/phoenix_component.ex); [form-bindings guide](https://github.com/phoenixframework/phoenix_live_view/blob/main/guides/client/form-bindings.md)

### Inferences
- **Why it "resonates":** (1) *separation of phases*: casting/filtering (trust boundary) is separate from validation (domain rules) and from applying (side effects), and each phase is an ordinary function you can compose, reorder, or reuse (`registration_changeset` vs `email_changeset`). (2) *data vs changes*: keeping `data` intact while `changes` holds only the diff lets you do "dirty" checks, partial updates (`UPDATE` only changed columns), `changed?/2`, and "reset", and it gives a clear precedence rule for rendering (changes → raw params → data). (3) *errors as data*: `{msg, opts}` with `validation:` metadata means one error list can feed i18n, API JSON (`traverse_errors`), and UI, and you can add errors from anywhere (DB constraints, external services). (4) *action-gated display*: a single field (`action`) cleanly separates "invalid" from "should I show that it's invalid?", which avoids the classic "form is covered in red before the user types" problem. (5) *immutability*: every event produces a new value, which fits LiveView's re-render model perfectly.
- **Downsides for a port to note:** meaning is spread across three maps (`data`, `params`, `changes`) and the rendered `value` may be a typed value, a raw string, a struct, or a nested changeset (Phoenix itself warns about this; see §9). `cast` permits via an explicit list that duplicates schema fields. Ecto types (not arbitrary validators) drive casting. Error-display timing needs two mechanisms (`action` *and* `used_input?`). Rebuilding from scratch on each event is simple but means stateful UI (like "which rows exist") has to live in params (hence sort/drop params).
- **Python mapping (proposal):** pydantic already does cast + type validation in one step; a pyview `Changeset[T]` could keep Ecto's shape: `data: T | None`, `params: dict[str, Any]` (raw, string-keyed, nested), `changes: dict` (typed diff), `errors: list[tuple[path, str, dict]]` (message template + opts such as `{"validation": "min_length", "min": 3}`, mapped from pydantic's `err["type"]`, `err["ctx"]`), `action: str | None`, `valid: bool`, with `cast(data, params, permitted)` → `validate_*` chain → `apply_action("insert")` returning `Ok(model) | Err(changeset)`. Pydantic's `ValidationError.errors()` already provides a `loc` path tuple plus `type`/`ctx`, which is the same idea as Ecto's `{msg, opts}`.

### Gaps
- Couldn't read hexdocs-rendered pages or Dashbit's "Working with Ecto associations and embeds" post (blocked), so no José Valim commentary on design intent beyond the moduledocs/guides.

---

## 2. Nested and dynamic collections in Ecto: `cast_assoc`/`cast_embed`, `with:`, `on_replace`, `sort_param`/`drop_param`

### Takeaway
Nested forms in Ecto are **nested changesets**: `cast_embed/cast_assoc` read `params[field]` (a list, or a map keyed by index), match entries to existing children by primary key, and run a child changeset function for each. Each child changeset gets its own `action` (`:insert`/`:update`/`:replace`/`:delete`) and is stored under the parent's `changes`. Since Ecto 3.10 (2023), `sort_param`/`drop_param` let the *form params themselves* encode reordering, insertion ("unknown index = new row") and deletion. So add/remove/reorder needs no server event handlers. It does require `on_replace: :delete` (or `:update` for singular).

### Cited Findings

**Matching algorithm.** For each param entry: no `"id"` (or `id: nil`) → new struct via the changeset fn → insert; id present but not among preloaded children → insert; id matches a child → update with existing struct; a preloaded child whose id isn't given → the `:on_replace` behaviour is invoked. Duplicate ids produce an error. "Every time the `MyApp.Address.changeset/2` function is invoked, it must return a changeset. This changeset will always be included under `changes` of the parent changeset, even if there are no changes. This is done for reflection purposes." The association must be preloaded (for updates) — [Ecto.Changeset.cast_assoc/3](https://github.com/elixir-ecto/ecto/blob/master/lib/ecto/changeset.ex)

**`on_replace` options.** `:raise` (default), `:mark_as_invalid`, `:nilify` (assocs; sets child action `:replace`), `:update` (only `has_one`/`belongs_to`/`embeds_one`), `:delete` (sets child action `:replace`; "must be used carefully … allow users to delete any associated data by simply setting it to nil or an empty list"), `:delete_if_exists`. The docs suggest a virtual `delete` boolean as a safer explicit-delete pattern:
```elixir
schema "comments" do
  field :body, :string
  field :delete, :boolean, virtual: true
end
def changeset(comment, %{"delete" => "true"}) do
  %{Ecto.Changeset.change(comment, delete: true) | action: :delete}
end
def changeset(comment, params), do: cast(comment, params, [:body])
```
— [Ecto.Changeset moduledoc](https://github.com/elixir-ecto/ecto/blob/master/lib/ecto/changeset.ex)

**Custom child actions.** A child changeset can set `action: :ignore` to drop blank rows ("if one of the associations has only empty fields, you want to ignore the entry altogether instead of showing an error"):
```elixir
|> case do
  %{valid?: false, changes: changes} = changeset when changes == %{} ->
    %{changeset | action: :ignore}
  changeset -> changeset
end
```
— [Ecto.Changeset.cast_assoc/3](https://github.com/elixir-ecto/ecto/blob/master/lib/ecto/changeset.ex)

**Params as index-keyed maps + `sort_param`/`drop_param`:**
```elixir
cast_embed(changeset, :addresses,
  sort_param: :addresses_sort,
  drop_param: :addresses_drop)

%{"name" => "john doe", "addresses" => %{...}, "addresses_drop" => [0]}   # drop index 0
%{"name" => "john doe", "addresses" => %{...}, "addresses_sort" => [1, 0]} # reorder
```
"Note that any index not present in `"addresses_sort"` will come _before_ any of the sorted indexes. If an index is not found, an empty entry is added in its place." After a drop, "the remaining elements are re-indexed sequentially starting from 0". "These parameters can be powerful in certain UIs as it allows you to decouple the sorting and replacement of the data from its representation." — [Ecto.Changeset.cast_assoc/3](https://github.com/elixir-ecto/ecto/blob/master/lib/ecto/changeset.ex)

**Positions for associations (arity-3 `with:`).** Embeds are rewritten in order, but DB associations need an explicit position column:
```elixir
defp child_changeset(child, _changes, position) do
  child |> change(position: position)
end
changeset |> cast_assoc(:children, sort_param: ..., with: &child_changeset/3)
```
The third argument is "the position of the associated element in the list, or `nil`, if the association is being replaced". `sort_param`/`drop_param` raise for `belongs_to`/`has_one` — [Ecto.Changeset](https://github.com/elixir-ecto/ecto/blob/master/lib/ecto/changeset.ex). Ecto v3.14.0 (2026-05-19) added `Ecto.Changeset.reorder_assoc/2` — [Ecto CHANGELOG](https://github.com/elixir-ecto/ecto/blob/master/CHANGELOG.md)

**Other `cast_assoc` options:** `:required`, `:required_message`, `:invalid_message`, `:force_update_on_change`, `:with` (fn or `{m, f, args}`), `:drop_param`, `:sort_param` — [Ecto.Changeset](https://github.com/elixir-ecto/ecto/blob/master/lib/ecto/changeset.ex)

**Real-world schema (Chris McCord's todo_trek demo):**
```elixir
embeds_many :notifications, EmailNotification, on_replace: :delete do
  field :email, :string
  field :name, :string
end

def changeset(list, attrs) do
  list
  |> cast(attrs, [:title])
  |> validate_required([:title])
  |> cast_embed(:notifications,
    with: &email_changeset/2,
    sort_param: :notifications_order,
    drop_param: :notifications_delete)
end
```
— [todo_trek list.ex](https://github.com/chrismccord/todo_trek/blob/main/lib/todo_trek/todos/list.ex)

**The pre-3.10 pattern (still seen in the wild): server events that mutate the changeset.** Deprecated in practice, not formally deprecated:
```elixir
def handle_event("add-city", _, socket) do
  socket = update(socket, :changeset, fn changeset ->
    existing = Ecto.Changeset.get_field(changeset, :cities, [])
    Ecto.Changeset.put_embed(changeset, :cities, existing ++ [%{}])
  end)
  {:noreply, socket}
end

def handle_event("delete-city", %{"index" => index}, socket) do
  index = String.to_integer(index)
  socket = update(socket, :changeset, fn changeset ->
    existing = Ecto.Changeset.get_field(changeset, :cities, [])
    Ecto.Changeset.put_embed(changeset, :cities, List.delete_at(existing, index))
  end)
  {:noreply, socket}
end
```
plus a workaround for "empty list can't be expressed in form encoding" (`if changeset.params["cities"] == "[]" …`) — [LostKobrakai gist "Phoenix LiveView form with nested embeds and add/delete buttons"](https://gist.github.com/LostKobrakai/ce5385bd118189a24d60893188612de9)

### Inferences
- The key design idea worth porting: **make collection edits part of the submitted params, not server-side state**. The form stays a pure function of `(data, params)`, it survives reconnects and form recovery (the client resends everything), and the server needs no `add_row`/`remove_row` handlers. The index map (`addresses[0]…`, `addresses[1]…`) plus `*_sort[]`/`*_drop[]` lists is a tiny protocol a Python cast layer could implement generically for `list[SubModel]` fields.
- The event-based pattern has a subtle bug class: `put_embed` changes the changeset but the next `phx-change` rebuilds from params, so server-side mutations must be mirrored into params or they get lost. The sort/drop design removes this.
- Pydantic has no notion of "existing child matched by id → update, else insert". A port would need an explicit matching step (by primary-key field) if it wants to support DB-backed child collections, or it could support only embedded/value lists (like `embeds_many` + `on_replace: :delete`) at first.

### Gaps
- Couldn't retrieve the Ecto "associations cheatsheet" or the Dashbit post on associations/embeds (blocked).

---

## 3. Phoenix.HTML.Form, the FormData protocol, FormField, `to_form`, `inputs_for`, naming and IDs

### Takeaway
`Phoenix.HTML.Form` is a **render-side view model**, separate from the validation model: `{source, impl, id, name, data, params, errors, hidden, action, index, options}`. `form[:field]` returns a `FormField{id, name, value, errors, field, form}`. The `Phoenix.HTML.FormData` protocol turns any source into a Form (implemented for `Map` in phoenix_html, for `Ecto.Changeset` in phoenix_ecto, and by Ash for its forms). That's why the same `<.input field={@form[:email]}>` works on changesets, plain param maps, and Ash forms. Nesting is purely name/id concatenation: `user[addresses][0][street]` / `user_addresses_0_street`.

### Cited Findings

**Form struct fields:** `:source`, `:impl`, `:id`, `:name`, `:data` ("lookup data"), `:params`, `:hidden` ("fields that are required to submit the form behind the scenes as hidden inputs"), `:options`, `:errors`, `:action`, `:index` ("the index of the struct in the form") — [phoenix_html form.ex](https://github.com/phoenixframework/phoenix_html/blob/main/lib/phoenix_html/form.ex)

**Access behaviour → FormField:**
```elixir
defp fetch(%{errors: errors} = form, field, field_as_string) do
  {:ok, %Phoenix.HTML.FormField{
     errors: field_errors(errors, field), field: field, form: form,
     id: input_id(form, field_as_string), name: input_name(form, field_as_string),
     value: input_value(form, field)}}
end
```
"It is possible to "access" fields which do not exist in the source data structure. A `Phoenix.HTML.FormField` struct will be dynamically created with some attributes such as `name` and `id` populated." — [phoenix_html form.ex](https://github.com/phoenixframework/phoenix_html/blob/main/lib/phoenix_html/form.ex). FormField has `@enforce_keys [:id, :name, :errors, :field, :form, :value]` — [form_field.ex](https://github.com/phoenixframework/phoenix_html/blob/main/lib/phoenix_html/form_field.ex)

**Naming/ID rules:** `input_name(%{name: nil}, field) -> "field"`, else `"#{name}[#{field}]"`; `input_id(%{id: nil}, field) -> "field"`, else `"#{id}_#{field}"`; for radios/multi-checkboxes `input_id(form, field, value)` appends `"_" <> value` with non-word chars → `_` — [phoenix_html form.ex](https://github.com/phoenixframework/phoenix_html/blob/main/lib/phoenix_html/form.ex). Nested (many) forms: `id: id <> "_" <> index_string, name: name <> "[" <> index_string <> "]"` where `id`/`name` default to `form.id <> "_#{field}"` / `form.name <> "[#{field}]"` — [phoenix_ecto html.ex](https://github.com/phoenixframework/phoenix_ecto/blob/main/lib/phoenix_ecto/html.ex)

**Value precedence (Ecto impl):** changes → raw params (string key) → data:
```elixir
def input_value(%{changes: changes, data: data}, %{params: params}, field) when is_atom(field) do
  case changes do
    %{^field => value} -> value
    %{} ->
      string = Atom.to_string(field)
      case params do
        %{^string => value} -> value
        %{} -> Map.get(data, field)
      end
  end
end
```
— [phoenix_ecto html.ex](https://github.com/phoenixframework/phoenix_ecto/blob/main/lib/phoenix_ecto/html.ex). phoenix_html warns "there is no guarantee that the value will have a certain type. For example, a boolean field will be sent as "false" as a parameter"; use `normalize_value/2` (checkbox → boolean, `datetime-local` formatting, textarea leading newline) — [phoenix_html form.ex](https://github.com/phoenixframework/phoenix_html/blob/main/lib/phoenix_html/form.ex)

**Protocol shape:**
```elixir
defprotocol Phoenix.HTML.FormData do
  def to_form(data, options)                 # root form; shared opts :as, :id
  def to_form(data, form, field, options)    # nested forms -> [Form]; opts :id, :as, :default, :prepend, :append, :action
  def input_value(data, form, field)
  def input_validations(data, form, field)   # HTML5 attrs
end
```
— [phoenix_html form_data.ex](https://github.com/phoenixframework/phoenix_html/blob/main/lib/phoenix_html/form_data.ex)

**`to_form` from a plain map (params-backed forms, no changeset):** "When you pass a map to `to_form/1`, it assumes said map contains the form parameters, which are expected to have string keys." `to_form(user_params, as: :user)`; errors can be passed manually: `to_form(%{"search" => nil}, errors: [search: {"Can't be blank", []}])`. The Map impl warns if atom keys are given, reads values from `params` then `data`, and supports nested `inputs_for` via `:default` (map → one, list → many; params entries are sorted by key) — [Phoenix.Component.to_form/2](https://github.com/phoenixframework/phoenix_live_view/blob/main/lib/phoenix_component.ex); [form_data.ex Map impl](https://github.com/phoenixframework/phoenix_html/blob/main/lib/phoenix_html/form_data.ex)

**`to_form` options:** `:as` (name prefix), `:id`, `:errors` (maps only), `:action` (e.g. `to_form(changeset, action: :validate)`, "passed to the underlying `Phoenix.HTML.FormData` implementation options"). Passing an atom to `for` is deprecated ("Passing an atom to "for" in the form component is deprecated") — [Phoenix.Component](https://github.com/phoenixframework/phoenix_live_view/blob/main/lib/phoenix_component.ex)

**Changeset → form naming:** name defaults to the underscored last module segment (`MyApp.Users.User` → `"user"`, so params arrive under `%{"user" => …}`); a schemaless/non-struct changeset raises "cannot generate name … You must either pass the :as option". Primary keys become `hidden` fields; HTTP method is `"put"` for loaded records, `"post"` otherwise — [phoenix_ecto html.ex](https://github.com/phoenixframework/phoenix_ecto/blob/main/lib/phoenix_ecto/html.ex)

**Nested forms inherit the parent action; replaced children are skipped:**
```elixir
# If the parent changeset had no action, we need to remove the action
# from children changeset so we ignore all errors accordingly.
defp apply_action(changeset, nil), do: %{changeset | action: nil}
defp skip_replaced(changesets), do: Enum.reject(changesets, &match?(%Ecto.Changeset{action: :replace}, &1))
```
`:default` is not supported for changesets ("The default value must be set in the changeset data"); unloaded associations raise ("Please preload your associations before using them in inputs_for") — [phoenix_ecto html.ex](https://github.com/phoenixframework/phoenix_ecto/blob/main/lib/phoenix_ecto/html.ex)

**`<.inputs_for>` component (LiveView) and `_persistent_id`:**
```heex
<.inputs_for :let={f_nested} field={@form[:nested]}>
  <.input type="text" field={f_nested[:name]} />
</.inputs_for>
```
Attrs: `field` (required), `id`, `as`, `default`, `prepend`, `append`, `skip_hidden`, `skip_persistent_id` ("Skip the automatic rendering of hidden _persistent_id fields used for reordering inputs"), `options`. It renders each nested form's `hidden` fields (e.g. `id`) as `<input type="hidden">`, then the slot. Implementation assigns each nested form a `_persistent_id` param (reused from incoming params if present, else next free integer), builds the DOM id from it (`"#{parent_form.id}_#{field_name}_#{id}"`), and sets `index` to the positional index — [Phoenix.Component.inputs_for/1](https://github.com/phoenixframework/phoenix_live_view/blob/main/lib/phoenix_component.ex). `<.inputs_for>` added in LV 0.18.12 (2023-02); "Support ordered inputs within `inputs_for`, to pair with Ecto's new `sort_param` and `drop_param`" in 0.19.0 (2023-05-29); `skip_persistent_id` added in 1.0.6 (2025-03-20) — [LiveView v1.0 CHANGELOG](https://github.com/phoenixframework/phoenix_live_view/blob/v1.0/CHANGELOG.md)

**Legacy helpers:** phoenix_html 3.3.2 (2023-08-10) deprecated `inputs_for/2,3` (non-anonymous-function forms); phoenix_html 4.0.0 (2023-12-19) moved all HTML helpers (`form_for`, `text_input`, `error_tag`, …) to the separate `phoenix_html_helpers` package ("HTML Helpers are no longer used in new apps from Phoenix v1.7, instead it relies on function components") — [phoenix_html CHANGELOG](https://github.com/phoenixframework/phoenix_html/blob/main/CHANGELOG.md)

**Why `@form[:field]` rather than `:let`:** "LiveView can better optimize your code if you access the form fields using `@form[:field]` rather than through the let-variable `form`" — [Phoenix.Component.form/1](https://github.com/phoenixframework/phoenix_live_view/blob/main/lib/phoenix_component.ex). `Phoenix.HTML.Form.input_changed?/3` compares impl, id, name, action, per-field errors and value to support that change tracking — [phoenix_html form.ex](https://github.com/phoenixframework/phoenix_html/blob/main/lib/phoenix_html/form.ex)

### Inferences
- The two-layer split (validation model → **FormData protocol** → render-only `Form`/`FormField`) is the most portable idea. In Python: a `FormData` `Protocol` (or `functools.singledispatch`) with `to_form(source, *, as_=None, id=None, action=None)`, `nested_forms(source, form, field)`, `input_value(...)`, `input_validations(...)`, with implementations for `dict` (raw params), a pydantic/dataclass changeset, and third-party sources. Templates only ever see `Form`/`FormField` (id, name, value, errors, field, form). `form["email"]` via `__getitem__` matches Elixir's Access behaviour.
- `_persistent_id` appears to exist so DOM ids stay stable when rows are reordered or dropped (ids come from the persistent id while `index` is positional), which keeps DOM patching from confusing rows. This is inferred from the source; the purpose isn't documented (issue #3673's reporter explicitly asked what it's for).
- `input_validations` → HTML5 attributes is a cheap win for a pydantic port: `Field(min_length=, max_length=, ge=, le=)` → `minlength/maxlength/min/max`.

### Gaps
- No authoritative statement found on the design rationale for `_persistent_id` (comment threads not loadable).

---

## 4. The LiveView form lifecycle on the wire: phx-change/phx-submit, `_target`, serialization, `_unused_`/`used_input?`, debounce, recovery, trigger-action, disable-with

### Takeaway
On each input event the client serializes the **entire form** (`new FormData(form)` → `URLSearchParams`, files stripped) and sends it with `_target` (the path of the input that changed). It also appends a sibling `_unused_<name>` key for every non-hidden field the user hasn't focused or submitted. Server-side, `used_input?/1` uses those markers to hide errors on untouched fields. This replaced the client-side `phx-feedback-for` in LV 1.0 (May–Dec 2024). The server re-renders, but the client never overwrites the focused input's value. Forms with `id` + `phx-change` auto-recover after reconnects by replaying a change event.

### Cited Findings

**Basic events and the `validate`/`save` pair:**
```heex
<.form for={@form} id="my-form" phx-change="validate" phx-submit="save">
  <.input type="text" field={@form[:username]} />
  <.input type="email" field={@form[:email]} />
  <button>Save</button>
</.form>
```
```elixir
def handle_event("save", %{"user" => user_params}, socket) do
  case Accounts.create_user(user_params) do
    {:ok, user} -> {:noreply, socket |> put_flash(:info, "user created") |> redirect(to: ~p"/users/#{user}")}
    {:error, %Ecto.Changeset{} = changeset} -> {:noreply, assign(socket, form: to_form(changeset))}
  end
end
```
Per-input `phx-change` is allowed ("Only the individual input is sent as params for an input marked with `phx-change`") — [form-bindings guide](https://github.com/phoenixframework/phoenix_live_view/blob/main/guides/client/form-bindings.md)

**`_target`:** "the payload is pushed to the server with a `"_target"` param in the root payload containing the keyspace of the input name which triggered the change event": `<input name="user[username]"/>` → `%{"_target" => ["user", "username"], "user" => %{"username" => "Name"}}`. A reset button emits `phx-change` with `_target` = the reset button's name (`%{"_target" => ["reset"]}`) — [form-bindings guide](https://github.com/phoenixframework/phoenix_live_view/blob/main/guides/client/form-bindings.md)

**Client serialization (v1.2 TypeScript):** `serializeForm` injects the clicked submitter's name/value as a hidden input (in DOM order), builds `new FormData(form)`, deletes `File` entries, and for each field computes whether it's unused (`!(PHX_HAS_FOCUSED || PHX_HAS_SUBMITTED || phx-no-unused-field)`) and whether it's hidden-only. For unused, non-hidden fields (and not the submitter), it appends `prependFormDataKey(key, "_unused_")` with an empty value, then returns `params.toString()` (urlencoded). The change event payload is `{type: "form", event, value: formData, meta: {_target, ...phx-value-*}, uploads, cid}` — [view.ts](https://github.com/phoenixframework/phoenix_live_view/blob/v1.2/assets/js/phoenix_live_view/view.ts). The key rewriting only touches the last path segment:
```ts
export const prependFormDataKey = (key, prefix) => {
  const isArray = key.endsWith("[]");
  let baseKey = isArray ? key.slice(0, -2) : key;
  baseKey = baseKey.replace(/([^\[\]]+)(\]?$)/, `${prefix}$1$2`);  // user[email] -> user[_unused_email]
  if (isArray) baseKey += "[]";
  return baseKey;
};
```
— [view.ts](https://github.com/phoenixframework/phoenix_live_view/blob/v1.2/assets/js/phoenix_live_view/view.ts)

**`used_input?/1` (server):**
```elixir
def used_input?(%Phoenix.HTML.FormField{field: field, form: form}), do: used_param?(form.params, field)

defp used_param?(_params, "_unused_" <> _), do: false
defp used_param?(params, field) do
  field_str = "#{field}"; unused_field_str = "_unused_#{field}"
  case params do
    %{^field_str => _, ^unused_field_str => _} -> false
    %{^field_str => %{} = nested} when not is_struct(nested) ->
      Enum.any?(Map.keys(nested), &used_param?(nested, &1))   # composite inputs: used if any part used
    %{^field_str => _val} -> true
    %{} -> false
  end
end
```
Docs: "Used inputs are only those inputs that have been focused, interacted with, or submitted by the client … For non-LiveViews, all inputs are considered used." Example payload: `%{"title" => "new title", "email" => "", "_unused_email" => ""}` — [Phoenix.Component.used_input?/1](https://github.com/phoenixframework/phoenix_live_view/blob/main/lib/phoenix_component.ex)

**`phx-feedback-for` removal (the "saga").** LV 1.0.0-rc.0 (2024-05-08): "Remove `phx-feedback-for` in favor of `Phoenix.Component.used_input?`"; LV 1.0 "removes the client-based `phx-feedback-for` annotation for showing and hiding input feedback … replaced by `Phoenix.Component.used_input?/2`, which handles showing and hiding feedback using standard server rendering." A JS shim (`phx_feedback_dom.js`, passed as the `dom:` option to `LiveSocket`) was provided for old apps. The migration removes `phx-feedback-for={@name}` wrappers and `phx-no-feedback:` Tailwind variants and adds `errors = if Phoenix.Component.used_input?(field), do: field.errors, else: []`. Nested support in `used_input?` arrived in 1.0.0-rc.7 (2024-10-17); LV 1.0.0 final was 2024-12-03 — [LiveView v1.0 CHANGELOG](https://github.com/phoenixframework/phoenix_live_view/blob/v1.0/CHANGELOG.md)

**Opt-out:** `phx-no-unused-field` (on an input or the whole form) stops sending `_unused` params; added in v1.2.0-rc.0 (2026-04-23) in response to issue #3577 — [LiveView v1.2 CHANGELOG](https://github.com/phoenixframework/phoenix_live_view/blob/v1.2/CHANGELOG.md); [form-bindings guide](https://github.com/phoenixframework/phoenix_live_view/blob/main/guides/client/form-bindings.md)

**Hidden-only fields never get `_unused_`** (to cut payload size): "With large forms that contains multiple hidden inputs, the payload size increases unnecessarily because of the `_unused` parameters" — [PR #3244 (SteffenDE, May 2024)](https://github.com/phoenixframework/phoenix_live_view/pull/3244)

**Debounce/throttle:** `phx-debounce` takes ms or `"blur"` (default 300ms when valueless); `phx-throttle` takes ms. "When a `phx-submit`, or a `phx-change` for a different input is triggered, any current debounce or throttle timers are reset for existing inputs."
```heex
<input type="text" name="user[email]" phx-debounce="blur"/>
<input type="text" name="user[username]" phx-debounce="2000"/>
```
— [bindings guide](https://github.com/phoenixframework/phoenix_live_view/blob/v1.2/guides/client/bindings.md)

**Client is the source of truth for focused inputs:** "For any given input with focus, LiveView will never overwrite the input's current value, even if it deviates from the server's rendered updates." Opt out with `phx-patch-focused` (added v1.2.8, 2026-07-27: "Allow opting focused form elements into DOM patching"). While a `phx-change` is in flight, the input and form get `phx-change-loading` — [form-bindings guide](https://github.com/phoenixframework/phoenix_live_view/blob/main/guides/client/form-bindings.md); [LV v1.2 CHANGELOG](https://github.com/phoenixframework/phoenix_live_view/blob/v1.2/CHANGELOG.md)

**Submit behaviour and `phx-disable-with`:** on `phx-submit` inputs become `readonly`, submit buttons are disabled, and the form gets `phx-submit-loading`. On ack, the form is re-enabled and the last focused input is restored. `<button type="submit" phx-disable-with="Saving...">Save</button>` swaps `innerText` during submission. LiveView "ignores clicks on elements that are currently awaiting an acknowledgement" — [form-bindings guide](https://github.com/phoenixframework/phoenix_live_view/blob/main/guides/client/form-bindings.md)

**Number inputs:** "LiveView will not send change events from the client when an input is invalid" for `type="number"`; docs recommend `<input type="text" inputmode="numeric" pattern="[0-9]*">` — [form-bindings guide](https://github.com/phoenixframework/phoenix_live_view/blob/main/guides/client/form-bindings.md)

**Password inputs:** values aren't re-rendered for security; you must set `value={input_value(f[:password].value)}` explicitly — [form-bindings guide](https://github.com/phoenixframework/phoenix_live_view/blob/main/guides/client/form-bindings.md)

**`phx-trigger-action`:** validate over the socket, then do a real HTTP POST (for session-mutating routes such as login/reset password):
```heex
<.form :let={f} for={@changeset} action={~p"/users/reset_password"}
  phx-submit="save" phx-trigger-action={@trigger_submit}>
```
"Once `phx-trigger-action` is true, LiveView disconnects and then submits the form." — [form-bindings guide](https://github.com/phoenixframework/phoenix_live_view/blob/main/guides/client/form-bindings.md)

**Form recovery:** "all forms marked with `phx-change` and having `id` attribute will recover input values automatically after the user has reconnected or the LiveView has remounted after a crash … by the client triggering the same `phx-change` to the server as soon as the mount has been completed." Custom: `phx-auto-recover="recover_wizard"`; disable: `phx-auto-recover="ignore"` — [form-bindings guide](https://github.com/phoenixframework/phoenix_live_view/blob/main/guides/client/form-bindings.md). LV 1.2 test helpers now warn on `phx-change` forms without `id` "because without an `id` form recovery does not work" (opt out with `phx-ignore-missing-id` or `:missing_form_id` config) — [LV v1.2 CHANGELOG](https://github.com/phoenixframework/phoenix_live_view/blob/v1.2/CHANGELOG.md)

**Why `phx-change` is effectively mandatory:** "if an unrelated change happens on the page, LiveView should re-render the inputs with their updated values. Without `phx-change`, the inputs would otherwise be cleared. Alternatively, you can use `phx-update="ignore"`" — [Phoenix.Component.form/1](https://github.com/phoenixframework/phoenix_live_view/blob/main/lib/phoenix_component.ex)

**Triggering from JS / custom inputs:** `el.dispatchEvent(new Event("input", {bubbles: true}))` triggers `phx-change`; a submit `Event` triggers `phx-submit` — [form-bindings guide](https://github.com/phoenixframework/phoenix_live_view/blob/main/guides/client/form-bindings.md)

### Inferences
- The two-level error gating is: **(a) form-level `action`** (has the user done anything that warrants errors? It's set on validate/submit) × **(b) field-level `used_input?`** (has this particular field been touched or submitted?). On submit, the client marks all inputs as submitted, so no `_unused_` keys are sent and every error shows. A Python port gets this almost for free if pyview's JS client already mirrors LiveView's `serializeForm`, since the `_unused_` keys arrive in the params dict. `used_input(field)` is ~15 lines (above).
- pyview's current `ChangeSet.apply` uses `_target[0]` to update a single field. Adopting LiveView's "always resend the whole form, rebuild from (data, params)" model would remove the need for that and make nested names (`_target = ["user", "addresses", "0", "street"]`) work.
- Parsing `user[addresses][0][street]=…&user[addresses_sort][]=0` into nested dicts/lists (Plug-style) is a prerequisite. Starlette's `FormData` gives flat multi-dict keys, so a Plug-compatible nested-key decoder is needed.

### Gaps
- Couldn't find a first-party write-up (blog/forum post by José Valim/Chris McCord) explaining *why* `phx-feedback-for` was dropped beyond the changelog's "handles showing and hiding feedback using standard server rendering". The phoenixframework.org LiveView 1.0 announcement was blocked.

---

## 5. `core_components.ex`: `<.input>`, `<.error>`, `translate_error`, `simple_form` → `<.form>`, and "generated code you own"

### Takeaway
Phoenix doesn't ship a styled form-component library. `mix phx.new` **generates** `CoreComponents` into your app (Tailwind; since Phoenix 1.8, Tailwind + daisyUI), and you edit it. `<.input field={@form[:x]}>` is a multi-clause function component: the first clause turns a `FormField` into `id/name/value/errors` (filtering errors with `used_input?` and translating them), and later clauses render per `type`. Phoenix 1.8 (2025-08-05) simplified these components and dropped `<.simple_form>` in favour of the built-in `<.form>`.

### Cited Findings

**The FormField → assigns clause (Phoenix 1.8 template):**
```elixir
attr :field, Phoenix.HTML.FormField, doc: "a form field struct retrieved from the form, for example: @form[:email]"
attr :type, :string, default: "text",
  values: ~w(checkbox color date datetime-local email file month number password
             search select tel text textarea time url week hidden)
attr :errors, :list, default: []
attr :class, :any, default: nil;  attr :error_class, :any, default: nil
attr :rest, :global, include: ~w(accept autocomplete capture cols disabled form list max maxlength min minlength
                                 multiple pattern placeholder readonly required rows size step)

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
— [Phoenix 1.8 core_components](https://github.com/phoenixframework/phoenix/blob/v1.8/installer/templates/phx_web/components/core_components.ex.eex)

**Checkbox renders a hidden "false" twin** (so unchecked boxes still send a value):
```heex
<input type="hidden" name={@name} value="false" disabled={@rest[:disabled]} form={@rest[:form]} />
<input type="checkbox" id={@id} name={@name} value="true" checked={@checked} class={@class || "checkbox checkbox-sm"} {@rest} />
```
Default text input:
```heex
<div class="fieldset mb-2">
  <label for={@id}>
    <span :if={@label} class="label mb-1">{@label}</span>
    <input type={@type} name={@name} id={@id} value={Phoenix.HTML.Form.normalize_value(@type, @value)}
      class={[@class || "w-full input", @errors != [] && (@error_class || "input-error")]} {@rest} />
  </label>
  <.error :for={msg <- @errors}>{msg}</.error>
</div>
```
Unsupported types: "Unsupported types, such as radio, are best written directly in your templates." — [Phoenix 1.8 core_components](https://github.com/phoenixframework/phoenix/blob/v1.8/installer/templates/phx_web/components/core_components.ex.eex)

**Philosophy statement in the generated moduledoc:** "At first glance, this module may seem daunting, but its goal is to provide core building blocks for your application, such as tables, forms, and inputs. … You may customize and style them in any way you want, based on your application growth and needs. The foundation for styling is Tailwind CSS … augmented with daisyUI" — [Phoenix 1.8 core_components](https://github.com/phoenixframework/phoenix/blob/v1.8/installer/templates/phx_web/components/core_components.ex.eex). `form-bindings` guide: "`input/1` is a function component for rendering inputs, most often defined in your own application, often encapsulating labelling, error handling, and more" — [form-bindings guide](https://github.com/phoenixframework/phoenix_live_view/blob/main/guides/client/form-bindings.md)

**Phoenix 1.8 changes:** "Extend tailwindcss support in new apps with daisyUI"; "Simplify core components and live generators to more closely match basic `phx.gen.html` crud"; v1.8.0 released 2025-08-05; a later 1.8.x "(re-)add `<.input field={@form[:foo]} type="hidden" />` support" — [Phoenix v1.8 CHANGELOG](https://github.com/phoenixframework/phoenix/blob/v1.8/CHANGELOG.md). The 1.8 core_components contains no `simple_form` (0 occurrences), whereas 1.7's defined:
```elixir
def simple_form(assigns) do
  ~H"""
  <.form :let={f} for={@for} as={@as} {@rest}>
    <div class="mt-10 space-y-8 bg-white">
      {render_slot(@inner_block, f)}
      <div :for={action <- @actions} class="mt-2 flex items-center justify-between gap-6">{render_slot(action, f)}</div>
    </div>
  </.form>
  """
end
```
— [Phoenix 1.7 core_components](https://github.com/phoenixframework/phoenix/blob/v1.7/installer/templates/phx_web/components/core_components.ex); [Phoenix 1.8 core_components](https://github.com/phoenixframework/phoenix/blob/v1.8/installer/templates/phx_web/components/core_components.ex.eex)

**1.8 generated LiveView form (phx.gen.live):**
```heex
<.form for={@form} id="post-form" phx-change="validate" phx-submit="save">
  ...inputs...
  <footer>
    <.button phx-disable-with="Saving..." variant="primary">Save Post</.button>
  </footer>
</.form>
```
```elixir
def handle_event("validate", %{"post" => post_params}, socket) do
  changeset = Blog.change_post(socket.assigns.current_scope, socket.assigns.post, post_params)
  {:noreply, assign(socket, form: to_form(changeset, action: :validate))}
end
```
— [Phoenix 1.8 phx.gen.live form template](https://github.com/phoenixframework/phoenix/blob/v1.8/priv/templates/phx.gen.live/form.ex.eex) (template variables resolved by hand here for readability)

**`translate_errors/2` helper** for a keyword error list: `for {^field, {msg, opts}} <- errors, do: translate_error({msg, opts})` — [Phoenix 1.8 core_components](https://github.com/phoenixframework/phoenix/blob/v1.8/installer/templates/phx_web/components/core_components.ex.eex)

### Inferences
- The split between **framework primitives** (`<.form>`, `<.inputs_for>`, `to_form`, `used_input?`, FormField) and **app-owned presentation** (`<.input>`, `<.error>`, CSS) is the reason Phoenix forms don't feel locked to one CSS framework. For pyview, this suggests shipping headless primitives (Form, FormField, `inputs_for`, `used_input`, error translation hook) plus a *copyable* reference `input` template/component (e.g. via a `pyview` CLI scaffold) rather than a styled widget set.
- The single `<.input>` with multi-clause dispatch on `type` keeps call sites uniform (`<.input field=... type="select" options=...>`). This maps to a Python component with a `match type:` block.

### Gaps
- The Phoenix 1.8 release blog post (phoenixframework.org) was blocked; the rationale for dropping `simple_form` comes only from the changelog phrase "Simplify core components".

---

## 6. Add/remove/reorder rows in HEEx: sort/drop params, buttons vs hidden checkboxes, and the old event pattern

### Takeaway
The official pattern (LV ≥0.19 + Ecto ≥3.10) is **all-HTML**: inside `<.inputs_for>`, each row has a hidden `parent[items_sort][]` with its index and a remove control named `parent[items_drop][]` with value = index. An "add" control is named `parent[items_sort][]` with `value="new"` (any unknown value creates a row). There's also one empty hidden `parent[items_drop][]` outside the loop so that "delete all" survives. Buttons use `type="button"` + `phx-click={JS.dispatch("change")}` to trigger `phx-change`. Label-wrapped hidden checkboxes are an older variant.

### Cited Findings

**Official markup (Phoenix.Component docs):**
```heex
<.inputs_for :let={ef} field={@form[:emails]}>
  <input type="hidden" name="mailing_list[emails_sort][]" value={ef.index} />
  <.input type="text" field={ef[:email]} placeholder="email" />
  <.input type="text" field={ef[:name]} placeholder="name" />
  <button type="button" name="mailing_list[emails_drop][]" value={ef.index}
          phx-click={JS.dispatch("change")}>
    <.icon name="hero-x-mark" class="w-6 h-6 relative top-2" />
  </button>
</.inputs_for>

<input type="hidden" name="mailing_list[emails_drop][]" />

<button type="button" name="mailing_list[emails_sort][]" value="new" phx-click={JS.dispatch("change")}>
  add more
</button>
```
Explanations from the docs: the hidden sort input "tells Ecto's cast operation how to sort existing children, or where to insert new children"; `JS.dispatch("change")` makes the button click "a change event, rather than a submit event"; the empty hidden drop input exists "to ensure that all children are deleted when saving a form where the user dropped all entries. This hidden input is required whenever dropping associations"; the add button "must have `type="button"` to prevent it from submitting the form. Ecto will treat unknown sort params as new children"; put a similar button before `<.inputs_for>` to prepend. "When using these options, `on_replace: :delete` on the `has_many` and `embeds_many` is required." — [Phoenix.Component.inputs_for/1 docs](https://github.com/phoenixframework/phoenix_live_view/blob/main/lib/phoenix_component.ex)

**Mechanism behind "buttons work as inputs":** "Like inputs, buttons with name/value pairs are serialized with form data on change and submit events" — [Phoenix.Component.inputs_for/1 docs](https://github.com/phoenixframework/phoenix_live_view/blob/main/lib/phoenix_component.ex); the client injects the submitter's name/value as a hidden input "in the order that it exists in the DOM" — [view.ts](https://github.com/phoenixframework/phoenix_live_view/blob/v1.2/assets/js/phoenix_live_view/view.ts)

**Checkbox variant + drag-and-drop (todo_trek, the 0.19 demo app):**
```heex
<label class="block cursor-pointer">
  <input type="checkbox" name="list[notifications_order][]" class="hidden" />
  <.icon name="hero-plus-circle" /> prepend
</label>
<div id="notifications" phx-hook="SortableInputsFor" class="space-y-2">
  <.inputs_for :let={f_nested} field={@form[:notifications]}>
    <div class="flex space-x-2 drag-item">
      <input type="hidden" name="list[notifications_order][]" value={f_nested.index} />
      <.icon name="hero-bars-3" class="w-6 h-6 relative top-2" data-handle />
      <.input type="text" field={f_nested[:email]} placeholder="email" />
      <.input type="text" field={f_nested[:name]} placeholder="name" />
      <label>
        <input type="checkbox" name="list[notifications_delete][]" value={f_nested.index} class="hidden" />
        <.icon name="hero-x-mark" class="w-6 h-6 relative top-2" />
      </label>
    </div>
  </.inputs_for>
</div>
<label class="block cursor-pointer">
  <input type="checkbox" name="list[notifications_order][]" class="hidden" />
  <.icon name="hero-plus-circle" /> add more
</label>
<input type="hidden" name="list[notifications_delete][]" />
```
with the validate handler `changeset |> Map.put(:action, :validate)` — [todo_trek form_component.ex](https://github.com/chrismccord/todo_trek/blob/main/lib/todo_trek_web/live/list_live/form_component.ex). Drag-and-drop works because a JS hook reorders the DOM rows and the hidden `*_order[]` inputs then serialize in the new order (inferred from markup; hook source not read).

**Official announcement:** LiveView 0.19 (May 29, 2023) "includes long awaited dynamic form features … Dynamically adding and removing inputs with inputs_for is now supported by rendering checkboxes for inserts and removals. This can be combined with Ecto.Changeset.cast/3's `:sort_param` and `:drop_param` options" — [Phoenix Blog: LiveView 0.19 released](https://www.phoenixframework.org/blog/phoenix-liveview-0.19-released) (seen only as a search snippet; date corroborated by [LV CHANGELOG 0.19.0 (2023-05-29)](https://github.com/phoenixframework/phoenix_live_view/blob/v1.0/CHANGELOG.md))

**Ash's analogous magic params:** `form[_add_locations]=end|start|<index>`, `form[_drop_locations][]=<index>`, `form[_sort_locations][]=<index>` (see §8) — [ash_phoenix nested-forms guide](https://github.com/ash-project/ash_phoenix/blob/main/documentation/topics/nested-forms.md)

**Deprecated / older approach:** server events with `get_field` + `put_embed` (see §2 snippet) — [LostKobrakai gist](https://gist.github.com/LostKobrakai/ce5385bd118189a24d60893188612de9)

### Inferences
- The sort/drop protocol is essentially a **params-level command language** (`sort[]` = desired order + "new" sentinels; `drop[]` = indices to delete; an always-present empty `drop[]` to distinguish "empty list" from "field absent"). A pyview port could implement it in a generic `cast_list(changeset, "emails", sort_param="emails_sort", drop_param="emails_drop")` over `list[BaseModel]`, and provide small helpers so templates don't hand-write the names: e.g. `{{ sort_input(f) }}`, `{{ drop_button(f, label) }}`, `{{ add_button(form, "emails") }}`.
- Pure HTML needs no JS hooks for add/remove (only reorder-by-drag needs a hook), which fits pyview's minimal-client approach.
- Because of "unknown index → new empty child", the **order of hidden sort inputs is significant**. The Python cast must iterate `sort` in submission order, which means the multi-dict decoding must preserve order.

### Gaps
- Didn't read the `SortableInputsFor` hook source in todo_trek (not fetched). The Dockyard (Mar 2024) and Arrowsmith Labs nested-forms tutorials were blocked, so their tips aren't included.

---

## 7. Polymorphic / conditional nested forms: `polymorphic_embed`, Ash union forms

### Takeaway
Core Ecto has no polymorphic embeds. The community `polymorphic_embed` library (v5.x) adds `polymorphic_embeds_one/many` with a discriminator param (`__type__` by default, or type inferred from which fields are present), `cast_polymorphic_embed/3` (supports `sort_param`/`drop_param`), and a `<.polymorphic_embed_inputs_for>` component that renders a hidden `__type__`. Conditional fields in templates are done with a plain `case` on the row's type. AshPhoenix does the same for union types via a hidden `_union_type` param, and switching type means `remove_form` + `add_form`.

### Cited Findings

**Schema:**
```elixir
schema "reminders" do
  field :date, :utc_datetime
  field :text, :string
  polymorphic_embeds_one :channel,
    types: [sms: MyApp.Channel.SMS, email: MyApp.Channel.Email],
    on_type_not_found: :raise,
    on_replace: :update
end

def changeset(struct, values) do
  struct
  |> cast(values, [:date, :text])
  |> cast_polymorphic_embed(:channel, required: true)
  |> validate_required(:date)
end
```
Lists: `polymorphic_embeds_many :contexts, types: [...], on_replace: :delete, ...`. Stored as `:map` in the DB — [polymorphic_embed README](https://github.com/mathieuprog/polymorphic_embed/blob/master/README.md)

**Type discrimination:** by default "we expect a `"__type__"` (or `:__type__`) parameter containing the type"; alternatively `[email: [module: MyApp.Channel.Email, identify_by_fields: [:address, :confirmed]]]` infers type from present fields (an explicit `__type__` still wins). Options: `:type_field_name`, `:use_parent_field_for_type`, `:on_type_not_found` (`:raise | :changeset_error | :nilify | :ignore`), mandatory `:on_replace` (`:update` for one, `:delete` for many), `:retain_unlisted_types_on_load`, `:nilify_unlisted_types_on_load`. `cast_polymorphic_embed` supports `:with` per type, `:drop_param`, `:sort_param`, `:default_type_on_sort_create` ("in some cases, sort creates a new entry; this option specifies which type to use by default") — [polymorphic_embed README](https://github.com/mathieuprog/polymorphic_embed/blob/master/README.md)

**LiveView rendering:**
```heex
<.form :let={f} for={@changeset} id="reminder-form" phx-change="validate" phx-submit="save">
  <.polymorphic_embed_inputs_for field={f[:channel]} :let={channel_form}>
    <%= case source_module(channel_form) do %>
      <% SMS -> %>   <.input field={channel_form[:number]} label="Number" />
      <% Email -> %> <.input field={channel_form[:address]} label="Email Address" />
    <% end %>
  </.polymorphic_embed_inputs_for>
</.form>
```
Helpers "render a hidden input for the `"__type__"` field". Caveat: "`Ecto.changeset.traverse_errors/2` won't include the errors of polymorphic embeds. You may instead use `PolymorphicEmbed.traverse_errors/2`" — [polymorphic_embed README](https://github.com/mathieuprog/polymorphic_embed/blob/master/README.md)

**Ash unions:** a union type is declared with `tag: :type, tag_value: :normal` per member; "We track the type of the value in a hidden param called `_union_type`". Changing type:
```elixir
def handle_event("type-changed", %{"_target" => path} = params, socket) do
  new_type = get_in(params, path)
  path = :lists.droplast(path)
  form =
    socket.assigns.form
    |> AshPhoenix.Form.remove_form(path)
    |> AshPhoenix.Form.add_form(path, params: %{"_union_type" => new_type})
  {:noreply, assign(socket, :form, form)}
end
```
```heex
<.inputs_for :let={fc} field={@form[:content]}>
  <.input field={fc[:_union_type]} phx-change="type-changed" type="select"
          options={[Normal: "normal", Special: "special"]} />
  <%= case fc.params["_union_type"] do %>
    <% "normal" -> %>  <.input type="text" field={fc[:body]} />
    <% "special" -> %> <.input type="text" field={fc[:text]} />
  <% end %>
</.inputs_for>
```
Non-embedded union members (e.g. `:integer`) still render as a nested form accessed via `nested_form[:value]` — [ash_phoenix union-forms guide](https://github.com/ash-project/ash_phoenix/blob/main/documentation/topics/union-forms.md)

### Inferences
- Pydantic already has **discriminated unions** (`Annotated[Union[SMS, Email], Field(discriminator="type")]`), which map directly onto the `__type__`/`_union_type` hidden-param approach. A pyview `inputs_for` over a discriminated-union field could render the hidden discriminator automatically and expose `f.type`/`f.model_cls` for a template `match`/`if`.
- Note the `_target` trick in Ash's handler: `_target` gives the full path of the changed select, so one generic handler can rebuild the subform at any depth. pyview should expose `_target` as a parsed path for the same reason.
- polymorphic_embed's `traverse_errors` caveat shows a real risk: if polymorphism is bolted on outside the core changeset, generic tooling (error traversal, FormData) can miss it. For a port, discriminated unions should be first-class in the nested-form machinery.

### Gaps
- Didn't read polymorphic_embed's HexDocs or source for how it resets child params when `__type__` changes mid-edit (for example, whether stale fields from the old type get dropped).

---

## 8. AshPhoenix.Form: model, API, how it differs from changesets, and why Ash built it

### Takeaway
`AshPhoenix.Form` is a **stateful, recursive form tree** designed to live in the LiveView's assigns and be updated in place (`validate/3`, `add_form/3`, `remove_form/3`, `sort_forms/3`, `update_params/3`, `submit/2`). Each node wraps an Ash changeset or query for a specific **action** (create/update/destroy/read). Nested forms are **inferred automatically** from `manage_relationship` arguments, embedded resources and union types. It stores raw params and touched keys, tracks `submitted_once?`/`just_submitted?`/`changed?`, addresses subforms by **path** (`[:locations, 0]` or `"form[locations][0]"`), and implements `Phoenix.HTML.FormData`, so the standard `<.form>`/`<.inputs_for>`/`<.input>` work unchanged. This is the opposite of Ecto's "single use, rebuild every event" stance.

### Cited Findings

**Lifecycle (moduledoc):** "1. Create a form with `AshPhoenix.Form` 2. Render the form with `Phoenix.Component.form` … 3. To validate the form (e.g with `phx-change` for liveview), pass the submitted params to `AshPhoenix.Form.validate/3` 4. On form submission, pass the params to `AshPhoenix.Form.submit/2` 5. On success, use the result to redirect or assign. On failure, reassign the provided form." State keys: "`submitted_once?` - If the form has ever been submitted. Useful for not showing any errors on the first attempt to fill out a form"; "`just_submitted?`"; "`.changed?`"; "`.touched_forms` - A MapSet containing all keys in the form that have been modified. When submitting a form, only these keys are included in the parameters." — [AshPhoenix.Form source](https://github.com/ash-project/ash_phoenix/blob/main/lib/ash_phoenix/form/form.ex)

**Struct:** `resource, action, type, params, source, name, data, form_keys, forms, domain, method, submit_errors, opts, id, transform_errors, post_process_errors, original_data, transform_params, prepare_params, prepare_source, raw_params, any_removed?, added?, changed?, touched_forms, valid?, errors (bool), submitted_once?, just_submitted?` — [AshPhoenix.Form source](https://github.com/ash-project/ash_phoenix/blob/main/lib/ash_phoenix/form/form.ex)

**Typical LiveView usage (code-interface generated `form_to_*`):**
```elixir
def mount(_params, _session, socket) do
  {:ok, assign(socket, form: MyApp.Accounts.form_to_register_with_password() |> to_form())}
end

def handle_event("validate", %{"form" => params}, socket) do
  {:noreply, assign(socket, :form, AshPhoenix.Form.validate(socket.assigns.form, params))}
end

def handle_event("submit", %{"form" => params}, socket) do
  case AshPhoenix.Form.submit(socket.assigns.form, params: params) do
    {:ok, _user} -> {:noreply, socket |> put_flash(:success, "User registered successfully") |> push_navigate(to: ~p"/")}
    {:error, form} -> {:noreply, socket |> put_flash(:error, "Something went wrong") |> assign(:form, form)}
  end
end
```
— [AshPhoenix.Form moduledoc](https://github.com/ash-project/ash_phoenix/blob/main/lib/ash_phoenix/form/form.ex)

**Auto-inferred nested forms from the action:**
```elixir
create :create do
  accept [:name]
  argument :locations, {:array, :map}
  change manage_relationship(:locations, type: :create)
end
```
"`AshPhoenix.Form` automatically infers what "nested forms" are available, based on introspecting actions which use `change manage_relationship`." Turn off with `forms: [auto?: false]`, or configure manually:
```elixir
AshPhoenix.Form.for_create(MyApp.Operations.Business, :create,
  forms: [locations: [type: :list, resource: MyApp.Operations.Location, create_action: :create]])
```
For updates, relationships must be loaded first (`Ash.load!(business, :locations)`) — [ash_phoenix nested-forms guide](https://github.com/ash-project/ash_phoenix/blob/main/documentation/topics/nested-forms.md)

**Add/remove/sort, two styles each (params-based and function-based):**
```heex
<!-- add via hidden checkbox: value "start" | "end" | index -->
<label><input type="checkbox" name={"#{@form.name}[_add_locations]"} value="end" class="hidden" /><.icon name="hero-plus" /></label>
<!-- drop -->
<input type="checkbox" name={"#{@form.name}[_drop_locations][]"} value={location.index} class="hidden" />
<!-- sort (e.g. with sortable.js) -->
<input type="hidden" name={"#{@form.name}[_sort_locations][]"} value={location_form.index} />
```
```elixir
def handle_event("add-form", %{"path" => path}, socket) do
  form = AshPhoenix.Form.add_form(socket.assigns.form, path, params: %{address: "Put your address here!"})
  {:noreply, assign(socket, :form, form)}
end
def handle_event("remove-form", %{"path" => path}, socket) do
  {:noreply, assign(socket, :form, AshPhoenix.Form.remove_form(socket.assigns.form, path))}
end
def handle_event("move-up", %{"path" => p}, socket), do: {:noreply, assign(socket, form: AshPhoenix.Form.sort_forms(socket, p, :decrement))}
```
Paths: "By always using a path "relative" to the root form, we can handle cases where we are adding a form to a multiply-nested form. So the path could be something like `locations[0][addresses][1]`." The `order_is_key: :position` option on `manage_relationship` writes list order into each item — [ash_phoenix nested-forms guide](https://github.com/ash-project/ash_phoenix/blob/main/documentation/topics/nested-forms.md). `add_form` path "can be one of two things: 1. A list of atoms and integers … `[:posts, 0, :comments]` … 2. The html name of the form, e.g `form[posts][0][comments]`"; options `prepend`, `params`, `validate?`, `validate_opts`, `type` (`:read|:create|:update|:destroy`, with a hidden `_form_type`), `data` — [AshPhoenix.Form source](https://github.com/ash-project/ash_phoenix/blob/main/lib/ash_phoenix/form/form.ex)

**Other API:** `validate(form, params, errors: true, target: ..., only_touched?: false)` ("Set to false to hide errors after validation"; `target` is "The `_target` param provided by phoenix. Used to support the `only_touched?` option"); `update_params(form, fun)` for non-input events (e.g. button picks a time slot); `params(form)` returns "the parameters from the form that would be submitted to the action"; `errors(form, format: :simple | :raw | :plaintext, for_path: [...] | :all)`, where `:all` returns `%{[:comments, 0] => [body: "is invalid"], ...}`; `add_error`, `touch`, `ignore` (`_ignore` param), `get_form`, `has_form?`, `update_form`, `hidden_fields` (adds `_form_type`, `_touched`, `_union_type`, pkeys), `transform_errors`/`post_process_errors` (map an error on `:amount` to composite sub-inputs) — [AshPhoenix.Form source](https://github.com/ash-project/ash_phoenix/blob/main/lib/ash_phoenix/form/form.ex)

**`sparse?` nested lists:** normally, leaving some forms out of the params removes them; with `sparse?: true` "the form actually ignores the *index* provided … and instead uses the primary key e.g `comments[0][id]` to match which form is being updated. This prevents you from having to find the index of the specific item you want to update. Which could be very gnarly on deeply nested forms." — [AshPhoenix.Form source](https://github.com/ash-project/ash_phoenix/blob/main/lib/ash_phoenix/form/form.ex)

**History / why a separate abstraction.** Before v0.5, ash_phoenix implemented forms directly on `Ash.Changeset` (helpers like `hide_errors/1` stored a flag in changeset context; "These will be deprecated at some point, once the work on `AshPhoenix.Form` is complete") — [ash_phoenix v0.4.24 lib/ash_phoenix.ex](https://github.com/ash-project/ash_phoenix/blob/v0.4.24/lib/ash_phoenix.ex). v0.5.0 (2021-07-18) "Breaking Changes: refactor forms", "refactor forms with new data structure `AshPhoenix.Form`", "first edition of auto forms" — [ash_phoenix v0.5.0 CHANGELOG](https://github.com/ash-project/ash_phoenix/blob/v0.5.0/CHANGELOG.md). The v0.5.0 moduledoc states: "`AshPhoenix.Form` (unlike ecto changeset based forms) expects to be reused throughout the lifecycle of the liveview", and nested forms had to be configured explicitly via `forms:` (auto-inference came later) — [ash_phoenix v0.5.0 form.ex](https://github.com/ash-project/ash_phoenix/blob/v0.5.0/lib/ash_phoenix/form/form.ex). The hidden-checkbox `_add_`/`_drop_`/`_sort_` features were announced later ("Use hidden checkboxes to automatically add, remove and reorder nested forms!") — [Elixir Forum Ash News: new guide on nested forms](https://elixirforum.com/t/new-tools-and-a-new-guide-on-nested-forms-with-ashphoenix-form/68654) (search snippet only)

**Known sharp edge:** nested forms are only auto-built when `manage_relationship` is declared on the action itself — [ash_phoenix issue #382](https://github.com/ash-project/ash_phoenix/issues/382) (title only: "nested forms are not built unless manage_relationship is explicitly defined in the action")

### Inferences
- **Why Ash needed its own abstraction (inference; no first-party rationale document was found):** in Ash, related data for an action arrives as *arguments* processed by `manage_relationship` when the action runs, so an `Ash.Changeset` doesn't hold a tree of child changesets the way `cast_assoc` produces one. A form layer that needs per-row errors, add/remove, and `inputs_for` therefore has to keep its own tree of subforms (each with its own changeset, params, and path). Once it has that tree, it's natural to make it long-lived and stateful (touched sets, submitted flags, path-addressed mutations).
- **Trade-off vs Ecto:** Ash gives more out of the box (auto nested forms from action metadata, path-addressed ops, touched-only params, union handling, errors by path), but it's more stateful and its API surface is large (the form.ex module alone defines ~80 distinct `def` names including callbacks/helpers, plus many options). Ecto+Phoenix is a smaller, more functional core (rebuild from `data + params` each event) where nesting is "just" `cast_embed` + `inputs_for`.
- **For pyview:** Ash's **path-addressed operations** (`add_form(form, "user[addresses][0][phones]")`) and **`errors(for_path=:all)`** are worth copying as helpers even if the core stays Ecto-like. Pydantic models could play the role of Ash action metadata: introspecting a model's `list[SubModel]`, `SubModel | None` and discriminated-union fields gives "auto nested forms" for free, which is the pydantic analogue of `manage_relationship` inference.

### Gaps
- No explicit design-rationale write-up by Zach Daniel was reachable (Elixir Forum/ash-hq blocked or snippet-only). The Phoenix.HTML.FormData implementation file for `AshPhoenix.Form` wasn't located under the guessed paths, so how Ash gates error display at render time (the `errors` boolean vs `submitted_once?`) was only read from option docs.

---

## 9. Pain points and community criticism

### Takeaway
The recurring pain is concentrated in **nested forms** (hidden-input conventions, `on_replace`, empty-list encoding, replaced records, IDs) and **error-display timing** (the `phx-feedback-for` → `used_input?` migration and its edge cases: selects/radios, hidden-input widgets, composite inputs, custom password fields). A third theme is **leaky `.value`**: a field's value can be a typed value, a raw string, a struct, or a changeset.

### Cited Findings

**Leaky `form[:field].value` (official warning):** "an `:integer` field may either contain integer values, but it may also hold a string, if the form has been submitted. This is particularly noticeable when using `inputs_for`. Accessing the `.value` of a nested field may either return a struct, a changeset, or raw parameters sent by the client (when using `drop_param`). This makes the `form[:field].value` impractical for deriving or computing other properties." Recommended fix: compute derived values from the changeset in `handle_event` (via `get_field`/`get_embed`) or put them in a `:virtual` field — [Phoenix.Component.inputs_for/1 docs](https://github.com/phoenixframework/phoenix_live_view/blob/main/lib/phoenix_component.ex)

**`phx-feedback-for` limitations (pre-1.0):** a custom composite `<.input type="money">` (amount + currency) couldn't hide errors correctly because "`phx-feedback-for` … expects a single input name, but composite components contain multiple inputs for one form field" (LV 0.20.2, Dec 2023; closed under the v1.0 milestone) — [issue #2968](https://github.com/phoenixframework/phoenix_live_view/issues/2968). `used_input?` handles this by treating a nested param map as used if any sub-key is used — [Phoenix.Component](https://github.com/phoenixframework/phoenix_live_view/blob/main/lib/phoenix_component.ex)

**`used_input?` edge cases after 1.0:**
- Unselected `<select>`/radio groups are absent from `FormData`, so there's neither a value nor an `_unused_` key, and `used_input?` never returns true, so required-field errors never show even after submit (LV 1.0.0, Dec 2024) — [issue #3580](https://github.com/phoenixframework/phoenix_live_view/issues/3580)
- JS widgets (e.g. flatpickr) that hide the real input as `type="hidden"` never get `_unused_` markers, so they look "used" immediately and show errors early — [issue #3620](https://github.com/phoenixframework/phoenix_live_view/issues/3620)
- Multi-select + companion empty hidden input (`user[addresses]` vs `user[addresses][]`) are treated as different fields, so the field is marked used — [issue #3577](https://github.com/phoenixframework/phoenix_live_view/issues/3577) (addressed by `phx-no-unused-field` in LV 1.2.0-rc.0 — [LV v1.2 CHANGELOG](https://github.com/phoenixframework/phoenix_live_view/blob/v1.2/CHANGELOG.md))
- `used_input?` returned false when a param value was a struct (e.g. DateTime), fixed in 1.0.10 (2025-04-17) — [issue #3757](https://github.com/phoenixframework/phoenix_live_view/issues/3757); [LV v1.0 CHANGELOG](https://github.com/phoenixframework/phoenix_live_view/blob/v1.0/CHANGELOG.md)
- phx.gen.auth settings: the "current password" field isn't in the changeset, so its errors didn't show under `used_input?` — [issue #3235](https://github.com/phoenixframework/phoenix_live_view/issues/3235); the 1.0 changelog has a dedicated migration note for the password case — [LV v1.0 CHANGELOG](https://github.com/phoenixframework/phoenix_live_view/blob/v1.0/CHANGELOG.md)
- Nested form fields not displaying errors (1.0.0-rc.7, Nov 2024) — [issue #3493](https://github.com/phoenixframework/phoenix_live_view/issues/3493)

**Nested-form friction:**
- "`inputs_for` omits associations that have been marked as `:replace`. If you remove every association of a collection, any other change to the form will cause all of the associations to be restored, as the absence of data for that field clears out the previous changes" (May 2023). This is the problem the always-present empty hidden `*_drop[]` input solves — [issue #2616](https://github.com/phoenixframework/phoenix_live_view/issues/2616); [Phoenix.Component docs](https://github.com/phoenixframework/phoenix_live_view/blob/main/lib/phoenix_component.ex)
- A user replicating the ElixirConf keynote demo got no nested rows and couldn't add/remove (their `validate` handler was a no-op that never re-cast params) — [issue #2646](https://github.com/phoenixframework/phoenix_live_view/issues/2646)
- `_persistent_id` initially produced ids like `#0_domain` (invalid CSS selectors) — [issue #2626](https://github.com/phoenixframework/phoenix_live_view/issues/2626); third-party `FormData` impls found `inputs_for` overriding their `index`/`id`; the reporter "don't know … what the purpose of the `_persistent_id` is" and had to seed `params: %{"_persistent_id" => index}` as a workaround "relying on an internal implementation detail" (Feb 2025), leading to `skip_persistent_id` in 1.0.6 — [issue #3673](https://github.com/phoenixframework/phoenix_live_view/issues/3673); [LV v1.0 CHANGELOG](https://github.com/phoenixframework/phoenix_live_view/blob/v1.0/CHANGELOG.md)
- Empty collections can't be expressed in urlencoded forms; old code used sentinel params (`"cities" => "[]"`) — [LostKobrakai gist](https://gist.github.com/LostKobrakai/ce5385bd118189a24d60893188612de9)
- Ash: nested forms silently not built unless `manage_relationship` is on the action — [ash_phoenix issue #382](https://github.com/ash-project/ash_phoenix/issues/382)

**Other lifecycle gotchas:** forms without `id` don't recover (now a test warning in 1.2) — [LV v1.2 CHANGELOG](https://github.com/phoenixframework/phoenix_live_view/blob/v1.2/CHANGELOG.md); `preventDefault()` in a submit hook "is not respected by LiveView", and `stopPropagation()` caused a full-page GET navigation (LV 1.0.11, May 2025), which later got a documented "Preventing form submission with JavaScript" recipe — [issue #3796](https://github.com/phoenixframework/phoenix_live_view/issues/3796); [form-bindings guide](https://github.com/phoenixframework/phoenix_live_view/blob/main/guides/client/form-bindings.md); `form="..."` + `phx-debounce` JS errors, fixed 1.1.20 (2026-01) — [issue #4102](https://github.com/phoenixframework/phoenix_live_view/issues/4102); [LV v1.1 CHANGELOG](https://github.com/phoenixframework/phoenix_live_view/blob/v1.1/CHANGELOG.md)

**Boilerplate:** every LiveView form repeats the same `validate`/`save` + `to_form(changeset, action: :validate)` + `{:error, changeset} -> assign(form: to_form(changeset))` shape (compare the generated template in §5 and the guide in §4) — [phx.gen.live template](https://github.com/phoenixframework/phoenix/blob/v1.8/priv/templates/phx.gen.live/form.ex.eex); the Ecto guide recommends separate form schemas when UI ≠ DB, which adds a mapping layer — [Ecto guide](https://github.com/elixir-ecto/ecto/blob/master/guides/howtos/Data%20mapping%20and%20validation.md)

### Inferences
- Most of the pain comes from **conventions encoded in magic parameter names** (`_unused_*`, `_persistent_id`, `*_sort[]`, `*_drop[]`, `_add_*`, `_union_type`, `__type__`, hidden `id`) that users must hand-write correctly in templates. A Python port can keep the wire protocol but **generate these inputs via helpers**, so users never type `name="list[notifications_delete][]"`.
- The used-input heuristic is fundamentally client-DOM-based, so it fails for inputs absent from `FormData` (unselected selects/radios, unchecked checkboxes without a hidden twin) and for hidden proxy inputs. A port should (a) always emit hidden "empty" twins for select/radio/checkbox groups and (b) provide a per-input opt-out/opt-in like `phx-no-unused-field`. It might also consider treating "form submitted at least once" (Ash's `submitted_once?`) as an override that shows all errors.
- "Value may be a string or a typed value" is avoidable in Python by exposing both `field.value` (a display string for the input) and `field.typed_value`/`changeset.get_field()` (parsed), instead of one ambiguous `value`.

### Gaps
- Elixir Forum threads (the richest source of qualitative complaints) were blocked; opinions here come only from GitHub issue bodies and official docs, so the "community sentiment" picture is partial. Couldn't read maintainer replies on the issues listed.

---

## 10. Newer developments (2024–2026): LiveView 1.0/1.1/1.2, Phoenix 1.8, Ecto 3.13/3.14

### Takeaway
Forms have been **stable** since LiveView 1.0 (Dec 2024). Later releases added ergonomics around forms rather than new form primitives: `phx-no-unused-field`, missing-form-id test warnings, `phx-patch-focused`, keyed comprehensions (`:key`) and change-tracked `:for`, portals, colocated hooks/CSS. Phoenix 1.8 (Aug 2025) slimmed generated components (daisyUI, no `simple_form`, scopes). Ecto added `reorder_assoc/2` and configurable trimming (3.14, May 2026).

### Cited Findings
- **LiveView 1.0.0** released 2024-12-03 (rc.0 2024-05-08): removed `phx-feedback-for`, introduced `used_input?` / `_unused_` params — [LV v1.0 CHANGELOG](https://github.com/phoenixframework/phoenix_live_view/blob/v1.0/CHANGELOG.md)
- **LiveView 1.1.0** released 2025-07-30 (rc.0 2025-06-17; Phoenix 1.8.0 "Use LiveView 1.1 release in generated code"): **colocated hooks** (`<script :type={Phoenix.LiveView.ColocatedHook} name=".PhoneNumber">`, requires Phoenix 1.8+, extracted to `phoenix-colocated/…` and imported in `app.js`), **change tracking in comprehensions** with a new `:key` attribute (`<li :for={item <- @items} :key={item.id}>`), **`<.portal>`**, `JS.ignore_attributes`, LazyHTML replacing Floki in tests — [LV v1.1 CHANGELOG](https://github.com/phoenixframework/phoenix_live_view/blob/v1.1/CHANGELOG.md); [Phoenix v1.8 CHANGELOG](https://github.com/phoenixframework/phoenix/blob/v1.8/CHANGELOG.md). Form-related 1.1.x fixes: "Ensure form recovery respects fieldsets" (1.1.3), "Fix form recovery not working when form is teleported" (1.1.14), "Fix form recovery not sending elements with `form="..."` attribute when using Firefox" (1.1.15), "Include form values from DOM in `Phoenix.LiveViewTest.submit_form/2`" (1.1.9) — [LV v1.1 CHANGELOG](https://github.com/phoenixframework/phoenix_live_view/blob/v1.1/CHANGELOG.md)
- **LiveView 1.2.0** released 2026-06-10 (rc.0 2026-04-23): `Phoenix.LiveView.ColocatedCSS`; `phx-no-unused-field`; configurable `:test_warnings` incl. missing form `id` warnings; `phx-patch-focused` (1.2.8). Latest seen: v1.2.12 (2026-09-16); `main` is v1.3-dev ("Empty so far") — [LV v1.2 CHANGELOG](https://github.com/phoenixframework/phoenix_live_view/blob/v1.2/CHANGELOG.md); [LV main CHANGELOG](https://github.com/phoenixframework/phoenix_live_view/blob/main/CHANGELOG.md)
- **Phoenix 1.8.0** (2025-08-05): daisyUI, single root layout, "Simplify core components and live generators", magic-link auth, **scopes** in generators (so generated `change_post(scope, post, params)` takes a scope), `AGENTS.md`/usage_rules generation. `main` is now 1.9-dev — [Phoenix v1.8 CHANGELOG](https://github.com/phoenixframework/phoenix/blob/v1.8/CHANGELOG.md); [phx.gen.live form template](https://github.com/phoenixframework/phoenix/blob/v1.8/priv/templates/phx.gen.live/form.ex.eex)
- **Ecto 3.14.0** (2026-05-19): `Ecto.Changeset.reorder_assoc/2`; `Ecto.Type.trim/2` + `:trim_values` cast option. 3.14.2 dated 2026-08-14 — [Ecto CHANGELOG](https://github.com/elixir-ecto/ecto/blob/master/CHANGELOG.md)
- **ash_phoenix**: current docs describe `AshPhoenix.Form.sort_forms/3`, `update_params/2`, `raw_errors/2`, union forms, `mix ash_phoenix.gen.live` — [ash_phoenix CHANGELOG](https://github.com/ash-project/ash_phoenix/blob/main/CHANGELOG.md); [getting-started guide](https://github.com/ash-project/ash_phoenix/blob/main/documentation/tutorials/getting-started-with-ash-and-phoenix.md)

### Inferences
- No new "form object" abstraction has appeared in core Phoenix through 2026; the core team's direction is to keep forms as `changeset → to_form → function components` and fix edges. For pyview, that means the Ecto/Phoenix model described above is a stable target, not a moving one.
- Keyed comprehensions (`:key`) matter for dynamic rows: they let LiveView send minimal diffs when rows are inserted, reordered or removed. A pyview port with dynamic `inputs_for` should key rows by the persistent id.

### Gaps
- No evidence found of new form features in the unreleased LV 1.3 / Phoenix 1.9 branches (their changelogs are near-empty).
