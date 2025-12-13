from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, ValidationError

Base = TypeVar("Base", bound=BaseModel)


@dataclass
class ChangeSet(Generic[Base]):
    cls: type[Base]
    changes: dict[str, Any]
    errors: dict[str, Any]
    valid: bool
    used_fields: set[str] = field(default_factory=set)

    def __getitem__(self, key: str) -> Any:
        return self.changes.get(key, "")

    @property
    def model(self) -> Optional[Base]:
        try:
            return self.cls(**self.changes)
        except ValidationError:
            return None

    @property
    def attrs(self) -> SimpleNamespace:
        return SimpleNamespace(**self.changes)

    @property
    def fields(self) -> list[str]:
        return list(self.cls.model_fields)

    def used_input(self, field_name: str) -> bool:
        """Check if user has interacted with this field.

        LiveView 1.0+ sends _unused_<fieldname> for fields the user hasn't touched.
        This replaces the deprecated phx-feedback-for client-side attribute.
        """
        return field_name in self.used_fields

    def save(self, payload: dict[str, Any]) -> Optional[Base]:
        self.errors = {}
        try:
            model = self.cls(**payload)
            return model
        except ValidationError as e:
            for error in e.errors():
                loc = str(error["loc"][0])
                self.errors[loc] = error["msg"]
            return None

    def apply(self, payload: dict[str, Any]):
        target = payload.get("_target")
        if not target:
            return
        k = target[0]
        self.changes[k] = payload.get(k, [""])[0]
        self.errors = {}

        # Track which fields have been used (interacted with by user)
        # LiveView 1.0+ sends _unused_<fieldname> for untouched fields
        for field_name in self.fields:
            unused_key = f"_unused_{field_name}"
            if unused_key not in payload:
                # Field has been used (no _unused_ marker)
                self.used_fields.add(field_name)

        try:
            self.cls(**self.changes)
            self.valid = True
        except ValidationError as e:
            for error in e.errors():
                loc = str(error["loc"][0])
                if loc in self.changes:
                    self.errors[loc] = error["msg"]
            self.valid = False


def change_set(cls: type[Base]) -> ChangeSet[Base]:
    return ChangeSet(cls, {}, {}, False)
