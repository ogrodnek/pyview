"""The changeset: raw params in, typed model or path-keyed errors out.

Four ideas carry the whole design, each stolen from somewhere that proved it.

1. **The state is the raw params tree, never the parsed model.**
   You have to redisplay ``"abc"`` in a number field after it fails to parse, so
   the model cannot be the source of truth. Colander names the three
   representations pstruct/cstruct/appstruct; Ecto keeps ``params`` beside
   ``changes``; Django keeps ``data`` beside ``cleaned_data``. Same idea.

2. **Errors are addressed by path, and so is everything else.**
   ``("pets", "0", "age")`` names an error, a value, a DOM id and an input name.
   One address space means a deeply nested error lands next to its input for free.

3. **An error that exists is not automatically an error you show.**
   Ecto gates display on ``changeset.action``; Phoenix 1.0 added ``used_input?``;
   React Hook Form calls it ``touchedFields``; GOV.UK calls it "reward early,
   punish late". A form that turns red before you have typed anything is a bug.

4. **State and view are two objects.**
   ``Changeset`` carries the API (``validate``, ``submit``, ``valid``, ``errors``);
   ``changeset.form`` is a namespace whose every name is a field. Merging the two
   is what gives WTForms its reserved-word problem, where a field called ``data``
   or ``errors`` quietly shadows the framework. Ecto splits it the same way:
   the changeset is the state, ``to_form/1`` produces the thing you render.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, Iterable, Iterator, Mapping, Optional, TypeVar, Union

from pydantic import BaseModel, ValidationError

from .errors import FormUsageError, format_keys, unknown_field
from .params import normalize_payload
from .paths import Path, canon, get_in, unwrap
from .schema import (
    FieldSpec,
    check_aliases,
    clean_loc,
    field_specs,
    prepare,
    sub_model,
    union_variants,
    variant_specs,
)

__all__ = [
    "Changeset",
    "FormError",
    "changeset",
    "FormView",
    "FormField",
    "FieldList",
    "Result",
    "errors_of",
    "name_of",
    "path_of",
]

M = TypeVar("M", bound=BaseModel)

#: pydantic error types that mean "you have not filled this in yet" rather than
#: "what you typed is wrong". Held back until submit so an untouched form is calm.
_ABSENCE = frozenset(
    {
        "missing",
        "missing_argument",
        "model_attributes_type",
        # "you have not picked a variant yet" for a blank discriminated sub-form
        "union_tag_not_found",
    }
)


@dataclass(frozen=True)
class FormError:
    """One error, with its interpolation data kept intact.

    Ecto stores ``{field, {"must be at least %{count} characters", count: 3}}``
    rather than a finished English sentence, because that is the only shape you
    can translate or re-word later. pydantic already hands us the same thing -
    ``type``, ``msg`` and ``ctx`` - so we keep all three instead of flattening
    to a string on the way in.
    """

    msg: str
    type: str = ""
    ctx: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.msg

    def __eq__(self, other: Any) -> bool:
        # compares equal to its own message, so `"..." in field.errors` works
        if isinstance(other, str):
            return self.msg == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.msg)


@dataclass(frozen=True)
class Result(Generic[M]):
    """What :meth:`Changeset.submit` gives you back."""

    ok: bool
    value: Optional[M] = None

    def __bool__(self) -> bool:
        return self.ok


class Changeset(Generic[M]):
    """A pydantic model plus the in-flight, possibly-invalid user input for it.

    ::

        cs = Changeset(Signup)                 # blank
        cs = Changeset(Signup, data=existing)  # editing something

        cs.validate(payload)                   # phx-change
        if result := cs.submit(payload):       # phx-submit
            create_user(result.value)          # a real, typed Signup
    """

    def __init__(
        self,
        model: type[M],
        data: Union[M, dict[str, Any], None] = None,
        *,
        name: Optional[str] = None,
        fields: Optional[Iterable[str]] = None,
    ):
        _check_usable(model)
        _check_model(model)

        self.model = model
        self.name = name if name is not None else default_name(model)
        self.action: Optional[str] = None

        #: Once a submit has been attempted, errors stay visible. Without the
        #: latch the next keystroke sets action back to "validate" and quietly
        #: un-reveals every error the user has not personally touched - the form
        #: appears to forget it was rejected.
        self.submitted: bool = False
        self.touched: set[Path] = set()

        #: High-water mark per repeated field, so a dropped row's index is never
        #: handed out again. Reusing it makes the new row inherit the old one's
        #: DOM state and its aria wiring.
        self._row_seq: dict[str, int] = {}

        #: Trusted starting point: whatever we were editing. Never comes from
        #: the browser. Ecto calls this `data` and keeps it strictly apart from
        #: `params` for exactly this reason.
        self.data: dict[str, Any] = _as_params(data) if data is not None else {}

        #: Untrusted: the last payload the browser sent, verbatim.
        self.params: dict[str, Any] = dict(self.data)

        #: Which fields the browser is allowed to set. Anything outside this set
        #: keeps its value from `data`, so a hidden `role` input in a crafted
        #: payload cannot promote anyone. Ecto's `cast/3` permitted list.
        self.permitted: Optional[set[str]] = set(fields) if fields is not None else None

        self._errors: dict[Path, list[FormError]] = {}
        self._absent: set[Path] = set()
        self._value: Optional[M] = None
        self._specs = field_specs(model)

        if self.permitted is not None:
            known = set(self._specs) | {spec.name for spec in self._specs.values()}
            for name in sorted(self.permitted - known):
                raise unknown_field(model.__name__, name, sorted(known), "fields=")

        self._revalidate()

    # -- lifecycle ---------------------------------------------------------

    def validate(self, payload: dict[str, Any]) -> Changeset[M]:
        """Handle a ``phx-change``. Re-validates; shows errors only where touched."""
        normalized = normalize_payload(payload)
        self.params = self._cast(payload)

        # The client serializes the whole form every time; `_target` only names
        # the input that fired. It decides what to *show*, never what to validate.
        target = normalized.get("_target")
        if target:
            path = canon(_target_path(target, self.name))
            for i in range(1, len(path) + 1):
                self.touched.add(path[:i])

        self.action = "validate"
        self._revalidate()
        return self

    def submit(self, payload: dict[str, Any]) -> Result[M]:
        """Handle a ``phx-submit``. Shows every error; returns the typed model if valid.

        A submit carrying a row-mutation intent (see :meth:`apply_intent`) is not
        a real submit: the user pressed "add a pet", so keep their input, add the
        row, and do not light the form up with errors.
        """
        self.params = self._cast(normalize_payload(payload))

        if self.apply_intent(payload):
            self.action = "validate"
            return Result(False, None)

        self.action = "submit"
        self.submitted = True
        self._revalidate()
        return Result(self.valid, self._value)

    def reveal(self) -> Changeset[M]:
        """Show every error without submitting."""
        self.action = "submit"
        self.submitted = True
        return self

    def add_error(self, path: Union[str, tuple[str, ...]], message: str) -> Changeset[M]:
        """Attach a server-side error - a uniqueness check, a payment decline.

        These arrive after validation, from a database or a remote API, and have
        to land in the same error set as everything else so they render in the
        same place. Ecto does this with ``add_error/3`` and constraint errors.
        """
        key = (path,) if isinstance(path, str) else path
        if key and str(key[0]) not in self._by_wire_name():
            raise unknown_field(self.model.__name__, str(key[0]), self._by_wire_name(), "add_error")
        self._errors.setdefault(canon(key), []).append(FormError(msg=message, type="custom"))
        self.action = self.action or "validate"
        self.touched.add(canon(key))
        return self

    #: Reserved input name carrying a list mutation. See :meth:`apply_intent`.
    INTENT = "_intent"

    def apply_intent(self, payload: dict[str, Any]) -> bool:
        """Apply an ``add``/``drop`` intent that rode along with the form data.

        Borrowed from Conform (the Remix form library), which is the only design
        in this space that is natively server-shaped. A row button is a real
        submit button carrying a reserved name and an encoded instruction::

            <button type="submit" name="_intent" value="add:pets">Add a pet</button>
            <button type="submit" name="_intent" value="drop:pets:0">Remove</button>

        Because it is part of the form, the browser sends *everything the user
        has typed* along with it. A ``phx-click`` handler cannot do that - its
        payload carries only the button's own values - so adding a row while a
        debounce is still pending would silently discard the pending keystrokes.
        It also degrades: with JavaScript off, this is just a form post.

        Returns True if an intent was found and applied.
        """
        intent = normalize_payload(payload).get(self.INTENT)
        if not isinstance(intent, str) or not intent:
            return False

        op, _, rest = intent.partition(":")
        field, _, index = rest.partition(":")

        if op == "add" and field:
            self.add_row(field)
            return True
        if op == "drop" and field and index:
            self.drop_row(field, index)
            return True
        return False

    def _check_payload(self, normalized: dict[str, Any]) -> None:
        """Catch a payload this form's inputs could not have produced.

        A form named ``signup`` renders inputs called ``signup[...]``, so its data
        arrives under that key. If it is absent the form would silently reset to
        its starting values on every keystroke, which looks like "validation does
        nothing" and is nearly impossible to work back from.
        """
        if self.name is None or self.name in normalized:
            return
        found = format_keys(normalized)
        if found is None:
            return
        raise FormUsageError(
            f"this changeset is named `{self.name}`, so it expects its inputs to be "
            f"named `{self.name}[...]`, but the payload only contains {found}.\n"
            f"Either render the inputs from this changeset (`{self.name}.form.<field> | input`), "
            f"or construct it with the name your inputs already use: "
            f'Changeset({self.model.__name__}, name="...")'
        )

    def _cast(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Take the form's subtree out of the payload, honouring the whitelist."""
        normalized = normalize_payload(payload)
        self._check_payload(normalized)
        incoming = unwrap(normalized, self.name)
        if self.permitted is None:
            return _overlay(self.data, incoming)
        allowed = {k: v for k, v in incoming.items() if k in self.permitted}
        return _overlay(self.data, allowed)

    def _revalidate(self) -> None:
        self._errors = {}
        self._absent = set()
        try:
            self._value = self.model.model_validate(prepare(self.model, self.params))
        except ValidationError as exc:
            self._value = None
            for err in exc.errors():
                path = clean_loc(self.model, err["loc"], self.params)
                self._errors.setdefault(path, []).append(_to_form_error(err))
                if err["type"] in _ABSENCE:
                    self._absent.add(path)

    # -- state -------------------------------------------------------------

    @property
    def valid(self) -> bool:
        return self._value is not None

    @property
    def value(self) -> Optional[M]:
        """The validated model, or ``None`` while the form is invalid."""
        return self._value

    @property
    def form(self) -> FormView:
        """The render-side view: a namespace where every name is a field."""
        return FormView(self, (), self._specs)

    @property
    def errors(self) -> list[FormError]:
        """Form-level errors: whole-model validators, which pydantic reports at ``()``."""
        return self.errors_at(())

    def errors_under(self, prefix: Path = ()) -> list[tuple[Path, FormError]]:
        """Every *shown* error at or below ``prefix``, in field order.

        This is what a fieldset needs to know it contains a problem, what a list
        container needs to mark a bad row, and what the error summary iterates.
        Conform builds the same thing with `isPathPrefix`; digestive-functors
        calls it `subView`.
        """
        out: list[tuple[Path, FormError]] = []
        for path in self._errors:
            if path[: len(prefix)] != prefix:
                continue
            out.extend((path, e) for e in self.errors_at(path))
        return out

    def all_errors(self) -> dict[Path, list[FormError]]:
        """Every error, shown or not. For tests and for an error summary."""
        return dict(self._errors)

    def value_at(self, path: Path) -> Any:
        """Raw value for redisplay. Never coerced, so bad input survives a round trip."""
        raw = get_in(self.params, path)
        return "" if raw is None else raw

    def errors_at(self, path: Path) -> list[FormError]:
        """The errors it is currently appropriate to *show* at ``path``."""
        found = self._errors.get(path)
        if not found:
            return []
        if self.action == "submit" or self.submitted:
            return found
        if self.action is None:
            return []
        if path in self._absent and path not in self.touched:
            return []
        return found if path in self.touched else []

    # -- dynamic rows ------------------------------------------------------

    def _by_wire_name(self) -> dict[str, FieldSpec]:
        return {spec.name: spec for spec in self._specs.values()}

    def _repeated(self, name: str) -> FieldSpec:
        """Resolve a repeated field, or explain why it is not one."""
        spec = self._specs.get(name) or self._by_wire_name().get(name)
        if spec is None:
            raise unknown_field(self.model.__name__, name, self._by_wire_name(), "row operation")
        if not spec.repeated:
            raise FormUsageError(
                f"row operation: `{self.model.__name__}.{spec.attr or spec.name}` is not a list, "
                f"so it has no rows to add or remove. Row operations apply to fields "
                f"annotated `list[SomeModel]`."
            )
        return spec

    def _wire(self, name: str) -> str:
        """Accept either the Python attribute name or the wire name.

        They differ only for aliased fields, and a caller should not have to know
        or care which one a given field uses.
        """
        spec = self._specs.get(name)
        return spec.name if spec else name

    def add_row(self, name: str, initial: Optional[dict[str, Any]] = None) -> Changeset[M]:
        """Append a row to a repeated field, server-side, with no custom JS."""
        name = self._repeated(name).name
        rows = _as_indexed(self.params.get(name))
        highest = max((int(k) for k in rows if k.isdigit()), default=-1)
        nxt = max(highest + 1, self._row_seq.get(name, 0))
        self._row_seq[name] = nxt + 1
        next_index = str(nxt)
        rows[next_index] = initial or {}
        self.params[name] = rows
        self._revalidate()
        return self

    def drop_row(self, name: str, index: Union[str, int]) -> Changeset[M]:
        """Remove a row by its rendered index. Siblings keep their indexes."""
        name = self._repeated(name).name
        rows = _as_indexed(self.params.get(name))
        rows.pop(str(index), None)
        self.params[name] = rows
        prefix = (name, str(index))
        self.touched = {p for p in self.touched if p[: len(prefix)] != prefix}
        self._revalidate()
        return self

    def __repr__(self) -> str:
        return f"<Changeset {self.model.__name__} valid={self.valid} action={self.action}>"


