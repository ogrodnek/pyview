# sveltekit-superforms (+Formsnap), React Hook Form, TanStack Form, Formik/Final Form, and Zod/Valibot/Standard Schema error shapes

Versions researched (2026-09-12): sveltekit-superforms 2.30.2 (npm tarball + main branch of ciscoheat/sveltekit-superforms and superforms-web), formsnap main (svecosystem), react-hook-form 7.x docs (rhf-docs main, `src/types/errors.ts`, `@hookform/resolvers` zod.ts), TanStack Form docs main, Formik docs main, final-form main (`src/types.ts`), zod 4.6.2 (ran), valibot 1.5.0 (ran), @standard-schema/spec main.

## TL;DR

- Every serious library has converged on **errors that mirror the data shape**: Superforms `$errors.address.city` (+ `_errors` at object/array level), RHF `errors.items[0].name.message` (+ `root`), Zod v4 `treeifyError` → `{errors, properties, items}`, Formik `errors.friends[1].name`. Flat "first path segment only" (pyview today) is the one thing nobody does.
- Server-side FormData parsing in Superforms is **schema-driven**: it converts to a JSON Schema, then coerces each posted string per field type (`parseInt`, `parseFloat`, `value=='false'→false`, `new Date`, repeated names → array). Missing checkbox → `false`; empty string → default / `null` / `undefined` depending on schema; nested objects are *refused* in form mode (`dataType:'json'` required) — a clear pain point pyview can beat because nested bracket names already arrive from Phoenix.
- **Constraints derive from the schema**: `constraints(jsonSchema)` yields `{required, minlength, maxlength, min, max, step, pattern}` per path, and users spread `{...$constraints.name}` onto inputs. Formsnap turns the same object into `aria-required`, `aria-invalid`, `aria-describedby`.
- Validation timing: Superforms default `validationMethod:'auto'` = "reward early, validate late" (errors appear on blur, but once a field has an error, re-validate on input); RHF's equivalent is `mode:'onTouched'` plus `reValidateMode:'onChange'` after submit; TanStack keys errors by *when* (`errorMap.onChange/onBlur/onSubmit`).
- "Tainted"/"dirty"/"touched" is first-class state, mirroring data (`$tainted.address.city === true`, `formState.touchedFields`, `field.state.meta.isTouched`), and gates both error display and the navigate-away warning (`taintedMessage`).
- Form-level and array-level errors are explicit slots: Superforms `_errors`, RHF `root.serverError`/`errors.items.root`, Final Form `FORM_ERROR`/`ARRAY_ERROR`, Zod `formErrors`, TanStack `{form, fields}` return.
- Multiple forms on a page need an id: Superforms `superValidate(..., {id})` + hidden `__superform_id`; `fail(400, {form})` is the universal "return the invalid form with status 400" idiom.
- Debug tooling is a feature: `<SuperDebug data={$form}/>`, TanStack `formDevtoolsPlugin`, RHF DevTools.

## Mental model & core abstractions

**Superforms** (server-first, SvelteKit). One function does everything: `superValidate(data, adapter, options?) -> Promise<SuperValidated>` where

```ts
type SuperValidated<Out, Message, In> = {
  id: string; valid: boolean; posted: boolean /*deprecated*/;
  errors: ValidationErrors<Out>;          // mirrors Out, leaves are string[], plus _errors?: string[]
  data: Out; constraints?: InputConstraints<Out>; message?: Message; shape?: SchemaShape;
}
type SuperValidateOptions<Out> = Partial<{ errors: boolean; id: string; preprocessed: (keyof Out)[];
  defaults: Out; jsonSchema: JSONSchema; strict: boolean; allowFiles: boolean; transport }>;
```
(`dist/superValidate.d.ts`). `data` can be `RequestEvent | Request | FormData | URLSearchParams | URL | Partial<In> | null`. Calling it with no data returns defaults derived from the schema (the "empty form" for GET), with `errors` suppressed unless `{errors:true}`. The **adapter** wraps a schema library: `zod`, `zod4`, `valibot`, `arktype`, `yup`, `joi`, `superstruct`, `typebox`, `effect`, `vine`, `classvalidator`, `schemasafe`, `standard` (dist/adapters/). Every adapter produces a JSON Schema, which is what drives defaults, coercion and constraints — the schema-library is only asked to validate.

