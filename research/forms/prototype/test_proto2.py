import sys; sys.path.insert(0, __import__("os").path.dirname(__file__))
from typing import Annotated, Literal
from pydantic import BaseModel, Field
from pyview_forms_proto2 import Form

class Address(BaseModel):
    street: str = Field(min_length=3)
    city: str
class Personal(BaseModel):
    kind: Literal["personal"] = "personal"
    nickname: str = Field(min_length=2)
class Business(BaseModel):
    kind: Literal["business"] = "business"
    company: str = Field(min_length=2)
class Profile(BaseModel):
    name: str = Field(min_length=3)
    addresses: list[Address] = Field(min_length=1)
    account: Annotated[Personal | Business, Field(discriminator="kind")]

def serialize(form, extra=(), target=None):
    """Simulate the 0.20.17 client: FormData of the *rendered* inputs (from form.params), in order,
    plus the submitter pair (extra), plus _target."""
    pairs = []
    p = form.params
    pairs.append(("profile[name]", p.get("name", "")))
    for i, row in enumerate(p.get("addresses", [])):
        pairs.append((f"profile[addresses][{i}][_key]", row["_key"]))
        pairs.append((f"profile[addresses][{i}][street]", row.get("street", "")))
        pairs.append((f"profile[addresses][{i}][city]", row.get("city", "")))
    acct = p.get("account", {"kind": "personal"})
    pairs.append(("profile[account][kind]", acct["kind"]))
    if acct["kind"] == "personal":
        pairs.append(("profile[account][nickname]", acct.get("nickname", "")))
    else:
        pairs.append(("profile[account][company]", acct.get("company", "")))
    pairs.extend(extra)
    if target:
        pairs.append(("_target", target))
    return pairs

form = Form.for_model(Profile, as_="profile")
form.validate([("profile[name]", "Larry"), ("profile[addresses][0][street]", "Main St"), ("profile[addresses][0][city]", "Paris"),
               ("profile[account][kind]", "business"), ("profile[account][company]", "ACME"), ("_target", "profile[name]")])
rows = form["addresses"].items()
print("rows:", [(r.key, r.id, r.name) for r in rows])
print("add button:", form["addresses"].intent_button("add", "Add address"))

# click "Add address": the button (name=profile[addresses][_intent] value=add) is the submitter
form.validate(serialize(form, extra=[("profile[addresses][_intent]", "add")], target="profile[addresses][_intent]"))
rows = form["addresses"].items()
print("after add:", [(r.key, r["street"].value) for r in rows], "| visible errors row2:", rows[1]["street"].errors, "| all errors:", [(e.path, e.code) for e in form.errors])
k1, k2 = rows[0].key, rows[1].key

# type into row 2, then remove row 1 -> row 2 keeps key + value
form.params["addresses"][1]["street"] = "Second Ave"
form.validate(serialize(form, extra=[("profile[addresses][_intent]", f"remove:{k1}")], target="profile[addresses][_intent]"))
rows = form["addresses"].items()
print("after remove:", [(r.key, r["street"].value, r["street"].name, r["street"].id) for r in rows])
assert rows[0].key == k2 and rows[0]["street"].value == "Second Ave" and rows[0]["street"].name == "profile[addresses][0][street]"

# add again and move the new row up
form.validate(serialize(form, extra=[("profile[addresses][_intent]", "add")]))
k3 = form["addresses"].items()[1].key
form.validate(serialize(form, extra=[("profile[addresses][_intent]", f"move:{k3}:up")]))
print("after move:", [r.key for r in form["addresses"].items()], "(k3 first)")
assert [r.key for r in form["addresses"].items()] == [k3, k2]

# union shelf: switch business -> personal -> business keeps company
form.validate(serialize(form) and [p if p[0] != "profile[account][kind]" else (p[0], "personal") for p in serialize(form) if not p[0].startswith("profile[account][company]")] + [("profile[account][nickname]", ""), ("_target", "profile[account][kind]")])
print("switched to personal; params.account =", form.params["account"], "| shelf:", form.shelf)
form.validate([p if p[0] != "profile[account][kind]" else (p[0], "business") for p in serialize(form) if not p[0].startswith("profile[account][nickname]")] + [("_target", "profile[account][kind]")])
print("switched back; company restored:", form["account"]["company"].value)
assert form["account"]["company"].value == "ACME"
form.params["addresses"][0].update(street="New Row St", city="Rome")
form.params["addresses"][1].update(city="Lyon")
print("model after submit:", form.submit(serialize(form)).model, [(e.path, e.code) for e in form.errors])
assert form.valid and [a.street for a in form.model.addresses] == ["New Row St", "Second Ave"]
print("ALL OK")
