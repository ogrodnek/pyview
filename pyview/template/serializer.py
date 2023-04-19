from typing import Any, Union, Protocol, Optional
from dataclasses import fields, is_dataclass
from pydantic import BaseModel

import inspect


def serialize(assigns: Any) -> dict[str, Any]:
    if isinstance(assigns, dict):
        return assigns

    if is_dataclass(assigns):
        df = [f.name for f in fields(assigns) if not f.name.startswith("_")]
        pf = prop_names(assigns)

        return {k: getattr(assigns, k) for k in df + pf}

    raise TypeError("Assigns must be a dict or have an asdict() method")


def isprop(v):
    return isinstance(v, property)


def prop_names(instance: Any) -> list[str]:
    """Returns a list of property names for the given class."""
    # print(fields(cls))

    cls = instance.__class__

    return [prop for prop in cls.__dict__ if isinstance(cls.__dict__[prop], property)]
