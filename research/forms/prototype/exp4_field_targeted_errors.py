"""Experiment 4: can a model_validator attach errors to specific field paths?"""
from typing import Any
from pydantic import BaseModel, Field, ValidationError, model_validator, field_validator, ValidationInfo
from pydantic_core import PydanticCustomError, InitErrorDetails

class FieldErrors(Exception):
    """Helper: raise from a model_validator with {path: (code, message, ctx)} to attach errors to fields."""
    def __init__(self, errors: dict[str, str | tuple]):
        self.errors = errors

class Reg(BaseModel):
    password: str = Field(min_length=8)
    password_confirmation: str
    start: int
    end: int

    @model_validator(mode="after")
    def check(self):
        line_errors: list[InitErrorDetails] = []
        if self.password != self.password_confirmation:
            line_errors.append(InitErrorDetails(type=PydanticCustomError("mismatch", "Passwords do not match"),
                                                loc=("password_confirmation",), input=self.password_confirmation))
        if self.end < self.start:
            line_errors.append(InitErrorDetails(type=PydanticCustomError("range", "End must be after start ({start})", {"start": self.start}),
                                                loc=("end",), input=self.end))
        if line_errors:
            raise ValidationError.from_exception_data(self.__class__.__name__, line_errors)
        return self

try:
    Reg.model_validate({"password": "longenough", "password_confirmation": "nope", "start": "5", "end": "1"})
except ValidationError as e:
    for err in e.errors(include_url=False):
        print(err["loc"], err["type"], err["msg"], err.get("ctx"))

print("--- combined with a field error (does the model validator still run? no: after-validators skip when fields failed)")
try:
    Reg.model_validate({"password": "short", "password_confirmation": "nope", "start": "5", "end": "1"})
except ValidationError as e:
    for err in e.errors(include_url=False):
        print(err["loc"], err["type"], err["msg"])

print("--- idiomatic: field_validator with info.data (loc on the second field)")
class Reg2(BaseModel):
    password: str = Field(min_length=8)
    password_confirmation: str
    @field_validator("password_confirmation")
    @classmethod
    def match(cls, v, info: ValidationInfo):
        if "password" in info.data and v != info.data["password"]:
            raise PydanticCustomError("mismatch", "Passwords do not match")
        return v
try:
    Reg2.model_validate({"password": "longenough", "password_confirmation": "nope"})
except ValidationError as e:
    for err in e.errors(include_url=False):
        print(err["loc"], err["type"], err["msg"])

print("--- nested: errors from a model_validator inside a list item keep the outer path?")
class Item(BaseModel):
    lo: int; hi: int
    @model_validator(mode="after")
    def order(self):
        if self.hi < self.lo:
            raise ValidationError.from_exception_data("Item", [InitErrorDetails(type=PydanticCustomError("order", "hi < lo"), loc=("hi",), input=self.hi)])
        return self
class Outer(BaseModel):
    items: list[Item]
try:
    Outer.model_validate({"items": [{"lo": 1, "hi": 2}, {"lo": 5, "hi": 1}]})
except ValidationError as e:
    for err in e.errors(include_url=False):
        print(err["loc"], err["type"], err["msg"])
