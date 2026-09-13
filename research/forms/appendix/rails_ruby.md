# Rails form helpers / ActiveModel errors / nested attributes / simple_form, and dry-schema / dry-validation / Reform / superform (Ruby)

Versions researched (all executed locally with ruby 3.3.6, real output pasted below): activemodel/actionview 8.1.3.1, rack 3.2.7, dry-schema 1.16.0, dry-validation 1.11.1, reform 2.6.2 (+disposable 0.6.3), superform 0.7.0 (+phlex 2.4.1), active_interaction 5.5.0; simple_form, cocoon, turbo-site read from git clones (main). Date: 2026-09-12. Demo scripts: `scratchpad/research/rb/{rails_demo,dry_demo,dry_validation_demo,reform_demo,superform_demo,ai_demo}.rb`.

## TL;DR

- Rails' whole form stack hangs on ONE naming convention, `object[assoc_attributes][0][field]`, decoded by `Rack::Utils.parse_nested_query` into nested hashes (`a[]` -> array, `a[b]` -> hash, `a[][b]` -> array of hashes grouped by repeated key; `a[0][b]` -> a HASH with string key `"0"`, not an array). Everything else (ids, labels, error wrapping, nested attributes, cocoon) derives from it.
- Errors are typed objects, not strings: `errors.add(:name, :too_short, count: 3)` stores `ActiveModel::Error(attribute, type, options)`; `.messages`, `.details`, `.full_messages`, `.where(:name, :too_short)`, `.of_kind?`, `.added?`, `:base` for form-level. The message is resolved lazily through a documented i18n key chain (model/attribute/type -> model/type -> global type), with `%{count}` interpolation and pluralisation.
- Rails helpers do NOT infer `required` from validators; simple_form does (`required_by_validators?` = any `presence` validator matching the current action), plus `maxlength`/`min`/`max`/`pattern` from validators and input type from column type + attribute-name regexes (`password`, `email`, `phone`, `url`, `time_zone`, `country`).
- simple_form's wrappers DSL (`config.wrappers :bootstrap do |b| b.use :label; b.use :input; b.use :error, wrap_with: {...} end`) is the cleanest "theming layer" in this survey: field rendering = a named pipeline of components; per-call `input_html:`/`wrapper_html:` overrides.
- dry-schema separates *input-source coercion* (`Params` processor: `"" -> nil`, `"1"/"true" -> bool`, `"3" -> 3`; `JSON` processor: no string coercion) from *type/predicate checks*, and produces nested errors `{address: {city: [...]}, items: {1: {qty: [...]}}}` + a typed `result.to_h`. dry-validation adds `rule(:field)` blocks that run ONLY if that key's schema checks passed (verified), `rule(:items).each`, cross-field rules, `base.failure`, injected deps.
- Reform = "form object between params and model": `validate(params)` deserialises into a twin (model untouched), populators decide how nested fragments map to nested objects (`populate_if_empty:`, `skip_if: :all_blank`, custom `populator:` with `skip!`), then `sync`/`save`. Nested errors flatten to `"songs.length"` keys, and each nested form has its own `errors`.
- superform proves you can derive `name`/`id` AND the permitted-params whitelist from a single form definition tree (`Namespace`/`Field`/`NamespaceCollection`), rendering with plain Ruby (Phlex) instead of a builder+ERB.
- Turbo/Hotwire convention for HTML-over-the-wire re-render: respond `422 Unprocessable Content` with the re-rendered form; the client keeps the URL and swaps the body. LiveView does the equivalent over the socket, so pyview only needs the *changeset -> re-render* half.

## Mental model & core abstractions

