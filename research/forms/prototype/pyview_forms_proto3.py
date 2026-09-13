"""Consolidated spike (v3) implementing the corrected semantics after the critique:

- Params: decoded wire payload with target/intents/meta/unused/recovered (accepts pairs, a wire string,
  or a parse_qs dict); Plug-style bracket grammar; `[]` only as the last segment; dunder segments and
  oversized payloads rejected; `_target` trailing `[]` stripped; 1.x `_unused_` prefix detected on the
  *last* bracket segment; everything outside the form prefix is meta (phx-value-*, _csrf_token, ...).
- Form: Ecto cast/merge semantics (absent key keeps initial data; "" becomes default/None and IS a change),
  whole-model validation, used+action gating (ancestor-of-used rule), variant-named discriminated-union
  inputs (profile[account][business][company]) lifted before validation so switching never pollutes,
  explicit applied intents, submitted_once/just_submitted/changed flags, external errors that survive
  re-validation, SecretStr never echoed.
- Field: sub-fields by attribute/item (digit strings ok); template-facing metadata under `.html`.
"""
from __future__ import annotations

import datetime as dt
import decimal
import enum
import itertools
import re
import types
from dataclasses import dataclass, field
from typing import Any, Generic, Iterable, Literal, Optional, TypeVar, Union, get_args, get_origin
from urllib.parse import parse_qsl

import annotated_types as at
from pydantic import BaseModel, SecretStr, ValidationError
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

Path = tuple[Union[str, int], ...]
M = TypeVar("M", bound=BaseModel)
_KEY_RE = re.compile(r"^([^\[\]]+)((?:\[[^\[\]]*\])*)$")
_DUNDER = re.compile(r"^__.*__$")
INTENT, ROWKEY, UNUSED = "_intent", "_key", "_unused_"
MAX_PAIRS, MAX_DEPTH = 10_000, 32
_counter = itertools.count(1)


# ============================================================== Params (wire -> structure)
@dataclass(frozen=True)
class Intent:
    op: Literal["add", "remove", "move"]
    path: Path
    key: str | None = None
    arg: str | None = None


@dataclass
class Params:
    data: dict                      # nested, under the form prefix, meta-free
    target: Path | None             # e.g. ("addresses", 0, "city"); None on submit
    intents: list[Intent]
    meta: dict                      # _csrf_token, phx-value-*, submitter pairs outside the prefix...
    unused: set[Path]               # from 1.x _unused_ keys
    recovered: bool = False

    @classmethod
    def decode(cls, payload, *, prefix: str, recovered: bool = False) -> "Params":
        pairs = _to_pairs(payload)
        if len(pairs) > MAX_PAIRS:
            raise ValueError("too many form fields")
        root: dict = {}
        meta: dict = {}
        unused: set[Path] = set()
        intents: list[Intent] = []
        target_raw = None
        for key, value in pairs:
            if key == "_target":
                target_raw = value
                continue
            segs = _split_name(key)
            if len(segs) > MAX_DEPTH:
                raise ValueError(f"form key too deep: {key}")
            if any(_DUNDER.match(s) for s in segs):
                raise ValueError(f"illegal segment in {key}")
            if segs[0] != prefix:                       # anything outside the prefix is metadata
                meta.setdefault(key, []).append(value)
                continue
            # 1.x client: user[addresses][0][_unused_city]=  /  user[_unused_tags][]=
            last = segs[-1] if segs[-1] != "" else segs[-2]
            if last.startswith(UNUSED):
                clean = [s for s in segs if s != ""]
                clean[-1] = clean[-1][len(UNUSED):]
                unused.add(_intify(clean[1:]))
                continue
            _insert(root, segs, value, key)
        data = _compact(root).get(prefix, {})
        data, intents = _pop_intents(data, ())
        target = None
        if target_raw:
            tsegs = [s for s in _split_name(target_raw) if s != ""]
            if tsegs and tsegs[0] == prefix:
                target = _intify(tsegs[1:])
            else:
                meta["_target"] = [target_raw]
        # 1.0.6+ client: meta arrives as a JSON key on the event instead of inside the string
        return cls(data, target, intents, meta, unused, recovered)


