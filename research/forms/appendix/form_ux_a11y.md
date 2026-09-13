# Form UX, error presentation, validation timing and accessibility (GOV.UK, WCAG 2.2, WAI, NN/g, Baymard, Adam Silver) — a checklist for default rendering

Versions researched (2026-09-12): govuk-frontend 6.5.0 (main, 2026-09-11), govuk-design-system main, w3c/wai-tutorials master-2.0 (forms pages last_updated 2019–2024), w3c/wcag main (understanding/20, 21, 22), phoenix_live_view 1.2.11 guides + the 0.20.17 client bundled in pyview (`pyview/static/assets/app.js`). Research articles (Baymard, NN/g, Adam Silver, Wroblewski, Smashing) were reachable only through WebSearch snippets — their claims are marked "(via search snippet)".

## TL;DR

- **Two-level error presentation is the accessible baseline**: an *error summary* at the top (heading "There is a problem", `role="alert"`, one link per error to the field's `id`, keyboard focus moved to the summary) **plus** an inline *error message* per field, same wording in both places, with a visually-hidden "Error:" prefix and wired to the input by `aria-describedby`. GOV.UK ships this as three tiny components (`govukErrorSummary`, `govukErrorMessage`, per-input `govuk-form-group--error`), and it is what WCAG 3.3.1/3.3.3/4.1.3 ask for.
- **Per-field markup contract** (GOV.UK `input/template.njk`): `id` defaults to `name`; hint id is `{id}-hint`, error id is `{id}-error`; `aria-describedby` = `"{caller-supplied} {id}-hint {id}-error"` in that order; error class on the group *and* the input; label `for={id}`. Copy this literally — it is the most tested form markup on the web.
- **Validation timing is contested; the research converges on "not per keystroke"**. GOV.UK: validate on submit only, show everything, `novalidate`, no `required`. Baymard/Wroblewski/NN/g: inline validation *after the user leaves the field* helps (Wroblewski/Etre 2009: −22 % errors, −42 % completion time, best variant "after" not "during"), but *premature* (on-change) validation hurts. Adam Silver lists 9 usability failures of live validation. Recommended pyview default: **validate on blur (`phx-debounce="blur"`) for used inputs, all errors on submit, errors clear as soon as the field becomes valid**; make "submit-only" and "eager" one-line policy switches.
- **Never disable the submit button** until valid (Silver: users cannot discover what is wrong, disabled buttons are not focusable, ~100 % abandonment in Smashing's data (via search snippet)); *do* disable it during an in-flight submit (`phx-disable-with`), which the Phoenix client does for you.
- **Error copy rules** (GOV.UK error-message guidance): specific, instruction or description, reuse the label's words, no "please/sorry/valid/invalid/oops", no jargon, never clear the user's input. Pydantic's default strings ("Input should be a valid integer") violate all of them — pyview needs a `(type, ctx) -> message` mapping layer with i18n hooks.
- **LiveView-specific**: keep the "used input" gate (0.20 client: `phx-feedback-for` + `phx-no-feedback` class, driven by `phx-has-focused`/`phx-has-submitted`; 1.0+: `_unused_<field>` params + `used_input?/1`); the client never overwrites a focused input's value, so re-rendering errors on every event is safe; on submit the client sets inputs `readonly`, disables the buttons, restores focus afterwards.
- **Lists/rows**: announce add/remove via a polite live region, move focus to the new row's first input (or to the "Add" button / previous row after removal), give each row a `fieldset` + `legend` ("Address 2"), and link summary errors to the *first* input in the row.

## Mental model & core abstractions

The a11y literature treats a form as four cooperating layers:

1. **Identification** — every control has an accessible name (`<label for>` or a `<legend>` for groups), and optionally a description (hint) reachable by `aria-describedby` (WAI "Labeling Controls", "Grouping Controls"). GOV.UK's twist: the question *is* the label/legend, and can be the page `<h1>` (`label.isPageHeading` / `legend.isPageHeading` in the Nunjucks macros) so screen-reader users hear it once.
2. **Instruction** — hints are single short sentences, no links, no full stops, and always outside the placeholder (WAI: "placeholder text is not a replacement for labels"; GOV.UK: "Avoid placeholder text").
3. **Error identification + suggestion** — WCAG 3.3.1 (identify the error in text), 3.3.3 (suggest a fix), delivered as both a summary and an inline message.
4. **Notification** — how the change is announced: page reload with `<title>` prefixed "Error: " (GOV.UK) / "3 Errors – Billing Address" (WAI), or for in-page updates a `role="alert"` container that receives focus, or `aria-live="polite"` regions for non-error status (WCAG 4.1.3).

The single most reused abstraction across GOV.UK is the **form group**: `<div class="govuk-form-group [govuk-form-group--error]">label, hint, error message, control</div>`. Every component (input, textarea, select, radios, checkboxes, date-input, file-upload, character-count, password-input) is this shell with a different control inside, and every component threads one variable, `describedBy`, through hint and error. That is exactly the "field widget" unit pyview should generate.

## Data in (naming, parsing, coercion, nested/lists)

The sources say little about wire format but a lot about *forgiveness*, which is a parsing concern:

- GOV.UK validation pattern: "accept information in different formats, as long as it's not ambiguous" — postcodes with/without spaces, names with apostrophes/diacritics; **ignore unwanted characters** (spaces, hyphens, brackets, full stops) in numbers and codes, before/after an answer (copy-paste), and from dictation software. Their date input research: hundreds of users typed month *names* into the month box, so they now accept "Jan"/"January".
- Date of birth is three text inputs (`inputmode="numeric"`, `autocomplete="bday-day|bday-month|bday-year"`), not `<input type="date">`; whole numbers use `type="text" inputmode="numeric"`, decimals `inputmode="decimal"`; `type="number"` is discouraged (accidental scroll-increment; no negative numbers on some keypads).
- WCAG 1.3.5 (Identify Input Purpose): user-data fields must carry the HTML `autocomplete` token (`given-name`, `family-name`, `email`, `postal-code`, `bday`, `tel`...). For pyview this means the field-metadata layer should allow `autocomplete=` and, ideally, infer it from field names/types.

Implication for pyview: coercion should happen in a **lenient pre-parse** step (strip/normalise before pydantic) so that "£1,000 " or "SW1A 1AA" do not become errors the user cannot see.

## Validation & error model (structure, codes/messages/params, i18n, timing)

### Structure: summary + inline, identical text

GOV.UK error summary (`error-summary/template.njk`, verified):

```njk
<div class="govuk-error-summary" data-module="govuk-error-summary"
     {% if params.disableAutoFocus !== undefined %}data-disable-auto-focus="..."{% endif %}>
  {#- role="alert" is on a *child* to avoid a race between the focusing JS and the alert announcement #}
  <div role="alert">
    <h2 class="govuk-error-summary__title">{{ params.titleText }}</h2>   {# "There is a problem" #}
    <div class="govuk-error-summary__body">
      <ul class="govuk-list govuk-error-summary__list">
        {% for item in params.errorList %}<li><a href="{{ item.href }}">{{ item.text }}</a></li>{% endfor %}
      </ul>
    </div>
  </div>
</div>
```

`error-summary.mjs` focuses the root on init (`setFocus(this.$root)` unless `disableAutoFocus`), and on link click it finds the target input, scrolls its **legend or label** into view first (legend for radios/checkboxes, otherwise the label — with a viewport heuristic so the input is not hidden under a mobile keyboard), then `$input.focus({ preventScroll: true })`. Rules from the docs: always show the summary even for one error; put it at the top of `main`, below back link/breadcrumbs, above `<h1>`; link to the field for single-input questions, to the *first* field with an error for multi-input questions (date), to the *first* radio/checkbox for groups; prefix the `<title>` with "Error: ".

Inline error (`error-message/template.njk`, verified):

```njk
<p id="{{ params.id }}" class="govuk-error-message">
  <span class="govuk-visually-hidden">{{ params.visuallyHiddenText | default("Error") }}:</span> {{ params.text }}
</p>
```

Placement: after label and hint, before the control, red text + red left border on the group (`govuk-form-group--error`) and red border on the input (`govuk-input--error`). For multi-input questions (date), the error names the sub-field ("must include a year") and only that sub-field gets the red border; date-input shows only the *highest-priority* error.

WAI notifications tutorial agrees on shape (`<div role="alert"><h4>There are 2 errors in this form</h4><ul><li><a href="#firstname">…`) and adds: when errors are inserted dynamically (AJAX/LiveView), the list must be inserted into a prominent container at the top *and* focus set there (or to the first invalid input). It also shows `<input id="firstname" aria-describedby="firstname_error">`.

### WCAG 2.2 criteria, one line each

- **1.3.5 Identify Input Purpose (AA)** — user-data inputs carry `autocomplete="given-name|email|…"` (technique H98).
- **3.3.1 Error Identification (A)** — errors are identified *in text* and the erroneous item named; `aria-invalid="true"` + text message; colour alone is not enough (G83, G85, ARIA21).
- **3.3.2 Labels or Instructions (A)** — `<label for>`, `<legend>`, hint via `aria-describedby`; required/format instructions given up front (G131, H44, ARIA1).
- **3.3.3 Error Suggestion (AA)** — when a fix is known, say it ("Enter a date after 31 August 2017"), unless it endangers security (G85, G177).
- **3.3.4 Error Prevention (Legal, Financial, Data) (AA)** — reversible, or checked with a chance to correct, or a review/confirm step ("Check your answers" pages).
- **3.3.7 Redundant Entry (A, new in 2.2)** — never re-ask within a process; auto-populate or offer "same as billing" (understanding doc: browser autofill does *not* count, the *content* must supply it).
- **3.3.8 Accessible Authentication (Minimum) (AA, new)** — no cognitive-function test without an alternative; allow paste and password managers (don't block `autocomplete="current-password"`, don't `onpaste="return false"`).
- **4.1.3 Status Messages (AA)** — content changes not receiving focus are announced via `role="status"`/`aria-live="polite"` (counts, "saved", search results) or `role="alert"` for errors (ARIA19, ARIA22, ARIA23).
- (3.3.6 Error Prevention (All) is AAA — same as 3.3.4 but for every submission.)

### Timing: what the sources actually say

- **GOV.UK** (validation pattern, verified text): "Do not validate when the user moves away from a field. Wait until they try to move to the next part of the service". "Only add this sort of validation if your user research shows that, on balance, it solves more problems for users than it causes." Exception: character count, where wasted writing effort justifies live feedback. Turn off HTML5 validation (`novalidate`), "Do not add `required`". Reasoning: cross-AT reliability, slow typists, consistency of copy, and they openly ask for research on whether omitting `required` harms screen-reader users.
- **Wroblewski / Etre 2009** (via search snippet; lukew.com/ff/entry.asp?883): six variants × 20 users; the best inline variant gave −22 % errors, −42 % completion time, +22 % success, +31 % satisfaction; the winning variant validated *after* the user finished a field, and "premature" (during-typing) variants performed worst — hence "reward early, punish late".
- **Baymard** (via search snippet; baymard.com/blog/inline-form-validation): 31 % of e-commerce sites have no inline validation, only ~4 % implement it well; keys are (a) avoid premature validation, (b) remove the error as soon as the input is corrected, (c) use *positive* inline validation (checkmark) so users know they are done; recommends validating on blur.
- **NN/g** (via search snippet; "10 Design Guidelines for Reporting Errors in Forms"): ideally all validation is inline "as soon as the user has finished filling in a field"; keep messages next to the field; also a summary for long forms; messages explicit, human-readable, polite, precise, constructive; never wipe the user's work; severity-appropriate presentation (no modals for field errors).
- **Adam Silver** (via search snippets; "The problem with live validation and what to do instead"): 9 usability issues — first keystroke of a min-length field is already an error; on-blur errors distract from the *next* field; errors appearing/disappearing make the page jump; multi-input fields (checkbox groups, dates) cannot sensibly be validated per input; live validation is never bulletproof so users need a way out. His alternatives: reduce the need for validation (question protocol, forgiving formats), error summary on submit, and **never disabled buttons**.
- **Smashing / Vitaly Friedman 2022** (via search snippet): live validation is "useful when it works, frustrating when it fails"; supports "reward early, punish late"; always allow overriding a live-validation false positive.

Synthesis: there is agreement that (1) per-keystroke *error* display is harmful, (2) submit-time full validation with a summary is mandatory regardless, (3) after-field (blur) validation is beneficial *for single-input text fields* if errors clear immediately on fix, and (4) groups/dates/multi-input questions should validate on submit only.

### Message copy rules (GOV.UK error-message, verified)

- Use the label's words: label "Address line 1" → "Enter address line 1, typically the building and street".
- Instructions for empties ("Enter your first name"), descriptions for constraints ("First name must be 35 characters or less"); be consistent.
- Ban list: "An error occurred", "Select an option", "This field is required", "please", "sorry", "valid/invalid", "forbidden/illegal/prohibited", "oops", error codes.
- Same text in the summary and inline; don't repeat an on-screen example in the message.
- Standard templates exist for addresses, dates ("Date of birth must include a month"), email, file upload, character count.

Mapping Pydantic v2 error `type`s to compliant defaults (proposal, message strings are mine but the pattern is GOV.UK's):

| pydantic `type` | default string | replacement (uses `{label}`, `ctx`) |
|---|---|---|
| `missing` / `string_too_short` with min 1 | "Field required" | "Enter {label}" |
| `int_parsing` | "Input should be a valid integer, unable to parse string as an integer" | "{label} must be a whole number" |
| `float_parsing` / `decimal_parsing` | "Input should be a valid number" | "{label} must be a number, like 12.50" |
| `string_too_long` | "String should have at most {max_length} characters" | "{label} must be {max_length} characters or less" |
| `greater_than_equal` | "Input should be greater than or equal to {ge}" | "{label} must be {ge} or more" |
| `date_from_datetime_parsing` / `date_parsing` | "Input should be a valid date…" | "{label} must be a real date" |
| `value_error` (email) | "value is not a valid email address: …" | "Enter an email address in the correct format, like name@example.com" |
| `enum` / `literal_error` | "Input should be 'a', 'b' or 'c'" | "Select {label}" |

The lookup key should be `(field_path, type)` → `type` → fallback, with `ctx` interpolation, and a translator hook — exactly Ecto's `{msg, opts}` + `translate_error/1` pattern pyview already admires.

## Form state (bound/unbound, touched/used, attempted values)

- **Attempted values are sacred**: GOV.UK "show them the page again, with the form fields as the user filled them in"; NN/g "respect user effort". Re-render from the *raw params*, not from the parsed model — a rejected "12x" must stay "12x".
- **Used/touched gating**: LiveView 0.20 client (bundled in pyview) marks inputs `phx-has-focused` on focus and the form `phx-has-submitted` on submit; `maybeHideFeedback` adds `phx-no-feedback` to every element whose `phx-feedback-for` names an input that has neither, and `showError` removes it when the input's change event lands (`app.js` lines 2654–2714, 5574). LiveView 1.0+ replaced this with `_unused_<name>` params sent alongside untouched inputs and `Phoenix.Component.used_input?/1` (`phoenix_component.ex:1758`): a field is used unless `_unused_<field>` is present in params. Known wart (issue #3620): hidden inputs driven by JS libraries never get marked unused. pyview's changeset today approximates this with "key in changes"; the correct model is a server-side `used: set[str]` filled from `_target` (0.20) or from the absence of `_unused_` (1.0) plus a `submitted: bool` that flips everything to used.
- **Submit attempted flag**: after the first submit *all* errors show (summary + inline), regardless of touch state; this is the GOV.UK behaviour and what Baymard/NN/g assume.
- **Focus preservation**: the LiveView client "will never overwrite the input's current value" of the focused input and restores the last focused input after `phx-submit`; so server re-renders that add/remove error paragraphs are safe as long as the input's `id` is stable. Changing `aria-describedby` on the focused input is fine (attributes are patched).
- **Positive state**: Baymard's checkmark. Represent as `field.state ∈ {"untouched", "valid", "invalid"}` so a renderer can add `govuk-input--error`-style or `is-valid` classes; GOV.UK deliberately does *not* show success ticks (unverified rationale, but none of their components have one).

## Rendering & customization & styling

Reference field markup, assembled from `input/template.njk`, `label`, `hint`, `error-message` (all verified):

```html
<div class="govuk-form-group govuk-form-group--error">
  <label class="govuk-label" for="user-age">Age</label>
  <div id="user-age-hint" class="govuk-hint">For example, 34</div>
  <p id="user-age-error" class="govuk-error-message">
    <span class="govuk-visually-hidden">Error:</span> Age must be a whole number
  </p>
  <input class="govuk-input govuk-input--error govuk-input--width-3" id="user-age" name="user[age]"
         type="text" inputmode="numeric" value="12x" aria-describedby="user-age-hint user-age-error">
</div>
```

Notes: `id` = `params.id or params.name` (pyview should slugify `user[age]` → `user_age`); `aria-describedby` is built as `describedBy + " " + hintId`, then `+ " " + errorId` — **hint before error**; GOV.UK does *not* emit `aria-invalid` (they rely on the "Error:" text); WAI and WCAG technique ARIA21 recommend adding `aria-invalid="true"`, and it is harmless, so pyview should add it. Grouped controls (radios, checkboxes, date-input) put `aria-describedby` on the `<fieldset>` (`fieldset/template.njk` accepts `describedBy`), never on individual radios, and the error message sits inside the fieldset after the legend/hint.

Character count (`character-count.mjs`): the visible count message is duplicated in a visually-hidden `aria-live="polite"` element updated only after 500 ms of no typing (`lastInputTimestamp`), with `data-threshold` to stay silent until e.g. 75 %; on over-limit the count message gets `govuk-error-message` and the textarea `govuk-textarea--error`. This is the canonical "live but polite" pattern for any per-keystroke feedback pyview offers.

Customisation surface GOV.UK exposes per macro (`params`): `id, name, type, value, label{text|html,classes,isPageHeading}, hint{text|html}, errorMessage{text|html,visuallyHiddenText}, describedBy, classes, formGroup{classes,attributes,beforeInput,afterInput}, prefix/suffix, autocomplete, inputmode, spellcheck, pattern, disabled, attributes{}`. This list is a good minimum for pyview's per-field render options; the `attributes` escape hatch (arbitrary HTML attrs, via `govukAttributes`) is what keeps designers from forking the template.

## Nested / dynamic / conditional

- **Grouping**: WAI — every radio/checkbox group and every repeated address block is a `<fieldset><legend>`; when legends may not be read, prefix the first label with visually-hidden context ("<span class=visuallyhidden>Shipping </span>Name"). GOV.UK's radios support `conditional` reveal: the revealed panel is `<div class="govuk-radios__conditional" id="conditional-x">` and the radio gets `aria-controls="conditional-x"` + `aria-expanded` (radios.mjs; unverified line numbers, but the attribute names are in the docs).
- **Conditional questions**: GOV.UK's stronger recommendation is *one thing per page* — branch by navigation, not by show/hide; when you must reveal, keep the revealed inputs inside the same fieldset so errors and `aria-describedby` still resolve.
- **Dynamic rows** (synthesis of WAI notifications + WCAG 4.1.3; no single source has a rows recipe): (a) each row is a `fieldset` with legend "Item {n}"; (b) after "Add", move focus to the new row's first input and announce "Item 3 added" via `role="status"`; (c) after "Remove", move focus to the next row's remove button or the "Add" button and announce "Item 2 removed"; (d) keep row `id`s stable (use a per-row key, not index) so LiveView's DOM patching keeps focus and so summary links stay valid; (e) summary links target the first input of the row that errors; (f) a whole-row error (e.g. duplicate) is an error message inside the fieldset after the legend.
- **Multi-page**: WAI multi-page tutorial and GOV.UK: number/announce steps, repeat the error summary per page, and a final "Check your answers" page for 3.3.4.

## DX highlights with real code (cite each)

1. GOV.UK `govukInput` threads `describedBy` and derives ids (`input/template.njk`, quoted above): `{% set hintId = id + '-hint' %}{% set describedBy = describedBy + ' ' + hintId if describedBy else hintId %}` — one convention, zero configuration.
2. Error summary auto-focus and label-aware scrolling (`error-summary.mjs`, quoted above) — link `href="#id"` is all the author writes.
3. LiveView 1.x used-input gating (`guides/client/form-bindings.md`):
   ```elixir
   def input(%{field: %Phoenix.HTML.FormField{} = field} = assigns) do
     errors = if Phoenix.Component.used_input?(field), do: field.errors, else: []
   ```
4. LiveView per-input timing (`guides/client/bindings.md`): `<input name="user[email]" phx-debounce="blur"/> <input name="user[username]" phx-debounce="2000"/>` — timing is a per-input attribute, not a form-wide mode.
5. WAI live-region feedback (`notifications.md`): `<span id="username_feedback" aria-live="polite"></span>` updated as the user types; on-focus-change variant uses `aria-live="assertive"` — the tutorial itself shows both "as you type" and "on blur" as legitimate.
6. WAI required marking (`validation.md`): `<label for="name">Name (required): </label><input … required aria-required="true">` — text "(required)" in the label for everyone, attribute for AT; GOV.UK instead marks *optional* fields "(optional)" and never uses asterisks.

## Pain points & criticisms (cite)

- GOV.UK's "submit-only, no `required`" stance is admitted to be under-researched ("we'd like to expand the guidance… whether not adding `required` causes problems for screen reader users").
- Live validation (Silver's 9 issues; Baymard's "premature validation"; Smashing "never bulletproof") — most real-world failures are in *timing*, not in message text.
- Disabled submit buttons: not focusable, unexplained, high abandonment (Silver, Smashing via snippets).
- `role="alert"` + focus race: GOV.UK had to move `role="alert"` to a child element to stop screen readers dropping the announcement when focus moves (comment in template). Any pyview summary must copy this.
- LiveView `_unused_` heuristic breaks for JS-managed hidden inputs (phoenix_live_view #3620) and composite inputs (#2968) — a server-side `used` set that the developer can override is safer than trusting the client.
- Pydantic default messages are developer-facing ("unable to parse string as an integer", "Input should be 'a', 'b' or 'c'") and expose `loc` tuples, not labels — they must never reach users unmapped.

## Lessons for pyview — steal / adapt / avoid

**Steal**
- The GOV.UK form-group contract verbatim: `{id}-hint`, `{id}-error`, `aria-describedby="[extra] {id}-hint {id}-error"`, visually-hidden "Error:" prefix, error class on group + control, label `for`, fieldset+legend with `aria-describedby` on the fieldset for groups. Ship it as the *default renderer* with a class-map (`FormTheme`) so Tailwind/Bootstrap themes just swap class strings.
- Error summary component: `<div role="alert">` child, heading, `<a href="#{id}">` per error, `phx-mounted`/hook or a tiny JS command to focus it after submit, label/legend-aware scrolling; add "Error: " to the `<title>` via a `page_title` assign.
- Ecto-style error tuples `(msg_template, params)` + `translate_error` hook; a `MESSAGE_MAP: dict[str, str]` keyed by pydantic `type` with GOV.UK-quality defaults and `{label}`/`ctx` interpolation.
- Per-input timing via `phx-debounce` emitted by the renderer according to a `ValidationPolicy`.

**Adapt (recommended default policy)**
- `policy="blur"` (default): renderer emits `phx-debounce="blur"` on text-like inputs, nothing on radios/checkboxes/selects (they validate on submit or on change of that group only); server shows inline errors only for `used` fields; errors disappear the moment the field validates; on `phx-submit` mark everything used, render summary + inline, and push focus to the summary. `policy="submit"` (GOV.UK strict): no `phx-change` errors at all, only the submit pass. `policy="eager"`: `phx-debounce="300"` with errors as you type — opt-in for things like username availability, always with `aria-live="polite"` and a 500 ms quiet period like character-count.
- `used` tracking on the server: from `_target` on the 0.20 client, from `_unused_` on 1.0; expose `form.mark_used(...)`/`form.submitted` so developers can override for JS-driven inputs.
- Emit `aria-invalid="true"`, `autocomplete=`, `inputmode=` from field metadata (`Field(json_schema_extra={"autocomplete": "email"})` or an `Annotated` marker); mark optional fields "(optional)" rather than required ones with `*`; default `novalidate` on the form and no HTML `required` (configurable — GOV.UK's reasoning is about consistency, not a WCAG rule).
- Lenient pre-parse (strip whitespace, ignore separators in numbers/codes, month names) before pydantic; keep raw params for re-render.
- List rows: stable per-row keys, fieldset+legend per row, `role="status"` announcements and focus moves on add/remove, summary links to first input in the row.

**Avoid**
- Errors on first keystroke / while typing by default; validating checkbox groups or date parts on blur.
- Disabled submit until valid; instead disable *during* submit with `phx-disable-with`.
- Placeholders as labels/hints; `<input type="number">` by default; links in hint text.
- Leaking pydantic wording or `loc` paths to users; clearing invalid values on re-render; showing only a summary or only inline (must be both).

## Sources (URLs / repo paths actually read)

- govuk-design-system: `src/patterns/validation/index.md`, `src/patterns/question-pages/index.md`, `src/components/error-summary/index.md`, `src/components/error-message/index.md`, `src/components/text-input/index.md` (grep), `src/components/date-input/index.md` (grep), `src/components/character-count/index.md` (grep).
- govuk-frontend 6.5.0: `packages/govuk-frontend/src/govuk/components/{error-summary/template.njk, error-summary/error-summary.mjs, error-message/template.njk, input/template.njk, label/template.njk, hint/template.njk, fieldset/template.njk, date-input/template.njk (grep), character-count/template.njk + character-count.mjs (grep)}`.
- w3c/wai-tutorials `content/forms/{validation,notifications,labels,grouping,instructions}.md`.
- w3c/wcag `understanding/20/{error-identification,error-suggestion,labels-or-instructions,error-prevention-legal-financial-data}.html`, `understanding/21/{status-messages,identify-input-purpose}.html`, `understanding/22/{redundant-entry,accessible-authentication-minimum}.html` (intent paragraphs).
- phoenix_live_view 1.2.11: `lib/phoenix_component.ex` (`used_input?/1`), `guides/client/form-bindings.md`, `guides/client/bindings.md`; pyview `pyview/static/assets/app.js` (0.20.17 client: `phx-feedback-for`, `phx-no-feedback`, `phx-has-focused`, `phx-has-submitted`, `showError`, `maybeHideFeedback`).
- Via WebSearch snippets only (sites blocked): https://baymard.com/blog/inline-form-validation ; https://www.lukew.com/ff/entry.asp?883= ; https://www.nngroup.com/articles/errors-forms-design-guidelines/ ; https://www.nngroup.com/articles/error-message-guidelines/ ; https://adamsilver.io/blog/the-problem-with-live-validation-and-what-to-do-instead/ ; https://adamsilver.io/blog/the-problem-with-disabled-buttons-and-what-to-do-instead/ ; https://www.smashingmagazine.com/2022/09/inline-validation-web-forms-ux/ ; https://www.smashingmagazine.com/2018/10/form-design-patterns-excerpt-a-registration-form/ ; https://github.com/phoenixframework/phoenix_live_view/issues/3620 ; https://github.com/phoenixframework/phoenix_live_view/issues/2968.
