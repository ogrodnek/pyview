# Part 7 — Evidence from the prototype spike

A ~300-line spike (`prototype/`) was written during the research to check that the proposed core is feasible with pydantic 2.13 and the 0.20.17 client conventions. Everything below was run, not reasoned about.

## What the spike implements

- `decode_form(pairs)` — Plug.Conn.Query-compatible bracket decoder with `_target` → path, meta separation, `[]` appends, index-keyed maps compacted to ordered lists.
- `normalize_empty(data)` — Ecto `empty_values` semantics (strip, `""` → absent).
- `Form` — `validate(pairs)` / `submit(pairs)`, attempted `params`, whole-model validation, `used` paths from `_target`, `errors` as records, `visible_errors(path)` gating (used ∪ submitted), discriminated-union tag skipping.
- `Field` — `name`, `id`, `value`, `errors`, `label` (from `Field(title=)`), `constraints` (HTML attrs from `annotated_types` metadata), `input_type` inference, nested and row traversal.
- `DEFAULT_MESSAGES` — a first human-readable catalog keyed by pydantic error type with `ctx` interpolation.
- An Ibis render test proving `{{ form.name | input }}`, `{% for row in form.addresses %}{{ row.city | input }}{% endfor %}` work with the vendored engine unchanged.

## Findings (pydantic 2.13.4, Python 3.11)

| Question | Result |
|---|---|
| Error `loc` for nested / list / union | `('addresses', 0, 'street')`; discriminated unions insert the tag: `('account', 'business', 'company')`; model-level validators give `()`. |
| Empty string coercion in lax mode | `""` fails for `int`, `float`, `Decimal`, `bool`, `date`, `datetime`, `Enum`, `Literal` **and** `Optional[int]` (`int_parsing`, not `None`). Only `str` accepts it. ⇒ the form layer must normalise empties (Ecto rule) before validation. |
| Bool strings | `"on"`, `"true"`, `"yes"`, `"1"` → True; `"off"`, `"false"`, `"no"`, `"0"` → False; `""`, `"checked"` → `bool_parsing`. |
| Number strings | `" 21 "` and `"21.0"` → 21; `"1e3"` → `int_parsing`; `"1,5"` → `decimal_parsing`/`float_parsing`. |
| Date strings | `"2024-05-01"` → `date`; `"2024-05-01T13:45"` (datetime-local) → naive `datetime`. |
| Single string for `list[str]` | `list_type` error — lists must arrive as lists (`name[]`). |
| `experimental_allow_partial` | Does **not** suppress `missing` errors for required fields (`('addresses', 0, 'city') missing` still reported) — it only tolerates truncated trailing data, so it is not a "validate only what's touched" tool. |
| Single-field validation | `TypeAdapter(Annotated[fi.annotation, fi]).validate_python(v)` validates one field with its constraints; `validate_assignment=True` also works per attribute. Not needed: whole-model validation is cheap enough. |
| Cost of whole-model validation | ~19 µs for a 3-level model with 14 sub-objects (~60 fields), i.e. negligible per keystroke. |
| Field-targeted errors from a `model_validator` | `raise ValidationError.from_exception_data(name, [InitErrorDetails(type=PydanticCustomError(...), loc=("end",), input=...)])` attaches the error to `end`; inside `list[Item]` the path composes to `('items', 1, 'hi')`. After-validators do not run while field errors exist (so cross-field errors appear once the fields are individually valid). |
| Idiomatic cross-field | `@field_validator("password_confirmation")` reading `info.data["password"]` puts the error on the confirmation field. |
| Introspection | `model_fields[name]` gives `annotation`, `is_required()`, `default`, `title`, `description`, `metadata` (`MinLen(3)`, `MaxLen(20)`, `Ge(18)`, …) — enough to derive labels, `required`, `minlength`, `maxlength`, `min`, `max`, `pattern` and the widget. |

## End-to-end scenario that passes

Model: `Profile(name, age, newsletter, addresses: list[Address] (min 1), account: Personal | Business discriminated by "kind")`. Simulated client payloads (`profile[...]` names + `_target`):

1. User types `ab` in name → whole model invalid (5 errors) but only `name` shows "Must be at least 3 characters"; `age`, `company` show nothing.
2. User enters `17` in age → age shows "Must be at least 18", attempted value `17` kept; attrs `required min=18`, type `number`.
3. User types `A` in company (union variant) → `form["account"]["company"].errors == ["Must be at least 2 characters"]`, label "Company name" (from `Field(title=)`), name `profile[account][company]`, id `profile_account_company`; the untouched `addresses[0].street` still shows nothing.
4. Submit with a bad street → now every error is visible.
5. Submit with valid data → `form.valid` and `form.model` is a `Profile` with a `Business` account.