def _to_pairs(payload) -> list[tuple[str, str]]:
    if isinstance(payload, str):
        return parse_qsl(payload, keep_blank_values=True)
    if isinstance(payload, dict):                       # parse_qs shape {k: [v, ...]} or {k: v}
        out = []
        for k, v in payload.items():
            for x in (v if isinstance(v, list) else [v]):
                out.append((k, x))
        return out
    return list(payload)


def _split_name(name: str) -> list[str]:
    m = _KEY_RE.match(name)
    if not m:
        return [name]
    segs = [m.group(1)] + re.findall(r"\[([^\[\]]*)\]", m.group(2))
    if "" in segs[:-1]:
        raise ValueError(f"'[]' may only be the last segment: {name}")
    return segs


def _insert(root: dict, segs: list[str], value: str, key: str):
    node: Any = root
    for i, seg in enumerate(segs):
        last = i == len(segs) - 1
        if seg == "":
            node.append(value)
            return
        nxt_is_append = (not last) and segs[i + 1] == ""
        if last:
            node[seg] = value
        else:
            child = node.get(seg)
            if child is None or (nxt_is_append and not isinstance(child, list)) or (not nxt_is_append and not isinstance(child, dict)):
                child = [] if nxt_is_append else {}
                node[seg] = child
            node = child


def _intify(segs: Iterable[str]) -> Path:
    return tuple(int(s) if isinstance(s, str) and s.isdigit() else s for s in segs)


def _compact(node: Any) -> Any:
    """dicts whose keys are all digits become lists ordered numerically (sparse indices ok)."""
    if isinstance(node, dict):
        node = {k: _compact(v) for k, v in node.items()}
        if node and all(k.isdigit() for k in node):
            return [node[k] for k in sorted(node, key=int)]
        return node
    if isinstance(node, list):
        return [_compact(v) for v in node]
    return node


def _pop_intents(node: Any, path: Path) -> tuple[Any, list[Intent]]:
    """A list path carries its control key as `<path>[_intent]=add|remove:<key>|move:<key>:up|down`.
    Because that key sits next to the digit keys, the compacted node is a dict {"_intent": .., "0": ..}."""
    intents: list[Intent] = []
    if isinstance(node, dict):
        raw = node.pop(INTENT, None)
        if raw is not None:
            op, *args = raw.split(":")
            intents.append(Intent(op, path, args[0] if args else None, args[1] if len(args) > 1 else None))  # type: ignore[arg-type]
            node = _compact({k: v for k, v in node.items()})
            if isinstance(node, dict) and not node:
                node = []
        if isinstance(node, dict):
            out = {}
            for k, v in node.items():
                v, sub = _pop_intents(v, path + (_intify([k])[0],))
                out[k] = v
                intents += sub
            return out, intents
    if isinstance(node, list):
        out = []
        for i, v in enumerate(node):
            v, sub = _pop_intents(v, path + (i,))
            out.append(v)
            intents += sub
        return out, intents
    return node, intents


# ============================================================== messages
DEFAULT_MESSAGES: dict[str, str | tuple[str, str, str]] = {
    "missing": "{label} is required",
    "string_too_short": ("{label} must be at least {min_length} character", "{label} must be at least {min_length} characters", "min_length"),
    "string_too_long": ("{label} must be at most {max_length} character", "{label} must be at most {max_length} characters", "max_length"),
    "string_pattern_mismatch": "{label} is not in the right format",
    "int_parsing": "{label} must be a whole number",
    "int_type": "{label} must be a whole number",
    "float_parsing": "{label} must be a number",
    "decimal_parsing": "{label} must be a number",
    "bool_parsing": "Select {label}",
    "greater_than_equal": "{label} must be at least {ge}",
    "less_than_equal": "{label} must be at most {le}",
    "greater_than": "{label} must be more than {gt}",
    "less_than": "{label} must be less than {lt}",
    "too_short": ("Add at least {min_length} item to {label}", "Add at least {min_length} items to {label}", "min_length"),
    "too_long": ("{label} can have at most {max_length} item", "{label} can have at most {max_length} items", "max_length"),
    "enum": "Select a valid option for {label}",
    "literal_error": "Select a valid option for {label}",
    "union_tag_invalid": "Select a valid option for {label}",
    "union_tag_not_found": "Select an option for {label}",
    "date_from_datetime_parsing": "{label} must be a real date",
    "datetime_from_date_parsing": "{label} must be a real date and time",
    "value_error": "{error}",
}


