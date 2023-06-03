from __future__ import annotations
from pyview import LiveView, LiveViewSocket
from typing import TypedDict, Optional
from pydantic import BaseModel, validator
from pydantic.types import constr
from pyview.changesets import change_set, ChangeSet
from pyview.vendor.ibis import filters
from markupsafe import Markup


@filters.register
def input_tag(changeset: ChangeSet, field_name: str, options: Optional[dict[str, str]] = None) -> Markup:
    type = (options or {}).get("type", "text")
    return Markup(
        """<input type="{type}" id="{field_name}" name="{field_name}" phx-debounce="2000" value="{value}" />"""
    ).format(type=type, field_name=field_name, value=changeset.changes.get(field_name, ""))


@filters.register
def error_tag(changeset: ChangeSet, field_name: str) -> Markup:
    return Markup(
        """<span style="margin-top: -8px; color: red;" phx-feedback-for={field_name}><small>{error}</small></span>"""
    ).format(field_name=field_name, error=changeset.errors.get(field_name, ""))


checked_str = constr(min_length=3, max_length=20)


class Registration(BaseModel):
    name: checked_str
    email: checked_str
    password: checked_str
    password_confirmation: checked_str

    @validator("password_confirmation")
    def passwords_match(cls, v, values, **kwargs):
        if "password" in values and v != values["password"]:
            raise ValueError("passwords do not match")
        return v


class RegistrationContext(TypedDict):
    changeset: ChangeSet[Registration]


class RegistrationLiveView(LiveView):
    async def mount(self, socket: LiveViewSocket, _session):
        socket.context = RegistrationContext(changeset=change_set(Registration))

    async def handle_event(self, event, payload, socket: LiveViewSocket[RegistrationContext]):
        print(event, payload)
        if event == "validate":
            socket.context["changeset"].apply(payload)
