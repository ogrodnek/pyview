"""Reading a form's shape out of a plain pydantic model.

The design bet: **one schema, not two**. Validation rules and UI hints live on
the same model, because keeping a parallel "uiSchema" in sync (react-jsonschema-form,
JSONForms) is where those libraries lose people. Everything that can be inferred
is inferred; anything that cannot be is attached with ``Annotated[T, ui(...)]``,
which pydantic carries around and ignores.

    class Signup(BaseModel):
        email: Annotated[str, ui(widget="email", autocomplete="email")]
        bio: Annotated[Optional[str], ui(widget="textarea", rows=4)] = None
        seats: int = Field(default=1, ge=1, le=500)   # -> number, min=1, max=500
"""

from __future__ import annotations

import enum
import types
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Literal, Optional, Union, get_args, get_origin

from annotated_types import Ge, Gt, Le, Lt, MaxLen, MinLen
from pydantic import BaseModel
from pydantic.fields import FieldInfo

__all__ = [
    "ui",
    "FieldSpec",
    "field_specs",
    "unwrap_optional",
    "is_model",
    "sub_model",
    "clean_loc",
    "union_variants",
]


@dataclass(frozen=True)
class ui:  # noqa: N801 - reads as a declaration, not a class, at the call site
    """UI-only metadata, attached with ``Annotated``. Invisible to pydantic."""

    widget: Optional[str] = None
    label: Optional[str] = None
    help: Optional[str] = None
    placeholder: Optional[str] = None
    rows: Optional[int] = None
    autocomplete: Optional[str] = None
    choices: Optional[list[tuple[str, str]]] = None
    hidden: bool = False
    attrs: Optional[dict[str, Any]] = None


@dataclass
class FieldSpec:
    """Everything the renderer needs to know about one leaf field."""

    name: str
    widget: str
    label: str
    required: bool
    attrs: dict[str, Any] = field(default_factory=dict)
    choices: Optional[list[tuple[str, str]]] = None
    help: Optional[str] = None
    hidden: bool = False

    # structural: set for fields that are themselves forms
    nested: Optional[type[BaseModel]] = None
    repeated: bool = False

    # set for a discriminated union: the arms, and the field that selects between them
    variants: Optional[list[type[BaseModel]]] = None
    discriminator: Optional[str] = None


def unwrap_optional(annotation: Any) -> tuple[Any, bool]:
    """``Optional[str]`` -> ``(str, True)``; anything else -> ``(annotation, False)``."""
    if get_origin(annotation) in (Union, types.UnionType):
        args = get_args(annotation)
        rest = [a for a in args if a is not type(None)]
        if len(rest) < len(args):
            return (rest[0] if len(rest) == 1 else Union[tuple(rest)]), True
    return annotation, False


def is_model(annotation: Any) -> bool:
    return isinstance(annotation, type) and issubclass(annotation, BaseModel)


def sub_model(annotation: Any) -> Optional[type[BaseModel]]:
    """The nested model behind ``Address``, ``Optional[Address]`` or ``list[Pet]``."""
    ann, _ = unwrap_optional(annotation)
    if is_model(ann):
        return ann
    if get_origin(ann) in (list, tuple, set):
        args = get_args(ann)
        if args and is_model(args[0]):
            return args[0]
    return None


def _hint(info: FieldInfo) -> ui:
    for meta in info.metadata:
        if isinstance(meta, ui):
            return meta
    return ui()


def _constraints(info: FieldInfo, widget: str) -> dict[str, Any]:
    """pydantic constraints double as HTML validation attributes.

    Free client-side pre-validation and correct mobile keyboards, with nothing
    for the developer to restate.
    """
    attrs: dict[str, Any] = {}
    for meta in info.metadata:
        if isinstance(meta, MinLen):
            attrs["minlength"] = meta.min_length
        elif isinstance(meta, MaxLen):
            attrs["maxlength"] = meta.max_length
        elif isinstance(meta, Ge):
            attrs["min"] = meta.ge
        elif isinstance(meta, Gt):
            attrs["min"] = meta.gt
        elif isinstance(meta, Le):
            attrs["max"] = meta.le
        elif isinstance(meta, Lt):
            attrs["max"] = meta.lt

    if widget in ("number", "range"):
        attrs.pop("minlength", None)
        attrs.pop("maxlength", None)
    elif widget not in ("date", "datetime-local", "time"):
        # min/max on a text input mean nothing; keep them off the markup
        attrs.pop("min", None)
        attrs.pop("max", None)
    return attrs