The client half is `superForm(data.form, options)` returning stores: `form`, `errors`, `constraints`, `message`, `tainted`, `submitting`, `delayed`, `timeout`, `allErrors`, `formId`, plus `enhance`, `isTainted(path?)`, `reset(opts)`, `validate(path, {value, update, taint, errors})`, `validateForm({update, schema, focusOnError})`, `capture()/restore()` (snapshots) (`client/superForm.d.ts`). `errors.set(v, {force})`, `errors.clear()`, `form.set(v, {taint: boolean | 'untaint' | 'untaint-form'})`.

**Formsnap** is a thin a11y layer on top: `<Field {form} name="email">` (generic over `FormPath<T>`) provides snippet props `{value, errors, tainted, constraints}`; `<Control>` mints `id`/`labelId` with `useId()` and emits `aria-describedby` (description + errors ids), `aria-invalid`, `aria-required` (from constraints), `data-fs-error`, `data-fs-control`; `<FieldErrors>` renders `aria-live="assertive"` (`formsnap.svelte.ts` lines ~285-315). `<Fieldset>`/`<Legend>`/`<ElementField>` cover groups and array elements.

**React Hook Form** is uncontrolled-input-first: `register(name, options)` returns `{onChange, onBlur, ref, name}` to spread on a DOM input; `formState` is a proxied object (subscribing only to what you read). `useFieldArray({control, name, keyName='id', rules, shouldUnregister})` manages lists. Resolvers adapt schema libraries to `{values, errors}`.

**TanStack Form** is a headless store: `useForm({defaultValues, validators:{onChange, onBlur, onSubmit, onMount, onChangeAsync, onSubmitAsync, onDynamic}, onSubmit})`; `<form.Field name="people[0].name" validators={...} asyncDebounceMs={500}>` gives `field.state.value`, `field.state.meta`, `field.handleChange`, `field.handleBlur`. Standard-Schema schemas can be passed anywhere a validator function goes.

**Formik**: `values/errors/touched` trio; `handleBlur` sets `touched[name]=true`; `validateOnChange`/`validateOnBlur` default `true`; `<FieldArray name="friends">` exposes `arrayHelpers.push/insert/remove/swap/move/pop/unshift`.

**Final Form**: framework-agnostic observable; `form.registerField(name, callback, subscription)` where subscription is a pick of `FieldState` keys (`active, dirty, dirtySinceLastSubmit, error, initial, invalid, modified, pristine, submitError, submitFailed, touched, valid, validating, value, visited`, `src/types.ts` L74-99), so a field re-renders only for the slices it asked for. Sentinels `FORM_ERROR = "FINAL_FORM/form-error"` and `ARRAY_ERROR = "FINAL_FORM/array-error"` (`constants.ts`).

## Data in (naming, parsing, coercion, nested/lists)

**Superforms form-mode parsing** (`src/lib/formData.ts`). `parseFormData(formData, schemaData, options)`:
1. If the post contains `__superform_json` (client with `dataType:'json'`), the whole `$form` is devalue-parsed and files re-attached from `__superform_file_<path>` entries; the schema does not need to describe the post.
2. Otherwise iterate schema properties (or all keys when `additionalProperties`). Skip a key that is absent from FormData **unless its type includes boolean** (so an unchecked checkbox becomes `false`) (L309-311). Take `formData.getAll(key)`; if the property is `array`/`set`, map every entry through the item type; else take the **last** entry.
3. `parseFormDataEntry(key, value, type, info)`: for empty value → `false` for optional boolean with `default:true`; keep `''` for enums/`const`; else schema default → `null` if nullable → `undefined` if optional. Then by type: `integer → parseInt`, `number → parseFloat`, `boolean → Boolean(value=='false' ? '' : value)`, `unix-time → new Date(value)` (invalid → `undefined`), `bigint → BigInt`, `stringbool` kept as string for Zod, and `array|object|set → throw SchemaError("... Set the dataType option to \"json\" ...")`.
4. Unions are rejected in form mode unless "compatible" (`unionError`), which is a frequent user complaint.

