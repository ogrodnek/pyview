# pyview: current state of form & event-data handling (baseline for a pydantic/dataclass-first form library)

Scope: the pyview repo at HEAD `9b32095` (2026-09-26, "Merge pull request #220 from ogrodnek/upload_correctness"), package version `0.9.0`, plus the Phoenix LiveView JS client bundled with it. All code links are permalinks to `https://github.com/ogrodnek/pyview/blob/9b32095/...`; line numbers were read from the local checkout at `/home/user/pyview`. Where I say "verified empirically", I ran a throwaway probe script against HEAD on CPython 3.11.15 (script in scratchpad, not in the repo).

---

## 1. How are phx-change / phx-submit / other event payloads received and parsed?

### Takeaway
All `"event"` messages go through one branch in `ws_handler.py`. Form events (`payload["type"] == "form"`) are decoded with a bare `urllib.parse.parse_qs(value)`, which returns a **flat `dict[str, list[str]]`**. There is **no bracket-notation decoding** (`user[addresses][0][city]` stays a literal key), **blank values are dropped** (`keep_blank_values` is not set, so a cleared field disappears from the payload), `_target` arrives as an ordinary key (`{"_target": ["name"]}`), and there is no `_unused_` handling because the bundled 0.20.17 client never sends it. Click, key and hook payloads are *not* URL-encoded. They arrive as JSON dicts of plain strings, so handlers see two different payload shapes.