def changeset(
    model: type[M], data: Union[M, dict[str, Any], None] = None, **kw: Any
) -> Changeset[M]:
    """Shorthand for ``Changeset(model, data)``."""
    return Changeset(model, data, **kw)


# ---------------------------------------------------------------------------
# render-side views
# ---------------------------------------------------------------------------
#
# One rule governs this section: **a namespace has no attributes of its own.**
#
# WTForms merges the two - `form.email` is a field but `form.data`, `form.errors`
# and `form.validate` are the framework - so a model with a field called `data`
# breaks in a way that is hard to see. Django sidesteps it by never using
# attribute access for fields (`form["email"]`). Phoenix sidesteps it with
# Elixir's separate syntaxes (`f.name` is the struct, `f[:name]` is the field).
#
# Python has no separate syntax, and pyview's template engine resolves `a.b` as
# getattr-then-getitem, so a colliding name would silently render the framework's
# value instead of the user's. Making namespaces pure removes the possibility:
# on a FormView every name is a field, always. Group-level metadata is reached
# with a function (`errors_of(form.address)`) or a template filter
# (`{{ form.address | errors }}`) instead of an attribute.
#
# Leaves are different: nothing is ever looked up *inside* a FormField, so it is
# free to carry `.value`, `.errors`, `.label` and friends.