Multiple inputs with the same `name` yield an array (docs: nested-data L174) — only top-level. Nested objects need `dataType:'json'` + `use:enhance`. `preprocessed: ['field']` skips coercion for a field (for Zod `preprocess`). `strict: true` disables default-filling.

**RHF** uses dot paths only: `register("test.0.firstName")` is valid, `register("test[0].firstName")` is not (register.mdx L124-127). Coercion is per input via `{valueAsNumber, valueAsDate, setValueAs}` and happens *before* validation; disabled inputs yield `undefined`; values are not removed on unmount unless `shouldUnregister`. `values` prop (v7.41) reactively overrides `defaultValues` (server data), with `resetOptions:{keepDefaultValues}`.

**TanStack** paths are lodash-style `people[0].name` / `details.email`; the array field is declared with `mode="array"` and children are `<form.Field key={i} name={`people[${i}].name`}>` (arrays.md L21-45); values are typed, no coercion layer (you do `e.target.valueAsNumber` yourself).

**Formik** takes lodash dot/bracket paths (`friends[1].name`) and `setNestedObjectValues` to touch everything on submit.

## Validation & error model

**Superforms errors** are produced by `mapErrors(issues: ValidationIssue[], shape)` (`errors.ts`): each `{message, path}` issue is walked into a nested object; leaf → `string[]`; empty path → top-level `_errors`; an issue whose path points at an object/array (not a leaf, last segment non-numeric) is stored at `<path>._errors`. Client display filter `updateErrors(New, Previous, force)` keeps previous positions (set to `undefined`) so an error can be shown again. `flattenErrors` → `[{path:'items[0].name', messages}]` feeds `$allErrors`. Server helpers:

```ts
import { superValidate, setError, message, fail } from 'sveltekit-superforms';
const form = await superValidate(request, zod4(schema));
if (!form.valid) return fail(400, { form });
if (await emailTaken(form.data.email)) return setError(form, 'email', 'E-mail already exists.'); // -> fail(400,{form}), valid=false
setError(form, `post.tags[${i}].name`, 'Invalid tag name.');   // nested path
setError(form, '', 'Form-level');  setError(form, 'tags._errors', 'Max 3');   // '' or "._errors" suffix
return message(form, 'Saved!', { status: 303 /* >=400 => valid=false */ });
```
(`superValidate.d.ts`, error-handling docs L40-70, L195-249.) Caveat in docs L71: `setError` errors vanish at the first client-side validation — schema `refine` with `path` is preferred.

Timing (`validationMethod`, client-validation docs L133-143 and `superForm.ts` L800-935): `'auto'` = validate on *value change*, show a text-leaf error on **blur** matching the path, or on **input** if that path already had an error; object-level errors show on blur once the parent path has been tainted; `'oninput'`/`'onblur'` force one event; `'onsubmit'` validates only on submit; `'submit-only'` also disables... (semantic difference from `onsubmit` not verified). `customValidity:true` uses `setCustomValidity` browser tooltips instead of `$errors`. Client validation always validates the *whole* schema because refinements can add errors anywhere.