**Rails**: `form_with(model: @post)` picks `object_name` (`post`) via `model_name.param_key` and a `FormBuilder`; each helper (`f.text_field(:title)`) builds `name="post[title]" id="post_title"` and reads `@post.title` for the value. `f.fields_for(:comments)` reuses the builder with the child object and a nested prefix, automatically switching to `post[comments_attributes][i][...]` when the model responds to `comments_attributes=` (the hook `accepts_nested_attributes_for` defines). Validation lives in the model (`ActiveModel::Validations`, `valid?(context)`), errors in `model.errors` (`ActiveModel::Errors`). Rendering-time error decoration is a global proc (`ActionView::Base.field_error_proc`, default wraps the tag in `<div class="field_with_errors">`). Form objects without DB use `include ActiveModel::Model` (or `ActiveModel::API`) + `ActiveModel::Attributes` for typed attributes.

**simple_form** replaces the builder: `f.input :email` looks up the *input type* (`default_input_type`), instantiates an `Inputs::*Input`, then runs a named **wrapper** pipeline (components `:html5, :placeholder, :maxlength, :minlength, :pattern, :min_max, :readonly, :label_input, :hint, :error`).

**dry-schema / dry-validation**: `Dry::Schema.Params { required(:age).filled(:integer) }` is a *compiled processor*: key coercion -> type coercion -> predicate rules -> `Result` (`to_h`, `errors`, `error?(path)`). `Dry::Validation::Contract` = `params { schema }` + `rule(...)` blocks + injected `option`s. Pure data-in/data-out; no rendering, no model.

**Reform**: `Reform::Form` subclasses declare `property`/`collection` (with nested blocks = nested forms) and a `validation do ... end` block (dry-validation contract). Lifecycle (README §"Overview"): `new(model)` -> optional `prepopulate!` -> render -> `validate(params)` (deserialise + populate + validate) -> `sync` or `save` (block form yields the nested hash instead of saving).

**superform**: a tree of `Superform::Namespace` (object), `Superform::Field` (leaf), `NamespaceCollection` (array of objects), `FieldCollection` (array of values); each node has `.dom` (`id`, `name`, `value`) and `serialize`/`assign`.

## Data in (naming, parsing, coercion, nested/lists)

`Rack::Utils.parse_nested_query` (rack 3.2.7), actual output:

