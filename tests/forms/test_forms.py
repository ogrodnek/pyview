from datetime import date
from typing import Annotated, Literal, Optional, Union

import pytest
from pydantic import AliasChoices, BaseModel, Field, model_validator

from pyview.forms import DEFAULT_MESSAGES, Changeset, humanize, set_messages, ui
from pyview.forms.form import FormError
from pyview.forms.params import decode, decode_target
from pyview.forms.paths import normalize
from pyview.forms.render import errors as render_errors

# ---------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------


class Address(BaseModel):
    street: str = Field(min_length=1)
    city: str = Field(min_length=1)
    zip: str = Field(pattern=r"^\d{5}$")


class Email(BaseModel):
    kind: Literal["email"] = "email"
    address: str = Field(pattern=r"^[^@]+@[^@]+$")


class Phone(BaseModel):
    kind: Literal["phone"] = "phone"
    number: str = Field(min_length=7)


Contact = Annotated[Union[Email, Phone], Field(discriminator="kind")]


class Pet(BaseModel):
    name: str = Field(min_length=2)
    age: int = Field(ge=0, le=40)


class Owner(BaseModel):
    name: str = Field(min_length=3)
    joined: Optional[date] = None
    address: Address
    contact: Contact
    pets: list[Pet] = Field(default_factory=list)


class Signup(BaseModel):
    email: Annotated[str, ui(widget="email")]
    password: str = Field(min_length=8)
    confirm: str

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.confirm:
            raise ValueError("passwords do not match")
        return self


def payload(params: dict, target: Optional[str] = None) -> dict:
    out = dict(params)
    if target is not None:
        out["_target"] = decode_target(target)
    return out


# ---------------------------------------------------------------------------
# param decoding
# ---------------------------------------------------------------------------


class TestDecode:
    @pytest.mark.parametrize(
        "query,expected",
        [
            ("name=Fern", {"name": "Fern"}),
            ("owner[name]=Fern", {"owner": {"name": "Fern"}}),
            ("owner[address][city]=PDX", {"owner": {"address": {"city": "PDX"}}}),
            ("t[]=a&t[]=b", {"t": ["a", "b"]}),
            ("owner[name]=", {"owner": {"name": ""}}),
            ("owner%5Bname%5D=Ms+Fern", {"owner": {"name": "Ms Fern"}}),
            ("weird[=1", {"weird[": "1"}),
        ],
    )
    def test_shapes(self, query, expected):
        assert decode(query) == expected

    def test_indexed_rows_are_maps_not_lists(self):
        # deliberate: deleting row 1 of 0/1/2 must not renumber the survivors
        assert decode("o[pets][0][name]=Rex&o[pets][1][name]=Ace") == {
            "o": {"pets": {"0": {"name": "Rex"}, "1": {"name": "Ace"}}}
        }

    def test_last_value_wins(self):
        # this is what makes the hidden-input-before-checkbox trick work
        assert decode("terms=false&terms=true") == {"terms": "true"}

    def test_unchecked_checkbox_sends_nothing_at_all(self):
        assert "terms" not in decode("name=x")

    @pytest.mark.parametrize(
        "target,expected",
        [
            ("name", ["name"]),
            ("owner[email]", ["owner", "email"]),
            ("owner[pets][0][name]", ["owner", "pets", "0", "name"]),
            ("owner[tags][]", ["owner", "tags"]),
        ],
    )
    def test_target_paths(self, target, expected):
        assert decode_target(target) == expected

    def test_normalize_orders_rows_numerically(self):
        assert normalize({"pets": {"10": "j", "2": "b", "1": "a"}}) == {"pets": ["a", "b", "j"]}


# ---------------------------------------------------------------------------
# when errors are allowed to show
# ---------------------------------------------------------------------------


class TestErrorVisibility:
    def test_blank_form_is_silent(self):
        cs = Changeset(Owner)
        assert not cs.valid
        assert cs.form.name.errors == []
        assert cs.form.address.city.errors == []

    def test_only_the_touched_field_complains(self):
        cs = Changeset(Owner)
        cs.validate(payload({"owner": {"name": "Fe"}}, target="owner[name]"))

        assert cs.form.name.errors, "touched and invalid -> show"
        assert cs.form.address.city.errors == [], "untouched -> stay quiet"

    def test_submit_reveals_everything(self):
        cs = Changeset(Owner)
        cs.submit(payload({"owner": {"name": "Fe"}}))

        assert cs.form.name.errors
        assert cs.form.address.city.errors

    def test_missing_is_held_back_even_when_touched_elsewhere(self):
        cs = Changeset(Owner)
        cs.validate(payload({"owner": {"name": "Fern"}}, target="owner[name]"))
        assert cs.form.name.errors == []
        assert cs.form.address.zip.errors == []