def _infer_widget(annotation: Any) -> tuple[str, Optional[list[tuple[str, str]]]]:
    ann, _ = unwrap_optional(annotation)

    if isinstance(ann, type) and issubclass(ann, enum.Enum):
        return "select", [(str(e.value), _humanize(e.name)) for e in ann]

    if get_origin(ann) is Literal:
        return "select", [(str(a), _humanize(str(a))) for a in get_args(ann)]

    if ann is bool:
        return "checkbox", None
    if ann is date:
        return "date", None
    if ann is datetime:
        return "datetime-local", None
    if ann is time:
        return "time", None
    if ann in (int, float, Decimal):
        return "number", None

    return "text", None


def _humanize(name: str) -> str:
    return name.replace("_", " ").strip().capitalize()


def field_specs(model: type[BaseModel]) -> dict[str, FieldSpec]:
    """Derive a :class:`FieldSpec` for every field on ``model``, in declaration order."""
    specs: dict[str, FieldSpec] = {}

    for name, info in model.model_fields.items():
        hint = _hint(info)
        annotation, optional = unwrap_optional(info.annotation)
        required = info.is_required() and not optional

        variants = union_variants(info.annotation)
        if variants:
            specs[name] = FieldSpec(
                name=name,
                widget="union",
                label=hint.label or _humanize(name),
                required=required,
                help=hint.help or info.description,
                variants=variants,
                discriminator=getattr(info, "discriminator", None),
            )
            continue

        nested = sub_model(info.annotation)
        repeated = get_origin(annotation) in (list, tuple, set)

        if nested is not None:
            specs[name] = FieldSpec(
                name=name,
                widget="fieldset",
                label=hint.label or _humanize(name),
                required=required,
                help=hint.help or info.description,
                nested=nested,
                repeated=repeated,
            )
            continue

        widget, choices = _infer_widget(info.annotation)
        if repeated and choices is None:
            args = get_args(annotation)
            if args:
                widget, choices = _infer_widget(args[0])
                widget = "select" if choices else widget
        widget = hint.widget or widget

        attrs = _constraints(info, widget)
        if required:
            attrs["required"] = True
        if hint.placeholder:
            attrs["placeholder"] = hint.placeholder
        if hint.autocomplete:
            attrs["autocomplete"] = hint.autocomplete
        if hint.rows:
            attrs["rows"] = hint.rows
        if widget == "number" and annotation is int:
            attrs["step"] = 1
        if repeated and widget == "select":
            attrs["multiple"] = True
        attrs.update(hint.attrs or {})

        specs[name] = FieldSpec(
            name=name,
            widget=widget,
            label=hint.label or _humanize(name),
            required=required,
            attrs=attrs,
            choices=hint.choices or choices,
            help=hint.help or info.description,
            hidden=hint.hidden,
            repeated=repeated,
        )

    return specs


# ---------------------------------------------------------------------------
# error locations
# ---------------------------------------------------------------------------


def union_variants(annotation: Any) -> Optional[list[type[BaseModel]]]:
    """The model variants of a union field, or ``None`` if it is not one."""
    ann, _ = unwrap_optional(annotation)
    if get_origin(ann) not in (Union, types.UnionType):
        return None
    variants = [a for a in get_args(ann) if is_model(a)]
    return variants or None


def _discriminator_value(variant: type[BaseModel], tag: str) -> bool:
    """Does ``variant`` carry a ``Literal[tag]`` field? (i.e. is it the tagged one)"""
    for info in variant.model_fields.values():
        if get_origin(info.annotation) is Literal and tag in [
            str(a) for a in get_args(info.annotation)
        ]:
            return True
    return False


def clean_loc(model: type[BaseModel], loc: tuple[Any, ...]) -> tuple[str, ...]:
    """Translate a pydantic error location into a form path.

    pydantic reports union errors with the variant spliced into the location:
    a discriminated union yields ``("contact", "email", "address")`` and a plain
    one yields ``("contact", "Email", "address")``. Neither matches the input's
    name, which is ``owner[contact][address]``. Walking the location against the
    model lets us drop exactly the segments that are variant tags and keep the
    ones that are real fields or list indexes.
    """
    out: list[str] = []
    current: Any = model

    for segment in loc:
        key = str(segment)

        variants = union_variants(current) if current is not None else None
        if variants:
            chosen = next(
                (v for v in variants if v.__name__ == key or _discriminator_value(v, key)),
                None,
            )
            if chosen is not None:
                current = chosen  # the tag addresses a variant, not a field: drop it
                continue

        if is_model(current):
            info = current.model_fields.get(key)
            if info is not None:
                current = info.annotation
                out.append(key)
                continue

        inner, _ = unwrap_optional(current) if current is not None else (None, False)
        if get_origin(inner) in (list, tuple, set):
            args = get_args(inner)
            current = args[0] if args else None
            out.append(key)
            continue

        # unrecognised - keep it so the error is at least addressable
        current = None
        out.append(key)

    return tuple(out)


