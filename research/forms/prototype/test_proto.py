import sys; sys.path.insert(0, __import__("os").path.dirname(__file__))
from urllib.parse import parse_qsl, urlencode
from typing import Annotated, Literal, Optional
from pydantic import BaseModel, Field
from pyview_forms_proto import decode_form, Form, normalize_empty

# 1. decoder
cases = [
    "a=1&b=2",
    "user[name]=Larry&user[age]=3",
    "tags[]=a&tags[]=b",
    "user[addresses][0][city]=Paris&user[addresses][2][city]=Rome",   # sparse after a removal
    "items[][name]=a&items[][name]=b",
    "a=1&a=2",
    "user[tags][]=x&_target=user[tags][]&_csrf_token=abc",
    "user[addresses][1][city]=Rome&_target=user[addresses][1][city]",
    "_unused_user[name]=&user[name]=",
]
for c in cases:
    data, meta = decode_form(parse_qsl(c, keep_blank_values=True))
    print(f"{c:70} -> {data}  meta={meta}")

# 2. form state with nested list + discriminated union
class Address(BaseModel):
    street: str = Field(min_length=3)
    city: str
class Personal(BaseModel):
    kind: Literal["personal"]
    nickname: str = Field(min_length=2)
class Business(BaseModel):
    kind: Literal["business"]
    company: str = Field(min_length=2, title="Company name")
class Profile(BaseModel):
    name: str = Field(min_length=3, max_length=20)
    age: int = Field(ge=18)
    newsletter: bool = False
    addresses: list[Address] = Field(min_length=1)
    account: Annotated[Personal | Business, Field(discriminator="kind")]

form = Form.for_model(Profile, as_="profile")
def change(**kw):
    """simulate the Phoenix client: whole form serialized + _target"""
    return parse_qsl(urlencode(list(kw.items())), keep_blank_values=True)

# user types 'ab' in name: only name errors are visible
form.validate([("profile[name]", "ab"), ("profile[age]", ""), ("profile[addresses][0][street]", ""), ("profile[addresses][0][city]", ""),
               ("profile[account][kind]", "business"), ("profile[account][company]", ""), ("_target", "profile[name]")])
print("valid:", form.valid, "| all errors:", [(e.path, e.code) for e in form.errors])
print("visible name:", form["name"].errors, "| visible age:", form["age"].errors, "| visible company:", form["account"]["company"].errors)
# user tabs to age, types 17
form.validate([("profile[name]", "ab"), ("profile[age]", "17"), ("profile[addresses][0][street]", ""), ("profile[addresses][0][city]", ""),
               ("profile[account][kind]", "business"), ("profile[account][company]", ""), ("_target", "profile[age]")])
print("visible age:", form["age"].errors, "| value kept:", form["age"].value, "| attrs:", form["age"].constraints, form["age"].input_type)
# nested row + union field after typing in them
form.validate([("profile[name]", "Larry"), ("profile[age]", "40"), ("profile[addresses][0][street]", "x"), ("profile[addresses][0][city]", "Paris"),
               ("profile[account][kind]", "business"), ("profile[account][company]", "A"), ("_target", "profile[account][company]")])
print("company:", form["account"]["company"].errors, "label:", form["account"]["company"].label, "name:", form["account"]["company"].name, "id:", form["account"]["company"].id)
print("street (not yet used):", form["addresses"][0]["street"].errors)
# submit: everything visible
form.submit([("profile[name]", "Larry"), ("profile[age]", "40"), ("profile[addresses][0][street]", "x"), ("profile[addresses][0][city]", "Paris"),
             ("profile[account][kind]", "business"), ("profile[account][company]", "A")])
print("after submit street:", form["addresses"][0]["street"].errors, "| rows:", [f.name for f in form["addresses"]])
form.submit([("profile[name]", "Larry"), ("profile[age]", "40"), ("profile[addresses][0][street]", "Main St"), ("profile[addresses][0][city]", "Paris"),
             ("profile[account][kind]", "business"), ("profile[account][company]", "ACME")])
print("valid:", form.valid, form.model)
print("required attr on name:", form["name"].constraints, "| newsletter:", form["newsletter"].input_type, form["newsletter"].constraints)
