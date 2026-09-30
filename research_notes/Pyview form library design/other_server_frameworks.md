# Form handling in other server-side / server-driven frameworks and in the functional tradition (transferable ideas for a pyview form library)

> Method note: most official doc sites (guides.rubyonrails.org, livewire.laravel.com, filamentphp.com, learn.microsoft.com, playframework.com, vaadin.com, dry-rb.org, dev.to, reddit) were blocked by this environment's egress proxy. I read the **source Markdown of the official docs from their GitHub repos** instead: rails/rails `guides/source` (main), livewire/livewire `docs` (main = 4.x), filamentphp/filament `4.x`/`5.x`, laravel/docs `13.x`, dotnet/AspNetCore.Docs (main), playframework (main), vaadin/docs (main), streamlit/docs (main). All were at commits from late September 2026, so they reflect current docs. Community opinions come mostly from web-search snippets and GitHub discussions and are marked as such. I could not open the formlets paper PDF, so I reconstructed its core type from the Haskell `formlets` package source. The paper's Links-syntax example is quoted from memory and marked unverified.

---

## Ruby on Rails: form_with / FormBuilder / fields_for / nested attributes / strong params / simple_form & formtastic / form objects (Reform, dry-validation) / Hotwire nested fields

### Takeaway
Rails has three layers. (1) A **path-based param naming convention** (`person[addresses_attributes][0][street]`) that the server parses into nested hashes. (2) A **FormBuilder object** scoped to a model or sub-model. You customize it by subclassing, and `fields_for` gives nested builders. (3) Model-side `accepts_nested_attributes_for`, which handles `_destroy`, `reject_if` and `allow_destroy`. simple_form adds the most transferable styling idea: a **declarative "wrappers" pipeline** of named components (label/input/hint/error), plus per-field overrides (`as:`, `wrapper:`, `input_html:`). Form-object libraries (Reform, dry-validation) pull validation **out of the model** into a separate contract.

### Cited Findings

