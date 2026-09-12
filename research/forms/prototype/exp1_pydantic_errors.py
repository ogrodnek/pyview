"""Experiment 1: what pydantic v2 error locs look like for nested/list/discriminated-union models,
and how lax coercion treats typical HTML form strings."""
from typing import Literal, Annotated, Optional
from pydantic import BaseModel, Field, ValidationError, TypeAdapter, model_validator
import pydantic, json

print("pydantic", pydantic.VERSION)

class Address(BaseModel):
    street: str = Field(min_length=3)
    city: str
    zip: str = Field(pattern=r"^\d{5}$")

class Personal(BaseModel):
    kind: Literal["personal"]
    nickname: str = Field(min_length=2)

class Business(BaseModel):
    kind: Literal["business"]
    company: str = Field(min_length=2)
    vat: Optional[str] = None

class Profile(BaseModel):
    name: str = Field(min_length=3, max_length=20)
    age: int = Field(ge=18)
    newsletter: bool = False
    tags: list[str] = []
    addresses: list[Address] = Field(min_length=1)
    account: Annotated[Personal | Business, Field(discriminator="kind")]

    @model_validator(mode="after")
    def check(self):
        if self.name.lower() == "admin":
            raise ValueError("name cannot be admin")
        return self

bad = {
    "name": "ad",
    "age": "17",
    "newsletter": "on",
    "tags": ["a", "b"],
    "addresses": [{"street": "x", "city": "", "zip": "1234"}, {"street": "long street", "city": "Paris", "zip": "12345"}],
    "account": {"kind": "business", "company": "A"},
}
try:
    Profile.model_validate(bad)
except ValidationError as e:
    for err in e.errors(include_url=False):
        print(err["loc"], "|", err["type"], "|", err["msg"], "|", err.get("ctx"))

print("--- model-level validator loc")
good = dict(bad, name="admin", age="20", addresses=[bad["addresses"][1]], account={"kind": "business", "company": "ACME"})
try:
    Profile.model_validate(good)
except ValidationError as e:
    for err in e.errors(include_url=False):
        print(err["loc"], "|", err["type"], "|", err["msg"])

print("--- coercion of form strings")
for raw in [{"age": ""}, {"age": " 21 "}, {"newsletter": ""}, {"newsletter": "off"}, {"newsletter": "yes"}, {"tags": "a"}]:
    try:
        r = Profile.model_validate({**good, **raw})
        print(raw, "->", {k: getattr(r, k) for k in raw})
    except ValidationError as e:
        print(raw, "-> ERR", [(x["loc"], x["type"]) for x in e.errors()])

print("--- Optional[int] with empty string")
class M(BaseModel):
    n: Optional[int] = None
    s: Optional[str] = None
try:
    print(M.model_validate({"n": "", "s": ""}))
except ValidationError as e:
    print("ERR", [(x["loc"], x["type"]) for x in e.errors()])

print("--- discriminator missing/invalid")
try:
    Profile.model_validate({**good, "account": {"kind": "other"}})
except ValidationError as e:
    for err in e.errors(include_url=False):
        print(err["loc"], "|", err["type"], "|", err["msg"], "|", err.get("ctx"))

print("--- partial validation (experimental_allow_partial)")
ta = TypeAdapter(Profile)
try:
    r = ta.validate_python({"name": "Larry", "age": "30", "addresses": [{"street": "long street"}]}, experimental_allow_partial=True)
    print("partial ok ->", r)
except ValidationError as e:
    print("partial ERR", [(x["loc"], x["type"]) for x in e.errors()])
try:
    r = ta.validate_python({"name": "Larry"}, experimental_allow_partial="trailing-strings")
    print("partial ok ->", r)
except ValidationError as e:
    print("partial ERR", [(x["loc"], x["type"]) for x in e.errors()])

print("--- single-field validation via validate_assignment")
class P2(Profile):
    model_config = {"validate_assignment": True}
inst = P2.model_construct(name="ok!", age=1)
try:
    inst.name = "ab"
except ValidationError as e:
    print("assignment ERR", [(x["loc"], x["type"]) for x in e.errors()])
print("--- introspection")
for name, fi in Profile.model_fields.items():
    print(name, fi.annotation, "required=", fi.is_required(), "default=", fi.default if fi.default is not pydantic.fields.PydanticUndefined else "<undef>", "meta=", fi.metadata)