# ---------------------------------------------------------------------------
# nesting, lists, unions
# ---------------------------------------------------------------------------


class TestNesting:
    def test_names_and_ids_follow_the_path(self):
        cs = Changeset(Owner)
        assert cs.form.name.name == "owner[name]"
        assert cs.form.address.city.name == "owner[address][city]"
        assert cs.form.address.city.id == "owner_address_city"

    def test_bad_input_round_trips_for_redisplay(self):
        cs = Changeset(Owner)
        params = {"owner": {"pets": {"0": {"name": "Rex", "age": "abc"}}}}
        cs.validate(payload(params, target="owner[pets][0][age]"))

        pet = next(iter(cs.form.pets))
        assert pet.age.value == "abc", "the model cannot hold this, so the params must"
        assert pet.age.errors, "and the error lands on the row's field"

    def test_list_rows_are_addressable(self):
        cs = Changeset(Owner)
        params = {
            "owner": {"pets": {"0": {"name": "Rex", "age": "3"}, "1": {"name": "A", "age": "2"}}}
        }
        cs.submit(payload(params))

        rows = list(cs.form.pets)
        assert [r.name.value for r in rows] == ["Rex", "A"]
        assert rows[1].name.name == "owner[pets][1][name]"
        assert rows[1].name.errors and not rows[0].name.errors

    def test_discriminated_union_errors_land_on_the_visible_input(self):
        cs = Changeset(Owner)
        cs.submit(payload({"owner": {"contact": {"kind": "phone", "number": "12"}}}))

        # pydantic reports ("contact", "phone", "number"); the input is
        # owner[contact][number], so the variant tag has to be dropped
        assert ("contact", "number") in cs.all_errors()

    def test_untagged_union_fails_with_a_useful_message(self):
        class Bad(BaseModel):
            contact: Union[Email, Phone]

        with pytest.raises(TypeError, match="discriminated union"):
            Changeset(Bad)


class TestDynamicRows:
    def test_add_and_drop_without_javascript(self):
        cs = Changeset(Owner)
        cs.validate(payload({"owner": {"pets": {"0": {"name": "Rex", "age": "3"}}}}))

        cs.add_row("pets")
        assert len(cs.form.pets) == 2

        cs.drop_row("pets", 0)
        rows = list(cs.form.pets)
        assert len(rows) == 1
        assert rows[0].name.name == "owner[pets][1][name]", "survivors keep their index"


# ---------------------------------------------------------------------------
# submit
# ---------------------------------------------------------------------------


class TestSubmit:
    def test_valid_submit_returns_the_typed_model(self):
        cs = Changeset(Owner)
        result = cs.submit(
            payload(
                {
                    "owner": {
                        "name": "Fern Gully",
                        "joined": "2024-03-01",
                        "address": {"street": "1 Main", "city": "PDX", "zip": "97214"},
                        "contact": {"kind": "email", "address": "fern@example.com"},
                        "pets": {"0": {"name": "Rex", "age": "7"}},
                    }
                }
            )
        )

        assert result
        assert isinstance(result.value, Owner)
        assert result.value.joined == date(2024, 3, 1)
        assert result.value.pets[0].age == 7
        assert isinstance(result.value.contact, Email)

    def test_invalid_submit_returns_no_value(self):
        cs = Changeset(Owner)
        result = cs.submit(payload({"owner": {"name": "no"}}))
        assert not result
        assert result.value is None

    def test_form_level_errors_live_at_the_root(self):
        cs = Changeset(Signup)
        cs.submit(
            payload({"signup": {"email": "a@b.co", "password": "longenough", "confirm": "other"}})
        )
        assert any("passwords do not match" in e.msg for e in cs.errors)

    def test_editing_an_existing_record_prefills(self):
        existing = Owner(
            name="Fern Gully",
            address=Address(street="1 Main", city="PDX", zip="97214"),
            contact=Email(address="fern@example.com"),
            pets=[Pet(name="Rex", age=7)],
        )
        cs = Changeset(Owner, data=existing)

        assert cs.form.name.value == "Fern Gully"
        assert cs.form.address.city.value == "PDX"
        assert list(cs.form.pets)[0].name.value == "Rex"
        assert cs.valid


# ---------------------------------------------------------------------------
# inference
# ---------------------------------------------------------------------------


class TestInference:
    def test_widgets_and_attrs_come_from_the_model(self):
        cs = Changeset(Owner)
        assert cs.form.name.widget == "text"
        assert cs.form.name.attrs["minlength"] == 3
        assert cs.form.name.required

        pet = Changeset(Pet)
        assert pet.form.age.widget == "number"
        assert pet.form.age.attrs["min"] == 0 and pet.form.age.attrs["max"] == 40

    def test_ui_hint_overrides_inference(self):
        cs = Changeset(Signup)
        assert cs.form.email.widget == "email"

    def test_optional_is_not_required(self):
        cs = Changeset(Owner)
        assert cs.form.joined.widget == "date"
        assert not cs.form.joined.required

    def test_unknown_field_says_what_is_available(self):
        cs = Changeset(Owner)
        with pytest.raises(AttributeError, match="Available:"):
            _ = cs.form.nmae