class FormView:
    """A namespace whose every public name is a field.

    ``form.email``, ``form.address.city``, ``for pet in form.pets``. Has no
    attributes of its own, so no model field can be shadowed by the framework.
    """

    __slots__ = ("_cs", "_path", "_specs")

    def __init__(self, cs: Changeset[Any], path: Path, specs: dict[str, FieldSpec]):
        object.__setattr__(self, "_cs", cs)
        object.__setattr__(self, "_path", path)
        object.__setattr__(self, "_specs", specs)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        specs = object.__getattribute__(self, "_specs")
        try:
            spec = specs[name]
        except KeyError:
            raise AttributeError(
                f"no field {name!r} on this form. Available: {', '.join(specs)}"
            ) from None
        return _bind(
            object.__getattribute__(self, "_cs"),
            object.__getattribute__(self, "_path"),
            spec,
        )

    def __getitem__(self, name: str) -> Any:
        return getattr(self, name)

    def __iter__(self) -> Iterator[Any]:
        """Every field in declaration order - what a default render walks."""
        cs = object.__getattribute__(self, "_cs")
        path = object.__getattribute__(self, "_path")
        return (_bind(cs, path, spec) for spec in object.__getattribute__(self, "_specs").values())

    def __len__(self) -> int:
        return len(object.__getattribute__(self, "_specs"))

    def __repr__(self) -> str:
        path = object.__getattribute__(self, "_path")
        cs = object.__getattribute__(self, "_cs")
        specs = object.__getattribute__(self, "_specs")
        return f"<FormView {'.'.join(path) or cs.name} fields={list(specs)}>"