@dataclass(frozen=True)
class FormError:
    path: Path
    code: str
    params: dict
    message: str
    input: Any = None


# ============================================================== Form
def _ngettext(s, p, n):
    return s if n == 1 else p


@dataclass
class Form(Generic[M]):
    model_cls: type[M]
    data: M | None = None
    as_: str = ""
    params: dict = field(default_factory=dict)          # attempted values (strings) + shelved union variants
    errors: list[FormError] = field(default_factory=list)
    external_errors: list[FormError] = field(default_factory=list)
    used: set[Path] = field(default_factory=set)
    action: Optional[str] = None                         # None | "validate" | "submit"
    model: Optional[M] = None
    submitted_once: bool = False
    just_submitted: bool = False
    applied_intents: list[Intent] = field(default_factory=list)
    messages: dict = field(default_factory=dict)
    labels: dict = field(default_factory=dict)
    empty_values: tuple = ("",)

    def __post_init__(self):
        self.as_ = self.as_ or _snake(self.model_cls.__name__)
        if self.data is not None and not self.params:
            self.params = _serialize(self.data)

    # ---- events -------------------------------------------------------------------------
    def validate(self, payload, *, recovered: bool = False) -> "Form[M]":
        p = payload if isinstance(payload, Params) else Params.decode(payload, prefix=self.as_, recovered=recovered)
        self.just_submitted = False
        self.action = "validate"
        if p.target is not None:
            self.used.add(p.target)
        for path in p.unused:                              # 1.x client: authoritative
            self.used.discard(path)
        if p.recovered:                                    # phx-auto-recover replay: mark non-blank paths used
            self.used |= {path for path, v in _leaves(p.data) if v != ""}
        self._merge_params(p.data)
        self.applied_intents = []
        for intent in p.intents:
            self._apply_intent(intent)
        self._run()
        return self

    def submit(self, payload) -> "Form[M]":
        p = payload if isinstance(payload, Params) else Params.decode(payload, prefix=self.as_)
        self._merge_params(p.data)
        self.applied_intents = []
        for intent in p.intents:
            self._apply_intent(intent)
        self.action = "submit"
        self.submitted_once = True
        self.just_submitted = True
        self.external_errors = []
        self._run()
        return self

    def add_error(self, path: str | Path, code: str, message: str, **params) -> "Form[M]":
        path = _parse_path(path)
        self.external_errors.append(FormError(path, code, params, message))
        self.model = None
        return self

    def reset(self, data: M | None = None) -> "Form[M]":
        self.__init__(self.model_cls, data if data is not None else self.data, self.as_, messages=self.messages, labels=self.labels)  # type: ignore[misc]
        return self

    # ---- internals ----------------------------------------------------------------------
    def _merge_params(self, incoming: dict):
        """Phoenix replaces; we replace too, except that shelved union variants are preserved and
        row keys are assigned. Fields the template did not render are simply absent -> keep `data`."""
        merged = _replace_keeping_variants(self.params, incoming, self.model_cls)
        _assign_keys(merged, self.model_cls)
        self.params = merged

    def _apply_intent(self, intent: Intent):
        node = _get(self.params, intent.path)
        rows = node if isinstance(node, list) else []
        if intent.op == "add":
            rows.append({ROWKEY: f"k{next(_counter)}"})
        elif intent.op == "remove":
            rows = [r for r in rows if not (isinstance(r, dict) and r.get(ROWKEY) == intent.key)]
        elif intent.op == "move":
            i = next((n for n, r in enumerate(rows) if isinstance(r, dict) and r.get(ROWKEY) == intent.key), None)
            if i is not None:
                j = i - 1 if intent.arg == "up" else i + 1
                if 0 <= j < len(rows):
                    rows[i], rows[j] = rows[j], rows[i]
        _set(self.params, intent.path, rows)
        self.used.add(intent.path)
        self.applied_intents.append(intent)

    def _run(self):
        self.errors = []
        self.model = None
        inp = cast(self.model_cls, self.data, self.params, self.empty_values)
        try:
            self.model = self.model_cls.model_validate(inp)
        except ValidationError as e:
            self.errors = [self._humanize(x) for x in e.errors(include_url=False)]
        if self.external_errors:
            self.model = None

    def _humanize(self, err: dict) -> FormError:
        path = tuple(err["loc"])
        ctx = dict(err.get("ctx") or {})
        code = err["type"]
        msg = err["msg"].removeprefix("Value error, ")
        clean = strip_union_tags(self.model_cls, path)
        label = self.label_for(clean)
        entry = self.messages.get((_dotted(clean), code)) or self.messages.get(code) or DEFAULT_MESSAGES.get(code)
        if entry is None:
            text = msg
        else:
            if isinstance(entry, tuple):
                sing, plur, count_key = entry
                entry = _ngettext(sing, plur, ctx.get(count_key, 1))
            try:
                text = entry.format(label=label, error=msg, **ctx)
            except (KeyError, IndexError):
                text = msg
        return FormError(clean, code, ctx, text, err.get("input"))

    # ---- state ----------------------------------------------------------------------------
    @property
    def valid(self) -> bool:
        return self.model is not None and not self.external_errors

    @property
    def changed(self) -> bool:
        return cast(self.model_cls, self.data, self.params, self.empty_values) != (_serialize(self.data) if self.data else {})

    def all_errors(self) -> list[FormError]:
        return self.errors + self.external_errors

    def errors_for(self, path: Path, *, gated: bool = True) -> list[FormError]:
        """pydantic errors are gated by used/action; errors the server added deliberately always show."""
        ext = [e for e in self.external_errors if e.path == path]
        own = [e for e in self.errors if e.path == path]
        if not gated or self.visible(path):
            return own + ext
        return ext

    def visible(self, path: Path) -> bool:
        """submitted, or the path itself was used, or it is an ancestor of a used path."""
        if self.action is None:
            return False
        if self.action == "submit":
            return True
        return any(u[: len(path)] == path for u in self.used)

    def label_for(self, path: Path) -> str:
        key = _dotted(path)
        if key in self.labels:
            return self.labels[key]
        fi, _ = _info(self.model_cls, path)
        if fi is not None and fi.title:
            return fi.title
        last = next((p for p in reversed(path) if isinstance(p, str)), "")
        return last.replace("_", " ").capitalize()

    def __getitem__(self, name) -> "Field":
        return Field(self, (name,))

    def __getattr__(self, name) -> "Field":
        if name.startswith("_") or name in self.__dataclass_fields__ or name not in self.model_cls.model_fields:
            raise AttributeError(name)
        return Field(self, (name,))

    def debug(self) -> str:
        return f"params={self.params!r}\nused={sorted(map(str, self.used))}\naction={self.action}\nerrors={[(e.path, e.code) for e in self.all_errors()]}\nvalid={self.valid}"


