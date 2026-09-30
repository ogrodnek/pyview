# JS/TS Form Library Ecosystem (2026): Ideas That Transfer to a Server-Driven, Schema-First pyview Form Library

Scope: Conform, Superforms, TanStack Form, React Hook Form, older libraries (Formik, Final Form, Felte, VeeValidate, Modular Forms/Formisch), schema-driven auto-form generators (RJSF, JSON Forms, Formily, uniforms, AutoForm), Standard Schema, headless/accessible field primitives (React Aria, shadcn `Field`), error-timing UX consensus, and React 19 / server-action trends. Most facts come from the libraries' own docs, read from their GitHub doc sources in Sept 2026. Versions and dates come from the npm registry and were checked on 2026-09-30.

Version snapshot (npm `latest` dist-tag and its publish date, checked 2026-09-30 via registry.npmjs.org):

| Package | Latest | Published | Note |
|---|---|---|---|
| @conform-to/react | 1.21.1 | 2026-08-18 | active; the "future" APIs are experimental |
| sveltekit-superforms | 2.31.0 | 2026-09-30 | active |
| @tanstack/react-form | 1.33.5 | 2026-08-11 | active, v1 |
| react-hook-form | 7.89.0 | 2026-09-26 | active, v7 |
| formik | 2.4.9 | 2025-11-10 | slow-moving; a `next` tag at 3.0.0-next.8 |
| final-form / react-final-form | 5.0.1 / 7.0.1 | 2026-05-05 | maintained |
| @felte/core | 1.4.4 | 2024-10-29 | no release for about 2 years |
| vee-validate | 4.15.1 | 2025-06-07 | Vue |
| @modular-forms/react | 0.12.0 | 2026-01-18 | in maintenance; replaced by Formisch |
| @formisch/react | 1.1.0 | 2026-09-08 | successor to Modular Forms |
| @formily/core | 2.3.7 | 2025-05-15 | slow-moving |
| @rjsf/core | 6.11.0 | 2026-09-29 | active, v6 |
| @jsonforms/core | 3.8.0 | 2026-06-16 | active |
| uniforms | 4.0.0 | 2025-02-28 | v4 |
| @autoform/core | 4.0.0 | 2026-07-08 | active |

