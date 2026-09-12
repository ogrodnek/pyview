# Conform (edmundhung/conform): progressively-enhanced, server-validated forms with nested objects, lists and intents — v1.21.1 (npm, 2026-08-18), repo HEAD 6b2831e (2026-09-11); researched 2026-09-12

Scope: the stable v1 API (`@conform-to/react`, `@conform-to/zod`, `@conform-to/dom`, all 1.21.1) plus the "future" export (`@conform-to/react/future`, `@conform-to/zod/v4/future`) that is the announced v2 direction (discussion #954). v1.0.0 shipped 2024-01-31 (year from memory of the release timeline; the release page shows only "Jan 31"). Everything below was read from the repo clone or verified by running the packed npm packages under Node 22.

## TL;DR (5-8 bullets)

- **The form element / `FormData` is the source of truth; the library owns only metadata.** Values are read back from the DOM via `new FormData(form)` on every `input` event and a `MutationObserver`; what Conform keeps is errors, a `validated` (v1) / `touchedFields` (future) set, list `key`s, constraints and the last submission. Unmounted inputs therefore contribute nothing (deliberate, discussion #455).
- **One name grammar ties everything together:** `object.property`, `array[index]`, trailing `tags[]`. `parsePath`/`formatPath` + `setPathValue` turn `FormData` into a nested payload; the *same* path strings key the error dict, the constraint dict, the key dict, the `fields` list and element `id`s. Form-level errors live under the empty key `''`.
- **Every non-submit interaction is an *intent*, sent as a normal form submission.** A hidden submit button named `__intent__` carries a JSON `{type, payload}` (v1) or `insert("tasks",{...})` string (future). `parse()`/`resolveSubmission()` apply `insert/remove/reorder/update/reset` to the payload *before* validation on both client and server, so list mutation works with JavaScript disabled and the server never needs a separate endpoint.
- **`parseWithZod(formData, {schema, async, error, formatError})` returns a `Submission`** with `status: 'success' | 'error' | undefined` (undefined = "this was an intent, not a submit"), `payload` (raw nested strings), `value` (typed) or `error` (`Record<path, string[] | null>`), and `reply({formErrors, fieldErrors, hideFields, resetForm})` which produces the JSON-serialisable `SubmissionResult` the client consumes as `lastResult`.
- **Coercion is schema-driven, not input-driven:** `coerceFormValue(schema)` rewrites the zod tree so `'' → undefined`, `'on' → true`, `Number()`, `new Date()`, `BigInt()`, single value → `[value]` for arrays, `undefined → {}` for objects (so required errors land on leaves). It is cached per schema and configurable via `configureCoercion({stripEmptyString, type:{number,boolean,date}, customize})`.
- **Validation timing is a two-phase policy:** `shouldValidate` (first time) and `shouldRevalidate` (after a field is validated), each `onSubmit | onBlur | onInput`, default `onSubmit`; the documented sweet spot is `onBlur` then `onInput`. Errors for fields that were never validated/touched are simply not shown, and `form.validate()` without a name marks everything touched (discussion #1109).
- **HTML constraints are derived from the schema:** `getZodConstraint(schema)` → `{required, minLength, maxLength, min, max, step, multiple, pattern, accept}` per path with `[]` wildcards for list items; `getInputProps(field, {type})` spreads `key/id/name/form/required/…/aria-invalid/aria-describedby/defaultValue|defaultChecked`.
- **Known friction:** the `key`-remount dance for `update`/`reset` with uncontrolled inputs, custom UI components needing a hidden native input (`useInputControl` / `useControl`), conditional fields losing values, API churn between v1 helpers and the future export (breaking changes in minor releases 1.19–1.21), and docs that lag.

## Mental model & core abstractions

Conform is three layers (packages/):

1. **`@conform-to/dom`** — framework-agnostic. `formdata.ts` (path grammar, `parseSubmission`, `report`, `isDirty`, `defaultSerialize`, `normalize`), `submission.ts` (v1 `parse`, `Submission`, `SubmissionResult`, intents, `serializeIntent`), `form.ts` (the client state machine `createFormContext`: meta → derived state proxies → subscribers), `dom.ts` (`requestIntent`, `updateField`, `isDirtyInput`, global forms observer).
2. **`@conform-to/react`** — `useForm`, `useField`, `useFormMetadata`, `FormProvider`, `FormStateInput`, `useInputControl`, and the prop helpers `getFormProps/getFieldsetProps/getInputProps/getSelectProps/getTextareaProps/getCollectionProps`. Metadata objects are lazy `Proxy`s that record which properties a component read, so `useSyncExternalStore` re-renders only subscribers whose slice changed (`context.tsx: getMetadata`, `updateSubjectRef`).
3. **Schema adapters** — `@conform-to/zod` (`/v3`, `/v4`, default), `@conform-to/yup`, `@conform-to/valibot`: `parseWith*`, `get*Constraint`, coercion, `formatResult`.

Submission lifecycle (docs/overview.md, packages/conform-dom/submission.ts):

```
<form id={form.id}> ──submit/intent──▶ FormData(form, submitter)
   ▲                                         │ parseWithZod / parseSubmission
   │ lastResult (JSON)                       ▼
useForm({lastResult}) ◀── submission.reply() / report() ◀── Submission{status,payload,value|error,intent}
```

Client-side objects (`form.ts`):

```ts
export type FormMeta<FormError> = {
  formId: string; isValueUpdated: boolean; pendingIntents: Intent[];
  submissionStatus?: 'error' | 'success';
  defaultValue: Record<string, unknown>;   // serialize(options.defaultValue)
  initialValue: Record<string, unknown>;   // lastResult?.initialValue ?? defaultValue
  value: Record<string, unknown>;          // live FormData snapshot
  error: Record<string, FormError>;        // keyed by path, '' = form
  constraint: Record<string, Constraint>;
  key: Record<string, string | undefined>; // list-item identity
  validated: Record<string, boolean>;
};
```

`FormState` adds derived `valid` and `dirty` maps (proxies). Per-field `Metadata` (context.tsx) is:

```ts
{ key, id /* `${formId}-${name}` */, errorId /* `${id}-error` */, descriptionId, name,
  defaultValue, defaultOptions, defaultChecked, initialValue, value,
  errors /* state.error[name] */, allErrors /* every key with prefix name */,
  valid /* no error under prefix */, dirty }
  & Constraint & { formId } & { getFieldset() | getFieldList() }
```

The **future** API keeps the same philosophy but drops `value` from metadata entirely (use `useFormData(formRef, selector)`), replaces `validated` with `touchedFields`, replaces `getFormProps(form)` with `form.props`, moves `form.validate/insert/...` to an `intent` dispatcher, accepts a Standard Schema as first argument (`useForm(schema, options)`), and makes intents extensible (`defineIntent`, `configureForms({intents, customState, extendFieldMetadata, getConstraints, validateSchema, shouldValidate, serialize, intentName})`). Server side: `parseSubmission(formData)` → `resolveSubmission(submission)` → `{intent, targetValue}` → `report(submission, {error | issues, targetValue, reset, hideFields, keepFiles})`.

## Data in: naming conventions, parsing, coercion, nested/list handling

**Grammar** (`packages/conform-dom/formdata.ts: parsePath`): token regex `/([^.[\]]+)|\[(\d*)\]/g`; a single `.` is allowed between tokens; `[]` yields an empty segment `''` (only legal as the last segment, meaning "push"); numeric brackets must be non-negative integers; the segments `__proto__` and `constructor` throw. `formatPath(['todos', 0, 'content'])` → `todos[0].content`; `appendPath('tags', '')` → `tags[]`. Related helpers: `getRelativePath`, `isPathPrefix`, `getPathValue`, `setPathValue(target, path, valueOrFn, {mutate, silent})` (copy-on-write unless `mutate`).

**FormData → nested object** (`parseSubmission`, future; `getSubmissionContext`, v1): iterate entries in order; skip the intent (`__INTENT__` future / `__intent__` v1) and `__state__` (v1) names; for every other entry set the value at the parsed path; if a value already exists at that path the two become `[prev, next]` (then `push`); a name ending in `[]` is always an array even with one entry. Invalid paths are skipped silently (`silent: true`). `File` objects are kept as-is. Live run against the packed 1.21.1 dist (my `run1.mjs`):

```
--- parseSubmission (future) nested + repeated names + [] + empty string
{ "payload": { "title": "",
    "todos": [ { "content": "Buy milk", "completed": "on" }, { "content": "" } ],
    "address": { "city": "Paris" },
    "colors": [ "red", "blue" ],          // two entries named "colors"
    "tags": [ "one" ] },                  // one entry named "tags[]"
  "fields": [ "title","todos[0].content","todos[0].completed","todos[1].content","address.city","colors","tags[]" ],
  "intent": "save" }
```

Note `fields` records the *raw names present*, which the client later uses to decide which fields count as validated after a submit.

**Empty strings, files, checkboxes, multi-values.** The parser keeps `''` verbatim; stripping happens in two other places: (a) coercion (`'' → undefined` before zod sees it) and (b) `reply()`/`report()` → `normalize()` drops `''`, `null`, empty arrays/objects and (server-side) `File`s, so `initialValue` echoed to the client omits blank fields (in my run `age` and `address` disappeared from `initialValue`). Files are stripped from results because a file input cannot be re-populated; `report({keepFiles: true})` opts out. A checkbox submits `'on'` (or its `value`) only when checked; a checkbox *group* is the same name repeated, i.e. an array; `<select multiple>` with nothing selected submits no entry. Conform documents this input-type behaviour explicitly in docs/integration/ui-libraries.md ("File Inputs … When empty, it still contributes an empty File object").

**Coercion** (`packages/conform-zod/v4/coercion.ts`, docs/api/zod/coerceFormValue.md). `parseWithZod` wraps the schema with `coerceFormValue(schema)` unless `disableAutoCoercion: true`. Rules: empty string / empty `File` → `undefined`; `z.number()` → `Number(text)` (whitespace-only → `NaN`); `z.boolean()` → `true` iff text is `'on'` (anything else stays a string and fails type-check); `z.date()` → `new Date(text)` (the `/v4/future` variant appends `Z` to `YYYY-MM-DDTHH:mm` strings that carry no timezone, so `datetime-local` values are treated as UTC); `z.bigint()` → `BigInt`; `z.literal(1)`/`z.literal(true)` use the matching converter; enums/literals stay strings. Structural rules: `array`: `undefined`/empty → `[]`, scalar → `[value]`; `object`: `undefined → {}` so missing nested objects still produce per-leaf `required` errors; optional/default/nullable/readonly/pipe/intersection/union/discriminatedUnion/tuple/lazy are rebuilt recursively with a `resolved` map to survive `z.lazy()` recursion. Conversion failure returns the original string so zod reports a normal `invalid_type`. `coerceStructure(schema)` is a second mode that coerces without validating (NaN/false/Invalid Date sentinels) for reading live typed values. Live run:

```
--- parseWithZod: coercion of empty/number/boolean/date/array
status: error
error: {"name":["Too small: expected string to have >=2 characters"],
        "address.city":["Invalid input: expected string, received undefined"],
        "address.zip":["Invalid string: must match pattern /^\\d{5}$/"],
        "todos[0].content":["Invalid input: expected string, received undefined"]}
status: success value: {"name":"Alice","age":42,"subscribe":false,"born":"2020-01-02T00:00:00.000Z",
        "tags":["x"],"address":{"city":"Paris","zip":"75001"},"todos":[{"content":"ok"}]}
        born instanceof Date: true  age type number
```

(`subscribe` was absent from the second FormData; `z.boolean().default(false)` supplied `false`; `tags` had one entry `'x'` and became `['x']`.)

**Serialising defaults *out*** is the mirror image (`submission.ts: serialize`, future `defaultSerialize`): booleans → `'on'` / omitted (`null` in future), numbers/bigints → `toString()`, `Date` → ISO (future: ISO without trailing `Z`), nested objects/arrays recursed; anything else `undefined`. `defaultValue` given to `useForm` is passed through this before becoming `initialValue`, so every metadata `initialValue` is a string, string[] or nested structure of those.

## Validation & error model (structure, codes vs messages, params, i18n, cross-field, when validation runs)

**Structure.** v1: `error: Record<string, FormError | null> | null` where `FormError = string[]` by default and the key is the field path; form-level errors sit under `''`. `null` for a *field* means "validation skipped — keep the previous error for this field" (`conformZodMessage.VALIDATION_SKIPPED = '__skipped__'`); `null` for the *whole* error means "validation not defined here — fall back to the server" (`VALIDATION_UNDEFINED = '__undefined__'`, `parse.ts: getError`). Future: `FormError = { formErrors: ErrorShape | null; fieldErrors: Record<string, ErrorShape> }`, normalised by `normalizeFormError` (empty arrays/strings removed). `report(submission, {error: {issues}})` accepts raw Standard Schema issues and formats them by joining `issue.path` with `appendPath`.

**Codes vs messages, i18n.** Default is messages only (`issues.map(i => i.message)`), but `parseWithZod({formatError: (issues) => …})` (v1) and `formatResult(result, {formatIssues: (issues, name) => …})` (future) let you return any `FormError` shape — e.g. `{code, params}` for client-side translation — and the generic `ErrorShape` flows through `useForm<…, FormError>` and `configureForms({isError: shape<MyError>()})`. Zod's own `error` map (`parseWithZod({error})`, v4) / `errorMap` (v3) is the i18n hook for messages.

**Cross-field** is delegated to the schema (`.refine((d) => d.password === d.confirmPassword, {path: ['confirmPassword']})`, docs/api/zod/conformZodMessage.md); the error lands on whatever path the refinement names, so a refinement without `path` becomes a form-level error.

**When validation runs** (`form.ts: willValidate`, verbatim):

```ts
function willValidate(element: FieldElement, eventName: 'onInput' | 'onBlur'): boolean {
  const { shouldValidate = 'onSubmit', shouldRevalidate = shouldValidate } = latestOptions;
  const validated = meta.validated[element.name];
  return validated
    ? shouldRevalidate === eventName && (eventName === 'onInput' || meta.isValueUpdated)
    : shouldValidate === eventName;
}
```

`onInput`/`onBlur` are document-level listeners; when they decide to validate they `dispatch({type: 'validate', payload: {name}})`, which **submits the form** through a temporary hidden `<button name="__intent__" value='{"type":"validate","payload":{"name":"email"}}' formnovalidate>` (`dom.ts: requestIntent`). If `onValidate` is configured the submit handler runs it synchronously, calls `submission.reply()` and feeds the result to `report()` locally (the network request is prevented); without `onValidate` the intent goes to the server, which sees `submission.status === undefined` and returns `submission.reply()` — i.e. server-side blur/input validation is the *same* code path with a network hop. After any result, `handleIntent` marks names validated (`validate` with a name → that name; `validate` without a name or a real submit → every `fields` entry plus every errored key) and then **filters `error` down to validated names or names under a validated prefix**, which is how "don't show errors for untouched fields" is implemented.

**Async and expensive validation** (docs/validation.md): client `onValidate` must be synchronous; the pattern is a schema *factory* `createSchema(intent, {isEmailUnique?})`. On the client the async check is undefined → add a fatal issue with `VALIDATION_UNDEFINED` → whole client result becomes `null` → Conform submits to the server; on the server `parseWithZod(formData, {schema: (intent) => createSchema(intent, {isEmailUnique}), async: true})`. To avoid re-running the uniqueness query on every keystroke elsewhere, the factory inspects `intent` and emits `VALIDATION_SKIPPED` for that field unless `intent === null || (intent.type === 'validate' && intent.payload.name === 'email')`. Future API replaces this with staged validation: `onValidate` may return `{result, pending: Promise<FormError>}`.

Other behaviours: on `status === 'error'` the client focuses the first element whose name has an error (`report()` in form.ts); `defaultNoValidate: true` sets `noValidate` after hydration so browser bubbles do not fire; future `isValid(state, name)` ignores errors of untouched fields (`state.ts`), while v1 `valid` considers every error under the prefix regardless of touch.

## Form state: bound/unbound, touched/dirty/used, initial vs submitted, attempted values, reset

Three value tiers exist per form (`createFormMeta`): `defaultValue` (what `useForm({defaultValue})` said, serialised), `initialValue` (`lastResult.initialValue ?? defaultValue` — i.e. the last *attempted* payload wins after a failed submit, so a full-page reload still shows what the user typed), and `value` (live, re-read from the DOM on every input/mutation). `dirty` is `JSON.stringify(defaultValue[name]) !== JSON.stringify(value[name])` with `shouldDirtyConsider(name)` filtering out things like CSRF tokens; the future `isDirty(formData, {defaultValue, skipEntry, serialize})` does the same as a pure function over `FormData`.

"Touched" is `validated` (v1) / `touchedFields` (future); a fieldset counts as touched if any child is (`isTouched` uses `getRelativePath`). It is set by: a validate intent naming the field, any full submit (all `fields`), intents that mutate lists (`insert/remove/reorder` mark the list name validated and shift the per-index state with `setListState`), or `update({validated: true|false})` (v1) which can also *clear* errors ("Clear all error" example in docs/intent-button.md). Because this state only lives in memory, the optional `<FormStateInput/>` renders `<input type="hidden" name="__state__" value='{"validated":{…}}'>` so a JS-less submission of, say, an `insert` intent still returns with the previously validated set intact (`getSubmissionContext` reads `__state__` back into `context.state`, and `reply()` echoes it as `result.state`).

`key` is the identity mechanism for list items: `getDefaultKey` assigns a `generateId()` to every array index in the default value; `insert/remove/reorder` splice the key map in lock-step with the values (`setListState(meta.key, intent, …)`); `update`/`reset` on a subtree assign a *new* key to that subtree. `createKeyProxy` composes `parentKey/childKey`, so `<li key={task.key}>` and `<input key={field.key}>` remount React elements exactly when their `initialValue` changed — which is the only way to push a new default into an uncontrolled input. The docs are explicit that `update`/`reset` "requires setting up the inputs with the key from the field metadata" unless you use `useInputControl`, which resets on key change.

Reset paths: `submission.reply({resetForm: true})` → `{initialValue: null}` → client `reset()` (re-creates meta from `defaultValue`, pushes a synthetic `reset` intent so `runSideEffect` restores DOM values); a `reset` intent with no name does the same server-side; changing `useForm({id})` resets (documented trick for `/articles/foo → /articles/bar`); native `<form>` `reset` events are honoured. `hideFields: ['password']` deletes those paths from the echoed payload. `submission.status` / `form.status` is `'success' | 'error' | undefined` and is the primary way the UI learns the outcome. Multiple forms: any number of `useForm`s coexist because everything is keyed by `formId`; inputs may live outside the `<form>` via the `form` attribute; `FormProvider`s nest and `useField(name, {formId})` targets a specific one.

## Rendering: HTML generation, customization layers, escape hatches for hand-written HTML

Conform generates **no HTML**. The layers are:

1. **Raw metadata** — `fields.email.id/name/initialValue/errors/errorId/required/…`. The tutorial shows the fully manual form (docs/tutorial.md) and every helper page says "The helper is optional".
2. **Prop helpers** (`helpers.ts`) — `getFormProps(form)` → `{id, onSubmit, noValidate, aria-describedby?}`; `getFieldsetProps(meta)` → `{id, name, form, aria-describedby?}`; `getInputProps(meta, {type, value?, ariaAttributes?, ariaInvalid: 'errors'|'allErrors', ariaDescribedBy?})` → adds `key, required, minLength, maxLength, min, max, step, pattern, multiple, accept` and either `defaultValue` or (`checkbox|radio`) `value` + `defaultChecked` (`initialValue === value` or `initialValue.includes(value)`); `getSelectProps`, `getTextareaProps`; `getCollectionProps(meta, {type: 'checkbox'|'radio', options})` returns one props object per option with `id: `${meta.id}-${value}`` and drops `required` for checkbox groups. `aria-invalid` is set only when the field has errors; `aria-describedby` = `errorId` (+ optional description id).
3. **Custom components** — `useField(name)` inside a `FormProvider` for reusable `<FormField name=…>` components, typed with the branded `FieldName<FieldSchema, FormSchema, FormError>`; `useInputControl(meta)` (v1) or `useControl({defaultValue})` (future) to bridge non-native widgets: it registers a hidden native `<input name=…>`, exposes `value/change/focus/blur` (`register`, `options`, `checked`, `files`, `payload` in future) and dispatches real `input`/`focusout` events so timing rules still apply. Focus delegation for the "first invalid field" behaviour needs a visually-hidden focusable input (docs/api/react/useInputControl.md).
4. **Global adapters** (future) — `configureForms({extendFieldMetadata(meta, {when}) {…}})` to expose e.g. `field.textFieldProps` for React Aria / shadcn, so call sites stop hand-mapping props.

## Styling / theming

Nothing built in. Examples toggle classes from metadata (`className={!fields.title.valid ? 'error' : ''}` in examples/react-router/app/routes/todos.tsx) and the repo ships integration examples for shadcn/ui (Radix and Base UI), Chakra, Material UI, Headless UI, React Aria. The accessibility contract (`id`, `errorId`, `descriptionId`, `aria-invalid`, `aria-describedby`, `required`, `pattern` …) is the only "theme" Conform enforces, and it is entirely attribute-level so any CSS system works.

## Nested, dynamic (add/remove/reorder) and conditional forms

**Nested objects / lists** (docs/complex-structures.md): `fields.address.getFieldset()` yields `{street, zipcode, …}` with names `address.street`; `fields.todos.getFieldList()` yields one metadata per item in `initialValue` with names `todos[0]`, each of which can `getFieldset()` again → `todos[0].title`. `getFieldList` throws if the initial value is not an array; list length is therefore driven purely by `initialValue`, which is why every mutation must go through an intent that updates `initialValue` and `key` together.

**Intents** (`submission.ts`):

```ts
export type Intent =
  | { type: 'validate'; payload: { name?: string } }
  | { type: 'reset';    payload: { name?: string; index?: number } }
  | { type: 'update';   payload: { name?: string; index?: number; value?: any; validated?: boolean } }
  | { type: 'insert';   payload: { name: string; defaultValue?: any; index?: number } }
  | { type: 'remove';   payload: { name: string; index: number } }
  | { type: 'reorder';  payload: { name: string; from: number; to: number } };
export const INTENT = '__intent__';
```

Server-side `parse()` applies them to the raw payload *before* `resolve()` (so validation sees the post-mutation list), then `createSubmission` returns `status: undefined` (an intent never counts as a submit) and `reply()` echoes `intent`, `initialValue` (the mutated payload) and `fields`. Live run of an `insert` at index 1:

```
--- v1 parse() with insert intent
status: undefined payload: {"title":"Hello","tasks":["a","NEW","b"]}
reply(): {"intent":{"type":"insert","payload":{"name":"tasks","index":1,"defaultValue":"NEW"}},
          "initialValue":{"tasks":["a","NEW","b"],"title":"Hello"},"fields":["title","tasks[0]","tasks[1]"]}
```

Client-side, `form.insert.getButtonProps({name, index?, defaultValue?})` returns `{name: '__intent__', value: serializeIntent(intent), form: formId, formNoValidate: true}` for a declarative `<button>`; `form.insert({...})` calls `requestIntent` imperatively. Both go through the submit path, so with `onValidate` present the mutation is applied optimistically by `handleIntent(update, intent, fields, initialized=true)` (splices `initialValue` and `key`) and `runSideEffect` writes `update`/`reset` values into DOM elements (`updateField`, plus `element.dataset.conform = generateId()` to wake `useInputControl`). Without JS the button is an ordinary submit whose `__intent__` value the server parses — hence "works even if JavaScript hasn't loaded" (docs/accessibility.md). The future API adds `insert({from: 'newTag'})` (validate another field, move its value into the list, clear it), `onInvalid: 'revert' | 'insert'` for min/max-items constraints, `intent.validate.serialize('title')` for hand-written no-JS buttons, and user-defined intents (`defineIntent({parse, resolve, apply, touch, move})`, e.g. `copyField({from, to})`).

**Conditional fields.** Nothing special is offered beyond schemas: `z.discriminatedUnion` is supported by coercion (it re-attaches `propValues` after rebuilding each option) and by `getZodConstraint` (union branches are merged; `required` is only kept if all branches agree, controlled by `preserveBranchSpecificRequired`, which the v1 export sets to `false`). The important limitation: because values are read from the DOM, **inputs that are not rendered do not exist** — switching a tab or collapsing an accordion loses their data, and the maintainer's answer is to keep them mounted but hidden (discussion #455).

## DX highlights — with real code (copied/adapted from primary sources; cite each example)

**1. Whole loop in one file** (docs/overview.md, Remix-style action + component):

```tsx
const schema = z.object({ username: z.string(), password: z.string() });

export async function action({ request }) {
  const submission = parseWithZod(await request.formData(), { schema });
  if (submission.status !== 'success') return submission.reply();       // also handles intents
  const session = await login(submission.value);
  if (!session) return submission.reply({ formErrors: ['Incorrect username or password'] });
  return redirect('/dashboard');
}

export default function LoginForm() {
  const lastResult = useActionResult();
  const [form, fields] = useForm({
    shouldValidate: 'onBlur', lastResult,
    onValidate({ formData }) { return parseWithZod(formData, { schema }); },
  });
  return (
    <form method="post" id={form.id} onSubmit={form.onSubmit}>
      <div>{form.errors}</div>
      <input type="text" name={fields.username.name} /><div>{fields.username.errors}</div>
      <input type="password" name={fields.password.name} /><div>{fields.password.errors}</div>
      <button>Login</button>
    </form>
  );
}
```

**2. Nested list with intents, no extra components** (docs/intent-button.md "Insert, remove and reorder intents"):

```tsx
const tasks = fields.tasks.getFieldList();
<form id={form.id} onSubmit={form.onSubmit}>
  <ul>{tasks.map((task, index) => (
    <li key={task.key}>
      <input name={task.name} />
      <button {...form.reorder.getButtonProps({ name: fields.tasks.name, from: index, to: 0 })}>Move to top</button>
      <button {...form.remove.getButtonProps({ name: fields.tasks.name, index })}>Delete</button>
    </li>))}
  </ul>
  <button {...form.insert.getButtonProps({ name: fields.tasks.name })}>Add task</button>
  <button>Save</button>
</form>
```

**3. Boilerplate before/after with `getInputProps`** (docs/api/react/getInputProps.md):

```tsx
// Before
<input key={fields.task.key} id={fields.task.id} name={fields.task.name} form={fields.task.formId}
  defaultValue={fields.task.initialValue} aria-invalid={!fields.task.valid || undefined}
  aria-describedby={!fields.task.valid ? fields.task.errorId : undefined}
  required={fields.task.required} minLength={fields.task.minLength} maxLength={fields.task.maxLength}
  min={fields.task.min} max={fields.task.max} step={fields.task.step} pattern={fields.task.pattern} multiple={fields.task.multiple} />
// After
<input {...getInputProps(fields.task, { type: 'text' })} />
<input {...getInputProps(fields.completed, { type: 'checkbox', value: 'yes' })} />
```

**4. Server-only async check with skip semantics** (docs/api/zod/conformZodMessage.md, condensed):

```ts
function createSchema(intent: Intent | null, options?: { isEmailUnique(email: string): Promise<boolean> }) {
  return z.object({
    email: z.string().email().pipe(z.string().superRefine((email, ctx) => {
      const isValidatingEmail = intent === null || (intent.type === 'validate' && intent.payload.name === 'email');
      if (!isValidatingEmail) { ctx.addIssue({ code: 'custom', message: conformZodMessage.VALIDATION_SKIPPED }); return; }
      if (typeof options?.isEmailUnique !== 'function') {
        ctx.addIssue({ code: 'custom', message: conformZodMessage.VALIDATION_UNDEFINED, fatal: true }); return; }
      return options.isEmailUnique(email).then((ok) => { if (!ok) ctx.addIssue({ code: 'custom', message: 'Email is already used' }); });
    })),
  });
}
// server: parseWithZod(formData, { schema: (intent) => createSchema(intent, { isEmailUnique }), async: true })
// client: onValidate: ({ formData }) => parseWithZod(formData, { schema: (intent) => createSchema(intent) })
```

**5. Future API todos route** (examples/react-router/app/routes/todos.tsx):

```tsx
const schema = coerceFormValue(z.object({
  title: z.string(),
  tasks: z.array(z.object({ content: z.string(), completed: z.boolean().default(false) })).nonempty(),
}));
export async function action({ request }) {
  const submission = parseSubmission(await request.formData());
  const result = schema.safeParse(submission.payload);
  if (!result.success) return { result: report(submission, { error: { issues: result.error.issues } }) };
  await todos.setValue(result.data, id);
  return { result: report(submission, { reset: true, targetValue: result.data }) };
}
const { form, fields, intent } = useForm(schema, { lastResult: actionData?.result, defaultValue: loaderData.todos, shouldValidate: 'onBlur' });
const dirty = useFormData(form.id, (fd) => isDirty(fd, { defaultValue: form.defaultValue, skipEntry: (n) => n === 'id' }));
…
<button type="button" onClick={() => intent.update({ name: task.name, value: { content: '' } })}>Clear</button>
<button type="button" onClick={() => intent.reset({ defaultValue: null })}>Clear form</button>
<button disabled={!dirty}>Save</button>
```

**6. Constraint derivation** (docs/api/zod/getZodConstraint.md, verified by my run):

```ts
const constraint = getZodConstraint(z.object({
  title: z.string().min(5).max(20), description: z.string().min(100).max(1000).optional(),
  password: z.string().regex(/[A-Z]/).regex(/[0-9]/),
}));
// { title: { required: true, minLength: 5, maxLength: 20 },
//   description: { required: false, minLength: 100, maxLength: 1000 },
//   password: { required: true, pattern: '^(?=.*(?:[A-Z]))(?=.*(?:[0-9])).*$' } }
// my run: tags → {required:true, multiple:true}; 'tags[]' → {required:true}; 'todos[3].done' → {required:false} (index normalised to [])
```

**7. Custom widget bridge** (docs/upgrading-v1.md):

```tsx
const control = useInputControl(fields.title);
<CustomSelect name={fields.title.name} value={control.value}
  onChange={(e) => control.change(e.target.value)} onFocus={control.focus} onBlur={control.blur} />
```

**8. User-defined intent** (docs/api/react/future/defineIntent.md):

```ts
const copyField = defineIntent<CopyField>({
  parse(options) { /* validate args */ return options; },
  resolve({ value, payload }) { return setPathValue(value, payload.to, getPathValue(value, payload.from)); },
  touch({ name, payload }) { return name === payload.to; },
});
const forms = configureForms({ intents: { copyField } });
// intent.copyField({ from: fields.billing.name, to: fields.shipping.name })
```

## Known pain points & criticisms (cite)

- **Conditional fields lose values** when unmounted; by design ("Conform does not keep any value of your form. What you get from Conform is just a value synced with the FormData API") — workaround is hidden inputs (discussion #455). The same DOM-first stance drew a request for state-derived values in the future-API thread (#954, user heiwen).
- **Key/remount coupling**: `update`/`reset` only take effect on uncontrolled inputs if you render `key={field.key}`; forgetting it silently does nothing (docs/intent-button.md). Multiple intents in a row needed `flushSync` in v1; the future dispatcher batches ("Inserting two items will only cause one re-render now", #1014).
- **Validation semantics surprise**: `form.validate()` with no name marks *all* fields touched, unlike blur validation (#1109, maintainer: intended, docs to improve). `valid` in v1 ignores touch state while `errors` respects it, so `aria-invalid` derived from `valid` can flag untouched fields — hence the `ariaInvalid: 'errors' | 'allErrors'` option.
- **Checkbox ambiguity**: the server cannot know whether a name is a boolean checkbox or a group, so `initialValue` may be `string | string[]` and errors for group items land on `answer[0]` not `answer` (docs/checkbox-and-radio-group.md); same for `files[0]` (docs/file-upload.md) — you must read `allErrors`.
- **UI-library integration**: `getInputProps` on top of React Aria / Radix "gives a false sense of correctness" because those libraries already wire ids/aria (docs/integration/ui-libraries.md warns; echoed in epic-stack #933); every non-native control needs a hidden native input and focus delegation.
- **Docs/maintenance/API churn**: epic-stack #933 (cjoecker): "many open issues, pull requests, and unanswered comments", examples that do not copy-paste, no search; the future export ships breaking changes in minors (1.19.0 removed `FormOptionsProvider`/`BaseMetadata`, 1.20.0 renamed `value → targetValue` and changed staged validation syntax, 1.21.0 removed `stripEmptyValues`/`invalid`), so two parallel APIs coexist in 2026.
- **React 19 auto-reset** clashes with `lastResult` handling; fix is `onSubmit(event){ event.preventDefault(); startTransition(...) }` (#606).
- **Pattern derivation is best-effort**: no `i` flag, back-references may break when several regexes are merged (docs/api/zod/getZodConstraint.md). `.pipe()` handling in constraints is marked `FIXME` in constraint.ts.
- **Security**: v1.19.4 patched a DoS in future `parseSubmission` with many repeated fields; docs now say to enforce part/size limits *before* parsing.
- **Verbose server workflow** in the future API (`parseSubmission` → `safeParse` → `formatResult` → `report`) noted by users in #1014.

## Lessons for pyview — steal / adapt / avoid (opinionated and concrete; tie to the brief; where useful sketch what the pyview-equivalent could look like in Python)

pyview is structurally *simpler* than Conform's target: there is only one runtime (the server), the client is Phoenix's JS (which already gives `_target`, debounce, recovery), and the payload arrives as `parse_qs` output. That removes Conform's hardest problem (keeping client and server in agreement without JS) but keeps every problem about *data shape, naming, touched-state, errors and intents*. Concretely:

**Steal**

1. **The path grammar as the single contract.** Adopt `user.address.city` / `todos[0].content` / `tags[]` for `name=` attributes, error keys, constraint keys and DOM ids, and write the Python twin of `parsePath/formatPath/setPathValue` (reject `__proto__`-style keys → for Python, reject `__dunder__` and non-identifier segments). Phoenix's own `user[address][city]` bracket style works too, but Conform's dotted form maps 1:1 onto pydantic `loc` tuples (`('todos', 0, 'content')` ⇄ `todos[0].content`), which makes error mapping trivial.
2. **`Submission` → `reply()` as the changeset protocol.** Replace `ChangeSet.apply` with `form.parse(payload, intent) -> Submission(status, payload, value|errors, fields, intent)` and a `result` object the template consumes. Keep `status ∈ {success, error, None}` where `None` means "an intent/validate event, not a submit"; keep `fields` (raw names present) to compute touched-ness; keep `hide_fields` for passwords; keep form-level errors under `''`.
3. **Intents as first-class events.** `insert/remove/reorder/update/reset/validate` with `{name, index, default_value, from, to}` payloads, applied to the *raw* payload before pydantic validation. In pyview these can be `phx-click="form:intent" phx-value-intent='insert("tasks")'` (or a `phx-submit` button with `name="_intent"` for no-JS/fallback); handle them generically in the form object so views never write list-splicing code. Make intents extensible like `defineIntent` (`parse/resolve/touch`).
4. **Schema-driven coercion table**, ported to pydantic: `'' → unset` (so defaults apply and `Optional` becomes `None`), `'on' → True` and *absent checkbox → False* for `bool` fields, repeated names / `[]` → list, scalar → `[scalar]` for `list[...]`, missing nested object → `{}` so leaf errors appear, `datetime-local` without tz → UTC. Implement it once as a pre-validation transform driven by the pydantic core schema (walk `model_fields` / `TypeAdapter.core_schema`) — the exact analogue of `coerceFormValue`. Also its inverse `serialize()` for defaults (bool → `'on'`, datetime → ISO) so templates always get strings.
5. **Constraint derivation** from `FieldInfo`: `required` (no default), `min_length/max_length → minlength/maxlength`, `ge/le → min/max`, `gt/lt → min/max ± step`, `multiple_of → step`, `pattern → pattern`, `list[...] → multiple`, `Literal/Enum → pattern or options`, with the `[]` wildcard for list items. This is cheap and gives instant browser-side hints and screen-reader semantics for free.
6. **Touched/validated tracking with prefix semantics** (`isTouched` via `getRelativePath`, errors filtered to touched names, `allErrors` by prefix, `valid` by prefix). pyview gets touched-ness *cheaper* than Conform: `_target` on every `phx-change` names the input; submit marks all `fields`; intents mark their list. This subsumes `phx-feedback-for`.
7. **Stable list keys** (`key` per index, spliced with the list). In LiveView this is doubly important because DOM patching keys rows by `id`; generate `key`s server-side on insert/reorder and use them for row `id`s so inputs keep focus/scroll state across patches.

**Adapt (sketch)**

```python
class Address(BaseModel):
    city: str
    zip: str = Field(pattern=r"^\d{5}$")

class Todo(BaseModel):
    content: str = Field(min_length=1)
    done: bool = False

class Todos(BaseModel):
    title: str
    tasks: list[Todo] = Field(min_length=1)
    address: Address | None = None            # conditional subtree

# mount
self.form = Form(Todos, id="todos", default=existing)          # ≈ useForm({id, defaultValue, constraint: derived})

async def handle_event(self, event, socket, payload):
    match event:
        case "validate": self.form.validate(payload)             # phx-change: coerce, validate, touch payload["_target"]
        case "intent":   self.form.apply_intent(payload)         # insert/remove/reorder/update/reset, re-validate touched
        case "save":
            sub = self.form.submit(payload)                      # ≈ parseWithZod + status
            if sub.status != "success":
                return sub.reply(hide_fields=["password"])
            await save(sub.value)                                # sub.value: Todos instance
            self.form.reset()
```

Template (t-string): `<input {f.tasks[0].content.attrs(type="text")}>` expands to `id name value required minlength aria-invalid aria-describedby` (the `getInputProps` equivalent, with `attrs(...)` overridable per widget), `{f.tasks.errors}`, `<button {f.intent.insert("tasks", default={"content": ""})}>` → `type="button" phx-click="intent" phx-value-…`. Provide `f.field("address.city")` for hand-written HTML (the `useField(name)` escape hatch) so users who bring their own markup only need `name=` strings and error lookups. Keep three layers exactly as Conform does: metadata → attribute helpers → optional widget/HTML generation on top, so "give me my pydantic class and do the rest" is layer 3 while layers 1–2 stay usable with custom HTML.

**Avoid**

- **DOM-as-only-truth.** Conform must forget unmounted conditional fields; pyview should not. Keep the *accumulated* params dict on the server (like the current `changes`) and overlay each `phx-change` payload on it, so a hidden subtree keeps its data and conditional nesting "just works" — while still using `fields`/`_target` for touched-ness.
- **JSON-in-a-button intents as the primary channel.** Conform needs them for no-JS; pyview has events. Use structured `phx-value-*` attributes / event payloads, and only fall back to a `_intent` submit field for `phx-submit` buttons.
- **The key-remount dance.** Because pyview re-renders values from server state, it can set `value=` directly; don't replicate `initialValue` vs `value` split — one `value` per field (attempted value if present, else default) is enough.
- **Two coexisting APIs.** Conform's v1 vs future split (breaking minors, `unstable_`/`future` prefixes) is the main DX complaint; pick one metadata shape (`id, name, value, errors, all_errors, valid, touched, dirty, constraints, key`) and keep it.
- **Ambiguous checkbox/boolean handling.** Because the schema is known server-side, resolve `bool` vs `list[str]` from the type, and put group errors on the list path rather than on `answer[0]`.

## Sources (every URL / repo path you actually read)

Repository clone `edmundhung/conform` @ 6b2831e (2026-09-11), files read:
- docs/overview.md, docs/tutorial.md, docs/validation.md, docs/complex-structures.md, docs/intent-button.md, docs/checkbox-and-radio-group.md, docs/file-upload.md, docs/accessibility.md, docs/upgrading-v1.md
- docs/api/react/useForm.md, useField.md, useFormMetadata.md, FormProvider.md, FormStateInput.md, getInputProps.md, getFormProps.md, getFieldsetProps.md, getCollectionProps.md, useInputControl.md
- docs/api/react/future/useForm.md, useField.md, useFormMetadata.md (props section), defineIntent.md, report.md, parseSubmission.md, useIntent.md, configureForms.md, resolveSubmission.md
- docs/api/zod/parseWithZod.md, getZodConstraint.md, coerceFormValue.md, conformZodMessage.md; docs/integration/ui-libraries.md
- packages/conform-dom/formdata.ts, submission.ts, form.ts, dom.ts (requestIntent/updateField/isDirtyInput), index.ts, future/index.ts, tests/submission.test.ts
- packages/conform-react/helpers.ts, context.tsx, hooks.ts, integrations.ts (head), future/state.ts (isTouched/isValid), future/intent.ts (head)
- packages/conform-zod/v4/coercion.ts, parse.ts, constraint.ts, format.ts, index.ts, future.ts
- examples/react-router/app/routes/todos.tsx, signup-server-validation.tsx
- package.json, packages/conform-react/package.json (version 1.21.1)

npm packages (packed and executed with Node v22.22.2, script `scratchpad/pkgs/npm-conform/run1.mjs`): @conform-to/dom@1.21.1, @conform-to/zod@1.21.1, @conform-to/react@1.21.1, zod@4.

Web:
- https://github.com/edmundhung/conform/discussions/954 (future APIs announcement)
- https://github.com/edmundhung/conform/discussions/1014 (future useForm design)
- https://github.com/edmundhung/conform/discussions/455 (conditional fields lose values)
- https://github.com/edmundhung/conform/discussions/606 (reset after submission / React 19)
- https://github.com/edmundhung/conform/discussions/1109 (form.validate() vs blur validation)
- https://github.com/epicweb-dev/epic-stack/discussions/933 (RVF vs Conform criticism)
- https://github.com/edmundhung/conform/releases (v1.19.0 … v1.21.1 notes), https://github.com/edmundhung/conform/releases/tag/v1.0.0
- WebSearch result summaries (pkgpulse / projectsupply comparisons) used only for the progressive-enhancement framing.