def cast(model_cls: type[BaseModel], data: BaseModel | None, params: dict, empty_values=("",)) -> dict:
    """Ecto cast semantics on top of pydantic: start from the initial data (serialised to python values),
    overlay every key present in params, turn empty values into the field's default (or None), lift the
    active variant of discriminated unions from variant-named inputs, strip control keys."""
    base = data.model_dump(mode="python") if data is not None else {}
    return _cast_model(model_cls, base, params, empty_values)


def _cast_model(model_cls, base: dict, params: dict, empty_values) -> dict:
    out = dict(base)
    for name, fi in model_cls.model_fields.items():
        if name not in params:
            continue                                       # absent -> keep data (or `missing` if none)
        raw = params[name]
        ann = fi.annotation
        if isinstance(raw, str) and raw.strip() in empty_values:
            if fi.default is not PydanticUndefined:
                out[name] = fi.default
            elif fi.default_factory is not None:
                out[name] = fi.default_factory()  # type: ignore[call-arg]
            elif _is_optional(ann):
                out[name] = None
            else:
                out.pop(name, None)                        # required and cleared -> missing
            continue
        disc = fi.discriminator if isinstance(fi.discriminator, str) else None
        if disc and isinstance(raw, dict):
            tag = raw.get(disc)
            variant = next((m for m in _union_members(ann) if _literal_value(m, disc) == tag), None)
            active = raw.get(tag, {}) if isinstance(raw.get(tag), dict) else {}
            sub_base = base.get(name) if isinstance(base.get(name), dict) else {}
            lifted = _cast_model(variant, {k: v for k, v in sub_base.items() if k != disc}, active, empty_values) if variant else {}
            out[name] = {disc: tag, **lifted}
            continue
        sub_model = _unwrap_model(ann)
        if sub_model is not None and isinstance(raw, dict):
            out[name] = _cast_model(sub_model, base.get(name) or {}, raw, empty_values)
            continue
        if get_origin(_strip_optional(ann)) is list and isinstance(raw, list):
            item = get_args(_strip_optional(ann))[0]
            item_model = _unwrap_model(item)
            rows = []
            for r in raw:
                if item_model is not None and isinstance(r, dict):
                    rows.append(_cast_model(item_model, {}, r, empty_values))
                elif isinstance(r, str) and r.strip() in empty_values:
                    continue                                # Ecto: empty elements are dropped from arrays
                else:
                    rows.append(r)
            out[name] = rows
            continue
        out[name] = raw.strip() if isinstance(raw, str) else raw
    return {k: v for k, v in out.items() if k not in (ROWKEY, INTENT)}