**form_with, FormBuilder and custom builders**
- `form_with` (Rails 5.1+) replaced `form_tag`/`form_for`. Both are now "discouraged in favor of `form_with`" (so they are effectively deprecated) — [Rails guide: form_helpers.md](https://github.com/rails/rails/blob/main/guides/source/form_helpers.md)
- You customize by subclassing `ActionView::Helpers::FormBuilder` and calling `super`, so you can override one helper without rewriting the others — [Rails guide](https://github.com/rails/rails/blob/main/guides/source/form_helpers.md):
  ```ruby
  class LabellingFormBuilder < ActionView::Helpers::FormBuilder
    def text_field(attribute, options = {})
      label(attribute) + super   # super calls the original text_field
    end
  end
  # per form:  form_with model: @person, builder: LabellingFormBuilder do |form| ...
  # or wrap:   def labeled_form_with(**options, &block)
  #              options[:builder] = LabellingFormBuilder; form_with(**options, &block); end
  ```
  The builder class also picks the partial: `render partial: f` renders `labelling_form` for a `LabellingFormBuilder` and `form` for the default builder — [Rails guide](https://github.com/rails/rails/blob/main/guides/source/form_helpers.md)
- Output shows the id/name derivation: `<label for="person_first_name">`, `<input name="person[first_name]" id="person_first_name">` — [Rails guide](https://github.com/rails/rails/blob/main/guides/source/form_helpers.md)

**Param naming convention (the wire format)**
- "HTML forms don't have an inherent structure to the user input data, all they generate is name-value string pairs. The arrays and hashes you see in your application are the result of parameter naming conventions that Rails uses." — [Rails guide](https://github.com/rails/rails/blob/main/guides/source/form_helpers.md)
  - `person[address][city]` gives `{"person"=>{"address"=>{"city"=>...}}}`
  - `person[phone_number][]` repeated gives an array
  - `person[addresses][][line1]` gives an array of hashes. **"only one level of 'arrayness' is allowed. Arrays can usually be replaced by hashes"** (for example, keyed by id)
  - Checkbox gotcha: array params "do not play well with the `checkbox` helper". The helper emits an auxiliary hidden input so an unchecked box still submits a value.
- `fields_for address, index: address.id` renders `person[address][23][city]`, so the server knows which record each row belongs to — [Rails guide](https://github.com/rails/rails/blob/main/guides/source/form_helpers.md)

**Nested attributes (`accepts_nested_attributes_for`)**
- The model declares it, which creates `addresses_attributes=` — [Rails guide](https://github.com/rails/rails/blob/main/guides/source/form_helpers.md):
  ```ruby
  class Person < ApplicationRecord
    has_many :addresses, inverse_of: :person
    accepts_nested_attributes_for :addresses, allow_destroy: true,
      reject_if: lambda { |attributes| attributes["kind"].blank? }   # or reject_if: :all_blank
  end
  ```
  ```erb
  <%= form.fields_for :addresses do |addresses_form| %>
    <%= addresses_form.checkbox :_destroy %>
    <%= addresses_form.text_field :kind %>
  <% end %>
  ```
  This renders `name="person[addresses_attributes][0][kind]"`, `id="person_addresses_attributes_0_kind"` and `name="person[addresses_attributes][0][_destroy]"`. "The actual value of the keys in the `:addresses_attributes` hash is not important. But they need to be strings of integers and different for each address." For persisted children, `fields_for` auto-emits a hidden `id` input (disable it with `include_id: false`).
- `fields_for` renders nothing when the association is empty. The idiom is to build blank children in the controller (`2.times { @person.addresses.build }`) — [Rails guide](https://github.com/rails/rails/blob/main/guides/source/form_helpers.md)
- `_destroy` truthy values are `1`, `'1'`, `true` and `'true'`. `:all_blank` rejects records whose attributes are all blank, ignoring `_destroy` — [Rails guide](https://github.com/rails/rails/blob/main/guides/source/form_helpers.md)

**Strong parameters**
- The current guide uses `params.expect`. It must describe nested arrays of hashes with a **double array**, `[[...]]` — [Rails guide](https://github.com/rails/rails/blob/main/guides/source/form_helpers.md), [action_controller_overview.md](https://github.com/rails/rails/blob/main/guides/source/action_controller_overview.md):
  ```ruby
  params.expect(person: [ :name, addresses_attributes: [[ :id, :kind, :street ]] ])
  params.expect(users: [[:name]])  # => array of permitted hashes; users: [:name] raises ParameterMissing
  ```
  "`expect` is strict with types." "Nested hashes and arrays must be specified, including any nested keys, or they will be filtered out." `params.expect(user: {})` permits everything but "bypasses the security aspects of strong parameters". The older `params.require(:person).permit(...)` still appears in the same guide's `_destroy` example.

**Error display and Turbo**
- The Getting Started guide re-renders with `render :new, status: :unprocessable_entity` (422) so "the browser [knows] this POST request failed", and shows `form.object.errors.full_messages.first` — [getting_started.md](https://github.com/rails/rails/blob/main/guides/source/getting_started.md)
- simple_form's wrapper config uses the Rails-standard `error_class: :field_with_errors` — [simple_form README](https://github.com/heartcombo/simple_form)

**simple_form (wrappers API, inputs, per-field overrides)**
- `f.input :attr` infers the input type from the DB column type and from the name. For example, a `string` column named `/email/` becomes `input[type=email]`, `/password/` becomes password, `text` becomes textarea, `boolean` becomes checkbox, and `belongs_to` becomes select — [simple_form README](https://github.com/heartcombo/simple_form)
- Wrappers are a declarative pipeline of components (`:label`, `:input`, `:label_input`, `:hint`, `:error`) and "extensions" (`:html5`, `:placeholder`, `:maxlength`, `:pattern`, `:readonly`) — [simple_form README](https://github.com/heartcombo/simple_form):
  ```ruby
  config.wrappers tag: :div, class: :input,
                  error_class: :field_with_errors, valid_class: :field_without_errors do |b|
    b.use :html5
    b.optional :pattern          # only when explicitly enabled per input
    b.use :maxlength
    b.use :placeholder
    b.use :label_input, class: 'label-input-class', error_class: 'is-invalid', valid_class: 'is-valid'
    b.wrapper :my_wrapper, tag: :div, class: 'separator' do |component|
      component.use :hint,  wrap_with: { tag: :span, class: :hint }
      component.use :error, wrap_with: { tag: :span, class: :error }
    end
  end
  config.wrappers :small do |b| b.use :placeholder; b.use :label_input end
  ```
  You pick a wrapper per form (`simple_form_for @user, wrapper: :small`) or per input (`f.input :name, wrapper: :small`). Named sub-wrappers can be tweaked per input (`my_wrapper: false`, `my_wrapper_html: {id: ...}`, `my_wrapper_tag: :p`). `unless_blank: true` skips empty wrappers.
- Per-field overrides that don't require ejecting: `as: :text`, `input_html: {class:}`, `label_html:`, `wrapper_html:`, `hint:`, `f.error :x`, `f.full_error :x` — [simple_form README](https://github.com/heartcombo/simple_form)
- Custom and overridden inputs are discovered by class name. `app/inputs/currency_input.rb` defines `CurrencyInput < SimpleForm::Inputs::Base` and you use it as `f.input :price, as: :currency`. Redefining a built-in by name (`class CollectionSelectInput < SimpleForm::Inputs::CollectionSelectInput; def input_html_classes; super.push('chosen'); end; end`) changes **all** selects app-wide. `config.custom_inputs_namespaces << "CustomInputs"` avoids collisions — [simple_form README](https://github.com/heartcombo/simple_form)
- simple_form works on any object that includes `ActiveModel::Model`, which is how form objects plug in — [simple_form README](https://github.com/heartcombo/simple_form)
- Bootstrap 5 via `rails generate simple_form:install --bootstrap`. Per a search summary, there is "no Tailwind-specific configuration baked in", so third-party gems such as `simple_form_tailwind_css` fill the gap — [AppSignal blog (2024)](https://blog.appsignal.com/2024/05/15/creating-forms-in-ruby-on-rails-with-simple-form.html), [simple_form_tailwind_css](https://github.com/abevoelker/simple_form_tailwind_css), [dev.to nejremeslnici](https://dev.to/nejremeslnici/styling-simple-form-forms-with-tailwind-4pel)
- Praise and trade-off, per a search summary: use simple_form "when your app has many CRUD-style forms and you want labels, hints, and validation errors generated from one f.input call per field". Stick with `form_with` for "heavily customized designs, or zero extra dependencies" — [AppSignal blog](https://blog.appsignal.com/2024/05/15/creating-forms-in-ruby-on-rails-with-simple-form.html)

**formtastic**
- `semantic_form_for` plus `f.inputs` groups (`f.inputs :name => "Advanced" do ...`) and `f.input :x, :as => :radio`. A bare `f.inputs` renders "one for _most_ columns in the database table, and one for each ActiveRecord `belongs_to`-association". Formtastic 6.x requires Rails 7.2+ — [formtastic README](https://github.com/formtastic/formtastic)

**Form objects: Reform and dry-validation (contract separate from model)**
- Reform: "Form objects decoupled from your models … validations no longer go into the model." The API is `validate(params)`, which updates only the form (the model stays unchanged) and runs validations, plus `errors`, `sync` (write back to the model), `save` and `prepopulate!`. It supports nested `property :artist do ... end` and `collection :songs do ... end`, reuse via `property :artist, form: ArtistForm`, and composition of multiple models (`property :title, on: :album`). dry-validation is the "recommended" validation backend — [Reform README](https://github.com/trailblazer/reform):
  ```ruby
  class AlbumForm < Reform::Form
    property :title
    validates :title, presence: true
    property :artist do
      property :full_name
      validates :full_name, presence: true
    end
    collection :songs do
      property :name
    end
  end
  ```
- dry-validation: "Strict, explicit data schemas are separated from the domain validation logic". Schemas (dry-schema) "sanitize, coerce and type-check", and "Contract rules are applied only once the values they rely on have" passed the schema — [dry-validation docs source](https://github.com/dry-rb/dry-validation/blob/release-1.10/docsite/source/index.html.md):
  ```ruby
  class NewUserContract < Dry::Validation::Contract
    params do
      required(:email).filled(:string)
      required(:age).value(:integer)
    end
    rule(:age) { key.failure('must be greater than 18') if value <= 18 }
  end
  NewUserContract.new.call(email: 'jane@doe.org', age: '17')
  # => Result{:email=>"jane@doe.org", :age=>17} errors={:age=>["must be greater than 18"]}
  ```

**Dynamic nested fields (cocoon, then Stimulus/Turbo)**
- cocoon "depends on jQuery". Its README says it is compatible with Rails 3–5, and the last commit is 2022-06-08. Treat it as **legacy/deprecated** for new apps — [cocoon repo](https://github.com/nathanvda/cocoon)
- The current idiom renders a `<template>` holding `f.fields_for :tasks, Task.new, child_index: "NEW_RECORD"`. A Stimulus controller clones it and replaces `NEW_RECORD` with `Date.getTime()`. On remove, it deletes new rows from the DOM, or sets the hidden `_destroy=1` and hides persisted rows. Turbo Streams can also append rows server-side. Sources are search-result summaries only (pages blocked) — [Jonathan Yeong](https://jonathanyeong.com/writing/rails-stimulus-dynamic-nested-form/), [millarian.com "Nested Forms in Rails 8: Life After Cocoon"](https://millarian.com/posts/nested-forms-in-rails-8/), [code.avi.nyc Turbo Streams](https://code.avi.nyc/rails-nested-forms-with-turbo-streams)

**Criticisms of nested attributes**
- Per a search summary, `accepts_nested_attributes_for` "turns the feature on globally and cannot just be made available at the controller level" (authorization lives in controllers) and "is not able to help avoid duplicates". An alternative is separate per-child forms with auto-save plus Turbo Streams — [Rails Designer](https://railsdesigner.com/nested-forms-without-accepts-nested-attributes/). The skepticism is long-standing — [SmartLogic 2009](https://smartlogic.io/blog/2009-02-24-rails-23-nested-object-forms-im-not-crazy-about-them/)

### Inferences
- **Wire format:** pyview needs *one* canonical path encoding shared by input `name`s, error keys and the parser. Rails brackets (`user[addresses][0][street]`) are the most widely understood, and Phoenix/Plug use the same format. Rails' "one level of arrayness" limit and the "keys only need to be distinct" rule argue for **dict-keyed lists** (`items[<stable-key>][field]`) over positional `[]`. This matters more in LiveView, where rows are added and removed between renders.
- **Stable row keys:** Rails `child_index: "NEW_RECORD"` → timestamp and `index: address.id` both show that rows need a stable identity that is not their position. pyview could generate a key per sub-form row (uuid or counter) and keep an ordering field (`_order`) separately.
- **`_destroy` + `reject_if` + `allow_destroy`** is a reusable vocabulary for list editing that doesn't depend on ORMs. In pyview it can be a *form-level* concern (drop, mark-deleted, ignore blank rows) rather than a model concern. That also answers the "global at model level" criticism.
- **Strong params ≈ declared paths.** A pydantic/dataclass-derived form already knows its allowed paths, so it can silently drop (or reject) undeclared keys. The double-array `[[...]]` in `params.expect` shows how awkward it is to express "list of objects" by hand, which is a reason to derive it from type annotations.
- **simple_form's wrappers** map cleanly to a Python "field template" pipeline: an ordered list of named slots (label, input, hint, errors) with per-slot classes, a named-wrapper registry chosen per form or per field, and `optional` slots that render only when enabled. Class-name-based input lookup (`as: :currency` → `CurrencyInput`) maps to a registry keyed by name or type.
- **Reform/dry-validation** match pydantic almost exactly. The "schema" is pydantic field types and coercion. "Rules" are `@model_validator`/`@field_validator`, and like dry-validation they should only run when the fields they depend on parsed successfully. A pyview form object should hold raw input and errors *without mutating the target model* until `sync`/`save` (Reform's key design choice).

### Gaps
- Could not fetch api.rubyonrails.org for `field_error_proc` (the default `<div class="field_with_errors">` wrapper) or `default_form_builder` configuration details.
- The criticism pages (railsdesigner, millarian) were blocked. Claims come from search-engine summaries.
- I did not verify which Rails version introduced `params.expect`. I believe it is Rails 8.0, but the guide does not say.

---

## Laravel: Livewire form objects, #[Validate], real-time validation, nested/array properties, FormRequest, Filament schema builder (conditional/dependent fields, Repeater, Builder)

### Takeaway
Livewire is the closest analogue to pyview. Form state lives in public server properties, bound by **dot paths** (`wire:model="form.items.0.name"`). Updates are **deferred by default** and become live per field (`.live`, `.blur`, `.debounce`). `#[Validate]` rules run **on each property update** and on `validate()`, and errors are keyed by the same dot path. Filament layers a **server-side schema of field objects** on top. Every setting accepts a closure with injected `Get`/`Set`, a field can be marked `->live()` to trigger schema re-evaluation, and it has lifecycle hooks (hydrate, update, dehydrate), partial re-rendering, and `Repeater`/`Builder` for lists and polymorphic block lists. This is the richest model for conditional nesting, and it also documents the performance costs of server round-trips.

### Cited Findings

**Livewire (docs on main are 4.x; examples use v4 single-file components `⚡create.blade.php`)**
- Basic binding: `<form wire:submit="save"><input type="text" wire:model="title">`. `#[Validate('required')]` on a public property. `$this->validate()` in the action. `@error('title') <span class="error">{{ $message }}</span> @enderror` — [Livewire forms.md](https://github.com/livewire/livewire/blob/main/docs/forms.md)
- **Form objects** (`php artisan livewire:form PostForm`) — [Livewire forms.md](https://github.com/livewire/livewire/blob/main/docs/forms.md):
  ```php
  class PostForm extends Form {
      public ?Post $post;
      #[Validate('required|min:5')] public $title = '';
      #[Validate('required|min:5')] public $content = '';
      public function setPost(Post $post) { $this->post = $post; $this->title = $post->title; $this->content = $post->content; }
      public function store()  { $this->validate(); Post::create($this->only(['title', 'content'])); $this->reset(); }
      public function update() { $this->validate(); $this->post->update($this->only(['title','content'])); }
  }
  // component: public PostForm $form;  save(): $this->form->store();
  // view: <input wire:model="form.title">  @error('form.title') ... @enderror
  ```
  `reset()` restores declared defaults (typed properties without defaults become *uninitialized*). `pull()` means "retrieve and reset".
- Instead of attributes you can define a `rules()` method, which is needed for `Rule::unique('posts')->ignore($this->post)`. Rules from `rules()` run **only on `validate()`**. An empty `#[Validate]` on a property opts that property back into per-update validation — [Livewire forms.md](https://github.com/livewire/livewire/blob/main/docs/forms.md)
- `#[Validate]` options include `as:` (attribute name in messages), `message:` (custom text, can stack multiple attributes), `translate: false`, and `onUpdate: false` (don't validate on update; call `$this->form->validate()` manually). There is also an array form for a property and its children — [Livewire validation.md](https://github.com/livewire/livewire/blob/main/docs/validation.md):
  ```php
  #[Validate(['todos' => 'required', 'todos.*' => ['required', 'min:3', new Uppercase]])]
  public $todos = [];
  ```
- **Real-time validation:** with `.live`/`.blur`, "Each of those network requests will run the appropriate validation rules before updating each property. If validation fails, the property won't be updated on the server and a validation message will be shown" — [Livewire forms.md](https://github.com/livewire/livewire/blob/main/docs/forms.md)
- **Livewire 4 modifier semantics (changed from v3):** `wire:model` syncs only when an action runs. `.live` sends on input with a default 150 ms debounce (per wire-model.md). forms.md says "250ms", which is an internal docs inconsistency. `.blur` "delays syncing until the user clicks away", and **to also send a request on blur you need `.blur.live`/`.live.blur`**. Other modifiers: `.change`, `.enter`, `.debounce.Xms`, `.throttle.Xms`, `.renderless`, and `.lazy` ("v3 compatible") — [Livewire wire-model.md](https://github.com/livewire/livewire/blob/main/docs/wire-model.md), [forms.md](https://github.com/livewire/livewire/blob/main/docs/forms.md)
- Nested paths: `wire:model="address.city"`, `"items.0.name"`, `"form.title"`, with bracket equivalents `address['city']` and `items[0].name` — [wire-model.md](https://github.com/livewire/livewire/blob/main/docs/wire-model.md)
- Dependent selects need `wire:key="{{ $selectedState }}"` on the child select so it re-initializes when options change — [wire-model.md](https://github.com/livewire/livewire/blob/main/docs/wire-model.md)
- UX helpers: the submit button is auto-disabled and inputs are set `readonly` during submission. A `data-loading` attribute is available for Tailwind (`in-data-loading:hidden`). `wire:dirty.class="border-yellow"` and `<div wire:dirty wire:target="title">Unsaved...</div>` show unsynced fields. The `updated($name, $value)` hook supports autosave — [forms.md](https://github.com/livewire/livewire/blob/main/docs/forms.md)
- Error API: `$this->addError(key, msg)` (auto-prefixed with the form property name inside form objects, e.g. `data.key`), `resetValidation(?key)`, `withValidator(fn($v) => ...)`. Any thrown `ValidationException` is caught and shown. The client can read `$errors.has/first/get/all/clear` (e.g. `wire:show="$errors.has('email')"`) — [validation.md](https://github.com/livewire/livewire/blob/main/docs/validation.md)
- **Deprecated:** `#[Rule]` was renamed to `#[Validate]` because of naming conflicts with Laravel Rule objects — [validation.md](https://github.com/livewire/livewire/blob/main/docs/validation.md)
- Reusable inputs: Blade components with `@props(['name'])` forward `{{ $attributes }}` (including `wire:model`) to the inner `<input>` and render `@error($name)`. A fully custom control uses Alpine `x-modelable="count"` so `wire:model` binds to its internal state. A child *Livewire* component can expose one `#[Modelable] public $value` so the parent can `wire:model` it ("only supports a single `#[Modelable]` attribute") — [forms.md](https://github.com/livewire/livewire/blob/main/docs/forms.md), [nesting.md](https://github.com/livewire/livewire/blob/main/docs/nesting.md)
- **Pain point, nested arrays:** a discussion from January 2024 reports that real-time `#[Validate]` doesn't trigger for array sub-keys (e.g. `email_settings.rspamd_reject_score`) in Livewire 3.4.1. The workaround `updatedBilling() { $this->validate(); }` "causes unexpected behavior when using form classes". The maintainer asked for a failing test, and it remained largely unresolved through September 2024 — [livewire discussion #7839](https://github.com/livewire/livewire/discussions/7839). Similar threads exist: [#7704](https://github.com/livewire/livewire/discussions/7704), [#6890](https://github.com/livewire/livewire/discussions/6890) (validating an array of objects wiped the values)

**Laravel FormRequest / validation (docs branch 13.x)**
- `php artisan make:request StorePostRequest` gives a class with `authorize()` and `rules()`. You type-hint it in the controller and it is validated before the action runs. `$request->validated()`, `$request->safe()->only([...])`. `after()` returns closures or invokables for cross-field checks. Class attributes include `#[StopOnFirstFailure]`, `#[FailOnUnknownFields]`, `#[RedirectTo]` and `#[ErrorBag('login')]` — [laravel/docs validation.md](https://github.com/laravel/docs/blob/13.x/validation.md)
- Nested rules use dot paths (`'author.name' => ['required']`) and wildcards (`photos.*.description`). Escape literal dots with `'v1\.0'`. On failure, input is flashed and `old('title')` repopulates the form. `exclude_if:field,value` / `Rule::excludeIf(closure)` **removes a field from the validated data** when a condition holds — [validation.md](https://github.com/laravel/docs/blob/13.x/validation.md)
- **Precognition** runs a route's FormRequest validation for a "precognitive request" without executing the controller, which gives "live" validation "without having to duplicate your validation rules" in the frontend. It is built into Inertia 2.3+ — [precognition.md](https://github.com/laravel/docs/blob/13.x/precognition.md)

**Filament (v4.x docs; 5.x forms docs are identical apart from version tags; 5.x targets Livewire v4; a 6.x branch exists)**
- Mounting a form in a Livewire component: `implements HasSchemas`, `use InteractsWithSchemas`, `public ?array $data = []`, `mount(): $this->form->fill()` (required "even if it doesn't have any initial data"), and `form(Schema $schema)` returning `->components([...])->statePath('data')`. In the view, `{{ $this->form }}`. Submit with `$this->form->getState()` ("use this method instead of accessing the `$this->data` property directly, because the form's data needs to be validated and transformed") — [Filament docs/12-components/02-form.md](https://github.com/filamentphp/filament/blob/4.x/docs/12-components/02-form.md); branch/README evidence: [5.x README](https://github.com/filamentphp/filament/blob/5.x/README.md)
- Fields are fluent objects: `TextInput::make('name')->required()->maxLength(255)->label('Full name')`. Dot notation binds nested keys (`TextInput::make('socials.github_url')`). The label is derived from the name. Rule methods also give "frontend validation" and IDE autocomplete — [forms/01-overview.md](https://github.com/filamentphp/filament/blob/4.x/packages/forms/docs/01-overview.md)
- **Almost every setting accepts a closure with named-parameter utility injection** (`$state`, `$rawState`, `Get $get`, `Set $set`, `$record`, `$operation`, `$component`, `$livewire`, `$old`) — [01-overview.md](https://github.com/filamentphp/filament/blob/4.x/packages/forms/docs/01-overview.md):
  ```php
  Select::make('role')->options(['user'=>'User','staff'=>'Staff'])->live();
  Toggle::make('is_admin')->hidden(fn (Get $get): bool => $get('role') !== 'staff');
  TextInput::make('middle_name')->required(fn (): bool => auth()->user()->hasMiddleName());
  Toggle::make('is_admin')->disabledOn('edit');   // operation-aware: create/edit/view
  ```
  Typed getters: `$get->string('email')`, `->integer`, `->boolean`, `->enum('status', StatusEnum::class)`, `->filled`, `->blank`, `isNullable: true`.
- **Reactivity:** "By default, when a user uses a field, the schema will not re-render." `->live()` re-renders on change. Other forms are `->live(onBlur: true)` and `->live(debounce: 500)`. `Get` on a non-live field only sees the new value on the *next* request — [01-overview.md](https://github.com/filamentphp/filament/blob/4.x/packages/forms/docs/01-overview.md)
- **Client-side escape hatches** avoid round-trips: `hiddenJs(<<<'JS' $get('role') !== 'staff' JS)`, `visibleJs()` and `afterStateUpdatedJs()`. These run JS expressions with `$get`/`$set` in the browser, and the docs carry XSS warnings — [01-overview.md](https://github.com/filamentphp/filament/blob/4.x/packages/forms/docs/01-overview.md)
- **Lifecycle** — [01-overview.md](https://github.com/filamentphp/filament/blob/4.x/packages/forms/docs/01-overview.md):
  - Hydration (on `fill()`): `afterStateHydrated`, `formatStateUsing(fn ($state) => ucwords($state))`.
  - Update: `afterStateUpdated(function (?string $state, ?string $old) {...})`, with `$set('title', 'x', shouldCallUpdatedHooks: true)`.
  - Dehydration (on `getState()`): `dehydrateStateUsing(...)`. `saved(false)` excludes a field from state (for example `password_confirmation`), but "Even when a field is not saved, it is still validated". Opt out with `validatedWhenNotDehydrated(false)` — [23-validation.md](https://github.com/filamentphp/filament/blob/4.x/packages/forms/docs/23-validation.md)
  - Disabled fields are not saved. `->disabled()->saved()` keeps them, with the warning "a skilled user could still edit the field's value by manipulating Livewire's JavaScript".
- **Partial rendering:** "Each time a reactive field is updated, the HTML of the entire Livewire component … is re-generated". Mitigations are `partiallyRenderComponentsAfterStateUpdated(['email'])`, `partiallyRenderAfterStateUpdated()` and `skipRenderAfterStateUpdated()` — [01-overview.md](https://github.com/filamentphp/filament/blob/4.x/packages/forms/docs/01-overview.md)
- **Polymorphic sub-form by select** (the cookbook's "Dynamic fields based on a select option"). A layout component's `schema()` takes a closure, and on type change the child schema is re-`fill()`ed — [01-overview.md](https://github.com/filamentphp/filament/blob/4.x/packages/forms/docs/01-overview.md):
  ```php
  Select::make('type')->options(['employee'=>'Employee','freelancer'=>'Freelancer'])->live()
      ->afterStateUpdated(fn (Select $component) => $component->getContainer()
          ->getComponent('dynamicTypeFields')->getChildSchema()->fill());
  Grid::make(2)
      ->schema(fn (Get $get): array => match ($get('type')) {
          'employee'   => [TextInput::make('employee_number')->required(), FileUpload::make('badge')->image()->required()],
          'freelancer' => [TextInput::make('hourly_rate')->numeric()->required()->prefix('€'), FileUpload::make('contract')->required()],
          default => [],
      })
      ->key('dynamicTypeFields');
  ```
- **Repeater** produces a JSON array of one schema, with `->columns(2)`, add/delete/reorder/clone/collapse, relationship integration, `->simple(TextInput::make(...))` for single-field lists, table repeaters, min/max item counts, and distinct-value validation. Internally, items are keyed by **UUID** (`$state[Str::uuid()] = [...]`). `$get()` inside an item is **relative to the item**, and `$get('../client_id')` climbs up. `$get()` with no argument returns the whole item — [12-repeater.md](https://github.com/filamentphp/filament/blob/4.x/packages/forms/docs/12-repeater.md)
- **Builder** is a list of *heterogeneous typed blocks* (a tagged-union list) — [13-builder.md](https://github.com/filamentphp/filament/blob/4.x/packages/forms/docs/13-builder.md):
  ```php
  Builder::make('content')->blocks([
      Block::make('heading')->schema([TextInput::make('content')->required(), Select::make('level')->options([...])->required()]),
      Block::make('paragraph')->schema([Textarea::make('content')->required()]),
      Block::make('image')->schema([FileUpload::make('url')->image()->required(), TextInput::make('alt')->required()]),
  ])
  ```
  It also supports block labels and icons, previews, a searchable block picker, and a per-block max-usage limit.
- **Custom fields:** `php artisan make:filament-form-field LocationPicker` creates `class LocationPicker extends Field { protected string $view = '...'; }`. The view wraps the input in `<x-dynamic-component :component="$getFieldWrapperView()" :field="$field">`, binds `wire:model="{{ $getStatePath() }}"`, and uses `$applyStateBindingModifiers('wire:model')` to respect live/blur/debounce. "Filament form fields are **not** Livewire components." There are also extra-content slots around every part of a field (above/before/after label, content and error) plus `extraAttributes`/`extraInputAttributes` — [22-custom-fields.md](https://github.com/filamentphp/filament/blob/4.x/packages/forms/docs/22-custom-fields.md), [01-overview.md](https://github.com/filamentphp/filament/blob/4.x/packages/forms/docs/01-overview.md)
- **Global defaults:** `Checkbox::configureUsing(fn (Checkbox $c) => $c->inline(false));` runs in a service provider and can still be overridden per field — [01-overview.md](https://github.com/filamentphp/filament/blob/4.x/packages/forms/docs/01-overview.md)
- Security: "Filament exposes all non-`$hidden` model attributes to JavaScript via Livewire's model binding … only attributes with corresponding form fields are actually editable". Conditionally hidden `FileUpload` fields are not valid upload targets. `extra*Attributes()` values are rendered unescaped by design — [docs/09-advanced/06-security.md](https://github.com/filamentphp/filament/blob/4.x/docs/09-advanced/06-security.md)
- **Criticisms (search summaries):**
  - Slow forms with hundreds of repeater rows ("data sent back and forth becomes huge") — [AnswerOverflow](https://www.answeroverflow.com/m/1395754080684736512)
  - Typing lag with live fields ("letters being lost") — [AnswerOverflow](https://www.answeroverflow.com/m/1158305853301071926)
  - Users can interact with fields that are in a stale state during `live()` round-trips, and a loading-indicator request exists — [filament discussion #12431](https://github.com/filamentphp/filament/discussions/12431)
  - A 2026 post claims v4.12/v5.7 made forms "92% faster", with a 10-item repeater dropping from 28 ms to under 3 ms. I could not open it to verify — [dev.to](https://dev.to/hafiz619/filament-v412-and-v57-92-faster-forms-and-the-security-fixes-you-still-have-to-turn-on-47d)

### Inferences
- **The Livewire form object is the template for pyview:**
  - A Python class (pydantic model or dataclass) held on the LiveView's state, with a bind path like `form.title`.
  - Per-field validation on each change event, full validation on submit.
  - `reset()`/`pull()`, and errors keyed by the same dot/bracket path.
  - pyview can do better than Livewire's weak spot, arrays: validate `items.3.name` on change by re-validating the whole model and *filtering errors to touched paths*, instead of looking up per-property rules.
- **Keep invalid input:** Livewire does not assign a property when real-time validation fails, which loses the user's typed value on the server. pyview should keep the **raw input** and the **parsed value** separately, so an invalid string can be re-rendered as typed.
- **Filament's `Get` closures + `live()` + closure-valued `schema()`** is exactly the "conditional nesting" feature. In pyview (always server-rendered on each event) the default can be "everything is live-capable". The cost lesson carries over: whole-component re-render on each keystroke hurts, so pyview needs debounce/blur defaults (phx-debounce) and ideally per-field diffing. LiveView's diff engine already gives cheaper partial updates than Livewire.
- **Relative paths inside repeated sub-forms** (`$get('../x')`) are a good API for dependent fields inside list rows. **UUID-keyed items** avoid index-shift bugs.
- **Re-`fill()` the child schema when the discriminator changes.** This is the key step for polymorphic sub-forms: on a type switch, reset the sub-form state to the new variant's defaults. For pyview this maps to pydantic discriminated unions (`Annotated[Union[Employee, Freelancer], Field(discriminator="type")]`).
- **Hidden and conditional fields:** either don't validate or save them (Laravel `exclude_if`, Filament hidden-upload rule) or, as Filament does for `saved(false)`, validate them anyway. Filament's footgun shows the default should be "hidden ⇒ excluded from validation and output".
- **The hydrate/dehydrate hooks** (`formatStateUsing`/`dehydrateStateUsing`) correspond to pydantic serializers and validators (model → form-display string, form string → model value). Exposing them per field avoids custom widget classes for simple formatting.
- **Precognition's "validate the same contract server-side on demand"** is natively what a LiveView does. The transferable idea is running the *same* pydantic model for live validation and final submission, with no duplicate rules.

### Gaps
- livewire.laravel.com and filamentphp.com were blocked. Content comes from their GitHub doc sources, which match the published docs.
- I did not verify when Livewire 4 or Filament 5 were released, or what Filament 6.x (branch exists) changes. The 5.x/6.x forms overview differs from 4.x only in version tags.
- Filament's exact default for validating *hidden* (as opposed to not-saved) fields was not stated in the docs I read.

---

## .NET Blazor: EditForm, EditContext, FieldIdentifier, ValidationMessageStore, DataAnnotations, input components and FieldCssClassProvider, nested validation, interactive server mode

### Takeaway
Blazor splits concerns cleanly. The **EditContext** owns per-field metadata (modified or not, validation messages). **FieldIdentifier = (model instance, property name)** is the key for everything. Validators are pluggable components that write into a **ValidationMessageStore** and signal changes. Input components derive their CSS class from a swappable **FieldCssClassProvider**, which is the best "theme hook" in this survey. Nested and collection validation was a long-standing gap. .NET 10 fixed it with source-generated validation (`AddValidation`), and .NET 11 adds async validation with `pending`/`faulted` states.

### Cited Findings
- Validation timing: "Field validation runs after a field changes. In an interactive form, this occurs in .NET while the user edits the form. Full-form validation normally runs when `EditForm` handles submission through `OnValidSubmit` or `OnInvalidSubmit`." Results without a member name go to the summary, not to a field — [AspNetCore.Docs blazor/forms/validation.md](https://github.com/dotnet/AspNetCore.Docs/blob/main/aspnetcore/blazor/forms/validation.md)
- Submission callbacks are `OnValidSubmit`, `OnInvalidSubmit`, and `OnSubmit`. `OnSubmit` takes over validation, which you then run via `EditContext.Validate()` — [blazor/forms/index.md](https://github.com/dotnet/AspNetCore.Docs/blob/main/aspnetcore/blazor/forms/index.md)
- **Custom validation via EditContext** — [validation.md](https://github.com/dotnet/AspNetCore.Docs/blob/main/aspnetcore/blazor/forms/validation.md):
  ```razor
  <EditForm EditContext="editContext" OnValidSubmit="Submit">
      <DataAnnotationsValidator />
      <ValidationSummary />
  </EditForm>
  @code {
      editContext = new EditContext(Model);
      messages = new ValidationMessageStore(editContext);
      editContext.OnValidationRequested += (s, e) => { messages.Clear(); ValidateIdentifier(); editContext.NotifyValidationStateChanged(); };
      editContext.OnFieldChanged += (s, e) => {
          if (e.FieldIdentifier.FieldName != nameof(Starship.Identifier) && e.FieldIdentifier.FieldName != nameof(Starship.MaximumAccommodation)) return;
          messages.Clear(editContext.Field(nameof(Starship.Identifier)));
          ValidateIdentifier(); editContext.NotifyValidationStateChanged(); };
      void ValidateIdentifier() {
          if (Model.MaximumAccommodation == 1 && string.IsNullOrWhiteSpace(Model.Identifier))
              messages.Add(editContext.Field(nameof(Starship.Identifier)), "An identifier is required for a single-occupant ship.");
      }
  }
  ```
  The pattern shows how a cross-field rule attaches its error to a specific field and re-checks when *either* dependency changes.
- Error display: `<ValidationMessage For="() => Model.Identifier" />`. "The `For` expression identifies the field by its model instance and property … a `FieldIdentifier`, so properties with the same name on different model instances are treated as different." There is also `<ValidationSummary Model="Model" />` and `editContext.GetValidationMessages(field)`, which reads state without triggering validation — [validation.md](https://github.com/dotnet/AspNetCore.Docs/blob/main/aspnetcore/blazor/forms/validation.md)
- Default CSS classes: inputs get `valid`/`invalid` plus `modified` after the user edits. Messages get `validation-message`, and the summary gets `validation-summary-errors`/`-valid`. In .NET 11, async-validated inputs get `pending` or `faulted` — [validation.md](https://github.com/dotnet/AspNetCore.Docs/blob/main/aspnetcore/blazor/forms/validation.md)
- **FieldCssClassProvider (the theming hook)** — [validation.md](https://github.com/dotnet/AspNetCore.Docs/blob/main/aspnetcore/blazor/forms/validation.md):
  ```csharp
  public sealed class BootstrapFieldCssClassProvider : FieldCssClassProvider {
      public override string GetFieldCssClass(EditContext editContext, in FieldIdentifier fieldIdentifier) {
          if (!editContext.IsModified(fieldIdentifier)) return string.Empty;   // don't show state until touched
          return editContext.IsValid(fieldIdentifier) ? "is-valid" : "is-invalid";
      }
  }
  editContext.SetFieldCssClassProvider(new BootstrapFieldCssClassProvider());
  ```
  Custom markup calls `editContext.FieldCssClass(() => Model.Identifier)` to apply the same class to a wrapper `<div>`.
- Input components: `InputText`, `InputTextArea`, `InputNumber<T>`, `InputDate<T>`, `InputCheckbox`, `InputSelect<T>`, `InputRadioGroup<T>`/`InputRadio<T>`, `InputFile`, `InputHidden`, and `Label<TValue>` (.NET 11+). Unmatched attributes are splatted onto the element. `InputNumber`/`InputDate` "handle unparseable values gracefully by registering unparseable values as validation errors", with templated messages (`ParsingErrorMessage = "The {0} field must be a date."`, where `{0}` = `DisplayName`) — [input-components.md](https://github.com/dotnet/AspNetCore.Docs/blob/main/aspnetcore/blazor/forms/input-components.md)
- **Nested objects and collections:** in .NET ≤ 9, "`DataAnnotationsValidator` validates top-level model properties but doesn't recursively validate collection or complex-type properties". The workaround is the experimental `ObjectGraphDataAnnotationsValidator` + `[ValidateComplexType]`, which is now **legacy**. In .NET 10+, `builder.Services.AddValidation()` activates a source generator: "Generated metadata is available → Validates nested objects and collections". `ValidatableTypeAttribute` is experimental in .NET 10, and model types must live in `.cs` rather than `.razor` files — [validation.md](https://github.com/dotnet/AspNetCore.Docs/blob/main/aspnetcore/blazor/forms/validation.md); background in [Telerik blog (search summary)](https://www.telerik.com/blogs/advanced-form-validation-blazor-10)
- Community pain: a 2024 issue reports custom messages for nested object properties not showing in `ValidationMessage` (while they do show in `ValidationSummary`), even with `ObjectGraphDataAnnotationsValidator` — [dotnet/aspnetcore #58584](https://github.com/dotnet/aspnetcore/issues/58584)
- .NET 11 async validation: `e.AddAsyncValidator` in `OnValidationRequested`, `EditContext.RegisterAsyncFieldValidator` in `OnFieldChanged`, and a form-level pending state used to disable submit — [validation.md](https://github.com/dotnet/AspNetCore.Docs/blob/main/aspnetcore/blazor/forms/validation.md)
- Render modes: "client-side validation requires an active Blazor SignalR circuit". Static-SSR forms validate on the server when posted, and in the latest docs they get automatic client-side validation when `DataAnnotationsValidator` is present — [index.md](https://github.com/dotnet/AspNetCore.Docs/blob/main/aspnetcore/blazor/forms/index.md)
- Overposting: "we recommend using a separate view model/data transfer object (DTO) for the form and database" — [index.md](https://github.com/dotnet/AspNetCore.Docs/blob/main/aspnetcore/blazor/forms/index.md)

### Inferences
- **Per-field context object:** a pyview `FormState` could mirror EditContext: `field(path) -> FieldState{raw, value, errors, modified, pending}`, `is_valid(path)`, `messages(path)`, `notify_changed(path)`. Validators and business rules register as listeners, so cross-field rules like the Starship example attach errors to one path and re-run on changes to any of their dependencies.
- **FieldIdentifier = (owner, name)** vs. **string path:** Blazor's instance-based identity is why nested and collection errors were hard to route. A string path (`items.3.name` / pydantic `loc` tuple) is simpler for a server-rendered, serializable LiveView state, and matches pydantic's error `loc`.
- **A pluggable `field_css_class(state) -> str`** (with "don't show validity until modified") is a small, high-leverage theming hook for Tailwind/Bootstrap/DaisyUI. It pairs well with simple_form-style wrappers for structural markup.
- **Parse errors are validation errors.** A numeric field receiving `"abc"` should keep `"abc"` as its display value and produce a field error, as InputNumber does, instead of failing the whole form or silently coercing.
- **Validation state should include `pending`** if pyview ever supports async validators (uniqueness checks), with a form-level "validation pending" flag to disable submit.

### Gaps
- learn.microsoft.com was blocked. I used the doc sources on GitHub (main) with version monikers, so .NET 11 features may be preview/in-development as of 2026-09.
- I did not read the "validation-advanced" page (building a reusable validator component) or the InputBase<T> `TryParseValueFromString` custom-input docs in detail.

---

## Functional tradition: formlets, digestive-functors, Elm forms (etaque, dillonkearns/elm-form), Play Scala Form mappings, PureScript Lumi forms

### Takeaway
The FP line of work shows that a form can be a **single composable value that yields both a view (with auto-generated names) and a parser/validator for the submitted data**. Nesting is ordinary composition (a date formlet used twice inside a travel formlet), so names, errors and rendering compose automatically. Later libraries added **error-aware views** (digestive-functors `View`, `subView`), a **raw-input model separate from the parsed result** (elm-form, Lumi), **field status** for when to show errors, **dynamic/dependent sub-forms selected by a parsed discriminator** (elm-form `Form.dynamic`, Lumi `match` with prisms), and **multi-form dispatch** (elm-form `hiddenKind` + `Form.Handler`).

### Cited Findings

**Formlets (Cooper, Lindley, Wadler, Yallop; APLAS 2008)**
- The paper argues that most web environments "do not support abstraction of form components, leading to a lack of compositionality". It uses idioms (applicative functors) and factors the formlet idiom into three idioms — [Springer chapter page / search summary](https://link.springer.com/chapter/10.1007/978-3-540-89330-1_15), [draft PDF](https://homepages.inf.ed.ac.uk/slindley/papers/formlets-essence-draft.pdf) (not fetched). A follow-up tech report, "An idiom's guide to formlets", has the validation extension — [search summary](https://link.springer.com/chapter/10.1007/978-3-540-89330-1_15), [Hackage formlets](https://hackage.haskell.org/package/formlets)
- The Haskell implementation makes those three idioms concrete: an **environment reader** (submitted data), a **name-supply state** (fresh names), and a **markup writer** (XML) — [chriseidhof/formlets Text/Formlets.hs](https://github.com/chriseidhof/formlets/blob/master/Text/Formlets.hs):
  ```haskell
  type Env = [(String, Either String File)]
  type FormState = [Integer]                      -- name supply
  newtype Form xml m a = Form { deform :: Env -> State FormState (m (Validator a), xml, FormContentType) }
  generalInput' i fromLeft = Form $ \env -> mkInput env <$> freshName   -- every input gets a generated name
  ```
  The `formlets` Hackage package is **deprecated in favor of digestive-functors** (last upload 2010) — [Hackage formlets](https://hackage.haskell.org/package/formlets)
- (Unverified, from memory of the paper; I could not fetch the PDF.) The canonical Links example composes a `date_formlet` inside a `travel_formlet`:
  ```
  date_formlet = formlet <div>Month: {input_int ⇒ month} Day: {input_int ⇒ day}</div> yields make_date month day
  travel_formlet = formlet <#>Name: {input ⇒ name} Arrive: {date_formlet ⇒ arrive} Depart: {date_formlet ⇒ depart}{submit "Submit"}</#>
                   yields (name, arrive, depart)
  ```
  Reusing `date_formlet` twice works because names are generated, not hand-written.

**digestive-functors (Haskell)**
- Described as "A practical formlet library". Its improvements over formlets are "better error handling, so a web page can display input errors right next to the corresponding fields; the ability to easily add <label> elements; separation of the validation model and the HTML output" — [Hackage digestive-functors](https://hackage.haskell.org/package/digestive-functors)
- Fields get **explicit names** via `.:` (instead of generated names) "to do some really useful stuff, like separating the `Form` from the actual HTML layout" — [digestive-functors tutorial.lhs](https://github.com/jaspervdj/digestive-functors/blob/master/examples/tutorial.lhs):
  ```haskell
  userForm = User <$> "name" .: text Nothing
                  <*> "mail" .: check "Not a valid email address" checkEmail (text Nothing)
  packageForm = Package <$> "name" .: text Nothing
                        <*> "version" .: validate validateVersion (text (Just "0.0.0.1"))   -- parse+validate in one step
                        <*> "category" .: choice categories Nothing
  releaseForm = Release <$> "author" .: userForm <*> "package" .: packageForm              -- composition = nesting
  ```
- The **View** (form + user input + errors) is what gets rendered, and views compose with `subView`. Paths are dot-separated — [tutorial.lhs](https://github.com/jaspervdj/digestive-functors/blob/master/examples/tutorial.lhs):
  ```haskell
  releaseView view = do
      userView $ subView "author" view          -- reuse the sub-form's view function
      childErrorList "package" view             -- all errors under package.*
      label "package.version" view "Version: "; inputText "package.version" view
  ```

**dillonkearns/elm-form (v3.x) — parsing + rendering unified**
- Built around "a single `Form.Model` value as an unparsed set of raw field values and `FieldStatus` (blurred, changed, etc.)". The `Form` definition runs validations against the unparsed values and renders fields with errors. It comes out of elm-pages, and its core values are progressive enhancement and accessibility ("Forms are always rendered within a `<form>` element") — [elm-form README](https://github.com/dillonkearns/elm-form)
- It explicitly rejects the "a Msg per field" pattern in favor of one `FormMsg` and one `Form.Model` for all forms on a page — [elm-form README](https://github.com/dillonkearns/elm-form)
- A form is a function of its fields that returns `{ combine, view }`, so cross-field validation and rendering are defined together — [elm-form README](https://github.com/dillonkearns/elm-form):
  ```elm
  signUpForm =
      (\username password passwordConfirmation ->
          { combine =
              Validation.succeed SignUpForm
                  |> Validation.andMap username
                  |> Validation.andMap
                      (Validation.map2 (\p c -> if p == c then Validation.succeed p
                                                 else Validation.fail "Must match password" passwordConfirmation)
                          password passwordConfirmation |> Validation.andThen identity)
          , view = \formState -> [ fieldView "username" username, ... ]
          })
          |> Form.form
          |> Form.field "username" (Field.text |> Field.required "Required")
          |> Form.field "password" (Field.text |> Field.password |> Field.required "Required")
  ```
  Note that `Validation.fail "..." passwordConfirmation` attaches a *cross-field* error to a specific field.
- Error display is gated by status: `if formState.submitAttempted then formState.errors |> Form.errorsForField field ...`. Field status values are `NotVisited | Focused | Changed | Blurred`, with `statusAtLeast` — [src/Form.elm](https://github.com/dillonkearns/elm-form/blob/main/src/Form.elm), [src/Form/Validation.elm](https://github.com/dillonkearns/elm-form/blob/main/src/Form/Validation.elm)
- **`Form.dynamic`: sub-form chosen by a parsed discriminator** — [src/Form.elm](https://github.com/dillonkearns/elm-form/blob/main/src/Form.elm):
  ```elm
  dependentForm =
      Form.form (\kind postForm_ -> { combine = kind |> Validation.andThen postForm_.combine, view = \_ -> [] })
          |> Form.field "kind" (Field.select [ ( "link", Link ), ( "post", Post ) ] (\_ -> "Invalid") |> Field.required "Required")
          |> Form.dynamic (\parsedKind -> case parsedKind of
                                Link -> linkForm
                                Post -> postForm)
  -- Form.Handler.run [("kind","link"),("url","https://...")] (dependentForm |> Form.Handler.init identity)
  --   --> Valid (ParsedLink "https://...")
  ```
- **`hiddenKind` + `Form.Handler`** tell apart several forms on one page or endpoint, and let the backend parse submissions with the *same* form definition ("code sharing to keep your backend and frontend validations in sync") — [src/Form/Handler.elm](https://github.com/dillonkearns/elm-form/blob/main/src/Form/Handler.elm):
  ```elm
  updateProfile = ... |> Form.hiddenKind ( "kind", "update-profile" ) "Expected kind"
  handler = Form.Handler.init UpdateProfile updateProfile |> Form.Handler.with SendMessage sendMessage
  ```
- Initial values come from an input passed at render time (`Field.withInitialValue`) — [elm-form README](https://github.com/dillonkearns/elm-form)

**etaque/elm-form (older Elm approach)**
- Its validation API is like `Json.Decode` (`succeed Foo |> andMap (field "bar" email) |> andMap (field "baz" bool)`) and gives "either the desired output value or all field errors". It supports nested fields `foo.bar.baz` and lists `todos.1.checked`. The trade-off: "losing some type safety (field names are made of strings)". `field.liveError` drives display — [etaque/elm-form README](https://github.com/etaque/elm-form)

**Play Framework (Scala) Form mappings**
- A mapping is a **bidirectional binder**: `apply` builds the value from fields and `unapply` fills fields from a value. On Scala 3 you define `unapply` explicitly — [Play ScalaForms code](https://github.com/playframework/playframework/blob/main/documentation/manual/working/scalaGuide/main/forms/code/ScalaForms.scala):
  ```scala
  case class UserData(name: String, age: Int)
  object UserData { def unapply(u: UserData): Option[(String, Int)] = Some((u.name, u.age)) }
  val userForm = Form(mapping("name" -> text, "age" -> number)(UserData.apply)(UserData.unapply))
  val contactForm: Form[Contact] = Form(mapping(
      "firstname" -> nonEmptyText, "lastname" -> nonEmptyText, "company" -> optional(text),
      "informations" -> seq(mapping(
          "label" -> nonEmptyText, "email" -> optional(email),
          "phones" -> list(text.verifying(pattern("""[0-9.+]+""".r, error = "A valid phone number is required")))
      )(ContactInformation.apply)(ContactInformation.unapply))
  )(Contact.apply)(Contact.unapply))
  contactForm.bindFromRequest().fold(formWithErrors => BadRequest(views.html.contact.form(formWithErrors)),
                                     contact => Redirect(...))
  Ok(views.html.contact.form(contactForm.fill(existingContact)))
  ```
  There is also `ignored(23L)` (a server-side value that is never bound from input), `optional(...)`, `of[URL]` with a custom `Formatter[T]` (`bind`/`unbind`), and form-level `.verifying("msg", data => ...)`.
- Wire format: nested fields use `homeAddress.street`, and repeated fields use `emails[0]` or `emails[]` — [ScalaForms.md](https://github.com/playframework/playframework/blob/main/documentation/manual/working/scalaGuide/main/forms/ScalaForms.md), [code](https://github.com/playframework/playframework/blob/main/documentation/manual/working/scalaGuide/main/forms/code/ScalaForms.scala)
- Errors are `FormError(key, message, args)`, accessed via `errors`, `globalErrors` (errors with no key), `error("name")` and `errors("name")`. Field helpers render field errors automatically. There is a "Maximum number of fields for a single tuple or mapping is 22" — [ScalaForms.md](https://github.com/playframework/playframework/blob/main/documentation/manual/working/scalaGuide/main/forms/ScalaForms.md)
- **Theming via an implicit `FieldConstructor`:** every input helper takes an implicit field constructor (a template receiving `FieldElements`). Importing a different one re-themes all fields. Per-call args prefixed with `_` (`'_label`, `'_help`, `'_showConstraints -> false`, `'_error`, `'_showErrors`) configure the constructor, and other args go to the `<input>` — [ScalaCustomFieldConstructors.md](https://github.com/playframework/playframework/blob/main/documentation/manual/working/scalaGuide/main/forms/ScalaCustomFieldConstructors.md):
  ```html
  @(elements: helper.FieldElements)
  <div class="@if(elements.hasErrors) {error}">
      <label for="@elements.id">@elements.label</label>
      <div class="input">@elements.input <span class="errors">@elements.errors.mkString(", ")</span>
           <span class="help">@elements.infos.mkString(", ")</span></div>
  </div>
  ```
  ([template source](https://github.com/playframework/playframework/blob/main/documentation/manual/working/scalaGuide/main/forms/code/scalaguide/forms/scalafieldconstructor/myFieldConstructorTemplate.scala.html))

**PureScript Lumi forms (lumihq/purescript-lumi-components)**
- `FormBuilder' ui props unvalidated result`: "An applicative functor which can be used to build forms", essentially `props -> unvalidated -> { edit :: ((unvalidated -> unvalidated) -> Effect Unit) -> ui, validate :: Maybe result }`. The form edits an **unvalidated** state type and produces a **validated result** type — [Form/Internal.purs](https://github.com/lumihq/purescript-lumi-components/blob/master/src/Lumi/Components/Form/Internal.purs)
- Optics-based composition — [Form.purs](https://github.com/lumihq/purescript-lumi-components/blob/master/src/Lumi/Components/Form.purs):
  - `focus :: Lens' s a -> FormBuilder' ui props a result -> FormBuilder' ui props s result` ("Focus a FormBuilder on a smaller piece of state").
  - `match :: Prism s s a a -> Prism s t a result -> ...` ("Focus a FormBuilder on a possible type of state, using a Prism"). This is the sum-type/polymorphic sub-form combinator, and it renders nothing when the state isn't that variant.
  - `via` (Iso) changes representation.
  - `array { label, addLabel, defaultValue, editor }` "displays a removable section for each array element, along with an 'Add...' button".
  - `mapUI` re-skins the UI based on props, value and validated result.

### Inferences
- **pyview's core abstraction can be "formlet-shaped":** a `Form[T]` object that knows (a) how to render itself under a name prefix, (b) how to parse and validate a nested dict of raw strings under that prefix into `T` or path-keyed errors, and (c) how to unparse a `T` into raw strings for initial display (Play's `fill`/unbind). Nesting is composition by prefix, and a list sub-form is `array(editor)` (Lumi) / `seq(mapping)` (Play). Python doesn't need applicatives: a pydantic model already *is* the combined parser, so the "formlet" is mainly the **view + raw-state + path** layer.
- **Two types per form:** raw/unvalidated state (all strings, plus field status) and the result (the pydantic instance). elm-form, Lumi, Blazor's `CurrentValueAsString` and Vaadin converters all converge on this. It prevents losing user input on type errors and makes "unchanged since load" and "dirty" tracking easy.
- **Sub-views for reuse:** digestive's `subView "author" view` suggests `form["address"]` should return a sub-form view that can be passed to a reusable template or component. Its errors, ids and names are already prefixed, and `childErrorList` gives "all errors under this subtree".
- **Polymorphic sub-forms:** implement elm-form's `dynamic` / Lumi's `match` as "a discriminator field whose parsed value selects which sub-form to render and parse". This maps directly onto pydantic discriminated unions. Validation of inactive variants is skipped.
- **Error gating:** adopt elm-form's status lattice (`not_visited < focused < changed < blurred`) plus `submit_attempted`, and let the theme decide the visibility rule (e.g. show errors if `status >= blurred or submit_attempted`). LiveView's `phx-change` gives pyview the events to track `changed`, and `phx-blur`/`phx-focus` give `blurred`/`focused`.
- **Multi-form dispatch:** `hiddenKind` corresponds to a hidden `_form` field, or separate `phx-submit` event names per form. Useful when a LiveView hosts multiple forms.
- **The `_`-prefixed per-call options** (Play) versus attributes passed through to the input is a neat convention for the per-field override API: `field("email", _label="E-mail", _hint="...", class_="w-full")`.

### Gaps
- Could not fetch the formlets paper or tech report. The Links syntax example is unverified.
- Could not load package.elm-lang.org or Pursuit. Elm and PureScript details come from GitHub source doc comments. I did not verify whether lumihq/purescript-lumi-components is still maintained (it may be archived).
- Did not cover Idris forms or the "form lenses" work (Foster et al., BX 2013), which appeared in search results but was not read: [formlenses.pdf](https://www.cs.cornell.edu/~jnfoster/papers/formlenses.pdf).

---

## Other ecosystems: Go (gorilla/schema), Rust (Leptos ActionForm), Java/Kotlin (Spring MVC + Bean Validation, Vaadin Binder), Streamlit, SwiftUI

### Takeaway
Distinct ideas from these ecosystems:
- **Vaadin Binder** (server-driven like LiveView) has an explicit per-field **converter → validator → getter/setter pipeline**, a choice between *buffered* (`readBean`/`writeBean`) and *unbuffered* (`setBean`) editing, and "show errors only after the user edited a field".
- **Spring** binds a request into a command object plus a separate `BindingResult`.
- **gorilla/schema and Leptos** show struct ↔ form-values codecs using dotted or bracketed paths.
- **Streamlit** shows the batching-vs-reactivity trade-off: widgets inside a form cannot depend on each other.
- **SwiftUI** styles forms from the container (`Form` + `.formStyle`) rather than per field.

### Cited Findings

**Vaadin Flow Binder (docs main, 2026-09)**
- Explicit binding — [vaadin/docs components-binder.adoc](https://github.com/vaadin/docs/blob/main/articles/flow/binding-data/components-binder.adoc):
  ```java
  Binder<Person> binder = new Binder<>(Person.class);
  binder.forField(titleField).bind(Person::getTitle, Person::setTitle);
  binder.readBean(person);                         // load into fields (buffered)
  try { binder.writeBean(person); } catch (ValidationException e) { notifyValidationException(e); }
  ```
  "There can be only one Binder instance for each form." You bind read-only data by passing a `null` setter.
- Converter and validator chain, with error-display hooks — [components-binder-validation.adoc](https://github.com/vaadin/docs/blob/main/articles/flow/binding-data/components-binder-validation.adoc), [components-binder-beans.adoc](https://github.com/vaadin/docs/blob/main/articles/flow/binding-data/components-binder-beans.adoc):
  ```java
  binder.forField(emailField)
      .withValidator(new EmailValidator("This doesn't look like a valid email address"))
      .withValidator(email -> email.endsWith("@acme.com"), "Only acme.com email addresses are allowed")
      .withStatusLabel(emailStatus)                   // or .withValidationStatusHandler(status -> ...)
      .bind(Person::getEmail, Person::setEmail);
  binder.forField(titleField).asRequired("Every employee must have a title").bind(...);   // also shows required indicator
  binder.forField(yearOfBirthField).withConverter(new StringToIntegerConverter("Enter a number")).bind("yearOfBirth");
  binder.withValidator(p -> p.getYearOfMarriage() > p.getYearOfBirth(), ...);             // bean-level validator
  ```
  "By default, validators run whenever the user changes the field value."
- Less boilerplate options:
  - `binder.bind(field, "address.street")`: string property paths, with the warning that typos cause runtime exceptions.
  - `binder.bindInstanceFields(this)`: matches UI member fields to bean properties by name, with `@PropertyId("address.street")` overrides.
  - `BeanValidationBinder` picks up JSR-303 annotations (`@Max`, `@Size`).
  - Tip: "Prefer explicit `forField().bind()` binding with getter and setter method references for anything beyond the simplest forms"

  Source: [components-binder-beans.adoc](https://github.com/vaadin/docs/blob/main/articles/flow/binding-data/components-binder-beans.adoc)
- Buffered vs unbuffered: `setBean(person)` writes on every valid change, with a warning about shared instances. The alternatives are `readBean`/`writeBean`, `writeBeanIfValid`, `writeChangedBindingsToBean` and `binder.validate()`. "To prevent displaying multiple errors to the user, validation errors only display after the user has edited each field and submitted (i.e., loaded) the form." — [components-binder-load.adoc](https://github.com/vaadin/docs/blob/main/articles/flow/binding-data/components-binder-load.adoc)

**Spring MVC + Bean Validation + Thymeleaf**
- A command object with `@Size(min=2, max=30)`, `@NotNull` and `@Min(18)`, handled by the controller — [spring-guides/gs-validating-form-input](https://github.com/spring-guides/gs-validating-form-input):
  ```java
  @PostMapping("/")
  public String checkPersonInfo(@Valid PersonForm personForm, BindingResult bindingResult) {
      if (bindingResult.hasErrors()) { return "form"; }
      return "redirect:/results";
  }
  ```
  ```html
  <form th:action="@{/}" th:object="${personForm}" method="post">
    <input type="text" th:field="*{name}" />
    <td th:if="${#fields.hasErrors('name')}" th:errors="*{name}">Name Error</td>
  ```
  `th:field` derives name, id and value from the bound object path.

**Go: gorilla/schema**
- `decoder.Decode(&person, r.PostForm)` and `encoder.Encode(person, form)` form a two-way struct ↔ `url.Values` codec. Struct tags handle naming, required and ignored fields (`schema:"name,required"`, `schema:"-"`) and defaults (`schema:"age,default:21"`) — [gorilla/schema README](https://github.com/gorilla/schema)
- Nested structs use dotted paths, and "only for slices of structs the slice index is required": `Phones.0.Label`, `Phones.0.Number`, … — [gorilla/schema doc.go](https://github.com/gorilla/schema/blob/main/doc.go)

**Rust: Leptos ActionForm / server functions**
- `<ActionForm action=add_todo>` posts to a `#[server]` function, and input `name`s must match the function's argument names. It "only works with the default URL-encoded POST encoding … to ensure graceful degradation". It exposes `.input()`, `.pending()` and `.value()` signals — [Leptos book action_form.md](https://github.com/leptos-rs/book/blob/main/src/progressive_enhancement/action_form.md)
- Nested struct arguments use `serde_qs` bracket notation: `name="hefty_arg[settings][display_name]"`. Client-side pre-validation uses `AddTodo::from_event(&ev)` (the `FromFormData` trait) in an `on:submit:capture` handler — [action_form.md](https://github.com/leptos-rs/book/blob/main/src/progressive_enhancement/action_form.md)

**Streamlit `st.form`**
- A form batches widget input into one rerun: `with st.form("my_form"): ...; st.form_submit_button('Submit')`. Limitations: every form needs a submit button, forms can't be nested, and only the submit button can have a callback. "Interdependent widgets within a form are unlikely to be particularly useful … widget2 will only update when the form is submitted." — [streamlit/docs forms.md](https://github.com/streamlit/docs/blob/main/content/develop/concepts/architecture/forms.md)

**SwiftUI `Form`**
- "SwiftUI applies platform-appropriate styling to views contained inside a form … forms appear as grouped lists on iOS, and as aligned vertical stacks on macOS." Controls (`Picker`, `Toggle`, `Button`) inside `Form { Section(header:) { ... } }` restyle automatically, and per-control style modifiers such as `.pickerStyle(.inline)` refine them — [Apple SwiftUI Form docs](https://developer.apple.com/documentation/swiftui/form)

### Inferences
- **Vaadin's `forField().withConverter().withValidator().bind()` chain** suggests pyview should model each field as a pipeline: raw string → (converter/parse, may fail) → typed value → (validators) → model attribute. pydantic covers the middle steps, but exposing per-field `converter=` / `validators=` overrides keeps simple customizations from needing a model change.
- **Buffered vs unbuffered** is a real design axis for server-stateful UIs:
  - Buffered: edit a copy and commit on submit (default; Reform-like).
  - Unbuffered: each valid change writes through, like Livewire's `updated()` autosave and Vaadin's `setBean`.

  pyview could offer both.
- **Spring's `BindingResult`** (binding and validation errors carried alongside the target) and **Play's `Form[T]` with errors** are the same idea as a pyview `Form` holding `data`, `errors` and `raw`. Keep errors out of the model.
- **gorilla/schema, Leptos serde_qs, Rails and Plug** are all variants of path encoding. Picking bracket notation keeps pyview compatible with standard `<form>` posts (progressive enhancement) and with Phoenix LiveView JS, which pyview mirrors.
- **The Streamlit lesson:** batching (deferred) forms can't support dependent fields. pyview's LiveView model, where `phx-change` sends the whole form, supports dependent and conditional fields by default. This is a strength to lean into, with debounce as the cost control.
- **The SwiftUI lesson:** put the style on the container (form-level theme/context) and let controls pick it up, with per-field overrides as an escape hatch. This is the same layering as simple_form's global wrappers + `wrapper:` per form or field.

### Gaps
- I did not research templ (Go) form patterns (the docs path was not found), Kotlin-specific frameworks (e.g. Ktor, kotlinx.html), or Spring's own `docs.spring.io` pages (blocked). The Spring info comes from the official guide repo.
- Vaadin's handling of **collections and lists** in Binder (a common complaint) was not covered in the pages I read. Vaadin 25 "signals" changes, if any, were not checked.

---

## Cross-cutting: (a) deriving forms from models, (b) overriding one field without ejecting, (c) conditional/polymorphic sub-forms, (d) error representation and display, (e) theming/styling

### Takeaway
The frameworks converge on the following:
- **(a)** Derive fields from the model's types, names and constraints (simple_form column → input table, formtastic bare `f.inputs`, Vaadin `bindInstanceFields`/`BeanValidationBinder`, Blazor DataAnnotations, Filament labels from names), with explicit per-field declarations as the escape hatch.
- **(b)** Override through layered configuration: global defaults, per-form wrapper/builder, per-field options, and a custom widget class/template registered by name.
- **(c)** A discriminator field whose value selects a sub-schema, re-evaluated on change (Filament closure `schema()` + `live()` + `fill()`, elm-form `dynamic`, Lumi `match`), with inactive branches excluded from validation and output (Laravel `exclude_if`).
- **(d)** Errors as a flat map from **field path → list of messages**, plus a keyless "global/form" bucket (Play `globalErrors`, Blazor summary, Livewire error bag), and display gated by a touched/modified/blurred/submitted status.
- **(e)** Styling via a wrapper/field-constructor template plus a state → CSS class function (simple_form wrappers with `error_class`/`valid_class`, Play implicit `FieldConstructor`, Blazor `FieldCssClassProvider`, Filament `configureUsing` + extra-content slots).

### Cited Findings
- (a) Derivation:
  - simple_form maps DB column type and name patterns to inputs (`string` + `/email/` → `input[type=email]`, `text` → textarea, `belongs_to` → select) — [simple_form README](https://github.com/heartcombo/simple_form)
  - formtastic `f.inputs` with no args renders inputs for most columns and `belongs_to` associations — [formtastic README](https://github.com/formtastic/formtastic)
  - Vaadin: `bindInstanceFields(this)` matches by name. `BeanValidationBinder` "automatically adds validators based on JSR 303 constraints" — [Vaadin binder-beans](https://github.com/vaadin/docs/blob/main/articles/flow/binding-data/components-binder-beans.adoc)
  - Filament "the label of the field will be automatically determined based on its name" — [Filament overview](https://github.com/filamentphp/filament/blob/4.x/packages/forms/docs/01-overview.md)
  - Filament validation methods also produce frontend validation — [Filament validation](https://github.com/filamentphp/filament/blob/4.x/packages/forms/docs/23-validation.md)
  - Vaadin `asRequired` shows a visual required indicator — [Vaadin validation](https://github.com/vaadin/docs/blob/main/articles/flow/binding-data/components-binder-validation.adoc)
  - simple_form's `:html5`, `:maxlength` and `:pattern` wrapper extensions derive HTML attributes from validations — [simple_form README](https://github.com/heartcombo/simple_form)
- (b) Override one field:
  - Rails subclass + `super` — [Rails guide](https://github.com/rails/rails/blob/main/guides/source/form_helpers.md)
  - simple_form `as:`, `wrapper:`, `input_html:`, and same-name input-class override — [simple_form README](https://github.com/heartcombo/simple_form)
  - Filament per-field closures, `extraInputAttributes`, extra-content slots (above/below label, content and error), and a custom `Field` with its own view that reuses `$getFieldWrapperView()` — [Filament overview](https://github.com/filamentphp/filament/blob/4.x/packages/forms/docs/01-overview.md), [custom fields](https://github.com/filamentphp/filament/blob/4.x/packages/forms/docs/22-custom-fields.md)
  - Play `_label`/`_help` args — [Play field constructors](https://github.com/playframework/playframework/blob/main/documentation/manual/working/scalaGuide/main/forms/ScalaCustomFieldConstructors.md)
  - Livewire Blade components with `$attributes` forwarding and `x-modelable` — [Livewire forms.md](https://github.com/livewire/livewire/blob/main/docs/forms.md)
- (c) Conditional and polymorphic:
  - Filament `hidden(fn (Get $get) => ...)`, closure `schema()` with `match`, `->key()` + `getChildSchema()->fill()`, and `Builder` blocks — [Filament overview](https://github.com/filamentphp/filament/blob/4.x/packages/forms/docs/01-overview.md), [builder](https://github.com/filamentphp/filament/blob/4.x/packages/forms/docs/13-builder.md)
  - elm-form `Form.dynamic` — [Form.elm](https://github.com/dillonkearns/elm-form/blob/main/src/Form.elm)
  - Lumi `match` with prisms — [Form.purs](https://github.com/lumihq/purescript-lumi-components/blob/master/src/Lumi/Components/Form.purs)
  - Laravel `exclude_if` / `Rule::excludeIf` — [Laravel validation](https://github.com/laravel/docs/blob/13.x/validation.md)
  - Livewire dependent selects need `wire:key` — [wire-model.md](https://github.com/livewire/livewire/blob/main/docs/wire-model.md)
- (d) Errors:
  - Play `FormError(key, message, args)` + `globalErrors` — [Play ScalaForms.md](https://github.com/playframework/playframework/blob/main/documentation/manual/working/scalaGuide/main/forms/ScalaForms.md)
  - Livewire error bag keyed by dot path (`form.title`, auto-prefix in form objects) — [Livewire validation.md](https://github.com/livewire/livewire/blob/main/docs/validation.md)
  - Blazor `ValidationMessageStore` keyed by `FieldIdentifier`, with model-level messages going to the summary — [Blazor validation.md](https://github.com/dotnet/AspNetCore.Docs/blob/main/aspnetcore/blazor/forms/validation.md)
  - dry-validation `errors={:age=>[...]}` — [dry-validation](https://github.com/dry-rb/dry-validation/blob/release-1.10/docsite/source/index.html.md)
  - digestive `errorList "mail"` / `childErrorList "package"` — [tutorial](https://github.com/jaspervdj/digestive-functors/blob/master/examples/tutorial.lhs)
  - Display gating:
    - Blazor `modified` class and the provider's `IsModified` check — [Blazor](https://github.com/dotnet/AspNetCore.Docs/blob/main/aspnetcore/blazor/forms/validation.md)
    - Vaadin "only display after the user has edited each field" — [Vaadin load](https://github.com/vaadin/docs/blob/main/articles/flow/binding-data/components-binder-load.adoc)
    - elm-form `submitAttempted` + FieldStatus — [Form.elm](https://github.com/dillonkearns/elm-form/blob/main/src/Form.elm)
- (e) Theming:
  - simple_form named wrappers with `error_class`/`valid_class`, and the Bootstrap generator — [simple_form](https://github.com/heartcombo/simple_form)
  - Play implicit `FieldConstructor` — [Play](https://github.com/playframework/playframework/blob/main/documentation/manual/working/scalaGuide/main/forms/ScalaCustomFieldConstructors.md)
  - Blazor `FieldCssClassProvider` — [Blazor](https://github.com/dotnet/AspNetCore.Docs/blob/main/aspnetcore/blazor/forms/validation.md)
  - Filament `configureUsing` — [Filament](https://github.com/filamentphp/filament/blob/4.x/packages/forms/docs/01-overview.md)
  - SwiftUI container-driven styling — [Apple](https://developer.apple.com/documentation/swiftui/form)
  - Rails custom `FormBuilder` for Tailwind (search-engine summary: a builder "whose only job is to insert your styling", after which "the builder will point you straight back to Rails magic land". I couldn't confirm which of these two pages the quote comes from) — [testdouble](https://testdouble.com/insights/optimizing-rails-forms-with-tailwind), [Rails Designer](https://railsdesigner.com/tailwindcss-rails-forms/)

### Inferences
Concrete design sketch for pyview, combining the strongest ideas:

1. **Form object = typed model + raw state + field status + errors** (Livewire Form / Reform / elm-form Model / Blazor EditContext):
   ```python
   form = Form(SignupModel, data=initial)      # dataclass or pydantic model
   form.raw["address.city"]                     # string as typed (Blazor CurrentValueAsString / elm raw values)
   form.errors["items.2.qty"]                   # list[str], path == pydantic loc joined; form.errors[""] = global
   form.status("email")                         # not_visited|focused|changed|blurred ; form.submit_attempted
   form.validate(params) -> Model | None         # Reform: never mutates target model until sync/save
   ```
2. **One path grammar** used for `name=` (bracket style `user[items][<key>][qty]`, compatible with Rails, Plug, serde_qs and Leptos), error keys (dot style is fine internally), and ids (`user_items_<key>_qty`, as Rails derives them). List rows are keyed by **stable ids** (Filament UUIDs, Rails `NEW_RECORD`→timestamp or `index: record.id`), not positions. Support `_destroy`/`_delete` and `reject_if="all_blank"` semantics (Rails).
3. **Derive by default, override locally:** field type from annotation + `annotated_types` constraints → widget + HTML attributes (`required`, `maxlength`, `min`, `pattern`), like simple_form/Filament/BeanValidationBinder. Override per field with `widget=`/`as_=`, pass-through attrs, `_label`/`_hint` (Play-style), or a custom widget class looked up by name (simple_form `CurrencyInput`).
4. **Theme = wrapper template + class provider + global configure hook:** a named wrapper registry (simple_form) chosen globally, per form or per field; a `field_css_class(field_state)` callable (Blazor); and `Widget.configure_using(...)` global defaults (Filament).
5. **Conditional and polymorphic sub-forms:** closures that receive a `get(path)` accessor (Filament) and a discriminated-union sub-form (elm-form `dynamic`), re-initialized when the discriminator changes. Hidden or inactive branches are excluded from validation and output by default (Laravel `exclude_if`), with an explicit opt-in to keep them.
6. **Cross-field rules attach errors to a specific path** (elm-form `Validation.fail msg field`, Blazor `messages.Add(editContext.Field(...))`, dry-validation `rule(:age)` running only after the schema passes).
7. **Liveness knobs per field** (Livewire `.live/.blur/.debounce`, Filament `live(onBlur:, debounce:)`) map to LiveView `phx-debounce`/`phx-blur`. Default to blur/debounce for text fields to avoid the lag reported for Filament and Livewire.

### Gaps
- There is no single comparative source. The cross-framework synthesis is my inference from the primary docs above.
- Accessibility specifics (aria-invalid, aria-describedby for errors) were only mentioned by elm-form as a core value. I didn't gather concrete markup conventions from each framework.
- No quantitative data (adoption and satisfaction surveys) on these form libraries was found or searched.