Source for all rows: npm registry (for example [formik](https://www.npmjs.com/package/formik), [@conform-to/react](https://www.npmjs.com/package/@conform-to/react), [@felte/core](https://www.npmjs.com/package/@felte/core)).

---

## Q1. Conform (Remix/React Router/Next.js): schema-first, progressive enhancement, intent-driven list operations

### Takeaway
Conform fits a server-driven design better than any other JS library. Form state is plain `FormData` with path-encoded names (`tasks[0].content`). Every structural operation (validate, reset, update, insert, remove, reorder) is an **intent**: a serialized string placed on a reserved submit-button name. The server can resolve an intent to a new target value, validate that value and send it back, so dynamic lists work with **no JavaScript**. The newer "future" API (experimental in 1.x) formalizes this as a server-side pipeline: `parseSubmission → resolveSubmission → validate → report`. It also adds pluggable custom intents (`defineIntent`) and a schema-adapter factory (`configureForms`). A Python server-side implementation can copy this design almost directly.

### Cited Findings

**Status and positioning**
- Version 1.21.1, MIT, © 2026 Edmund Hung. Features listed: "Full type safety with schema field inference", "Standard Schema support with enhanced Zod and Valibot integration", "Progressive enhancement first design with built-in accessibility features", "Native Server Actions support for Remix and Next.js", "Built on web standards" — [Conform README](https://github.com/edmundhung/conform/blob/main/README.md)
- The "future" export (`@conform-to/react/future`) is experimental: "These APIs are experimental and may change in minor versions." They are opt-in, may break in minors (the author says to lock to patch versions), and are the path to v2. The author's motivation: "We have seen where people get stuck, where the API causes confusion, and where the complexity starts to pile up", with the goal of being "simpler, more flexible, and easier to reason about without giving up type safety or progressive enhancement" — [Conform future discussion #954](https://github.com/edmundhung/conform/discussions/954); [future useForm doc](https://github.com/edmundhung/conform/blob/main/docs/api/react/future/useForm.md)

**Naming convention for nested and array data**
- "Conform uses the `object.property` and `array[index]` syntax… e.g. `tasks[0].content`. If the form data has an entry `['tasks[0].content', 'Hello World']`, the object constructed will become `{ tasks: [{ content: 'Hello World' }] }`." Names are generated from field metadata, not written by hand — [Complex structures](https://github.com/edmundhung/conform/blob/main/docs/complex-structures.md)
- `parseSubmission(formData)` rules: `name`, `object.property`, `array[0]`, and `items[]` (repeated values become an array). It returns `{ payload, fields: string[], intent: string | null }`. The intent field name defaults to `__INTENT__` and can be changed with `intentName`. `skipEntry` excludes fields — [parseSubmission](https://github.com/edmundhung/conform/blob/main/docs/api/react/future/parseSubmission.md)
- Security advice: enforce limits on parts, fields, total size and files **before** parsing — [parseSubmission](https://github.com/edmundhung/conform/blob/main/docs/api/react/future/parseSubmission.md)

**v1 server flow (still the stable API)**
```tsx
export async function action({ request }) {
  const formData = await request.formData();
  const submission = parseWithZod(formData, { schema });
  if (submission.status !== 'success') {
    return submission.reply();                      // errors + last payload back to client
  }
  const message = await sendMessage(submission.value);
  if (!message.sent) {
    return submission.reply({ formErrors: ['Failed to send the message. Please try again later.'] });
  }
  return redirect('/messages');
}
```
— [Conform tutorial](https://github.com/edmundhung/conform/blob/main/docs/tutorial.md)
- `parseWithZod` coerces automatically by default. It "strip[s] empty value and coerce[s] form value to the correct type by introspecting the schema". It can be turned off with `disableAutoCoercion`. It also takes `async: true` (uses `safeParseAsync`) and `formatError` — [parseWithZod](https://github.com/edmundhung/conform/blob/main/docs/api/zod/parseWithZod.md)
- Field metadata API: `fields.address.getFieldset()` for objects and `fields.tasks.getFieldList()` for arrays. Each list item has a stable `key` to use as the React key (`<li key={task.key}>`) — [Complex structures](https://github.com/edmundhung/conform/blob/main/docs/complex-structures.md)
- `getInputProps(meta, { type })` returns id, name, default value or checked state, constraint attributes, and `aria-invalid`/`aria-describedby`. `ariaInvalid` can be based on `errors` or `allErrors`, and `ariaDescribedBy` can append a `descriptionId` — [getInputProps](https://github.com/edmundhung/conform/blob/main/docs/api/react/getInputProps.md)

**Intent buttons (the key idea for pyview)**
- "A submit button will contribute to the form data when it triggers the submission as a submitter… Conform utilizes the submission intent for all form controls, such as validating or removing a field. This is achieved by giving the buttons a reserved name with the intent serialized as the value." — [Intent button](https://github.com/edmundhung/conform/blob/main/docs/intent-button.md)
- v1 helpers:
```tsx
<button {...form.validate.getButtonProps({ name: fields.email.name })}>Validate Email</button>
<button {...form.reset.getButtonProps({ name: fields.tasks.name })}>Reset field</button>
<button {...form.update.getButtonProps({ name: fields.agenda.name, value: { title: 'My agenda' } })}>Update</button>
<button {...form.update.getButtonProps({ validated: false })}>Clear all error</button>
<button {...form.reorder.getButtonProps({ name: fields.tasks.name, from: index, to: 0 })}>Move to top</button>
<button {...form.remove.getButtonProps({ name: fields.tasks.name, index })}>Delete</button>
<button {...form.insert.getButtonProps({ name: fields.tasks.name })}>Add task</button>
```
Reset and update need inputs keyed by the field `key`, because Conform "relies on the key to notify React for re-mounting the input with the updated initialValue" — [Intent button](https://github.com/edmundhung/conform/blob/main/docs/intent-button.md)
- In the future API, each intent method has a `serialize()` that returns the button value without dispatching it, "which lets a native submit button trigger the same form intent when JavaScript is unavailable":
```tsx
<button name={form.intentName} value={intent.validate.serialize('title')}>Validate title</button>
```
— [useIntent](https://github.com/edmundhung/conform/blob/main/docs/api/react/future/useIntent.md)
- The wire format is `type(jsonArgs…)`. For example, `insert({"name":"tasks"})` is produced by `${intent.type}(${JSON.stringify(args).slice(1,-1)})`, with a sentinel for `undefined` args. Deserialization checks that the string ends with `)` and JSON-parses `[args]` — [intent.ts source](https://github.com/edmundhung/conform/blob/main/packages/conform-react/future/intent.ts)
- The built-in intent set and options: `validate(name?)`, `reset({defaultValue?})`, `update({name?, index?, value})`, `insert({name, index?, defaultValue?, from?, onInvalid?: 'revert'})`, `remove({name, index, onInvalid?: 'revert' | 'insert', defaultValue?})`, `reorder({name, from, to})`. `insert({from: 'newTag'})` validates the source field, inserts it if valid and clears the source, or cancels and shows the error on the source field. `onInvalid: 'revert'` cancels an insert or remove that would break array constraints such as max or min items — [useIntent](https://github.com/edmundhung/conform/blob/main/docs/api/react/future/useIntent.md)

**Server-side intent resolution (future API)**
```ts
export async function action({ request }) {
  const formData = await request.formData();
  const submission = parseSubmission(formData);
  const { intent, targetValue } = resolveSubmission(submission);  // applies insert/remove/... to payload
  const result = schema.safeParse(targetValue);
  if (!intent) return new Response('Invalid form intent', { status: 400 });
  if (intent.type !== 'submit' || !result.success) {
    return report(submission, { targetValue, error: result.success ? null : result.error });
  }
  await save(result.data);
  return report(submission, { reset: true });
}
```
Resolution rules: a missing intent becomes `{type:'submit'}`. Values matching `type(...)` go through the registered handlers, and unknown or malformed ones return `undefined`. **Any other value is a submit intent that carries the raw value** (e.g. `delete` → `{type:'submit', payload:'delete'}`), so plain "Save" and "Delete" buttons can share the intent field name — [resolveSubmission](https://github.com/edmundhung/conform/blob/main/docs/api/react/future/resolveSubmission.md)
- `report(submission, options)` builds the result sent to the client. `error` takes either Standard Schema `issues` or `{formErrors, fieldErrors}`, with `null` meaning valid. Other options: `targetValue` (a new value to apply), `reset`, `keepFiles` (default false: files are stripped because they cannot re-initialize file inputs), and `hideFields: ['password','confirmPassword']` so secrets are never echoed back — [report](https://github.com/edmundhung/conform/blob/main/docs/api/react/future/report.md)

**Custom intents**
- `defineIntent({ parse, resolve, apply, touch, move })`. `parse` validates the arguments. `resolve({value, payload})` returns the new form value. `apply` adjusts the result (the built-in reset returns `{reset:true}`). `touch({name, payload})` decides which fields become touched. `move` keeps per-item state when list items move; without it, state under the changed paths is invalidated. Example: a `copyField` intent that copies billing to shipping with `setPathValue(value, payload.to, getPathValue(value, payload.from))`. Intents can be registered globally through `configureForms({ intents })` or per form — [defineIntent](https://github.com/edmundhung/conform/blob/main/docs/api/react/future/defineIntent.md)

**Validation timing and state model**
- `shouldValidate: 'onSubmit' | 'onBlur' | 'onInput'` (default `onSubmit`) and `shouldRevalidate` (default: same as `shouldValidate`). Example: "validate on blur initially, but revalidate on every input after the first validation." — [configureForms](https://github.com/edmundhung/conform/blob/main/docs/api/react/future/configureForms.md)
- Future `useForm` "manages validation state (errors, touched, valid) that updates on events like submit or blur, not on every keystroke" — [future useForm](https://github.com/edmundhung/conform/blob/main/docs/api/react/future/useForm.md)
- Internal `FormState` shape (future): `{ resetKey, defaultValue, targetValue /* values to sync to DOM */, serverValue, serverError, clientError, touchedFields: string[], listKeys: Record<string,string[]>, customState }`. Server errors and client errors are stored separately. Touched is a flat list of path names. List keys are stored per array path — [types.ts](https://github.com/edmundhung/conform/blob/main/packages/conform-react/future/types.ts)
- A field counts as "touched" when validated "through `intent.validate()` or the `shouldValidate` option". Field metadata includes `touched`, `valid`, `errors`, `fieldErrors` (errors of touched subfields), `ariaInvalid`, `ariaDescribedBy`, generated `id`/`errorId`/`descriptionId` (`{formId}-field-{fieldName}`), `defaultValue`, `defaultOptions`, `defaultChecked`, constraint attributes (`required`, `minLength`, `maxLength`, `pattern`, `min`, `max`, `step`, `multiple`), `getFieldset()` and `getFieldList()` — [future useField](https://github.com/edmundhung/conform/blob/main/docs/api/react/future/useField.md)
- Skipping expensive validation by intent. The schema is a function of the intent, and a field can return a `VALIDATION_SKIPPED` issue so the previous result is reused:
```ts
schema: (intent) => createSchema(intent, { isEmailUnique }),
// inside: const isValidatingEmail = intent === null || (intent.type === 'validate' && intent.payload.name === 'email');
// if (!isValidatingEmail) ctx.addIssue({ code: 'custom', message: conformZodMessage.VALIDATION_SKIPPED });
```
— [Validation](https://github.com/edmundhung/conform/blob/main/docs/validation.md)
- Async validation runs only on the server (`async: true`). The client schema leaves `isEmailUnique` unimplemented and marks it `VALIDATION_UNDEFINED`, which defers to the server — [Validation](https://github.com/edmundhung/conform/blob/main/docs/validation.md)
- Staged async validation: `onValidate` returns `{ result, pending }`. `result` is applied immediately and the `pending` promise replaces it later — [future useForm](https://github.com/edmundhung/conform/blob/main/docs/api/react/future/useForm.md)

**Schema adapter factory**
- `configureForms({ isSchema, validateSchema(schema, payload, options) → {error, value?}, getConstraints(schema) → Record<path, ValidationAttributes>, serialize, intents, shouldValidate, shouldRevalidate, isError: shape<string[]>(), extendFormMetadata, extendFieldMetadata(metadata, ctx) })`. It returns customized `useForm`, `useField`, `useIntent`, `FormProvider` and `resolveSubmission`. `extendFieldMetadata` is the hook for UI-kit integration, and `ctx.when` exposes shape-dependent props — [configureForms](https://github.com/edmundhung/conform/blob/main/docs/api/react/future/configureForms.md)
- Default value serializer: `true → 'on'`, `false → null`, Date → UTC datetime without `Z`, numbers → `.toString()`, strings and Files unchanged — [configureForms](https://github.com/edmundhung/conform/blob/main/docs/api/react/future/configureForms.md)
- `isDirty(formData, { defaultValue, serialize })` compares current form data with the serialized defaults, for example to warn about unsaved changes — [isDirty](https://github.com/edmundhung/conform/blob/main/docs/api/react/future/isDirty.md)

**Conditional fields and hidden steps**
- `PreserveBoundary name="step-1"` keeps the values of unmounted fields for "multi-step wizards, form dialogs, and virtualized lists". The docs warn to use it "only for navigational conditions… not when the user is intentionally excluding data": a conditionally hidden `discountCode` should simply unmount so it is not submitted. Stale preserved values "are automatically removed on remount" when the fields inside change, for example after switching account type — [PreserveBoundary](https://github.com/edmundhung/conform/blob/main/docs/api/react/future/PreserveBoundary.md)
- `<FormStateInput/>` renders a hidden input that holds form state across a full document reload. Without it, information about which fields were validated is lost after a no-JS non-submit intent (e.g. insert) — [FormStateInput](https://github.com/edmundhung/conform/blob/main/docs/api/react/FormStateInput.md)

### Inferences
- In pyview, form state already lives on the server, so the "no-JS fallback" path becomes the main path. Every intent can be a `phx-click` or `phx-submit` whose value is the serialized intent. `insert`, `remove` and `reorder` then run on the server's value tree, list keys are regenerated, and the view re-renders. The same `type(args)` wire format could work over both Phoenix events and plain POST, which keeps a no-websocket fallback possible.
- Conform's separation of **submission** (raw payload + intent), **resolution** (intent → targetValue), **validation** and **report** (errors + targetValue + reset + hidden fields) maps cleanly to a Python pipeline: `parse_form(params) → resolve_intent() → schema.validate() → FormResult`.
- Keeping `touchedFields` as a flat set of path strings and `listKeys` as per-array-path lists of stable keys is a small, serializable model that suits server-held state. Stable keys matter because Phoenix's DOM patching relies on stable `id`s. This is an inference and was not verified against pyview's patcher.
- Two ideas carry over directly: `hideFields` (never echo passwords back) and `keepFiles=False` (uploads cannot re-populate a file input). They matter even more on a server that re-renders full inputs.
- The rule "unmount = excluded from submission, unless inside a preserve boundary" gives a clear, explicit semantics for conditional fields. A server library can make this a per-field or per-section policy: `on_hide = "drop" | "keep"`.

### Gaps
- conform.guide was not fetched directly. Findings come from the docs sources in the GitHub repo, which the site renders. I found no published v2 release date or final v2 API. The future API is still marked experimental as of 1.21.1.

---

## Q2. Superforms (SvelteKit): server-validated form object, tainted tracking, JSON posting, adapters

### Takeaway
Superforms treats the form as a **server-produced object** (`SuperValidated`): `{id, valid, posted, data, errors, constraints, message}`. It is built by `superValidate(request | data | null, adapter(schema))` in both `load` and actions, then hydrated into client stores. It derives defaults and HTML constraints from the schema, controls when errors appear on initial load, tracks "tainted" (dirty) fields to guard navigation, and supports nested data with `dataType: 'json'`, which posts the serialized model instead of the inputs. Its validator adapter layer covers more than 10 schema libraries.

### Cited Findings
- Server API: `superValidate(data: RequestEvent | Request | FormData | URL | URLSearchParams | Partial<In> | null, adapter, options)` returns `SuperValidated<T,M,In> = { id; valid; posted; data: T; errors: Nested<T, string[]|undefined>; constraints?: Nested<T, InputConstraints|undefined>; message?: M }`. Options include `errors`, `id`, `preprocessed`, `defaults`, `jsonSchema`, `strict` ("validate exactly the posted data, no defaults added"), `allowFiles` and `transport` — [Superforms API](https://superforms.rocks/api)
- Initial errors: "If no data was posted or sent to `superValidate`, **no errors will be returned** unless the `errors` option… is `true`". If data *was* sent, errors are returned unless `errors: false`. "The `errors` option does not affect the `valid` property" — [Error handling](https://superforms.rocks/concepts/error-handling)
- Server-side errors after validation:
```ts
const form = await superValidate(request, zod(schema));
if (!form.valid) return fail(400, { form });
if (db.users.find({ where: { email: form.data.email } })) {
  return setError(form, 'email', 'E-mail already exists.');   // returns fail(400, {form})
}
// nested: setError(form, `post.tags[${i}].name`, 'Invalid tag name.');
```
"Errors added with `setError` will be removed when client-side validation is used, and the first client validation occurs." — [Error handling](https://superforms.rocks/concepts/error-handling)
- Recommendation: return a status **message** rather than throwing, because "this will make even the non-JS users keep their form data" — [Error handling](https://superforms.rocks/concepts/error-handling)
- Error focus: `errorSelector = '[aria-invalid="true"],[data-invalid]'`, `scrollToError`, `autoFocusOnError: boolean | 'detect'`, `stickyNavbar`, and `customValidity` (use the browser's native tooltip bubbles) — [Error handling](https://superforms.rocks/concepts/error-handling)
- Schema-derived defaults when data is empty: string `""`, number `0`, boolean `false`, Array `[]`, object `{}`. Nullable wins over optional. Unions need an explicit default. An enum defaults to its first value — [Default values](https://superforms.rocks/default-values)
- Constraints are spread onto inputs as native attributes (`required`, `pattern`, `step`, `minlength`, `maxlength`, `min`, `max`):
```svelte
<input name="email" type="email" bind:value={$form.email} {...$constraints.email} />
```
— [Client-side validation](https://superforms.rocks/concepts/client-validation)
- Client validation: `validators: ClientValidationAdapter | 'clear' | false`. `'clear'` removes a field's error as soon as the field is modified. `validationMethod: 'auto' | 'oninput' | 'onblur' | 'onsubmit'`. The default `'auto'` follows "reward early, validate late": "If entering data in a field that has or previously had errors, validate on `input`. Otherwise, validate on `blur`." The whole schema is re-validated on each change because refinements can add errors to any path. Validators can be swapped at runtime for multi-step forms (`options.validators = valibot(schema)`) — [Client-side validation](https://superforms.rocks/concepts/client-validation)
- Nested data: `dataType: 'json'` posts the entire `$form` (serialized with devalue) instead of the inputs, so "they are now simply UI components for modifying a data model". This requires JS plus `use:enhance`, and `disabled` no longer excludes fields. `$errors` and `$constraints` mirror the data shape. Array-level errors live under `_errors` (e.g. `$errors.tags._errors`) — [Nested data](https://superforms.rocks/concepts/nested-data)
- Without JSON mode, arrays of primitives still work by repeating the same input name, but only at the top level of the schema — [Nested data](https://superforms.rocks/concepts/nested-data)
- Tainted (= dirty): `taintedMessage` blocks navigation away from a tainted form. `isTainted()` and `isTainted('name')`. Programmatic updates can opt out with `form.update(fn, { taint: false | 'untaint' | 'untaint-form' })`. The form is untainted automatically after a valid result. The docs note that password managers can taint login forms — [Tainted fields](https://superforms.rocks/concepts/tainted)
- Proxies (`intProxy`, `dateProxy`, `arrayProxy`, `fieldProxy`, `formFieldProxy` returning `{path, value, errors, constraints, tainted}`) convert between string input values and typed model values. Nested proxy paths such as `'user.profile.email'` create missing parents — [Proxy objects](https://superforms.rocks/concepts/proxy-objects); [API](https://superforms.rocks/api)
- Adapters exist for many libraries. The docs mention Zod (and zod4), Valibot, ArkType, Yup, Joi, TypeBox, VineJS, Effect, Superstruct, class-validator, JSON Schema and schemasafe. `jsonSchema` is an option to "Override JSON schema from the adapter", which implies adapters produce a JSON Schema used for defaults and constraints — [get-started pages source](https://github.com/ciscoheat/superforms-web/tree/main/src/routes/get-started); [API](https://superforms.rocks/api)

### Inferences
- `SuperValidated` is a good template for a pyview `FormState` dataclass: `{id, valid, posted, data, errors (mirrored tree), constraints (mirrored tree), message}`. The "no errors unless posted" rule solves the empty-form-on-mount problem cleanly.
- Superforms normalizes each schema library to JSON Schema to get defaults and constraints. In Python, pydantic's `model_json_schema()` could fill the same role. msgspec, dataclasses and attrs would need a converter layer (see Q7).
- `_errors` for container-level (array or object) errors next to per-item errors is a simple convention worth adopting: e.g. `errors["tags"]["_errors"]` versus `errors["tags"][0]`.
- `dataType:'json'` shows that once state lives in a model rather than in DOM inputs, input names become optional. Pyview is already in that model. It can still emit `name` attributes for autofill and for a no-JS POST fallback.

### Gaps
- I did not check the exact list of Superforms adapters against the current package exports; the list above comes from word counts in the get-started docs. I found no statement on how Superforms converts non-JSON-Schema libraries (e.g. Joi) for defaults.

---

## Q3. TanStack Form: headless, typed field API, arrays, validator timing matrix, listeners, composition

### Takeaway
TanStack Form is a controlled, framework-agnostic store with a very explicit **validator timing matrix**: `onMount`, `onChange`, `onBlur`, `onSubmit`, each with an async version and debouncing, at field or form level. Errors are kept per trigger in an `errorMap`. It adds `revalidateLogic` (mode before and after the first submit), `listeners` for side effects (e.g. reset `province` when `country` changes), `onChangeListenTo` for linked fields, and form-level validators that can set nested field errors by path string. It supports Standard Schema natively, and `createFormHook` handles design-system composition.

### Cited Findings
- Field meta: `isTouched` ("true once the user changes or blurs the field"), `isDirty` (persistent: stays true even if the value goes back to the default), `isPristine`, `isBlurred`, `isDefaultValue`. "We have chosen the persistent 'dirty' state model… `const nonPersistentIsDirty = !isDefaultValue`". The docs compare this with RHF, Formik and Final Form (non-persistent) and with Angular and FormKit (persistent) — [Basic concepts](https://tanstack.com/form/latest/docs/framework/react/guides/basic-concepts)
- Arrays:
```tsx
<form.Field name="people" mode="array">
  {(field) => (<div>
    {field.state.value.map((_, i) => (
      <form.Field key={i} name={`people[${i}].name`}>
        {(sub) => <input value={sub.state.value} onChange={(e) => sub.handleChange(e.target.value)} />}
      </form.Field>))}
    <button type="button" onClick={() => field.pushValue({ name: '', age: 0 })}>Add person</button>
  </div>)}
</form.Field>
```
— [Arrays](https://tanstack.com/form/latest/docs/framework/react/guides/arrays). `FieldApi` also has `insertValue`, `removeValue(index)`, `moveValue` and `swapValues` — [FieldApi reference](https://tanstack.com/form/latest/docs/reference/classes/FieldApi)
- Per-trigger validators on a field: `validators={{ onChange: ({value}) => value < 13 ? 'You must be 13…' : undefined, onBlur: … }}`. `field.state.meta.errors` holds all current errors, and `field.state.meta.errorMap['onChange']` gives the errors by trigger. The error type matches what the validator returns (objects are allowed, not only strings) — [Validation](https://tanstack.com/form/latest/docs/framework/react/guides/validation)
- Form-level validators can set field errors by path:
```ts
validators: { onSubmitAsync: async ({ value }) => {
  const hasErrors = await verifyDataOnServer(value)
  return hasErrors ? { form: 'Invalid data', fields: {
    age: 'Must be 13 or older to sign', 'socials[0].url': 'The provided URL does not exist',
    'details.email': 'An email is required' } } : null } }
```
— [Validation](https://tanstack.com/form/latest/docs/framework/react/guides/validation)
- Async debouncing: `onChangeAsyncDebounceMs: 500`. Standard Schema libraries (Zod, Valibot, ArkType, Effect/Schema) can be passed directly as validators. With a Standard Schema, the form-level `errorMap.onChange` is `Record<string, StandardSchemaV1Issue[]>` keyed by field name — [Validation](https://tanstack.com/form/latest/docs/framework/react/guides/validation)
- Dynamic or revalidation logic: `validationLogic: revalidateLogic({ mode: 'change'|'blur'|'submit' (default submit), modeAfterSubmission: 'change' (default)|'blur'|'submit' })` together with the `onDynamic` validator — [Dynamic validation](https://tanstack.com/form/latest/docs/framework/react/guides/dynamic-validation)
- Listeners, used for side effects rather than validation: `listeners={{ onChange: ({value}) => form.setFieldValue('province', '') }}`. Available events are `onChange`, `onBlur`, `onMount`, `onSubmit` and `onUnmount`, with `onChangeDebounceMs` and `onBlurDebounceMs` — [Listeners](https://tanstack.com/form/latest/docs/framework/react/guides/listeners)
- Linked fields: `validators={{ onChangeListenTo: ['password'], onChange: … }}` on `confirm_password` re-runs its validation when `password` changes — [Linked fields](https://tanstack.com/form/latest/docs/framework/react/guides/linked-fields)
- SSR and server validation: `createServerValidate({...formOpts, onServerValidate})` throws `ServerValidateError` carrying `formState`. On the client, `useTransform(base => mergeForm(base, state))` merges the server state into the form. Adapters exist for TanStack Start, Next.js (`useActionState(someAction, initialFormState)`) and Remix — [SSR guide](https://tanstack.com/form/latest/docs/framework/react/guides/ssr)
- Composition: "A common criticism of TanStack Form is that it is verbose out-of-the-box". `createFormHook({ fieldContext, formContext, fieldComponents: { TextField }, formComponents })` produces `useAppForm`, and `form.AppField` renders pre-bound components that read `useFieldContext<string>()` — [Form composition](https://tanstack.com/form/latest/docs/framework/react/guides/form-composition)
- Philosophy: "Controlled is Cool" (firmly in the controlled camp), "Generics are grim" (infer everything from runtime defaults), and "Libraries are liberating" (wrap it in your own design system) — [Philosophy](https://tanstack.com/form/latest/docs/philosophy)

### Inferences
- A server-side form library can adopt TanStack's **per-trigger error map** (`errors_by_trigger = {"change": ..., "blur": ..., "submit": ..., "server": ...}`). Pyview receives distinct `phx-change`, `phx-blur` and `phx-submit` events, so errors can be kept and cleared per source. For example, clear "server" errors on the next change, as React Aria and Superforms also do.
- `listeners` and `onChangeListenTo` are declarative cross-field dependencies. A Python library could express them as `Field(depends_on=["password"])` for revalidation, and `@form.on_change("country")` for side effects that reset dependent fields.
- `revalidateLogic(mode, modeAfterSubmission)` is a clean two-phase timing policy that could be a single form-level setting.
- The persistent-versus-non-persistent "dirty" choice should be made explicitly. Offering both (`dirty` = ever changed, `is_default` = equals initial) avoids confusion.

### Gaps
- I did not verify the exact `FieldApi` method signatures beyond the headings in the reference. I also did not check whether form-level Standard Schema errors map onto nested array paths in exactly the same way as field-name strings.

---

## Q4. React Hook Form: uncontrolled inputs, resolvers, field arrays, mode/reValidateMode, shouldUnregister

### Takeaway
React Hook Form (RHF) is still the most widely used React form library. Its main ideas are separate **before-submit and after-submit validation modes**, including `onTouched`, which approximates "reward early, punish late"; pluggable **resolvers** for any schema library; **field arrays keyed by generated ids**; and `shouldUnregister`, which decides whether an unmounted (conditionally hidden) field keeps its value. Newer releases add server-oriented props: `errors` (server errors), `values` (external data), `progressive` (emit native constraint attributes) and a form-level `validate`.

### Cited Findings
- `mode: onChange | onBlur | onSubmit | onTouched | all` (default `onSubmit`) sets the validation strategy **before** submission. `onTouched`: "Validation is initially triggered on the first `blur` event. After that, it is triggered on every `change` event." `reValidateMode: onChange | onBlur | onSubmit` (default `onChange`) sets when fields with errors are re-validated **after** submission. Since 7.56.0 both are reactive — [useForm](https://react-hook-form.com/docs/useform)
- Server integration props: `errors` ("Server returns errors to update form", since 7.49.0), `values` (reactive external values, since 7.41.0) with `resetOptions: { keepDirtyValues: true, keepErrors: true }` to keep user edits when server data arrives — [useForm](https://react-hook-form.com/docs/useform)
- `shouldUnregister` (default `false`): "By default, an input value will be retained when an input is removed." With `false`, "unmounted fields are **not validated** by built-in validation." With `true`, "Unmounting an input removes its value… Only registered inputs are included as submission data", and the form "behave[s] more closely to native forms" — [useForm](https://react-hook-form.com/docs/useform)
- `progressive: true` (since 7.44.0) forwards validation rules as native attributes, e.g. for SSR or validation before hydration. `shouldUseNativeValidation` drives `setCustomValidity`/`reportValidity`. `criteriaMode: firstError | all`. `shouldFocusError` defaults to true. A form-level `validate({formValues, formState, eventType, name})` was added in 7.72.0 and cannot be combined with `resolver` — [useForm](https://react-hook-form.com/docs/useform)
- Resolvers (`@hookform/resolvers`) cover Yup, Zod, Joi, Ajv, Vest and custom functions: `useForm({ resolver: zodResolver(schema) })` — [useForm](https://react-hook-form.com/docs/useform). shadcn's RHF guide notes you can "replace it with any other Standard Schema validation library supported by React Hook Form" — [shadcn RHF guide](https://github.com/shadcn-ui/ui/blob/main/apps/v4/content/docs/forms/react-hook-form.mdx)
- `useFieldArray` returns `fields` (each with a generated `id`) plus `append`, `prepend`, `insert`, `swap`, `move`, `update`, `replace` and `remove`. Rule: "The `field.id` (and not `index`) must be added as the component key". Array-level `rules` put errors at `errors.<name>.root`. Appended data "is required and cannot be partial" — [useFieldArray](https://react-hook-form.com/docs/usefieldarray)
- `formState`: `isDirty` and `dirtyFields` (compared with `defaultValues`, so "make sure to provide all inputs' `defaultValues`"), `touchedFields`, `isSubmitted` (true until reset), `isValid`, `errors` — [formState](https://react-hook-form.com/docs/useform/formstate)

### Inferences
- The two-phase `mode`/`reValidateMode` design (together with TanStack's `revalidateLogic` and Conform's `shouldValidate`/`shouldRevalidate`) is the de facto consensus API shape for timing. Pyview could offer `validate_on="blur"` and `revalidate_on="change"`.
- `shouldUnregister` shows that conditional-field semantics need an explicit switch. The default `false` (keep values, skip validation) suits wizards, while `true` suits "hidden means not submitted". A server-side library should make this a per-field or per-section policy rather than a hidden global.
- The generated-id-per-array-row rule is required in any system that re-renders lists. It is the same idea as Conform's `listKeys`.
- `root` for array-level errors is RHF's version of Superforms' `_errors`.

### Gaps
- I found no official RHF v8 timeline in the docs I read. The docs contain v8 hints only indirectly (e.g. deprecations).

---

## Q5. Historical and other libraries: Formik, Final Form, Felte, VeeValidate, Modular Forms / Formisch, Formily

### Takeaway
Formik established the `values / errors / touched` triple and the rule "show an error only if touched" (with submit touching all fields). Final Form added a richer per-field meta model (`active`, `visited`, `touched`, `modified`, `dirtySinceLastSubmit`, and a separate `submitError`) plus opt-in subscriptions. These models still underlie most libraries. Formik and Felte are low-activity. Modular Forms is in maintenance and has been replaced by Formisch, a schema-first (Valibot) library. Formily's JSON-Schema `x-*` extensions separate "hidden in UI, data kept" from "not visible, data removed".

### Cited Findings
- Formik display pattern: `{errors.email && touched.email && <div>{errors.email}</div>}`. Field-level `validate` runs "after any `onChange` and `onBlur` by default", which can be changed with `validateOnChange`/`validateOnBlur`. "In addition to change/blur, all field-level validations are run at the beginning of a submission attempt and then the results are deeply merged with any top-level validation results." — [Formik validation guide](https://github.com/jaredpalmer/formik/blob/main/docs/guides/validation.md)
- Formik submit phases: "Pre-submit: Touch all fields… Set `isSubmitting` to `true`, increment `submitCount`". Then validation: run all validations, abort on errors. Then submission — [Formik form submission](https://github.com/jaredpalmer/formik/blob/main/docs/guides/form-submission.md)
- Formik status: latest 2.4.9 (Nov 2025), with a long-running `3.0.0-next.8` tag — [npm formik](https://www.npmjs.com/package/formik). (Inference: in maintenance mode rather than actively evolving.)
- Final Form field state: `active` ("currently has focus"), `visited` ("has ever gained focus"), `touched` ("has ever gained and lost focus"), `modified` ("value has ever been changed"), `dirty`, `dirtySinceLastSubmit`, `modifiedSinceLastSubmit`, `pristine`, `error`, **`submitError`** ("The submission error for this field"), `submitFailed`, `submitSucceeded`, `submitting`, `valid`, `invalid`, `validating`, `initial`, `value`, `length`, `data` — [Final Form FieldState](https://github.com/final-form/final-form/blob/main/docs/types/FieldState.md). "Opt-in subscriptions - only update on the state you need!" — [Final Form README](https://github.com/final-form/final-form/blob/main/README.md)
- Modular Forms is in maintenance mode, and Formisch is its official successor by the same author (Fabian Hiller, author of Valibot). Formisch is "schema-based, headless", type-safe, modular, and targets React, Solid, Vue, Svelte, Qwik and Preact from a framework-agnostic core. The v1 RC was announced on formisch.dev — [Formisch v1 RC blog](https://formisch.dev/blog/formisch-v1-release-candidate/); [Migrate from Modular Forms](https://formisch.dev/solid/guides/migrate-from-modular-forms/); [Fabian Hiller on X](https://x.com/FabianHiller/status/1944961165513089327). (The maintenance-mode wording comes from a search-result summary of those pages, not a full read.) React Aria's forms guide lists Formisch next to RHF and Formik as supported form libraries — [React Aria forms guide](https://github.com/adobe/react-spectrum/blob/main/packages/dev/s2-docs/pages/react-aria/forms.mdx). shadcn/ui has a Formisch forms guide — [shadcn forms docs dir](https://github.com/shadcn-ui/ui/tree/main/apps/v4/content/docs/forms)
- Formily schema extensions: `x-visible` ("Field display hidden"), `x-hidden` ("Field UI hidden (data retention)"), `x-disabled`, `x-editable`, `x-read-only`, `x-read-pretty`, and `x-reactions` ("Field linkage agreement"), e.g.
```json
"x-reactions": { "target": "target", "when": "{{$self.value === '123'}}",
  "fulfill": { "state": { "visible": false } }, "otherwise": { "state": { "visible": true } } }
```
— [Formily Schema API](https://github.com/alibaba/formily/blob/formily_next/packages/react/docs/api/shared/Schema.md)
- Felte's last core release was 1.4.4 (Oct 2024) — [npm @felte/core](https://www.npmjs.com/package/@felte/core). VeeValidate (Vue) is at 4.15.1 (Jun 2025) — [npm vee-validate](https://www.npmjs.com/package/vee-validate)

### Inferences
- Final Form's distinction between `visited`, `touched` and `modified`, together with `submitError` being separate from `error`, is the most complete meta model. A pyview state model could track `focused`/`visited` (if focus events are sent), `touched` (blurred), `modified` (changed), `dirty` (≠ initial), `submitted_count`, and keep `client_errors`, `server_errors` and `submit_errors` separate.
- Formily's `x-visible` versus `x-hidden` is the same distinction as RHF `shouldUnregister` and Conform `PreserveBoundary`, expressed declaratively in the schema. A Python schema could carry `json_schema_extra={"x-visible": ...}` or a dedicated `ui` metadata field.
- Formik's rule that submit touches all fields is still the standard rule for revealing every error on submit.

### Gaps
- I did not read VeeValidate or Felte docs in depth, so their specific ideas (e.g. VeeValidate's `useField`/`useFieldArray` and Felte's action-based DOM binding) are not documented here. I did not directly confirm Formik's maintenance status in an official statement; it is inferred from release cadence only. The Formily docs were read only for the Schema table; its reactive core model (`@formily/reactive`) was not studied.

---

## Q6. Schema-driven auto-generated forms: RJSF, JSON Forms, uniforms, AutoForm (and shadcn auto-form)

### Takeaway
Every auto-form system splits into (1) a data schema (**what**), (2) a UI schema or field config (**how**), and (3) a **renderer registry** chosen by type, widget name or a ranked tester function. The strongest designs are JSON Forms (a separate UI schema with layouts plus `rule` objects whose conditions are themselves JSON Schema; renderer sets chosen by ranked "testers") and uniforms (an abstract `Bridge` interface that adapts any schema system to a common field API). RJSF is the most complete JSON-Schema implementation but has known weak spots: `oneOf`/`anyOf`/`allOf` overlap, heavy JSON configuration for layout, and cross-field logic JSON Schema cannot express. AutoForm positions itself as a tool for "internal tools and simple forms" with escape hatches, which is the right scope for auto-generation.

### Cited Findings

**RJSF (react-jsonschema-form, v6.11.0)**
- "JSON Schema is limited for describing how a given data type should be rendered as a form input component. That's why this library introduces the concept of uiSchema… the uiSchema… defines how each property should be rendered", following the same tree structure. `{"ui:widget": ...}` and `{"ui:options": {widget: ...}}` are equivalent — [uiSchema](https://rjsf-team.github.io/react-jsonschema-form/docs/api-reference/uiSchema)
- uiSchema keys include `ui:widget`, `ui:field`, `ui:options`, `classNames`, `autofocus`, `description`, `disabled`, `emptyValue`, `enumDisabled`, `enumNames`, `enumOrder`, `help`, `hideError`, `inputType`, `label`, `order`, `placeholder`, `readonly`, `rows`, `title`, `submitButtonOptions`, `ui:globalOptions` and `ui:definitions` — [uiSchema](https://rjsf-team.github.io/react-jsonschema-form/docs/api-reference/uiSchema)
- Dynamic uiSchema: `items` can be a function `(itemData, index, formContext) => UiSchema` that changes widgets and help text per array item (e.g. show `guardianName` when `relationship === 'child'`) — [Dynamic uiSchema examples](https://rjsf-team.github.io/react-jsonschema-form/docs/api-reference/dynamic-ui-schema-examples)
- Conditionals: `dependencies` (from an older JSON Schema draft, "not part of the latest JSON Schema spec"). Property dependencies (`credit_card: ['billing_address']`) make fields required. Schema dependencies add properties, and `oneOf` inside dependencies enables dynamic subforms — [Dependencies](https://rjsf-team.github.io/react-jsonschema-form/docs/json-schema/dependencies)
- Limits: "properties declared inside the `anyOf/oneOf` should not overlap with properties 'outside' of the `anyOf/oneOf`". `allOf` is merged with a merge library and is "dropped" if the subschemas are incompatible. `additionalItems: true` is unsupported ("no widget to represent an item of any type") — [Internals](https://rjsf-team.github.io/react-jsonschema-form/docs/advanced-customization/internals)
- Customization layers: *widgets* ("a HTML tag for the user to enter data") versus *fields* ("wraps one or more widgets… think of a field as a form row, including the labels"), overridden via the `widgets` and `fields` props — [Custom widgets and fields](https://rjsf-team.github.io/react-jsonschema-form/docs/advanced-customization/custom-widgets-fields). Templates: `FieldTemplate`, `ObjectFieldTemplate`, `ArrayFieldTemplate`, `ArrayFieldItemTemplate`, `BaseInputTemplate`, `FieldErrorTemplate`, `FieldHelpTemplate`, `ErrorListTemplate`, `DescriptionFieldTemplate`, `TitleFieldTemplate`, `MultiSchemaFieldTemplate`, `WrapIfAdditionalTemplate`, and buttons (`AddButton`, `RemoveButton`, `MoveUp`/`MoveDown`, `SubmitButton`) — [Custom templates](https://rjsf-team.github.io/react-jsonschema-form/docs/advanced-customization/custom-templates)
- Validation props: `liveValidate` (`onChange` or `onBlur`; boolean deprecated), `omitExtraData` + `liveOmit` (strip data that no field renders, i.e. data from hidden conditional branches), `customValidate`, `transformErrors`, and `extraErrors` (server or async errors; non-blocking unless `extraErrorsBlockSubmit`) — [Form props](https://rjsf-team.github.io/react-jsonschema-form/docs/api-reference/form-props)
- Criticisms, from secondary and older sources: Talend's UIForm wiki cites trouble placing arbitrary content (banners, info text) inside schema-driven forms, and validations JSON Schema cannot express (e.g. "a number is larger than another number") — [Talend UIForm V3 wiki](https://github.com/Talend/ui/wiki/UIForm-V3). The JSON Schema org set up a "form vocabulary" special interest group because UI concerns do not fit JSON Schema — [json-schema-org discussion #70](https://github.com/json-schema-org/community/discussions/70). (Both are summarized from search results, not fully read.)

**JSON Forms (EclipseSource, v3.8.0)**
- Architecture: a UI-agnostic `@jsonforms/core` with React, Angular and Vue bindings, and interchangeable **renderer sets** (material, vanilla HTML5, Angular Material, Vue vanilla, Vuetify) — [Architecture](https://jsonforms.io/docs/architecture)
- The UI schema is separate from the data schema and made of `Control` elements (`scope: "#/properties/name"`) and layouts (`VerticalLayout`, `HorizontalLayout`, `Group`, `Categorization`/`Category`) — [Layouts](https://jsonforms.io/docs/uischema/layouts)
- Rules: `"rule": { "effect": "HIDE"|"SHOW"|"ENABLE"|"DISABLE", "condition": { "scope": "#/properties/counter", "schema": { "const": 10 } } }`. The condition is **any JSON Schema** validated against the scoped data, so `enum`, `not`, `minimum`/`exclusiveMaximum` all work. Undefined scope data matches unless `failWhenUndefined: true` — [Rules](https://jsonforms.io/docs/uischema/rules)
- Renderer selection by ranked testers: each renderer is registered with a tester `(uischema, schema) → number`, where `-1` means not applicable. `rankWith(3, scopeEndsWith('rating'))` beats the default set's rank of 2. Testers compose with `and`/`or` — [Custom renderers](https://jsonforms.io/docs/tutorial/custom-renderers)
- Validation modes: `ValidateAndShow` (default), `ValidateAndHide` (validate but hide errors), `NoValidation`. `additionalErrors` injects backend errors as AJV `ErrorObject`s keyed by `instancePath` — [Validation](https://jsonforms.io/docs/validation)

**uniforms (v4)**
- "To make use of any schema, uniforms have to create a _bridge_ of it - a unified schema mapper." Current bridges: `JSONSchemaBridge`, `SimpleSchema2Bridge`, `ZodBridge`. Deprecated: SimpleSchema (v1) and GraphQL. The JSON Schema bridge's `allOf`/`anyOf`/`oneOf` handling "is not complete" (properties are merged, last wins; `required` is accumulated; the first `type` is used) — [uniforms Bridges](https://github.com/vazco/uniforms/blob/master/website/versioned_docs/version-4.0/api-reference/bridges.mdx)
- Abstract `Bridge` methods: `getField(name)`, `getSubfields(name?)`, `getType(name)` ("`AutoField` component will work correctly only with standard JavaScript constructors, like `String` or `Number`"), `getInitialValue(name)`, `getInitialModel()`, `getProps(name)`, `getError(name, error)`, `getErrorMessage(name, error)`, `getErrorMessages(error)`, and `getValidator(options)` (returns a function model → error | null) — [Bridge.ts](https://github.com/vazco/uniforms/blob/master/packages/uniforms/src/Bridge.ts)

**AutoForm (vantezzen, @autoform/* v4) and the shadcn origin**
- AutoForm takes a schema provider (`new ZodProvider(userSchema)`) and renders a form through a UI-library package (`@autoform/mui/react-hook-form`, shadcn, Mantine, AntD, Chakra), on top of RHF or TanStack Form. "AutoForm is mostly meant as a drop-in form builder for your internal tools and simple forms… does not aim to be a full-featured form builder or support every edge case." Customization is through `fieldConfig` and by replacing the renderer. It "evolved from a shadcn/ui component into a standalone library" — [AutoForm README](https://github.com/vantezzen/autoform)

### Inferences
- uniforms' `Bridge` is the best Python analogue for "any schema library": a `SchemaBridge` protocol with `fields()`, `subfields(path)`, `field_type(path)`, `initial_value(path)`, `props(path)` (label, required, constraints, choices), `validate(data) → issues` and `error_for(path, issues)`. Pydantic, dataclasses, attrs and msgspec would each implement it.
- JSON Forms' rule conditions ("condition = a schema applied to the scoped value") give a declarative, serializable, server-evaluable way to express show/hide/enable/disable that fits pyview. The server can evaluate rules on every `phx-change` and re-render.
- Ranked-tester renderer selection works better than a fixed type→widget map. Users can override a single field (e.g. every `*_rating` path) without forking the theme.
- RJSF's `omitExtraData`/`liveOmit` is another answer to what happens to data in hidden branches (strip anything that no rendered field owns). Together with RHF, Formily and Conform, this shows every mature library had to give conditional-field data an explicit policy.
- The shared criticism (layout, arbitrary content, cross-field logic) suggests a pyview library should make auto-generation an **opt-in convenience layer on top of a hand-composable field API**, as AutoForm and TanStack/shadcn do, and not the only way to build forms.

### Gaps
- I could not reach uniforms.tools, ui.shadcn.com or smashingmagazine.com (egress blocked) and used their GitHub doc sources instead. I did not verify the `fieldConfig` API details of AutoForm v4, or whether the original vantezzen/auto-form shadcn component is officially archived. I did not document Formily's full reactive linkage semantics (`x-reactions` dependencies/`$deps`).

---

## Q7. Standard Schema (standardschema.dev): a shared validation interface, and a model for Python adapters

### Takeaway
Standard Schema is a tiny, dependency-free interface (`~standard.validate(value) → {value} | {issues:[{message, path}]}`) created by the authors of Zod, Valibot and ArkType. It has become the way form libraries accept "any schema": TanStack Form, Conform future `useForm(schema)`, RHF resolvers and Formisch all use or support it. A companion spec, **Standard JSON Schema**, adds `~standard.jsonSchema.input/output({target})` for tools such as form generators that need introspection rather than just validation. This two-part split (validate versus introspect) is the right model for Python adapters.

### Cited Findings
- Interface (abridged):
```ts
interface StandardSchemaV1<Input = unknown, Output = Input> {
  readonly "~standard": {
    readonly version: 1; readonly vendor: string;
    readonly validate: (value: unknown, options?: { libraryOptions?: Record<string, unknown> })
      => Result<Output> | Promise<Result<Output>>;
    readonly types?: { input: Input; output: Output };
  };
}
type Result<O> = { value: O; issues?: undefined } | { issues: ReadonlyArray<Issue> };
interface Issue { message: string; path?: ReadonlyArray<PropertyKey | { key: PropertyKey }> }
```
— [Standard Schema spec](https://github.com/standard-schema/standard-schema/blob/main/packages/spec/README.md)
- Design goals: "Minimal", "Avoid API conflicts" (everything sits under one `~standard` property), and "Do no harm to DX" (the tilde prefix keeps it low in autocompletion). The spec was "designed by the creators of Zod, Valibot, and ArkType" — [Standard Schema spec](https://github.com/standard-schema/standard-schema/blob/main/packages/spec/schema.md)
- Implementers: Zod 3.24.0+, Valibot v1.0+, ArkType v2.0+, Effect Schema v3.13.0+ (via adapter), Arri, Formgator and others. Integrators include tRPC, TanStack Form, TanStack Router, Hono and Elysia — [spec implementers list](https://github.com/standard-schema/standard-schema/blob/main/packages/spec/schema.md)
- Spec v1.0.0 released January 26, 2025 — [CHANGELOG](https://github.com/standard-schema/standard-schema/blob/main/packages/spec/CHANGELOG.md)
- Standard JSON Schema: `~standard.jsonSchema.input(options)` / `.output(options)` with `target: "draft-2020-12" | "draft-07" | "openapi-3.0" | string`. Motivation explicitly includes "Form generation tools" because "type information was commonly destroyed in the process of converting a schema… to JSON Schema" — [Standard JSON Schema](https://github.com/standard-schema/standard-schema/blob/main/packages/spec/json-schema.md)
- Conform's `report()` accepts `{ issues: StandardSchemaV1.Issue[] }` directly — [report](https://github.com/edmundhung/conform/blob/main/docs/api/react/future/report.md). TanStack Form types Standard Schema form errors as `Record<string, StandardSchemaV1Issue[]>` — [Validation](https://tanstack.com/form/latest/docs/framework/react/guides/validation)

### Inferences
- Python equivalent: define two small `Protocol`s. `FormValidator.validate(data) -> Success(value) | Failure(issues=[Issue(message, path: tuple[str|int,...])])` covers validation, and `FormIntrospector.json_schema(mode="input"|"output")` (or a richer field-tree API) covers rendering. Pydantic maps directly (`ValidationError.errors()` gives `loc` tuples and `model_json_schema(mode="validation"|"serialization")`). msgspec (`msgspec.json.schema`), dataclasses and attrs need adapters, e.g. via pydantic `TypeAdapter`.
- Input versus output types matter for forms. The form **input** schema (strings from HTML, optional or empty values) differs from the validated **output** type. Standard JSON Schema exposes both, and a pyview library should keep the same distinction; Conform's automatic coercion and Superforms' proxies both exist because of this gap.
- A path of `(key | {key})` segments converts easily to Conform, Superforms and TanStack name strings (`tasks[0].content`). A single canonical path↔name codec should be one core module.

### Gaps
- I found no Python-ecosystem equivalent of Standard Schema. Whether one exists would need a separate search, which was out of scope here.

---

## Q8. Headless and accessible field primitives: React Aria forms, shadcn `Field`, "copy the component" styling

### Takeaway
The accessibility contract is now standard: generated ids linking label, description and error; `aria-invalid` only when invalid; `aria-describedby` pointing to help text and the error; errors appear after the value is **committed** (blur) or on submit; server errors are passed in as a `name → messages` map and **cleared as soon as the user edits that field**. React Aria also separates **native** validation behavior (blocks submit, uses constraint validation) from **aria** behavior (only marks the field invalid, letting a form library decide). shadcn/ui's current forms guides build on a small set of copy-pasteable `Field` primitives (`Field`, `FieldLabel`, `FieldDescription`, `FieldError`, `FieldGroup`) driven by `data-invalid`/`aria-invalid`, whichever form library is used.

### Cited Findings
- React Aria validation: constraint validation (`isRequired`, `minValue`/`maxValue`, `minLength`/`maxLength`, `pattern`, `type="email"|"url"`) is "checked by the browser when the user commits changes to the value (e.g. on blur) or submits the form". `<FieldError>` shows the message, and a render function receives `validationDetails` (a `ValidityState`) for custom messages. Custom `validate` results "are displayed to the user after the value is committed (e.g. on blur) to avoid distracting them on each keystroke" — [React Aria forms guide](https://github.com/adobe/react-spectrum/blob/main/packages/dev/s2-docs/pages/react-aria/forms.mdx)
- Realtime validation is opt-in through a controlled `isInvalid` and `errorMessage` (e.g. password rules). "By default, invalid fields block forms from being submitted. To avoid this, use `validationBehavior="aria"`, which will only mark the field as required and invalid for assistive technologies, and will not prevent form submission." — [React Aria forms guide](https://github.com/adobe/react-spectrum/blob/main/packages/dev/s2-docs/pages/react-aria/forms.mdx)
- Server errors: `<Form validationErrors={errors}>` maps each field `name` to messages. They "are displayed as soon as the `validationErrors` prop is set, and cleared after the user modifies each field's value." The docs recommend localizing errors on the server ("to avoid large bundles") and show `useActionState` + `<Form action={formAction}>` — [React Aria forms guide](https://github.com/adobe/react-spectrum/blob/main/packages/dev/s2-docs/pages/react-aria/forms.mdx)
- For RHF integration, React Aria recommends `validationBehavior="aria"` with `isInvalid={invalid}` and `errorMessage={error?.message}` ("Let React Hook Form handle validation instead of the browser") — [React Aria forms guide](https://github.com/adobe/react-spectrum/blob/main/packages/dev/s2-docs/pages/react-aria/forms.mdx)
- Conform generates `id`, `errorId` and `descriptionId`, and recommends `aria-describedby={!valid ? `${errorId} ${descriptionId}` : descriptionId}` — [Conform accessibility](https://github.com/edmundhung/conform/blob/main/docs/accessibility.md)
- shadcn/ui forms docs have guides for React Hook Form, TanStack Form, Formisch and Next.js (server actions). Each uses the `<Field />` component, "which gives you **complete flexibility over the markup and styling**":
```tsx
<Field data-invalid={fieldState.invalid}>
  <FieldLabel htmlFor={field.name}>Bug Title</FieldLabel>
  <Input {...field} id={field.name} aria-invalid={fieldState.invalid} />
  <FieldDescription>Provide a concise title for your bug report.</FieldDescription>
  {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
</Field>
```
— [shadcn RHF guide](https://github.com/shadcn-ui/ui/blob/main/apps/v4/content/docs/forms/react-hook-form.mdx); [shadcn forms docs dir](https://github.com/shadcn-ui/ui/tree/main/apps/v4/content/docs/forms)
- The shadcn Next.js guide uses `useActionState`, server-side Zod validation, `defaultValue={formState.values.title}` for re-population, and `disabled={pending}` — [shadcn Next.js forms guide](https://github.com/shadcn-ui/ui/blob/main/apps/v4/content/docs/forms/next.mdx)
- Superforms' focus-on-error selector is `'[aria-invalid="true"],[data-invalid]'`, so ARIA attributes also serve as the library's hook for scrolling to and focusing the first error — [Superforms error handling](https://superforms.rocks/concepts/error-handling)

### Inferences
- For pyview, the "headless + copy the component" strategy means the core library should emit **field view-models** (`id`, `name`, `value`, `errors`, `error_id`, `description_id`, `aria_invalid`, `aria_describedby`, constraints, choices). Rendering should go through overridable templates or components that users can copy into their project (shadcn-style), rather than fixed widgets. The `data-invalid`/`aria-invalid` attributes make styling and focus behavior independent of the CSS framework.
- React Aria's native-versus-aria split maps to a server-driven choice. Either emit native constraint attributes (`required`, `minlength`, …) so the browser validates before the round-trip, or leave them off and let server validation drive all messages. Conform, Superforms (`$constraints`) and RHF (`progressive`) all emit constraints from the schema, so this should be an option.
- Clearing server errors for a field on its next edit is common to React Aria, Superforms (`setError` cleared on first client validation) and Superforms' `'clear'` validator mode. A server-side form can do this in its `phx-change` handler.

### Gaps
- I could not fetch ui.shadcn.com directly (egress blocked), so I could not confirm from the site whether the older `<Form>/<FormField>` (RHF-context) component is officially deprecated. Radix's own form primitive (`@radix-ui/react-form`) was not researched.

---

## Q9. Error display timing: the consensus

### Takeaway
There is a clear consensus. **Do not show errors on untouched or empty initial fields. Validate a field for the first time on blur ("punish late"). Once a field has shown an error, re-validate on every input so the error clears as soon as it is fixed ("reward early"). On submit, mark every field touched and show all errors.** Libraries encode this as two settings (initial trigger, revalidate trigger) or as an "auto" mode.

### Cited Findings
- Superforms' default `validationMethod: 'auto'` "is based on the 'reward early, validate late' pattern, a researched way of validating input data that makes for a high user satisfaction: If entering data in a field that has or previously had errors, validate on `input`. Otherwise, validate on `blur`." It cites Mihael Konjević's article — [Superforms client-side validation](https://superforms.rocks/concepts/client-validation); [original article (Medium/wdstack)](https://medium.com/wdstack/inline-validation-in-forms-designing-the-experience-123fb34088ce)
- Smashing Magazine's guide to live validation UX describes "reward early, punish late": validate immediately while the user corrects an erroneous field, and wait until the user leaves a field that was previously valid — [Smashing Magazine, 2022](https://www.smashingmagazine.com/2022/09/inline-validation-web-forms-ux/) (read via search summary; page fetch was blocked)
- RHF `mode: 'onTouched'`: "initially triggered on the first `blur` event. After that… on every `change` event", and `reValidateMode` defaults to `onChange` after submit — [RHF useForm](https://react-hook-form.com/docs/useform)
- TanStack `revalidateLogic({ mode: 'submit' (default), modeAfterSubmission: 'change' (default) })` — [TanStack dynamic validation](https://tanstack.com/form/latest/docs/framework/react/guides/dynamic-validation)
- Conform: `shouldValidate` (default `onSubmit`) plus `shouldRevalidate`, e.g. "validate on blur initially, but revalidate on every input after the first validation" — [Conform configureForms](https://github.com/edmundhung/conform/blob/main/docs/api/react/future/configureForms.md)
- React Aria shows errors "after the value is committed (e.g. on blur), or when the form is submitted. This avoids confusing the user with irrelevant errors while they are still entering a value." — [React Aria forms guide](https://github.com/adobe/react-spectrum/blob/main/packages/dev/s2-docs/pages/react-aria/forms.mdx)
- Formik: show `errors.x && touched.x`, and submit touches all fields — [Formik validation](https://github.com/jaredpalmer/formik/blob/main/docs/guides/validation.md); [Formik submission](https://github.com/jaredpalmer/formik/blob/main/docs/guides/form-submission.md)
- Superforms does not return errors for unposted forms unless `errors: true` — [Superforms error handling](https://superforms.rocks/concepts/error-handling)

### Inferences
- In a server-driven model, "touched" must be tracked on the server from events. `phx-blur` or focus-out marks a field as touched, and `phx-change` includes which input changed. Error **visibility** is then `touched or submitted` (per field), while validation can still run on every change. This is the Formik `errors && touched` rule applied on the server. (Phoenix LiveView 1.0's `used_input?/1` and `_unused_` parameters provide something similar natively. This comes from background knowledge, was not verified in this research, and belongs to the Phoenix-focused research.)
- The "reward early" half needs per-field memory of "has shown an error". Conform tracks this as `touchedFields`, and Superforms says "has or previously had errors".
- With a network round-trip per validation, debouncing (TanStack `onChangeAsyncDebounceMs`) and `phx-debounce="blur"` become important. Validation can run on change while only *revealing* errors per the timing policy.

### Gaps
- I could not fetch the original Luke Wroblewski / A List Apart 2009 inline-validation study or the Smashing article directly (egress blocked), so no quantitative UX figures are cited here.

---

## Q10. 2025–2026 trends: React 19 form actions, server actions, and the shift to server validation

### Takeaway
React 19 made the server round-trip a built-in part of forms (`<form action={fn}>`, `useActionState(reducer, initial, permalink)` returning `[state, dispatch, isPending]`, and automatic reset of uncontrolled fields on success). Form libraries have converged toward it: Conform (`report`/`lastResult`), TanStack Form (`createServerValidate` + `mergeForm`), RHF (`errors`/`values` props), React Aria (`validationErrors`) and shadcn's Next.js guide all treat **server validation results as the source of truth** that is merged into client state. Standard Schema lets the same schema object run on both sides. This validates pyview's direction, where the server state is the only state.

### Cited Findings
- `const [state, dispatchAction, isPending] = useActionState(reducerAction, initialState, permalink?)`. The reducer receives `(previousState, actionPayload)`. With `permalink`, "If `reducerAction` is a Server Function and the form is submitted before the JavaScript bundle loads, the browser will navigate to the specified permalink URL", which gives progressive enhancement. Calls are queued sequentially — [React useActionState](https://react.dev/reference/react/useActionState)
- `<form action={fn}>`: the function receives `FormData` and runs in a Transition. "After the `action` function succeeds, all uncontrolled field elements in the form are reset." — [React `<form>`](https://react.dev/reference/react-dom/components/form)
- TanStack Form's Next.js integration: `useActionState(someAction, initialFormState)` + `useTransform((baseForm) => mergeForm(baseForm, state))`, where the server throws `ServerValidateError` carrying `formState` — [TanStack SSR](https://tanstack.com/form/latest/docs/framework/react/guides/ssr)
- Conform supports "Native Server Actions support for Remix and Next.js" and shows `parseSubmission` inside a `'use server'` action — [Conform README](https://github.com/edmundhung/conform/blob/main/README.md); [parseSubmission](https://github.com/edmundhung/conform/blob/main/docs/api/react/future/parseSubmission.md)
- The shadcn Next.js guide uses "`useActionState` for managing form state and errors", "Server-side validation using Zod" and the Next.js `<Form />` "for navigation and progressive enhancement" — [shadcn Next.js forms guide](https://github.com/shadcn-ui/ui/blob/main/apps/v4/content/docs/forms/next.mdx)
- React Aria's server-validation example returns `{ values: Object.fromEntries(formData), errors }` from an action and re-populates inputs with `defaultValue={values?.username}` — [React Aria forms guide](https://github.com/adobe/react-spectrum/blob/main/packages/dev/s2-docs/pages/react-aria/forms.mdx)
- RHF added server-oriented props: `errors` (7.49), `values` (7.41) and `progressive` (7.44) — [RHF useForm](https://react-hook-form.com/docs/useform)
- Opinion piece arguing "schemas won" and that form libraries lag behind (unverified opinion, cited for sentiment only) — [DEV Community: "Schemas Won. Form Libraries Haven't Noticed Yet"](https://dev.to/oluwawunmiadesewa/schemas-won-form-libraries-havent-noticed-yet-2ek6)

### Inferences
- The JS ecosystem is now rebuilding what LiveView-style frameworks already have: the server returns `{values, errors}` and the client re-renders. The remaining client-side value in JS libraries is instant client validation and fine-grained re-renders. Pyview gets fine-grained updates from diffs, so its form library should focus on the **server state machine** (parse → intent → validate → touched and visibility → render model) and on accessible output markup.
- The common action result shape (`{values, errors, reset?}`, echoing submitted values minus secrets) is a good default contract for a pyview `FormResult`.

### Gaps
- I did not find adoption statistics for React 19 form actions versus client-side libraries.

---

## Q11. Cross-cutting synthesis: which "great ideas" transfer best to pyview (server-held state, Phoenix JS client)

### Takeaway
The most transferable ideas are (1) Conform's **intent protocol** for structural edits and its parse → resolve → validate → report pipeline; (2) a **canonical path↔name codec** (`a.b[0].c`); (3) a **server-held meta model** (touched, dirty/modified, submitted, and separate client, server and submit errors, as in Final Form, Conform and Superforms); (4) **two-phase timing** (`validate_on` / `revalidate_on`, "reward early, punish late"); (5) an explicit **conditional-field data policy** (drop versus keep when hidden: RHF `shouldUnregister`, Formily `x-visible`/`x-hidden`, Conform `PreserveBoundary`, RJSF `omitExtraData`); (6) a **schema bridge** plus a Standard-Schema-like issue format for pydantic, dataclasses, attrs and msgspec; (7) **field view-models with ARIA wiring** and an overridable renderer registry chosen by ranked testers (JSON Forms, uniforms, RJSF, shadcn).

### Cited Findings
- Intent strings on a reserved submit name, resolved on the server into a new target value; unknown intents return `undefined` (400) — [Conform resolveSubmission](https://github.com/edmundhung/conform/blob/main/docs/api/react/future/resolveSubmission.md); [intent.ts](https://github.com/edmundhung/conform/blob/main/packages/conform-react/future/intent.ts)
- Conform's form state stores `serverError` and `clientError` separately, plus `touchedFields` and `listKeys` — [Conform types.ts](https://github.com/edmundhung/conform/blob/main/packages/conform-react/future/types.ts). Final Form keeps `submitError` separate from `error` — [Final Form FieldState](https://github.com/final-form/final-form/blob/main/docs/types/FieldState.md)
- Two-phase timing in RHF (`mode`/`reValidateMode`), TanStack (`revalidateLogic`), Conform (`shouldValidate`/`shouldRevalidate`) and Superforms (`'auto'`) — sources in Q9.
- Conditional-field policies: RHF `shouldUnregister` — [RHF useForm](https://react-hook-form.com/docs/useform); Formily `x-hidden` "data retention" versus `x-visible` — [Formily Schema](https://github.com/alibaba/formily/blob/formily_next/packages/react/docs/api/shared/Schema.md); Conform `PreserveBoundary` "only for navigational conditions" — [PreserveBoundary](https://github.com/edmundhung/conform/blob/main/docs/api/react/future/PreserveBoundary.md); RJSF `omitExtraData`/`liveOmit` — [RJSF form props](https://rjsf-team.github.io/react-jsonschema-form/docs/api-reference/form-props)
- Declarative show/hide rules whose condition is a schema — [JSON Forms rules](https://jsonforms.io/docs/uischema/rules)
- Schema bridges — [uniforms Bridge.ts](https://github.com/vazco/uniforms/blob/master/packages/uniforms/src/Bridge.ts); Standard Schema and Standard JSON Schema — [spec](https://github.com/standard-schema/standard-schema/blob/main/packages/spec/README.md)
- Schema-derived HTML constraints and defaults — [Superforms client validation](https://superforms.rocks/concepts/client-validation); [Superforms default values](https://superforms.rocks/default-values); [Conform configureForms `getConstraints`](https://github.com/edmundhung/conform/blob/main/docs/api/react/future/configureForms.md)
- Array-level error slot: Superforms `_errors`, RHF `errors.<name>.root` — [Superforms nested data](https://superforms.rocks/concepts/nested-data); [RHF useFieldArray](https://react-hook-form.com/docs/usefieldarray)
- Never echo secrets and strip files in the result — [Conform report](https://github.com/edmundhung/conform/blob/main/docs/api/react/future/report.md)
- Custom intents with parse/resolve/touch/move hooks — [Conform defineIntent](https://github.com/edmundhung/conform/blob/main/docs/api/react/future/defineIntent.md)

### Inferences
Below is an illustrative Python sketch that combines these ideas. It is **not** from any source; it is a proposal for the report writer to evaluate.

```python
# 1) Schema bridge (uniforms-style) + Standard-Schema-like issues
class Issue(NamedTuple):
    message: str
    path: tuple[str | int, ...]          # ("tasks", 0, "content")

class SchemaBridge(Protocol):
    def fields(self, path: Path = ()) -> list[str]: ...            # getSubfields
    def field_info(self, path: Path) -> FieldInfo: ...              # type, label, required, choices, constraints, ui hints
    def initial_value(self, path: Path = ()) -> Any: ...            # getInitialValue/getInitialModel
    def validate(self, data: dict) -> Ok[T] | Err[list[Issue]]: ... # ~standard.validate
    def json_schema(self, mode: Literal["input", "output"]) -> dict: ...  # Standard JSON Schema analogue

# 2) Server-held state (Conform FormState + Final Form meta + Superforms SuperValidated)
@dataclass
class FormState(Generic[T]):
    id: str
    initial: dict                       # defaults (schema-derived, Superforms-style)
    value: dict                         # current raw (input-typed) values
    touched: set[str]                   # "tasks[0].content" (blurred or validated)
    modified: set[str]                  # ever changed (persistent dirty, TanStack)
    list_keys: dict[str, list[str]]     # stable ids per array path (Conform listKeys / RHF field.id)
    client_errors: dict[str, list[str]] # from schema validation
    server_errors: dict[str, list[str]] # from handler (setError); cleared on next edit of that field
    submit_count: int = 0
    # visible_errors(name) = errors if (name in touched or submit_count > 0) -> "reward early, punish late"

# 3) Intents: same wire format over phx-click/phx-submit and no-JS POST
#   <button name="__intent__" value='insert({"name":"tasks"})'>Add</button>
#   <button name="__intent__" value='remove({"name":"tasks","index":2})'>Remove</button>
#   <button name="__intent__" value='reorder({"name":"tasks","from":2,"to":0})'>Up</button>
#   parse -> resolve(intent, value) -> validate(target) -> FormState update -> re-render

# 4) Timing and conditional policy
Form(schema, validate_on="blur", revalidate_on="change",   # RHF/Conform/TanStack two-phase
     on_hidden="drop")                                      # vs "keep" (RHF shouldUnregister / Formily x-hidden)
```
- Suggested renderer architecture: `FieldViewModel` (id, name, value, errors, aria-*, constraints, choices, description_id, error_id) → a template registry keyed by ranked testers (`rank_with(3, path_endswith("rating"))`) → default templates users copy and override (shadcn model). Keep auto-generation (`AutoForm(schema)`) as a thin layer over this, following AutoForm's stated scope of "internal tools and simple forms".
- Conditional fields in a server-driven model are easier than on the client: the server re-evaluates visibility rules (JSON Forms-style `rule` with a condition schema, or Python predicates) on each change, and the `on_hidden` policy decides whether hidden values are kept in `value`, excluded from validation, and excluded from the final validated output.

### Gaps
- None of the findings above were tested against pyview's actual event payloads (`phx-change` target info, blur events, upload handling). That mapping should come from the pyview/Phoenix-focused research. Performance of full-schema re-validation on every change for large forms, which Superforms notes is necessary because refinements can target any path, was not measured.