# ============================================================== Field (template contract)
@dataclass(frozen=True)
class Html:
    name: str
    id: str
    value: Any                   # str | list[str]
    errors: list[str]            # gated, translated
    label: str
    hint: str | None
    required: bool
    type: str
    attrs: str
    key: str | None


@dataclass(frozen=True)
class Field:
    form: Form
    path: Path

    def __getitem__(self, key) -> "Field":
        if isinstance(key, str) and key.isdigit():
            key = int(key)
        return Field(self.form, self.path + (key,))

    def __getattr__(self, name) -> "Field":
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]

    def __iter__(self):
        v = _get(self.form.params, self.path)
        return iter([self[i] for i in range(len(v))] if isinstance(v, list) else [])

    @property
    def used(self) -> bool:
        return self.form.visible(self.path)

    @property
    def typed(self) -> Any:
        return _get(cast(self.form.model_cls, self.form.data, self.form.params), self.path)

    @property
    def html(self) -> Html:
        f = self.form
        fi, ann = _info(f.model_cls, self.path)
        raw = _get(f.params, self.path)
        key = raw.get(ROWKEY) if isinstance(raw, dict) else None
        if isinstance(raw, dict):
            raw = None                                   # a row / nested model has no scalar value
        base = _strip_optional(ann) if ann is not None else str
        secret = isinstance(base, type) and issubclass(base, SecretStr)
        value = "" if secret or raw is None else raw
        attrs = {}
        if fi is not None:
            if fi.is_required() and not _is_optional(ann):
                attrs["required"] = True
            for m in fi.metadata:
                if isinstance(m, at.MinLen): attrs["minlength"] = m.min_length
                elif isinstance(m, at.MaxLen): attrs["maxlength"] = m.max_length
                elif isinstance(m, at.Ge): attrs["min"] = m.ge
                elif isinstance(m, at.Le): attrs["max"] = m.le
                elif getattr(m, "pattern", None): attrs["pattern"] = m.pattern
        errs = [e.message for e in f.errors_for(self.path)]
        id_ = self._id()
        described = [x for x, ok in ((f"{id_}-hint", bool(fi and fi.description)), (f"{id_}-error", bool(errs))) if ok]
        if described:
            attrs["aria-describedby"] = " ".join(described)
        if errs:
            attrs["aria-invalid"] = "true"
        rendered = " ".join(k if v is True else f'{k}="{v}"' for k, v in attrs.items())
        return Html(name=self._name(), id=id_, value=value, errors=errs, label=f.label_for(self.path),
                    hint=fi.description if fi else None, required=bool(attrs.get("required")),
                    type=_input_type(base, secret), attrs=rendered, key=key)

    def _name(self) -> str:
        return self.form.as_ + "".join(f"[{p}]" for p in self.path)

    def _id(self) -> str:
        parts = [self.form.as_]
        node: Any = self.form.params
        for seg in self.path:
            node = _get(node, (seg,)) if node is not None else None
            parts.append(node[ROWKEY] if isinstance(seg, int) and isinstance(node, dict) and ROWKEY in node else str(seg))
        return "_".join(parts)


