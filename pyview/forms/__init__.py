"""Forms module for PyView.

Provides FormField and related utilities for building forms with
Pydantic-backed validation.
"""

from .field import FormField
from .types import get_field_constraints, infer_input_type

__all__ = [
    "FormField",
    "infer_input_type",
    "get_field_constraints",
]
