# Cross-Cutting Best Practices for Form Libraries (for a pyview pydantic/dataclass form library)

> Research method note: the network egress proxy blocked direct fetches of nngroup.com, baymard.com, smashingmagazine.com, alistapart.com, design-system.service.gov.uk, w3.org, developer.mozilla.org, web.dev, hexdocs.pm, adrianroselli.com and cheatsheetseries.owasp.org. Where possible I read the **primary source files on GitHub** instead (GOV.UK Design System markdown, govuk-frontend JS, W3C WCAG "Understanding" sources, OWASP cheat sheet markdown, Phoenix/LiveView/Ecto/phoenix_html source + docs, Rails guides, Django docs, pydantic docs, React Aria docs, MOJ Frontend JS, Rack source). Claims from NN/g, Baymard, Smashing, A List Apart, web.dev, Adrian Roselli, Tailwind and shadcn come from **search-engine result summaries** only and are flagged "(search summary)". Treat those as lower-confidence than the GitHub-sourced items.

---

## 1. Validation / error-display timing UX

### Takeaway
The evidence converges on: **never show an error while the user is still typing into a field that was fine ("punish late"), but clear/update an existing error immediately as the user fixes it ("reward early")**, and always show everything on submit with an error summary. The main disagreement is whether "late" means *on blur* (NN/g, Baymard, Wroblewski, React Aria default) or *only on submit / next page* (GOV.UK). A library should implement a per-field state machine (pristine → used/blurred → errored) and make the policy configurable, defaulting to blur-then-live-correction.

