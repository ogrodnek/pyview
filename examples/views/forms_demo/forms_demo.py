"""Nested, dynamic and conditional forms from one pydantic model.

Everything on screen - labels, input types, min/max, the select options, the
error messages, the accessibility wiring - comes from the model below. The view
handles two events and touches no HTML.
"""

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator

from pyview import LiveView, LiveViewSocket
from pyview.forms import TAILWIND, Changeset, set_theme, ui

set_theme(TAILWIND)


class Species(StrEnum):
    cat = "cat"
    dog = "dog"
    ferret = "ferret"


class Address(BaseModel):
    street: str = Field(min_length=1, max_length=80)
    city: str = Field(min_length=1, max_length=60)
    zip: Annotated[str, ui(label="ZIP", placeholder="97214")] = Field(pattern=r"^\d{5}$")


class EmailContact(BaseModel):
    """One arm of the conditional sub-form."""

    kind: Literal["email"] = "email"
    address: Annotated[str, ui(widget="email", label="Email address")] = Field(
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    )
    newsletter: Annotated[bool, ui(label="Send me the newsletter")] = False


class PhoneContact(BaseModel):
    kind: Literal["phone"] = "phone"
    number: Annotated[str, ui(label="Phone number", placeholder="555-0100")] = Field(min_length=7)
    sms_ok: Annotated[bool, ui(label="Texting is fine")] = False


class Pet(BaseModel):
    name: str = Field(min_length=2, max_length=30)
    species: Species = Species.cat
    age: Annotated[int, ui(help="In years.")] = Field(ge=0, le=40)


class Owner(BaseModel):
    """The only thing this demo actually declares."""

    name: Annotated[str, ui(autocomplete="name")] = Field(min_length=3, max_length=60)
    joined: Optional[date] = None
    address: Address
    # no default: the initial arm is chosen by the trusted `data` handed to the
    # changeset, which is also what a real "edit this record" form would supply
    contact: Annotated[Union[EmailContact, PhoneContact], Field(discriminator="kind")]
    pets: list[Pet] = Field(default_factory=list)

    @model_validator(mode="after")
    def needs_a_pet(self):
        if not self.pets:
            raise ValueError("Add at least one pet.")
        return self


def _new_changeset() -> Changeset[Owner]:
    # `data` is the trusted starting point - here just enough to pick the
    # initial arm of the conditional contact sub-form.
    return Changeset(Owner, data={"contact": {"kind": "email"}})


@dataclass
class FormsDemoContext:
    owner: Changeset[Owner] = field(default_factory=_new_changeset)
    saved: Optional[Owner] = None


class FormsDemoLiveView(LiveView[FormsDemoContext]):
    """
    Nested Forms

    Deeply nested, dynamic and conditional forms from a single pydantic model
    """

    async def mount(self, socket: LiveViewSocket[FormsDemoContext], session):
        socket.context = FormsDemoContext()

    async def handle_event(self, event, payload, socket: LiveViewSocket[FormsDemoContext]):
        owner = socket.context.owner

        if event == "validate":
            owner.validate(payload)

        elif event == "save":
            if result := owner.submit(payload):
                socket.context.saved = result.value
                socket.context.owner = _new_changeset()

        elif event == "reset":
            socket.context = FormsDemoContext()
