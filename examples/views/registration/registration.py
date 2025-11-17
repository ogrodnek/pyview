from __future__ import annotations

from typing import Optional, TypedDict

from markupsafe import Markup
from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self

from pyview import LiveView, LiveViewSocket
from pyview.changesets import ChangeSet, change_set
from pyview.vendor.ibis import filters


@filters.register
def input_tag(
    changeset: ChangeSet, field_name: str, options: Optional[dict[str, str]] = None
) -> Markup:
    type = (options or {}).get("type", "text")
    error_class = (
        "border-red-300 focus:border-red-500 focus:ring-red-500"
        if changeset.errors.get(field_name)
        else "border-gray-300 focus:border-blue-500 focus:ring-blue-500"
    )
    return Markup(
        """<input type="{type}" id="{field_name}" name="{field_name}" phx-debounce="2000" value="{value}" class="w-full px-3 py-2 border rounded-md shadow-sm focus:outline-none focus:ring-1 transition-colors {error_class}" />"""
    ).format(
        type=type,
        field_name=field_name,
        value=changeset.changes.get(field_name, ""),
        error_class=error_class,
    )


@filters.register
def error_tag(changeset: ChangeSet, field_name: str) -> Markup:
    error = changeset.errors.get(field_name, "")
    if error:
        return Markup(
            """<div class="flex items-center mt-2" phx-feedback-for={field_name}>
                <svg class="w-4 h-4 text-red-500 mr-1" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
                </svg>
                <span class="text-sm text-red-600">{error}</span>
            </div>"""
        ).format(field_name=field_name, error=error)
    return Markup("")


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

    async def handle_event(self, event, payload, socket: LiveViewSocket[RegistrationContext]):
        print(event, payload)
        if event == "validate":
            socket.context["changeset"].apply(payload)