### Cited Findings
- The entry point is this code. `parse_qs` is imported at the top of the module (`from urllib.parse import parse_qs, urlparse`, line 5):
  ```python
  if event == "event":
      value = payload["value"]
      if payload["type"] == "form":
          value = parse_qs(value)
          socket.upload_manager.maybe_process_uploads(value, payload)
  ```
  — [pyview/ws_handler.py L186-191](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/ws_handler.py#L186-L191)
- Routing after decoding:
  - If the payload has a `cid` (set via `phx-target`), the event goes to `socket.components.handle_event(target_cid, event_name, value)`.
  - Otherwise it goes to `call_handle_event(socket.liveview, event_name, value, socket)`.
  - The built-in `lv:clear-flash` event is special-cased before either path.
  - A non-int `cid` is only logged as a warning.
  — [pyview/ws_handler.py L197-222](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/ws_handler.py#L197-L222)
- After every event the server re-renders, diffs, and replies with `{"diff": diff | hook_events}`. Nothing in the reply is form-specific: no per-form status and no errors channel. — [pyview/ws_handler.py L224-246](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/ws_handler.py#L224-L246)
- URL query params for `handle_params` also use bare `parse_qs(url.query)`, merged with path params (`{**query_params, **path_params}`). — [pyview/ws_handler.py L121-126](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/ws_handler.py#L121-L126), and [L252-263](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/ws_handler.py#L252-L263) for `live_patch`
- **Verified empirically.** Nested names stay flat, and blanks are dropped. `parse_qs("user%5Bname%5D=Al&user%5Baddresses%5D%5B0%5D%5Bcity%5D=NYC&tags%5B%5D=a&tags%5B%5D=b&email=&agree=on&_target=user%5Bname%5D")` returns:
  ```
  {'user[name]': ['Al'], 'user[addresses][0][city]': ['NYC'], 'tags[]': ['a', 'b'], 'agree': ['on'], '_target': ['user[name]']}
  ```
  `email=` is missing. With `keep_blank_values=True` it would be `'email': ['']`. — decoding code at [pyview/ws_handler.py L190](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/ws_handler.py#L190)
- Multi-value fields such as `tags[]` or `<select multiple>` survive only as a list under the literal key (`'tags[]'`). The `[]` suffix is not stripped anywhere in `pyview/` (grep found no bracket-parsing code in the package). — [pyview/binding/params.py](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/binding/params.py)
- `_target` is read in only two places, and both assume it is present:
  - `ChangeSet.apply` does `k = payload["_target"][0]`. — [pyview/changesets/changesets.py L47](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/changesets/changesets.py#L47)
  - `UploadManager.maybe_process_uploads` does `config_key = qs["_target"][0]`. — [pyview/uploads.py L466-477](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/uploads.py#L466-L477)
- Non-form events carry dict values built by the client's `extractMeta`:
  - It collects `phx-value-*` attributes, stripping only the `phx-value-` prefix, so `phx-value-user-id` becomes the key `user-id` (no dash→underscore conversion).
  - It adds `value` for inputs, and deletes `value` for unchecked checkboxes and radios.
  - Hook `pushEvent` payloads are arbitrary JSON.
  — [pyview/static/assets/app.js L5498-5534](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/static/assets/app.js#L5498-L5534)
- The docs acknowledge the two shapes: "Form values in the raw payload are always lists (e.g., `["value"]`) to support multi-select elements. Typed parameter binding handles this automatically." — [docs/core-concepts/event-handling.md L255](https://github.com/ogrodnek/pyview/blob/9b32095/docs/core-concepts/event-handling.md#L255)
- The only raw-socket-message pre-parsing is `phx_message.parse_message` (JSON text frames, or binary upload chunks). It carries TODOs: "need to handle these message types better" and "handle: other errors?". — [pyview/phx_message.py L8-21](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/phx_message.py#L8-L21)

### Inferences
- A form library needs its own decoder that runs on the raw URL-encoded string, or re-encodes the `parse_qs` output. The `parse_qs` step has already lost blank values, and its dict loses the relative order of keys that share a prefix. The raw string is available as `payload["value"]` before line 190 mutates `value`, but the handler only ever receives the parsed dict. The cleanest hook is to change L189-191 to keep the raw string (for example, stash it on the socket or context), or to switch to `parse_qsl(..., keep_blank_values=True)`.
- Blank-dropping breaks "the user cleared this field" semantics. A cleared required field currently looks identical to a field never rendered.
- `_target` and any future `_unused_*` keys are mixed into the same namespace as user fields. A form decoder should strip the reserved keys (`_target`, `_csrf_token` if ever present, `_unused_*`) before validation.

### Gaps
- I did not verify whether the Phoenix client ever sends `type: "form"` with a non-string `value`, for example from `JS.push` with a form. From the bundle, `pushInput` and `pushFormSubmit` always call `serializeForm(...)`, which returns `params.toString()` ([app.js L4667-4703](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/static/assets/app.js#L4667-L4703)).

---

## 2. Existing changeset / form / validation abstraction

### Takeaway
There is one small, pydantic-only, flat `ChangeSet` in `pyview/changesets/changesets.py` (67 lines). Its design fits "validate one field per phx-change": `apply()` copies only the `_target` field, keeping just the first value.

It has several concrete bugs and limitations:
- no nesting or lists;
- `save()` cannot accept a raw form payload;
- `apply()` raises `KeyError` on submit payloads, which carry no `_target`;
- errors are keyed only by the top-level `loc[0]`;
- it has no tests.

There is no form or field rendering helper in the core package; examples define their own ibis filters.

### Cited Findings
- The full public API:
  ```python
  @dataclass
  class ChangeSet(Generic[Base]):          # Base = TypeVar("Base", bound=BaseModel)
      cls: type[Base]
      changes: dict[str, Any]
      errors: dict[str, Any]
      valid: bool
      def __getitem__(self, key): return self.changes.get(key, "")
      @property model -> Optional[Base]    # self.cls(**self.changes), None on ValidationError
      @property attrs -> SimpleNamespace   # SimpleNamespace(**self.changes)
      @property fields -> list[str]        # list(self.cls.model_fields)
      def save(self, payload) -> Optional[Base]   # self.cls(**payload); errors[str(loc[0])] = msg
      def apply(self, payload):
          k = payload["_target"][0]
          self.changes[k] = payload.get(k, [""])[0]
          ...  # re-validate whole model; model-level errors (empty loc) attributed to field k;
               # only record errors for keys already in self.changes
  def change_set(cls) -> ChangeSet: return ChangeSet(cls, {}, {}, False)
  ```
  — [pyview/changesets/changesets.py L1-67](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/changesets/changesets.py#L1-L67); exported via [pyview/changesets/__init__.py](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/changesets/__init__.py). It is not re-exported from top-level `pyview` ([pyview/__init__.py](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/__init__.py)).
- The "touched-field" behaviour lives inside `apply`: `if loc in self.changes: self.errors[loc] = error["msg"]`. Errors appear only for fields the user has changed at least once. This is the server-side substitute for Phoenix `used_input?`. — [changesets.py L55-62](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/changesets/changesets.py#L55-L62)
- `save()` with a raw form payload fails. **Verified empirically:** `change_set(M).save(parse_qs("name=Al"))` returned `None` with `errors == {'name': 'Input should be a valid string'}`, because the values are lists. No example calls `save()`. — [changesets.py L35-44](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/changesets/changesets.py#L35-L44)
- Calling `apply()` on a phx-submit payload raises `KeyError`. The client's submit path calls `serializeForm(formEl, {submitter, ...meta})` with no `_target` ([app.js L5646-5677](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/static/assets/app.js#L5646-L5677)). Yet the docs' "Input Validation" pattern calls `socket.context["changeset"].apply(payload)` inside the `save_user` submit handler. — [docs/core-concepts/event-handling.md L421-457](https://github.com/ogrodnek/pyview/blob/9b32095/docs/core-concepts/event-handling.md#L421-L457)
- Tests: `grep -rn "changeset|ChangeSet|BaseModel|pydantic" tests/` finds no test of `ChangeSet`. The only pydantic mention in the tests is `tests/uploads/test_configuration.py:4`. — [tests/](https://github.com/ogrodnek/pyview/tree/9b32095/tests)
- Git history for `pyview/changesets` is not visible because the clone is shallow (`git rev-parse --is-shallow-repository` → `true`, 111 commits back to 2026-04-04). No recent commit touches it. — [commit history](https://github.com/ogrodnek/pyview/commits/9b32095)
- The plants example carries a stale pydantic-v1-style `class Config: error_msg_templates = {...}` nested inside a **dataclass** context (`PlantsContext`). It has no effect. — [examples/views/form_validation/plants.py L10-19](https://github.com/ogrodnek/pyview/blob/9b32095/examples/views/form_validation/plants.py#L10-L19)

### Inferences
Limitations that matter for complex forms:
1. **No nested paths.** Error locs are collapsed to `str(loc[0])`, so `("addresses", 0, "city")` becomes `"addresses"`. `changes` is a flat `dict[str, str]`.
2. **First value only** (`[0]`), so multi-selects and checkbox groups are lost.
3. **Pydantic only.** There is no dataclass support, although the binder supports dataclasses and not pydantic (see §3). The two halves are complementary but disconnected.
4. **Not idempotent under full-form replays.** Form recovery (§9) and a "validate whole form" flow both need `apply` to consume the full payload, not just `_target`.
5. **No "action"/"submitted" state** comparable to Ecto's `changeset.action`, so there is no way to reveal all errors after a failed submit.
6. **No data/initial model.** You cannot build an edit form from an existing `Plant` instance: `changes` starts empty, and there is no `change_set(Plant, data=plant)`.
7. **No type coercion of display values.** `attrs` returns the raw strings.

A new library can replace `pyview.changesets` or keep a compatibility shim. The API is small (`change_set`, `.apply`, `.save`, `.model`, `.attrs`, `.errors`, `.valid`, `__getitem__`) and only two examples plus one docs page use it.

### Gaps
- Upstream issue tracker: a semantic search of GitHub issues on `ogrodnek/pyview` for "forms validation changeset nested form data" returned **0 results**. I found no open issues about forms.

---

## 3. Typed event params: dependency injection and parameter binding

### Takeaway
pyview has a signature-driven binder (`pyview/binding/`, added around PR #101/#102, Dec 2025) plus a FastAPI-style `Depends()`. It runs for LiveView `mount`, `handle_params`, `handle_event`, and for `@event`-decorated methods through `BaseEventHandler`.

Parameters resolve in this order:
1. `Depends` defaults;
2. **injectables by name or type** (`socket`, `session`/`Session`, `event`, `payload`, `url`, `params`);
3. **stdlib dataclass** parameters, assembled field-by-field from the *root* of the payload;
4. otherwise, `payload[param_name]`, converted by `ConverterRegistry` (int/float/str/bool, Optional/Union, list/set/tuple, dataclass).

There is **no pydantic model binding, no `TypeAdapter`, no nesting/prefix support, and no error-tolerant mode**. Any binding error raises `ValueError`, which crashes the LiveView process. LiveComponent `handle_event` bypasses the binder entirely (open PR #126 addresses this).

### Cited Findings
- Module docstring:
  - Reserved names: `socket`, `url`, `event`, `payload`.
  - Type-based `params` rules: `params: Params` injects the container; `params: dict` injects a dict; `params: str` is treated as a URL param name.
  — [pyview/binding/__init__.py L1-26](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/binding/__init__.py#L1-L26)
- `Binder.bind` / `abind`:
  - Iterates `inspect.signature(func).parameters`, skipping `self`, `*args` and `**kwargs`.
  - Uses `get_type_hints(func, include_extras=True)`, falling back to `{}` on `NameError`/`AttributeError`/`RecursionError`.
  - A `_DependsMarker` default is resolved recursively (cached per-request in `ctx.cache`); otherwise `_resolve_param` is called.
  — [pyview/binding/binder.py L40-93](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/binding/binder.py#L40-L93), [L193-271](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/binding/binder.py#L193-L271)
- `_resolve_param` order: injectables, then dataclass, then raw lookup (`ctx.params` first, then `ctx.payload[name]`), then defaults / Optional → None, else `ParamError("missing required parameter")`. — [binder.py L121-166](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/binding/binder.py#L121-L166)
- Dataclass gathering only looks at top-level keys named exactly like the fields:
  ```python
  for field in dataclasses.fields(expected):
      if ctx.params.has(field.name): result[field.name] = ctx.params.getlist(field.name)
      elif ctx.payload and field.name in ctx.payload: result[field.name] = ctx.payload[field.name]
  ```
  — [binder.py L168-179](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/binding/binder.py#L168-L179)
- `ConverterRegistry.convert`:
  - Handles `Union`/`X | None` (tries each variant; `""` or `[""]` becomes `None` for Optional).
  - Handles `list`/`set`/`tuple` (homogeneous or fixed heterogeneous tuples).
  - Handles scalars `int/float/str/bool`. For these it **takes the first list element**. Bool accepts `true/1/yes/on` and `false/0/no/off/""`.
  - Handles dataclasses via `_convert_dataclass`, recursing per field and requiring every non-default, non-Optional field.
  - **Otherwise it returns the raw value unchanged** (`# Fallback: return as-is`). This covers pydantic models, enums, `datetime`, `Decimal`, `Literal`, and so on.
  — [pyview/binding/converters.py L24-191](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/binding/converters.py#L24-L191)
- `InjectableRegistry.resolve`:
  - Checks the `Session` type first (`Annotated[dict, _SessionInjector()]`).
  - Then name-based: `socket`, `session`, `event`, `payload`, `url`, and `params` (only when annotated `Params`/`dict`/untyped).
  - Then `ctx.extra[name]`.
  - `params: dict[str, T]` converts every value to `T`.
  — [pyview/binding/injectables.py L28-135](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/binding/injectables.py#L28-L135)
- `Params` is a multi-value container: `get`, `getlist`, `getone`, `has`, `items`, `multi_items`, `raw`, `to_flat_dict`. — [pyview/binding/params.py L21-105](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/binding/params.py#L21-L105)
- For events, `params` is always empty and form data lives only in `payload`. The context is built as `ctx = BindContext(params=Params({}), payload=payload, url=None, socket=socket, event=event)` in both [pyview/binding/helpers.py L117-144](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/binding/helpers.py#L117-L144) and [pyview/events/BaseEventHandler.py L74-99](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/events/BaseEventHandler.py#L74-L99). The DI docs nevertheless describe `params` as "URL/form parameters". — [docs/core-concepts/dependency-injection.md L231-243](https://github.com/ogrodnek/pyview/blob/9b32095/docs/core-concepts/dependency-injection.md#L231-L243)
- A binding failure escalates. `call_handle_event` logs each `ParamError` and then `raise ValueError(f"Event binding failed: {result.errors}")`. `BaseEventHandler.handle_event` does the same. — [helpers.py L136-144](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/binding/helpers.py#L136-L144), [BaseEventHandler.py L91-99](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/events/BaseEventHandler.py#L91-L99)
- **Verified empirically:**
  - (a) A dataclass `F(name: str, email: str)` bound from `parse_qs("name=Al&email=&_target=email")` gives `ParamError(... reason='Missing required fields for F: email')`. The blank email was dropped by `parse_qs` and became "missing", so a phx-change on a partially filled form would raise.
  - (b) A pydantic `M(BaseModel)` parameter `m: M` gives `ParamError(name='m', ..., reason='missing required parameter')`. Pydantic models are not bound.
  - (c) `user_id: str` with payload `{"user-id": "5"}` gives `missing required parameter`.
  — code at [binder.py L143-160](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/binding/binder.py#L143-L160)
- Point (c) contradicts the docs example `<button phx-click="delete_user" phx-value-user-id="{{user.id}}">` → `async def handle_event(self, event, socket, user_id: str, ...)`. — [docs/core-concepts/event-handling.md L181-196](https://github.com/ogrodnek/pyview/blob/9b32095/docs/core-concepts/event-handling.md#L181-L196)
- The `@event` decorator:
  - Sets `func._event_names`.
  - `BaseEventHandler.__init_subclass__` scans `dir(cls)` into `cls._event_handlers`.
  - `AutoEventDispatch` wraps handlers in `EventMethodDescriptor` / `BoundEventMethod`, whose `__str__` returns the event name, so `phx-click={self.increment}` works in t-strings.
  — [pyview/events/BaseEventHandler.py L12-72](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/events/BaseEventHandler.py#L12-L72), [pyview/events/AutoEventDispatch.py L6-98](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/events/AutoEventDispatch.py#L6-L98)
- `Depends` is a `@dataclass(frozen=True) _DependsMarker(dependency, use_cache=True)`, typed via `TYPE_CHECKING` overloads to return the dependency's result type. `Session = Annotated[dict[str, Any], _SessionInjector()]`. Ruff ignores `B008` for this pattern. — [pyview/depends.py L29-75](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/depends.py#L29-L75), [pyproject.toml ruff ignore](https://github.com/ogrodnek/pyview/blob/9b32095/pyproject.toml)
- LiveComponents are not bound:
  - `ComponentsManager.handle_event` calls `await component.handle_event(event, payload, socket)` positionally. — [pyview/components/manager.py L211-240](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/components/manager.py#L211-L240)
  - `send_to_parent` calls `self.parent_socket.liveview.handle_event(event, payload, self.parent_socket)` positionally, which only works for legacy or `BaseEventHandler` signatures. — [manager.py L263-273](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/components/manager.py#L263-L273)
  - Open PR #126, "update binding to support LiveComponents" (opened 2026-02-01, last updated 2026-08-01, +369/−14, not merged), targets this. — [PR #126](https://github.com/ogrodnek/pyview/pull/126)
- Real usage of typed binding in the examples:
  - `FifaAudienceLiveView.handle_event(self, socket, perPage: int)` for a `<select name="perPage">` inside `<form phx-change="select-per-page">`. — [examples/views/fifa/fifa.py L31-39](https://github.com/ogrodnek/pyview/blob/9b32095/examples/views/fifa/fifa.py#L31-L39)
  - `handle_params(self, socket, paging_params: PagingParams)` with a dataclass. — [fifa.py L9-12, L41-46](https://github.com/ogrodnek/pyview/blob/9b32095/examples/views/fifa/fifa.py#L9-L46)
  - `@event async def save(self, name: Optional[str], socket)`. — [examples/views/flash_demo/flash_demo.py L24-32](https://github.com/ogrodnek/pyview/blob/9b32095/examples/views/flash_demo/flash_demo.py#L24-L32)
  - `@event("search") async def handle_search(self, socket, q: str = "")`. — [examples/views/index/index.py L133-135](https://github.com/ogrodnek/pyview/blob/9b32095/examples/views/index/index.py#L133-L135)
- Tests cover the binder thoroughly (dataclass from params and payload, Optional, defaults, unions, containers, `*args`/`**kwargs` skipping) using pytest classes and fixtures that build a `BindContext` directly. — [tests/binding/test_binder.py](https://github.com/ogrodnek/pyview/blob/9b32095/tests/binding/test_binder.py), plus test_converters/test_injectables/test_params/test_depends/test_helpers/test_backward_compat in [tests/binding/](https://github.com/ogrodnek/pyview/tree/9b32095/tests/binding)

### Inferences
Extension points for a form library in the binder:
1. **`Binder._resolve_param` (L121-166)** is the natural place to add "if `expected` is a Form type, a pydantic `BaseModel`, or `Annotated[T, FormMarker]`, then build it from the decoded nested payload". This would sit alongside the existing dataclass branch at L143-149.
2. **`ConverterRegistry.convert` (L37-63)** is the place to delegate unknown types to `pydantic.TypeAdapter(expected).validate_python(...)`. Today it falls through to "return as-is".
3. **`InjectableRegistry`** could inject a per-event decoded structure (for example `form: FormData`) or `_target`. Its name- and type-based lookup is simple to extend, for instance with another `Annotated` marker like `Session`.
4. **`BindContext.extra`** already lets callers add arbitrary injectables. `call_handle_event` could put `{"form": decoded}` there.

Behavioural gaps to design around:
- Binding errors are fatal (`ValueError`). phx-change needs a *non-raising* path that returns partial data plus errors. That argues for injecting a changeset/form object rather than a validated model.
- Dataclass binding ignores the parameter name (fields come from the payload root), so two forms or a prefixed form (`user[...]`) cannot be distinguished.
- Reserved names (`event`, `payload`, `socket`, `url`, `params`, `session`) collide with same-named form fields.
- Binding happens at most twice per event: `call_handle_event` binds `BaseEventHandler.handle_event`, which binds again for the decorated method. This matters only for cost and for `Depends` caching, which is per-`BindContext`.

### Gaps
- I did not read PR #126's diff. I know only its title, state and size. Whether it also changes how payloads are passed (for example, adds binder use in `send_to_parent`) is unverified.

---

## 4. Templating systems, components and slots: how would a form helper render?

### Takeaway
There are two templating systems, which can be mixed per view:
1. **Ibis** (vendored, Jinja-like `.html` next to the view; Python ≥3.11). Composition is via a global `@filters.register` registry, `{% include %}`/`{% extends %}`, and method calls with **literal-only positional args**. There are no macros.
2. **Python 3.14 t-strings** (`TemplateView.template()` returning `string.templatelib.Template`). Composition is via plain functions returning `Template`, `Markup`/`__html__` objects inserted raw, `live_component(...)` placeholders, and `slots(...)`.

Neither engine knows about attributes: t-string interpolation into attribute positions is plain HTML escaping. There is no boolean-attribute handling (`True` renders as `"True"`) and no attribute-dict spreading. LiveComponents (stateful, CID-targeted) exist only for t-strings.

### Cited Findings
- The overview table: HTML Templates (Ibis), 3.11+, `.html` files alongside views; T-String Templates, 3.14+, Python code in `template()` method. "You can use both approaches in the same project." — [docs/templating/overview.md L13-100](https://github.com/ogrodnek/pyview/blob/9b32095/docs/templating/overview.md#L13-L100)
- Ibis pipeline:
  - `LiveView.render` finds `<module>.html` via `find_associated_file`.
  - `LiveTemplate.tree` serializes dataclass assigns (fields plus `@property` names) and merges `context_processor` outputs.
  - Ibis `Template.tree(...)` produces the diff tree.
  — [pyview/live_view.py L51-63](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/live_view.py#L51-L63), [pyview/template/live_template.py L20-82](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/template/live_template.py#L20-L82), [pyview/template/serializer.py](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/template/serializer.py), [pyview/template/context_processor.py](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/template/context_processor.py)
- Ibis expression limits:
  - `re_func_call = r"^([\w.]+)\((.*)\)$"`. Arguments go through `ast.literal_eval`: "Arguments must be valid Python literals."
  - Filters are looked up in a global `filters.filtermap` ("Unrecognised filter name").
  - `PrintNode` escapes unless the value is `Markup`.
  — [pyview/vendor/ibis/nodes.py L55-141](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/vendor/ibis/nodes.py#L55-L141), [L256-290](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/vendor/ibis/nodes.py#L256-L290)
- Ibis supports the tags `for/empty`, `if/elif/else`, `cycle`, `include ... with a = b & c = d`, `extends`, `block`, `spaceless`, `trim` and `with`. There is no `macro`/`call`. — [nodes.py register() calls L295-738](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/vendor/ibis/nodes.py#L295-L738)
- The t-string processor `LiveViewTemplate.process` maps each interpolation as follows:
  | Interpolated value | Result |
  |---|---|
  | `None` | `""` |
  | a format spec is present | applied first |
  | `LiveComponentPlaceholder` | CID int (or `ComponentMarker` when unconnected) |
  | nested `Template` | recursive sub-tree (good diffs) |
  | anything with `__html__` (e.g. `Markup`) | raw string |
  | `str` | escaped |
  | `int`/`float`/`bool` | `str(v)`, so `True` becomes `"True"` |
  | `StreamList` | stream |
  | `list` | comprehension `{"s","d"}` |
  | anything else | `escape(str(v))`, so dicts get stringified |

  — [pyview/template/live_view_template.py L101-195](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/template/live_view_template.py#L101-L195)
- The HTML escaper replaces `& < > " '`. — [pyview/template/html.py](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/template/html.py)
- The `TemplateView` mixin calls `self.template(assigns, meta)`, requires a `Template` return, and falls back to the Ibis `super().render`. The module raises `ImportError` below 3.14 and is exported only when `sys.version_info >= (3, 14)`. — [pyview/template/template_view.py L125-170](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/template/template_view.py#L125-L170), [pyview/template/__init__.py L25-29](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/template/__init__.py#L25-L29)
- Stateless "function components" are simply functions returning `Template`, e.g. `def Card(title: str, children: Template, *, footer: Template | None = None) -> Template`. The same file contains `Button(label, event_ref, *, style, size, disabled)` with `disabled` handled by branching into two different t-strings. — [examples/views/components/stateless_demo.py L30-100](https://github.com/ogrodnek/pyview/blob/9b32095/examples/views/components/stateless_demo.py#L30-L100)
- LiveComponents: `LiveComponent[T]` has `mount(socket, assigns)`, `update(socket, assigns)`, `template(assigns, meta) -> Template`, and `handle_event(event, payload, socket)`. `ComponentMeta` has `cid`, `parent_meta`, `slots`, and `myself`. `ComponentSocket` has `context`, `cid`, `manager`, and `send_parent(event, payload)`. — [pyview/components/base.py L30-212](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/components/base.py#L30-L212)
- `live_component(cls, id=..., **assigns)` returns a placeholder. Identity is keyed by `(class, id)` in `ComponentsManager._by_key`. Assigns are applied via queued mount/update. — [live_view_template.py L330-342](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/template/live_view_template.py#L330-L342), [pyview/components/manager.py L74-126](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/components/manager.py#L74-L126)
- Slots: `slots(__default: Template | None = None, **named: Template) -> dict[str, Template]` is passed as `live_component(Card, id=..., slots=slots(...))`. Slots are extracted from assigns in `register()` and exposed as `meta.slots['header']`. — [pyview/components/slots.py L48-73](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/components/slots.py#L48-L73), [manager.py L91-95](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/components/manager.py#L91-L95)
- The components docs cover `meta.myself` targeting, parent-child communication and slots. — [docs/core-concepts/live-components.md](https://github.com/ogrodnek/pyview/blob/9b32095/docs/core-concepts/live-components.md)
- Existing Ibis form helpers are user-defined filters returning `Markup`:
  - `input_tag(changeset, field_name, options)` and `error_tag(changeset, field_name)` in the registration example. — [examples/views/registration/registration.py L14-46](https://github.com/ogrodnek/pyview/blob/9b32095/examples/views/registration/registration.py#L14-L46)
  - `live_file_input` and `upload_preview_tag` in core. — [pyview/uploads.py L715-749](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/uploads.py#L715-L749)
- Since `Markup` has `__html__`, the same helper functions can be called directly in t-strings (`{live_file_input(cfg)}`). Each renders as one opaque dynamic string. — [live_view_template.py L167-171](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/template/live_view_template.py#L167-L171)

### Inferences
- A cross-engine form library probably needs a **renderer-agnostic core** (a field/path model with name, id, value, errors, used/touched state) plus two thin adapters:
  - **Ibis**: expose objects whose methods take literal args. `{{ form.field("email").value }}` works, but `{{ form.field(name_var) }}` does not, because args must be literals. Helpers also need to be registered as global filters. Iterating nested lists works through `{% for addr in form.addresses %}{{ addr.city.value }}`, provided `form.addresses` returns sub-form objects with attribute access, since Ibis resolves dotted paths.
  - **t-strings**: return nested `Template`s for granular diffs, or `Markup` for simplicity.
- A t-string form helper must implement its own attribute rendering (boolean attrs like `checked`, `selected`, `disabled`, `required`, `multiple`, and attr dicts), because the processor offers none.
- `LiveComponent` could host a self-contained sub-form (its own changeset in `socket.context`, `phx-target={meta.myself}`). Today, though, it would receive raw `parse_qs` dicts through the unbound `handle_event(event, payload, socket)`.
- Slots (`dict[str, Template]`) could carry custom field/label/error markup into a generic form component.

### Gaps
- I did not examine how the Ibis `tree()` splits statics and dynamics within attribute values (`nodes.py tree_parts`). So I cannot say whether an Ibis-rendered attribute diff is per-attribute or per-print-node.

---

## 5. Form-related examples: patterns and boilerplate

### Takeaway
Only two examples do real validation, both through the flat pydantic `ChangeSet` (plants, registration), and they duplicate error markup by hand. The other forms are single-field (search, per-page select, flash name, file upload) or not forms at all (checkboxes use `phx-click`). There are **no examples of nested data, lists of sub-forms, checkbox groups, multi-selects, radios, conditional fields, or edit-existing-record forms**. The registration example never handles its `register` submit event.

### Cited Findings
- **Plants (form validation).**
  - Model: `Plant(BaseModel)` with `name: str = Field(min_length=3, max_length=20)` and `watering_schedule_days: int = Field(ge=1, le=30)`. — [examples/views/form_validation/data.py L8-16](https://github.com/ogrodnek/pyview/blob/9b32095/examples/views/form_validation/data.py#L8-L16)
  - Context: `changeset: ChangeSet[Plant] = field(default_factory=lambda: change_set(Plant))`.
  - A string-dispatched `handle_event(self, event, payload, socket)`:
    ```python
    if event == "save":
        # TODO: should really look at the model...
        v = socket.context.changeset.model
        if v:
            socket.context.plants.append(v)
            socket.context = PlantsContext(plants=socket.context.plants)   # reset form by replacing context
        return
    if event == "validate":
        socket.context.changeset.apply(payload)
    ```
    — [examples/views/form_validation/plants.py L22-48](https://github.com/ogrodnek/pyview/blob/9b32095/examples/views/form_validation/plants.py#L22-L48)
  - Template:
    - `<form method="post" phx-submit="save" phx-change="validate" autocomplete="off">` (no `id`, so no form recovery).
    - Per field it hand-writes `value="{{changeset.attrs.name}}"`, `phx-debounce="2000"` / `phx-debounce="blur"`, and `<div phx-feedback-for="name">{% if changeset.errors.get("name") %}...{{changeset.errors.get("name", "")}}...{% endif %}</div>`, with the error SVG block copy-pasted per field.
    — [examples/views/form_validation/plants.html L6-63](https://github.com/ogrodnek/pyview/blob/9b32095/examples/views/form_validation/plants.html#L6-L63)
- **Registration.**
  - `Registration(BaseModel)` has four `str` fields and a `@model_validator(mode="after") passwords_match`. Model-level errors (empty `loc`) get attributed to the current `_target` field by `ChangeSet.apply`.
  - Filters render the inputs:
    ```python
    @filters.register
    def input_tag(changeset: ChangeSet, field_name: str, options: Optional[dict[str, str]] = None) -> Markup:
        type = (options or {}).get("type", "text")
        ...
        return Markup('<input type="{type}" id="{field_name}" name="{field_name}" phx-debounce="2000" value="{value}" class="... {error_class}" />').format(...)
    ```
    used as `{{ changeset | input_tag("password", {"type" : "password"}) }}` and `{{ changeset | error_tag("password") }}`.
  - The handler handles only `"validate"`; the form's `phx-submit="register"` is unhandled and carries a debug `print(event, payload)`.
  — [examples/views/registration/registration.py L14-81](https://github.com/ogrodnek/pyview/blob/9b32095/examples/views/registration/registration.py#L14-L81), [registration.html L8-48](https://github.com/ogrodnek/pyview/blob/9b32095/examples/views/registration/registration.html#L8-L48)
- **Flash demo** (Ibis and t-string versions): `<form phx-submit="save">` with one `name` input, and `@event async def save(self, name: Optional[str], socket)`. Validation is manual (`if not name: socket.put_flash("error", ...)`). — [examples/views/flash_demo/flash_demo.py L24-32](https://github.com/ogrodnek/pyview/blob/9b32095/examples/views/flash_demo/flash_demo.py#L24-L32), [flash_demo_tstring.py L26-87](https://github.com/ogrodnek/pyview/blob/9b32095/examples/views/flash_demo/flash_demo_tstring.py#L26-L87)
- **FIFA:** a `<form phx-change="select-per-page">` wraps a `<select name="perPage">` whose options use `{% if paging.perPage == 10 %} selected{% endif %}`, with typed `perPage: int` binding. — [examples/views/fifa/fifa.html L13-22](https://github.com/ogrodnek/pyview/blob/9b32095/examples/views/fifa/fifa.html#L13-L22), [fifa.py L31-39](https://github.com/ogrodnek/pyview/blob/9b32095/examples/views/fifa/fifa.py#L31-L39)
- **Index search:** `<form phx-change="search">` with `<input name="q" phx-debounce="300">` and `@event("search") handle_search(self, socket, q: str = "")`. — [examples/views/index/index.html L39-58](https://github.com/ogrodnek/pyview/blob/9b32095/examples/views/index/index.html#L39-L58), [index.py L133-135](https://github.com/ogrodnek/pyview/blob/9b32095/examples/views/index/index.py#L133-L135)
- **Checkboxes:** individual `<input type="checkbox" phx-click="toggle" phx-value-index="{{ loop.index }}" ... {% if checkbox %}checked{% endif %}>` elements, not a form. The handler does `int(payload["index"])`. — [examples/views/checkboxes/checkboxes.html L15-18](https://github.com/ogrodnek/pyview/blob/9b32095/examples/views/checkboxes/checkboxes.html#L15-L18), [checkboxes.py L37-42](https://github.com/ogrodnek/pyview/blob/9b32095/examples/views/checkboxes/checkboxes.py#L37-L42)
- **File upload:** `<form id="upload-form" phx-change="validate" phx-submit="save">` containing `{{upload_config | live_file_input}}`. The handler has no `validate` branch, so the change event is only used to register upload entries (§8). — [examples/views/file_upload/file_upload.html L5-37](https://github.com/ogrodnek/pyview/blob/9b32095/examples/views/file_upload/file_upload.html#L5-L37), [file_upload.py L39-61](https://github.com/ogrodnek/pyview/blob/9b32095/examples/views/file_upload/file_upload.py#L39-L61)
- **JS commands:** a `<form id="focus-form">` exists only for focus demos, with no phx-change or phx-submit. — [examples/views/js_commands/js_commands.html L133](https://github.com/ogrodnek/pyview/blob/9b32095/examples/views/js_commands/js_commands.html#L133)
- Other handlers index raw payloads directly, e.g. kanban `payload["taskId"]`, `payload["task_list"]`. — [examples/views/kanban/kanban.py L41-52](https://github.com/ogrodnek/pyview/blob/9b32095/examples/views/kanban/kanban.py#L41-L52)

### Inferences
The boilerplate a form library should eliminate:
1. Repeating the field name 3-4 times per input (`name=`, `id=`, `value=`, `phx-feedback-for=`, `errors.get(...)`).
2. Copy-pasting error markup per field.
3. `if event == "validate"` / `"save"` string dispatch with manual `changeset.apply` and `.model` calls.
4. Resetting the form by rebuilding the context.
5. `selected` / `checked` conditionals written by hand in the template.
6. No path for editing an existing model instance.

The complex cases the user wants (deeply nested, conditional, dynamic lists) have **zero prior art** in the repo.

### Gaps
- None within the repo. All form-bearing examples were enumerated via grep for `phx-change|phx-submit|<form|<select|checkbox|radio|textarea`.

---

## 6. Form documentation in docs/ and docs-site/

### Takeaway
`docs-site/src/content/docs` is a **symlink to `../../../docs`** (Astro Starlight), so `docs/` is the single source of truth. Forms are covered only in `docs/core-concepts/event-handling.md`: payload shapes, typed params, dataclass binding and a short `ChangeSet` "Input Validation" pattern. Parts of that page are inaccurate:
- the submit handler calls `apply()`, which raises `KeyError` without `_target`;
- `phx-value-user-id` does not bind to `user_id`;
- the DI docs say `params` holds form params, but it is empty for events.

The upload docs show a `phx-change="validate"` form. There is no dedicated forms page, and nothing on nested params, errors UI, recovery, debounce, or `phx-feedback-for`.

### Cited Findings
- The symlink `docs-site/src/content/docs -> ../../../docs`. Sidebar sections: Home, Getting Started, Live Examples, Single-File Apps, Streams, Core Concepts (autogenerated), Templating (autogenerated), Features (Authentication, Flash Messages, JS Commands, JavaScript Interop, File Uploads). There is no Forms entry. — [docs-site/astro.config.mjs L25-60](https://github.com/ogrodnek/pyview/blob/9b32095/docs-site/astro.config.mjs#L25-L60), [docs-site/src/content](https://github.com/ogrodnek/pyview/tree/9b32095/docs-site/src/content)
- Event-handling docs sections:
  - "Form Change Events", showing `query: str = ""` / `category: str = "all"` binding and the legacy `payload.get("query", [""])[0]`.
  - "Form Submission Events", showing a `@dataclass class UserForm: name: str; email: str; role: str = "user"` bound as `user: UserForm`. Values come from the root of the payload, so the parameter name `user` is irrelevant.
  - "Form Handling Patterns → Input Validation", using `change_set(User)`, `@event("validate") handle_validate(self, socket, payload: dict): socket.context["changeset"].apply(payload)`, and `@event("save_user") ... apply(payload); if .valid: user = .model ...`.
  — [docs/core-concepts/event-handling.md L213-328](https://github.com/ogrodnek/pyview/blob/9b32095/docs/core-concepts/event-handling.md#L213-L328), [L421-457](https://github.com/ogrodnek/pyview/blob/9b32095/docs/core-concepts/event-handling.md#L421-L457)
- The docs list `phx-change`, `phx-submit`, `phx-blur`, `phx-focus`, `phx-keydown` and `phx-keyup` as supported UI events. — [event-handling.md L15-25](https://github.com/ogrodnek/pyview/blob/9b32095/docs/core-concepts/event-handling.md#L15-L25)
- The DI docs' name-based table: "`params` | `Params` or `dict` | URL/form parameters". — [docs/core-concepts/dependency-injection.md L231-243](https://github.com/ogrodnek/pyview/blob/9b32095/docs/core-concepts/dependency-injection.md#L231-L243)
- The direct-upload quick start: `<form phx-submit="save" phx-change="validate">` with `{{ upload_config | live_file_input }}`, entries/progress/errors loops, and `consume_uploads()` on save. — [docs/features/file-uploads/direct.md L44-104](https://github.com/ogrodnek/pyview/blob/9b32095/docs/features/file-uploads/direct.md#L44-L104)
- The t-string docs' "Composable Helper Methods" section shows helpers returning `Template`, the likely house style for a t-string form API. — [docs/templating/t-string-templates.md L93-122](https://github.com/ogrodnek/pyview/blob/9b32095/docs/templating/t-string-templates.md#L93-L122)
- The flash docs describe flash as a place for "validation errors", with a `<form phx-submit="save">` t-string example. — [docs/features/flash-messages.md L9, L102-150](https://github.com/ogrodnek/pyview/blob/9b32095/docs/features/flash-messages.md)

### Inferences
- A forms page would be a new entry, either under Features or Core Concepts (which is autogenerated from `docs/core-concepts/`). The event-handling "Form Handling Patterns" section and the `ChangeSet` docs would need rewriting or deprecating.

### Gaps
- None found beyond what is listed. `docs/getting-started.md` and `docs/index.md` only link to event-handling for forms.

---

## 7. Git history, TODOs and issues about forms

### Takeaway
The local clone is shallow (111 commits, 2026-04-04 → 2026-09-26). The visible history has no form or changeset work. Recent effort went into upload correctness (PR #220), Python 3.15 support, a collab editor example, and dependency bumps. Remote PR history shows the binding system (PRs #101/#102, Dec 2025), Depends (#125), flash (#130), and an **open PR #126 to extend binding to LiveComponents**. There is one form TODO in code, in the plants example.

### Cited Findings
- `git rev-parse --is-shallow-repository` → `true`; `git log --oneline | wc -l` → 111. The oldest visible commit is `7f4fc86 2026-04-04 Bump defu ...`. — [commits](https://github.com/ogrodnek/pyview/commits/9b32095)
- Notable visible commits:
  - `9b32095` (2026-09-26), the upload_correctness merge: ~40 commits such as "Require preflight approval before starting uploads" and "validate file types".
  - `6be6d48` (2026-08-04), "Support Python 3.15 (#205)".
  - `64a56b3` (2026-07-31), "collab editor example (#202)".
  - `5f24eaa` (2026-07-12), "Remove dead code from core package (#197)".
  - `0dae229` (2026-09-04), "Bump phoenix to 1.8.9" (the `phoenix` JS package, not `phoenix_live_view`).
  — [commit list](https://github.com/ogrodnek/pyview/commits/9b32095)
- PR search on `repo:ogrodnek/pyview form OR changeset OR binding` returned:
  - #126 "update binding to support LiveComponents" (open);
  - #125 "Depends injection" (closed);
  - #102 "Add typed binding system (converters, injector, binder) and tests" (closed);
  - #101 "Add params binder module with binding types and registries" (closed);
  - #130 "Add flash message support" (closed);
  - #104 "Claude/review pyview docs" (closed).
  — [PR #126](https://github.com/ogrodnek/pyview/pull/126), [PR #102](https://github.com/ogrodnek/pyview/pull/102), [PR #101](https://github.com/ogrodnek/pyview/pull/101), [PR #125](https://github.com/ogrodnek/pyview/pull/125)
- The GitHub issues search for forms, validation, changesets or nested form data returned 0 items. — [issues](https://github.com/ogrodnek/pyview/issues)
- TODOs in code:
  - `examples/views/form_validation/plants.py:40`, "# TODO: should really look at the model...";
  - `pyview/ws_handler.py:258`, "TODO: I don't think this is actually going to work...", about path params on `live_patch`;
  - `pyview/phx_message.py:16,20`, message-type handling.
  — [plants.py L40](https://github.com/ogrodnek/pyview/blob/9b32095/examples/views/form_validation/plants.py#L40), [ws_handler.py L258](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/ws_handler.py#L258), [phx_message.py L16-20](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/phx_message.py#L16-L20)

### Inferences
- Forms have not been touched since the changeset was introduced (pre-April 2026, beyond the shallow window). The binder (Dec 2025) is the most recent adjacent investment, and a form library should build on it rather than beside it.

### Gaps
- Full history before 2026-04-04 is unavailable locally (shallow clone), so I could not see when or why `ChangeSet` was designed around `_target`.

---

## 8. Uploads: how they work and how they would interact with a form library

### Takeaway
pyview implements Phoenix's upload protocol fully:
- `socket.allow_upload(name, UploadConstraints(...))` returns an `UploadConfig` (pydantic);
- the `live_file_input` filter renders the file input;
- entries register on phx-change via `payload["uploads"]`;
- `allow_upload` preflight, `lvu:` channel joins, chunks and progress follow;
- files are consumed with `consume_uploads()` or `consume_upload_entry()` on submit.

File values are **stripped from the serialized form**, so uploads never appear in the form payload. The coupling point is `maybe_process_uploads`, which finds the config by `qs["_target"][0]` and requires the file input's `name` to equal the upload name. Upload errors live on `UploadConfig.errors` and `entry.errors`, separate from any changeset.

### Cited Findings
- The client's `serializeForm` removes files: `formData.forEach((val, key) => { if (val instanceof File) toRemove.push(key) })` … `toRemove.forEach((key) => formData.delete(key))`. — [pyview/static/assets/app.js L4667-4703](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/static/assets/app.js#L4667-L4703)
- `pushInput` attaches `uploads = LiveUploader.serializeUploads(inputEl)` (entries keyed by the input's `data-phx-upload-ref`, each carrying `path: inputEl.name`, `ref`, `name`, `size`, `type`, `last_modified`, and optional `meta`) to the `{type:"form", event, value, uploads, cid}` message. — [app.js L3049-3064](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/static/assets/app.js#L3049-L3064), [L5552-5576](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/static/assets/app.js#L5552-L5576)
- Server-side registration code:
  ```python
  def maybe_process_uploads(self, qs, payload):
      if "uploads" in payload:
          uploads = payload["uploads"]
          config_key = qs["_target"][0]
          config = self.config_for_name(config_key)
          if config:
              if config.ref in uploads: config.add_entries(uploads[config.ref])
              else: logger.warning(...)
  ```
  — [pyview/uploads.py L466-477](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/uploads.py#L466-L477)
- `live_file_input(config)` renders `<input type="file" id="{config.ref}" name="{config.name}" data-phx-upload-ref=... data-phx-active-refs=... data-phx-done-refs=... data-phx-preflighted-refs=... data-phx-update="ignore" phx-hook="Phoenix.LiveFileUpload" {accept} {multiple} {auto_upload}>`. `upload_preview_tag(entry)` renders an `<img ... data-phx-hook="Phoenix.LiveImgPreview">`. Both are Ibis filters returning `Markup`. — [uploads.py L715-749](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/uploads.py#L715-L749)
- Models and API:
  - `UploadConstraints(max_file_size=10MB, max_files=10, accept=["image/*"], chunk_size=64KB)` with `accepts_file_type`.
  - `UploadConfig`: `name`, `entries_by_ref`, `ref`, `errors`, `autoUpload`, `constraints`, `progress_callback`, `external_callback`, `entry_complete_callback`, and `uploads`.
  - Methods `entries`, `cancel_entry`, `add_entries`, `update_progress`, `consume_uploads()` (a context manager), `consume_upload_entry`, `consume_external_upload(s)`.
  - `ConstraintViolation.message` covers "too_large", "too_many_files" and "not_accepted".
  — [uploads.py L88-423](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/uploads.py#L88-L423)
- `socket.allow_upload(upload_name, constraints, auto_upload=False, progress=None, external=None, entry_complete=None) -> UploadConfig` exists on both the connected and unconnected sockets. `UploadManager.allow_upload` raises `UploadConfigurationInUseError` if the name already has entries. — [pyview/live_socket.py L90-107, L362-373](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/live_socket.py#L90-L373), [uploads.py L433-455](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/uploads.py#L433-L455)
- The websocket upload events (`allow_upload`, `phx_join` on `lvu:*`, `chunk`, `progress`, `phx_leave` on `lvu:*`) are handled in `ws_handler`. — [pyview/ws_handler.py L304-463](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/ws_handler.py#L304-L463)
- On submit, the client defers `phx-submit` until uploads finish (`hasUploadsInProgress` leads to `scheduleSubmit`, and `inputsAwaitingPreflight` leads to `uploadFiles` then submit). — [app.js L5646-5677](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/static/assets/app.js#L5646-L5677)
- Form recovery clears file inputs: `inputs.forEach((input2) => input2.hasAttribute(PHX_UPLOAD_REF) && LiveUploader.clearFiles(input2))`. — [app.js L5760-5781](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/static/assets/app.js#L5760-L5781)
- Upload tests are extensive (preflight, chunks, cancel, consume, progress, validation, configuration) with factories and fixtures. — [tests/uploads/](https://github.com/ogrodnek/pyview/tree/9b32095/tests/uploads)

### Inferences
- A form library should model upload fields as **references to an `UploadConfig`**, validated separately (entry errors, constraints) and merged into the form's error display. The pydantic model would receive consumed-file metadata after `consume_uploads()`, not the file itself.
- If the library prefixes input names (`profile[avatar]`), `maybe_process_uploads` will not find the config unless the upload is also named `profile[avatar]`, because `config_for_name(_target)` does an exact string match and `live_file_input` uses `name="{config.name}"`. Either keep upload inputs unprefixed or change the lookup to use the `data-phx-upload-ref` keys already present in `payload["uploads"]`. Iterating `payload["uploads"]` by ref with `config_for_ref` is more robust.
- `maybe_process_uploads` runs before the handler and before any form decoding, so upload registration is independent of a form library as long as `_target` semantics are kept.

### Gaps
- I did not trace the external (S3) upload path's interplay with forms beyond the preflight code. See [docs/features/file-uploads/external.md](https://github.com/ogrodnek/pyview/blob/9b32095/docs/features/file-uploads/external.md).

---

## 9. Phoenix JS client: version and form behaviours pyview inherits

### Takeaway
pyview bundles **phoenix_live_view 0.20.17** (pre-1.0) with `phoenix` 1.8.9. On phx-change the client sends:
- `type: "form"`;
- `value`, the URL-encoded `FormData` with files removed, plus `phx-value-*` meta from the form and a `_target`;
- `uploads` and `cid`.

An input with its own `phx-change` sends only its own name. Submit sends the whole form plus the submitter's name/value, with no `_target`.

**`_unused_` params do not exist in 0.20.17.** They arrived in LV 1.0, which also removed `phx-feedback-for`. The 0.20 client still implements `phx-feedback-for` by toggling a `phx-no-feedback` class, but pyview ships no CSS for that class, so the attributes in the examples have no visible effect.

Form recovery (`phx-auto-recover`) is purely client-driven: on rejoin, the client re-sends each recoverable form as a phx-change event. pyview needs no special server code, but forms must have an `id`, and state must be rebuilt from the full payload, which `ChangeSet.apply` does not do. `phx-trigger-action` would need a POST route, and LiveView routes are GET-only.

### Cited Findings
- Version pins:
  - `"phoenix_live_view": "^0.20.17"` and `"phoenix": "^1.8.9"` in package.json; the lockfile resolves `phoenix_live_view` to `0.20.17`.
  - The server constant `PHOENIX_LIVEVIEW_VERSION = "0.20.17"`, commented "Must match phoenix_live_view version in pyview/assets/package.json".
  - The bundle reports `return "0.20.17"`.
  — [pyview/assets/package.json](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/assets/package.json), [pyview/assets/package-lock.json L30-33](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/assets/package-lock.json#L30-L33), [pyview/ws_handler.py L22-23](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/ws_handler.py#L22-L23), [app.js L5915](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/static/assets/app.js#L5915)
- The bundle is built with `npx esbuild js/app.js --bundle --target=es2017 --outdir=../static/assets/` (`just build-js`). `app.js` passes `hooks`, `params: {_csrf_token}`, `uploaders` and `dom` from `window.LiveViewConfig`. — [justfile](https://github.com/ogrodnek/pyview/blob/9b32095/justfile), [pyview/assets/js/app.js L59-75](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/assets/js/app.js#L59-L75)
- `serializeForm(form, metadata, onlyNames)`:
  - builds `new FormData(form)`;
  - injects a hidden input for a named submitter;
  - deletes `File` values;
  - appends the remaining entries to a `URLSearchParams`, filtered by `onlyNames` when given;
  - appends each `meta` key;
  - returns `params.toString()`.
  — [app.js L4667-4703](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/static/assets/app.js#L4667-L4703)
- `pushInput`: `if (inputEl.getAttribute(this.binding("change"))) formData = serializeForm(inputEl.form, {_target: opts._target, ...meta}, [inputEl.name]) else formData = serializeForm(inputEl.form, {_target: opts._target, ...meta})`. `meta = this.extractMeta(inputEl.form)`, i.e. the form's `phx-value-*` attributes. The reply callback runs `dom.showError(inputEl, phx-feedback-for, phx-feedback-group)`. — [app.js L5548-5576](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/static/assets/app.js#L5548-L5576)
- In the change listener, `_target` comes from `e.target.name`. Invalid number inputs are skipped (`input.type === "number" && input.validity.badInput`), and the input is marked `PHX_HAS_FOCUSED` before pushing, subject to debounce. — [app.js L6600-6622](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/static/assets/app.js#L6600-L6622)
- In `JS.exec` push, `_target = _target || (dom.isFormInput(sourceEl) ? sourceEl.name : undefined)`. — [app.js L2178-2181](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/static/assets/app.js#L2178-L2181)
- Submit: `pushFormSubmit` calls `serializeForm(formEl, {submitter, ...meta})` with no `_target`. It defers while uploads are in progress or awaiting preflight. `disableForm` handles `phx-disable-with` and adds `phx-submit-loading`. — [app.js L5640-5677](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/static/assets/app.js#L5640-L5677)
- The feedback constants in 0.20.17 are `PHX_FEEDBACK_FOR = "feedback-for"`, `PHX_FEEDBACK_GROUP = "feedback-group"`, `PHX_NO_FEEDBACK_CLASS = "phx-no-feedback"`, `PHX_HAS_FOCUSED`, `PHX_HAS_SUBMITTED`, `PHX_TRIGGER_ACTION = "trigger-action"`, `PHX_AUTO_RECOVER = "auto-recover"`, `PHX_DEBOUNCE`, and `PHX_THROTTLE`. `showError`/`resetForm`/`shouldHideFeedback` match `[name=X]`, `[name="X[]"]` and the feedback group. — [app.js L1844-1876](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/static/assets/app.js#L1844-L1876), [L2670-2710](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/static/assets/app.js#L2670-L2710)
- A grep for `no-feedback` across `.py`, `.html`, `.css` and `.md` in the repo returned nothing, so no CSS hides `.phx-no-feedback` elements. The plants and registration examples use `phx-feedback-for` anyway. — [examples/views/form_validation/plants.html L20](https://github.com/ogrodnek/pyview/blob/9b32095/examples/views/form_validation/plants.html#L20), [examples/views/registration/registration.py L39](https://github.com/ogrodnek/pyview/blob/9b32095/examples/views/registration/registration.py#L39)
- A grep for `_unused` in the bundle returned no matches. — [pyview/static/assets/app.js](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/static/assets/app.js)
- Form recovery in the bundle:
  - `getFormsForRecovery()` (when `joinCount > 0`) collects `form[phx-change]` elements that have an `id` and elements and are not `phx-auto-recover="ignore"`, cloning them.
  - `pushFormRecovery(oldForm, newForm, ...)` uses `phx-auto-recover`, else the `phx-change` event. It picks inputs without their own `phx-change`, clears file inputs, and calls `pushInput(input, ..., phxEvent, {_target: input.name})` with the first non-hidden input. The full form is serialized.
  — [app.js L5760-5781](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/static/assets/app.js#L5760-L5781), [L5806-5816](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/static/assets/app.js#L5806-L5816); recovery is invoked from the join path at [L5067](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/static/assets/app.js#L5067)
- Upstream docs (current main) say:
  - "the payload is pushed to the server with a `"_target"` param in the root payload containing the keyspace of the input name which triggered the change event";
  - "all forms marked with `phx-change` and having `id` attribute will recover input values automatically after the user has reconnected or the LiveView has remounted after a crash. This is achieved by the client triggering the same `phx-change` to the server as soon as the mount has been completed";
  - "provide a `phx-auto-recover` binding on the form to specify a different event to trigger for recovery";
  - "The `phx-trigger-action` attribute can be added to a form to trigger a standard form submit on DOM patch to the URL specified in the form's standard `action` attribute";
  - "LiveView will not send change events from the client when an input is invalid" (number inputs).
  — [phoenix_live_view guides/client/form-bindings.md](https://raw.githubusercontent.com/phoenixframework/phoenix_live_view/main/guides/client/form-bindings.md)
- On LV ≥1.0 (not what pyview bundles), the same guide says: "LiveView sends special parameters on form events starting with `_unused_` to indicate that the input for the specific field has not been interacted with yet", and "`Phoenix.Component.used_input?/1` can be used to filter error messages." — [form-bindings.md](https://raw.githubusercontent.com/phoenixframework/phoenix_live_view/main/guides/client/form-bindings.md)
- LV 1.0.0 was released 2024-12-03. Its changelog says "LiveView 1.0 removes the client-based `phx-feedback-for` annotation for showing and hiding input feedback, such as validation errors", replaced by `Phoenix.Component.used_input?`. The `phx-no-feedback` class was removed, and `phx-page-loading` was removed in favour of `JS.push(page_loading: true)`. — [phoenix_live_view v1.0 CHANGELOG](https://raw.githubusercontent.com/phoenixframework/phoenix_live_view/v1.0/CHANGELOG.md)
- LiveView HTTP routes are GET-only: `self.routes.append(Route(path, auth.wrap(lv), methods=["GET"]))`. A `phx-trigger-action` POST to the LiveView path would 405. There is no helper for it. — [pyview/pyview.py L74-80](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/pyview.py#L74-L80)
- The server side of recovery is simply the ordinary `"event"` branch. pyview has no recovery-specific code, and `grep auto-recover` in `pyview/*.py` finds nothing. — [pyview/ws_handler.py L186-246](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/ws_handler.py#L186-L246)

### Inferences
- **Designing on 0.20.17:**
  - Touched/used tracking must be done server-side, which `ChangeSet` does by recording `_target` keys over time. Alternatively, rely on the client `phx-no-feedback` class plus shipped CSS.
  - The server-side approach survives an LV upgrade.
  - After an upgrade to LV ≥1.0, the library could read `_unused_<name>` keys, which have exact Phoenix `used_input?` semantics. A design that abstracts "used" behind one function (as Phoenix does) supports both.
- **Recovery:** the library's change handler must be **idempotent over the full payload**. It should re-derive the whole form state from all submitted keys, not just `_target`, so recovery restores every field. Forms rendered by the library should always get a stable `id` so recovery is on by default. Note that `_target` during recovery is the first non-hidden input, not a field the user actually touched. A touched-tracker keyed on `_target` will therefore mark that field as used on reconnect, a minor false positive.
- **Debounce/throttle** are pure client attributes (`phx-debounce="300"|"blur"`, `phx-throttle`). A form helper should just let callers pass them per field or per form.
- **Upgrade risk:** the pyview README and constants tie the server to 0.20.17 (`liveview_version` mismatch logs a console error, [app.js L4858-4871](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/static/assets/app.js#L4858-L4871)). A form library should not assume 1.x behaviour, but should be forward compatible with it.

### Gaps
- hexdocs.pm was blocked by the egress proxy, and the GitHub MCP could not read `phoenixframework/phoenix_live_view`. Upstream quotes therefore come from raw.githubusercontent.com copies of current `main` and the `v1.0` branch CHANGELOG, not from the 0.20.17 tag docs. 0.20.17 behaviour was verified directly from the bundled `app.js` instead.
- I did not find a date-stamped statement of when `_unused_` was introduced (1.0.0-rc.x vs 1.0.0). The v1.0 CHANGELOG summary mentions `used_input?` together with the `phx-feedback-for` removal.

---

## 10. Project conventions (Python version, dependencies, testing, style)

### Takeaway
- **Runtime:** Python ≥3.11, with CI on 3.11 through 3.15 (3.15 allowed to fail).
- **Pydantic:** already a hard dependency (`pydantic>=2.11,<3`), and the classifiers include `Framework :: Pydantic`.
- **Tooling:** uv build backend; pytest with `asyncio_mode = "auto"` and class-based tests plus fixtures; ruff (line length 100, py311 target, many rule sets, `Optional[X]` style kept); pyright.
- **t-string code:** must be excluded from ruff and pyright and skipped by tests on Python below 3.14.
- **Libraries:** stdlib dataclasses are used heavily for contexts; pydantic is used for upload models and the changeset.

### Cited Findings
- `pyproject.toml`:
  - `requires-python = ">=3.11"`;
  - dependencies `starlette>=0.50.0,<2`, `wsproto`, `APScheduler>=3.11.0,<4`, `markupsafe>=3.0.2,<4`, `itsdangerous`, `pydantic>=2.11,<3`, `click`;
  - dev group: pytest 9, ruff ≥0.14, pyright, pytest-cov, pytest-asyncio;
  - `[tool.pytest.ini_options] asyncio_mode = "auto"`;
  - ruff `line-length = 100`, `target-version = "py311"`, selects `E,W,F,I,N,UP,B,C4,SIM,PLC0415` and ignores `UP007`/`UP045` (keep `Optional[X]` and `Union`) and `B008` (for `Depends()`);
  - pyright and ruff `exclude` lists enumerate t-string files such as `pyview/template/template_view.py`, `pyview/components/slots.py` and `tests/test_live_view_template.py`.
  — [pyproject.toml](https://github.com/ogrodnek/pyview/blob/9b32095/pyproject.toml)
- CI matrix `python-version: ["3.11", "3.12", "3.13", "3.14", "3.15"]` with `continue-on-error` for 3.15. Steps: `uv sync --group dev`, `uv run pytest --cov --cov-branch`, the JS uploader tests `npm test --prefix pyview/assets` on 3.14, and `uv run pyright`. — [.github/workflows/test.yml L16-55](https://github.com/ogrodnek/pyview/blob/9b32095/.github/workflows/test.yml)
- t-string tests are skipped below 3.14 via `pytest_ignore_collect` (by filename) and `pytest_collection_modifyitems`. — [tests/conftest.py](https://github.com/ogrodnek/pyview/blob/9b32095/tests/conftest.py)
- The justfile has `test: uv run pytest -vvvs`, `type-check: uv run pyright`, `lint: uv run ruff check .`, `format: uv run ruff format .`, and `build-js` (esbuild). — [justfile](https://github.com/ogrodnek/pyview/blob/9b32095/justfile)
- The test style is pytest classes with docstrings, fixtures returning `Binder()`/`BindContext(...)`, `MagicMock` sockets, and `@dataclass` definitions inside tests. — [tests/binding/test_binder.py L1-50](https://github.com/ogrodnek/pyview/blob/9b32095/tests/binding/test_binder.py#L1-L50)
- Public exports are curated in `pyview/__init__.py` (`LiveView`, `LiveViewSocket`, `Depends`, `Session`, `LiveComponent`, `Stream`, `js`, and so on). Changesets and uploads are imported from submodules. — [pyview/__init__.py](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/__init__.py)
- Vendored code (ibis, flet pubsub) lives under `pyview/vendor/`, with relaxed ruff rules. — [pyproject.toml per-file-ignores](https://github.com/ogrodnek/pyview/blob/9b32095/pyproject.toml)

### Inferences
- A new `pyview.forms` (or rewritten `pyview.changesets`) package can use pydantic v2 APIs such as `TypeAdapter`, `ValidationError.errors()` with full `loc` tuples, and `model_fields` without adding dependencies.
- Dataclass support could go through `pydantic.TypeAdapter(dataclass_cls)` or `pydantic.dataclasses`, which unifies the two worlds the binder and the changeset split today.
- Any t-string rendering helpers must live in files excluded from ruff and pyright, or build `Template` objects without t-string literal syntax (e.g. `Template(*parts)`), so they import on 3.11–3.13. The core must stay importable on 3.11.

### Gaps
- No `CONTRIBUTING` or code-style document was found beyond `pyproject.toml` and the justfile.

---

## 11. Gaps, pain points and extension points for complex, nested or conditional forms (synthesis)

### Takeaway
Today pyview gives you:
- flat `parse_qs` dicts;
- a strict, fatal, root-level dataclass binder;
- a flat, one-field-at-a-time pydantic `ChangeSet`;
- hand-written Ibis filters or t-string helpers for markup.

Nothing handles nested paths, indexed lists, add/remove rows, conditional sub-models, multi-value fields, edit-existing data, submit-time "show all errors", or form recovery correctness. The concrete hook points are listed below.

### Cited Findings
- **Decode hook:** the form branch `value = parse_qs(value)` at [ws_handler.py L189-191](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/ws_handler.py#L189-L191) is the single choke point for all form payloads to LiveViews and components.
- **Bind hooks:**
  - `Binder._resolve_param` dataclass branch, [binder.py L143-149](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/binding/binder.py#L143-L149);
  - `ConverterRegistry.convert` fallback, [converters.py L58-63](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/binding/converters.py#L58-L63);
  - `InjectableRegistry.resolve` name/type/extra lookup, [injectables.py L44-70](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/binding/injectables.py#L44-L70);
  - `BindContext.extra`, [context.py L15-35](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/binding/context.py#L15-L35).
- **Dispatch hooks:**
  - `call_handle_event`, [helpers.py L117-144](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/binding/helpers.py#L117-L144);
  - `BaseEventHandler.handle_event`, [BaseEventHandler.py L74-99](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/events/BaseEventHandler.py#L74-L99);
  - the `@event` decorator, which stores metadata on the function (`func._event_names`) and so could carry form metadata too, [BaseEventHandler.py L12-39](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/events/BaseEventHandler.py#L12-L39);
  - `ComponentsManager.handle_event`, [manager.py L211-240](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/components/manager.py#L211-L240).
- **Render hooks:**
  - `@filters.register` for Ibis, [ibis/filters.py L16-40](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/vendor/ibis/filters.py#L16-L40);
  - `__html__` objects and nested `Template`s for t-strings, [live_view_template.py L163-171](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/template/live_view_template.py#L163-L171);
  - `context_processor` for auto-injecting helpers into Ibis context, [context_processor.py](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/template/context_processor.py);
  - `live_component` and `slots` for stateful sub-forms, [live_view_template.py L330-342](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/template/live_view_template.py#L330-L342), [slots.py L48-73](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/components/slots.py#L48-L73).
- **State:** `socket.context` holds whatever the view wants (dataclass or TypedDict) and is serialized for Ibis via `serialize()` (dataclass fields plus `@property` names). A form object in context is rendered by attribute access. — [serializer.py](https://github.com/ogrodnek/pyview/blob/9b32095/pyview/template/serializer.py)

### Inferences
Pain points, ranked for nested, conditional or dynamic forms:
1. **No nested decoding.** `a[b][0][c]` keys are literal strings, and `[]` suffixes are not stripped (§1).
2. **Blank values dropped**, so "cleared" looks like "absent" (§1).
3. **Fatal binding errors** on partial data during phx-change (§3).
4. **Pydantic models not bindable** and dataclasses not validatable (§2, §3).
5. **`ChangeSet` is flat, first-value-only and `_target`-only**, breaks on submit and recovery, collapses error locs to `loc[0]`, and has no "submitted" state (§2).
6. **No markup helpers** in core. Attribute rendering (boolean attrs, `selected`/`checked`, ids and names for nested paths) is hand-written, and t-strings have no attribute awareness (§4, §5).
7. **No list-manipulation protocol** (add/remove/reorder rows). Phoenix ≥0.20's `sort_param`/`drop_param` convention for `inputs_for` has no counterpart here. This was not verified in the 0.20.17 client, which does not need to know about it since it is server-side name convention only.
8. **Components don't bind params** (open PR #126).
9. **Uploads keyed by exact `_target` name**, which conflicts with prefixed names (§8).
10. **`phx-feedback-for` has no CSS**, and LV 1.0's `_unused_` is unavailable (§9).
11. **Docs are inaccurate** in several places (§6).

Minimal-disruption strategy these findings suggest:
- Add a decoder (raw string → nested dict/list, keeping blanks and multi-values).
- Add a form/changeset object that validates with pydantic `TypeAdapter` (covering dataclasses too), keeps full-path errors plus a used-fields set (from `_target` history, or `_unused_` when available), and exposes a field tree for rendering.
- Wire it through an injectable/annotation in the binder, so `@event async def validate(self, socket, form: Form[Signup])` never raises.
- Ship renderers for both Ibis (filters or context objects) and t-strings (functions returning `Template`/`Markup`).

### Gaps
- I did not verify whether Phoenix 0.20.17's `inputs_for`-style `sort_param`/`drop_param` idioms need any client support. They are a server-side HEEx/Ecto convention, and the 0.20.17 bundle was not searched for them.
