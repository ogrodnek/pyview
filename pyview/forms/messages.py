"""Turning validation failures into sentences a person would write.

``"String should have at least 3 characters"`` is a fine thing for a library to
say to a programmer and a bad thing to say to someone filling in a form. It also
cannot be translated, because by the time it is a string the ``3`` is welded into
the English.

This is why :class:`~pyview.forms.form.FormError` keeps pydantic's ``type`` and
``ctx`` instead of flattening to ``msg`` on the way in - the same reason Ecto
stores ``{"should be at least %{count} characters", count: 3}``. A catalog maps
``type`` to a template, the template interpolates ``ctx`` plus the field's label,
and swapping the catalog is the entire i18n story.
"""

from __future__ import annotations

from typing import Callable, Optional

from .form import FormError

__all__ = ["DEFAULT_MESSAGES", "humanize", "set_messages"]


#: ``type`` -> template. ``{label}`` is the field's label; everything else comes
#: from pydantic's ``ctx``.
DEFAULT_MESSAGES: dict[str, str] = {
    "missing": "{label} is required.",
    "string_too_short": "{label} must be at least {min_length} characters.",
    "string_too_long": "{label} must be {max_length} characters or fewer.",
    "string_pattern_mismatch": "{label} is not in the expected format.",
    "value_error": "{label} is not valid.",
    "int_parsing": "{label} must be a whole number.",
    "float_parsing": "{label} must be a number.",
    "decimal_parsing": "{label} must be a number.",
    "bool_parsing": "{label} must be yes or no.",
    "date_parsing": "{label} must be a date.",
    "date_from_datetime_parsing": "{label} must be a date.",
    "datetime_parsing": "{label} must be a date and time.",
    "time_parsing": "{label} must be a time.",
    "greater_than": "{label} must be greater than {gt}.",
    "greater_than_equal": "{label} must be {ge} or more.",
    "less_than": "{label} must be less than {lt}.",
    "less_than_equal": "{label} must be {le} or less.",
    "enum": "Choose one of the available options for {label}.",
    "literal_error": "Choose one of the available options for {label}.",
    "too_short": "Add at least {min_length} to {label}.",
    "too_long": "{label} allows at most {max_length}.",
    "url_parsing": "{label} must be a valid URL.",
    "uuid_parsing": "{label} must be a valid ID.",
}

_messages: dict[str, str] = dict(DEFAULT_MESSAGES)
_fallback: Optional[Callable[[FormError, str], str]] = None


def set_messages(
    messages: dict[str, str], fallback: Optional[Callable[[FormError, str], str]] = None
) -> None:
    """Replace or extend the catalog. Pass a locale's dict here to translate.

    ``fallback`` is consulted for error types the catalog does not cover; the
    default is to use pydantic's own message, which is always better than a
    placeholder.
    """
    global _messages, _fallback
    _messages = {**DEFAULT_MESSAGES, **messages}
    _fallback = fallback


def humanize(error: FormError, label: str = "This field") -> str:
    """Render one error as a sentence.

    Unknown types fall back to pydantic's message rather than to something
    useless, so an uncatalogued validator degrades to "slightly technical"
    instead of "wrong".
    """
    template = _messages.get(error.type)
    if template is None:
        return _fallback(error, label) if _fallback else error.msg

    try:
        return template.format(label=label, **error.ctx)
    except (KeyError, IndexError):
        # a catalog entry referencing a ctx key this error does not carry
        return error.msg
