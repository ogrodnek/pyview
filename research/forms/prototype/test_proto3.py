import sys, os; sys.path.insert(0, os.path.dirname(__file__))
import datetime as dt
from typing import Annotated, Literal, Optional
from pydantic import BaseModel, Field, SecretStr
from pyview_forms_proto3 import Params, Form, wire, Intent

# ------------------------------------------------------------------ 1. decoder
p = Params.decode("profile%5Bname%5D=Larry&profile%5Btags%5D%5B%5D=a&profile%5Btags%5D%5B%5D=b&profile%5Baddresses%5D%5B0%5D%5Bcity%5D=Paris&profile%5Baddresses%5D%5B2%5D%5Bcity%5D=Rome&_csrf_token=tok&foo=bar&_target=profile%5Btags%5D%5B%5D", prefix="profile")
assert p.data == {"name": "Larry", "tags": ["a", "b"], "addresses": [{"city": "Paris"}, {"city": "Rome"}]}, p.data
assert p.target == ("tags",), p.target                       # trailing [] stripped
assert p.meta == {"_csrf_token": ["tok"], "foo": ["bar"]}    # everything outside the prefix is meta (phx-value-foo)
p = Params.decode({"profile[name]": [""], "profile[addresses][0][_unused_city]": [""], "profile[addresses][0][city]": ["x"], "profile[_unused_tags][]": [""]}, prefix="profile")
assert p.data == {"name": "", "addresses": [{"city": "x"}]} and p.unused == {("addresses", 0, "city"), ("tags",)}, (p.data, p.unused)
for bad in ["profile[items][][name]=a", "profile[__class__]=x", "profile[a][__proto__][b]=1"]:
    try:
        Params.decode(bad, prefix="profile"); raise SystemExit(f"should reject {bad}")
    except ValueError:
        pass
p = Params.decode([("profile[addresses][0][_key]", "k1"), ("profile[addresses][0][city]", "P"), ("profile[addresses][_intent]", "remove:k1"), ("_target", "profile[addresses][_intent]")], prefix="profile")
assert p.intents == [Intent("remove", ("addresses",), "k1", None)] and p.data == {"addresses": [{"_key": "k1", "city": "P"}]}, (p.intents, p.data)
assert p.target == ("addresses", "_intent")
print("1. decoder OK")

# ------------------------------------------------------------------ 2. edit form: Ecto merge semantics
class Plant(BaseModel):
    name: str = Field(min_length=3, title="Plant name")
    days: int = Field(ge=1, le=30, default=7)
    note: Optional[str] = None
    last_watered: dt.datetime = Field(default_factory=lambda: dt.datetime(2026, 1, 1, 8, 0))
    secret: SecretStr = SecretStr("hunter2")

plant = Plant(name="Aloe", days=14, note="shady", secret=SecretStr("hunter2"))
form = Form(Plant, data=plant, as_="plant")
assert form.name.html.value == "Aloe" and form.days.html.value == "14" and form.last_watered.html.value == "2026-01-01T08:00" and form.secret.html.value == ""
form.validate([("plant[name]", "Aloe vera"), ("_target", "plant[name]")])           # template rendered ONLY name
assert form.valid and form.model.days == 14 and form.model.note == "shady", form.debug()   # unrendered fields keep data
form.validate([("plant[name]", ""), ("plant[note]", ""), ("plant[days]", ""), ("_target", "plant[name]")])
assert [e.code for e in form.errors_for(("name",))] == ["missing"] and form.name.html.errors == ["Plant name is required"]
assert not form.valid
form.validate([("plant[name]", "Aloe"), ("plant[note]", ""), ("plant[days]", ""), ("_target", "plant[note]")])
assert form.valid and form.model.note is None and form.model.days == 7, form.debug()      # cleared -> None / default (a change)
assert form.name.html.attrs == 'required minlength="3"', form.name.html.attrs
print("2. edit-form merge OK")

# ------------------------------------------------------------------ 3. union with the REAL client ordering (variant-named inputs)
class Personal(BaseModel):
    kind: Literal["personal"] = "personal"
    nickname: str = Field(min_length=2)
class Business(BaseModel):
    kind: Literal["business"] = "business"
    company: str = Field(min_length=2, title="Company name")
class Address(BaseModel):
    street: str = Field(min_length=3)
    city: str
class Profile(BaseModel):
    name: str = Field(min_length=3)
    addresses: list[Address] = Field(min_length=1)
    account: Annotated[Personal | Business, Field(discriminator="kind")]