```
a=1&a=2                                  => {"a"=>"2"}                       # last wins, no [] => scalar
a[]=1&a[]=2                              => {"a"=>["1", "2"]}
a[b]=1&a[c]=2                            => {"a"=>{"b"=>"1", "c"=>"2"}}
a[][b]=1&a[][c]=2&a[][b]=3               => {"a"=>[{"b"=>"1","c"=>"2"}, {"b"=>"3"}]}   # new hash when key repeats
a[0][b]=1&a[1][b]=2                      => {"a"=>{"0"=>{"b"=>"1"}, "1"=>{"b"=>"2"}}}  # NOT an array
u[addr][city]=x&u[tags][]=t1&u[tags][]=t2=> {"u"=>{"addr"=>{"city"=>"x"}, "tags"=>["t1","t2"]}}
x[]=1&x[b]=2                             => Rack::QueryParser::ParameterTypeError: expected Hash (got Array) for param `x'
```

Rails therefore uses *indexed hashes* for nested collections (`post[comments_attributes][0][body]`) and `assign_nested_attributes_for_collection_association` accepts either a Hash (uses `.values`, unless it contains an `id` key, then it's one record) or an Array (activerecord/lib/active_record/nested_attributes.rb:491-508). Keys need not be numeric: cocoon renders the template with `child_index: "new_tasks"` (cocoon/lib/cocoon/view_helpers.rb:51) and the JS replaces `[new_tasks]`/`_new_tasks_` with `new Date().getTime()` before insertion (cocoon.js:52-55). Each nested row carries `hidden_field :id` (only if persisted) and `_destroy` (`UNASSIGNABLE_KEYS = %w(id _destroy)`, line 412); `reject_if: :all_blank` = `REJECT_ALL_BLANK_PROC` ignoring `_destroy` (line 303); `allow_destroy`, `limit`, `update_only` are the only options (line 356). Strong params must mirror the shape: `permit(:name, tasks_attributes: [:id, :description, :done, :_destroy])` (cocoon README:120).

Real ActionView output (rails_demo.rb; HTML-unescaped for readability):

```html
<input type="hidden" name="utf8" value="✓">                      <!-- form_with(local: true) -->
<div class="field_with_errors"><label>Title</label></div>       <!-- field_error_proc wraps label AND input -->
<div class="field_with_errors"><input required="required" type="text" value="" name="post[title]"></div>
<input name="post[draft]" type="hidden" value="0"><input type="checkbox" value="1" checked name="post[draft]">
<select name="post[category]"><option value="">-- pick --</option><option value="a">A</option><option selected value="b">B</option></select>
<input name="post[tags][]" type="hidden" value=""><select multiple name="post[tags][]">...</select>  <!-- multi-select gets hidden "" too -->
<input type="hidden" value="7" name="post[comments_attributes][0][id]" id="post_comments_attributes_0_id">
<input type="text" value="old" name="post[comments_attributes][0][body]" id="post_comments_attributes_0_body">
<input name="post[comments_attributes][0][_destroy]" type="hidden" value="0"><input type="checkbox" value="1" name="post[comments_attributes][0][_destroy]" id="post_comments_attributes_0__destroy">
<input type="hidden" name="post[comments_attributes][1][id]">   <!-- new record: empty id -->
<input type="text" value="Ann" name="post[author][name]" id="post_author_name">   <!-- fields_for(:author, obj): no _attributes suffix when no author_attributes= -->
<select id="post_published_on_1i" name="post[published_on(1i)]">   <!-- date_select multiparameter: (1i)(2i)(3i) -->
field_name: post[comments][body][]   field_id: post_3_comments_body      <!-- f.field_name(:comments,:body,multiple:true); f.field_id(:comments,:body,index:3) -->
```

Note `required="required"` appears only because I passed `required: true`; plain Rails helpers don't derive it (simple_form does, see below). The checkbox "hidden 0 then checkbox 1" trick and the multi-select hidden `""` exist because unchecked/empty controls are absent from urlencoded bodies; the *server* then has to treat `""` in an array as "no selection".

`ActiveModel::Attributes` casting (real output): `attribute :age, :integer` -> `"abc"` => `0` (!), `"12"` => `12`; `:boolean` -> `"0"`/`"false"`/`"f"` => `false`, `""` => `nil`, `"anything"` => `true`; `:date` -> `"2020-02-30"` => `nil` (silently), `"2020-02-03"` => `Date`; `:decimal` -> `"1.50"` => `0.15e1`. Lossy casts are a known Rails wart: validation must run on the cast value, and the original string is only kept in ActiveRecord (`*_before_type_cast`; ActiveModel::Attributes has no such method - verified NoMethodError). Multiparameter attributes (`published_on(1i)`) are assembled in `ActiveRecord::AttributeAssignment` (unverified that plain ActiveModel handles them).

**dry-schema Params vs JSON** (real output, same input `{"age"=>"3","nick"=>""}`): `Params` -> `{:age=>3, :nick=>nil}`; `JSON` -> `{:age=>"3", :nick=>""}` with error `{:age=>["must be an integer"]}`. Under Params: `"1"` -> `true`, `""` for `maybe(:float)` -> `nil`, `"2020-01-02"` -> `Date`, `"abc"` for `:integer` -> **error** "must be an integer" (not 0). `required(:x)` = key must be present; `optional(:x)` = may be absent; `.filled(:t)` = non-nil/non-empty; `.maybe(:t)` = nil allowed; `.value(:t, pred: arg)` raw predicates; `.hash do ... end` and `.array(:hash) do ... end` nest. `config.validate_keys = true` reports `{:extra=>["is not allowed"], :meta=>{:junk=>["is not allowed"]}}` (strong-params-like), `key_map.to_dot_notation` => `["name", "meta.k"]`, and the `:info` extension exposes `{keys: {name: {required: true, type: "string", nullable: false}, ...}}` - schema introspection usable for rendering.

**ActiveInteraction** (3 lines): typed filters `string :email; integer :quantity, default: 1; hash :address do string :city end; array :items, index_errors: true do hash do ... end end`; `run(params)` -> `valid?`, `errors.details` with **dotted/indexed keys** `{:"address.zip"=>[{error: :missing}], :"items[1].qty"=>[{error: :invalid_type, type: "integer"}]}` and `inputs.given?(:ship_on)` distinguishing "absent" from "nil".

## Validation & error model

**ActiveModel::Errors** (real output):

```ruby
validates :name, presence: true, length: {minimum: 3}
validates :age, numericality: {greater_than: 0}, allow_nil: true
validates :password, presence: true, on: :create
u.valid?(:create)          # => false ; u.valid? (no context) => true for a user w/o password
u.errors.messages          # {:name=>["is too short (minimum is 3 characters)"], :age=>["must be greater than 0"], :password=>["can't be blank"]}
u.errors.details           # {:name=>[{:error=>:too_short, :count=>3}], :age=>[{:error=>:greater_than, :value=>0, :count=>0}], :password=>[{:error=>:blank}]}
u.errors.full_messages     # ["Name is too short (minimum is 3 characters)", ...]   (format "%{attribute} %{message}")
u.errors.where(:name, :too_short).first  # ActiveModel::Error: attribute=:name type=:too_short options={:count=>3} message=... full_message=...
u.errors.of_kind?(:name, :blank) # false ; errors.added?(:name, :too_short, count: 3) => true
u.errors.add(:age, "must be sane")      # free string => details {:error=>"must be sane"}
u.errors.add(:base, :bad_combo, reason: "x")   # form-level, key :base, appears in full_messages without attribute prefix
u.errors.to_hash(true)     # full messages per attribute
User.validators_on(:name)  # [[PresenceValidator, {}], [LengthValidator, {minimum: 3}]]  <- what simple_form introspects
```

i18n chain (activemodel/lib/active_model/error.rb:79-94): `activemodel.errors.models.<model>.attributes.<attr>.<type>` -> `activemodel.errors.models.<model>.<type>` (walking ancestors) -> `activemodel.errors.messages.<type>` -> `errors.attributes.<attr>.<type>` -> `errors.messages.<type>`; `:message` option overrides; `%{model} %{attribute} %{value} %{count}` always interpolatable; `too_short`/`too_long`/`greater_than` use `count` and the pluralisation forms `one/other` (locale/en.yml). `Model.human_attribute_name(:born_on)` => `"Born on"` (i18n `activemodel.attributes.<model>.<attr>` else humanize). Contexts: `on: :create`; `valid?(:ctx)` runs unscoped + `:ctx` validators.

**dry-validation** (real output; contract in dry_validation_demo.rb):

```ruby
class NewUserContract < Dry::Validation::Contract
  option :taken_emails, default: proc { ["taken@x.com"] }      # injected dependency
  params do
    required(:email).filled(:string, format?: /@/)
    required(:age).filled(:integer)
    required(:address).hash { required(:city).filled(:string); required(:country).filled(:string) }
    required(:items).array(:hash) { required(:sku).filled(:string); required(:qty).filled(:integer) }
  end
  register_macro(:not_taken) { key.failure(:taken, email: value) if taken_emails.include?(value) }
  rule(:email).validate(:not_taken)
  rule(:age) { key.failure("must be at least 18 (got %{n})" % {n: value}) if value < 18 }
  rule(:password, :password_confirmation) { key(:password_confirmation).failure("must match password") if values[:password] != values[:password_confirmation] }
  rule(address: :city) { key.failure("we only ship to Munich") if value != "Munich" }
  rule(:items).each { |index:| key([:items, index, :qty]).failure("must be > 0") if value[:qty] <= 0 }
  rule { base.failure("form-level: ...") if values[:address][:country] == "XX" }