### Cited Findings
- **Wroblewski's 2009 inline validation study** (published in A List Apart): the best-performing inline-validation variant, compared with a control that validated only on submit, produced a **22% increase in success rates, 22% decrease in errors, 31% increase in satisfaction, 42% decrease in completion times and 47% fewer eye fixations**; the study measured success, errors, completion time, satisfaction and eye-tracking metrics per variant — [LukeW](https://www.lukew.com/ff/entry.asp?883=); [A List Apart](https://alistapart.com/article/inline-validation-in-web-forms/) (search summary; article itself not fetchable).
- **"Reward early, punish late" (Mihael Konjević)**: if the user is editing a field that was in an *invalid* state, validate *during* entry so the error is removed and success confirmed as soon as possible (reward early); if the field was *valid* and is being edited, wait until the user moves to the next field before flagging errors (punish late). Implementing it requires tracking each field's state and contents and thresholds for when to start validating — [Konjević, "Inline validation in forms — designing the experience"](https://medium.com/wdstack/inline-validation-in-forms-designing-the-experience-123fb34088ce); [Smashing Magazine, "A Complete Guide To Live Validation UX" (2022)](https://www.smashingmagazine.com/2022/09/inline-validation-web-forms-ux/) (search summary).
- **Baymard**: fields shouldn't be prematurely validated; error messages should be removed as soon as input is corrected; "positive inline validation" should indicate everything is OK. Premature validation (error shown before the user finished the field) annoys users and makes them hunt for non-existent errors and contributed to checkout abandonment in testing; recommendation is to flag errors after the user finishes a field (on blur), not while typing. Reported that 31% of sites don't provide live inline validation — [Baymard, "Usability Testing of Inline Form Validation"](https://baymard.com/blog/inline-form-validation) (search summary).
- **Baymard**: sites should retain even sensitive credit-card field data after validation errors (title: "34% Don't") — [Baymard](https://baymard.com/research-articles/preserve-card-details-on-error) (search summary; title only).
- **NN/g**: "Ideally, all validation should be inline; that is, as soon as the user has finished filling in a field, an indicator should appear nearby if the field contains an error"; messages should say how to fix, not just identify, the problem; **don't use validation summaries as the only indication of an error** — [NN/g, "10 Design Guidelines for Reporting Errors in Forms"](https://www.nngroup.com/articles/errors-forms-design-guidelines/) (search summary). NN/g's hostile-patterns guidance: wait until the user moves from a field before displaying an error; don't pile on multiple indicators (asterisk + red outline + message) — [NN/g, "Hostile Patterns in Error Messages"](https://www.nngroup.com/articles/hostile-error-messages/) (search summary).
- **GOV.UK (dissenting/stricter position)**: "Do not validate when the user moves away from a field. Wait until they try to move to the next part of the service"; inline validation should only be added "if your user research shows that, on balance, it solves more problems for users than it causes." On error: "show an Error summary component at the top of the page, and move keyboard focus to it" plus Error message components next to each field; add "Error: " to the start of the page `<title>`; "You'll always need to carry out server side validation, even if you use client side validation." — [GOV.UK Design System, Validation pattern (source)](https://raw.githubusercontent.com/alphagov/govuk-design-system/main/src/patterns/validation/index.md).
- **GOV.UK error summary**: "Always show an error summary when there is a validation error, even if there's only one"; heading "There is a problem"; messages in the summary must be "worded the same as those which appear next to the inputs with errors"; placed at the top of `main`, above the `<h1>` — [GOV.UK Error summary (source)](https://raw.githubusercontent.com/alphagov/govuk-design-system/main/src/components/error-summary/index.md).
- **React Aria default timing**: "By default, validation errors are displayed after the value is committed (e.g. on blur), or when the form is submitted." Realtime validation (e.g., password rules) is opt-in by making the field controlled and setting `isInvalid`/`errorMessage`. **Server errors** passed via `<Form validationErrors={...}>` "are displayed as soon as the `validationErrors` prop is set, and cleared after the user modifies each field's value." — [React Aria Forms guide (source)](https://raw.githubusercontent.com/adobe/react-spectrum/main/packages/dev/s2-docs/pages/react-aria/forms.mdx).
- **Phoenix LiveView's server-driven mechanism**: on every `phx-change` the client serializes the whole form and, for each input that has not been focused or submitted, appends an extra empty param prefixed `_unused_`; the server uses `Phoenix.Component.used_input?/1` to show only errors for fields the user "focused, interacted with, or submitted": `errors = if Phoenix.Component.used_input?(field), do: field.errors, else: []`. Opt out with `phx-no-unused-field` — [LiveView form bindings guide (source)](https://raw.githubusercontent.com/phoenixframework/phoenix_live_view/main/guides/client/form-bindings.md); [LiveView `view.ts` serializeForm](https://raw.githubusercontent.com/phoenixframework/phoenix_live_view/main/assets/js/phoenix_live_view/view.ts). In the JS, "used" = `PHX_HAS_FOCUSED || PHX_HAS_SUBMITTED || phx-no-unused-field`, i.e., **focus**, not blur, marks a field as used — [view.ts](https://raw.githubusercontent.com/phoenixframework/phoenix_live_view/main/assets/js/phoenix_live_view/view.ts).
- The change payload also carries `_target` = the keyspace of the input that triggered the event, e.g. `%{"_target" => ["user", "username"], "user" => %{"username" => "Name"}}` — [LiveView form bindings (source)](https://raw.githubusercontent.com/phoenixframework/phoenix_live_view/main/guides/client/form-bindings.md).
- **CSS-level timing**: `:user-invalid`/`:user-valid` match a control only "after a user has significantly interacted with the input", replacing stateful code that tracked initial value, focus state, extent of changes and validity to add a class — [web.dev, ":user-valid and :user-invalid"](https://web.dev/articles/user-valid-and-user-invalid-pseudo-classes) (search summary).

### Inferences
- **Recommended default policy for pyview** (server-authoritative, LiveView-style). Per field track `used` (focused/blurred), `had_error` (error was visible on last render), and form-level `submitted`:
  ```python
  def visible_errors(field, form, event):
      if form.submitted:                 # after submit attempt: show everything
          return field.errors
      if not field.used:                 # pristine: never nag
          return []
      if field.had_error:                # reward early: live-update / clear as they fix it
          return field.errors
      if event.target == field.path and not event.is_blur:
          return []                      # punish late: don't flag a previously-valid field mid-typing
      return field.errors                # after blur
  ```
  Because LiveView's `_unused_` marks a field "used" as soon as it is focused, a pure `used_input?` policy shows errors *while typing* unless the input is debounced to blur. A pyview library should therefore either track blur separately (e.g., a client hook or `phx-blur` event) or combine `_target` + prior error state as above. (Phoenix also offers `phx-debounce="blur"` for this, per its bindings docs — from prior knowledge, not re-verified in this session.)
- Make the policy a per-form setting: `"blur"` (default; NN/g/Baymard/Wroblewski/React Aria), `"submit"` (GOV.UK style; best for multi-page transactional services), `"live"` (for password-rule checklists / availability checks).
- Always pair inline errors with an error summary **after submit** (GOV.UK + NN/g agree the summary must not be the *only* indicator). Summary text must equal the inline text, so render both from the same error object.
- Server errors (e.g., "email already taken") should be cleared when the user edits that field, as React Aria does, rather than persisting until the next submit.
- Never disable the submit button as the error-prevention mechanism; let submit trigger the summary (consistent with the GOV.UK pattern of validating on submit; the Smashing 2022 article also discusses disabled buttons but I could not read its exact wording).

### Gaps
- Could not read the Wroblewski article directly; variant-level details (e.g., that the "after"/on-blur variant beat "while typing" and "before-and-while" variants, and that live feedback helped for username/password fields) are from memory and unverified.
- Could not read Smashing's 2022 article text directly (quotes about disabled buttons, layout shift).
- No primary quantitative study found comparing "on blur" vs "on submit only" head-to-head for government-style multi-page forms; GOV.UK's position is based on its own (not publicly quantified here) user research.

---

## 2. Accessibility of forms

### Takeaway
The accessible baseline every generated field must hit: a programmatic `<label for>`; hint + error text linked via `aria-describedby`; `aria-invalid="true"` on invalid controls; errors expressed in **text** (not only color) with a visually-hidden "Error:" prefix; groups (radios, checkboxes, date parts, nested sub-forms, repeated items) wrapped in `fieldset`/`legend`; an error summary that receives focus after a failed submit and links to the first control of each group; `autocomplete` tokens for personal data; and explicit focus management + announcements when repeated items are added/removed.

### Cited Findings
**WCAG 2.2 criteria**
- **3.3.1 Error Identification (A)**: "Users are aware that an error has occurred and can determine what is wrong"; "The error must be indicated in text"; must include "information about the nature of the error, including the identity of the item in error"; color/icons are fine only "in addition to the text description" — [WCAG Understanding 3.3.1 (source)](https://raw.githubusercontent.com/w3c/wcag/main/understanding/20/error-identification.html).
- **3.3.3 Error Suggestion (AA)**: intent is to "ensure that users receive appropriate suggestions for correction of an input error if it is possible"; example: user types "12" in a month field → suggest "Choose one of: January, February, March..." or "Do you mean December?" — [WCAG Understanding 3.3.3 (source)](https://raw.githubusercontent.com/w3c/wcag/main/understanding/20/error-suggestion.html).
- **3.3.7 Redundant Entry (A, new in 2.2)**: "Don't ask for the same information twice in the same activity"; previously entered info must be auto-populated or "available to select" (select from a drop-down, copy from the page, or "tick a checkbox to populate inputs with the same values as previously entered", e.g. billing = delivery address). Exceptions: essential re-entry (memory games), security (password re-entry), and when previous info is no longer valid — [WCAG Understanding 3.3.7 (source)](https://raw.githubusercontent.com/w3c/wcag/main/understanding/22/redundant-entry.html).
- **3.3.8 Accessible Authentication (Minimum) (AA, new in 2.2)**: username/password inputs are acceptable if the author "enables the user agent (browser) and any third-party password managers to fill in the fields"; if password managers are blocked "or users are prevented from copy and paste operations... the page would fail this criterion unless an alternative is provided"; meeting 1.3.5 Identify Input Purpose (autocomplete) with a correct accessible name enables this — [WCAG Understanding 3.3.8 (source)](https://raw.githubusercontent.com/w3c/wcag/main/understanding/22/accessible-authentication-minimum.html).
- **Status Messages**: a status message "provides information to the user on the success or results of an action, on the waiting state of an application, on the progress of a process, or on the existence of errors" and is "not delivered via a change in context"; listed examples include "5 errors on page" after an incomplete submission and "5 items" after adding to a cart — implemented with `role="status"`, `role="alert"` / live regions — [WCAG Understanding Status Messages (source)](https://raw.githubusercontent.com/w3c/wcag/main/understanding/21/status-messages.html). (This is SC 4.1.3 in WCAG 2.1/2.2; the summarizer of the `main`-branch file reported a different number, so verify numbering against the published WCAG 2.2 TR.)
- **ARIA21 technique**: use `aria-invalid` to flag fields in error together with `aria-describedby` pointing at the error text — [W3C ARIA21](https://www.w3.org/WAI/WCAG21/Techniques/aria/ARIA21); [W3C WAI Forms tutorial – User Notification](https://www.w3.org/WAI/tutorials/forms/notifications/) (search summary; w3.org not fetchable).

**GOV.UK Design System (research-backed component guidance)**
- Error message placement: "put the message in red after the question text and hint text" with "a red border to visually connect the message and the question"; the component "includes a hidden 'Error:' before the error message" for screen-reader users; "Do not clear any form fields when showing the Error message component. Keep both passing and failing answers." — [GOV.UK Error message (source)](https://raw.githubusercontent.com/alphagov/govuk-design-system/main/src/components/error-message/index.md).
- Wording: avoid generic "An error occurred" / "Answer the question" / "Select an option"; avoid "forbidden", "illegal", "you forgot", "prohibited", "please", "sorry", "valid"/"invalid"; "Describe what has happened and tell them how to fix it" — [GOV.UK Error message (source)](https://raw.githubusercontent.com/alphagov/govuk-design-system/main/src/components/error-message/index.md).
- Error summary links: single fields link directly to the input; for multi-part fields (date input) "Link to the first field that contains an error. If you do not know which field contains an error, link to the first field"; for radios/checkboxes "Link to the first radio or checkbox" — [GOV.UK Error summary (source)](https://raw.githubusercontent.com/alphagov/govuk-design-system/main/src/components/error-summary/index.md).
- govuk-frontend's error-summary JS focuses the summary on load (unless `disableAutoFocus`), and when a summary link is clicked it finds "The `<legend>` associated with the closest `<fieldset>` ancestor, as long as the top of it is no more than half a viewport height away from the bottom of the input", else the `<label for>`, else the enclosing `<label>`; it scrolls that legend/label into view *before* focusing the input with `preventScroll: true` so the question context is visible and announced — [govuk-frontend error-summary.mjs](https://raw.githubusercontent.com/alphagov/govuk-frontend/main/packages/govuk-frontend/src/govuk/components/error-summary/error-summary.mjs).
- GOV.UK recommends turning off HTML5 validation (`novalidate`, no `required`) because browser messages' style, placement and content can't be made consistent — [GOV.UK Validation (source)](https://raw.githubusercontent.com/alphagov/govuk-design-system/main/src/patterns/validation/index.md).

**`aria-errormessage` vs `aria-describedby`**
- `aria-errormessage` is only conveyed when `aria-invalid="true"`; Roselli's testing found strong support in JAWS, NVDA and iOS VoiceOver but limited elsewhere; `aria-describedby` remains the broadly-supported generic mechanism — [Adrian Roselli, "Exposing Field Errors" (2023)](http://adrianroselli.com/2023/04/exposing-field-errors.html) (search summary). A 2024 review: "Support for aria-errormessage is getting better, but still not there yet" — [Cerovac (2024)](https://cerovac.com/a11y/2024/06/support-for-aria-errormessage-is-getting-better-but-still-not-there-yet/) (title/search summary). There is an open ARIA WG issue proposing deprecating `aria-errormessage` in favor of `aria-describedby` — [w3c/aria #2048](https://github.com/w3c/aria/issues/2048).

**Framework precedents**
- **Django 5.0** auto-adds `aria-describedby` linking help text to its input (on the `<fieldset>` if the widget is rendered in one, otherwise on the input) and `aria-invalid="true"` on invalid fields — [Django 5.0 release notes](https://docs.djangoproject.com/en/6.1/releases/5.0/) (search summary); [Django ticket #32819](https://code.djangoproject.com/ticket/32819).
- **React Aria** `validationBehavior="native"` (default) uses constraint validation and "invalid fields block forms from being submitted"; `"aria"` "will only mark the field as required and invalid for assistive technologies, and will not prevent form submission" — [React Aria Forms (source)](https://raw.githubusercontent.com/adobe/react-spectrum/main/packages/dev/s2-docs/pages/react-aria/forms.mdx).

**Repeated items (add/remove) — MOJ "Add another" component (UK Ministry of Justice design system)**
- Uses a `<template>` whose `name`/`id` attributes contain `%index%` placeholders; after add *or* remove it calls `updateAllItems()` which re-indexes names/ids and **re-numbers legends and error messages**; after adding it focuses the **new item's fieldset** (`setTimeout(() => setFocus($fieldset), 100)`); after removal `focusItemAfterRemoval()` first focuses a neutral target then the target item on the next frame "to allow screen readers to recalculate accessible names"; legends are **replaced, not mutated** (`$legend.replaceWith($replacementLegend)`) so AT recomputes the fieldset name. No `aria-live` region is used — [moj-frontend add-another.mjs](https://raw.githubusercontent.com/ministryofjustice/moj-frontend/main/src/moj/components/add-another/add-another.mjs).
- Remove buttons should carry item context in their accessible name ("Remove address 2", not just "Remove") — [search summary of accessibility guidance](https://gitlab.com/gitlab-org/gitlab-services/design.gitlab.com/-/issues/3048) (weak source; GitLab design-system issue).

### Inferences
- **Canonical single-field markup** a generator should emit (GOV.UK-style ordering: label → hint → error → control):
  ```html
  <div class="field" data-field="user.email" data-invalid data-used>
    <label for="user_email">Email address</label>
    <p id="user_email-hint" class="hint">We'll send your receipt here</p>
    <p id="user_email-error" class="error-message">
      <span class="visually-hidden">Error:</span>
      Enter an email address in the correct format, like name@example.com
    </p>
    <input id="user_email" name="user[email]" type="email" autocomplete="email"
           value="bob@"                                   <!-- raw input preserved -->
           aria-describedby="user_email-hint user_email-error"
           aria-invalid="true">
  </div>
  ```
  Use `aria-describedby` for both hint and error (robust support); optionally also emit `aria-errormessage` since it's harmless when `aria-invalid` is set, but don't rely on it alone.
- **Groups and nested sub-forms**: radios, checkbox sets, multi-part dates, and every nested model / repeated item → `<fieldset>` + `<legend>`, with the group's hint/error on the fieldset's `aria-describedby`; the error summary links to the **first control's id** in the group:
  ```html
  <fieldset aria-describedby="order_addresses_1-error">
    <legend>Address 2 of 3</legend>
    <p id="order_addresses_1-error" class="error-message"><span class="visually-hidden">Error:</span> Enter a postcode</p>
    <label for="order_addresses_1_street">Street</label>
    <input id="order_addresses_1_street" name="order[addresses][1][street]" autocomplete="shipping address-line1">
    ...
    <button type="button" name="order[addresses_drop][]" value="1">Remove address 2</button>
  </fieldset>
  ```
  Nested fieldsets are legal but announcement gets verbose; for deep models prefer a fieldset per logical group rather than per Python class (the WAI grouping tutorial could not be fetched to confirm specific nesting guidance).
- **Error summary** (render only after a submit attempt, focus it on arrival, prefix `<title>` with "Error: "):
  ```html
  <div class="error-summary" id="error-summary" tabindex="-1" role="alert" aria-labelledby="error-summary-title">
    <h2 id="error-summary-title">There is a problem</h2>
    <ul>
      <li><a href="#user_email">Enter an email address in the correct format, like name@example.com</a></li>
      <li><a href="#order_addresses_1_street">Enter a postcode</a></li>
    </ul>
  </div>
  ```
  In LiveView there is no page load after submit, so focus must be moved explicitly (e.g., a hook or `JS.focus` on the summary when the submit handler returns errors); linking behaviour should mimic govuk-frontend (scroll legend/label into view, then focus input).
- **Add/remove repeated items**: after add → focus the new item's first input (or its fieldset/legend); after remove → focus the next item's legend/first input, or the "Add" button if the list became empty; update "Item N of M" legends; optionally announce via a pre-existing polite live region ("Address 2 removed. 2 addresses."). Because LiveView re-renders the DOM, stable DOM ids per item (not index-based) are needed so focus isn't lost when indices shift.
- **Autocomplete**: map common field names/types to HTML `autocomplete` tokens (`email`, `name`, `given-name`, `tel`, `postal-code`, `street-address`, `current-password`, `new-password`, `one-time-code`) — needed for 1.3.5 and 3.3.8; never set `autocomplete="off"` on credentials and never block paste.
- **Required indicators**: GOV.UK's approach (mark optional fields "(optional)" rather than asterisking required ones) vs Baymard's finding that checkouts should mark *both* required and optional explicitly ([Baymard, "Mark both required and optional fields explicitly (Only 14% do so)"](https://baymard.com/blog/required-optional-form-fields), title only) — make it a theme choice; derive required-ness from the schema.
- **Redundant entry**: multi-step wizards should carry values forward (server state) and support "same as X" checkboxes; this is naturally done in LiveView by keeping the model in socket state.

### Gaps
- Could not fetch the W3C WAI forms tutorials (labels, grouping, notifications, validation) or MDN directly; guidance on nested fieldsets and on `aria-live` vs focus for added rows is from established practice rather than a fetched source.
- No authoritative primary source found that prescribes focus behaviour after removing a repeated item beyond the MOJ implementation.
- Exact GOV.UK error-summary markup (role/tabindex placement in current govuk-frontend Nunjucks template) not verified; the snippet above is illustrative.

---

## 3. Encoding nested and repeated data in HTML form field names

### Takeaway
For a LiveView-style system whose JS client serializes with `FormData` → `URLSearchParams` and reports the triggering field as a keyspace list (`_target`), **bracket notation with explicit integer indices (`order[items][0][sku]`) is the right choice**: it round-trips unambiguously to nested dicts, matches Phoenix/Rails/PHP tooling, and aligns with `_target`. Lists of objects should be **index-keyed maps** (not `[]`-appended arrays), with explicit "sort/drop" control params, a hidden empty input to express "empty list", hidden `false` for checkboxes, hidden `""` for multi-selects, and server-side caps on indices and nesting.

### Cited Findings
**Bracket notation (Rails/Rack/PHP/Phoenix)**
- `name="person[name]"` → `{"person"=>{"name"=>...}}`; `person[address][city]` → nested hash; names ending in `[]` build arrays (`person[phone_number][]`); arrays of hashes via `person[addresses][][line1]` — [Rails Form Helpers guide (source)](https://raw.githubusercontent.com/rails/rails/main/guides/source/form_helpers.md).
- Rack decides array-of-hash boundaries heuristically: for `x[][y]` it inspects the **last element of the array** — if it is a hash (that doesn't already have that key) it adds to it, otherwise it starts a new hash — [Rack `query_parser.rb`](https://raw.githubusercontent.com/rack/rack/main/lib/rack/query_parser.rb). (This is why `[]`-style arrays of objects are fragile: an item with a missing/unchecked field can merge into the neighbour.)
- Rails lets you key by record id instead of position: `fields_for address, index: address.id` → `name="person[address][#{address.id}][city]"`, so "you can tell which Address records should be modified" — [Rails guide (source)](https://raw.githubusercontent.com/rails/rails/main/guides/source/form_helpers.md).
- Rails nested attributes use `person[addresses_attributes][0][_destroy]`; "If the associated object is already saved, `fields_for` autogenerates a hidden input with the `id` of the saved record"; `reject_if: :all_blank` skips entirely-blank rows — [Rails guide (source)](https://raw.githubusercontent.com/rails/rails/main/guides/source/form_helpers.md).

**Phoenix / Ecto (the closest analogue to pyview)**
- `inputs_for` renders nested fields and "By default it will add the necessary hidden input fields for tracking ids of Ecto associations"; there is also a hidden `_persistent_id` field (suppressible with `skip_persistent_id`) — [LiveView form bindings (source)](https://raw.githubusercontent.com/phoenixframework/phoenix_live_view/main/guides/client/form-bindings.md); [phoenix_component.ex](https://raw.githubusercontent.com/phoenixframework/phoenix_live_view/main/lib/phoenix_component.ex).
- Ecto receives nested lists as **index-keyed maps**: `%{"addresses" => %{0 => %{...,"id" => 1}, 1 => %{...}}}` — [Ecto.Changeset (source)](https://raw.githubusercontent.com/elixir-ecto/ecto/master/lib/ecto/changeset.ex).
- `cast_assoc`/`cast_embed` accept `:sort_param` ("parameter name which keeps a list of indexes to sort from the relation parameters") and `:drop_param` ("list of indexes to drop") — [Ecto.Changeset (source)](https://raw.githubusercontent.com/elixir-ecto/ecto/master/lib/ecto/changeset.ex).
- Phoenix's documented add/remove recipe (verbatim pieces):
  ```heex
  <button type="button" name="mailing_list[emails_drop][]" value={ef.index}
          phx-click={JS.dispatch("change")}>delete</button>

  <input type="hidden" name="mailing_list[emails_drop][]" />

  <button type="button" name="mailing_list[emails_sort][]" value="new"
          phx-click={JS.dispatch("change")}>add more</button>
  ```
  The button "must have `type="button"` to prevent it from submitting the form"; the empty hidden drop input "is required whenever dropping associations" to "ensure that all children are deleted when saving a form where the user dropped all entries"; "Ecto will treat unknown sort params as new children and build a new child" — [phoenix_component.ex `inputs_for` docs](https://raw.githubusercontent.com/phoenixframework/phoenix_live_view/main/lib/phoenix_component.ex).
- LiveView's client serializer: `new FormData(form)`, **removes `File` entries** (uploads go through a separate channel), copies into `URLSearchParams`, injects the submitter's `name`/`value` as a temporary hidden input, and appends `_unused_`-prefixed keys for untouched inputs — [view.ts](https://raw.githubusercontent.com/phoenixframework/phoenix_live_view/main/assets/js/phoenix_live_view/view.ts). `_target` gives the keyspace list, e.g. `["user","username"]` — [form bindings (source)](https://raw.githubusercontent.com/phoenixframework/phoenix_live_view/main/guides/client/form-bindings.md).
- Phoenix's generated checkbox component emits `<input type="hidden" name={@name} value="false" .../>` before the checkbox — [Phoenix core_components template](https://raw.githubusercontent.com/phoenixframework/phoenix/main/installer/templates/phx_web/components/core_components.ex.eex).

**Unchecked checkboxes / multi-select**
- "According to the HTML specification unchecked checkboxes submit no value"; Rails emits `<input name="biography" type="hidden" value="0">` then `<input type="checkbox" value="1" name="biography">`: "If the checkbox is unchecked only the hidden input is submitted. If it is checked then both are submitted but the value submitted by the checkbox takes precedence." `collection_checkboxes` adds a hidden empty value by default (`include_hidden: true`) — [Rails guide (source)](https://raw.githubusercontent.com/rails/rails/main/guides/source/form_helpers.md).

**Dash notation (Django formsets)**
- Names are `{prefix}-{index}-{field}` (`form-0-title`, or `article-0-title` with `prefix='article'`); a **management form** (`form-TOTAL_FORMS`, `form-INITIAL_FORMS`, plus informational `MIN_NUM_FORMS`/`MAX_NUM_FORMS`) is required, otherwise "ManagementForm data is missing or has been tampered with"; `can_delete` adds a `DELETE` boolean and `can_order` an `ORDER` integer per form; `empty_form` renders a template with prefix `__prefix__` for JS cloning; "The formset is smart enough to ignore extra forms that were not changed" — [Django formsets docs (source)](https://raw.githubusercontent.com/django/django/main/docs/topics/forms/formsets.txt).

**Dot notation (Conform / Spring-style)**
- Conform combines `object.property` and `array[index]`, e.g. `tasks[0].content` → `{ tasks: [{ content: 'Hello World' }] }`; names are inferred via `getFieldset()`/`getFieldList()`; each list item exposes a stable `key` for rendering; list mutation via `insert`/`remove`/`reorder` intents — [Conform "Nested Objects and Arrays" (source)](https://raw.githubusercontent.com/edmundhung/conform/main/docs/complex-structures.md).
- pydantic's docs show converting an error `loc` tuple like `('items', 1, 'value')` into `items[1].value` — [pydantic errors docs (source)](https://raw.githubusercontent.com/pydantic/pydantic/main/docs/errors/errors.md).

**Client-side template/re-indexing (non-LiveView)**
- MOJ add-another clones a `<template>` with `%index%` placeholders and **re-indexes all remaining items' names and ids after removal** — [moj-frontend add-another.mjs](https://raw.githubusercontent.com/ministryofjustice/moj-frontend/main/src/moj/components/add-another/add-another.mjs).

**Large/sparse indexes**
- Node's `qs` limits array indices: indices above 20 (configurable `arrayLimit`) become **object keys** instead of array slots because someone could send `a[999999999]` and "it will take significant time to iterate over this huge array"; `qs.parse('a[100]=b')` → `{ a: { '100': 'b' } }`; sparse arrays are compacted — [ljharb/qs README](https://github.com/ljharb/qs) (search summary).

### Inferences
- **Recommended pyview encoding**: `model[field]`, `model[sub][field]`, and `model[items][<i>][field]` where `<i>` is an explicit integer; parse lists of objects from **dicts keyed by index strings**, sort keys numerically, and *compact* (so index gaps after a removal are harmless). Never rely on `[]`-appended arrays for lists of objects; reserve `name[]` for lists of scalars (multi-select, checkbox groups).
- **Why brackets over dots/dashes for pyview**: the Phoenix JS client already produces `_target` as a bracket-derived keyspace (`["user","items","0","sku"]`), so bracket names parse directly into that path; dot notation (`items[0].sku`) is equally expressive but diverges from Phoenix/Plug tooling; dash notation requires a management form and flattens nesting poorly.
- **Expressing "list is now empty"**: always render a sentinel (e.g., `<input type="hidden" name="order[items_drop][]">` or a hidden `order[items]` marker) so the server can distinguish "user removed every item" from "field not submitted"; for scalar lists (checkbox groups, `<select multiple>`) emit `<input type="hidden" name="x[]" value="">` and strip empty strings on parse (Ecto removes empty values inside arrays — see §7).
- **Stable identity for reorder/remove**: index in the name is for *transport*; identity should be a separate hidden key (DB id for persisted rows, a random/persistent id for new rows — cf. Phoenix `_persistent_id`, Conform `key`). Use it for DOM ids / LiveView keyed rendering so focus and client state survive re-indexing.
- **Add/remove/reorder via named buttons**: use `<button type="button" name="order[items_sort][]" value="new">` / `name="order[items_drop][]" value="3"` dispatching a change event (Phoenix recipe), so list operations are plain form data that go through the same parse/validate pipeline and remain progressively enhanced; alternatively dedicated `phx-click` events with bounded integer payloads.
- **Checkbox**: hidden `false` before the checkbox with the same name; the parser must take the **last** value for duplicate scalar keys (the checkbox) — ordering is guaranteed because `FormData` iterates in tree order.
- **File inputs**: must not go through the change/submit params in a LiveView clone (Phoenix strips `File` entries and uploads over a dedicated channel); the form library should treat file fields as references to upload entries.
- **Name collisions**: reserve a namespace for control params (`_target`, `_unused_*`, `*_sort`, `*_drop`, `_persistent_id`); forbid model field names that collide (e.g., a pydantic field literally named `items_drop`) or make the suffix configurable.
- **JSON-in-a-hidden-field** (serializing the whole sub-structure into one `<input type="hidden" value='{"...":...}'>`): simplest for complex widgets (rich editors, drag-sort trees) but loses per-field `_target`/`_unused_` tracking, per-field error anchoring, native autofill/constraint validation, LiveView form recovery granularity, and progressive enhancement; keep it as an escape hatch for custom widgets only.

### Gaps
- Did not verify Plug.Conn.Query's exact duplicate-key semantics (last-wins for non-`[]` keys) or its depth/length limits from source in this session.
- Did not find an authoritative source on PHP `max_input_vars` / `max_input_nesting_level` (php.net unreachable).
- Phoenix LiveView's exact behaviour for `_unused_` on hidden inputs (`!hidden` guard) seen in code but not documented.

---

## 4. Conditional fields and polymorphic / discriminated sub-forms

### Takeaway
Model polymorphic sub-forms as **discriminated (tagged) unions**: the tag field (a `<select>`/radios) drives which variant's fields are rendered and which schema validates. Validate only the active variant; decide explicitly whether values of hidden variants are **discarded** (safe default, matches what's submitted) or **stashed server-side** for restore-on-switch (better UX). JSON Schema's `if/then/else`, `dependentRequired`, `dependentSchemas` and `oneOf`+`discriminator` are the declarative vocabulary to borrow.

### Cited Findings
- **JSON Schema conditionals**: `dependentRequired` maps a property to a list of properties that become required if it is present; `dependentSchemas` "conditionally applies a subschema when a given property is present... applied in the same way allOf applies schemas. Nothing is merged or extended"; `if`/`then`/`else`: if subschema A validates, B must validate, else C; before Draft 2019-09 both were one keyword, `dependencies` — [JSON Schema: Conditional schema validation](https://json-schema.org/understanding-json-schema/reference/conditionals); [source](https://github.com/json-schema-org/website/blob/main/pages/understanding-json-schema/reference/conditionals.md) (search summary).
- **pydantic discriminated unions**: each member declares a `Literal` tag and the union uses `Field(discriminator='pet_type')`; a callable `Discriminator(...)` with `Tag('apple')` handles members without a common field (must handle both dict and model inputs). They are "both more performant and more predictable than untagged unions"; errors are reported **only for the matched member** (much less noise than trying every member); JSON Schema output uses the OpenAPI `discriminator`; the **error `loc` includes the tag**, e.g. `pet.cat...` — [pydantic Unions docs (source)](https://raw.githubusercontent.com/pydantic/pydantic/main/docs/concepts/unions.md).
  ```python
  class Cat(BaseModel):
      pet_type: Literal['cat']
      meows: int
  class Dog(BaseModel):
      pet_type: Literal['dog']
      barks: float
  class Model(BaseModel):
      pet: Cat | Dog = Field(discriminator='pet_type')
  ```
- Django formsets ignore extra sub-forms that weren't changed, and Rails `reject_if: :all_blank` skips all-blank nested rows — precedents for "don't validate sub-forms the user never engaged with" — [Django formsets (source)](https://raw.githubusercontent.com/django/django/main/docs/topics/forms/formsets.txt); [Rails guide (source)](https://raw.githubusercontent.com/rails/rails/main/guides/source/form_helpers.md).
- LiveView forms send the whole form plus `_target` on every change — so switching the tag select triggers a server round-trip that can re-render the variant — [LiveView form bindings (source)](https://raw.githubusercontent.com/phoenixframework/phoenix_live_view/main/guides/client/form-bindings.md).

### Inferences
- **Rendering**: render the discriminator as radios/select named `payment[kind]`; render only the active variant's fields under the same parent namespace (`payment[card_number]`, or a variant-scoped namespace `payment[card][number]` if variants share field names with different types). In a server-rendered LiveView model, fields not in the DOM are not submitted, which automatically yields "validate only visible fields".
- **Error mapping pitfall**: pydantic error locs for discriminated unions contain the tag segment (`('payment', 'card', 'number')`) that does **not** exist in the HTML name (`payment[number]`); the library must strip/translate tag segments when mapping errors to inputs.
- **Preserve vs discard**: offer both:
  ```python
  class PaymentForm(Form):
      payment: Card | BankTransfer = Field(discriminator="kind")
      class Meta:
          on_variant_switch = "stash"   # or "discard" (default)
  ```
  "stash" keeps the last raw params per variant in server state (never submitted, never validated) and re-hydrates on switch back; on final submit only the active variant is parsed, so stale hidden data can't leak (security + correctness). Avoid CSS-hiding inactive variants while leaving them in the form: they'd still be submitted and — if `required` — block native validation.
- **Simple show/hide conditions** (e.g., "Other – please specify" textbox when a radio = "other") map to `if/then` or `dependentRequired`; implement as a model validator plus a render-time predicate on the same condition so UI and validation can't drift. GOV.UK's "conditionally revealed" radios are the UX precedent (not fetched this session).
- Validation "only visible fields" should be derived from the **model** (active variant / condition true), not from what the client says is visible (client can lie).

### Gaps
- Did not fetch React Hook Form (`shouldUnregister`) or Zod (`z.discriminatedUnion`) docs to cite their preserve/discard defaults.
- Did not find a UX study on whether users expect values of a hidden variant to be retained when switching back.
- Did not fetch the GOV.UK "conditional reveal" guidance (e.g., its advice to keep conditional questions simple).

---

## 5. Rendering architecture patterns and trade-offs

### Takeaway
The best libraries use **progressive disclosure of complexity**: a one-line auto-render for the 80% case, then override at progressively finer grains (per-field metadata → per-type widget → per-form layout → field-level helpers in your own template → headless state/props → ejected/generated code you own) without rewriting from scratch at each step. Django 5's field-group templates, Phoenix `core_components`, simple_form wrappers, crispy-forms template packs, React Aria, Conform and shadcn/ui each demonstrate one rung.

### Cited Findings
- **Progressive disclosure of complexity** (François Chollet, Keras): "Make it easy to get started, yet make it possible to handle arbitrarily flexible use cases, only requiring incremental learning at each step. Like zooming in a complex landscape." — [Chollet on X](https://x.com/fchollet/status/1231285340335267840?lang=en). Keras "doesn't force you to follow a single true way... enables a wide range of different workflows from the very high level to the very low level", exposing "only an incremental amount of complexity when you start customizing things" — [Deep Learning with Python, ch. 7](https://deeplearningwithpython.io/chapters/chapter07_deep-dive-keras/) (search summary).
- **Generated code you own — Phoenix `core_components`**: generated into the app; "The components consist mostly of markup and are well-documented with doc strings and declarative assigns. You may customize and style them in any way you want". The `input/1` component takes a `%Phoenix.HTML.FormField{}` and computes `errors = if Phoenix.Component.used_input?(field), do: field.errors, else: []`, has per-type clauses (checkbox with hidden `false`, select via `options_for_select/2`, textarea, default), toggles an error class `@errors != [] && (@error_class || "input-error")`, and translates errors with Gettext — [Phoenix core_components template](https://raw.githubusercontent.com/phoenixframework/phoenix/main/installer/templates/phx_web/components/core_components.ex.eex).
- **shadcn/ui ("open code")**: not an npm package but a code-distribution system; the CLI copies component source into your project so you own and can modify every line and are insulated from upstream breaking changes — [Vercel Academy, "Why shadcn/ui is Different"](https://vercel.com/academy/shadcn-ui/why-shadcn-ui-is-different); [RedMonk, "the Revenge of Copypasta" (2025)](https://redmonk.com/kholterhoff/2025/04/22/ui-component-libraries-shadcn-ui-and-the-revenge-of-copypasta/) (search summaries).
- **Theme/template packs — django-crispy-forms**: separate template packs (`crispy-bootstrap5`, `crispy-tailwind`, `crispy-bulma`) selected by `CRISPY_TEMPLATE_PACK`; `FormHelper` controls layout/classes/submit and `Layout` objects (`Row`, `Column`, `Field`, `Submit`) define structure in Python; `{% crispy %}` renders — [crispy-forms install docs](https://django-crispy-forms.readthedocs.io/en/latest/install.html); [crispy-tailwind layout objects](https://django-crispy-forms.github.io/crispy-tailwind/layout_objects.html) (search summaries).
- **Wrappers — simple_form** ("Forms made easy for Rails! It's tied to a simple DSL, with no opinion on markup"): a wrappers API composes components per input:
  ```ruby
  config.wrappers do |b|
    b.use :label_input
    b.wrapper tag: :div, class: 'separator' do |component|
      component.use :hint,  wrap_with: { tag: :span, class: :hint }
      component.use :error, wrap_with: { tag: :span, class: :error }
    end
  end
  ```
  Named wrappers can be toggled/configured per input (`my_wrapper: false`, `my_wrapper_html:`) — [simple_form](https://github.com/heartcombo/simple_form); [Custom Wrappers wiki](https://github.com/heartcombo/simple_form/wiki/Custom-Wrappers) (search summaries).
- **Django 5.0 field-group templates**: "field group" templates render label, widget, help text and errors together; `as_field_group()` uses `django/forms/field.html` by default and "can be customized on a per-project, per-field, or per-request basis" — a built-in ladder (`{{ form }}` → `{{ form.field.as_field_group }}` → manual `{{ field.label_tag }} {{ field }} {{ field.errors }}`) — [Django 5.0 release notes](https://docs.djangoproject.com/en/6.1/releases/5.0/) (search summary).
- **Field-level helpers with inferred names — Conform**: `getFieldset()` / `getFieldList()` give each child field metadata "with name infered automatically", so developers write markup but never hand-build names — [Conform (source)](https://raw.githubusercontent.com/edmundhung/conform/main/docs/complex-structures.md).
- **Headless-with-state-attributes — React Aria Components**: state is exposed through ARIA attributes where possible and `data-*` attributes otherwise; `className`/`style` accept functions of state (render props); server errors plug in via `<Form validationErrors>` — [React Aria styling](https://react-aria.adobe.com/styling) (search summary); [React Aria Forms (source)](https://raw.githubusercontent.com/adobe/react-spectrum/main/packages/dev/s2-docs/pages/react-aria/forms.mdx).

### Inferences
- **Proposed ladder for pyview** (each rung reuses the one below; nothing is thrown away when you step down):
  1. **Auto**: `{{ form.render() }}` — render all fields from the pydantic/dataclass model using the active theme.
  2. **Schema metadata**: `email: Annotated[EmailStr, FormField(label="Work email", hint="...", autocomplete="email", widget="email")]`.
  3. **Per-type widget registry**: `widgets.register(date, DateInput)`, `widgets.register(Money, MoneyInput)`; discriminated unions and `list[Model]` get default "variant switcher" and "repeater" widgets.
  4. **Per-form layout**: `form.render(layout=[Row("first_name","last_name"), Fieldset("Address", "street", "city")])` (crispy-style) or partial auto-render `{{ form.render(exclude=["notes"]) }}` + custom markup for the rest.
  5. **Field helpers in your template**: `{{ f.email.label() }} {{ f.email.input(class_="...") }} {{ f.email.hint() }} {{ f.email.errors() }}` or `{{ f.email.field_group() }}` — ids/names/aria wiring computed by the library.
  6. **Headless**: `f.email.name`, `.id`, `.value` (raw), `.errors` (visible), `.attrs()` (name/id/value/aria-*/constraint attrs/data-state as a dict) for fully custom markup.
  7. **Eject**: a CLI (`pyview forms eject`) copies the theme's widget templates/components into the project (Phoenix core_components / shadcn model), after which the app owns them.
- **Trade-offs**: full auto-generation is fast but tends to hit a cliff (layout, custom widgets) — mitigated only if rungs 2–6 exist. Theme packs (crispy) and wrappers (simple_form) centralize markup but add indirection; "code you own" (Phoenix/shadcn) maximizes control but forfeits upstream fixes (e.g., accessibility improvements won't propagate). A good compromise: keep **wiring** (names, ids, aria, constraint attrs, error visibility) in the library (rungs 5–6) and put only **markup/styling** in owned/overridable templates, so ejecting templates doesn't eject correctness.
- **Accessibility belongs in the lowest shared layer**: the attrs() helper should emit `aria-invalid`/`aria-describedby`/`autocomplete`/`required`; if only the auto-renderer does it, every developer who drops down a rung loses it. (Phoenix's generated `input` component excerpt returned by the fetch did not show `aria-*` wiring — verify; if absent, this is a concrete gap pyview can improve on.)

### Gaps
- TanStack Form / React Hook Form headless APIs not fetched; could be cited as additional headless examples.
- No authoritative "ladder of abstraction" article for form libraries specifically was found (Bret Victor's "Up and Down the Ladder of Abstraction" is a related concept but was not fetched).
- Did not confirm whether Phoenix 1.8's generated `input` component emits `aria-invalid`/`aria-describedby`.

---

## 6. Styling strategies

### Takeaway
Expose field state to CSS as **attributes rendered by the server** (`aria-invalid="true"` plus `data-invalid`, `data-used`/`data-touched`, `data-dirty`, `data-required`, `data-disabled` on the field wrapper) so any styling system (plain CSS, Tailwind `aria-*`/`data-*` variants, design tokens) can style without the library knowing class names; offer an optional **class-provider** hook for utility-class users. Generate native constraint attributes from the schema for autofill/keyboard/`:user-invalid` benefits, but keep the server as the source of truth and decide deliberately whether browser validation UI is suppressed (`novalidate`).

### Cited Findings
- **React Aria**: components expose states "using DOM attributes... ARIA attributes wherever possible, or data attributes when a relevant ARIA attribute does not exist" (e.g., `data-invalid`, `data-focus-visible`), plus render-prop `className`/`style` functions and a Tailwind plugin for the states — [React Aria styling](https://react-aria.adobe.com/styling); [React Aria Group](https://react-spectrum.adobe.com/react-aria/Group.html) (search summaries).
- **Tailwind CSS**: built-in variants `invalid`, `user-valid`, `user-invalid`, `in-range`, built-in `aria-invalid:` (matches `aria-invalid="true"`), arbitrary `aria-[invalid=grammar]:`, and `data-*` variants (e.g. `data-[invalid]:`); custom variants can unify states, e.g. `@custom-variant aria-invalid (&[aria-invalid="true"], &[data-invalid]);` — [Tailwind "Hover, focus, and other states"](https://tailwindcss.com/docs/hover-focus-and-other-states) (search summary; the `@custom-variant` example came from a secondary course page, [Steve Kinney](https://stevekinney.com/courses/tailwind/aria-integration)).
- **`:user-invalid`**: represents a validated form element whose value fails its constraints **after the user has interacted with it**; Baseline Newly available in 2023 (Oct 2023 per web.dev) — [web.dev](https://web.dev/articles/user-valid-and-user-invalid-pseudo-classes); [MDN :user-invalid](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Selectors/:user-invalid) (search summaries). Baseline "widely available" status follows ~30 months after newly-available (so roughly spring 2026) — inference from Baseline's definition, not verified.
- **GOV.UK** turns off browser validation UI (`novalidate`, no `required`) for consistency of style/placement/content — [GOV.UK Validation (source)](https://raw.githubusercontent.com/alphagov/govuk-design-system/main/src/patterns/validation/index.md).
- **Phoenix core_components** styles errors by toggling a class server-side: `class={[@class || "w-full input", @errors != [] && (@error_class || "input-error")]}` — [Phoenix core_components template](https://raw.githubusercontent.com/phoenixframework/phoenix/main/installer/templates/phx_web/components/core_components.ex.eex).
- **React Aria `validationBehavior`** "native" (constraint validation, blocks submit) vs "aria" (AT-only marking, no blocking) — [React Aria Forms (source)](https://raw.githubusercontent.com/adobe/react-spectrum/main/packages/dev/s2-docs/pages/react-aria/forms.mdx).

### Inferences
- **State attributes (server-rendered)** — style with plain CSS or Tailwind:
  ```html
  <div class="field" data-invalid data-used data-required>
    <label for="age">Age</label>
    <input id="age" name="p[age]" type="number" min="0" max="130" step="1"
           inputmode="numeric" required aria-invalid="true" aria-describedby="age-error">
    <p id="age-error" class="error-message">...</p>
  </div>
  ```
  ```css
  :root { --field-border: #6b7280; --field-border-invalid: #b91c1c; }
  .field input { border: 1px solid var(--field-border); }
  .field[data-invalid] input,
  .field input[aria-invalid="true"] { border-color: var(--field-border-invalid); }
  ```
  ```html
  <!-- Tailwind -->
  <input class="border-gray-400 aria-invalid:border-red-700 data-[dirty]:bg-yellow-50">
  ```
  Using `aria-invalid` as the styling hook guarantees the visual and AT states can't diverge.
- **Class provider** for utility-class users: `ClassProvider.field(state) / .input(state) / .label(state) / .error(state)` returning strings (tailwind-variants/cva style), selected per theme; default provider emits no classes (pure attribute styling).
- **Design tokens**: themes should ship CSS custom properties (colors, radius, spacing, focus ring) rather than hard-coded values, so a theme pack is mostly tokens + templates.
- **Schema → native constraints** (pydantic): `min_length/max_length` → `minlength/maxlength`; `ge/le/gt/lt` → `min/max` (strict bounds need step adjustment); `multiple_of` → `step`; `pattern` → `pattern` (**caution**: Python `re` and JS `RegExp` (HTML uses the `v` flag) dialects differ — only emit when translatable); non-optional without default → `required`; `EmailStr` → `type=email`; `AnyUrl` → `type=url`; `date/datetime/time` → `type=date/datetime-local/time`; `int` → `type=number` or `inputmode=numeric` (GOV.UK-style text + `inputmode` avoids number-input pitfalls); `bool` → checkbox; `Literal`/`Enum` → select/radios.
- **Interplay decision**: (a) *progressive-enhancement mode*: emit constraints and `novalidate` on the form — browsers don't block submit or show bubbles, but `:user-invalid` styling and mobile keyboards still work, and the server renders the authoritative messages; (b) *native mode*: no `novalidate`, browser blocks submit until constraints pass (React Aria "native"-like); (c) *GOV.UK mode*: no constraint attributes at all. Default to (a). Note that in LiveView, server-rendered `aria-invalid` and client-computed `:user-invalid` may disagree briefly (e.g., server-only rules like uniqueness) — style primarily from server state.

### Gaps
- Could not fetch MDN/web.dev to confirm exact `:user-invalid` trigger rules (blur/commit vs. form submission) and whether it matches on submit attempt under `novalidate`.
- Radix `data-state` / Headless UI data-attribute conventions not fetched.
- Tailwind v4 docs not fetched directly; variant list is from a search summary.

---

## 7. Data-in / data-out concerns

### Takeaway
A form object must hold **four distinct things**: initial data, raw submitted params (strings, exactly as typed), the parsed/validated value (or none), and errors keyed by path — and render inputs from **raw params first** so "12abc" survives a failed parse. Empty-string normalization, dirty tracking against initial data, partial updates, and machine-readable error codes (for i18n) all fall out of keeping these separate, as Ecto changesets do.

### Cited Findings
- **Ecto changeset model**: `cast/4` handles *external* data ("user input from a form that needs to be type-converted and properly validated") and "you must explicitly list which data you accept"; the changeset keeps `data` (original), `params` (raw) and `changes` (successfully cast diffs) — [Ecto.Changeset (source)](https://raw.githubusercontent.com/elixir-ecto/ecto/master/lib/ecto/changeset.ex).
- **Empty values**: Ecto's `:empty_values` defaults to `[""]`; "Values are automatically trimmed and then checked"; if empty "the field is set to its default value"; for array fields "any empty value inside the array will be removed"; e.g. `cast(%Post{}, %{title: "", topics: []}, [:title, :topics]).changes == %{topics: []}` — [Ecto.Changeset (source)](https://raw.githubusercontent.com/elixir-ecto/ecto/master/lib/ecto/changeset.ex).
- **Raw-value redisplay**: Phoenix's `input_value/2` "will look for changes, then fallback to parameters, and finally fallback to the default struct/map value" — so an uncastable input (no change produced) is re-rendered from the raw param — [phoenix_html form.ex](https://raw.githubusercontent.com/phoenixframework/phoenix_html/main/lib/phoenix_html/form.ex). The `Phoenix.HTML.Form` struct carries `source`, `impl`, `id`, `name`, `data`, `params`, `hidden`, `options`, `errors`, `action`, `index` — same source.
- **pydantic errors are machine-readable**: each error has `type` (machine id, e.g. `int_parsing`), `loc` (path tuple), `msg`, **`input` (the raw input value)**, `ctx` (values for message templates) and `url`; messages can be customized by mapping `type` → template (`'url_scheme': 'Hey, use the right URL scheme! I wanted {expected_schemes}.'`) — [pydantic errors docs (source)](https://raw.githubusercontent.com/pydantic/pydantic/main/docs/errors/errors.md).
- **i18n of messages**: Phoenix generated apps translate `{msg, opts}` errors through Gettext's `"errors"` domain, using `dngettext` when `opts[:count]` is present (pluralization) — [Phoenix core_components template](https://raw.githubusercontent.com/phoenixframework/phoenix/main/installer/templates/phx_web/components/core_components.ex.eex).
- **Keep what the user typed**: GOV.UK — show the page again "with the form fields as the user filled them in", keeping failing answers helps users "see what went wrong, edit their previous answer, avoid re-entering information" — [GOV.UK Validation (source)](https://raw.githubusercontent.com/alphagov/govuk-design-system/main/src/patterns/validation/index.md). WCAG 3.3.7 similarly penalizes making users re-enter data — [WCAG 3.3.7 (source)](https://raw.githubusercontent.com/w3c/wcag/main/understanding/22/redundant-entry.html).
- **Dirty tracking**: Django formsets ignore extra forms that weren't changed and expose `has_changed()` comparing data with initial — [Django formsets (source)](https://raw.githubusercontent.com/django/django/main/docs/topics/forms/formsets.txt).
- **Server errors lifecycle**: React Aria clears server-supplied errors "after the user modifies each field's value" — [React Aria Forms (source)](https://raw.githubusercontent.com/adobe/react-spectrum/main/packages/dev/s2-docs/pages/react-aria/forms.mdx).
- **Reconnect**: LiveView forms with `phx-change` and an `id` "recover input values automatically after the user has reconnected or the LiveView has remounted after a crash"; customizable with `phx-auto-recover` — [LiveView form bindings (source)](https://raw.githubusercontent.com/phoenixframework/phoenix_live_view/main/guides/client/form-bindings.md).
- **Server vs client duplication**: "You'll always need to carry out server side validation, even if you use client side validation" — [GOV.UK Validation (source)](https://raw.githubusercontent.com/alphagov/govuk-design-system/main/src/patterns/validation/index.md).

### Inferences
- **FormState shape for pyview** (changeset-like):
  ```python
  @dataclass
  class FormState(Generic[M]):
      schema: type[M]
      initial: dict            # from model instance / defaults (serialized to form strings)
      raw: dict                # nested dict of submitted strings (exactly as typed)
      value: M | None          # parsed model if valid
      errors: dict[Path, list[ErrorInfo]]  # ErrorInfo(type, msg, ctx, input)
      used: set[Path]          # from _unused_ / blur tracking
      submitted: bool
      def input_value(self, path): return get(self.raw, path, default=get(self.initial, path))
      @property
      def changed(self) -> set[Path]: ...   # compare normalized raw vs initial
  ```
  Render from `raw` first (like `input_value`), falling back to `initial` — so "12abc" stays in the int field alongside "Enter a whole number".
- **Empty string vs None vs missing** (define explicitly; pydantic does not do this for you): `""` for `Optional[T]` → `None`; `""` for a required field → a *missing/required* error ("Enter your age"), not `int_parsing`; key **absent** from params → "not submitted" (keep existing value in partial updates; needed for fields not rendered) — except booleans (need hidden `false`) and lists (need a sentinel), which is exactly why those tricks exist. Trim whitespace before emptiness check (Ecto precedent).
- **Coercion**: parse from strings with lax mode (pydantic lax mode coerces `"42"` → `42`), but map pydantic's generic messages to user-facing ones by `type` (`int_parsing` → "Enter a whole number, like 12"); store message templates keyed by error `type` for i18n, and interpolate `ctx` (e.g., `{min_length}`) — the ErrorInfo should keep `type`/`ctx`, not only the English `msg`.
- **Locale**: render values with a formatter/parser pair per field (e.g., `Decimal` with locale grouping in a text input + `inputmode="decimal"`), because HTML `type=number`/`type=date` always use locale-independent wire formats (from HTML spec knowledge, not fetched this session).
- **Partial updates / PATCH semantics**: only fields present in `raw` (plus sentinels) should be considered changed; compute `changes = parsed − initial` for persistence (`model_dump(exclude_unset=True)` analogue) so unrelated fields aren't overwritten.
- **Client/server duplication**: in a LiveView model the server validates on every change anyway, so client-side validation is only an enhancement (constraint attrs for instant styling/keyboard). Avoid writing rules twice; derive client attrs from the same schema.

### Gaps
- Did not verify pydantic lax-mode coercion specifics (e.g., `""` → int error type) from docs in this session.
- Did not fetch Django `BoundField.value()` / `Form.changed_data` docs.
- No source fetched on HTML number/date wire formats (WHATWG spec unreachable).

---

## 8. Security considerations

### Takeaway
Treat every form payload — including hidden fields, ids, `_target`, sort/drop indices and event payloads — as attacker-controlled. The form schema must be an **explicit allow-list DTO** (not the DB model), list sizes/indices/nesting must be capped at parse time, every event must re-authorize, and the websocket join must be CSRF-protected.

### Cited Findings
- **Mass assignment / autobinding / object injection**: frameworks that "automatically bind HTTP request parameters into program code variables or objects" let attackers add unintended params, e.g. `...&email=bobby@tables.com&isAdmin=true`. Defences: **allow-list** bindable fields, block-list sensitive ones, or use **DTOs** ("create Data Transfer Objects and avoid binding input directly to domain objects"). Framework examples: Spring `setAllowedFields()`/`setDisallowedFields()`, Laravel `$fillable`/`$guarded`, Mongoose protect flags — [OWASP Mass Assignment Cheat Sheet (source)](https://raw.githubusercontent.com/OWASP/CheatSheetSeries/master/cheatsheets/Mass_Assignment_Cheat_Sheet.md).
- **Rails strong parameters** for nested data: `params.expect(person: [ :name, addresses_attributes: [[ :id, :kind, :street ]] ])` or `permit(:name, addresses_attributes: [:id, :kind, :street, :_destroy])` — [Rails guide (source)](https://raw.githubusercontent.com/rails/rails/main/guides/source/form_helpers.md).
- **Ecto `cast`** is an allow-list: "Because you are receiving external data from a third-party, you must explicitly list which data you accept" — [Ecto.Changeset (source)](https://raw.githubusercontent.com/elixir-ecto/ecto/master/lib/ecto/changeset.ex).
- **List-size DoS**: Django's `absolute_max` "allows limiting the number of forms that can be instantiated when supplying POST data. This protects against memory exhaustion attacks using forged POST requests"; defaults to `max_num + 1000`; `validate_max` enforces `max_num` in validation; missing/forged management data → "ManagementForm data is missing or has been tampered with" — [Django formsets (source)](https://raw.githubusercontent.com/django/django/main/docs/topics/forms/formsets.txt).
- **Parser limits**: Rack's query parser caps total bytes (default 4,194,304), number of params (default 4,096) and nesting depth, raising `QueryLimitError` (alias `ParamsTooDeepError`) — [Rack query_parser.rb](https://raw.githubusercontent.com/rack/rack/main/lib/rack/query_parser.rb). `qs` turns indices >20 into object keys specifically because of payloads like `a[999999999]` — [ljharb/qs](https://github.com/ljharb/qs) (search summary).
- **LiveView threat model**: "Every time a user performs an action on your system, the server should verify if said user is authorized to do so, regardless if using LiveViews or not"; "An attacker can use browser developer tools or custom scripts to send any payload to your LiveView, bypassing your UI restrictions entirely"; "a savvy user can directly talk to the server and request a deletion anyway" — [LiveView security model guide (source)](https://raw.githubusercontent.com/phoenixframework/phoenix_live_view/main/guides/server/security-model.md).
- **CSRF over websockets (LiveView)**: the CSRF token is read from a `<meta>` tag and passed as `params: {_csrf_token: csrfToken}` when constructing `LiveSocket`; the socket is configured with `connect_info: [session: @session_options]` so the server can validate the token against the session; the session key is fixed as `"_csrf_token"` — [Phoenix.LiveView docs](https://hexdocs.pm/phoenix_live_view/Phoenix.LiveView.html) (search summary); [phoenix_live_view #2370](https://github.com/phoenixframework/phoenix_live_view/issues/2370).
- **Hidden id fields exist in the payload**: Rails `fields_for` and Phoenix `inputs_for` emit hidden `id` inputs for persisted children — [Rails guide (source)](https://raw.githubusercontent.com/rails/rails/main/guides/source/form_helpers.md); [LiveView form bindings (source)](https://raw.githubusercontent.com/phoenixframework/phoenix_live_view/main/guides/client/form-bindings.md).

### Inferences
- **Allow-list by construction**: the pydantic/dataclass form model *is* the allow-list; parse with `extra="ignore"` (or `"forbid"` to log tampering) and never bind form params onto ORM/domain objects directly — map validated DTO → domain explicitly. Warn loudly (or refuse) if a developer passes an ORM model class as a form schema.
- **Server-owned fields**: `id`, `owner_id`, `role`, prices, `is_admin` should not be form fields at all; for nested persisted children, hidden ids must be re-checked against the parent's children loaded server-side (ids not belonging to the parent → error, not a lookup of arbitrary records). In LiveView, prefer keeping identity in socket state (index → id map) and not trusting the submitted id at all.
- **Hidden fields are untrusted**: never put authorization-relevant state (price, discount, workflow step permissions, "variant already verified") in hidden inputs; keep it in server/socket state. Re-validate discriminator tags against allowed variants.
- **Parse-time caps** (before pydantic): max total params, max nesting depth (e.g., 16–32), max list index (e.g., reject any index > `max_items*2` or > 1,000) and **never allocate by index** (build dicts, then sort/compact — so `items[999999]=x` costs one entry, not a million); per-field `max_length` on lists and strings in the schema (`Field(max_length=...)`); cap sort/drop arrays to the current item count; validate `_target` paths against the schema before using them.
- **CSRF / origin on websocket join**: verify a CSRF token on the socket connect (as LiveView does via `_csrf_token` in connect params checked against the session) and check the `Origin` header on the websocket upgrade (Phoenix `check_origin` — prior knowledge, not re-verified this session); a pyview form library should assume the transport does this and re-authorize in every `handle_event`/submit handler.
- **Rate-limit change events**: `phx-change` fires per keystroke; server-side validation on every event should be cheap — expensive checks (uniqueness queries) should run on blur/submit or be debounced, which also limits enumeration (e.g., "username taken" probing).

### Gaps
- OWASP's cheat sheet (as fetched) has no Python/pydantic- or Django-specific guidance; Django ModelForm's `fields`/`exclude` requirement (Django refuses a ModelForm without `fields` or `exclude`) was not re-verified from docs this session.
- Could not verify Plug's default limits (`Plug.Parsers` length, `Plug.Conn.Query` depth) or Phoenix `check_origin` defaults from primary sources.
- No primary source found quantifying real-world DoS incidents via huge array indices (only library rationale in `qs`, Django, Rack).
