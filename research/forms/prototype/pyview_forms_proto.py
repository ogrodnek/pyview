"""Prototype: bracket-name decoder + pydantic-backed Form state for pyview.

Goal: prove the core loop works end-to-end with the Phoenix client conventions:
  <input name="profile[addresses][0][city]">  ->  {"profile": {"addresses": [{"city": ...}]}}
  phx-change payload with _target -> validate whole model, show errors only for used paths
"""
from __future__ import annotations

import re
import types
import typing
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal, Optional, Union, get_args, get_origin

import annotated_types as at
from pydantic import BaseModel, ValidationError
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

Path = tuple[Union[str, int], ...]

# ---------------------------------------------------------------- 1. decoding
_KEY_RE = re.compile(r"^([^\[\]]+)((?:\[[^\[\]]*\])*)$")
META_KEYS = ("_target", "_csrf_token", "_method")


def split_name(name: str) -> list[str]:
    """'user[addresses][0][city]' -> ['user','addresses','0','city'];  'tags[]' -> ['tags','']"""
    m = _KEY_RE.match(name)
    if not m:
        return [name]
    head, rest = m.group(1), m.group(2)
    return [head] + re.findall(r"\[([^\[\]]*)\]", rest)


def decode_form(pairs: Iterable[tuple[str, str]], *, max_depth: int = 32) -> tuple[dict, dict]:
    """Plug.Conn.Query-compatible decoding of (key, value) pairs.

    Rules: a[b]=1 -> {'a': {'b': '1'}};  a[]=1&a[]=2 -> {'a': ['1','2']};
    a[0][x]=1&a[1][x]=2 -> {'a': [{'x':'1'},{'x':'2'}]} (digit keys collected then ordered numerically,
    so sparse indices after a client-side removal still work);  plain repeated key: last wins.
    Returns (data, meta) where meta holds _target (as a path), _csrf_token, _unused_* etc.
    """
    root: dict = {}
    meta: dict = {}
    for key, value in pairs:
        if key in META_KEYS or key.startswith("_unused_"):
            meta.setdefault(key, []).append(value)
            continue
        segs = split_name(key)
        if len(segs) > max_depth:
            raise ValueError(f"form key too deep: {key}")
        node: Any = root
        for i, seg in enumerate(segs):
            last = i == len(segs) - 1
            if seg == "":  # append
                if not isinstance(node, list):
                    raise ValueError(f"cannot append into non-list at {key}")
                if last:
                    node.append(value)
                else:
                    node.append({})
                    node = node[-1]
                continue
            nxt = segs[i + 1] if not last else None
            container = list if nxt == "" else dict
            if isinstance(node, dict):
                if last:
                    node[seg] = value
                else:
                    node = node.setdefault(seg, container())
            else:
                raise ValueError(f"cannot index list with key {seg!r} in {key}")
    data = _indexed_dicts_to_lists(root)
    if "_target" in meta:
        meta["_target"] = tuple(_intify(s) for s in split_name(meta["_target"][-1]))
    return data, meta


def _intify(s: str):
    return int(s) if s.isdigit() else s


def _indexed_dicts_to_lists(node: Any) -> Any:
    if isinstance(node, dict):
        node = {k: _indexed_dicts_to_lists(v) for k, v in node.items()}
        if node and all(k.isdigit() for k in node):
            return [node[k] for k in sorted(node, key=int)]
        return node
    if isinstance(node, list):
        return [_indexed_dicts_to_lists(v) for v in node]
    return node


# ---------------------------------------------------- 2. empty-value handling
def normalize_empty(data: Any) -> Any:
    """Ecto-style: strip strings, and treat '' as *absent* so pydantic reports `missing` for
    required fields and applies defaults for optional ones (instead of int_parsing etc)."""
    if isinstance(data, dict):
        out = {}
        for k, v in data.items():
            v = normalize_empty(v)
            if v is _ABSENT:
                continue
            out[k] = v
        return out
    if isinstance(data, list):
        return [v for v in (normalize_empty(x) for x in data) if v is not _ABSENT]
    if isinstance(data, str):
        s = data.strip()
        return _ABSENT if s == "" else s
    return data


