"""FormField - a lightweight view of a single form field."""

from dataclasses import dataclass
from typing import Any

from pydantic.fields import FieldInfo

from .types import get_field_constraints, infer_input_type


@dataclass(frozen=True)
class FormField:
    """Immutable view of a single form field for use in templates.

    FormField provides a convenient interface for accessing field data,
    errors, and metadata when rendering forms. It is intentionally
    immutable (frozen) to ensure it represents a snapshot of the field
    state at a point in time.

    Attributes:
        name: Full path to the field (e.g., "email", "address.city")
        value: Current value of the field
        errors: Tuple of validation error messages
        field_info: Pydantic FieldInfo containing metadata
        annotation: Python type annotation for the field

    Example:
        >>> field = FormField(
        ...     name="email",
        ...     value="test@example.com",
        ...     errors=(),
        ...     field_info=None,
        ...     annotation=str,
        ... )
        >>> field.id
        "email"
        >>> field.label
        "Email"
        >>> field.has_errors
        False
    """

    name: str
    value: Any
    errors: tuple[str, ...]
    field_info: FieldInfo | None = None
    annotation: Any | None = None

    @property
    def id(self) -> str:
        """HTML-safe id derived from field name.

        Converts dot notation and brackets to underscores.

        Examples:
            "email" → "email"
            "address.city" → "address_city"
            "tags[0]" → "tags_0_"
        """
        return (
            self.name.replace(".", "_")
            .replace("[", "_")
            .replace("]", "_")
            .rstrip("_")
        )

    @property
    def label(self) -> str:
        """Human-readable label for the field.

        Priority:
        1. field_info.title if set
        2. Last segment of name, titlecased with underscores as spaces

        Examples:
            "email" → "Email"
            "first_name" → "First Name"
            "address.city" → "City"
        """
        if self.field_info and self.field_info.title:
            return self.field_info.title

        # Use last segment of path
        last_segment = self.name.split(".")[-1]
        # Handle list indices
        if last_segment.isdigit():
            parts = self.name.split(".")
            if len(parts) >= 2:
                last_segment = parts[-2]

        return last_segment.replace("_", " ").title()

    @property
    def has_errors(self) -> bool:
        """Whether this field has any validation errors."""
        return len(self.errors) > 0

    @property
    def first_error(self) -> str | None:
        """First validation error message, or None if no errors."""
        return self.errors[0] if self.errors else None

    @property
    def placeholder(self) -> str | None:
        """Placeholder text from field metadata.

        Looks for 'placeholder' in field_info.json_schema_extra.
        """
        if self.field_info:
            extra = self.field_info.json_schema_extra
            if isinstance(extra, dict):
                return extra.get("placeholder")
        return None

    @property
    def description(self) -> str | None:
        """Field description/help text from Pydantic metadata."""
        if self.field_info:
            return self.field_info.description
        return None

    @property
    def input_type(self) -> str:
        """Inferred HTML input type for this field.

        Uses field name patterns, type annotation, and explicit
        configuration to determine the appropriate input type.

        Examples:
            "email" field → "email"
            int annotation → "number"
            bool annotation → "checkbox"
            default → "text"
        """
        return infer_input_type(self.name, self.annotation, self.field_info)

    @property
    def constraints(self) -> dict[str, Any]:
        """HTML input constraints derived from Pydantic validation.

        Returns dict with keys like 'minlength', 'maxlength', 'min', 'max',
        'pattern' that can be spread onto an HTML input element.
        """
        return get_field_constraints(self.field_info)

    @property
    def required(self) -> bool:
        """Whether this field is required.

        A field is required if Pydantic marks it as required (no default,
        not Optional).
        """
        if self.field_info is None:
            return False

        # Use Pydantic's is_required() method if available
        if hasattr(self.field_info, "is_required"):
            return self.field_info.is_required()

        # Fallback for older Pydantic versions
        from pydantic_core import PydanticUndefined

        # Check if field has a default
        if self.field_info.default is not PydanticUndefined:
            return False
        if self.field_info.default_factory is not None:
            return False

        # Check if annotation is Optional
        if self.annotation is not None:
            from typing import Union, get_args, get_origin

            origin = get_origin(self.annotation)
            if origin is Union:
                args = get_args(self.annotation)
                if type(None) in args:
                    return False

        return True

    def with_value(self, value: Any) -> "FormField":
        """Create a new FormField with a different value.

        Useful for creating modified versions of a field.
        """
        return FormField(
            name=self.name,
            value=value,
            errors=self.errors,
            field_info=self.field_info,
            annotation=self.annotation,
        )

    def with_errors(self, errors: tuple[str, ...]) -> "FormField":
        """Create a new FormField with different errors.

        Useful for creating modified versions of a field.
        """
        return FormField(
            name=self.name,
            value=self.value,
            errors=errors,
            field_info=self.field_info,
            annotation=self.annotation,
        )
