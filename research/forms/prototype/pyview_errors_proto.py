"""Sketch: normalized pyview form errors on top of pydantic-core error records."""
from __future__ import annotations
import types, typing, re
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Union, get_args, get_origin
from pydantic import BaseModel, Field, ValidationError, model_validator
from pydantic_core import PydanticCustomError

# ---- 1. default catalog: pydantic-core `type` -> template using ctx keys (verified in exp5) ----
# {label} is always available; plural templates are (singular, plural, count_key)
CATALOG: dict[str, str | tuple[str, str, str]] = {
    "missing": "{label} is required",
    "string_type": "{label} must be text", "string_too_short": ("{label} must be at least {min_length} character", "{label} must be at least {min_length} characters", "min_length"),
    "string_too_long": ("{label} must be {max_length} character or fewer", "{label} must be {max_length} characters or fewer", "max_length"),
    "string_pattern_mismatch": "{label} is not in the right format",
    "int_parsing": "{label} must be a whole number", "int_type": "{label} must be a whole number", "int_from_float": "{label} must be a whole number",
    "float_parsing": "{label} must be a number", "float_type": "{label} must be a number", "finite_number": "{label} must be a finite number",
    "bool_parsing": "Select {label}", "bool_type": "Select {label}",
    "greater_than": "{label} must be greater than {gt}", "greater_than_equal": "{label} must be {ge} or more",
    "less_than": "{label} must be less than {lt}", "less_than_equal": "{label} must be {le} or less", "multiple_of": "{label} must be a multiple of {multiple_of}",
    "enum": "{label} must be one of: {expected}", "literal_error": "{label} must be one of: {expected}",
    "date_parsing": "{label} must be a real date", "date_from_datetime_parsing": "{label} must be a real date", "date_type": "{label} must be a real date",
    "date_past": "{label} must be in the past", "date_future": "{label} must be in the future",
    "datetime_parsing": "{label} must be a real date and time", "datetime_from_date_parsing": "{label} must be a real date and time", "time_parsing": "{label} must be a real time",
    "decimal_parsing": "{label} must be a number", "decimal_max_digits": "{label} must have no more than {max_digits} digits", "decimal_max_places": ("{label} must have no more than {decimal_places} decimal place", "{label} must have no more than {decimal_places} decimal places", "decimal_places"),
    "too_short": ("Add at least {min_length} item to {label}", "Add at least {min_length} items to {label}", "min_length"),
    "too_long": ("{label} can have at most {max_length} item", "{label} can have at most {max_length} items", "max_length"),
    "list_type": "{label} must be a list", "extra_forbidden": "{label} is not an allowed field",
    "union_tag_invalid": "Select a valid {label} type", "union_tag_not_found": "Select a {label} type",
    "url_parsing": "Enter a real web address for {label}", "uuid_parsing": "{label} must be a valid identifier",
    "value_error": "{error}", "assertion_error": "{error}",   # message authored in the validator
}

# ---- 2. normalized record ----
@dataclass(frozen=True)
class FormError:
    path: tuple[str | int, ...]      # loc with union-tag segments removed, e.g. ("addrs", 0, "zip")
    code: str                        # pydantic-core type or PydanticCustomError type
    params: dict[str, Any]           # ctx (+ label)
    message: str                     # pydantic's msg (fallback template)
    input: Any = None
    @property
    def name(self) -> str:           # HTML name, Phoenix-style
        if not self.path: return ""      # form-level (model_validator) error
        head, *rest = self.path
        return str(head) + "".join(f"[{seg}]" for seg in rest)
    @property
    def id(self) -> str: return "_".join(str(s) for s in self.path) or "form"

# ---- 3. path normalisation: drop union member-tag segments using the model's type graph ----
def _strip_union_tags(model: type[BaseModel], loc: tuple) -> tuple:
    out, cur = [], model
    i = 0
    while i < len(loc):
        seg = loc[i]
        origin = get_origin(cur)
        if isinstance(cur, type) and issubclass(cur, BaseModel):
            f = cur.model_fields.get(seg)
            if f is None: out.extend(loc[i:]); break
            out.append(seg); cur = f.annotation; i += 1
        elif origin in (list, tuple, set, dict):
            out.append(seg); cur = get_args(cur)[-1] if get_args(cur) else Any; i += 1
        elif origin in (Union, types.UnionType):
            members = [a for a in get_args(cur) if a is not type(None)]
            tagged = {getattr(m, "__name__", None): m for m in members}
            # pydantic uses class name for smart unions, discriminator tag for discriminated ones
            if isinstance(seg, str) and seg in tagged: cur = tagged[seg]; i += 1          # drop tag segment
            elif isinstance(seg, str) and seg in ("int","str","float","bool","list","dict"): i += 1  # primitive-member tag
            else:
                m = next((m for m in members if isinstance(m, type) and issubclass(m, BaseModel)), None)
                if m and hasattr(m, "model_fields") and _tag_matches(m, seg): cur = _member_by_tag(members, seg); i += 1
                else: cur = members[0]
        else:
            out.extend(loc[i:]); break
    return tuple(out)

