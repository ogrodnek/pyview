from __future__ import annotations
from pyview import LiveView, LiveViewSocket
from typing import TypedDict, Optional
from typing_extensions import Self

from pydantic import BaseModel, Field, model_validator
from pyview.changesets import change_set, ChangeSet
from pyview.vendor.ibis import filters
from markupsafe import Markup


@filters.register
def input_tag(
    changeset: ChangeSet, field_name: str, options: Optional[dict[str, str]] = None
) -> Markup:
    type = (options or {}).get("type", "text")
    return Markup(
        """<input type="{type}" id="{field_name}" name="{field_name}" phx-debounce="2000" value="{value}" />"""
    ).format(
        type=type, field_name=field_name, value=changeset.changes.get(field_name, "")
    )


@filters.register
def error_tag(changeset: ChangeSet, field_name: str) -> Markup:
    return Markup(
        """<span style="margin-top: -8px; color: red;" phx-feedback-for={field_name}><small>{error}</small></span>"""
    ).format(field_name=field_name, error=changeset.errors.get(field_name, ""))


class Registration(BaseModel):
    name: str = Field(min_length=3, max_length=20)
    email: str = Field(min_length=3, max_length=20)
    password: str = Field(min_length=3, max_length=20)
    password_confirmation: str = Field(min_length=3, max_length=20)

    @model_validator(mode="after")
    def passwords_match(self) -> Self:
        pw1 = self.password
        pw2 = self.password_confirmation
        if pw1 is not None and pw2 is not None and pw1 != pw2:
            raise ValueError("passwords do not match")
        return self


class RegistrationContext(TypedDict):
    changeset: ChangeSet[Registration]


class RegistrationLiveView(LiveView):
    """
    Registration Form Validation

    Form validation using Pydantic
    """

    async def mount(self, socket: LiveViewSocket, session):
        socket.context = RegistrationContext(changeset=change_set(Registration))

    async def handle_event(
        self, event, payload, socket: LiveViewSocket[RegistrationContext]
    ):
        print(event, payload)
        if event == "validate":
            socket.context["changeset"].apply(payload)
