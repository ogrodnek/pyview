import json, datetime
from typing import Literal, Annotated, Union
from pydantic import BaseModel, Field, ValidationError, EmailStr, field_validator, model_validator, Tag, Discriminator
from pydantic_core import PydanticCustomError
from decimal import Decimal
from enum import Enum
class Color(str, Enum): red="red"; blue="blue"
class Cat(BaseModel): kind: Literal["cat"]; lives: int
class Dog(BaseModel): kind: Literal["dog"]; bark: bool
class Addr(BaseModel):
    street: str = Field(min_length=3, title="Street address"); zip: str = Field(pattern=r"^\d{5}$")
class M(BaseModel, extra="forbid"):
    name: str = Field(min_length=2, max_length=5)
    age: int = Field(ge=18, le=99, multiple_of=1)
    score: float = Field(gt=0, lt=1)
    ok: bool; color: Color; when: datetime.date; dt: datetime.datetime; price: Decimal = Field(max_digits=4, decimal_places=1)
    tags: list[str] = Field(min_length=1, max_length=2); lit: Literal["a","b"]
    pet: Union[Cat, Dog] = Field(discriminator="kind")
    addr: Addr; addrs: list[Addr]; nick: str | None
    @field_validator("name")
    @classmethod
    def no_bob(cls, v):
        if v == "bob": raise PydanticCustomError("reserved_name", "Name '{name}' is reserved", {"name": v})
        return v
    @model_validator(mode="after")
    def check(self):
        if self.age == 20: raise ValueError("age 20 not allowed")
        return self
cases = [
 dict(),  # missing
 dict(name="a", age="x", score="1.5", ok="maybe", color="green", when="2020-13-01", dt="nope", price="123456", tags=[], lit="c", pet={"kind":"cow"}, addr={"street":"ab","zip":"1"}, addrs=[{"street":"ok st","zip":"x"}], nick=None, extra=1),
 dict(name="bob", age=17, score=0, ok=True, color="red", when="2020-01-01", dt="2020-01-01T00:00:00", price="1.23", tags=["a","b","c"], lit="a", pet={"lives":"two"}, addr={"street":"abc","zip":"12345"}, addrs="notalist", nick=None),
 dict(name="abcdefg", age=20, score=0.5, ok=True, color="red", when="2020-01-01", dt="2020-01-01T00:00:00", price="1.2", tags=["a"], lit="a", pet={"kind":"cat","lives":9}, addr={"street":"abc","zip":"12345"}, addrs=[], nick=None),
]
seen = {}
for c in cases:
    try: M(**c)
    except ValidationError as e:
        for err in e.errors(include_url=False):
            seen.setdefault(err["type"], (err["loc"], err["msg"], err.get("ctx"), err["input"] if not isinstance(err["input"], dict) else "<dict>"))
for t,(loc,msg,ctx,inp) in sorted(seen.items()):
    print(f"{t:28s} loc={loc!r:40s} ctx={ctx!r}\n{'':28s} msg={msg!r}")
print(len(seen), "types")