end
r.errors.to_h
# {:items=>{1=>{:sku=>["must be filled"], :qty=>["must be an integer"]}, 0=>{:qty=>["must be > 0"]}},
#  :email=>["taken@x.com is already taken"], :age=>["must be at least 18 (got 17)"],
#  :password_confirmation=>["must match password"], :address=>{:city=>["we only ship to Munich"]},
#  nil=>["form-level: address country must match shipping policy"]}       # base errors keyed nil
r.to_h   # typed: {:age=>17, :items=>[{:sku=>"a", :qty=>0}, {:sku=>"", :qty=>"x"}], ...}  (invalid leaves keep raw value)
r.error?([:items, 0, :qty]) => true ; r.error?("address.city") => true
```

Timing rule (verified by case 2): with `age: "abc"` the output is only `{:age=>["must be an integer"]}`; the `rule(:age)` block never ran because its key failed the schema, so rules can assume typed values. `rule(:nope)` on an undefined key raises `Dry::Validation::InvalidKeysError` at class-definition time. `key.failure(:too_many, max: 5)` resolves a symbol through the messages YAML with tokens (`"cannot exceed 5"`); `key.failure({text: :bad_code, code: "E42", severity: "warn"})` yields structured messages with `meta={:code=>"E42", :severity=>"warn"}` - errors carry machine metadata. Messages YAML (`dry_schema.errors.<predicate>` with `%{num}` tokens and per-key overrides `rules.email.filled?: "we need your email"`) verified in dry_demo case 5; `errors(full: true)` prefixes the key name.

## Form state (bound/unbound, touched, attempted values)

Rails has no touched/dirty concept in the *form*; the model is either fresh (unbound) or has been assigned params + `valid?` called (bound). Attempted values survive because helpers read from the (invalid, in-memory) model, and the lossy casts above are where this leaks (`age: "abc"` re-renders as `0`). ActiveModel::Dirty (`changed?`, `name_was`) exists but is model-level. Reform is explicitly two-phase: after `validate`, `form.title == "Nickelback Live"` while `album.title == "Old"` (real output: "model untouched"), and `form.changed?(:title)` reports twin-level changes. dry-schema has none: it's a pure function. Turbo's 422 re-render is full-form, so "touched" is emulated by only rendering errors when the object has errors (i.e. after a submit).

## Rendering & customization & styling

Rails: `field_error_proc` global wrapper (verified: label and input each wrapped in `<div class="field_with_errors">`); everything else is explicit per-helper options (`class:`, `data:`). `f.select(:cat, choices, include_blank: "-- pick --")` and `collection_select(..., {include_blank: true})` (renders `<option value="" label=" ">`). `f.field_name`/`f.field_id` (FormBuilder, form_helper.rb:1777/1797) expose the naming algorithm so hand-written HTML can stay consistent.

simple_form: `f.input :email` infers type (`lib/simple_form/form_builder.rb:555`, quoted above): explicit `as:` > custom mapping > `collection:` => `:select` > column type (`:timestamp`->`:datetime`, others pass through) > for strings, attribute-name regexes (`password`, `time_zone`, `country`, `email`, `phone`->`:tel`, `url`) > file attribute detection. Required: `required_by_validators?` (`helpers/required.rb:21`) = any `presence` validator whose `on:` matches the current action, else `required_by_default` config; HTML5 `required` attr only when `SimpleForm.browser_validations`. Components pull `maxlength`/`minlength`/`pattern`/`min`/`max` from `LengthValidator`/`FormatValidator`/`NumericalityValidator` options. Wrapper DSL from the generated initializer:

```ruby
config.wrappers :default, class: :input, hint_class: :field_with_hint, error_class: :field_with_errors, valid_class: :field_without_errors do |b|
  b.use :html5; b.use :placeholder
  b.optional :maxlength; b.optional :minlength; b.optional :pattern; b.optional :min_max; b.optional :readonly
  b.use :label_input
  b.use :hint,  wrap_with: { tag: :span, class: :hint }
  b.use :error, wrap_with: { tag: :span, class: :error }
