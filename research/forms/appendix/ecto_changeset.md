# Ecto.Changeset (Elixir) — the changeset abstraction — versions researched, date

Researched 2026-09-12 against cloned sources: **ecto** master `e1d536a` (2026-09-11, `@version "3.15.0-dev"`; latest release v3.14.2, 2026-08-14), **phoenix_ecto** 4.7.0 (`lib/phoenix_ecto/html.ex`, the `Phoenix.HTML.FormData` impl for changesets), **phoenix_live_view** master 1.2.11 (`lib/phoenix_component.ex`: `to_form/2`, `used_input?/1`, `inputs_for/1`), **phoenix_html** 4.3.0 (`Form`/`FormField` structs), **phoenix** master 1.9.0-dev (`phx.gen.live` templates, `core_components.ex.eex`) plus the v1.7.10 `core_components.ex` for the `phx-feedback-for` era that pyview's LV 0.20.17 client still speaks. No Elixir runtime was available in the sandbox, so "outputs" below are copied from Ecto's own test suite / doctests, not run by me.

## TL;DR (5-8 bullets)

- A changeset is a **pure data structure** (`%Ecto.Changeset{data, params, changes, errors, valid?, action, types, required, empty_values, ...}`) built by a **pipeline of plain functions** (`cast |> validate_required |> validate_format |> cast_embed |> unique_constraint`). Nothing about it knows HTML; the form layer is a separate protocol (`Phoenix.HTML.FormData`) implemented for changesets in phoenix_ecto.
- Three buckets of state: `data` (the original struct/map), `params` (raw external input, string keys, **kept verbatim even for non-permitted keys**), `changes` (only the permitted, type-cast values that differ from `data`). Rendering reads `changes → params → data` in that order, which is how a badly typed value is re-displayed exactly as the user typed it.
- `cast/4` does **filtering + type casting + empty-value normalisation** only; validations are separate functions that run **only on non-nil changes** (`validate_change/3`), except `validate_required` which looks at `get_field` (changes-then-data). Errors are `[{field, {"msg with %{count}", [count: 3, validation: :length, kind: :min, ...]}}]` — a template plus params, translated late (Gettext `dngettext` in Phoenix's `translate_error/1`).
- **Error visibility is gated by `changeset.action`**: `form_for_errors/2` returns `[]` when action is `nil`/`:ignore`. `Repo.insert/update` set it on failure; for non-DB forms you set it yourself via `to_form(changeset, action: :validate)` or `apply_action/2`. Per-field "touched" is handled *outside* the changeset: LV 1.x sends `_unused_<field>` sibling params and `used_input?/1` filters; LV 0.20 (pyview's client) used the client-side `phx-feedback-for` / `phx-no-feedback` mechanism.
- Nested data: `cast_embed/3`/`cast_assoc/3` recurse into child `changeset/2` functions, match incoming children to existing ones **by primary key** (hidden `id` inputs), accept lists or `%{"0" => ..., "1" => ...}` index-keyed maps, and support `sort_param`/`drop_param` (Ecto 3.10, 2023) so add/remove/reorder needs zero JS — just named buttons/hidden inputs. LiveView's `inputs_for` injects a `_persistent_id` hidden input per child to keep DOM ids stable.
- Constraints (`unique_constraint` etc.) are *declarations* that let the Repo translate a database exception into a field error **after the fact**; unmatched DB errors raise `Ecto.ConstraintError`. `unsafe_validate_unique` is the eager, racy pre-check.
- Non-DB forms are first-class: `embedded_schema` modules and schemaless `{data, types}` tuples get the whole API (except constraints, which need a table source).
- Chronic pain points (all with citations below): the `action` gate confuses beginners; `on_replace: :raise` default trips everyone doing nested forms; `form[:field].value` is polymorphic (struct / changeset / raw params); nested error shapes are inconsistent; the sort-order doc contradicts the code.

## Mental model & core abstractions

**The struct** (`lib/ecto/changeset.ex`, `defstruct`):

```elixir
defstruct valid?: false, data: nil, params: nil, changes: %{}, errors: [],
          validations: [], required: [], prepare: [], constraints: [], filters: %{},
          action: nil, types: %{}, empty_values: [""], repo: nil, repo_opts: []

@type error :: {String.t(), Keyword.t()}
@type action :: nil | :insert | :update | :delete | :replace | :ignore | atom
@type types :: %{atom => Ecto.Type.t() | {:assoc, term()} | {:embed, term()}}
```

Public fields per the moduledoc: `valid?`, `data`, `params`, `changes`, `errors`, `required`, `action`, `types`, `empty_values`, `repo`, `repo_opts`; private: `validations`, `constraints`, `filters`, `prepare`.

**External vs internal data.** The moduledoc frames the whole design around this: `cast/4` is for *external* params (string-keyed maps, untrusted, needing type conversion); `change/2` and `put_change/3` are for *internal* data (atom keys/structs, already typed, no validation). "This duality allows you to track the nature of your data: if you have structs or maps with atom keys, it means the data has been parsed/validated."

**`types`** is the one thing every changeset must have. For an `Ecto.Schema` struct it comes from `module.__changeset__()`; for schemaless use you pass `{data, types}` explicitly. Relations appear in `types` as `{:embed, %Ecto.Embedded{}}` / `{:assoc, %Ecto.Association.Has{}}` and are refused by `cast/4` ("casting embeds with cast/4 for :posts field is not supported, use cast_embed/3 instead").

**Validations vs constraints** (moduledoc): validations run immediately, in memory, on the data in the changeset *at the time the function is called*; constraints run in the database and are only checked if all validations pass. `unsafe_*` prefixed functions are validations that hit the DB but are racy.

**`action`.** A free atom. `Ecto.Repo.insert/update/delete` set it on the returned `{:error, changeset}`; `apply_action(changeset, action)` emulates that for non-persisted data: `{:ok, apply_changes(cs)}` if valid, else `{:error, %{cs | action: action}}`. The docs explicitly say "The action may be any atom" and Phoenix docs recommend `:validate` "to avoid giving the impression that a database operation has actually been attempted".

**The pipeline convention** — every schema module exposes `changeset/2` (this name is *load-bearing*: `cast_embed`/`cast_assoc` default `:with` to `Module.changeset/2`, see `Relation.on_cast_default/1`, which raises a helpful ArgumentError if it is missing):

```elixir
# lib/ecto/changeset.ex moduledoc
defmodule User do
  use Ecto.Schema
  import Ecto.Changeset

  schema "users" do
    field :name
    field :email
    field :age, :integer
  end

  def changeset(user, params \\ %{}) do
    user
    |> cast(params, [:name, :email, :age])
    |> validate_required([:name, :email])
    |> validate_format(:email, ~r/@/)
    |> validate_inclusion(:age, 18..100)
    |> unique_constraint(:email)
  end
end

changeset = User.changeset(%User{}, %{age: 0, email: "mary@example.com"})
{:error, changeset} = Repo.insert(changeset)
changeset.errors #=> [age: {"is invalid", []}, name: {"can't be blank", []}]
```

## Data in: naming conventions, parsing, coercion, nested/list handling

**Signature:** `cast(data, params, permitted, opts \\ [])` where `data` is a struct, an existing changeset, or `{data, types}`; `params` is a map with *either* string or atom keys (mixed keys raise `Ecto.CastError`; the check only inspects the first key for speed — see `convert_params/1`); `permitted` is a list of atoms (`cast_key/1` raises on anything else). Unknown fields raise `ArgumentError` listing "The known fields are: ...".

**Options** (doc + `cast/7`): `:trim_values` (2-arity fn, default `&Ecto.Type.trim/2` — trims *leading* whitespace of strings only: `def trim(type, value) when is_binary(value) and type != :binary, do: String.trim_leading(value)`), `:empty_values` (default `[""]`, applied after trimming, so whitespace-only strings are empty since 3.10), `:force_changes` (include values equal to current data), `:message` (`fn field, meta -> String.t() | nil` to override the cast failure message per field/type).

**Per-field algorithm** (`process_param/9` + `cast_field/9`, verified):

1. Look up `params[Atom.to_string(key)]`; absent → `:missing` (no change, no error).
2. `filter_values`: if `type` is `{:array, t}`, drop every element that is empty, then test the whole list; if the value is empty, substitute the **struct default** (`Map.get(struct.__struct__(), key)`, i.e. `nil` unless the schema field declares `default:`; always `nil` for schemaless).
3. `Ecto.Type.cast(type, value)`: `{:ok, v}` → skip if `Ecto.Type.equal?(type, current, v)` and not forced, else record in `changes`; `:error` → `{"is invalid", [type: type, validation: :cast]}`; `{:error, custom}` (from custom types) merges `custom` into the metadata, with `:message` popped as the message.
4. `valid?` becomes `false` on any error; `errors` are *prepended* (most recent first), later reversed once at the end of `cast`.

**Coercion rules worth stealing** (`lib/ecto/type.ex`): `cast_boolean/1` accepts `"true" | "1" | true` → `true`, `"false" | "0" | false` → `false`, anything else `:error`; integers/floats/decimals parse from strings; `:date`/`:time`/`:naive_datetime`/`:utc_datetime` parse ISO strings and also `%{"year" => .., "month" => ..}` maps (the select-based date inputs). `Ecto.Enum` casts strings *or* atoms to atoms. Because an empty string becomes `nil`, the canonical checkbox markup (Phoenix `core_components`) is a hidden `value="false"` followed by the checkbox `value="true"` under the same name so an unticked box submits `"false"` rather than nothing.

**Nested params shape.** Phoenix decodes bracket names with `Plug.Conn.Query.decode/1` (LiveView calls it in `lib/phoenix_live_view/channel.ex:912`): `user[addresses][0][street]=x` → `%{"user" => %{"addresses" => %{"0" => %{"street" => "x"}}}}`; `tags[]=a&tags[]=b` → list. The Plug docs warn that `user[][foo]` (nesting inside `[]`) is "ambiguous and unspecified"; explicit indexes are the supported form. `cast_relation/4` accepts either a **list** of maps or an **integer-keyed map** for `:many` relations; `cast_params(:many, value, sort, drop)` sorts map keys as integers (`key_as_int/1`), so `%{"0" => ..., "10" => ..., "2" => ...}` orders numerically, not lexically. `_target` arrives as a list keyspace: `%{"_target" => ["user", "username"], "user" => %{"username" => "Name"}}` (form-bindings guide).

**`changeset.params` keeps everything.** Only permitted keys become `changes`, but `params` is the whole map. This is deliberately exploited by the form layer: `_persistent_id`, `_unused_x`, `password_confirmation` (`validate_confirmation` reads `params["#{field}_confirmation"]`, never a schema field) and `terms_of_service` (`validate_acceptance` casts `params[field]` with `Ecto.Type.cast(:boolean, ...)`) all live in `params` without polluting the schema.

**Composing casts.** `cast(changeset, more_params, [:body])` merges params shallowly ("**not deep-merged**"), later params win, errors/changes accumulate — the doc shows `new_changeset.params #=> %{"title" => "Hello", "body" => "World"}`.

**Schemaless / non-DB forms** (moduledoc + `guides/howtos/Data mapping and validation.md`):

```elixir
# schemaless: plain map + explicit types
data  = %{}
types = %{name: :string, email: :string, age: :integer,
          role: Ecto.ParameterizedType.init(Ecto.Enum, values: [:reader, :editor, :admin])}
changeset =
  {data, types}
  |> Ecto.Changeset.cast(params, Map.keys(types))
  |> Ecto.Changeset.validate_required([:name, :email])
  |> Ecto.Changeset.validate_length(:name, min: 2)

# embedded_schema: a struct that is never persisted, used to shape a UI
defmodule Registration do
  use Ecto.Schema
  embedded_schema do
    field :first_name
    field :last_name
    field :email
  end
end
changeset = %Registration{} |> Ecto.Changeset.cast(params["sign_up"], [:first_name, :last_name, :email]) |> validate_required(...)
if changeset.valid? do
  registration = Ecto.Changeset.apply_changes(changeset)   # -> %Registration{}
else
  {:error, %{changeset | action: :registration}}            # "Annotate the action so the UI shows errors"
end
```

The guide's thesis: split "Database <-> Ecto schema <-> Forms / API" into two mappings when the UI shape differs from storage; `embedded_schema` is the tool for "here is the shape of my form".

## Validation & error model (structure, codes vs messages, params, i18n, cross-field, when validation runs)

**Error structure.** `errors :: [{atom, {String.t(), Keyword.t()}}]`. Real shapes from `test/ecto/changeset_test.exs`:

```elixir
[body: {"is invalid", [type: :string, validation: :cast]}]
[title: {"can't be blank", [validation: :required]}]
[title: {"has invalid format", [validation: :format]}]
[title: {"is invalid", [validation: :inclusion, enum: ~w(world)]}]
[title: {"should be at least %{count} character(s)", [count: 6, validation: :length, kind: :min, type: :string]}]
[posts: {"is invalid", [validation: :embed, type: {:array, :map}]}]          # embedded_test.exs
[email: {"has already been taken", [constraint: :unique, constraint_name: "users_email_index"]}]  # repo/schema.ex constraints_to_errors/3
```

So the "code" is the `:validation`/`:constraint` key, the human text is a template, and every number used in the template is also in the keyword list (`%{count}`, `%{number}`). `add_error(cs, :tags, "tag '%{val}' is too short", val: "x")` is the user-level way to add a templated error. Every `validate_*` accepts `:message` as a string **or** `{msg, extra_opts}` tuple (`message/4` merges extra opts into the metadata) so custom messages keep the i18n params.

**Translation happens at render time** (Phoenix installer `core_components.ex.eex`):

```elixir
def translate_error({msg, opts}) do
  if count = opts[:count] do
    Gettext.dngettext(MyAppWeb.Gettext, "errors", msg, msg, count, opts)
  else
    Gettext.dgettext(MyAppWeb.Gettext, "errors", msg, opts)
  end
end
# non-gettext fallback in the same template:
Enum.reduce(opts, msg, fn {key, value}, acc ->
  String.replace(acc, "%{#{key}}", fn _ -> to_string(value) end)
end)
```

The generated `priv/gettext/errors.pot` ships all default Ecto messages ("can't be blank", "should be at least %{count} character(s)" ...), so plural rules are handled by Gettext, not by Ecto.

**When validations run.** `validate_change/3` (the primitive all `validate_*` are built on): "It invokes the validator function to perform the validation **only if a change for the given field exists and the change value is not nil**". Consequences: validations never re-check untouched `data`; `validate_required` is the exception — it uses `get_field/2` (changes, then data), treats `nil` or any `empty_values` member as missing, **drops the field from `changes`**, records it in `changeset.required`, and skips fields that already carry an error. `validate_change/4` additionally records `{field, metadata}` in `changeset.validations`, which is pure reflection — phoenix_ecto's `input_validations/3` turns `{:length, min: 3, max: 100}` into `minlength="3" maxlength="100"` and `{:number, less_than: 10}` into `max="9" step="1"` HTML attributes, and `required in changeset.required` into `required`.

**Built-ins** (all `(changeset, field, ..., opts)`; `:message` everywhere): `validate_required(cs, fields_or_field, opts)`; `validate_format(cs, field, ~r/regex/, opts)` (raises if the change is not a string); `validate_inclusion(cs, field, enum, opts)`, `validate_subset` (each element of a list in enum), `validate_exclusion`; `validate_length(cs, field, is:/min:/max:/count: :codepoints|:graphemes|:bytes)` — strings, binaries, lists and maps all supported with different templates ("item(s)" vs "character(s)"); `validate_number(cs, field, less_than:/greater_than:/less_than_or_equal_to:/greater_than_or_equal_to:/equal_to:/not_equal_to:)` with `%{number}`; `validate_confirmation(cs, :password, required: true)` (compares `params["password"]` with `params["password_confirmation"]`, error keyed on `:password_confirmation`; *silently passes* if the confirmation param is absent unless `required: true` — by design, so APIs without the field aren't blocked); `validate_acceptance(cs, :terms)`; `unsafe_validate_unique(cs, fields, repo, opts)`.

**Custom / cross-field** — `validate_change/3` returns a list of errors that may target *other* fields; `field_missing?/2` and `get_field/2` support "at least one of" rules:

```elixir
# lib/ecto/changeset.ex docs
changeset = validate_change(changeset, :title, fn :title, title ->
  if title == "foo", do: [title: {"cannot be foo", additional: "info"}], else: []
end)

changeset = cast(%Post{}, %{color: "Red"}, [:color])
missing = Enum.filter([:title, :body], &field_missing?(changeset, &1))
changeset = if match?([_, _], missing),
  do: add_error(changeset, :title, "at least one of `:title` or `:body` must be present"),
  else: changeset
```

**Nested errors.** Child changesets live inside `changes` (e.g. `changes.posts` is a list of `%Ecto.Changeset{}`), each with its own `errors`; the parent's `errors` only holds parent-level problems (`posts: {"can't be blank", [validation: :required]}` or `{"is invalid", [validation: :embed, type: {:array, :map}]}`), and `valid?` is the conjunction. `traverse_errors(changeset, fn {msg, opts} -> ... end)` (or a 3-arity `fn changeset, field, {msg, opts}` for reflection against `changeset.validations`) flattens the tree. Real output from `test/ecto/changeset/embedded_test.exs`:

```elixir
# embeds_one + parent error
%{profile: %{name: ["SHOULD BE AT LEAST 3 CHARACTER(S)"]}, name: ["IS INVALID"]}
# embeds_many: a list positionally aligned with the children; valid child => %{}
%{posts: [%{title: ["SHOULD BE AT LEAST 3 CHARACTER(S)"]}, %{}], name: ["IS INVALID"]}
# but a *required* many-relation error sits on the parent key as a list of messages
%{posts: [{"can't be blank", [validation: :required]}]}
```

Note the shape inconsistency: `posts` is sometimes a list of per-child maps and sometimes a list of message tuples — JSON serialisers have tripped on this (ja_serializer issue #329 "EctoErrorSerializer doesn't render errors from relationships and embedded objects").

**Constraints: mapping DB errors back to fields after the fact.** `unique_constraint(cs, field_or_fields, name: ..., match: :exact | :suffix | :prefix, message: ..., error_key: ...)`, `foreign_key_constraint/3`, `check_constraint/3`, `exclusion_constraint/3`, `assoc_constraint/3`, `no_assoc_constraint/3` only *append* to `changeset.constraints` (`%{type, constraint, match, field, error_message, error_type}`). `Ecto.Repo.Schema.constraints_to_errors/3` then matches the adapter's reported constraint names against that list (`:exact`, `String.ends_with?`, `String.starts_with?`, or a `Regex`); a match becomes `{field, {msg, [constraint: :unique, constraint_name: name]}}` and `valid?: false`; **no match raises `Ecto.ConstraintError`**. The default name is inferred (`users_email_index`); the doc devotes paragraphs to partitioned-table suffix matching and case-sensitivity. `unique_constraint` requires `data.__meta__.source` — schemaless changesets get "cannot add constraint to changeset because it does not have a source". `prepare_changes(cs, fn cs -> ... cs end)` registers callbacks run *inside the Repo transaction* only when the changeset is valid (`changeset.repo` is available there); `merge/2` preserves them (3.14.2 fix).

## Form state: bound/unbound, touched/dirty/used, initial vs submitted, attempted values, reset

Ecto has **no notion of "bound" or "touched"**; those emerge from the three buckets plus `action`:

| Concept | Where it lives |
|---|---|
| initial values | `changeset.data` (struct or map) |
| what the user sent (including junk keys) | `changeset.params` (`nil` when the changeset came from `change/2` — "unbound") |
| what passed casting and differs from data | `changeset.changes` (see `changed?/3`, `get_change/3`, `fetch_change/2` → `{:ok, v} | :error`) |
| attempted-but-invalid value | *not* in `changes`; re-rendered from `params` by the form layer |
| dirty? | `changes != %{}` (`change/2` and `put_change/3` drop a change that equals the data value) |
| has an action been attempted? | `changeset.action` (`nil` → show no errors) |
| which fields were interacted with | **not in the changeset**; LV client `_unused_<field>` params + `Phoenix.Component.used_input?/1` (LV ≥ 1.0) or `phx-feedback-for` DOM annotation (LV ≤ 0.20) |

`Phoenix.HTML.FormData.input_value/3` for changesets (phoenix_ecto) encodes the display rule:

```elixir
def input_value(%{changes: changes, data: data}, %{params: params}, field) when is_atom(field) do
  case changes do
    %{^field => value} -> value
    %{} ->
      string = Atom.to_string(field)
      case params do
        %{^string => value} -> value      # attempted value survives a failed cast
        %{} -> Map.get(data, field)
      end
  end
end
```

`used_input?/1` (phoenix_component.ex) is purely param-driven and recursive: a field is "used" if `params[field]` exists without a sibling `params["_unused_" <> field]`; for nested maps it is used if *any* nested key is used. The LV 1.0 changelog (found via search; hexdocs blocked) says `phx-feedback-for` "has been replaced by `Phoenix.Component.used_input?/2`, which handles showing and hiding feedback using standard server rendering", with a `phx_feedback_dom.js` shim for old apps. In phoenix v1.7.10 `core_components.ex` the wrapper was `<div phx-feedback-for={@name}>`, inputs carried Tailwind variants `phx-no-feedback:border-zinc-300`, and `<.error>` had `phx-no-feedback:hidden` — i.e. errors were always rendered and the *client* hid them until the input was touched or the form submitted. **pyview's 0.20.17 client is in this regime**, so the server cannot rely on `_unused_` keys.

**Reset**: there is no reset API; you rebuild from `data` (`to_form(Context.change_user(user))`). LiveView's form-recovery re-sends `phx-change` after reconnect (form-bindings guide, "Recovery following crashes or disconnects"), so state naturally regenerates from params.

**Error gating in the form layer** (phoenix_ecto `html.ex`):

```elixir
defp form_for_errors(_changeset, nil = _action), do: []
defp form_for_errors(_changeset, :ignore = _action), do: []
defp form_for_errors(%Ecto.Changeset{errors: errors}, _action), do: errors

# nested forms inherit the parent's action; nil parent => children's errors are hidden too
defp apply_action(changeset, nil), do: %{changeset | action: nil}
defp apply_action(changeset, _action), do: changeset
```

## Rendering: HTML generation, customization layers, escape hatches for hand-written HTML

Layers, bottom-up:

1. **`Phoenix.HTML.FormData` protocol** (phoenix_html) — `to_form(source, opts)`, `to_form(source, form, field, opts)` (for nested), `input_value/3`, `input_type/3`, `input_validations/3`. Implemented for `Ecto.Changeset` (phoenix_ecto) and for plain maps (`%{"search" => nil}` + `errors: [search: {"Can't be blank", []}]`). Produces `%Phoenix.HTML.Form{source, impl, id, name, data, params, errors, hidden, options, action, index}`.
2. **`form[:field]`** (`Phoenix.HTML.Form.fetch/2`) returns `%Phoenix.HTML.FormField{id, name, value, errors, field, form}` — `name` = `"user[email]"`, `id` = `"user_email"`, nested `"user[addresses][0][street]"`/`"user_addresses_0_street"`. This struct is the *only* thing a component needs; it is what makes `<.input field={@form[:email]} />` possible without the component knowing about changesets.
3. **`Phoenix.Component.form/1`, `inputs_for/1`, `to_form/2`** (phoenix_live_view) — `<.form for={@form} phx-change="validate" phx-submit="save">` renders `<form>` plus CSRF/method hidden inputs; `inputs_for` iterates child forms, auto-rendering hidden primary-key inputs (`finner.hidden`, from `form_for_hidden/1` = the schema's primary keys) and `_persistent_id` unless `skip_hidden`/`skip_persistent_id`.
4. **`CoreComponents.input/1`** — *generated into the app* by the installer, so it is user-owned code. The `FormField` clause normalises everything, then dispatches on `type`:

```elixir
# phoenix/installer/templates/phx_web/components/core_components.ex.eex (1.9-dev)
def input(%{field: %Phoenix.HTML.FormField{} = field} = assigns) do
  errors = if Phoenix.Component.used_input?(field), do: field.errors, else: []

  assigns
  |> assign(field: nil, id: assigns.id || field.id)
  |> assign(:errors, Enum.map(errors, &translate_error(&1)))
  |> assign_new(:name, fn -> if assigns.multiple, do: field.name <> "[]", else: field.name end)
  |> assign_new(:value, fn -> field.value end)
  |> input()
end

def input(%{type: "checkbox"} = assigns) do
  assigns = assign_new(assigns, :checked, fn -> Phoenix.HTML.Form.normalize_value("checkbox", assigns[:value]) end)
  ~H"""
  <div class="fieldset mb-2">
    <label for={@id}>
      <input type="hidden" name={@name} value="false" disabled={@rest[:disabled]} form={@rest[:form]} />
      <span class="label">
        <input type="checkbox" id={@id} name={@name} value="true" checked={@checked}
               class={@class || "checkbox checkbox-sm"} {@rest} />{@label}
      </span>
    </label>
    <.error :for={msg <- @errors}>{msg}</.error>
  </div>
  """
end
```

The generic clause renders `<input type={@type} name={@name} id={@id} value={Phoenix.HTML.Form.normalize_value(@type, @value)} class={[@class || "w-full input", @errors != [] && (@error_class || "input-error")]} {@rest} />`. `normalize_value/2` handles `datetime-local` structs, textarea newlines, and checkbox truthiness (`"true"`/`true`).

5. **Generators as "schema → widgets" defaults.** `Mix.Tasks.Phx.Gen.Html.inputs/1` maps field types to markup: `:integer` → `type="number"`, `:float`/`:decimal` → `number step="any"`, `:boolean` → `checkbox`, `:text` → `textarea`, `:date`/`:time` → `date`/`time`, `*_datetime` → `datetime-local`, `{:array, _}` → `select multiple`, `{:enum, _}` → `select prompt="Choose a value" options={Ecto.Enum.values(Mod, :field)}`, else `text`; `:map` fields are skipped. phoenix_ecto's `input_type/3` has a similar mapping used by older `Phoenix.HTML` helpers.

**Escape hatches.** Every level is bypassable: use `@form[:email].name/.value/.errors` in raw `<input>` tags (the `used_input?` doc example does exactly that); pass `name=`/`value=`/`errors=` attrs to `<.input>` without a field; `skip_hidden`/`skip_persistent_id` on `inputs_for`; `Phoenix.HTML.Form.input_name/2`, `input_id/2`, `input_value/2` helpers; `options_for_select/2` for hand-built selects.

## Styling / theming

Ecto is style-free. Phoenix's stance is "generate the component into your project": the 1.9-dev `core_components` uses daisyUI/Tailwind classes (`fieldset`, `input`, `input-error`, `checkbox`, `select-error`, `text-error`) with `class`/`error_class` attrs as overrides (`@class || "w-full input"`), and `attr :rest, :global, include: ~w(accept autocomplete ... required rows size step)` to forward HTML attributes. Error styling is data-driven (`@errors != [] && "input-error"`). In the 1.7 era the "untouched" state was expressible in CSS via the `phx-no-feedback:` Tailwind variant (a plugin over the `phx-no-feedback` class the LV client toggled). There is no theme registry; theming = editing the generated file.

## Nested, dynamic (add/remove/reorder) and conditional forms

**Matching children** (`Ecto.Changeset.Relation.cast/5`, `cast_or_change/6`, `map_changes/9`): existing children are indexed by primary-key values (`process_current/3`; duplicate ids warn and keep the last). For each incoming param map, `param_pk/2` reads `"id"` (cast to the pk type) and `pop_current/2` removes the match: found → child `changeset/2` on the existing struct with `put_new_action(:update)`; not found or no id → `relation.__struct__.build(...)` + `on_cast` + `put_new_action(:insert)`; children left in `current` after the loop go through `on_replace/2`. `check_action!/2` refuses `:insert` for a struct that already exists and raises "Ecto forbids casting existing records through the association field for security reasons" if a param names an id not currently associated — you can't hijack another user's row by posting its id. `cast_assoc` on an unloaded association raises; `validate_required` on an unloaded assoc raises too — hence "preload before rendering" folklore.

**`on_replace`** (defined on the `has_many`/`embeds_many` declaration, not at cast time): `:raise` (default), `:mark_as_invalid`, `:nilify`, `:update` (one-cardinality only), `:delete`, `:delete_if_exists`. The raise text (relation.ex) is famous:

> you are attempting to change relation :posts of Author but the `:on_replace` option of this relation is set to `:raise`. By default it is not possible to replace or delete embeds and associations during `cast`. Therefore Ecto requires the parameters given to `cast` to have IDs matching the data currently associated ...

The moduledoc warns that `:delete` "must be used carefully as they allow users to delete any associated data by simply setting it to nil or an empty list" and shows the safer virtual `delete` boolean + `%{change(comment, delete: true) | action: :delete}` pattern; it also shows the `:ignore` action for "all fields blank → drop this child".

**`sort_param` / `drop_param`** (Ecto 3.10.0, 2023-04-10; 3.11 "Consider `sort_param` even if the relation param was not given"). Implementation `cast_params(:many, value, sort, drop)`:

```elixir
{sorted, pending} =
  if is_list(sort), do: Enum.map_reduce(sort -- drop, value, &Map.pop(&2, &1, %{})), else: {[], value}
sorted ++ (pending |> Map.drop(drop) |> Enum.map(&key_as_int/1) |> Enum.sort() |> Enum.map(&elem(&1, 1)))
```

Semantics from `test/ecto/changeset/embedded_test.exs` ("cast embeds_many with map and sort_param and delete_param"): with `posts = %{1 => "one", 2 => "two", 3 => "three"}`, `drop: [2]` → `["one","three"]`; `sort: [2,3,1]` → `two three one`; `sort: [2]` → `two one three` (**sorted indexes first, then the rest** — the `cast_assoc` doc says the opposite, "any index not present ... will come _before_ any of the sorted indexes"; code and tests win); `sort: ["new"]` → a fresh child with `%{}` params; `drop: [0]` on an existing child → `action: :replace`; non-list `sort: :x` is ignored. After a drop, positions are compacted and a 3-arity `:with` receives the final position (`with: fn child, attrs, position -> change(child, position: position) end`) — required for real DB associations, where order must be persisted in a `:position` column. `reorder_assoc/2,3` (3.14) sorts child changesets delete→update→insert to dodge unique-constraint collisions.

**Zero-JS add/remove/reorder markup** (`Phoenix.Component.inputs_for/1` docs, LV 1.2.11):

```elixir
schema "mailing_lists" do
  field :title, :string
  embeds_many :emails, EmailNotification, on_replace: :delete do
    field :email, :string
    field :name, :string
  end
end

def changeset(list, attrs) do
  list
  |> cast(attrs, [:title])
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

<button type="button" name="mailing_list[emails_sort][]" value="new" phx-click={JS.dispatch("change")}>
  add more
</button>
```

How it works: named buttons are serialised with the form on change/submit; `JS.dispatch("change")` turns a click into the form's `phx-change` so the server re-casts; the per-row hidden `emails_sort[]` = index records order; the trailing empty `emails_drop[]` guarantees the key is present (an empty list) when the last child is removed; `"new"` is an unknown index → new child. The docs note `on_replace: :delete` is required.

**`_persistent_id`** (`apply_persistent_id/4` in phoenix_component.ex): for each child form, reuse `params["_persistent_id"]` if the client sent one, else allocate the next integer not in `seen_ids`; set `form.id = "#{parent_form.id}_#{field}_#{persistent_id}"`, push it into `params` and into `hidden` so it renders as a hidden input. Result: DOM ids stay stable when rows are reordered/removed (so focus, LV's "never overwrite a focused input" rule, and JS hooks survive), while the `name` still carries the positional index. Ecto never sees it as a change because it is not permitted; it just rides along in `changeset.params`.

**Rendering nested forms** (phoenix_ecto `to_form/4`): children come from `source.changes[field]` if present (the changesets produced by `cast_embed`), else from `data` (`assoc_from_data`), else an empty struct for `:one`; `prepend`/`append` are applied only when the parent's params don't already contain the field; `skip_replaced/1` removes children whose `action == :replace` (so a dropped row disappears from the render); each child changeset is produced through the same `on_cast` function (`to_changeset/5` calls `cast.(data, %{})` or `cast.(data, %{}, index)`) so "new" rows render with the schema's defaults and validations metadata.

**Conditional forms.** There is no declarative conditional API; you branch in `changeset/2` (`if get_field(cs, :kind) == :company, do: validate_required(cs, [:vat])`) and in the template (`:if={@form[:kind].value == :company}`). The `inputs_for` docs warn against deriving state from `form[:field].value` because it is polymorphic (string vs integer, struct vs changeset vs raw params) and recommend computing derived values from the changeset in `handle_event` or storing them as virtual fields via `put_change`.

## DX highlights — with real code (copied/adapted from primary sources; cite each example)

1. **The generated LiveView form** (`phoenix/priv/templates/phx.gen.live/form.ex.eex`, 1.9-dev) — the canonical validate/save loop:

```elixir
def mount(params, _session, socket) do
  {:ok, socket |> assign(:return_to, return_to(params["return_to"])) |> apply_action(socket.assigns.live_action, params)}
end

defp apply_action(socket, :new, _params) do
  post = %Post{}
  socket
  |> assign(:page_title, "New Post")
  |> assign(:post, post)
  |> assign(:form, to_form(Blog.change_post(post)))          # action nil => no errors shown
end

def handle_event("validate", %{"post" => post_params}, socket) do
  changeset = Blog.change_post(socket.assigns.post, post_params)
  {:noreply, assign(socket, form: to_form(changeset, action: :validate))}   # errors now visible (for used inputs)
end

def handle_event("save", %{"post" => post_params}, socket) do
  case Blog.create_post(post_params) do                        # Repo.insert sets action: :insert on failure
    {:ok, post} -> {:noreply, socket |> put_flash(:info, "Post created successfully") |> push_navigate(to: ~p"/posts/#{post}")}
    {:error, %Ecto.Changeset{} = changeset} -> {:noreply, assign(socket, form: to_form(changeset))}
  end
end
```

```heex
<.form for={@form} id="post-form" phx-change="validate" phx-submit="save">
  <.input field={@form[:title]} type="text" label="Title" />
  <.input field={@form[:published]} type="checkbox" label="Published" />
  <footer>
    <.button phx-disable-with="Saving..." variant="primary">Save Post</.button>
  </footer>
</.form>
```

2. **`cast/4` empty values and custom cast messages** (doctests in `lib/ecto/changeset.ex`):

```elixir
iex> cast(%Post{}, %{title: "", topics: []}, [:title, :topics]).changes
%{topics: []}                       # "" is empty -> default nil == data nil -> no change; [] is not empty by default
iex> cast(%Post{}, %{title: "", topics: []}, [:title, :topics], empty_values: [[], nil]).changes
%{title: ""}
iex> cast(post, %{title: 1, body: 2}, [:title, :body], message: fn field, _meta -> [title: "must be a string"][field] end).errors
[title: {"must be a string", [type: :string, validation: :cast]},
 body:  {"is invalid",       [type: :string, validation: :cast]}]
```

3. **`apply_action/2` for non-persisted forms** (docs):

```elixir
iex> {:ok, data} = apply_action(changeset, :my_action)
iex> {:error, changeset} = apply_action(changeset, :update)
%Ecto.Changeset{action: :update}
iex> apply_action!(change(%Post{author: "bar"}, %{title: :bad}), :update)
** (Ecto.InvalidChangesetError) could not perform update because changeset is invalid.
```

4. **Custom "ignore blank child" action** (`cast_assoc/3` docs) — conditional nested logic expressed by returning a differently-actioned changeset:

```elixir
def changeset(struct, params) do
  struct
  |> cast(params, [:title, :body])
  |> validate_required([:title, :body])
  |> case do
    %{valid?: false, changes: changes} = changeset when changes == %{} -> %{changeset | action: :ignore}
    changeset -> changeset
  end
end
```

5. **Errors → JSON with `traverse_errors/2`** (doc example; the `%{count}` interpolation idiom):

```elixir
traverse_errors(changeset, fn {msg, opts} ->
  Regex.replace(~r"%{(\w+)}", msg, fn _, key ->
    opts |> Keyword.get(String.to_existing_atom(key), key) |> to_string()
  end)
end)
#=> %{title: ["should be at least 3 characters"]}
```

6. **Reflection → HTML validation attrs** (phoenix_ecto `html.ex`):

```elixir
def input_validations(%{required: required, validations: validations} = changeset, _, field) do
  [required: field in required] ++
    for {key, validation} <- validations, key == field, attr <- validation_to_attrs(validation, field, changeset), do: attr
end
defp validation_to_attrs({:length, opts}, _f, _cs), do: (if v = opts[:max], do: [maxlength: v], else: []) ++ (if v = opts[:min], do: [minlength: v], else: [])
defp validation_to_attrs({:number, opts}, field, cs), do: step_for(type) ++ min_for(type, opts) ++ max_for(type, opts)  # :integer => step: 1, less_than: 10 => max: 9
```

7. **Computing derived state from nested changesets instead of `form[:x].value`** (`inputs_for` docs):

```elixir
def handle_event("validate", %{"tracked_day" => params}, socket) do
  changeset = TrackedDay.changeset(socket.assigns.tracked_day, params)
  {:noreply, assign(socket, form: to_form(changeset, action: :validate), remaining: calculate_remaining(changeset))}
end

defp calculate_remaining(changeset) do
  total = Ecto.Changeset.get_field(changeset, :total)
  Ecto.Changeset.get_embed(changeset, :activities)
  |> Enum.reduce(total, fn
    %{valid?: true} = cs, acc -> acc - Ecto.Changeset.get_field(cs, :duration)
    _, acc -> acc
  end)
end
```

## Known pain points & criticisms (cite)

- **The `action` gate is a perennial beginner trap.** Elixir Forum threads "[SOLVED] When Ecto.Changeset action is set?" (#1455), "To_form not setting errors from the changeset errors" (#58486); the Mike Zornek/elixirfocus schemaless-changesets post (search summary) notes that "as you test validations on your web forms you will not see any errors" until you set an action. Ecto's own guide has to add the line "Annotate the action so the UI shows errors". The decision to hide errors is *right* (an empty new-record changeset is invalid on mount), but encoding it as "is `action` non-nil" is indirect.
- **`on_replace: :raise` by default.** PR elixir-ecto/ecto#1896 (Jan 2017) rewrote the error because of forum confusion and issue #1790; the message is now a small essay. Every nested-form tutorial (DockYard 2024, fly.io Phoenix Files, Arrowsmith Labs) has a paragraph on setting `on_replace: :delete`. The LiveView `inputs_for` docs must call it out in a warning box.
- **`form[:field].value` is polymorphic.** LiveView docs (inputs_for "A note on accessing a field's `value`"): the value "may either return a struct, a changeset, or raw parameters sent by the client (when using `drop_param`). This makes the `form[:field].value` impractical for deriving or computing other properties." Type of a scalar also flips between cast type and raw string depending on whether the cast succeeded.
- **Docs vs code on `sort_param` ordering** (found above): doc says unlisted indexes come *before* sorted ones; `cast_params/4` and the test show sorted ones first.
- **`validate_required` looks at `data`**, so a blank new struct is invalid before the user does anything → the whole `used_input?`/`phx-feedback-for` apparatus exists to compensate. Real-time validation "as soon as you start typing ... an error appears" (AppSignal 2021, search summary) is the UX complaint that motivated `phx-debounce="blur"` and `_unused_` tracking.
- **Nested error surfacing.** "How do I make validation errors in embedded schemas show up on the parent?" (Elixir Forum #65521); `changeset.errors` only has parent errors, you must `traverse_errors` — and its output shape differs for required-many vs per-child errors (ja_serializer #329, PR #257).
- **Single-responsibility critique.** "SOLID Ecto Changesets" (crossingtheruby, 2021; blocked, quoted via search): "A changeset is operating on two different levels: the low-level change tracking, validating, etc.; and the higher-level encoding of the overall process or flow of data through the application from request to repository ... changesets don't seem to comply with the Single Responsibility Principle." Constraints (`repo`, `repo_opts`, `prepare`, `filters`) living in the same struct as form casting is the concrete symptom; `unique_constraint` is unusable on schemaless data.
- **`empty_values` churn.** Ecto 3.10 changed semantics (whitespace-only strings empty, empty values detected inside lists — marked "**Potentially breaking change**" in 3.8), then 3.12 removed function support in favour of `:trim_values` (`cast/4` raises "passing functions in :empty_values is no longer support, use :trim_values instead").
- **Coupling through naming conventions**: `cast_embed` silently requires `Child.changeset/2` (arity-2 or 3) unless `:with` is given; `_confirmation`/`_sort`/`_drop`/`_persistent_id`/`_unused_` are all magic param-name suffixes; the `id` hidden input must be rendered for updates to be updates rather than inserts (search results: "The critical gotcha here is that you must include a hidden input field with the id for existing children").
- **Security footgun disguised as convenience**: `on_replace: :delete` lets a client delete any child by omitting it; Ecto's docs recommend a virtual `delete` boolean instead.

## Lessons for pyview — steal / adapt / avoid (opinionated and concrete; tie to the brief; where useful sketch what the pyview-equivalent could look like in Python)

**Architecture (steal the layering, verbatim).** The single most valuable lesson is the *three-layer split* the maintainer already senses ("a few different concerns"): (1) a `Changeset` that is pure data-in (`params → changes + errors`) and knows nothing about HTML; (2) a `Form`/`FormField` adapter that turns a changeset into names/ids/values/errors per field and per nested child; (3) components/templates that render `FormField` and own all styling. Phoenix's generated `input` component is user-owned code precisely so styling is never a library concern. For pyview: `pyview.forms.Changeset` (layer 1), `to_form(changeset, as_="user", action=...)` returning a `Form` with `form["email"] -> FormField(id, name, value, errors)` and `form.inputs_for("addresses") -> list[Form]` (layer 2), and a small set of t-string / Ibis helpers plus a *copyable* `core_components.py`-style module (layer 3).

**Steal: `data` / `params` / `changes` + `action`.**
- Keep the raw `params` dict on the changeset even for keys you don't accept; render `changes → params → data`. This gives "attempted values" for free and lets `_persistent_id`-style bookkeeping ride along.
- Gate error display on an explicit `action` (`None` after mount, `"validate"` after phx-change, `"save"` after submit). Make the pyview API *more explicit* than Ecto's: `Form(changeset, action="validate")`, and document it in the first example. Provide `apply_action(cs, "save") -> Ok(model) | Err(cs)`.
- Add a per-field **"used"** notion in the form layer, not in the changeset. Because pyview uses the 0.20.17 client, `_unused_` params are *not* sent; the current pyview trick ("keep errors only for keys already in changes") is a server-side approximation of "used". Better: track `used: set[str]` on the changeset from `_target` across phx-change events (each event marks its target path used; submit marks all used) and let `FormField.errors` be empty while unused. Optionally also emit `phx-feedback-for` markup so the client-side hiding works during recovery.

**Steal: error = (template, params) + late translation.** Represent errors as `Error(msg="should be at least %{count} character(s)", params={"count": 3, "validation": "length", "kind": "min"})` (or `str.format`-style `{count}`), translate at render time via a pluggable `translate_error(err) -> str` (gettext `ngettext` when `count` present). Pydantic v2 already gives you `type` (code), `msg`, `ctx`, `loc` per error (`ValidationError.errors()`); map `type → params["validation"]`, `ctx → params`, and keep `msg` as the default template. That is a near-1:1 port of Ecto's model with zero user boilerplate.

**Steal: `traverse_errors` + positional nested errors — but fix the shape.** Store errors as a tree keyed by path segments (`("addresses", 0, "street")`) — pydantic `loc` tuples are exactly that — and give `FormField.errors` for a nested child by prefix lookup. Avoid Ecto's two shapes for `posts` (list-of-maps vs list-of-messages): keep parent-level errors under a reserved key (e.g. `errors[("addresses",)]`) distinct from child errors.

**Steal: nested param decoding + index-keyed lists + sort/drop.** pyview must first add a `Plug.Conn.Query`-like decoder (`user[addresses][0][street]` → nested dict; `tags[]` → list; explicit indexes only, refuse `a[][b]`). Then implement `cast_nested(field, sort_param="addresses_sort", drop_param="addresses_drop")` with Ecto's exact semantics (sorted indexes first, unknown index → new blank child, drop → remove + compact, trailing empty `drop[]` hidden input so "delete last" works). Ship the *markup helpers* (`form.sort_input(child)`, `form.drop_button(child)`, `form.add_button("addresses")`) so the DockYard recipe is one line each. This gets "deeply nested + dynamic with zero JS" using only client features pyview already has (named buttons serialise on change; `JS.dispatch("change")` exists in 0.20).

**Steal: `_persistent_id`.** Allocate a per-child stable id in the form layer, render it as a hidden input, key DOM `id`s by it and `name`s by position. Cheap, and it fixes focus loss on reorder.

**Steal: match children by id with a security check.** For edit forms over persisted children, render a hidden `id` for existing children and refuse ids that are not currently associated (Ecto's "forbids casting existing records through the association field for security reasons"). For pure-pydantic (non-DB) lists, position + `_persistent_id` is enough.

**Adapt to pydantic: split "cast" from "validate", run validators only on changed values.** Ecto's per-field cast is `Ecto.Type.cast` per permitted key with empty-value normalisation *before* typing, then rule validations on `changes` only. A pyview equivalent:

```python
@dataclass
class Changeset(Generic[M]):
    model: type[M]
    data: M | dict            # initial values
    params: dict[str, Any]    # raw, nested, string-keyed; never trimmed to permitted keys
    changes: dict[str, Any]   # typed, per-field, only where differing from data
    errors: dict[tuple, list[Error]]   # path -> [Error(msg, params)]
    action: str | None = None
    used: set[tuple] = field(default_factory=set)

    def cast(self, params, permitted: list[str] | None = None, *, empty_values=("",)) -> "Changeset[M]": ...
    # per field: lookup -> empty-value -> default; TypeAdapter(field.annotation).validate_python(value) in lax mode
    # pydantic error -> Error(msg=e["msg"], params={"validation": e["type"], **e.get("ctx", {})})
    def validate(self) -> "Changeset[M]": ...        # run model_validator / field_validator rules via model.model_validate(merged) and keep only errors whose loc is in changes
    def validate_change(self, field, fn) / add_error(path, msg, **params) / get_field / put_change / apply_changes()
```

`empty_values=("",)` → `None` (or the field's default) is essential for HTML: pydantic will otherwise reject `""` for `int | None`. Checkbox handling should copy Phoenix: hidden `false` + checkbox `true`, cast `"true"|"1"|"on"` → `True`. Multi-select: `name="field[]"`, drop empty strings inside lists (Ecto's `filter_values` for arrays).

**Adapt: derive widgets from the pydantic schema, like `phx.gen.html`.** Ecto's *generator* (not the library) maps `int → number`, `bool → checkbox`, `Enum/Literal → select`, `list[...] → multi-select`, `date/datetime → date/datetime-local`, `str with max_length → maxlength`, `Field(ge=1) → min`, and nested `BaseModel`/`list[BaseModel]` → fieldset / `inputs_for`. Because pyview owns `type[BaseModel]`, do it at runtime (`form.render()` / `{{ form | render_inputs }}`) *and* keep the `FormField` escape hatch for hand-written HTML. Ecto's `input_validations` reflection (validations → `required/minlength/maxlength/min/max/step`) comes free from `FieldInfo.metadata`.

**Adapt: `changeset/2`-style hooks without the coupling.** Ecto needs a `changeset/2` function on every child module; pyview can default to "pydantic validators on the child model" and accept `with=callable` overrides for per-form rules (e.g. `cast_nested("addresses", with=AddressForm.changeset)`), so conditional/per-context rules (registration vs profile edit) don't pollute the model — the "Data mapping and validation" guide's argument for a separate `Registration` embedded schema applies to pydantic models too.

**Avoid.**
- Don't make error visibility depend on an implicit side effect of a persistence call (Ecto's `Repo.insert` setting `action`). Keep it a visible parameter of `to_form`/`Form`.
- Don't default nested collections to "raise if a child is missing" (`on_replace: :raise`); for in-memory pydantic lists the natural default is "replace the list"; for DB-backed children make deletion opt-in per relation (`on_missing="delete" | "ignore" | "error"`) and document the mass-delete risk.
- Don't expose a polymorphic `field.value`; expose `field.value` (display string) separately from `changeset.get_field(path)` (typed).
- Don't mix persistence concerns (`repo`, constraints, transactions) into the changeset struct; provide a *separate* hook to map an `IntegrityError` to a field error after the fact (`cs.add_error(("email",), "has already been taken", constraint="unique")`).
- Don't produce two different nested-error shapes; and don't require users to remember five magic param suffixes — generate them from helpers.

## Sources (every URL / repo path you actually read)

Local clones (shared cache `.../scratchpad/repos/`):
- `ecto/lib/ecto/changeset.ex` (moduledoc; `cast/4`, `change/2`, `changed?/3`, `cast_assoc/3`, `cast_embed/3`, `cast_relation/4`, `cast_params/4`, `reorder_assoc/2,3`, `fetch_field/2`, `get_field/3`, `get_assoc/3`, `get_embed/3`, `update_change/3`, `put_change/3`, `force_change/3`, `delete_change/2`, `apply_changes/1`, `apply_action/2`, `apply_action!/2`, `add_error/4`, `validate_change/3,4`, `validate_required/3`, `field_missing?/2`, `missing?/2`, `unsafe_validate_unique/4`, `validate_format/4`, `validate_inclusion/4`, `validate_length/3`, `validate_number/3`, `validate_confirmation/3`, `validate_acceptance/3`, `message/4`, `prepare_changes/2`, `constraints/1`, `unique_constraint/3`, `traverse_errors/2`, `traverse_validations/2`)
- `ecto/lib/ecto/changeset/relation.ex` (`cast/5`, `do_cast/7`, `cast_or_change/6`, `single_change`, `map_changes/9`, `on_replace/2`, `on_cast_default/1`, `check_action!/2`, `process_current/3`, `pop_current/2`, `param_pk/2`)
- `ecto/lib/ecto/repo/schema.ex` (`constraints_to_errors/3`)
- `ecto/lib/ecto/type.ex` (`cast_boolean/1`, `cast_fun/1`, `trim/2`), `ecto/lib/ecto/enum.ex`, `ecto/lib/ecto/schema.ex` (`embeds_many` primary key default)
- `ecto/test/ecto/changeset_test.exs` (error shapes; `traverse_errors` tests), `ecto/test/ecto/changeset/embedded_test.exs` (sort/drop test, `traverse_errors` nested shapes, invalid params)
- `ecto/CHANGELOG.md` (v3.15.0-dev, 3.14.x, 3.12, 3.11, 3.10, 3.9, 3.8 entries), `ecto/guides/howtos/Data mapping and validation.md`, `ecto/guides/howtos/Embedded Schemas.md`
- `phoenix_ecto/lib/phoenix_ecto/html.ex` (FormData impl: `to_form/2,4`, `input_value/3`, `input_type/3`, `input_validations/3`, `form_for_errors/2`, `form_for_hidden/1`, `apply_action/2`, `skip_replaced/1`)
- `phoenix_live_view/lib/phoenix_component.ex` (`to_form/2`, `used_input?/1`, `form/1` "A note on `:errors`", `inputs_for/1` docs + `apply_persistent_id/4`), `phoenix_live_view/guides/client/form-bindings.md`, `phoenix_live_view/lib/phoenix_live_view/channel.ex` (`Plug.Conn.Query.decode`)
- `phoenix_html/lib/phoenix_html/form.ex`, `form_field.ex`, `form_data.ex` (map impl)
- `phoenix/priv/templates/phx.gen.live/form.ex.eex`, `phoenix/installer/templates/phx_web/components/core_components.ex.eex` (`input/1`, `error/1`, `translate_error/1`, `translate_errors/2`), `phoenix/lib/mix/tasks/phx.gen.html.ex` (`inputs/1`)
- https://raw.githubusercontent.com/phoenixframework/phoenix/v1.7.10/installer/templates/phx_web/components/core_components.ex (`phx-feedback-for`, `phx-no-feedback:` classes)
- https://github.com/elixir-ecto/ecto/pull/1896 (on_replace error-message PR, references issue #1790)

Web searches (summaries only; the target hosts hexdocs.pm, elixirforum.com, dockyard.com, fly.io, crossingtheruby.com, mikezornek.com, amberbit.com were blocked):
- DockYard "How to Dynamically Add and Remove Embedded Item Inputs in a Form Using sort_param and drop_param" (2024-03-12); fly.io Phoenix Files "Sorting and Deleting many-to-many assocs with Ecto and LiveView"; Arrowsmith Labs "Nested forms in Phoenix LiveView: advanced tips and tricks"
- Elixir Forum: "[SOLVED] When Ecto.Changeset action is set?" (t/1455), "To_form not setting errors from the changeset errors" (t/58486), "How do I make validation errors in embedded schemas show up on the parent?" (t/65521), "Phoenix LiveView 1.0.0-rc.0 is out!" (t/63401)
- hexdocs Plug.Conn.Query (nesting-inside-lists ambiguity); Phoenix LiveView 1.0.0 changelog (phx-feedback-for removal, via search summary)
- crossingtheruby.com "SOLID Ecto Changesets" (2021-02-06); mikezornek.com "Using Schemaless Changesets to Separate Concerns" (2021-09); AppSignal "Real-Time Form Validation with Phoenix LiveView" (2021-09-28); vt-elixir/ja_serializer issue #329 / PR #257