_ABSENT = object()


# ------------------------------------------------------------ 3. messages
DEFAULT_MESSAGES = {
    "missing": "This field is required",
    "string_too_short": "Must be at least {min_length} characters",
    "string_too_long": "Must be at most {max_length} characters",
    "string_pattern_mismatch": "Doesn't match the expected format",
    "int_parsing": "Must be a whole number",
    "float_parsing": "Must be a number",
    "decimal_parsing": "Must be a number",
    "bool_parsing": "Must be yes or no",
    "greater_than_equal": "Must be at least {ge}",
    "less_than_equal": "Must be at most {le}",
    "greater_than": "Must be greater than {gt}",
    "less_than": "Must be less than {lt}",
    "too_short": "Add at least {min_length} item(s)",
    "too_long": "At most {max_length} item(s)",
    "enum": "Choose one of the options",
    "literal_error": "Choose one of the options",
    "union_tag_invalid": "Choose one of the options",
    "date_from_datetime_parsing": "Enter a valid date",
    "datetime_from_date_parsing": "Enter a valid date and time",
    "value_error": "{msg}",
}


@dataclass
class FormError:
    path: Path
    code: str
    message: str
    params: dict = field(default_factory=dict)


def humanize(err: dict, catalog=DEFAULT_MESSAGES) -> FormError:
    ctx = dict(err.get("ctx") or {})
    template = catalog.get(err["type"], err["msg"])
    msg = err["msg"]
    if err["type"] == "value_error":  # user-raised ValueError: keep their text
        msg = msg.removeprefix("Value error, ")
    try:
        text = template.format(**ctx, msg=msg)
    except (KeyError, IndexError):
        text = err["msg"]
    return FormError(tuple(err["loc"]), err["type"], text, ctx)


# ------------------------------------------------------------ 4. form state
@dataclass
class Form:
    model_cls: type[BaseModel]
    as_: str = "form"
    params: dict = field(default_factory=dict)      # raw (attempted) values, nested
    errors: list[FormError] = field(default_factory=list)
    used: set[Path] = field(default_factory=set)
    submitted: bool = False
    model: Optional[BaseModel] = None

    @classmethod
    def for_model(cls, model_cls, initial: BaseModel | dict | None = None, as_="form"):
        params = initial.model_dump(mode="json") if isinstance(initial, BaseModel) else dict(initial or {})
        return cls(model_cls, as_, params)

    # -- events -------------------------------------------------------------
    def validate(self, pairs: Iterable[tuple[str, str]]) -> "Form":
        """phx-change: keep attempted values, validate everything, mark _target as used."""
        data, meta = decode_form(pairs)
        self.params = data.get(self.as_, {})
        target = meta.get("_target")
        if target and target[0] == self.as_:
            self.used.add(target[1:])
        self._run()
        return self

    def submit(self, pairs) -> "Form":
        data, _ = decode_form(pairs)
        self.params = data.get(self.as_, {})
        self.submitted = True
        self._run()
        return self

    def _run(self):
        self.errors = []
        self.model = None
        try:
            self.model = self.model_cls.model_validate(normalize_empty(self.params))
        except ValidationError as e:
            self.errors = [humanize(x) for x in e.errors(include_url=False)]

    @property
    def valid(self) -> bool:
        return self.model is not None

    # -- errors visible to the user ----------------------------------------
    def visible_errors(self, path: Path) -> list[FormError]:
        # visible if submitted, or the path itself was used, or it is an ancestor of a used path
        # (Phoenix used_input? semantics: a parent counts as used when any child is; children do NOT
        # become used because their parent/list was — a freshly added row shows no errors yet)
        if not self.submitted and not any(u[: len(path)] == path for u in self.used):
            return []
        return [e for e in self.errors if _matches(e.path, path)]

    def __getitem__(self, name: str) -> "Field":
        return Field(self, (name,))


def _matches(err_path: Path, path: Path) -> bool:
    """error ('account','business','company') should display on field ('account','company')
    (discriminated-union tags are skipped when matching)."""
    ep = tuple(p for p in err_path)
    if ep == path:
        return True
    if len(ep) == len(path) + 1 and ep[:len(path) - 1] == path[:-1] and ep[-1] == path[-1]:
        return True  # tag inserted before the last segment
    return False


