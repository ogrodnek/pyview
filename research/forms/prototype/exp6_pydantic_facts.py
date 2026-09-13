"""Experiment 6: model_validate_strings on form dicts, errors() options, alias runtime flags,
TypeAdapter for stdlib dataclass/TypedDict, MISSING, Discriminator custom errors, JSON-schema formats,
PydanticKnownError, timing of validate_assignment."""
import dataclasses, datetime, json, timeit
from typing import Annotated, Literal, Optional
from typing_extensions import TypedDict
from pydantic import (BaseModel, Field, ValidationError, TypeAdapter, ConfigDict, EmailStr, SecretStr,
                      HttpUrl, Discriminator, Tag, field_validator)
from pydantic_core import PydanticKnownError, MISSING, PydanticCustomError

class Sub(BaseModel):
    n: int
class F(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
    age: int
    ok: bool = False
    when: datetime.date | None = None
    sub: Sub | None = None
    tags: list[int] = []
print("--- model_validate_strings (JSON-mode rules on a str-only nested dict)")
for d in [{"age": "21"}, {"age": " 21 "}, {"age": "21.0"}, {"age": "21", "ok": "on"}, {"age": "21", "when": "2024-05-01"},
          {"age": "21", "sub": {"n": "3"}}, {"age": "21", "tags": ["1", "2"]}, {"age": ""}, {"age": "21", "when": ""}]:
    try: print(d, "->", F.model_validate_strings(d).model_dump())
    except ValidationError as e: print(d, "-> ERR", [(x["loc"], x["type"]) for x in e.errors()])

print("--- errors() options")
try: F.model_validate({"age": "x", "sub": {"n": "y"}})
except ValidationError as e:
    print(e.error_count(), e.title)
    print(e.errors(include_url=False, include_context=False, include_input=False))
    print(json.loads(e.json(include_url=False))[0])

print("--- runtime by_alias / by_name")
class A(BaseModel):
    first_name: str = Field(alias="firstName", title="First name", description="Given name", examples=["Ada"],
                            json_schema_extra={"x-widget": "text"})
print(A.model_validate({"first_name": "x"}, by_name=True, by_alias=False))
try: A.model_validate({"first_name": "x"})
except ValidationError as e: print("default: loc uses alias ->", e.errors()[0]["loc"])
fi = A.model_fields["first_name"]
print("FieldInfo:", fi.alias, fi.title, fi.description, fi.examples, fi.json_schema_extra, fi.is_required(), fi.get_default())

print("--- TypeAdapter for stdlib dataclass / TypedDict")
@dataclasses.dataclass
class DC:
    x: int
    y: str = "d"
class TD(TypedDict):
    a: int
ta = TypeAdapter(DC); print(ta.validate_python({"x": "5"}), ta.validate_strings({"x": "6"}))
try: TypeAdapter(TD).validate_python({"a": "z"})
except ValidationError as e: print(e.errors(include_url=False)[0]["loc"], e.title)
print("stdlib dc fields via TypeAdapter core schema? ->", ta.core_schema["type"], [f["name"] for f in ta.core_schema["schema"]["fields"]])

print("--- MISSING sentinel (2.12+, experimental)")
class Patch(BaseModel):
    name: str | MISSING = MISSING
p = Patch.model_validate({}); print(repr(p), p.model_dump(exclude_unset=True), p.name is MISSING)

print("--- Discriminator custom error")
class Cat(BaseModel): kind: Literal["cat"]
class Dog(BaseModel): kind: Literal["dog"]
def disc(v): return (v.get("kind") if isinstance(v, dict) else getattr(v, "kind", None))
class Pet(BaseModel):
    pet: Annotated[Annotated[Cat, Tag("cat")] | Annotated[Dog, Tag("dog")],
                   Discriminator(disc, custom_error_type="bad_pet", custom_error_message="Choose cat or dog", custom_error_context={"x": 1})]
try: Pet.model_validate({"pet": {"kind": "cow"}})
except ValidationError as e: print(e.errors(include_url=False))
try: Pet.model_validate({"pet": {}})
except ValidationError as e: print(e.errors(include_url=False)[0]["type"])

print("--- JSON schema format hints")
class S(BaseModel):
    pw: SecretStr; url: HttpUrl; d: datetime.date; dt: datetime.datetime
    n: int = Field(ge=1, le=10, multiple_of=2); s: str = Field(min_length=2, pattern="^a"); c: Literal["x", "y"]
for k, v in S.model_json_schema()["properties"].items(): print(" ", k, v)

print("--- PydanticKnownError reuse of built-in messages")
class K(BaseModel):
    v: str
    @field_validator("v")
    @classmethod
    def f(cls, v):
        raise PydanticKnownError("string_too_short", {"min_length": 3})
try: K(v="a")
except ValidationError as e: print(e.errors(include_url=False)[0]["msg"], e.errors()[0]["type"])

print("--- validate_assignment timing (single-field validation)")
f = F(age=1); print("assign us:", round(timeit.timeit(lambda: setattr(f, "age", "22"), number=20000)/20000*1e6, 2))
print("TypeAdapter(int) us:", round(timeit.timeit(lambda: TypeAdapter(int).validate_python("22"), number=2000)/2000*1e6, 1), "(includes construction!)")
ti = TypeAdapter(int); print("prebuilt TA us:", round(timeit.timeit(lambda: ti.validate_python("22"), number=20000)/20000*1e6, 2))
