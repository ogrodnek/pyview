from dataclasses import dataclass, field as dataclass_field
from types import SimpleNamespace
from typing import Any, Generic, Optional, TypeVar, Union, get_args, get_origin

from pydantic import BaseModel, ValidationError
from pydantic.fields import FieldInfo

from .paths import get_nested, join_path, set_nested
from .payload import parse_form_payload

Base = TypeVar("Base", bound=BaseModel)


@dataclass
class ChangeSet(Generic[Base]):
    """Tracks changes and validation state for a Pydantic model.

    ChangeSet wraps a Pydantic model class and tracks:
    - changes: Current field values being modified
    - errors: Validation errors by field path
    - valid: Overall validation state

    Supports nested models and list fields using dot-notation paths:
    - "name" - simple field
    - "address.city" - nested model field
    - "tags.0" - list index
    - "addresses.0.city" - nested list item field

    Example:
        >>> from pydantic import BaseModel
        >>> class User(BaseModel):
        ...     name: str
        ...     email: str
        >>> cs = change_set(User)
        >>> cs.apply({"name": ["John"], "_target": ["name"]})
        >>> cs["name"]
        "John"
        >>> cs.valid
        False  # email is missing
    """

    cls: type[Base]
    changes: dict[str, Any]
    errors: dict[str, Any]
    valid: bool
    action: Optional[str] = dataclass_field(default=None)

    def __getitem__(self, path: str) -> Any:
        """Get value at path. Supports dot-notation for nested fields.

        Args:
            path: Field path (e.g., "name", "address.city", "tags.0")

        Returns:
            Value at path or empty string if not found
        """
        if "." in path:
            return get_nested(self.changes, path, "")
        return self.changes.get(path, "")

    @property
    def model(self) -> Optional[Base]:
        """Get validated model instance, or None if invalid."""
        try:
            return self.cls(**self.changes)
        except ValidationError:
            return None

    @property
    def attrs(self) -> SimpleNamespace:
        """Get changes as SimpleNamespace for template access.

        Note: Only works well for flat structures. For nested access,
        use __getitem__ with dot-notation paths.
        """
        return SimpleNamespace(**self.changes)

    @property
    def fields(self) -> list[str]:
        """Get list of top-level field names from the model."""
        return list(self.cls.model_fields)

    def save(self, payload: dict[str, Any]) -> Optional[Base]:
        """Attempt to save form data and return validated model.

        Args:
            payload: Form payload dict

        Returns:
            Validated model instance or None if validation fails
        """
        self.errors = {}
        self.action = "submit"

        # Merge payload into changes
        for key, value in payload.items():
            if key.startswith("_"):
                continue
            if isinstance(value, list) and len(value) == 1:
                value = value[0]
            if "." in key:
                set_nested(self.changes, key, value)
            else:
                self.changes[key] = value

        try:
            model = self.cls(**self.changes)
            self.valid = True
            return model
        except ValidationError as e:
            self._populate_errors(e)
            return None

    def apply(self, payload: dict[str, Any]) -> "ChangeSet[Base]":
        """Apply a change from a form event.

        This is called on phx-change events for real-time validation.

        Args:
            payload: Form payload with _target indicating changed field

        Returns:
            self for method chaining
        """
        path, value = parse_form_payload(payload)

        if path:
            if "." in path:
                set_nested(self.changes, path, value)
            else:
                self.changes[path] = value

        self.errors = {}
        self.action = "validate"

        try:
            self.cls(**self.changes)
            self.valid = True
        except ValidationError as e:
            self._populate_errors(e, changed_path=path)
            self.valid = False

        return self

    def _populate_errors(
        self, error: ValidationError, changed_path: Optional[str] = None
    ) -> None:
        """Populate errors dict from ValidationError.

        Args:
            error: Pydantic ValidationError
            changed_path: If provided, only include errors for fields in changes
        """
        for err in error.errors():
            loc = err["loc"]

            if not loc:
                # Model-level validator with no location - assign to changed field
                if changed_path:
                    self.errors[changed_path] = err["msg"]
                continue

            # Build dot-notation path from location tuple
            path = join_path(*loc)

            # When validating single field change, only show errors for fields
            # that have been touched (are in changes)
            if changed_path is not None:
                if not self._path_in_changes(path):
                    continue

            self.errors[path] = err["msg"]

    def _path_in_changes(self, path: str) -> bool:
        """Check if a path corresponds to a field that has been changed."""
        # Check exact match
        if path in self.changes:
            return True

        # Check if it's a nested path under a changed field
        parts = path.split(".")
        for i in range(len(parts)):
            prefix = ".".join(parts[: i + 1])
            if prefix in self.changes:
                return True
            # Also check flat changes dict for first segment
            if parts[0] in self.changes:
                return True

        # Check using get_nested
        return get_nested(self.changes, path) is not None

    def get_field_info(self, path: str) -> Optional[FieldInfo]:
        """Get Pydantic FieldInfo for a field path.

        Args:
            path: Field path (e.g., "name", "address.city")

        Returns:
            FieldInfo or None if path is invalid
        """
        segments = path.split(".")
        model_cls: type[BaseModel] = self.cls

        for i, segment in enumerate(segments):
            # Skip numeric segments (list indices)
            if segment.isdigit():
                continue

            if not hasattr(model_cls, "model_fields"):
                return None

            field_info = model_cls.model_fields.get(segment)
            if field_info is None:
                return None

            # If this is the last segment, return the field info
            if i == len(segments) - 1:
                return field_info

            # Otherwise, get the nested model class
            annotation = field_info.annotation
            if annotation is None:
                return None

            # Unwrap Optional, list, etc. to get inner type
            inner_type = self._unwrap_annotation(annotation)
            if inner_type is None or not isinstance(inner_type, type):
                return None

            if not issubclass(inner_type, BaseModel):
                # Reached a non-model type before end of path
                return None

            model_cls = inner_type

        return None

    def _unwrap_annotation(self, annotation: Any) -> Any:
        """Unwrap Optional, list, etc. to get the inner type."""
        origin = get_origin(annotation)

        # Handle Optional[X] -> X
        if origin is Union:
            args = get_args(annotation)
            non_none = [a for a in args if a is not type(None)]
            if non_none:
                return self._unwrap_annotation(non_none[0])
            return None

        # Handle list[X] -> X
        if origin is list:
            args = get_args(annotation)
            if args:
                return self._unwrap_annotation(args[0])
            return None

        return annotation


def change_set(cls: type[Base], initial: Optional[dict[str, Any]] = None) -> ChangeSet[Base]:
    """Create a new ChangeSet for a Pydantic model class.

    Args:
        cls: Pydantic model class
        initial: Optional initial values

    Returns:
        New ChangeSet instance
    """
    return ChangeSet(cls, initial or {}, {}, False)