class TestTrustBoundary:
    def test_unpermitted_fields_keep_their_trusted_value(self):
        class Account(BaseModel):
            email: str
            role: str = "user"

        existing = Account(email="a@b.co", role="admin")
        cs = Changeset(Account, data=existing, fields={"email"})

        # a crafted payload tries to demote the account
        result = cs.submit({"account": {"email": "a@b.co", "role": "user"}})

        assert result.value is not None
        assert result.value.role == "admin", "role was not permitted, so params cannot set it"

    def test_permitted_fields_still_come_from_the_browser(self):
        class Account(BaseModel):
            email: str
            role: str = "user"

        cs = Changeset(Account, data=Account(email="a@b.co"), fields={"email"})
        result = cs.submit({"account": {"email": "new@b.co"}})
        assert result.value is not None and result.value.email == "new@b.co"

    def test_absent_key_clears_rather_than_persists(self):
        # the client serializes the WHOLE form every change, so a missing key
        # means "unchecked", not "unchanged"
        class Prefs(BaseModel):
            subscribe: bool = False

        cs = Changeset(Prefs)
        cs.validate({"prefs": {"subscribe": "true"}, "_target": ["prefs", "subscribe"]})
        assert cs.value is not None and cs.value.subscribe is True

        cs.validate({"prefs": {}, "_target": ["prefs", "subscribe"]})
        assert cs.value is not None and cs.value.subscribe is False


class TestErrorsKeepTheirData:
    def test_error_carries_type_and_ctx_for_i18n(self):
        cs = Changeset(Pet)
        cs.submit({"pet": {"name": "x", "age": "3"}})

        err = cs.form.name.errors[0]
        assert err.type == "string_too_short"
        assert err.ctx.get("min_length") == 2
        assert str(err) == err.msg
        assert err == err.msg, "compares equal to its message, so templates stay simple"


class TestMessages:
    def test_messages_are_written_for_people_not_programmers(self):
        cs = Changeset(Pet)
        cs.submit({"pet": {"name": "A", "age": "99"}})

        assert "String should have at least" in cs.form.name.errors[0].msg
        assert "Name must be at least 2 characters." in str(render_errors(cs.form.name))
        assert "Age must be 40 or less." in str(render_errors(cs.form.age))

    def test_catalog_is_replaceable_for_i18n(self):
        cs = Changeset(Pet)
        cs.submit({"pet": {"name": "A", "age": "1"}})
        err = cs.form.name.errors[0]

        set_messages({"string_too_short": "{label} : au moins {min_length} caracteres."})
        try:
            assert humanize(err, "Nom") == "Nom : au moins 2 caracteres."
        finally:
            set_messages(DEFAULT_MESSAGES)

    def test_unknown_error_types_fall_back_to_pydantics_message(self):
        err = FormError(msg="something specific went wrong", type="not_in_catalog")
        assert humanize(err, "Field") == "something specific went wrong"


class TestStableRowKeys:
    """Rows keep their rendered index; errors have to follow them there."""

    def test_errors_follow_the_row_key_not_the_list_position(self):
        cs = Changeset(Owner)
        for name in ("Rex", "x", "Ace"):
            cs.add_row("pets", {"name": name, "age": "3"})
        cs.drop_row("pets", "0")
        cs.reveal()

        # rows are keyed 1 and 2 now; pydantic validates a compacted list and
        # reports index 0, which is row 1 on the wire
        assert list(cs.params["pets"]) == ["1", "2"]
        assert ("pets", "1", "name") in cs.all_errors()

        rows = dict(cs.form.pets.rows)
        assert rows["1"].name.errors, "the bad row shows its error"
        assert not rows["2"].name.errors, "and the good row does not"

    def test_dropping_the_middle_row_keeps_the_rest_addressable(self):
        cs = Changeset(Owner)
        for name in ("Rex", "Ace", "y"):
            cs.add_row("pets", {"name": name, "age": "3"})
        cs.drop_row("pets", "1")
        cs.reveal()

        rows = dict(cs.form.pets.rows)
        assert list(rows) == ["0", "2"]
        assert rows["2"].name.name == "owner[pets][2][name]"
        assert rows["2"].name.errors and not rows["0"].name.errors