def _bind(cs: Changeset[Any], prefix: Path, spec: FieldSpec) -> Any:
    path = (*prefix, spec.name)

    if spec.variants and spec.discriminator:
        # A conditional sub-form. Which arm we show is decided by the value the
        # user currently has selected, read straight out of the raw params - so
        # flipping the discriminator swaps the fields on the next keystroke with
        # no extra wiring in the view.
        tag = cs.value_at((*path, spec.discriminator))
        return FormView(cs, path, variant_specs(spec, tag))

    if spec.nested is not None and spec.repeated:
        return FieldList(cs, path, spec)
    if spec.nested is not None:
        return FormView(cs, path, field_specs(spec.nested))
    return FormField(cs, path, spec)


class FormField:
    """One leaf input: everything a template needs to render it and its error."""

    __slots__ = ("changeset", "path", "spec")

    def __init__(self, cs: Changeset[Any], path: Path, spec: FieldSpec):
        self.changeset = cs
        self.path = path
        self.spec = spec

    @property
    def name(self) -> str:
        """The ``name`` attribute: ``owner[pets][0][age]``."""
        return encode_path((*_root(self.changeset), *self.path))

    @property
    def id(self) -> str:
        """A DOM id from the same path, so ``<label for>`` always matches."""
        return "_".join((*_root(self.changeset), *self.path))

    @property
    def error_id(self) -> str:
        """The id of this field's error node, for ``aria-describedby``."""
        return f"{self.id}_error"

    @property
    def hint_id(self) -> str:
        """The id of this field's help text, for ``aria-describedby``."""
        return f"{self.id}_help"

    @property
    def describedby(self) -> Optional[str]:
        """Exactly what belongs in ``aria-describedby``, hint before error.

        Exposed as one property so a hand-written template cannot mis-wire it:
        pointing at an id that is not on the page is worse than omitting it.
        """
        ids = [self.hint_id] if self.spec.help else []
        if self.errors:
            ids.append(self.error_id)
        return " ".join(ids) or None

    @property
    def value(self) -> Any:
        return self.changeset.value_at(self.path)

    @property
    def errors(self) -> list[FormError]:
        return self.changeset.errors_at(self.path)

    @property
    def invalid(self) -> bool:
        return bool(self.errors)

    @property
    def label(self) -> str:
        return self.spec.label

    @property
    def required(self) -> bool:
        return self.spec.required

    @property
    def widget(self) -> str:
        return self.spec.widget

    @property
    def choices(self) -> list[tuple[str, str]]:
        return self.spec.choices or []

    @property
    def help(self) -> Optional[str]:
        return self.spec.help

    @property
    def attrs(self) -> dict[str, Any]:
        return dict(self.spec.attrs)

    def __repr__(self) -> str:
        return f"<FormField {self.name} value={self.value!r} errors={self.errors}>"