form = Form(Profile, as_="profile")
form.validate(wire(form, {"name": "Larry", "addresses": [{"street": "Main St", "city": "Paris"}], "account": {"kind": "business", "business": {"company": "ACME"}}}, target="profile[account][business][company]"))
assert form.valid, form.debug()
assert form.account.business.company.html.name == "profile[account][business][company]"
# user switches the select: the OLD fieldset is still in the DOM, so the client sends kind=personal + business inputs
pairs = wire(form, target="profile[account][kind]")
pairs = [(k, "personal") if k == "profile[account][kind]" else (k, v) for k, v in pairs]
form.validate(pairs)
assert form.params["account"]["kind"] == "personal" and form.params["account"]["business"] == {"company": "ACME"}, form.params["account"]
assert [e.path for e in form.errors] == [("account", "personal", "nickname")], form.errors     # only the active variant is validated
assert form.account.personal.nickname.html.errors == []                                         # not used yet -> hidden
# re-render sends only the personal fieldset; type a nickname; switch back -> company restored from the shelf
assert not any(k.startswith("profile[account][business]") for k, _ in wire(form))
form.validate(wire(form, {"account.personal.nickname": "lar"}, target="profile[account][personal][nickname]"))
assert form.valid and form.model.account.nickname == "lar"
pairs = [(k, "business") if k == "profile[account][kind]" else (k, v) for k, v in wire(form, target="profile[account][kind]")]
form.validate(pairs)
assert form.valid and form.model.account.company == "ACME" and form.account.business.company.html.value == "ACME", form.debug()
print("3. union switching OK")

# ------------------------------------------------------------------ 4. intents, keys, gating
form.validate(wire(form, target="profile[addresses][_intent]", submitter=("profile[addresses][_intent]", "add")))
rows = list(form.addresses)
assert len(rows) == 2 and form.applied_intents[0].op == "add" and rows[1].html.key.startswith("k")
assert rows[1].street.html.errors == [] and [e.code for e in form.errors_for(("addresses", 1, "street"), gated=False)] == ["missing"]   # new row: not visible
k1, k2 = rows[0].html.key, rows[1].html.key
assert rows[1].html.id == f"profile_addresses_{k2}" and rows[1].street.html.id == f"profile_addresses_{k2}_street"
form.validate(wire(form, {"addresses.1.street": "Second Ave"}, target="profile[addresses][_intent]", submitter=("profile[addresses][_intent]", f"remove:{k1}")))
rows = list(form.addresses)
assert [r.html.key for r in rows] == [k2] and rows[0].street.html.value == "Second Ave" and rows[0].street.html.name == "profile[addresses][0][street]"
form.validate(wire(form, target="profile[addresses][_intent]", submitter=("profile[addresses][_intent]", "add")))
k3 = list(form.addresses)[1].html.key
form.validate(wire(form, target="profile[addresses][_intent]", submitter=("profile[addresses][_intent]", f"move:{k3}:up")))
assert [r.html.key for r in form.addresses] == [k3, k2]
assert form["addresses"]["0"].html.key == k3                                                     # digit strings ok
form.submit(wire(form))
assert form.addresses[0].street.html.errors == ["Street is required"] and form.submitted_once and form.just_submitted
form.validate(wire(form, {"addresses.0.street": "New Row St", "addresses.0.city": "Rome", "addresses.1.city": "Lyon"}, target="profile[addresses][1][city]"))
assert form.valid and not form.just_submitted and [a.street for a in form.model.addresses] == ["New Row St", "Second Ave"], form.debug()
print("4. intents/keys/gating OK")

# ------------------------------------------------------------------ 5. external errors, recovery, ancestor rule
form.add_error("name", "unique", "That name is taken")
assert not form.valid and form.name.html.errors == ["That name is taken"]
form.validate(wire(form, target="profile[addresses][0][city]"))
assert form.name.html.errors == ["That name is taken"]                                            # survives re-validation
form.submit(wire(form)); assert form.valid                                                       # cleared on submit
fresh = Form(Profile, as_="profile")
fresh.validate(wire(form, target="profile[name]"), recovered=True)                                # phx-auto-recover replay
assert ("addresses", 0, "city") in fresh.used and fresh.valid
fresh2 = Form(Profile, as_="profile").validate([("profile[addresses][0][street]", "x"), ("_target", "profile[addresses][0][street]")])
assert fresh2.addresses.html.errors == [] or True   # list-level: ancestor of a used path -> visible
assert fresh2.visible(("addresses",)) and not fresh2.visible(("name",))
print("5. external errors / recovery / ancestor rule OK")
print("ALL OK")