# ============================================================== helpers
def _snake(s: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", s).lower()


def _dotted(path: Path) -> str:
    return ".".join(str(p) for p in path if not isinstance(p, int))


def _parse_path(p) -> Path:
    if isinstance(p, tuple):
        return p
    return _intify(p.replace("[", ".").replace("]", "").split("."))


def _get(node, path: Path):
    for seg in path:
        try:
            node = node[seg]
        except (KeyError, IndexError, TypeError):
            return None
    return node


def _set(node, path: Path, value):
    for seg in path[:-1]:
        if isinstance(node, dict) and seg not in node:
            node[seg] = {}
        node = node[seg]
    node[path[-1]] = value


def _leaves(node, path: Path = ()):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _leaves(v, path + (_intify([k])[0],))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _leaves(v, path + (i,))
    else:
        yield path, node


def _is_optional(ann) -> bool:
    return get_origin(ann) in (Union, types.UnionType) and type(None) in get_args(ann)


def _strip_optional(ann):
    if _is_optional(ann):
        rest = [a for a in get_args(ann) if a is not type(None)]
        return rest[0] if len(rest) == 1 else Union[tuple(rest)]  # type: ignore[return-value]
    return ann


def _union_members(ann):
    ann = _strip_optional(ann)
    return [a for a in get_args(ann)] if get_origin(ann) in (Union, types.UnionType) else [ann]


def _literal_value(model, disc):
    fi = model.model_fields.get(disc)
    return get_args(fi.annotation)[0] if fi and get_origin(fi.annotation) is Literal else None


def _unwrap_model(ann):
    ann = _strip_optional(ann)
    if isinstance(ann, type) and issubclass(ann, BaseModel):
        return ann
    return None


def _info(model_cls, path: Path) -> tuple[Optional[FieldInfo], Any]:
    cls: Any = model_cls
    fi, ann = None, None
    for seg in path:
        if isinstance(seg, int):
            ann = get_args(_strip_optional(ann))[0] if get_origin(_strip_optional(ann)) is list else Any
            cls = ann
            continue
        model = _unwrap_model(cls)
        if model is None:                                   # inside a union: seg may be a variant tag
            members = [m for m in _union_members(cls) if isinstance(m, type) and issubclass(m, BaseModel)]
            tagged = next((m for m in members if _literal_value(m, next(iter(m.model_fields))) == seg), None)
            if tagged is not None:
                cls = tagged
                continue
            model = next((m for m in members if seg in m.model_fields), None)
            if model is None:
                return None, None
        fi = model.model_fields[seg]
        ann = fi.annotation
        cls = ann
    return fi, ann


def strip_union_tags(model_cls, loc: Path) -> Path:
    """('account', 'business', 'company') -> ('account', 'business', 'company') stays for variant-named inputs;
    but pydantic also inserts tags for *smart* unions ('n', 'int') which are not variant names: drop those."""
    out: list = []
    cls: Any = model_cls
    for seg in loc:
        if isinstance(seg, int):
            out.append(seg)
            cls = get_args(_strip_optional(cls))[0] if get_origin(_strip_optional(cls)) is list else Any
            continue
        model = _unwrap_model(cls)
        if model is not None and seg in model.model_fields:
            out.append(seg)
            cls = model.model_fields[seg].annotation
            continue
        members = [m for m in _union_members(cls) if isinstance(m, type) and issubclass(m, BaseModel)]
        tagged = next((m for m in members if m.model_fields and _literal_value(m, next(iter(m.model_fields))) == seg), None)
        if tagged is not None:
            out.append(seg)                                 # a discriminated-union tag: kept (variant-named inputs)
            cls = tagged
            continue
        # smart-union member name ('int', 'str', 'Cat'): not addressable -> drop
    return tuple(out)


def _assign_keys(node, ann):
    model = _unwrap_model(ann)
    if isinstance(node, dict) and model is not None:
        for name, fi in model.model_fields.items():
            if name in node:
                if isinstance(fi.discriminator, str) and isinstance(node[name], dict):
                    for m in _union_members(fi.annotation):
                        tag = _literal_value(m, fi.discriminator)
                        if isinstance(node[name].get(tag), dict):
                            _assign_keys(node[name][tag], m)
                else:
                    _assign_keys(node[name], fi.annotation)
    elif isinstance(node, list) and get_origin(_strip_optional(ann)) is list:
        item = get_args(_strip_optional(ann))[0]
        for row in node:
            if isinstance(row, dict):
                row.setdefault(ROWKEY, None)
                if row[ROWKEY] is None:
                    row[ROWKEY] = f"k{next(_counter)}"
                _assign_keys(row, item)


def _replace_keeping_variants(old: dict, new: dict, model_cls) -> dict:
    """Phoenix replaces params with each payload. Discriminated-union variants that were not rendered
    (and therefore not sent) are kept from the previous params so switching back restores them."""
    out = dict(new)
    for name, fi in model_cls.model_fields.items():
        if isinstance(fi.discriminator, str) and isinstance(old.get(name), dict) and isinstance(out.get(name), dict):
            for tag, sub in old[name].items():
                if tag != fi.discriminator and tag not in out[name]:
                    out[name][tag] = sub
    return out


def _serialize(obj: Any) -> Any:
    """python values -> what an HTML input would hold (bool -> 'true'/'false', dates ISO, SecretStr never)."""
    if isinstance(obj, BaseModel):
        d = {}
        for name, fi in obj.model_fields.items():
            v = getattr(obj, name)
            if isinstance(fi.discriminator, str) and isinstance(v, BaseModel):
                tag = getattr(v, fi.discriminator)
                d[name] = {fi.discriminator: tag, tag: {k: x for k, x in _serialize(v).items() if k != fi.discriminator}}
            else:
                d[name] = _serialize(v)
        return d
    if isinstance(obj, SecretStr):
        return ""
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if isinstance(obj, enum.Enum):
        return str(obj.value)
    if isinstance(obj, dt.datetime):
        return obj.strftime("%Y-%m-%dT%H:%M")
    if isinstance(obj, (dt.date, dt.time)):
        return obj.isoformat()
    if isinstance(obj, (int, float, decimal.Decimal)):
        return str(obj)
    if isinstance(obj, list):
        return [_serialize(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if obj is None:
        return ""
    return obj


def _input_type(base, secret: bool) -> str:
    if secret:
        return "password"
    if base is bool:
        return "checkbox"
    if base in (int, float, decimal.Decimal):
        return "number"
    if base is dt.date:
        return "date"
    if base is dt.datetime:
        return "datetime-local"
    if base is dt.time:
        return "time"
    if get_origin(base) is Literal or (isinstance(base, type) and issubclass(base, enum.Enum)):
        return "select"
    return "text"


# ============================================================== test helper: what the client sends
def wire(form: Form, values: dict | None = None, *, target: str | None = None, submitter: tuple[str, str] | None = None) -> list[tuple[str, str]]:
    """Serialise the *rendered* inputs (from form.params overlaid with `values` given by dotted path), in order,
    exactly like the 0.20.17 client: hidden _key per row, submitter pair, then _target."""
    params = _deepcopy(form.params)
    for dotted, v in (values or {}).items():
        _set(params, _parse_path(dotted), v)
    pairs: list[tuple[str, str]] = []
    _emit(pairs, form.as_, params, form.model_cls)
    if submitter:
        pairs.append(submitter)
    if target:
        pairs.append(("_target", target))
    return pairs


def _emit(pairs, prefix, node, ann):
    model = _unwrap_model(ann) if ann is not None else None
    if isinstance(node, dict):
        if ROWKEY in node:
            pairs.append((f"{prefix}[{ROWKEY}]", node[ROWKEY]))
        for k, v in node.items():
            if k == ROWKEY:
                continue
            fi = model.model_fields.get(k) if model else None
            sub_ann = fi.annotation if fi else None
            if fi and isinstance(fi.discriminator, str) and isinstance(v, dict):   # only the ACTIVE variant is rendered
                tag = v.get(fi.discriminator)
                pairs.append((f"{prefix}[{k}][{fi.discriminator}]", tag))
                variant = next((m for m in _union_members(sub_ann) if _literal_value(m, fi.discriminator) == tag), None)
                _emit(pairs, f"{prefix}[{k}][{tag}]", v.get(tag, {}), variant)
                continue
            _emit(pairs, f"{prefix}[{k}]", v, sub_ann)
    elif isinstance(node, list):
        item = get_args(_strip_optional(ann))[0] if ann is not None and get_origin(_strip_optional(ann)) is list else None
        for i, v in enumerate(node):
            if isinstance(v, dict):
                _emit(pairs, f"{prefix}[{i}]", v, item)
            else:
                pairs.append((f"{prefix}[]", str(v)))
    else:
        pairs.append((prefix, "" if node is None else str(node)))


def _deepcopy(x):
    import copy
    return copy.deepcopy(x)