class FieldList:
    """A repeated nested model: ``for pet in form.pets``.

    Not a namespace - you index or iterate it - so it is free to carry its own
    attributes. Rows are keyed by their *rendered* index rather than by position,
    so removing one does not renumber its siblings, which keeps LiveView's diff
    small and stops a row's inputs from inheriting the previous row's DOM state.
    """

    __slots__ = ("changeset", "path", "spec")

    def __init__(self, cs: Changeset[Any], path: Path, spec: FieldSpec):
        self.changeset = cs
        self.path = path
        self.spec = spec

    @property
    def name(self) -> str:
        return encode_path((*_root(self.changeset), *self.path))

    @property
    def label(self) -> str:
        return self.spec.label

    @property
    def errors(self) -> list[FormError]:
        return self.changeset.errors_at(self.path)

    def _keys(self) -> list[str]:
        rows = self.changeset.value_at(self.path)
        if isinstance(rows, dict):
            return sorted((k for k in rows if str(k).isdigit()), key=int)
        if isinstance(rows, list):
            return [str(i) for i in range(len(rows))]
        return []

    def _row(self, key: str) -> FormView:
        assert self.spec.nested is not None
        return FormView(self.changeset, (*self.path, str(key)), field_specs(self.spec.nested))

    def __iter__(self) -> Iterator[FormView]:
        return (self._row(k) for k in self._keys())

    def __getitem__(self, index: Union[str, int]) -> FormView:
        return self._row(str(index))

    def __len__(self) -> int:
        return len(self._keys())

    def __bool__(self) -> bool:
        return bool(self._keys())

    @property
    def indexes(self) -> list[str]:
        """The rendered index of each row - what a remove button sends back."""
        return self._keys()

    @property
    def rows(self) -> list[tuple[str, FormView]]:
        """``(index, row)`` pairs, for templates that need the index."""
        return [(k, self._row(k)) for k in self._keys()]

    @property
    def empty_row(self) -> FormView:
        """A template row for JS-side cloning, indexed with a placeholder."""
        return self._row("__index__")

    def __repr__(self) -> str:
        return f"<FieldList {self.name} rows={len(self)}>"