class TestBlankDiscriminator:
    def test_an_unchosen_variant_does_not_shout_on_first_change(self):
        cs = Changeset(Owner)
        cs.validate({"owner": {"name": "Fern"}, "_target": ["owner", "name"]})

        # "Unable to extract tag using discriminator" means "you have not picked
        # yet", which is not something to turn the form red over
        assert cs.form.contact.kind.errors == []
        assert ("contact",) in cs.all_errors()


class TestAliases:
    def test_an_aliased_field_agrees_on_one_wire_name(self):
        class Contact(BaseModel):
            email_address: str = Field(alias="email", min_length=5)

        cs = Changeset(Contact)
        field = cs.form.email_address

        # pydantic reports errors under the alias, so the input has to use it too
        assert field.name == "contact[email]"
        cs.submit({"contact": {"email": "a"}})
        assert field.errors, "otherwise the error is filed under a name nothing renders"

        cs.submit({"contact": {"email": "someone@example.com"}})
        assert cs.value is not None and cs.value.email_address == "someone@example.com"

    def test_multi_source_aliases_are_rejected_with_a_reason(self):
        class Weird(BaseModel):
            token: str = Field(validation_alias=AliasChoices("token", "api_key"))

        with pytest.raises(TypeError, match="one input per field"):
            Changeset(Weird)

    def test_row_operations_accept_either_name(self):
        class Item(BaseModel):
            label: str = "x"

        class Cart(BaseModel):
            line_items: list[Item] = Field(default_factory=list, alias="lines")

        cs = Changeset(Cart)
        cs.add_row("line_items")  # the Python attribute
        cs.add_row("lines")  # the wire name
        assert len(cs.form.line_items) == 2
        assert list(cs.form.line_items)[0].label.name == "cart[lines][0][label]"

        cs.drop_row("line_items", 0)
        assert len(cs.form.line_items) == 1


class TestDecodeLimits:
    def test_dunder_segments_are_refused(self):
        with pytest.raises(ValueError, match="dunder"):
            decode("owner[__class__][x]=1")

    def test_absurd_nesting_is_refused(self):
        key = "a" + "[b]" * 40
        with pytest.raises(ValueError, match="deeper than"):
            decode(f"{key}=1")

    def test_ordinary_nesting_is_fine(self):
        assert decode("a[b][c][d]=1") == {"a": {"b": {"c": {"d": "1"}}}}


class TestLifecycleLatch:
    def test_a_rejected_submit_stays_rejected(self):
        cs = Changeset(Owner)
        cs.submit({"owner": {"name": "x"}})
        assert cs.form.address.city.errors

        # without a sticky latch, the next keystroke sets action back to
        # "validate" and quietly un-reveals every untouched error
        cs.validate({"owner": {"name": "xy"}, "_target": ["owner", "name"]})
        assert cs.form.address.city.errors, "the form must not forget it was rejected"
        assert cs.submitted


class TestRowIdentity:
    def test_a_dropped_index_is_never_handed_out_again(self):
        cs = Changeset(Owner)
        for _ in range(3):
            cs.add_row("pets")
        cs.drop_row("pets", "2")
        cs.add_row("pets")

        # reusing index 2 would make the new row inherit the dropped row's DOM
        # state (focus, selection, aria wiring) under morphdom
        assert list(cs.params["pets"]) == ["0", "1", "3"]


class TestErrorRecordHygiene:
    def test_validator_messages_lose_the_framework_prefix(self):
        class Reg(BaseModel):
            a: str = "x"

            @model_validator(mode="after")
            def check(self):
                raise ValueError("they must match")

        cs = Changeset(Reg)
        cs.submit({"reg": {"a": "y"}})
        assert cs.errors[0].msg == "they must match", "not 'Value error, they must match'"

    def test_ctx_stays_serializable(self):
        class Reg(BaseModel):
            a: str = "x"

            @model_validator(mode="after")
            def check(self):
                raise ValueError("nope")

        cs = Changeset(Reg)
        cs.submit({"reg": {"a": "y"}})
        # pydantic puts the live exception in ctx; keeping it would make the
        # error unserializable and pin a traceback in the socket's state
        assert all(
            isinstance(v, (str, int, float, bool, type(None))) for v in cs.errors[0].ctx.values()
        )


class TestConstraintAttrs:
    def test_exclusive_bounds_narrow_on_integers(self):
        class Order(BaseModel):
            qty: int = Field(gt=0, lt=10)

        attrs = Changeset(Order).form.qty.attrs
        # HTML min/max are inclusive; leaving gt=0 as min=0 lets the browser
        # accept a value the server rejects
        assert attrs["min"] == 1 and attrs["max"] == 9

    def test_exclusive_bounds_are_left_alone_on_floats(self):
        class Order(BaseModel):
            ratio: float = Field(gt=0, lt=1)

        attrs = Changeset(Order).form.ratio.attrs
        assert attrs["min"] == 0 and attrs["max"] == 1
