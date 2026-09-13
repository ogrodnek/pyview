# Wide survey: .NET (model binding/ModelState/DataAnnotations/FluentValidation/Blazor EditForm), JVM (Spring binding/BindingResult/Bean Validation/Thymeleaf th:field/Vaadin Binder), Go/Rust struct-tag binders & validators, functional formlets (digestive-functors/yesod-form/elm-form/Play Forms), and LiveView ports (LiveViewJS, AshPhoenix.Form)

Versions researched (2026-09-12): ASP.NET Core docs `main` (Blazor 11.0 async validation), FluentValidation `main` docs, Spring Framework `main` (`DefaultMessageCodesResolver.java`), Vaadin Flow Binder (javadoc 14/24 API), go-playground/validator v10, Keats/validator (README main), garde (README main), serde_qs 1.0, digestive-functors `examples/tutorial.lhs`, Yesod book `forms.asciidoc`, dillonkearns/elm-form README, Play `ScalaForms.md` main, LiveViewJS `packages/core/src/server/changeset/changeset.ts` (clone, main), AshPhoenix `lib/ash_phoenix/form/form.ex` + `documentation/topics/{nested-forms,union-forms}.md` (clone, main).

## TL;DR

- Every mature server-side ecosystem converges on **one canonical path syntax** for nested data in flat form bodies and uses it for *both* binding and error addressing: `.NET Address.City` / `Items[0].Name`, Spring `groups[0].name`, Play `homeAddress.street`, Rails/serde_qs/Phoenix `user[address][city]`, go-playground/form `Items[0].X`. pyview currently has none; pick Phoenix's bracket form and decode it in the ws handler.
- **Attempted values are kept separately from parsed values** (ASP.NET `ModelStateEntry.AttemptedValue/RawValue`, Spring `FieldError.getRejectedValue()`, Vaadin's buffered `readBean/writeBean`, elm-form's `Form.Model` of raw strings). Re-rendering an input from the *typed* model is the #1 cause of "my invalid input vanished" bugs; the .NET docs even warn about it.
- **Errors are structured records with a code, a message template, params, and a path**, not strings: Spring `FieldError(codes[], rejectedValue, arguments)`, Keats `ValidationError{code,message,params}`, go-playground `FieldError{Namespace(),Tag(),Param()}`, Bean Validation `ConstraintViolation{propertyPath, messageTemplate}`. Pydantic's `ErrorDetails{type, loc, msg, input, ctx}` is already exactly this — expose it, do not flatten it to `errors[loc[0]] = msg`.
- **Message resolution is a fallback hierarchy** (Spring `typeMismatch.user.age` -> `typeMismatch.age` -> `typeMismatch.int` -> `typeMismatch`, with `[0]` index-stripped variants; `.NET` `{0}` placeholders; FluentValidation `{PropertyName}` `{ComparisonValue}`). This is how i18n and per-form overrides coexist without touching the model.
- **Form-state flags beyond "valid"**: Blazor `EditContext.IsModified(field)` + `modified/valid/invalid` CSS classes via `FieldCssClassProvider`; AshPhoenix `submitted_once?`, `just_submitted?`, `changed?`, `touched_forms`; elm-form `FieldStatus` (blurred/changed) + `submitAttempted`; yesod `FormResult = FormMissing | FormFailure | FormSuccess`. pyview needs "used/touched" per path + "submitted once" as first-class.
- **Dynamic lists without JS**: AshPhoenix `_add_locations=end` / `_drop_locations[]=0` hidden-checkbox params handled inside `validate/3`, plus `add_form(form, [:posts, 0, :comments])` / `remove_form` by path; `.NET` `Items.index=a&Items[a].Name` non-sequential indices; Thymeleaf `__${i}__` preprocessing + re-post; Play `@repeat(form("emails"), min=1)`. The AshPhoenix approach maps 1:1 onto pyview's phx-change round-trip.
- **Conditional/polymorphic sub-forms** are solved by a **discriminator param**: AshPhoenix `_union_type` hidden field selects which nested form to render/parse; Pydantic discriminated unions give pyview this for free.
- **Applicative formlets** (digestive-functors, yesod, elm-form, Play `mapping`) prove that naming + parsing + rendering can be derived from a *static shape* — which is exactly what a Pydantic class is. "Parse, don't validate" (elm-form) = produce a typed `User` or a structured error tree, never a half-validated dict.

## Mental model & core abstractions

Three families:

