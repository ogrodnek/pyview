"""Experiment 2: lax-mode coercion of typical HTML form strings (no model validator interference),
single-field validation from FieldInfo, and timing of full revalidation."""
import time, datetime, decimal, enum
from typing import Optional, Literal, Annotated
from pydantic import BaseModel, Field, ValidationError, TypeAdapter, ConfigDict
from pydantic.fields import FieldInfo

class Color(enum.Enum):
    red = "red"; blue = "blue"

class M(BaseModel):
    age: int = 0
    price: decimal.Decimal = decimal.Decimal(0)
    ratio: float = 0.0
    flag: bool = False
    tags: list[str] = []
    nums: list[int] = []
    when: datetime.date | None = None
    at: datetime.datetime | None = None
    color: Color = Color.red
    lit: Literal["a", "b"] = "a"
    opt_s: Optional[str] = None
    opt_i: Optional[int] = None

cases = [
    {"age": ""}, {"age": " 21 "}, {"age": "21.0"}, {"age": "1e3"},
    {"price": "1,5"}, {"price": "1.50"}, {"ratio": "1,5"},
    {"flag": ""}, {"flag": "on"}, {"flag": "off"}, {"flag": "yes"}, {"flag": "true"}, {"flag": "0"}, {"flag": "checked"},
    {"tags": "a"}, {"tags": ["a", "b"]}, {"nums": ["1", "x"]},
    {"when": "2024-05-01"}, {"when": ""}, {"at": "2024-05-01T13:45"}, {"at": ""},
    {"color": "blue"}, {"color": ""}, {"lit": "c"},
    {"opt_s": ""}, {"opt_i": ""},
]
for c in cases:
    try:
        r = M.model_validate(c)
        print(f"{str(c):32} -> {[(k, getattr(r, k)) for k in c]}")
    except ValidationError as e:
        print(f"{str(c):32} -> ERR {[(x['loc'], x['type']) for x in e.errors()]}")

print("--- str_strip_whitespace + empty-string-to-None via a wrap validator on the *form layer*")
from pydantic import BeforeValidator, WrapValidator
from pydantic_core import PydanticUseDefault

def empty_to_default(v):
    if v == "":
        raise PydanticUseDefault()
    return v

class M2(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    opt_i: Annotated[Optional[int], BeforeValidator(empty_to_default)] = None
    age: Annotated[int, BeforeValidator(empty_to_default)] = 0
    name: str = ""
print(M2.model_validate({"opt_i": "", "age": "", "name": "  hi  "}))

print("--- validate ONE field using its FieldInfo (for per-field validation)")
fi: FieldInfo = M.model_fields["age"]
ta = TypeAdapter(Annotated[fi.annotation, fi])
for v in ["12", "x"]:
    try:
        print(v, "->", ta.validate_python(v))
    except ValidationError as e:
        print(v, "-> ERR", [(x["loc"], x["type"]) for x in e.errors()])

class Big(BaseModel):
    f1: str = Field(min_length=1); f2: str = Field(min_length=1); f3: int = Field(ge=0); f4: int = Field(ge=0)
    f5: str = ""; f6: str = ""; f7: float = 0; f8: float = 0; f9: bool = False; f10: bool = False
class Outer(BaseModel):
    a: Big; b: Big; items: list[Big] = Field(min_length=1)
    name: str = Field(min_length=2)
data = {"a": {"f1": "x", "f2": "y", "f3": "1", "f4": "2"}, "b": {"f1": "x", "f2": "y", "f3": "1", "f4": "2"},
        "items": [{"f1": "x", "f2": "y", "f3": "1", "f4": "2"} for _ in range(10)], "name": "ok"}
t = time.perf_counter(); N = 2000
for _ in range(N):
    Outer.model_validate(data)
dt = (time.perf_counter() - t) / N
print(f"--- full validate of a 3-level model with 14 sub-objects (~60 fields): {dt*1e6:.0f} µs per validation")