**RHF** `FieldError = {type, message?, types?, ref?, root?}`; `FieldErrors<T>` mirrors `T` with `root?: Record<string, GlobalError> & GlobalError` (`src/types/errors.ts` L20-60). `criteriaMode:'all'` fills `types: {required:'..', minLength:'..'}`. `setError('root.serverError', {type:'400', message})` for global errors; array-level `rules` errors land in `errors.items.root`. Zod resolver (`@hookform/resolvers/zod/src/zod.ts` L51-95): `_path = issue.path.join('.')`, `errors[_path] = {message, type: issue.code}`, for `invalid_union` it picks the union member with the fewest issues, then `toNestedErrors` un-flattens. Modes: `mode: onSubmit(default)|onBlur|onChange|onTouched|all`, `reValidateMode: onChange(default)|onBlur|onSubmit` (useform.mdx L128-148); `delayError: ms`; `shouldFocusError`; `shouldUseNativeValidation` mirrors errors into the Constraint Validation API.

**TanStack** stores `field.state.meta.errors: unknown[]` and `errorMap: {onChange?, onBlur?, onSubmit?, onMount?, onServer?}`; a validator returns `string | undefined` (or any object — typed errors) or, at form level, `{form?: string, fields: {'socials[0].url': '...', 'details.email': '...'}}` (validation.md L250-272). With Standard Schema validators, `errorMap.onChange` is `Record<string, StandardSchemaV1Issue[]>` keyed by dotted field name. Async: `onChangeAsync` + `asyncDebounceMs` per field, `onChangeAsyncDebounceMs` per event.

**Zod v4** issue base: `{code?, input?, path: PropertyKey[], message}` (`v4/core/errors.ts` L10-14); codes `invalid_type{expected}`, `too_small{origin, minimum, inclusive}`, `too_big`, `invalid_format`, `not_multiple_of`, `unrecognized_keys{keys}`, `invalid_union{errors: issue[][]}`, `invalid_key`, `invalid_element`, `custom`. Real output (zod 4.6.2, run in scratchpad):