1. **Model-first binders** (.NET MVC, Spring `@ModelAttribute`, gorilla/schema, go-playground/form, serde_qs, Play `mapping`, AshPhoenix auto forms). The typed model (class/struct/Ash action) *is* the schema; the binder walks it, derives field names, and coerces request strings. Validation is a separate layer (DataAnnotations/FluentValidation, Bean Validation, go-playground/validator, garde) that returns path-addressed violations. Presentation is a third layer (tag helpers `asp-for`, `th:field`, `@helper.inputText`) that reads *names + values + errors* from a bound "form/binding result" object.
2. **Buffered UI binders** (Vaadin `Binder`, Blazor `EditContext`). A live object holds per-field bindings with converter+validator chains; `readBean` copies model -> fields, `writeBean(bean)` validates all and copies back only if valid (`BeanValidationBinder` adds JSR-303 automatically). Blazor's `EditContext` is the event bus: `OnFieldChanged`, `OnValidationRequested`, `NotifyValidationStateChanged()`, with a `ValidationMessageStore` that any validator (DataAnnotations, custom, async) writes into keyed by `FieldIdentifier(model, fieldName)`.
3. **Applicative formlets** (digestive-functors `Form v m a`, yesod `AForm`/`MForm`, elm-form `Form.form`/`Validation.andMap`, Play `Form(mapping(...)(apply)(unapply))`). One value describes the form's *shape*; from it you derive (a) the names of inputs, (b) a parser from `Env -> Result`, (c) a `View` for rendering. Because it's applicative not monadic, the shape is known before any input arrives, so rendering an empty form and parsing a submission come from the same definition. elm-form adds `Form.dynamic` for the genuinely monadic case (a later field's definition depends on an earlier parsed value).

**LiveView ports**: LiveViewJS's `LiveViewChangeset<T>{action?, changes, errors?, data, valid}` built by `newChangesetFactory<T>(zodSchema)` — the same shape as pyview's `ChangeSet`, incl. the same `_target`-filtering trick. AshPhoenix.Form is the mature one: `for_create/for_update/for_action`, `validate/3`, `submit/2`, `add_form/remove_form`, `errors/2`, `params/2`, implements `Phoenix.HTML.FormData` so `<.form for={@form}>` / `<.inputs_for field={@form[:locations]}>` work unchanged.

## Data in (naming, parsing, coercion, nested/lists)

**.NET** (`model-binding.md`): binder searches `prefix.property_name` then bare `property_name`; `[Bind(Prefix=...)]`, `[ModelBinder(Name=...)]`, `[FromQuery(Name=...)]`. Collections accept five formats: `selectedCourses=1050&selectedCourses=2000`, `selectedCourses[0]=1050`, `[0]=1050`, `selectedCourses[]=1050` (form-data only), and **named indices** `selectedCourses[a]=1050&selectedCourses[b]=2000&selectedCourses.index=a&selectedCourses.index=b` — the escape hatch for client-side add/remove without renumbering. Numeric indices must be sequential from 0 ("gaps cause items after the gap to be ignored"). Dictionaries: `d[1050]=Chemistry` or `d[0].Key=1050&d[0].Value=Chemistry`. Empty string -> `null` for reference types by default (`[DisplayFormat(ConvertEmptyStringToNull=false)]` to disable); checkboxes rely on the `<input type=hidden name=X value=false>` twin emitted by `asp-for`. Tag helper `asp-for="Address.City"` emits `name="Address.City" id="Address_City"` plus `data-val="true" data-val-required="..."` attributes read by jQuery Unobtrusive Validation.

**Spring**: `@ModelAttribute` + `WebDataBinder` bind `user.groups[0].name` style paths via `BeanWrapper`; `List` auto-grows (`setAutoGrowNestedPaths`, `setAutoGrowCollectionLimit`, default 256); `@InitBinder` registers `PropertyEditor`s/`Formatter`s and `setDisallowedFields`. Bean Validation cascades via `@Valid` on nested/`List<@Valid Address>`; `ConstraintViolation.getPropertyPath()` yields `addresses[0].city`; `validator.validateProperty(bean, "email")` and `validateValue(User.class, "email", "x")` validate one field in isolation (useful for per-keystroke validation); groups (`@NotNull(groups=Create.class)`, `@Validated(Create.class)`) implement "different rules per action". **Thymeleaf** `th:object="${user}"` + `th:field="*{addresses[__${i}__].city}"` (`__${...}__` preprocessing evaluates the index before SpEL parsing) generates `name`/`id`/`value`; dynamic rows are done by re-posting the whole form with a special button (`th:formaction`/`params.addRow`) and letting the controller mutate the list — exactly a LiveView round-trip, sans websocket.

**Vaadin Binder**:
```java
BeanValidationBinder<Person> binder = new BeanValidationBinder<>(Person.class);
binder.bind(nameField, "name");
binder.forField(yearOfBirthField)
    .withConverter(new StringToIntegerConverter("Enter a number"))
    .withValidator(y -> y > 1900, "Too old")
    .bind("yearOfBirth");      // or bind(Person::getYear, Person::setYear)
binder.readBean(person);       // buffered: copies into fields
binder.writeBean(person);      // throws ValidationException; setBean() = unbuffered
binder.setValidationStatusHandler(status -> ...); // BinderValidationStatus: fieldValidationErrors + beanValidationErrors
```
The **converter runs before validators**, and a converter failure is itself a per-field error with a user message — the "typeMismatch is a normal error" rule.

**Go**: `gorilla/schema` decodes `Address.City`, `Items.0.Name` (dot-index) into structs via `schema:"name"` tags; `go-playground/form` decodes `Items[0].Name`, `Map[key]` and arbitrary nesting with `form:"name"` tags (and `RegisterCustomTypeFunc`). Neither validates. **go-playground/validator** tags: `required,email`, `min=18,max=120`, `eqfield=Password`, `required_if=Country usa`, `required_without=Alt`, `dive,required,min=3` (descend into slices/maps), struct-level `RegisterStructValidation`. Errors: `ValidationErrors []FieldError` with `Namespace()` (`User.Addresses[0].City`), `StructNamespace()`, `Field()`, `Tag()`, `Param()`, `Value()`, `Translate(ut.Translator)`; `RegisterTagNameFunc` swaps Go names for `json`/`form` tag names so `Namespace()` matches the wire names. `ozzo-validation` (code-based rules `validation.ValidateStruct(&a, validation.Field(&a.Street, validation.Required, validation.Length(5,50)))`) returns `validation.Errors` (`map[string]error`) which marshals to nested JSON `{"address":{"street":"cannot be blank"}}` — errors as a **tree mirroring the data**.

**Rust**: `serde_qs` = serde_urlencoded + nested keys `address[city]=x&vec[0]=1` (qs/Rails convention; `Config::new(max_depth, strict)`; ~50% slower than flat because of a two-pass parse). `serde_html_form` = flat urlencoded that maps repeated keys into `Vec<T>` (checkbox groups) — no nesting. Leptos `<ActionForm action=...>` posts a `<form>` to a server fn whose args are encoded with serde_qs, so nested struct args require inputs named `hefty_arg[first_name]` (Leptos book) — the same bracket convention as Phoenix. **Keats/validator**: `#[validate(email)]`, `length(min=1)`, `range`, `must_match(other="pw")`, `custom(function=...)`, `nested` (cascade), struct-level `#[validate(schema(function=..., skip_on_field_errors=true))]`; `ValidationError{code: Cow<str>, message: Option<Cow<str>>, params: HashMap<str, Value>}` (value auto-added under `"value"`), `ValidationErrors` = map of `ValidationErrorsKind::{Field(Vec<ValidationError>), Struct(Box<ValidationErrors>), List(BTreeMap<usize, Box<ValidationErrors>>)}` — again a **typed error tree** that serializes to nested JSON. **garde**: `#[garde(length(...), range(...), custom(f), dive, skip, context(Ctx), adapt(...))]`, `validate_with(&ctx)` for context-dependent rules (e.g. `PasswordContext{min_length}`), `Report` iterates `(Path, Error)` with paths like `items[0].name`; newtypes are `transparent` so paths stay clean.

**Functional**: digestive-functors names via `"name" .: text Nothing`, composes sub-forms with `"author" .: userForm` -> dotted paths `author.name`; `listOf` (unverified detail) produces `form.list.indices` + `form.list.0.field` names. Yesod: `fsName`/`fsId` auto-generated (`f1`, `f2`...) unless set in `FieldSettings{fsLabel, fsTooltip, fsId, fsName, fsAttrs}`; `Field{fieldParse :: [Text] -> [FileInfo] -> Handler (Either msg (Maybe a)), fieldView, fieldEnctype}`. Play: `Form(mapping("name" -> nonEmptyText, "homeAddress" -> mapping("street" -> text, "city" -> text)(Address.apply)(Address.unapply), "emails" -> seq(email))(User.apply)(User.unapply))`; browser must post `homeAddress.street`, `emails[0]`; `form.bindFromRequest().fold(hasErrors => BadRequest(view(hasErrors)), user => ...)`.

**LiveView ports**: LiveViewJS is *flat* (`issue.path[0]`, `name="${key}"`) — it never solved nesting. AshPhoenix reuses Phoenix's `form[posts][0][comments][1][body]` names; `add_form` accepts either `[:posts, 0, :comments]` or the html name `"form[posts][0][comments]"`.

## Validation & error model

- **.NET**: `ModelState` is `ModelStateDictionary` keyed by full path (`"Items[0].Name"`), each `ModelStateEntry{AttemptedValue, RawValue, Errors, ValidationState}`; `ModelState.AddModelError("Items[0].Name", msg)`; `ModelState.IsValid`. DataAnnotations messages use `{0}` = display name, `{1}`/`{2}` = params: `[StringLength(60, MinimumLength=3, ErrorMessage="{0} must be {2}-{1} chars")]`; `IValidatableObject.Validate(ValidationContext)` returns `ValidationResult(msg, memberNames)` for cross-field rules; server and client (`data-val-*`) share the same attributes. **FluentValidation**: `RuleFor(x => x.Name).NotEmpty().WithMessage("{PropertyName} is required")`, `RuleForEach(x => x.Orders).SetValidator(new OrderValidator())` -> `PropertyName = "Orders[0].Total"`; `OverrideIndexer((x, coll, el, i) => "<" + i + ">")` changes the bracket; `.When(x => x.IsCompany)`, `.Unless`, `.DependentRules`, `RuleSet("Create")`, `ChildRules(c => ...)` for inline collection rules; `ValidationFailure{PropertyName, ErrorMessage, ErrorCode, AttemptedValue, FormattedMessagePlaceholderValues}`. Its ASP.NET adapter writes failures straight into `ModelState` at the same paths.
- **Spring**: `BindingResult` holds `FieldError(objectName, field, rejectedValue, bindingFailure, codes[], arguments[], defaultMessage)`; `errors.rejectValue("email", "duplicate", "already used")`. `DefaultMessageCodesResolver.resolveMessageCodes(errorCode, objectName, field, fieldType)` returns, in order: `code.object.field`, `code.field`, `code.fieldType`, `code`, and for indexed fields both `typeMismatch.user.groups[0].name` and `typeMismatch.user.groups.name` (index-stripped) variants; `Format.PREFIX_ERROR_CODE` vs `POSTFIX_ERROR_CODE`. `SpringValidatorAdapter` maps Bean Validation violations onto that same `FieldError` model (code = annotation simple name, e.g. `NotNull.user.email`). Bean Validation messages: `"{jakarta.validation.constraints.Size.message}"` templates with `{min}`/`{max}` and `${validatedValue}` EL; `ConstraintViolation{propertyPath, invalidValue, messageTemplate, constraintDescriptor.attributes}`.
- **Go/Rust/Kotlin**: see above — all carry `(path, code/tag, params, value)`. go-playground translations: `en_translations.RegisterDefaultTranslations(v, trans)`; `v.RegisterTranslation("required", trans, registerFn, translateFn)`; `err.Translate(trans)`. konform (unverified specifics): `Validation<User>{ User::name { minLength(2) hint "..." }; User::addresses onEach { Address::city { ... } } }`, result `Invalid.errors` each with `dataPath ".addresses[0].city"` and `message`.
- **Yesod**: `FormResult a = FormMissing | FormFailure [Text] | FormSuccess a` (tri-state: distinguishes *not submitted* from *invalid*); `checkBool (>= 1990) "Year too old" intField`, `checkM` for monadic (DB) checks, `convertField`. **elm-form**: `Validation.succeed SignUp |> Validation.andMap name |> Validation.andMap email |> Validation.andThen (\v -> if ... then Validation.fail "..." field else ...)`; `Validation.global` for form-level errors; `Form.Validated = Valid a | Invalid (Maybe a) errors`; errors are shown according to `FieldStatus` (NotVisited/Focused/Changed/Blurred) and `submitAttempted`.
- **Timing**: Blazor validates on `OnFieldChanged` (per-field, `messageStore.Clear(e.FieldIdentifier)` then re-add) and on `OnValidationRequested` (submit); Blazor 11 adds `RegisterAsyncFieldValidator(fieldIdentifier, token => ...)` with `pending`/`faulted` states. AshPhoenix: `validate/3` on every phx-change, `submit/2` runs the action; errors suppressed until `submitted_once?` unless `errors: true`. LiveViewJS: `action` undefined = "empty form, don't validate" (`valid` forced true), and `_target` present = "only report the target field's error".

## Form state (bound/unbound, touched/used, attempted values)

| Concept | .NET | Blazor | Spring | Vaadin | AshPhoenix | elm-form | yesod |
|---|---|---|---|---|---|---|---|
| unbound vs bound | new model vs `ModelState` non-empty | — | `BindingResult` absent | `readBean` | `for_create` (empty) vs after `validate` | `Form.init` | `generateFormPost` vs `runFormPost`; `FormMissing` |
| attempted value | `ModelStateEntry.AttemptedValue` | field holds raw | `FieldError.rejectedValue` | field component holds raw | `form.params` | `Form.Model` (raw strings) | `fieldParse [Text]` |
| touched/modified | — | `IsModified(field)`, `MarkAsUnmodified` | — | `hasChanges()` | `touched_forms` (MapSet; only touched keys are submitted), `changed?` | `FieldStatus` | — |
| submitted-once | — | — | — | — | `submitted_once?`, `just_submitted?` | `submitAttempted` | — |
| classes | `input-validation-error` | `valid`/`invalid`/`modified` via `FieldCssClassProvider` | `th:errorclass` | `invalid` on component | — | attrs from `FieldView` | — |

Key .NET lesson (verbatim from docs): "When the page is redisplayed... the invalid input isn't shown in the form field. This is because the model property has been set to null or a default value" — i.e. if you re-render from the typed model, you lose what the user typed; render from `AttemptedValue`/params.

## Rendering & customization & styling

- **.NET**: `asp-for` tag helpers + `EditorTemplates/` folder: `@Html.EditorFor(m => m.Address)` looks up `Views/Shared/EditorTemplates/Address.cshtml` by *type name* or by `[UIHint("Money")]` on the property — a **widget registry keyed by type then by hint**; `[Display(Name=..)]`, `[DataType(DataType.Password)]` feed it. Blazor: `InputText/InputNumber/InputSelect/InputCheckbox` all extend `InputBase<T>` (`CurrentValueAsString`, `TryParseValueFromString`, `CssClass`), `ValidationMessage For="() => Model.Name"`, `ValidationSummary`; `editContext.SetFieldCssClassProvider(new CustomFieldClassProvider())` overriding `GetFieldCssClass(EditContext, in FieldIdentifier)` is the only global styling hook (returns e.g. Bootstrap `is-invalid`).
- **Thymeleaf**: `th:field` sets `id/name/value` (and `checked`/`selected`), `th:errors="*{email}"`, `th:errorclass="is-invalid"`, `#fields.hasErrors('*')`, `#fields.globalErrors()`. Markup stays hand-written; no widget layer.
- **Play**: `@helper.inputText(form("email"), '_label -> "Email", '_help -> "...")`; underscore-prefixed args go to the **FieldConstructor** (`@implicitFieldConstructor = @{ FieldConstructor(myFieldConstructorTemplate.f) }`) which wraps every input with label/errors/help — a theme-able "field chrome" separate from the input element (Bootstrap ships as `b3.vertical.fieldConstructor`).
- **Yesod**: `renderDivs` / `renderTable` / `renderBootstrap3 BootstrapBasicForm` are `FormRender` functions passed to `renderXxx form extra` — the layout is a *parameter*, the form definition doesn't know it; `fsAttrs = [("class","form-control"),("placeholder","...")]` per field.
- **digestive-functors**: `View` + `digestive-functors-blaze` helpers: `label "name" view "Name: "`, `inputText "name" view`, `errorList "mail" view`, `childErrorList "package" view`, `subView "author" view` for nested rendering. Names in the view are dotted paths.
- **elm-form**: `Form.renderHtml` gets a `FieldView` per field (`FieldView.input [] info.name`, `info.errors`, `info.status`), so any HTML/CSS library; the library owns no markup.
- **LiveViewJS**: `form_for("#", csrf, {phx_submit:"save", phx_change:"validate"})`, `text_input(changeset, "name", {placeholder, phx_debounce, className})`, `error_tag(changeset, "name")` -> `<span class="invalid-feedback" phx-feedback-for="name">`; `options_for_select`, `live_file_input`, `submit`. Minimal, not customizable beyond `className`.
- **AshPhoenix**: nothing of its own; relies on Phoenix `to_form/2` + generated `CoreComponents.input` (`<.input field={@form[:email]} />`), which is where `name`, `id`, `value`, `errors` and Tailwind classes live and are user-owned.

## Nested / dynamic / conditional

- **AshPhoenix** (best in class for pyview): `forms: [auto?: true]` derives nested forms from relationships/embeds/unions; `<.inputs_for :let={loc} field={@form[:locations]}>`; add via hidden checkbox `name="form[_add_locations]" value="end"` ("start"/"end"/index) or `AshPhoenix.Form.add_form(form, [:locations], params: %{...})`; drop via `name="form[_drop_locations][]" value={loc.index}` or `remove_form(form, path)`; `errors_for(form, path)`; union sub-forms carry `_union_type` hidden param, `add_form(path, params: %{"_union_type" => new_type})`, and templates `case fc.params["_union_type"]` to render the variant. Sort via `sort_param` (Phoenix 1.7 `inputs_for` `_sort` / `_drop` convention, unverified here).
- **.NET**: `Items.index=a` named-index trick; `EditorFor(m => m.Items)` auto-emits `Items[0].Name` prefixes for each element via `ViewData.TemplateInfo.HtmlFieldPrefix`; FluentValidation `.When()` for conditional rules; `[ValidateComplexType]` + `ObjectGraphDataAnnotationsValidator` (Blazor experimental package) needed because plain `DataAnnotationsValidator` does *not* recurse into nested objects.
- **Spring**: auto-grow lists on bind; `@Valid` cascade; groups for conditional rules; Thymeleaf `__${i}__` + re-post for add/remove rows.
- **elm-form** `Form.dynamic`: the only formlet with true dependent fields (a `kind` select decides which further fields exist and how to parse them); otherwise conditionals are `Validation.andThen`.
- **Play**: `seq/list/optional` mappings; `@repeat(form("emails"), min=1) { emailField => @inputText(emailField) }`; `tuple`/`mapping` nesting; `verifying("msg", user => ...)` for cross-field at any level.
- **Rust/Go**: nesting is free from serde/reflection (`serde_qs` depth-limited; `dive`/`nested`/`dive` tags for validation); conditionals via `required_if=Field value`, `skip_on_field_errors`, garde `context`.

## DX highlights with real code

1. **LiveViewJS changeset factory** (`changeset.ts`, verbatim core):
```ts
export const newChangesetFactory = <T>(schema: SomeZodObject): LiveViewChangesetFactory<T> =>
  (existing, newAttrs, action?) => {
    const merged = { ...existing, ...newAttrs };
    const result = schema.safeParse(merged);
    let errors;
    if (result.success === false) {
      const target = (newAttrs as any)["_target"] ?? false;
      errors = result.error.issues.reduce((acc, issue) => {
        if (target) { if (issue.path[0] === target) acc[target] = issue.message; return acc; }
        acc[issue.path[0]] = issue.message; return acc;
      }, {} as LiveViewChangesetErrors<T>);
    }
    return { action, changes: updatedDiff(existing, merged),
      data: result.success ? result.data : merged,
      valid: action !== undefined ? result.success : true, errors };
  };
```
The `// TODO recursively walk the full tree` comment is the exact wall pyview is at.

2. **AshPhoenix lifecycle** (moduledoc):
```elixir
def handle_event("validate", %{"form" => params}, socket),
  do: {:noreply, assign(socket, :form, AshPhoenix.Form.validate(socket.assigns.form, params))}
def handle_event("submit", %{"form" => params}, socket) do
  case AshPhoenix.Form.submit(socket.assigns.form, params: params) do
    {:ok, _user} -> {:noreply, push_navigate(socket, to: ~p"/")}
    {:error, form} -> {:noreply, assign(socket, :form, form)}
  end
end
# add nested: AshPhoenix.Form.add_form(form, [:posts, 0, :comments], params: %{"_union_type" => "text"})
```

3. **digestive-functors** composition + dotted names (`tutorial.lhs`):
```haskell
userForm = User <$> "name" .: text Nothing
                <*> "mail" .: check "Not a valid email address" checkEmail (text Nothing)
releaseForm = Release <$> "author" .: userForm <*> "package" .: packageForm
releaseView view = do userView (subView "author" view); childErrorList "package" view; inputText "package.name" view
```

4. **Blazor custom validation store** (validation.md):
```csharp
messageStore = new ValidationMessageStore(editContext);
editContext.OnValidationRequested += (s, e) => { messageStore.Clear(); /* add errors */ };
editContext.OnFieldChanged += (s, e) => messageStore.Clear(e.FieldIdentifier);
messageStore.Add(() => Model.Property, "Error message");
editContext.NotifyValidationStateChanged();
```

5. **go-playground/validator** conditional + dive + translated errors:
```go
type Form struct {
    Country  string   `validate:"required"`
    PostCode string   `validate:"required_if=Country usa"`
    Confirm  string   `validate:"required,eqfield=Password"`
    Emails   []string `validate:"dive,email"`
}
for _, fe := range err.(validator.ValidationErrors) { fmt.Println(fe.Namespace(), fe.Tag(), fe.Param(), fe.Translate(trans)) }
```

6. **Spring message-code fallback** (javadoc): for `typeMismatch`, object `user`, field `groups[0].name`: `typeMismatch.user.groups[0].name` -> `typeMismatch.user.groups.name` -> `typeMismatch.groups[0].name` -> `typeMismatch.groups.name` -> `typeMismatch.name` -> `typeMismatch.java.lang.String` -> `typeMismatch`.

7. **Play** repeat + fold:
```scala
val userForm = Form(mapping("name" -> nonEmptyText, "emails" -> seq(email),
  "homeAddress" -> mapping("street" -> text, "city" -> text)(Address.apply)(Address.unapply)
)(User.apply)(User.unapply).verifying("bad", u => u.emails.nonEmpty))
userForm.bindFromRequest().fold(withErrors => BadRequest(views.html.user(withErrors)), user => Redirect(...))
// template: @repeat(userForm("emails"), min = 1) { emailField => @inputText(emailField) }
```

## Pain points & criticisms (cite)

- .NET: numeric-gap rule silently drops items (docs); `DataAnnotationsValidator` does not recurse (`ObjectGraphDataAnnotationsValidator` is still "experimental"); re-render from typed model loses attempted input (docs warning); DataAnnotations can't express cross-field rules well (`IValidatableObject` runs only after all property validators pass) — hence FluentValidation's existence. FluentValidation issue #274/#874: `RuleForEach` property-chain/name overriding surprises.
- Spring: string-typed binding via `PropertyEditor`s is dated; BindingResult must be the *very next* parameter after `@ModelAttribute` or you get an exception; Thymeleaf dynamic rows require a full re-post (slow UX without JS).
- Vaadin: two modes (`setBean` unbuffered vs `readBean/writeBean` buffered) confuse users; validators run per binding *and* per bean, in different phases (`BinderValidationStatus` splits `fieldValidationErrors`/`beanValidationErrors`).
- Go/Rust struct-tags: string-typed DSL with no compile-time checking (`required_if=Country usa` typos), error `Namespace()` uses Go field names unless `RegisterTagNameFunc`; serde_qs has "quirks with optional types and enums with tuple variants" (Leptos discussion #2714); Keats/validator `ValidationErrors` is awkward to walk (three-variant enum).
- Formlets: applicative-only shape cannot express dependent fields (elm-form needed `Form.dynamic`; digestive-functors has none); yesod's `MForm` monadic escape hatch loses automatic layout; Play helper templates are ugly to customize (FieldConstructor Twirl).
- LiveViewJS: flat `path[0]` errors, `name=key`, no nested forms; abandoned-ish maintenance. AshPhoenix: `params/2` shape is unstable after `add_form` with non-string keys (its own docs warn); heavy dependence on Ash resources — not portable as-is.

## Lessons for pyview — steal / adapt / avoid

**Steal**
1. **Bracket path codec + structured error tree** (Phoenix/Rails/serde_qs/ozzo/Keats): decode `user[addresses][0][city]` in `ws_handler` into nested dict/list, feed to Pydantic; convert `ValidationError.errors()` (`loc`, `type`, `msg`, `input`, `ctx`) into a tree addressable by the same path, keep `type`+`ctx` for i18n/overrides.
2. **AshPhoenix `_add_x` / `_drop_x[]` / `_union_type` params handled inside `validate()`**, plus `form.add_form(path)` / `remove_form(path)` API and `inputs_for(field)` helper yielding sub-forms with computed `name`/`id`/`index`. Zero JS needed; conditional nesting = Pydantic `Discriminator` -> `_union_type`.
3. **Attempted-value store separate from model** (.NET `AttemptedValue`, Spring `rejectedValue`, elm-form `Form.Model`): `form.params` (raw strings) is what inputs render; `form.model` is `Optional[T]`.
4. **Form-state flags** from AshPhoenix + elm-form: `submitted_once`, `just_submitted`, `touched` (per path set, replacing "key in changes"; feed from `_target` and, when upgrading the JS client, `_unused_`), `changed`.
5. **Message-code fallback hierarchy** (Spring): resolve `f"{type}.{form}.{path}"` -> `f"{type}.{path_without_indices}"` -> `f"{type}"` against a user-supplied dict/gettext with `ctx` params; Pydantic `type` strings (`string_too_short`, `missing`) are the codes.
6. **Widget registry by type-then-hint** (.NET EditorTemplates/`[UIHint]`, yesod `Field` record with `fieldParse`+`fieldView`): map Pydantic annotation -> widget, override per field via `Field(json_schema_extra={"widget": "textarea"})` or `Annotated[str, Widget(...)]`; users register their own.

**Adapt**
- **FieldConstructor / renderer-as-parameter** (Play, yesod `renderBootstrap3`, Blazor `FieldCssClassProvider`): separate *input element* generation from *field chrome* (label/help/errors/classes); ship a plain + Tailwind renderer, let users pass a t-string function.
- **Per-field validation** (Bean Validation `validateProperty`, Blazor `OnFieldChanged` clearing only that field): on phx-change validate whole model but *display* per touched path; give hooks for async/DB checks that write into a `ValidationMessageStore`-like `form.add_error(path, msg)`.
- **Coercion rules table** (.NET empty-string->null, checkbox hidden twin, Spring auto-grow lists): define once, per Pydantic type, before validation.

**Avoid**
- Flat `errors[loc[0]]` and `name=key` (LiveViewJS) — dead end for nesting.
- Sequential-only indices that silently drop rows (.NET) — accept any index tokens, sort them.
- Validating from the typed model on re-render (.NET pitfall).
- Stringly-typed rule DSLs in tags (Go/Rust) — Pydantic validators are Python, keep it that way.
- Two buffering modes (Vaadin) — pyview has one: changeset over websocket.

**Ranked 12 most transferable ideas**
1. Nested bracket-path decoding + path-addressed error tree (Phoenix/serde_qs/Keats/ozzo).
2. `_add_*`/`_drop_*` hidden params + `add_form/remove_form(path)` (AshPhoenix).
3. `_union_type` discriminator for conditional sub-forms (AshPhoenix) <-> Pydantic discriminated unions.
4. Raw attempted values vs typed model (.NET ModelState / Spring rejectedValue / elm-form).
5. `submitted_once?`/`touched_forms`/`just_submitted?` flags (AshPhoenix) + `FieldStatus` (elm-form).
6. Message-code fallback with index stripping (Spring `DefaultMessageCodesResolver`).
7. Error records `{code, message, params, path}` (Keats validator / FluentValidation `ValidationFailure`).
8. Renderer-as-parameter / FieldConstructor for styling (yesod `renderBootstrap3`, Play, Blazor `FieldCssClassProvider`).
9. Widget registry keyed by type then hint (.NET EditorTemplates/`[UIHint]`, yesod `Field`).
10. `inputs_for` sub-form objects carrying `name`/`id`/`index`/`params`/`errors` (Phoenix/AshPhoenix, `.NET HtmlFieldPrefix`).
11. Converter-before-validator with type-mismatch as normal field error (Vaadin `withConverter`, Spring `typeMismatch`).
12. Applicative "static shape" = the Pydantic class; `Form.dynamic`-style escape hatch for truly dependent fields (elm-form, digestive-functors).

## Sources
- https://raw.githubusercontent.com/dotnet/AspNetCore.Docs/main/aspnetcore/mvc/models/model-binding.md
- https://raw.githubusercontent.com/dotnet/AspNetCore.Docs/main/aspnetcore/blazor/forms/validation.md
- FluentValidation: https://github.com/FluentValidation/FluentValidation/issues/274, /issues/874, /issues/1293 (via WebSearch summaries of docs collections.html)
- https://raw.githubusercontent.com/spring-projects/spring-framework/main/spring-context/src/main/java/org/springframework/validation/DefaultMessageCodesResolver.java
- Vaadin Binder javadoc / docs summaries: https://javadoc.io/static/com.vaadin/flow-data/2.1.4/com/vaadin/flow/data/binder/Binder.html, https://vaadin.com/docs/latest/flow/binding-data/components-binder-beans
- https://github.com/go-playground/validator (README)
- https://github.com/Keats/validator (README)
- https://github.com/jprochazk/garde (README)
- https://github.com/samscott89/serde_qs (README); Leptos: https://book.leptos.dev/progressive_enhancement/action_form.html, https://github.com/leptos-rs/leptos/discussions/2714 (search summaries)
- https://raw.githubusercontent.com/jaspervdj/digestive-functors/master/examples/tutorial.lhs
- https://raw.githubusercontent.com/yesodweb/yesodweb.com-content/master/book/asciidoc/forms.asciidoc
- https://github.com/dillonkearns/elm-form (README)
- https://raw.githubusercontent.com/playframework/playframework/main/documentation/manual/working/scalaGuide/main/forms/ScalaForms.md
- Clone: repos/liveviewjs/packages/core/src/server/changeset/changeset.ts, templates/helpers/inputs.ts
- Clone: repos/ash_phoenix/lib/ash_phoenix/form/form.ex (moduledoc, add_form/remove_form/add_error), documentation/topics/nested-forms.md, union-forms.md, lib/ash_phoenix/form/auto.ex
