"""Usage errors: the developer wired something up wrong.

Deliberately a different type from :class:`~pyview.forms.form.FormError`, which is
raised at nobody and means *the person filling in the form* typed something wrong.
Conflating the two audiences is how libraries end up showing stack traces to users
and validation copy to developers.

Every message here follows the same rules (borrowed from rustc's diagnostics guide
and pydantic's error pages): say what happened, in the developer's vocabulary; show
the value that caused it; and suggest the concrete fix, including the near-miss
name when there is one.
"""

from __future__ import annotations

import difflib
from typing import Iterable, Optional

__all__ = ["FormUsageError", "did_you_mean"]


class FormUsageError(TypeError):
    """Raised when a form is used in a way that could only be a mistake."""


def did_you_mean(name: str, candidates: Iterable[str]) -> str:
    """`` `emial` `` + the known fields -> a suggestion, or a list to choose from."""
    options = list(candidates)
    close = difflib.get_close_matches(name, options, n=1, cutoff=0.6)
    if close:
        return f"there is a field with a similar name: `{close[0]}`"
    return (
        f"available fields: {', '.join(f'`{o}`' for o in options)}"
        if options
        else "it has no fields"
    )


def unknown_field(
    model_name: str, name: str, candidates: Iterable[str], context: str
) -> FormUsageError:
    return FormUsageError(
        f"{context}: `{model_name}` has no field `{name}` -- {did_you_mean(name, candidates)}"
    )


def _fmt(names: Iterable[str], limit: int = 8) -> str:
    items = list(names)
    shown = ", ".join(f"`{n}`" for n in items[:limit])
    return shown + (f", ... ({len(items)} total)" if len(items) > limit else "")


def format_keys(keys: Iterable[str], limit: int = 8) -> Optional[str]:
    listed = [k for k in keys if not k.startswith("_")]
    return _fmt(listed, limit) if listed else None
