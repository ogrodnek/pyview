# Nested, dynamic (add/remove/reorder) and conditional forms: cross-library pattern catalogue + recommendation for a server-driven pydantic framework — versions: phoenix_live_view 0.20.17 client (pyview's vendored `static/assets/app.js`) + 1.2 docs, ecto 3.15-dev, @conform-to/react 1.21, Django 5.2.17, WTForms 3.2.2, Rails main, cocoon 1.2, RHF 7.x docs, TanStack form-core main, Filament 4.x docs, AshPhoenix main, JSON Forms core main, RJSF docs main, pydantic 2.11 — researched 2026-09-12

## TL;DR (5-8 bullets)
- Every server-side library ends up with the **same wire shape**: index-named inputs (`user[addresses][0][city]`, `pets-0-name`, `posts_attributes[0][title]`, `rows[0].variety`) plus a handful of **control params** riding in the same form (`emails_sort[]/emails_drop[]`, `pets-TOTAL_FORMS`, `_destroy`, `__intent__`, `_union_type`, `addRow`). The differences are only *who* interprets them (changeset vs formset vs controller) and *when* (change vs submit).
- The client-side libs (RHF `useFieldArray`, TanStack `pushFieldValue`, Formily `ArrayItems`, FormKit `list`) all converge on **stable per-row keys that are not the index** (`field.id`, `keyName`), because index keys make React reuse the wrong DOM node after removal. Phoenix has the same need and solves it server-side with the hidden `_persistent_id`.
- In pyview's client (verified in `app.js`): **`phx-click` never carries form values** — `pushEvent` sends only `phx-value-*` (`extractMeta`). Only two paths serialize the form: `phx-change` (`pushInput`, whole form or just the input, plus `_target`) and `phx-submit` (`pushFormSubmit`, with `e.submitter`'s `name=value` injected as a hidden input). A `<button name=… value=…>` that dispatches a `change` event is treated as the submitter of a change (`inputEl instanceof HTMLButtonElement`, L5554).
- **Recommendation**: primary mechanism = Phoenix's own: `<button type="button" name="signup[addresses_op]" value="add" phx-click={js.dispatch("change")}>` → arrives as a normal `phx-change` with `_target=signup[addresses_op]` and *every current DOM value* (no lost keystrokes, no form disabling, no HTML5 validation gate, no Enter-key implicit submission). Fallback = `phx-submit` with a named submitter (`name="_intent" value="add:addresses"` + `formnovalidate`) for JS-command-free markup. Avoid socket-state + plain `phx-click` as the default (loses keystrokes typed since the last debounced change).
- Conditional forms are best expressed as **pydantic discriminated unions** (`Field(discriminator="kind")`): pydantic already gives `('party','business','vat')` error locs and a `union_tag_invalid` error on the tag; the form layer only needs "which variant is selected" (the tag input) and re-render. Keep unselected-variant params in the attempted-params dict so switching back restores them (Conform's #455 lesson).
- Dependent selects and visibility do not need a rules engine: `_target` tells you which field changed; a small `Annotated[..., Show(when=...)]`/`Depends`-style hint is enough for the generated-HTML path, and template `{% if %}` for hand-written HTML.
- Wizards: one pydantic model per step + a final composed model; store per-step *validated dicts* in `socket.context`; validate a step with its own model on `phx-submit`, never with the whole model.

## Mental model & core abstractions
Three families:

1. **Params-driven server libs** (Ecto/Phoenix, Rails nested attributes, Django formsets, WTForms FieldList, AshPhoenix, Reform, Thymeleaf/Spring). Truth = the posted params. The list *is* whatever indices are present; add/remove/reorder are expressed as extra params that the cast step interprets. Phoenix: `cast_embed(:emails, sort_param: :emails_sort, drop_param: :emails_drop)`; Rails: `posts_attributes: [{id:, _destroy: '1'}]` with `accepts_nested_attributes_for :posts, allow_destroy: true, reject_if: :all_blank, limit:` (`nested_attributes.rb` L303-357); Django: hidden `ManagementForm` with `pets-TOTAL_FORMS/INITIAL_FORMS/MIN_NUM_FORMS/MAX_NUM_FORMS` and per-row `DELETE`/`ORDER`; WTForms: `FieldList(FormField(Address), min_entries=0, max_entries=None, separator="-")` with `append_entry(data)`, `pop_entry()`, names `addresses-0-city` (`list.py` L36-63, 155-188).
2. **Client-state libs** (RHF, TanStack, Formily, FormKit, Final Form Arrays). Truth = an in-memory value tree; the DOM is a projection. `useFieldArray({name, keyName="id", rules, shouldUnregister})` returns `fields` (each with a generated `id`) and `append/prepend/insert/remove/swap/move/update/replace` (usefieldarray.mdx L27-73); TanStack `FormApi.pushFieldValue/insertFieldValue/replaceFieldValue/removeFieldValue/swapFieldValues/moveFieldValues` (`FormApi.ts` L2715-2871); Filament `Repeater::make('members')->schema([...])->addable()/deletable()/reorderable()/reorderableWithButtons()/minItems()/maxItems()/defaultItems(3)/collapsible()/cloneable()` and `Builder::make('content')->blocks([Block::make('heading')->schema([...])])` (a tagged-union list; stored as `['type' => 'heading', 'data' => [...]]`, 13-builder.md L696).
3. **Hybrid "intent" libs** (Conform, AshPhoenix). Truth = the posted params *plus* a mutation instruction applied before validation. Conform: `__intent__` submit button whose value serializes `{type:'insert'|'remove'|'reorder'|'update'|'reset'|'validate', payload:{name, index?, from?, to?, defaultValue?}}` (`submission.ts`); parse applies the intent to the payload, returns `status: undefined` (not a submit), and the client bumps a `key` to remount the list. AshPhoenix: `add_form(form, "form[posts][0][comments]" | [:posts, 0, :comments], params:, type:, validate?:)`, `remove_form/3`, `update_form/4`, `sort_forms(form, [:comments] | [:comments, 2], [0,1,2] | :increment | :decrement)` — path-addressed mutations of a server-held form struct, driven from `handle_event` on a plain `phx-click` (the form is state on the socket, re-validated from `params(form)`).

**pyview belongs to family 1 with an optional family-3 flavour**: Ecto-style "params in, changeset out" is the maintainer's stated taste, and it makes the form stateless across reconnects (form recovery re-sends the whole form).

## Data in (naming, parsing, coercion, nested/lists)
- **Naming**: Phoenix `parent[children][0][field]` + `id="parent_children_0_field"`; Rails `member[posts_attributes][0][title]` (also accepts a hash keyed `'0' => {...}`, L297, `attributes_collection.keys` sorted); Django `prefix-index-field`; WTForms `name-index-field`; Conform/RHF/TanStack `todos[0].title` (dot for objects, brackets for lists); Thymeleaf `rows[__${rowStat.index}__].variety` (preprocessed index). Bracket syntax is what the Phoenix client sends verbatim (`serializeForm` uses `FormData` → `URLSearchParams`, no decoding), so pyview must add a Rack/Plug-style decoder: `a[b][]` → list append, `a[b][0][c]` → indexed list, `a[b][c]` → dict. Plug's rule: indices are not required to be contiguous; Ecto re-indexes by sorting keys (`cast_params(:many)` pops keys in `sort -- drop` order).
- **Control params travel next to data**: Phoenix `emails_sort[]` (one per existing row + `"new"` on add) and `emails_drop[]` (empty hidden always present so "delete all" sticks — issue #2616); Rails `_destroy` + `id`; Django `TOTAL_FORMS`; Conform `__intent__`; AshPhoenix `_union_type`, `_form_type`, `_touched`, `_index` (stripped before casting, `form.ex` L1446).
- **Coercion of a new empty row**: Ecto pops `%{}` for an unknown sort index (new child gets its own empty changeset); Rails builds from `{}` unless `reject_if: :all_blank` (`REJECT_ALL_BLANK_PROC` ignores hashes where every value is blank except `_destroy`, L303); Django extra rows are `empty_permitted=True` (untouched extras skip validation); RHF insists "append data is required and cannot be partial" (usefieldarray.mdx L66/138).

## Validation & error model (structure, codes/messages/params, i18n, timing)
- Errors are addressed by **path**: Ecto nests errors in child changesets (`traverse_errors` → `%{emails: [%{email: [...]}, %{}]}`); pydantic gives `loc` tuples — verified run:
  ```
  [('missing', ('party', 'business', 'vat'), None), ('missing', ('addresses', 0, 'city'), None)]
  [('union_tag_invalid', ('party',), {'discriminator': "'kind'", 'tag': 'other', 'expected_tags': "'personal', 'business'"}),
   ('too_short', ('addresses',), {'field_type': 'List', 'min_length': 1, 'actual_length': 0})]
  ```
  Note the discriminator label is *inside* the loc (`'business'`); a pyview error index must strip the variant segment when mapping to input names (`party[vat]`, not `party[business][vat]`) — or name the variant inputs `party[business][vat]` and preserve the other variant's params (see below).
- **List-level errors** exist everywhere: RHF `rules` → `errors.test.root`; Django `non_form_errors()`; pydantic `too_short/too_long` on `('addresses',)`; Rails `limit:` raises `TooManyRecords`. Render them next to the add button.
- **Timing**: Conform intents never count as a submit (`status: undefined`) but validation runs on the mutated payload; Phoenix runs `phx-change` validation with `action: :validate`; Django validates only on the real POST. For pyview: an add/remove op arriving via `phx-change` should re-run validation but keep the "used/touched" gate so the new empty row does not light up red immediately.
- **Renumbering after removal**: Ecto, AshPhoenix (`Enum.with_index`), Django (`TOTAL_FORMS` is what JS keeps), Conform (`fields: ["tasks[0]","tasks[1]"]` echoed after insert) all re-index from 0 on the server; the row *identity* survives only through a separate persistent id.

## Form state (bound/unbound, touched/used, attempted values)
- Phoenix: `_persistent_id` hidden per child (stored in params, used for DOM id), `used_input?` in 1.x / `phx-feedback-for` in 0.20 (pyview's client). AshPhoenix: hidden `_touched` list and `only_touched?` keyed on `_target` (`form.ex` L1231-1233, 2540).
- Conform: `initialValue` + `key` per list; every mutation updates both so React remounts (`handleIntent` splices `initialValue` and `key`).
- RHF: `fields[i].id` regenerated per row; "Field array relies on inputs being mounted and unmounted… `shouldUnregister: true` is not supported" (L116) — i.e. unmounted conditional inputs lose their values, the same trap as Conform #455 ("inputs that are not rendered do not exist").
- Attempted values for hidden variants: only the server-state libs (AshPhoenix keeps the whole form struct; Rails keeps nothing — hidden branch is simply gone) can preserve them. pyview's changeset should keep `params` for *all* variants ever entered and only *validate* the selected one.

## Rendering & customization & styling
- Phoenix: `<.inputs_for :let={ef} field={@form[:emails]}>` emits hidden `_persistent_id` (+ pk) inputs and hands you `ef[:email]` FormFields; `ef.index`, `ef.name`, `ef.id`. Buttons/checkboxes are plain HTML the user writes.
- Django: `formset.management_form`, `formset.empty_form` rendered with prefix `pets-__prefix__` for client cloning (`.replace(/__prefix__/g, n)`); no JS shipped. Cocoon: `link_to_add_association 'add task', f, :tasks` stores the rendered child partial in `data-association-insertion-template` with `child_index: "new_tasks"`, and `cocoon.js` replaces `new_tasks` with `Date.now()+counter` (`view_helpers.rb` L51, L99; `cocoon.js` L5-6, 54-66) — a *timestamp as index* is the pre-LiveView answer to unique new-row keys.
- Filament: every field is a PHP object with closures; conditional display is `->hidden(fn (Get $get): bool => $get('role') !== 'staff')` and the trigger is `->live()` / `->live(onBlur: true)` / `->live(debounce: 500)` on the *source* field (01-overview.md L274-286, 1177-1201) — exactly `phx-change` + `phx-debounce` semantics, with `$get('../sibling')` relative paths inside repeaters. Wizards: `Wizard::make([Step::make('Order')->schema([...]), ...])->skippable()->persistStepInQueryString()->submitAction(...)` (05-wizards.md).
- JSON-schema families: RJSF `uiSchema` `orderable/addable/removable` per array (arrays.md L98-139), conditional via `dependencies` + `oneOf` ("If exactly one matches, the rest of that schema is merged", dependencies.md L177); JSON Forms `Rule {effect: SHOW|HIDE|ENABLE|DISABLE, condition: SchemaBasedCondition{scope: '#/properties/kind', schema: {const:'business'}, failWhenUndefined?}}` (`uischema.ts` L79-150). These are the declarative-visibility precedents for a pydantic `Annotated` hint.

## Nested / dynamic / conditional

### Catalogue of add/remove/reorder mechanisms (concrete HTML/flow)
| Library | Add | Remove | Reorder | Identity | Round trip |
|---|---|---|---|---|---|
| Phoenix ≥0.19 + Ecto ≥3.10 | `<button type="button" name="ml[emails_sort][]" value="new" phx-click={JS.dispatch("change")}>` | `<button type="button" name="ml[emails_drop][]" value={ef.index} phx-click={JS.dispatch("change")}>` + trailing empty hidden `emails_drop[]` | hidden `ml[emails_sort][]` = `ef.index` per row (drag hook rewrites values, dispatches `input`) | `_persistent_id` | phx-change (no submit) |
| Phoenix checkbox variant | `<input type="checkbox" name="f[users_sort][]">` "add more" | `<input type="checkbox" name="f[users_drop][]" value={ef.index}>` | same | same | phx-change, zero JS commands |
| Conform | `<button {...form.insert.getButtonProps({name:'tasks', index, defaultValue})}>` → `name="__intent__" value='{"type":"insert",...}' formNoValidate` | `remove` intent | `reorder {from,to}` | `key` bump per list | submit (server parses intent; works without JS) |
| Django formsets | JS clones `empty_form` (`__prefix__`) + bump `TOTAL_FORMS` | `pets-0-DELETE` checkbox | `pets-0-ORDER` int | `pets-0-id` | POST |
| Rails + cocoon | template with `new_tasks` index → timestamp | hidden `_destroy=1` + hide row (`link_to_remove_association`) | none (add `position`) | `id` | POST |
| WTForms | server: `field.append_entry()` before render | `pop_entry()` / rebuild | none | none | POST |
| RHF / TanStack | `append(obj)` / `pushFieldValue(name, value)` | `remove(i)` / `removeFieldValue` | `move/swap` / `moveFieldValues/swapFieldValues` | generated `id` | none |
| Filament Repeater | `->addable()`, `->addAction` | `->deletable()` | `->reorderable()` drag, `->reorderableWithButtons()` | uuid item keys (unverified) | Livewire request |
| AshPhoenix | `phx-click="add"` + `phx-value-path={f.name}` → `AshPhoenix.Form.add_form(form, path)` | `remove_form(form, path)` | `sort_forms(form, path, :increment)` | `_index`/`_form_type` hidden | phx-click (form held on socket) |
| Thymeleaf/Spring | `<button type="submit" name="addRow">` → `@RequestMapping(params={"addRow"})` handler appends and re-renders | `name="removeRow" value="${rowStat.index}"` | none | none | full POST |

### What pyview's client actually does (verified in `pyview/static/assets/app.js`)
- `pushEvent(type, el, targetCtx, phxEvent, meta, opts)` → payload `{type, event, value: this.extractMeta(el, meta, opts.value), cid}` (L5528-5535). `extractMeta` collects `phx-value-*` and, for inputs, `value`. **A `phx-click` on a button inside a form does not include the form's inputs.**
- `bindForms` submit handler: `js_default.exec("submit", phxEvent, view, e.target, ["push", {submitter: e.submitter}])` (L6586-6590) → `pushFormSubmit(formEl, …, submitter)` → `serializeForm(formEl, {submitter, ...meta})`: if `submitter.name`, a hidden `<input name=submitter.name value=submitter.value>` is inserted before the button, serialized, then removed (L4668-4697). So a named submit button's value **is** in the `phx-submit` payload, at the button's document position.
- `pushFormSubmit` first calls `disableForm`: every `BUTTON` becomes `disabled`, every `INPUT/TEXTAREA/SELECT` `readOnly`, the form gets `phx-submit-loading`; a second submit while one is pending is ignored (L5617-5644, L5669). With a submitter, `phx-disable-with` text is applied only to the submitter and the form (L5439). Native HTML5 constraint validation runs before `submit` fires, so an intent button needs `formnovalidate`. And HTML implicit submission (Enter in a text input) clicks the form's **first** submit button — if that is "add address", Enter adds rows.
- `pushInput`: if the event source is an `HTMLButtonElement` it becomes `meta.submitter` (L5554), so a `<button type="button" name="x" value="y">` whose click runs `JS.dispatch("change")` (pyview: `js.dispatch("change")`, `pyview/js.py` L473) produces a `phx-change` payload with **all form values** + `x=y` + `_target=x`. No disabling, no HTML5 gate, no implicit-submission hazard, and since `serializeForm` reads the live DOM, the latest keystrokes are included even if their own debounced change event has not fired yet.
- DOM patching: the focused input is never value-patched, other attributes (including `name`) are merged (dom_patch L236-241, dom.js L467 per `phoenix_client_js.md`), so renumbering `addresses[2]`→`addresses[1]` under the cursor is safe **if the element's `id` stays the same** (morphdom matches by id). Selects whose options changed are re-morphed and blurred.

### Trade-off matrix for a server-driven add/remove
| | (b) button + `js.dispatch("change")` (Phoenix recipe) | (a) `phx-submit` + named submitter (`_intent`) | (c) socket state + plain `phx-click` (AshPhoenix style) |
|---|---|---|---|
| Carries current values | yes, whole form | yes, whole form | no — last `phx-change` snapshot; keystrokes typed inside the debounce window are lost |
| UI lock | none | whole form readonly until reply, `phx-submit-loading` | none |
| Needs JS command | yes (trivial) | no | no |
| Works w/ HTML5 `required` | yes | needs `formnovalidate` | yes |
| Enter-key hazard | none | yes unless a real submit button comes first | none |
| Validation semantics | it's a `validate` event | must be told "not a real submit" (Conform `status: undefined`) | separate event |
| Reconnect recovery | `phx-auto-recover` resends form; sort/drop hidden inputs still present | same | server state lost unless in session |

**Recommendation**: (b) primary, (a) as the no-JS-command fallback and for `<noscript>`-ish progressive enhancement, (c) only for operations that do not touch typed data (e.g. "load 10 more"). Encode the op in *one* control input per list so the parser can be generic: `name="signup[addresses][__op]"` with values `add`, `remove:<rid>`, `up:<rid>`, `down:<rid>`; Phoenix's split `_sort[]`/`_drop[]` is more general (drag-and-drop writes the sort list) — support both if you want a drag hook later.

### Stable row identity
Index is the *address*, not the *identity*. Emit per row a hidden `signup[addresses][0][_rid]` (uuid4 hex[:8], generated when the row is created — the Phoenix `_persistent_id` idea, cocoon's timestamp idea) and derive DOM ids from it: `id="signup-addresses-{rid}-city"`. Names use the index and get renumbered; ids do not, so LiveView's morph keeps focus and scroll, and `remove:<rid>` is unambiguous even after the user reordered. Do **not** use `_rid` as a pydantic field: strip `_`-prefixed keys before `model_validate` (AshPhoenix drops `_form_type/_touched/_union_type`, L1446).

### Min/max items
Read `min_length/max_length` from `FieldInfo.metadata` (pydantic v2 stores `MinLen/MaxLen` annotated constraints) to (1) render `defaultItems`-style starter rows (`min_length` empty rows, Django `min_num`, Filament `defaultItems`), (2) disable the add button at `max_length` (Filament `->maxItems()`, WTForms `max_entries` assertion in `_add_entry`), (3) refuse `add` server-side anyway, (4) show the list-level `too_short/too_long` error next to the add button.

### Discriminated-union subforms
Tag `<select name="signup[party][kind]">` is an ordinary `phx-change` target. Server: `changeset.params["party"]["kind"]` picks the variant; render that variant's inputs *named by variant*: `signup[party][business][vat]`. Advantages: the pydantic loc `('party','business','vat')` maps 1:1 to the name; both variants' params coexist in the attempted params (switching back restores typed values — the thing Conform/RHF cannot do because unmounted inputs vanish); on validate, build `party = {"kind": kind, **params["party"].get(kind, {})}`. Errors on the tag (`union_tag_invalid`) render at `signup[party][kind]`. AshPhoenix does the same with hidden `_union_type` (L553).

### Dependent selects (country → state)
`_target == "signup[address][country]"` → recompute `states` options in the handler, store on `socket.context`, clear `state` in params if it is not among the new options. The client will re-morph the `<select>` because its option set changed (and blur it). Filament's `->live()` + `->options(fn (Get $get) => ...)` is the same pattern with the dependency declared on the *dependent* field; for pyview the natural place is a per-field hint or plain handler code.

### Declarative visibility vs template logic
Hand-written templates: `{% if form.party.kind.value == "business" %}` — nothing to invent. Generated HTML: a small hint `Annotated[str, FormHint(show_when=lambda d: d.get("kind") == "business")]` or a `Show(field="kind", equals="business")` object (JSON Forms `Rule`/RJSF `dependencies` in Python clothes) evaluated against the *attempted params*, not the model (model may be invalid mid-edit). Hidden ≠ deleted: keep the params, skip validation for hidden fields only if the model itself makes them optional (pydantic has no "ignore this field" switch — use the union/variant model for real conditional requiredness).

### Wizards
Pydantic has no validation groups. Two workable designs: (1) **one model per step** (`Step1(BaseModel)`, `Step2`, …) and a final `Signup = Step1 + Step2 + …` (composition or `create_model`), each step is a normal single-model form with `phx-submit="next"`; (2) partial validation of the *whole* model via `model_construct` or `TypeAdapter(...).validate_python(..., experimental_allow_partial=True)` — the latter only tolerates *trailing* missing data and is meant for streaming (unverified for this use; do not rely on it). Choose (1). State: `socket.context["wizard"] = {"step": 2, "data": {"1": {...validated dict}, "2": {...}}}`; back navigation re-renders step n-1 from `data[str(n-1)]`; `phx-auto-recover="recover"` re-validates the current step's form on reconnect; deep-link with `push_patch(?step=2)` if you want Filament's `persistStepInQueryString`.

## DX highlights with real code (cite each)

**1. Phoenix inputs_for + sort/drop** (LiveView `inputs_for/1` docs, reproduced in `liveview_forms.md`):
```heex
<.inputs_for :let={ef} field={@form[:emails]}>
  <input type="hidden" name="mailing_list[emails_sort][]" value={ef.index} />
  <.input type="text" field={ef[:email]} placeholder="email" />
  <button type="button" name="mailing_list[emails_drop][]" value={ef.index} phx-click={JS.dispatch("change")}>x</button>
</.inputs_for>
<input type="hidden" name="mailing_list[emails_drop][]" />
<button type="button" name="mailing_list[emails_sort][]" value="new" phx-click={JS.dispatch("change")}>add more</button>
```
with `cast_embed(:emails, sort_param: :emails_sort, drop_param: :emails_drop)` and `embeds_many ... on_replace: :delete`.

**2. Conform intent** (`submission.ts`, `conform.md` live run): `insert` at index 1 turns payload `{"tasks":["a","b"]}` into `{"tasks":["a","NEW","b"]}`, `status: undefined`, `fields: ["title","tasks[0]","tasks[1]"]`; button props `{name:'__intent__', value: serializeIntent(intent), form: formId, formNoValidate: true}`.

**3. Django management form** (`formsets.py`, real run in `django_wtforms.md`): `<input type="hidden" name="pets-TOTAL_FORMS" value="2"> ... pets-INITIAL_FORMS ... pets-MIN_NUM_FORMS ... pets-MAX_NUM_FORMS`; `empty_form` → `pets-__prefix__-name`; deleted rows come back as `{'DELETE': True, ...}` in `deleted_forms`.

**4. Rails** (`nested_attributes.rb` L106-122): `accepts_nested_attributes_for :posts, allow_destroy: true`; `posts_attributes: [{title: 'Kari…'}, {title: '', _destroy: '1'}]` → second ignored; `reject_if: :all_blank`, `limit: 3`, `update_only: true`.

**5. RHF** (usefieldarray.mdx L39-48): `const { fields, append, prepend, remove, swap, move, insert } = useFieldArray({ control, name: "test" }); fields.map((field, index) => <input key={field.id} {...register(`test.${index}.value`)} />)` — the docs' rule: `key={field.id}`, never `key={index}`.

**6. AshPhoenix** (`form.ex` L3784-3800): `add_form(form, "form[posts][0][comments]")` or `add_form(form, [:posts, 0, :comments], params: %{...}, validate?: true)`; `sort_forms(form, [:comments, 2], :increment)`.

**7. Filament conditional** (01-overview.md L274-286): `Select::make('role')->options([...])->live()` then `Toggle::make('is_admin')->hidden(fn (Get $get): bool => $get('role') !== 'staff')`.

### pyview sketches (proposed API; names illustrative)

**Address list — model, handler, Ibis template**
```python
class Address(BaseModel):
    street: str
    city: str
class Signup(BaseModel):
    name: str
    addresses: Annotated[list[Address], Field(min_length=1, max_length=3)]

class SignupView(LiveView[Ctx]):
    async def mount(self, socket, session):
        socket.context["form"] = Form(Signup, params={"addresses": [{}]}, as_="signup")   # 1 starter row (min_length)
    async def handle_event(self, event, payload, socket):
        form = socket.context["form"]
        if event == "validate":            # phx-change, incl. add/remove/up/down via _target=signup[addresses][__op]
            form = form.apply(payload)     # decode brackets → nested dict; run list ops; validate; mark used via _target
        elif event == "save" and (m := form.apply(payload, action="submit").model):
            ...
        socket.context["form"] = form
```
```html
<form phx-change="validate" phx-submit="save" id="{{ form.id }}">
  {{ form.name | text_input }}
  {% for row in form.addresses %}
    <fieldset id="{{ row.id }}">                         {# id from _rid, stable across renumbering #}
      <input type="hidden" name="{{ row.name }}[_rid]" value="{{ row.rid }}">
      {{ row.street | text_input }} {{ row.city | text_input }}
      <button type="button" name="{{ form.addresses.name }}[__op]" value="remove:{{ row.rid }}"
              phx-click='{{ js.dispatch("change") }}'>Remove</button>
      <button type="button" name="{{ form.addresses.name }}[__op]" value="up:{{ row.rid }}"
              phx-click='{{ js.dispatch("change") }}'>Up</button>
    </fieldset>
  {% endfor %}
  {{ form.addresses.errors | error_tag }}                 {# too_short / too_long #}
  <button type="button" name="{{ form.addresses.name }}[__op]" value="add"
          phx-click='{{ js.dispatch("change") }}' {% if form.addresses.full %}disabled{% endif %}>Add address</button>
  <button type="submit" phx-disable-with="Saving…">Save</button>
</form>
```
Server-side `apply` for the op (≈ Ecto `cast_params(:many)` in Python): rows = `[params["addresses"][k] for k in sorted(int keys)]`; `add` → append `{"_rid": new_rid()}` unless `len >= max_length`; `remove:<rid>` → drop the matching row; `up/down` → swap; then renumber to `0..n-1` and validate `Signup` with `_`-keys stripped; errors keyed by `('addresses', i, 'city')` are looked up by the renumbered index. Fallback (a): same handler reached from `phx-submit` with `<button type="submit" name="_intent" value="add:addresses" formnovalidate>`; treat `_intent` present as "not a save".

**Personal/business union**
```python
class Personal(BaseModel): kind: Literal["personal"]; first_name: str; last_name: str
class Business(BaseModel): kind: Literal["business"]; company: str; vat: str
class Signup(BaseModel):
    party: Annotated[Union[Personal, Business], Field(discriminator="kind")]
```
```html
<select name="signup[party][kind]">{% for k in form.party.variants %}<option value="{{k}}" {{ form.party.kind == k | selected }}>{{k}}</option>{% endfor %}</select>
{% if form.party.kind == "business" %}
  {{ form.party.business.company | text_input }} {{ form.party.business.vat | text_input }}
{% else %} ... {% endif %}
```
Parser: `party = {"kind": p["kind"], **p.get(p["kind"], {})}`; both `p["personal"]` and `p["business"]` stay in attempted params. Generated-HTML mode renders the same by walking `get_args(Union)` and the `Literal` tag.

**Country → state**
```python
async def handle_event(self, event, payload, socket):
    form = socket.context["form"].apply(payload)
    if payload["_target"][0] == "signup[address][country]":
        socket.context["states"] = STATES[form.params["address"]["country"]]
        form = form.put("address.state", "")          # invalid selection cleared; select gets re-morphed
```

**3-step wizard**
```python
class Step1(BaseModel): email: EmailStr
class Step2(BaseModel): addresses: Annotated[list[Address], Field(min_length=1)]
class Step3(BaseModel): plan: Literal["free", "pro"]
STEPS = [Step1, Step2, Step3]
class Signup(Step1, Step2, Step3): pass

async def handle_event(self, event, payload, socket):
    w = socket.context["wizard"]                       # {"step": 0, "data": {}}
    form = Form(STEPS[w["step"]], params=w["data"].get(w["step"], {}), as_="wizard")
    if event == "validate": form = form.apply(payload)
    elif event == "next":
        form = form.apply(payload, action="submit")
        if form.model: w["data"][w["step"]] = form.model.model_dump(); w["step"] += 1
    elif event == "back": w["step"] -= 1               # data for that step is re-rendered from w["data"]
    if w["step"] == len(STEPS): final = Signup(**{k: v for d in w["data"].values() for k, v in d.items()})
```

## Pain points & criticisms (cite)
- Phoenix pre-0.19 `:append/:prepend` + `put_embed` round-trips lost rows on any other change (issue #2616 "if you remove every association … any other change to the form will cause all of the associations to be restored"); the sort/drop design fixed it but the trailing empty hidden `_drop[]` is easy to forget. `form[:field].value` "may either return a struct, a changeset, or raw parameters" — derived state must be computed in `handle_event`.
- Conform/RHF: unmounted inputs lose data (Conform discussion #455; RHF `shouldUnregister` incompatibility, usefieldarray.mdx L116); RHF requires full default objects on `append` (L138).
- Django: no JS for `empty_form`; `__prefix__` string replacement is fragile; management form is a common `missing_management_form` failure. WTForms `FieldList.populate_obj` raises `TypeError: populate_obj: cannot find a value…` when the target object lacks the attribute (verified in `django_wtforms.md`).
- Rails: `_destroy` rows must stay in the DOM (hidden) so the id is posted; `reject_if` silently drops rows, surprising users.
- AshPhoenix: `add_form(form, "foo", params: %{bar: 10})` yields non-string-keyed params until the next `validate` — the docs themselves warn "you should ideally not depend on" the params shape (L3790-3798).

## Lessons for pyview — steal / adapt / avoid (opinionated, concrete)
**Steal**
1. Phoenix's whole recipe verbatim: list ops are *form control params* interpreted by the cast step, triggered by `<button type="button" name=… value=… phx-click={js.dispatch("change")}>`. It is the only mechanism in pyview's client that carries the live DOM values without locking the form. Provide `form.addresses.add_button()/remove_button(row)` helpers that emit exactly this markup so users never hand-type it.
2. `_persistent_id` → `_rid`: hidden per-row id, DOM ids derived from it, names from the index. Strip all `_`-prefixed keys before pydantic.
3. Conform's "an intent is not a submit" rule: any payload containing a list op (or `_intent`) re-validates with `action="validate"` and never saves.
4. Ecto/AshPhoenix path addressing (`"form[posts][0][comments]"` ≡ `["posts", 0, "comments"]`): make `form.get("addresses.0.city")` and error lookup by pydantic `loc` tuple the same thing.
5. pydantic discriminated unions as *the* conditional-form primitive; variant-named inputs so both variants' params survive switching.

**Adapt**
- Django/Filament min/max → read `min_length/max_length` from `FieldInfo` to seed rows, cap the add button, and place list-level errors.
- Filament `->live()` semantics = `phx-change` + `_target`; expose `_target` as a parsed path (`("address","country")`) in the handler.
- One-model-per-step wizards with dict state on the socket; final composed model.

**Avoid**
- Plain `phx-click` + socket-held params as the default add/remove mechanism (lost keystrokes under `phx-debounce`, state lost on reconnect).
- A single `<button type="submit" name="_intent">` placed *before* the save button (Enter-key implicit submission adds rows); if you use the submit fallback put it after a real submit button and add `formnovalidate`.
- Django-style `__prefix__` client templates and `TOTAL_FORMS` counters — the server is authoritative in LiveView; there is nothing for the client to clone.
- Index-keyed DOM ids (`signup-addresses-1-city`) for rows that can be removed — focus and morph behaviour break exactly like React's `key={index}`.

## Sources (URLs / repo paths actually read)
- `/tmp/.../scratchpad/research/liveview_forms.md` (§Nested), `ecto_changeset.md`, `conform.md` (§Nested), `phoenix_client_js.md` (§Data in, §Nested), `django_wtforms.md` (§Nested)
- `/home/user/pyview/pyview/static/assets/app.js` L4668-4697 (`serializeForm` submitter injection), L5528-5535 (`pushEvent`), L5554 (`pushInput` button submitter), L5617-5700 (`disableForm`, `pushFormSubmit`), L6560-6600 (`bindForms`); `/home/user/pyview/pyview/js.py` L473-501 (`dispatch`)
- `repos/rails/activerecord/lib/active_record/nested_attributes.rb` L65-200, 297-357; `repos/cocoon/README.markdown` L88-255, `lib/cocoon/view_helpers.rb` L45-99, `app/assets/javascripts/cocoon.js` L5-74
- `pkgs/py/wtforms/fields/list.py` L22-188; Django formsets via `django_wtforms.md`
- `repos/rhf-docs/src/content/docs/usefieldarray.mdx` L25-138; `repos/tanstack-form/packages/form-core/src/FormApi.ts` L2715-2871
- `repos/filament/packages/forms/docs/12-repeater.md`, `13-builder.md` (L20-70, 696), `01-overview.md` L274-286, 1020-1050, 1177-1201; `packages/schemas/docs/05-wizards.md` L17-52, 150-209
- `repos/rjsf/packages/docs/docs/json-schema/dependencies.md`, `arrays.md` L98-139; `repos/jsonforms/packages/core/src/models/uischema.ts` L79-150
- `repos/formkit/packages/inputs/src/inputs/list.ts` (props `sync`, `dynamic`); FormKit docs via WebSearch (formkit.com/inputs/repeater, /essentials/schema; issue formkit/formkit#1144)
- AshPhoenix `lib/ash_phoenix/form/form.ex` (raw.githubusercontent, main) L553, 1231-1233, 1446, 2540-2580, 3699-3814
- Formily via WebSearch (github.com/alibaba/formily docs/guide/advanced/linkages.zh-CN.md, discussions #2709/#3785) — `x-reactions {dependencies, fulfill: {state}}` only, ArrayItems specifics unverified
- Thymeleaf + Spring tutorial 3.1 (thymeleaf.org PDF via WebSearch): `name="addRow"` submit + `@RequestMapping(params={"addRow"})`
- pydantic 2.11 run in `/home/user/pyview/.venv` (union/list error locs, output pasted above)