def _tag_matches(m, seg):  # discriminated union: segment is a Literal tag value, not a field
    return seg not in m.model_fields
def _member_by_tag(members, seg):
    for m in members:
        for f in m.model_fields.values():
            if get_origin(f.annotation) is Literal and seg in get_args(f.annotation): return m
    return members[0]

# ---- 4. labels: Field(title) > alias > pretty name; nested via parent model ----
def label_for(model: type[BaseModel], path: tuple) -> str:
    cur, label = model, str(path[-1]) if path else ""
    for seg in path:
        if isinstance(cur, type) and issubclass(cur, BaseModel) and seg in cur.model_fields:
            f = cur.model_fields[seg]; label = f.title or f.alias or str(seg).replace("_", " ").capitalize(); cur = f.annotation
        elif get_origin(cur) in (list, dict): cur = get_args(cur)[-1]
        elif get_origin(cur) in (Union, types.UnionType):  # descend into the member owning this field
            cur = next((m for m in get_args(cur) if isinstance(m, type) and issubclass(m, BaseModel) and seg in m.model_fields), cur)
            if isinstance(cur, type) and issubclass(cur, BaseModel):
                f = cur.model_fields[seg]; label = f.title or f.alias or str(seg).replace("_", " ").capitalize(); cur = f.annotation
    return label

# ---- 5. override hooks: app catalog < per-model < per-field/rule < per-error callable ----
MessageHook = Callable[[FormError], str | None]
class ErrorTranslator:
    def __init__(self, catalog=CATALOG, gettext=None, ngettext=None, hooks: list[MessageHook] = ()):
        self.catalog = dict(catalog); self._ = gettext or (lambda s: s); self._n = ngettext or (lambda s, p, n: s if n == 1 else p); self.hooks = list(hooks)
    def format(self, err: FormError, overrides: dict[str, str] | None = None) -> str:
        for hook in self.hooks:               # per-app / per-request hooks first
            if (m := hook(err)) is not None: return m.format_map(_Safe(err.params))
        key_field = f"{err.name}.{err.code}"; key_id = ".".join(map(str, (s for s in err.path if isinstance(s, str))))
        tpl = (overrides or {}).get(key_field) or (overrides or {}).get(f"{key_id}.{err.code}") or (overrides or {}).get(err.code) or self.catalog.get(err.code)
        if tpl is None: return err.message    # unknown type: pydantic's English msg (marked, no crash)
        if isinstance(tpl, tuple):
            sing, plur, count_key = tpl; n = int(err.params.get(count_key, 0)); tpl = self._n(sing, plur, n)
        else: tpl = self._(tpl)
        return tpl.format_map(_Safe(err.params))
class _Safe(dict):
    def __missing__(self, k): return "{" + k + "}"

def normalize(model: type[BaseModel], exc: ValidationError) -> list[FormError]:
    out = []
    for e in exc.errors(include_url=False):
        path = _strip_union_tags(model, tuple(e["loc"]))
        params = dict(e.get("ctx") or {}); params["label"] = label_for(model, path)
        if "error" in params: params["error"] = str(params["error"])  # ValueError/AssertionError instance -> text
        out.append(FormError(path, e["type"], params, e["msg"], e.get("input")))
    return out

# ---- demo ----
class Cat(BaseModel): kind: Literal["cat"]; lives: int
class Dog(BaseModel): kind: Literal["dog"]; bark: bool
class Addr(BaseModel): street: str = Field(min_length=3, title="Street address"); zip: str = Field(pattern=r"^\d{5}$", title="ZIP code")
class Signup(BaseModel):
    first_name: str = Field(min_length=2); age: int = Field(ge=18); pet: Union[Cat, Dog] = Field(discriminator="kind")
    addrs: list[Addr] = Field(min_length=1); n: int | str; free: Cat | Dog
    @model_validator(mode="after")
    def chk(self):
        if self.age == 99: raise ValueError("Ninety-nine is not allowed")
        return self
if __name__ == "__main__":
    tr = ErrorTranslator()
    for data in [dict(first_name="a", age="x", pet={"kind":"cow"}, addrs=[{"street":"ab","zip":"1"}], n=1.5, free={"kind":"cat","lives":"x"}),
                 dict(first_name="ab", age=17, pet={"kind":"cat","lives":1}, addrs=[], n=1, free={"kind":"dog","bark":True}),
                 dict(first_name="ab", age=99, pet={"kind":"cat","lives":1}, addrs=[{"street":"abc","zip":"12345"}], n=1, free={"kind":"dog","bark":True})]:
        try: Signup(**data)
        except ValidationError as ex:
            for err in normalize(Signup, ex):
                print(f"{err.name:22s} id={err.id:20s} {err.code:24s} -> {tr.format(err, overrides={'age.greater_than_equal': 'You must be {ge}+ to sign up'})}")
        print("--")