# ---------------------------------------------------------------------------
# preparing raw params for validation
# ---------------------------------------------------------------------------


def _is_plain_str(annotation: Any) -> bool:
    ann, _ = unwrap_optional(annotation)
    return ann is str


def _is_optional(info: FieldInfo) -> bool:
    _, optional = unwrap_optional(info.annotation)
    return optional or not info.is_required()


def _pick_variant(
    variants: list[type[BaseModel]], discriminator: Optional[str], raw: Any
) -> Optional[type[BaseModel]]:
    if not isinstance(raw, dict) or not discriminator:
        return None
    tag = raw.get(discriminator)
    if tag is None:
        return None
    for variant in variants:
        info = variant.model_fields.get(discriminator)
        if info is None:
            continue
        if get_origin(info.annotation) is Literal and str(tag) in [
            str(a) for a in get_args(info.annotation)
        ]:
            return variant
    return None


def prepare(model: type[BaseModel], data: Any) -> Any:
    """Turn a raw params tree into something pydantic can validate.

    Four jobs, all of which exist because HTML forms are a lossy transport:

    * **digit-keyed maps become lists.** ``pets[0][name]`` arrives as
      ``{"0": {...}}``; pydantic wants a list.
    * **empty strings become absent** for anything that is not a plain ``str``.
      A cleared date input sends ``""``, and ``Optional[date]`` rejects it -
      but the user meant "nothing", which is what ``None`` is for. Ecto solves
      this the same way, with ``:empty_values``.
    * **missing nested branches become empty dicts**, so a blank sub-form reports
      leaf errors at ``("address", "city")`` rather than one lump at ``("address",)``
      that the template has nowhere to render.
    * **unknown keys are dropped**, which quietly disposes of LiveView's
      ``_target``/``_csrf_token`` bookkeeping.
    """
    if not isinstance(data, dict):
        return data

    out: dict[str, Any] = {}

    for name, info in model.model_fields.items():
        annotation = info.annotation
        raw = data.get(name)
        nested = sub_model(annotation)
        inner, _ = unwrap_optional(annotation)
        repeated = get_origin(inner) in (list, tuple, set)

        if nested is not None and repeated:
            rows = raw if isinstance(raw, (dict, list)) else {}
            if isinstance(rows, dict):
                keys = sorted((k for k in rows if str(k).isdigit()), key=int)
                out[name] = [prepare(nested, rows[k]) for k in keys]
            else:
                out[name] = [prepare(nested, row) for row in rows]
            continue

        if nested is not None:
            if raw is None and _is_optional(info):
                continue
            out[name] = prepare(nested, raw if isinstance(raw, dict) else {})
            continue

        variants = union_variants(annotation)
        if variants:
            chosen = _pick_variant(variants, getattr(info, "discriminator", None), raw)
            if chosen is not None:
                out[name] = prepare(chosen, raw)
                continue

        if raw is None:
            continue
        if raw == "" and not _is_plain_str(annotation):
            continue

        out[name] = raw

    return out


def variant_tags(variants: list[type[BaseModel]], discriminator: str) -> list[tuple[str, str]]:
    """Every arm's tag, as select options."""
    out: list[tuple[str, str]] = []
    for variant in variants:
        info = variant.model_fields.get(discriminator)
        if info is None or get_origin(info.annotation) is not Literal:
            continue
        for arg in get_args(info.annotation):
            out.append((str(arg), _humanize(str(arg))))
    return out


def variant_for(variants: list[type[BaseModel]], discriminator: str, tag: Any) -> type[BaseModel]:
    """The arm named by ``tag``, falling back to the first one.

    Falling back rather than failing matters: on the very first render nothing
    has been selected yet, and the form still has to draw something.
    """
    chosen = _pick_variant(variants, discriminator, {discriminator: tag})
    return chosen or variants[0]


def variant_specs(spec: FieldSpec, tag: Any) -> dict[str, FieldSpec]:
    """The active arm's fields, with the discriminator turned into a real select.

    Inside a variant the discriminator is a ``Literal["email"]``, which on its own
    would render as a one-option select that can never change. Widening it to every
    arm's tag is what makes the sub-form switchable.
    """
    assert spec.variants and spec.discriminator
    variant = variant_for(spec.variants, spec.discriminator, tag)
    out = dict(field_specs(variant))

    if spec.discriminator in out:
        out[spec.discriminator] = replace(
            out[spec.discriminator],
            widget="select",
            choices=variant_tags(spec.variants, spec.discriminator),
            required=True,
        )
    return out