# -- functional accessors ---------------------------------------------------
# The escape hatch that lets FormView stay pure. Also registered as template
# filters, so a template writes `{{ form.address | errors }}`.


def path_of(target: Any) -> Path:
    if isinstance(target, FormView):
        return object.__getattribute__(target, "_path")
    return target.path


def changeset_of(target: Any) -> Changeset[Any]:
    if isinstance(target, FormView):
        return object.__getattribute__(target, "_cs")
    return target.changeset


def errors_of(target: Any) -> list[FormError]:
    """Errors for a field, a nested group, or a whole form."""
    if isinstance(target, Changeset):
        return target.errors
    return changeset_of(target).errors_at(path_of(target))


def name_of(target: Any) -> str:
    """The ``name`` attribute for anything addressable."""
    cs = changeset_of(target)
    return encode_path((*_root(cs), *path_of(target)))


def _root(cs: Changeset[Any]) -> tuple[str, ...]:
    return (cs.name,) if cs.name else ()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _to_form_error(err: Mapping[str, Any]) -> FormError:
    """Normalise one pydantic error into something renderable and serializable.

    Two fixes: pydantic prefixes messages raised from a validator with
    ``"Value error, "`` (and ``"Assertion failed, "`` for asserts), which is
    framework vocabulary leaking into user-facing copy; and ``ctx`` carries the
    live exception object, which cannot be serialized and keeps a traceback alive.
    """
    ctx = dict(err.get("ctx") or {})
    raised = ctx.pop("error", None)
    msg = str(raised) if raised is not None else err["msg"]
    ctx = {k: v for k, v in ctx.items() if isinstance(v, (str, int, float, bool, type(None)))}
    return FormError(msg=msg, type=err["type"], ctx=ctx)


def default_name(model: type[BaseModel]) -> str:
    """``Signup`` -> ``"signup"``; ``UserProfile`` -> ``"user_profile"``."""
    out: list[str] = []
    for i, ch in enumerate(model.__name__):
        if ch.isupper() and i:
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


def encode_path(path: Path) -> str:
    if not path:
        return ""
    head, *rest = path
    return head + "".join(f"[{p}]" for p in rest)


