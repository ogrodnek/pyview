from typing import TypeVar, Any, Generic, Optional
from pydantic import BaseModel, ValidationError
from dataclasses import dataclass
from types import SimpleNamespace

Base = TypeVar("Base", bound=BaseModel)


@dataclass
class ChangeSet(Generic[Base]):
    cls: type[Base]
    changes: dict[str, Any]
    errors: dict[str, Any]
    valid: bool

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
        k = payload["_target"][0]
        self.changes[k] = payload.get(k, [""])[0]
        self.errors = {}

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