@dataclass
class Field:
    form: Form
    path: Path

    def _info(self) -> tuple[Optional[FieldInfo], Any]:
        """Walk model_fields along path; returns (FieldInfo, annotation) for the leaf."""
        cls: Any = self.form.model_cls
        fi = None
        ann = None
        for seg in self.path:
            if isinstance(seg, int):
                ann = _list_item(ann)
                cls = ann
                continue
            model = _unwrap_model(cls)
            if model is None:
                return None, None
            fi = model.model_fields[seg]
            ann = fi.annotation
            cls = ann
        return fi, ann

    @property
    def name(self) -> str:
        return self.form.as_ + "".join(f"[{p}]" for p in self.path)

    @property
    def id(self) -> str:
        return self.form.as_ + "_" + "_".join(str(p) for p in self.path)

    @property
    def value(self) -> Any:
        node: Any = self.form.params
        for seg in self.path:
            try:
                node = node[seg]
            except (KeyError, IndexError, TypeError):
                return ""
        return node

    @property
    def errors(self) -> list[str]:
        return [e.message for e in self.form.visible_errors(self.path)]

    @property
    def label(self) -> str:
        fi, _ = self._info()
        if fi and fi.title:
            return fi.title
        return str(self.path[-1]).replace("_", " ").capitalize()

    @property
    def constraints(self) -> dict[str, Any]:
        """HTML attributes derived from the pydantic field (like Phoenix input_validations / superforms constraints)."""
        fi, ann = self._info()
        attrs: dict[str, Any] = {}
        if fi is None:
            return attrs
        if fi.is_required() and not _is_optional(ann):
            attrs["required"] = True
        for m in fi.metadata:
            if isinstance(m, at.MinLen): attrs["minlength"] = m.min_length
            elif isinstance(m, at.MaxLen): attrs["maxlength"] = m.max_length
            elif isinstance(m, at.Ge): attrs["min"] = m.ge
            elif isinstance(m, at.Le): attrs["max"] = m.le
            elif isinstance(m, at.Gt): attrs["min"] = m.gt  # approximation
            elif isinstance(m, at.Lt): attrs["max"] = m.lt
            elif getattr(m, "pattern", None): attrs["pattern"] = m.pattern
        return attrs

    @property
    def input_type(self) -> str:
        _, ann = self._info()
        base = _strip_optional(ann)
        if base is bool: return "checkbox"
        if base in (int, float): return "number"
        if base.__name__ in ("date",): return "date"
        if base.__name__ in ("datetime",): return "datetime-local"
        if get_origin(base) is Literal or (isinstance(base, type) and hasattr(base, "__members__")): return "select"
        return "text"

    def __getitem__(self, key) -> "Field":
        return Field(self.form, self.path + (key,))

    def items(self) -> list["Field"]:
        """For list fields: one Field per current row in params."""
        v = self.value
        return [self[i] for i in range(len(v))] if isinstance(v, list) else []

    def __iter__(self):
        return iter(self.items())


def _unwrap_model(ann):
    if isinstance(ann, type) and issubclass(ann, BaseModel):
        return ann
    if get_origin(ann) in (Union, types.UnionType):
        models = [a for a in get_args(ann) if isinstance(a, type) and issubclass(a, BaseModel)]
        if len(models) == 1:
            return models[0]
        if models:  # discriminated union: merge fields of all variants for lookup
            class _Merged(BaseModel):
                pass
            merged = {}
            for m in models:
                merged.update(m.model_fields)
            _Merged.model_fields = merged  # type: ignore[attr-defined]
            return _Merged
    return None


def _list_item(ann):
    return get_args(ann)[0] if get_origin(ann) is list else Any


def _is_optional(ann):
    return get_origin(ann) in (Union, types.UnionType) and type(None) in get_args(ann)


def _strip_optional(ann):
    if _is_optional(ann):
        return next(a for a in get_args(ann) if a is not type(None))
    return ann