def _target_path(target: Any, form_name: Optional[str]) -> list[str]:
    """LiveView's ``_target``, made relative to this form."""
    path = target if isinstance(target, list) else [str(target)]
    if form_name and path and path[0] == form_name:
        return path[1:]
    return path


def _check_usable(model: Any) -> None:
    """Reject things that are not a pydantic model class, in their own words."""
    if isinstance(model, BaseModel):
        raise FormUsageError(
            f"Changeset() takes the model class, not an instance. You passed a "
            f"`{type(model).__name__}` object -- pass the class, and the instance as "
            f"the data to edit:\n\n"
            f"    Changeset({type(model).__name__}, data=that_instance)"
        )
    if not (isinstance(model, type) and issubclass(model, BaseModel)):
        extra = ""
        if hasattr(model, "__dataclass_fields__"):
            extra = (
                " Dataclasses are not supported yet; pydantic can adopt one with "
                "`pydantic.dataclasses.dataclass`, or declare the model as a BaseModel."
            )
        raise FormUsageError(
            f"Changeset() needs a pydantic BaseModel subclass, but got "
            f"`{getattr(model, '__name__', type(model).__name__)}`.{extra}"
        )


def _check_model(model: type[BaseModel], seen: Optional[set[type]] = None) -> None:
    """Reject models a form cannot render unambiguously.

    Caught at construction rather than at render, because the failure is
    otherwise silent: an untagged union makes pydantic report the errors from
    every variant at once, so an email input would show "not a valid phone
    number" underneath it.
    """
    seen = seen or set()
    if model in seen:
        return
    seen.add(model)
    check_aliases(model)

    for name, info in model.model_fields.items():
        variants = union_variants(info.annotation)
        if variants and not getattr(info, "discriminator", None):
            names = ", ".join(v.__name__ for v in variants)
            raise TypeError(
                f"{model.__name__}.{name} is an untagged union of models ({names}).\n"
                f"Forms need a discriminated union so there is one sub-form to render and "
                f"one set of errors to show; pydantic otherwise reports the errors from "
                f"every variant at once. Add a Literal tag and point pydantic at it:\n\n"
                f"    class {variants[0].__name__}(BaseModel):\n"
                f'        kind: Literal["{default_name(variants[0])}"] = '
                f'"{default_name(variants[0])}"\n\n'
                f'    {name}: Annotated[Union[{names}], Field(discriminator="kind")]'
            )

        nested = sub_model(info.annotation)
        if nested is not None:
            _check_model(nested, seen)
        for variant in variants or []:
            _check_model(variant, seen)


def _as_params(data: Union[BaseModel, dict[str, Any]]) -> dict[str, Any]:
    """Render an existing record into the same representation the browser uses.

    Everything becomes a string, because that is what will come back on the next
    keystroke. Keeping the trusted starting point in params-shape means an
    untouched edit form round-trips byte-identically, and one code path reads
    values for display.
    """
    raw = data.model_dump(mode="json") if isinstance(data, BaseModel) else dict(data)
    return _stringify_tree(raw)


def _stringify_tree(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: _stringify_tree(v) for k, v in node.items()}
    if isinstance(node, list):
        return {str(i): _stringify_tree(v) for i, v in enumerate(node)}
    return _stringify(node)


def _overlay(data: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Lay the browser's values over the trusted starting point.

    Only top-level keys the browser actually sent are replaced, wholesale. That
    "wholesale" matters: the client serializes the entire form on every change,
    so an *absent* key means the input is gone (an unchecked checkbox), not that
    it is unchanged. Merging key-by-key here is the bug that makes checkboxes
    impossible to uncheck.
    """
    out = dict(data)
    out.update(incoming)
    return out


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _as_indexed(rows: Any) -> dict[str, Any]:
    """``[a, b]`` -> ``{"0": a, "1": b}``, the on-the-wire shape for repeated fields."""
    if isinstance(rows, dict):
        return dict(rows)
    if isinstance(rows, list):
        return {str(i): v for i, v in enumerate(rows)}
    return {}
