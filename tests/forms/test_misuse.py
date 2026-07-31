"""What happens when you hold it wrong.

The type: ignore comments are the point, not an oversight - pyright already
rejects most of these, and the runtime message is for everyone it doesn't.

A corpus, not a checklist: every entry is a way the prototype used to fail
silently or with an internal error, and the assertion is that the message names
the mistake and the fix. Borrowed from Elm's error-message catalog and Phoenix's
compile-time verification tests - it turns "good error messages" from an
aspiration into something CI enforces.
"""

from dataclasses import dataclass

import pytest
from pydantic import BaseModel, Field

from pyview.forms import Changeset
from pyview.forms.errors import FormUsageError


class Signup(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=8)


class Pet(BaseModel):
    name: str = "x"


class Owner(BaseModel):
    pets: list[Pet] = Field(default_factory=list)


@dataclass
class NotAModel:
    a: str


def test_a_typo_in_the_whitelist_is_not_a_silently_frozen_field():
    # previously: the field simply became uneditable, forever, with no signal
    with pytest.raises(FormUsageError, match="similar name: `email`"):
        Changeset(Signup, fields=["emial"])


def test_a_typo_in_add_error_is_not_an_unrenderable_error():
    # previously: stored under a path nothing renders, so the error vanished
    with pytest.raises(FormUsageError, match="similar name: `email`"):
        Changeset(Signup).add_error("emial", "already taken")


def test_row_operations_on_a_scalar_say_so():
    # previously: silently wrote {"0": {}} over the field's value
    with pytest.raises(FormUsageError, match="is not a list"):
        Changeset(Signup).add_row("email")


def test_row_operations_on_an_unknown_field_say_so():
    with pytest.raises(FormUsageError, match="has no field"):
        Changeset(Owner).add_row("pet")


def test_an_unnamespaced_payload_is_not_a_permanent_no_op():
    # previously: unwrap() found nothing, params reset to the initial data on
    # every keystroke, and validation appeared to do nothing at all
    with pytest.raises(FormUsageError, match="named `signup`"):
        Changeset(Signup).validate({"email": "a@b.co"})


def test_passing_an_instance_suggests_the_data_argument():
    with pytest.raises(FormUsageError, match="data=that_instance"):
        Changeset(Signup(email="a@b.co", password="longenough"))  # type: ignore[arg-type]


def test_a_non_pydantic_class_says_what_is_needed():
    with pytest.raises(FormUsageError, match="BaseModel subclass"):
        Changeset(NotAModel)  # type: ignore[arg-type]


def test_a_dataclass_gets_a_specific_hint():
    with pytest.raises(FormUsageError, match="pydantic.dataclasses"):
        Changeset(NotAModel)  # type: ignore[arg-type]


def test_an_empty_payload_is_left_alone():
    # a form with nothing in it is not a wiring mistake; only a payload that
    # plainly belongs to something else is
    cs = Changeset(Signup)
    cs.validate({"_target": ["signup", "email"]})
    assert cs.form.email.value == ""


def test_a_named_form_accepts_its_own_namespace():
    cs = Changeset(Signup, name="user")
    cs.validate({"user": {"email": "a@b.co"}, "_target": ["user", "email"]})
    assert cs.form.email.value == "a@b.co"