```
ISSUES [{"origin":"string","code":"too_small","minimum":2,"inclusive":true,"path":["name"],"message":"Too small: expected string to have >=2 characters"},
 {"expected":"string","code":"invalid_type","path":["address","city"],"message":"Invalid input: expected string, received undefined"},
 {"origin":"number","code":"too_small","minimum":1,"inclusive":true,"path":["items",0,"qty"],...},
 {"code":"invalid_union","errors":[],"note":"No matching discriminator","discriminator":"kind","options":["dog","cat"],"path":["pet","kind"],"message":"Invalid discriminator value. Expected 'dog' | 'cat'"}]
TREEIFY {"errors":[],"properties":{"name":{"errors":["Too small..."]},"address":{"errors":[],"properties":{"city":{"errors":[...]}}},
 "items":{"errors":[],"items":[{"errors":[],"properties":{"qty":{"errors":[...]}}}]},"pet":{"errors":[],"properties":{"kind":{"errors":[...]}}}}}
FLATTEN {"formErrors":[],"fieldErrors":{"name":[...],"address":[...],"items":[...],"pet":[...]}}
```
Notes: the `superRefine` `confirm` issue did **not** appear because object-level refinements do not run when child issues exist (Zod aborts refinements on an already-invalid object) — a subtlety pyview should copy deliberately (Pydantic model validators likewise don't run after field failures in `mode='after'`). `z.treeifyError` (v4) replaces v3 `error.format()` (`{_errors:[]}` per node); `flattenError` keeps only `path[0]`; `prettifyError` prints `✖ msg\n  → at items[0].qty`. Discriminated unions report `invalid_union` at `["pet","kind"]` with `discriminator/options` — precise enough to put the error on the discriminator select.

**Valibot 1.5.0** issue: `{kind:'schema'|'validation'|'transformation', type, input, expected, received, message, requirement?, path?: [{type:'object'|'array'|..., origin:'key'|'value', input, key, value}...], issues?}` (`types/issue.ts`). Real output: `path:[{"type":"object","key":"items"},{"type":"array","key":0},{"type":"object","key":"qty"}]`, `v.flatten(issues)` → `{"nested":{"items.0.qty":["Invalid value: Expected >=1 but received 0"]}}` (also `root`/`other` keys). `requirement` carries the parameter (1) for i18n.

**Standard Schema** (`spec/src/index.ts` L38-87): `schema['~standard'].validate(input) -> {value} | {issues: Issue[]}` with `Issue = {message: string; path?: ReadonlyArray<PropertyKey | {key: PropertyKey}>}`. That is the *entire* interop contract; Superforms' `standard` adapter, TanStack and RHF resolvers consume exactly it. Ran: `S["~standard"].validate({name:"x"}).issues` → same Zod issues; Valibot's → `path:["items",0,"qty"]` after mapping `p.key`.

## Form state

| | value store | touched/tainted | dirty | submit lifecycle | attempted values |
|---|---|---|---|---|---|
| Superforms | `$form` (typed `Out`) | `$tainted` mirrors data (`SuperStructArray<T, boolean>`), `isTainted(path)`, untainted after a `valid:true` result | same (tainted = modified vs initial) | `submitting`, `delayed` (after `delayMs=500`), `timeout` (after `timeoutMs=8000`), `multipleSubmits:'prevent'|'allow'|'abort'` | `form.data` is *coerced* data merged with defaults; raw strings not kept, hence `intProxy`, `dateProxy`, `booleanProxy`, `stringProxy`, `numberProxy({empty:'null'|'undefined', delimiter})`, `fileProxy`, `arrayProxy` (`client/proxies.d.ts`) to bind string inputs |
| RHF | DOM (uncontrolled) / `getValues()` | `touchedFields` (blur) | `dirtyFields`, `isDirty` (vs `defaultValues`) | `isSubmitting`, `isSubmitted`, `isSubmitSuccessful`, `submitCount`, `isValidating`, `validatingFields`, `isLoading` (async defaults) | raw input value until `valueAs*` |
| TanStack | `form.state.values` | `isTouched` (change or blur), `isBlurred` | `isDirty` (persistent) vs `isDefaultValue` | `isSubmitting`, `isSubmitted`, `submissionAttempts` | typed value |
| Formik | `values` | `touched` (blur; all on submit) | `dirty` = !isEqual(initialValues) | `isSubmitting`, `submitCount`, `status` | strings |
| Final Form | `values` | `touched`, `visited`, `active` | `dirty`, `dirtySinceLastSubmit`, `modified`, `pristine` | `submitting`, `submitFailed`, `submitSucceeded`, `submitError` | per subscription |

## Rendering & customization & styling

None of these libraries render HTML for you; they produce *attributes*. Superforms' idiom (error-handling docs L27-30):

```svelte
<input name="name" bind:value={$form.name} {...$constraints.name}
       aria-invalid={$errors.name ? 'true' : undefined} />
{#if $errors.name}<span class="invalid">{$errors.name}</span>{/if}
```
`constraints(schema)` (`jsonSchema/constraints.js`): `minLength→minlength`, `maxLength→maxlength`, `pattern` (first of `pattern`/`allOf[].pattern`), `minimum/maximum→min/max` (ISO string for `unix-time` dates), `multipleOf→step`, `required:true` unless optional/nullable/has default (and deleted if any union branch is optional). Formsnap adds the a11y contract; shadcn-svelte's `Form.*` components wrap Formsnap with Tailwind classes — styling lives in a user-owned component layer, not the library. RHF and TanStack are headless too; TanStack's `form-composition` guide (`createFormHook({fieldComponents, formComponents})`) is the "app-level pre-bound field components" pattern. Scroll/focus: Superforms `scrollToError:'auto'|'smooth'|'off'|ScrollIntoViewOptions`, `autoFocusOnError:'detect'`, `errorSelector:'[aria-invalid="true"],[data-invalid]'`; RHF `shouldFocusError`.

## Nested / dynamic / conditional

Superforms nested arrays (nested-data docs L95-110):

```svelte
const { form, errors, enhance } = superForm(data.form, { dataType: 'json' });
{#each $form.tags as _, i}
  <input data-invalid={$errors.tags?.[i]?.name} bind:value={$form.tags[i].name} />
  {#if $errors.tags?.[i]?.name}<span>{$errors.tags[i].name}</span>{/if}
{/each}
{#if $errors.tags?._errors}<div>{$errors.tags._errors}</div>{/if}   <!-- array-level: max(3) -->
```
Adding rows is plain `$form.tags = [...$form.tags, {id: 0, name: ''}]` — no ids; Svelte keyed each is the user's problem. `arrayProxy(superForm, 'tags')` returns `{path, values, errors, fieldErrors}` stores. Multi-step/conditional: swap `options.validators = valibot(schema)` at runtime (client-validation L118-125), `validateForm({schema})`.

RHF: `useFieldArray` returns `fields: (object & {id: string})[]` with an auto-generated key (`keyName`, default `id`; overwrites your `id` unless renamed) and `append/prepend/insert/swap/move/update/replace/remove(index|index[])`; must use `key={field.id}`, never index (usefieldarray.mdx L81-88); `shouldUnregister:true` is incompatible with field arrays (L116); `disabled` (v7.79) turns the whole array into a no-op "for discriminated-union form shapes" (L30). Conditional fields: render/unrender inputs; `unregister(name)` or `shouldUnregister` decides whether values survive.

TanStack: `field.pushValue(v)`, `removeValue(i)`, `moveValue(a,b)`, `swapValues`, `insertValue`; `form-groups` / `linked-fields` guides (`onChangeListenTo: ['password']`) cover cross-field revalidation; `dynamic-validation` guide adds `onDynamic` (unverified details).

Formik `<FieldArray name="friends" render={({push, remove, insert, swap, move, pop, unshift}) => ...}>`; Final Form needs `final-form-arrays` mutators (`push`, `remove`, `move`, …) registered at `createForm({mutators: arrayMutators})`.

## DX highlights with real code

1. **One call, one object, one hidden id** (Superforms README + multiple-forms docs L156-169):
```ts
// +page.server.ts
export const load = async () => ({ form: await superValidate(zod4(schema), { id: 'login' }) });
export const actions = { default: async ({ request }) => {
  const form = await superValidate(request, zod4(schema), { id: 'login' });
  if (!form.valid) return fail(400, { form });
  return message(form, 'Welcome');
}};
```
```svelte
<input type="hidden" name="__superform_id" bind:value={$formId} />   <!-- needed without use:enhance -->
```
2. **Constraint spread + tainted-gated submit** (tainted docs L76): `<button disabled={!isTainted($tainted)}>Submit</button>`.
3. **Debug**: `<SuperDebug data={$form} />` renders the live store (and `$errors`, `$tainted` if passed) as JSON with a status badge — the docs put it on nearly every example.
4. **RHF setError root** (seterror.mdx L35-45):
```js
setError("root.serverError", { type: "400", message: "Bad request" });
{errors.root?.serverError && <p>{errors.root.serverError.message}</p>}
```
5. **TanStack server-driven field errors** (validation.md L254-267): `onSubmitAsync` returns `{form:'Invalid data', fields:{'socials[0].url':'The provided URL does not exist'}}` and each field's `errorMap.onSubmit` lights up.
6. **Zod path on refinement** (api.mdx L2509-2563): `.refine(d => d.pw === d.confirm, { message: 'no match', path: ['confirm'] })` → issue `path:["confirm"]` so the error renders under the right input.
7. **Superforms proxies** for the "string in the DOM, number in the model" gap: `const age = intProxy(form, 'age', { empty: 'undefined' }); <input bind:value={$age}>`.

## Pain points & criticisms

- Superforms form-mode cannot post nested objects; the thrown message literally says "Set the dataType option to 'json'" (`formData.ts` L389-395). JSON mode then breaks `disabled` inputs and progressive enhancement (nested-data docs L31). Unions in form mode throw `unionError` (L30). Coercion surprises: `Boolean('false'→'')` means the string "false" is falsy but "0" is truthy; invalid dates silently become `undefined`; empty required enum keeps `''` so you need `strict` to detect missing values (comment L364-372).
- Superforms `setError` values are wiped by the first client validation (docs L71) — server-only errors and client validation fight.
- `posted` is deprecated as "inconsistent between server and client validation, and SPA mode" (`superValidate.d.ts`), a sign that "was this form submitted?" is a hard state to define.
- RHF: `register` merges options and cannot un-set them (`register('test', {})` is wrong, register.mdx L136-146); disabled inputs return `undefined`; dot-only paths; `useFieldArray` + `shouldUnregister` conflict; `keyName` overwrites DB `id` fields.
- RHF `mode:'onChange'` docs warn of "significant impact on performance" (useform.mdx L138) — the reason `onTouched` exists.
- TanStack: every `<form.Field>` needs both `onChange={field.handleChange}` and `onBlur={field.handleBlur}` wired by hand (validation.md L62-65); Standard Schema errors change the *type* of `errorMap` (string vs `Record<string, Issue[]>`) (L221).
- Zod: object-level `superRefine` is skipped when children fail (observed above), so "passwords differ" only shows after both fields individually validate — confusing; v3→v4 renamed `error.format()`→`treeifyError` and issue codes, breaking resolvers (`isZod4Error` shim in `@hookform/resolvers`).
- Formik: validates the whole form on every keystroke by default and re-renders everything (widely cited; unverified quantitative claims).

## Lessons for pyview — steal / adapt / avoid

**Steal**
1. **Errors mirror data, with `_errors` at every node.** Map Pydantic `ValidationError.errors()` (`loc` tuple) exactly the way Superforms `mapErrors` maps Standard-Schema `path`: leaf → `list[str]`, empty `loc` (model validator) → root `_errors`, `loc` ending at a list/dict → `<path>._errors`. Expose `changeset.errors.address.city`, `changeset.errors.items[0].qty`, `changeset.errors._errors`. Keep the raw Pydantic errors (`type`, `ctx`, `msg`) for i18n — Zod's `{code, minimum, inclusive}` and Valibot's `requirement` show why the params matter.
2. **Constraints derived from the schema, spread onto inputs.** Pydantic `FieldInfo.metadata` (`MinLen`, `MaxLen`, `Ge/Le/Gt/Lt`, `MultipleOf`, `Pattern`) + required/default ⇒ `{required, minlength, maxlength, min, max, step, pattern}`; a `constraints(path)` helper the user can splat into t-strings (`<input {**form.attrs("age")}>`). Cheap, and it gives free browser-side validation.
3. **`auto` timing** = Superforms "reward early, validate late": show a field's error only once it's *tainted and blurred* (phx-blur / `_target`) or once it has previously shown an error; re-validate on every phx-change. On LiveView 0.20 this maps to: tainted-set on `_target`, blur events via `phx-blur`, and `phx-feedback-for` for pre-touch hiding. After submit (`isSubmitted`), show everything (RHF `reValidateMode`).
4. **Tainted mirrors data** (`SuperStructArray<T, boolean>`): `changeset.tainted.address.city`, `is_tainted(path)`; clear on successful submit. Feed it to `disabled` on the submit button and to the error filter.
5. **Root/server errors as a first-class slot** (`setError(form, '', msg)`, RHF `root.serverError`, Final Form `FORM_ERROR`): `changeset.add_error("", "E-mail taken")` and `changeset.add_error("items[0].name", ...)` returning the changeset for chaining, plus a `valid=False` side effect and an HTTP-ish status concept only if needed.
6. **Debug component**: a `{{ changeset | super_debug }}` / `SuperDebug(changeset)` t-string helper that dumps data/errors/tainted/valid. Superforms' popularity owes a lot to it.

**Adapt**
7. **Schema-driven coercion of the flat urlencoded payload** — but do it *from bracket names*, which Phoenix already sends (`user[address][city]`, `user[items][0][qty]`), so pyview gets nested objects in "form mode" for free, avoiding Superforms' biggest limitation. Rules to copy: checkbox absent ⇒ `False` only for bool fields; repeated name ⇒ list; `''` ⇒ `None` for `Optional`, default if defaulted, else leave `''` so `missing`/`string_too_short` fires; ints/floats/dates left to Pydantic (`strict=False`) rather than a hand-rolled `parseInt`. Keep the *attempted raw strings* per path (Superforms had to add `intProxy` etc. because it did not).
8. **Stable list row ids** (RHF `field.id`, `keyName`): when rendering lists, generate a client-stable key per row (uuid stored in a hidden input or in the changeset's list metadata) so removing row 0 doesn't shift DOM state; LiveView's DOM patching needs it too.
9. **Validation split**: field-level (Pydantic field validators) vs form-level (`model_validator`) vs external (DB uniqueness) — expose the TanStack `{form, fields}` idea as `add_error(path, msg)` after `validate()`; document that model validators don't run when field errors exist (same as Zod).
10. **Multiple forms**: `id` on the changeset and a hidden `_form_id`/use `phx-target` — copy `superValidate(..., {id})`.

**Avoid**
- Requiring a JSON payload mode for nesting (`dataType:'json'`): it disables progressive enhancement and `disabled` semantics; pyview must handle nesting in the urlencoded path.
- Silent coercion that swallows invalid input (`new Date('x')→undefined`, `Boolean('false')`): store the raw value and let Pydantic produce the error.
- Server-set errors that a later validation silently wipes (Superforms `setError` caveat): namespace external errors so re-validation only replaces schema errors.
- Dot-only or bracket-only path syntax: accept both `items.0.name` and `items[0].name` (RHF vs TanStack incompatibility is pure friction), and emit the Phoenix bracket form in `name=`.

## Sources

- npm tarball: `/…/scratchpad/pkgs/npm-superforms/package/dist/{superValidate.d.ts, errors.d.ts, client/superForm.d.ts, client/proxies.d.ts, jsonSchema/constraints.d.ts, jsonSchema/constraints.js, adapters/}`, `README.md`
- `/…/scratchpad/repos/superforms/src/lib/formData.ts` (L30-40, 140-200, 300-440), `errors.ts` (L30-135), `client/superForm.ts` (L160, 800-935)
- `/…/scratchpad/repos/superforms-web/src/routes/concepts/{client-validation, tainted, error-handling, nested-data, multiple-forms, timers}/+page.md`
- `/…/scratchpad/repos/formsnap/packages/formsnap/src/lib/{formsnap.svelte.ts, components/field.svelte}`
- `/…/scratchpad/repos/rhf-docs/src/content/docs/{useform.mdx, useform/register.mdx, useform/formstate.mdx, useform/seterror.mdx, usefieldarray.mdx}`; `/…/repos/rhf/src/types/errors.ts`; `/…/repos/rhf-resolvers/zod/src/zod.ts`
- `/…/scratchpad/repos/tanstack-form/docs/framework/react/guides/{validation.md, arrays.md, basic-concepts.md, devtools.md}`
- `/…/scratchpad/repos/formik/docs/{api/formik.md, api/fieldarray.md, guides/arrays.md}`
- `/…/scratchpad/repos/final-form/src/{types.ts, constants.ts}`
- `/…/scratchpad/repos/zod/packages/zod/src/v4/core/errors.ts`, `packages/docs/content/api.mdx`; `/…/repos/valibot/library/src/{types/issue.ts, methods/flatten/flatten.ts}`; `/…/repos/standard-schema/packages/spec/src/index.ts`
- Executed: zod 4.6.2 and valibot 1.5.0 in `/…/scratchpad/pkgs/npm-superforms_client_libs` (outputs pasted above)