end
# usage: f.input :name, wrapper: :bootstrap, input_html: {class: "x"}, wrapper_html: {...}, label: false, hint: "...", error: false
```
Per-call overrides: `input_html:`, `label_html:`, `wrapper_html:`, `as:`, `collection:`, `label_method:`/`value_method:`, `prompt:`; everything not recognised is forwarded to the input (`form_builder.rb:169`). Labels/hints/placeholders come from i18n `simple_form.{labels,hints,placeholders}.<model>.<attr>` (README ~740-800), so the template rarely states them.

superform: rendering is Ruby (Phlex). The README's pattern: subclass `Superform::Rails::Form`, override `Field#input` to return your component, add a `labeled(component)` helper that wraps `component.field.label` + `component` in `div.form-row` (README:180-212). Then a form is three lines: `labeled Field(:name).input; labeled Field(:email).input(type: :email); submit "Sign up"`. Real DOM output from the node tree: `user[address][street]` / `user_address_street`, `user[addresses][0][street]` / `user_addresses_0_street`, field-collection item `user[tags][]` (ids get a running counter `user_tags_3`).

## Nested / dynamic / conditional

Rails: has_one/belongs_to nesting via `fields_for(:author)`; has_many via `fields_for(:comments)` with `[i]` indices; removal via `_destroy`; creation via a hidden template row with a placeholder index (cocoon's `new_tasks`) swapped client-side; `reject_if` drops blank rows. Conditional sections are just Ruby `if` in the template + validators with `if:`/`unless:` lambdas and contexts. Turbo 422 re-render preserves nothing client-side except what the server re-emits.

dry-validation: `rule(:items).each { |index:| ... }`, `rule(address: :city)`, conditional rules are plain Ruby in the rule block (`values[:kind] == "company"`); `Dry::Schema` also supports `.each`/`schema` composition and `Dry::Types` sum types, but discriminated unions need custom code (unverified beyond docs summaries).

Reform: `collection :songs, populate_if_empty: Song, skip_if: :all_blank` (real: blank row skipped, third row created); custom `populator: ->(fragment:, collection:, index:, **) { ...; skip! }` implements delete-by-flag (real: `items now: ["kept", ""]` after deleting the row flagged `delete=1`); `prepopulator:` fills defaults for rendering (`pf.prepopulate!(default_title: "Untitled")` => `songs=["empty slot"]`). Nested errors: `{:"artist.name"=>["must be filled"], :"songs.length"=>["must be greater than 0"]}` at the top, and per-nested-form `form.songs[1].errors.messages => {:length=>[...]}` - note the dotted key loses the index, a real weakness for lists.

superform: `namespace(:address) { |a| a.field(:city) }`, `collection(:addresses) { |addr| addr.field(:street) }`, `field(:tags).collection`; `form.assign(params)` writes through only defined nodes (`hacked: "ignored"` dropped; verified), `form.serialize` gives the same tree as a hash; no dynamic add/remove story of its own (it relies on Rails/Turbo/Stimulus).

## DX highlights with real code (cited)

1. `errors.add(:name, :too_short, count: 3)` + `errors.where(:name, :too_short)` + `details` - typed errors that stay renderable in any language (rails_demo.rb output above; error.rb:79-94 for the key chain).
2. `f.input :email` => type + label + hint + placeholder + required + maxlength from model metadata and i18n (simple_form form_builder.rb:555, helpers/required.rb:21, components/*.rb).
3. dry-schema one-liner processor: `Dry::Schema.Params { required(:age).value(:integer, gt?: 0); required(:tags).array(:string) }.call(params).to_h` => `{age: 3, tags: [...]}` with `errors.to_h` nested (dry_demo.rb cases 1-2).
4. dry-validation `rule(:password, :password_confirmation) { key(:password_confirmation).failure(...) }` runs only on schema-clean values and targets a specific key; `base.failure` for form-level (dry_validation_demo.rb).
5. Reform lifecycle `form.validate(params) && form.save { |nested_hash| ... }` - the block form hands you the clean nested hash `{"title"=>..., "artist"=>{...}, "songs"=>[...]}` (real output) without touching models.
6. superform `Superform(:user, object: user) { |f| f.field(:name); f.namespace(:address) { |a| a.field(:city) } }.serialize` doubles as the permitted-params whitelist (README:557 "automatically permits only the parameters that correspond to fields defined in your form"; verified `assign` ignores undefined keys).
7. ActiveInteraction `errors.details` keyed `"items[1].qty"` with `{error: :invalid_type, type: "integer"}` - a flat, path-addressable error map for nested input (ai_demo.rb).

## Pain points & criticisms (cited)

- Lossy ActiveModel casts: `"abc"` -> `0`, `"2020-02-30"` -> `nil`, re-rendering the cast value instead of what the user typed (verified above). dry-schema's "error instead of coerce" is the better default.
- `parse_nested_query` quirks: `a[0]` is a hash with string keys, `a[]` vs `a[b]` conflict raises `ParameterTypeError`, repeated `a[][b]` groups by key repetition, so ordering of inputs matters (verified). Indexed hashes are why Rails needs `id`/`_destroy` hidden inputs and `reject_if`.
- Hidden-input hacks (`check_box` hidden `0`, multi-select hidden `""`) leak into the server (`""` in arrays must be stripped; `date_select` needs multiparameter `(1i)` assembly).
- `field_error_proc` wrapping breaks CSS layouts and is global; simple_form exists largely to fix that.
- Reform's dotted nested error keys drop collection indices (`"songs.length"`), and its populator API (`fragment:, collection:, index:`, `skip!`) is powerful but arcane; the demo needed two fixes to get delete semantics right. disposable/representable stack is heavy and slow-moving (reform 2.6.2 is from 2020 - unverified exact date).
- dry-validation: `rule` keys must exist in the schema (raises `InvalidKeysError`), base errors keyed `nil` in `errors.to_h`, `errors(full: true)` prefixes with raw key names (`"password_confirmation must match password"`) - no human attribute names without extra work.
- simple_form's type inference by attribute *name* regex (`/password/`, `/email/`) is convenient but surprising (`email_notifications` boolean column is fine since the column type wins, but `string` columns named `url_shortener` become `:url`).
- superform requires committing to Phlex for the whole form and has no built-in validation/error rendering beyond `field.errors` (unverified extent), and no dynamic collection UI.

## Lessons for pyview - steal / adapt / avoid

**Steal**
1. Rack's bracket naming + a real `parse_nested_query` port (including `[]`, `[key]`, `[][key]` grouping, string `"0"` indices) - pyview currently has literal `"user[address][city]"` keys. Make the decoder convert `{"0": ..., "1": ...}` dicts whose keys are all ints into lists *before* handing to Pydantic, and keep a placeholder-index convention (`new_<field>`/timestamp) for client-cloned rows like cocoon.
2. Typed error objects with a code+params+i18n chain: `Error(path=("items",1,"qty"), type="greater_than", params={"count": 0}, message=...)`; `errors.where(path, type)`, `of_kind`, `full_message` with `human_attribute_name`, `base` for form-level. Pydantic's `ValidationError.errors()` already gives `loc`, `type`, `ctx`, `msg` - map that 1:1 and add a Rails-style override chain (`errors.models.<Model>.attributes.<field>.<type>` -> `errors.messages.<type>`).
3. dry-schema's *input-source coercion layer*: a `Params` pre-processor that turns `""` -> `None` for Optional fields, `"0"/"1"/"on"/"true"` -> bool, strips hidden-checkbox `"0"` and multi-select `""` sentinels, assembles multipart dates - run BEFORE Pydantic (which is a `JSON`-style strict processor). Never coerce lossily; on failure keep the raw string in `changes` and add an error (dry's behaviour, not ActiveModel's).
4. dry-validation's schema-then-rules split: run Pydantic field validation first, then `rule("password", "password_confirmation")`-style cross-field callables only over fields that passed, targeting a key path or `base`. Add `.each` on list fields with an `index` kwarg. Reject rules on unknown paths at class-definition time.
5. simple_form's wrapper DSL as the styling contract: a named component pipeline (`label`, `input`, `hint`, `error`, `wrapper tag/class`, `error_class`, `valid_class`) configured once per app/theme, `input_html`/`wrapper_html` per call; plus type inference from Pydantic field type + name (`EmailStr`, `SecretStr`, `date`, `bool`, `Literal`/`Enum` -> select, `list[Enum]` -> multi-select) and `required`/`min`/`max`/`maxlength`/`pattern` derived from `Field(...)` constraints (simple_form's validator introspection).
6. superform's single-tree principle: the form definition (or the Pydantic model) generates `name`, `id`, values, permitted keys, and serialisation; `Field` nodes are what templates render (`{{ form.address.city.input }}` style), so custom HTML still gets correct names via `field.name`/`field.id`/`field.value`/`field.errors` (Rails `field_name`/`field_id` equivalents).

**Adapt**
- Reform's two-phase state (`validate` fills the form/twin, `sync`/`save` touches the model) maps onto changesets: `changeset.changes` (typed), `changeset.params` (raw attempted values for re-render), `changeset.apply()` -> model only when valid. Keep populator-like hooks for lists (`populate_if_empty`, `skip_if="all_blank"`, `_destroy` flag) but express them declaratively on the field.
- Turbo's 422 re-render is what LiveView already does over the socket; keep phx-change validation per `_target` but validate the full model and filter errors by "used/touched" paths (LiveView 1.0 `_unused_` semantics) instead of Rails' submit-only model.

**Avoid**
- Lossy silent casts (`"abc"` -> 0) and rendering cast values back; always re-render the attempted raw value.
- Global `field_error_proc`-style DOM wrapping; make error decoration part of the wrapper pipeline.
- Dotted string error keys that lose list indices (Reform `"songs.length"`, ActiveInteraction `"items[1].qty"` string); use tuple paths and nested dicts (`errors.to_h` style) with a helper to address `["items", 1, "qty"]`.
- Hidden-input sentinels as an API surface: hide them inside the checkbox/multi-select widgets and strip them in the Params processor so user code never sees `"0"`/`""`.

## Sources (actually read / executed)
- Executed: `scratchpad/research/rb/rails_demo.rb`, `dry_demo.rb`, `dry_validation_demo.rb` (+`custom_errors.yml`), `reform_demo.rb`, `superform_demo.rb`, `ai_demo.rb` against gems in `scratchpad/pkgs/gems-reform_dry` (racc, rake added).
- `repos/rack` (rack 3.2.7 gem used at runtime for `Rack::Utils.parse_nested_query`).
- `repos/rails/activerecord/lib/active_record/nested_attributes.rb` (lines 303, 356, 412, 491-585); `activemodel/lib/active_model/error.rb` (26-97); `activemodel/lib/active_model/locale/en.yml`; `actionview/lib/action_view/helpers/form_tag_helper.rb` (101, 131), `form_helper.rb` (1777, 1797), `action_view/base.rb` (163-166 field_error_proc).
- `repos/simple_form/lib/simple_form/form_builder.rb` (169, 541-580, 635), `lib/simple_form/helpers/required.rb`, `helpers/validators.rb`, `components/{html5,maxlength,minlength,pattern,min_max,placeholders,labels}.rb`, `lib/generators/simple_form/templates/config/initializers/simple_form.rb`, README (i18n section).
- `repos/cocoon/README.markdown` (88-120, 239-260, 389-445), `lib/cocoon/view_helpers.rb` (29-99), `app/assets/javascripts/cocoon.js` (52-62).
- `repos/turbo-site/_source/handbook/02_drive.md` (line 337, 422 handling).
- `repos/superform/README.md` (54, 180-215, 270-310, 414-423, 536-560).
- `repos/reform/README.md` (44-46, 83-160, 234-236).
- dry-schema/dry-validation docsite pages were not present in the clones; behaviour claims come from executed code against dry-schema 1.16.0 / dry-validation 1.11.1.