## What the spike does not yet cover (deliberately)

Intents for list rows, row keys, the message override hooks, i18n, widgets/theme, t-string helpers, uploads, and the `meta` key of the 1.x client. These are specified in Part 4 and are the first implementation milestones.

## Part 2 of the spike: row keys, intents and the union shelf (`prototype/pyview_forms_proto2.py`)

Added after the client research confirmed the mechanism: a `<button type="button" name="profile[addresses][_intent]" value="add" phx-click='[["dispatch",{"event":"change"}]]'>` is serialised by the 0.20.17 client as the submitter of a `phx-change`, so the intent pair arrives together with every current input value.

| Step (simulated client payloads) | Result |
|---|---|
| Initial validate with one address | row key `k1`; `row.id == "profile_addresses_k1"`, `row.name == "profile[addresses][0]"` |
| Click *Add address* (intent `add`) | two rows `k1`, `k2`; the model now has two `missing` errors for the blank row, but **none are visible** (a freshly added row is not "used"; only the list path is) |
| Type into row 2, click *Remove* on row 1 (intent `remove:k1`) | one row left: key `k2`, value `Second Ave` kept, name renumbered to `profile[addresses][0][street]`, DOM id still `profile_addresses_k2_street` |
| Add, then *move up* the new row (intent `move:k3:up`) | order `[k3, k2]`; ids unchanged, names renumbered |
| Switch account `business` → `personal` → `business` | `company == "ACME"` restored from the shelf although the client only ever sends the rendered variant |
| Fill the rows and submit | `form.valid`; `Profile(addresses=[New Row St/Rome, Second Ave/Lyon], account=Business(company="ACME"))` |

Gating rule confirmed against Phoenix `used_input?` semantics: a path is visible when submitted, when it was itself used, or when it is an *ancestor* of a used path; children never inherit used-ness from a parent or list.

## Part 3 of the spike: the corrected semantics (`prototype/pyview_forms_proto3.py`, 790 lines, `test_proto3.py`)

Written after the critique (Part 8) to make every "(verified)" claim in Part 4 true against payloads the 0.20.17 client can actually produce.

| Scenario | Result |
|---|---|
| Decoder: wire string, `parse_qs` dict and pairs; `[]` appends; sparse indices `[0]`,`[2]` compacted; `_target=profile[tags][]` → `("tags",)`; `_csrf_token` and a `phx-value` key outside the prefix → `meta` | pass |
| 1.x `_unused_` on the last segment (`profile[addresses][0][_unused_city]=`, `profile[_unused_tags][]=`) → `unused == {("addresses", 0, "city"), ("tags",)}`, not in data | pass |
| `profile[items][][name]`, `profile[__class__]`, `…[__proto__]…` rejected | pass |
| `profile[addresses][_intent]=remove:k1` popped into `Intent("remove", ("addresses",), "k1")` | pass |
| Edit form: `Form(Plant, data=plant)`; a template rendering only `name` keeps `days`/`note` from data; clearing a required field → `missing` with the label-aware message "Plant name is required"; clearing an optional/defaulted field → `None`/default as a change; `SecretStr` renders `""`; `html.attrs == 'required minlength="3"'` | pass |
| Union with the **real client ordering**: switching the select sends the old fieldset's values with the new tag; with variant-named inputs nothing is polluted, only the active variant is validated, the untouched variant shows no errors, re-render sends only the active fieldset, switching back restores `company == "ACME"` | pass |
| Intents: add → new row with key, `applied_intents[0].op == "add"`, no visible errors on the blank row (the ungated error list does contain `missing`); remove by key → the other row keeps its key and value while its name is renumbered; add + `move:…:up` reorders; `form["addresses"]["0"]` accepts a digit string; submit makes every error visible; a later validate clears `just_submitted` | pass |
| `add_error("name", "unique", …)` is visible without the field being used and survives a re-validation; cleared by the next submit | pass |
| Recovery replay (`recovered=True`) marks every non-blank path used on a fresh form | pass |
| Ancestor rule: with only `addresses[0].street` used, `("addresses",)` is visible and `("name",)` is not | pass |

Also verified for Part 4: a six-line bracket-aware `splitc` in the vendored Ibis makes `{"type": "email", "class": "w-full"}` and list arguments parse as filter arguments (the stock helper raises `TemplateSyntaxError` on them).
