"""Forms for pyview - EXPERIMENTAL design spike.

Status: a prototype accompanying ``docs/design/forms.md``. It is deliberately not
exported from ``pyview`` yet and the API is expected to change. It exists so the
design can be run and felt rather than only read.

The shape of it::

    class Signup(BaseModel):
        email: str
        password: str = Field(min_length=12)

    @dataclass
    class Context:
        signup: Changeset[Signup] = field(default_factory=lambda: Changeset(Signup))

    class SignupView(LiveView[Context]):
        async def mount(self, socket, session):
            socket.context = Context()

        async def handle_event(self, event, payload, socket):
            if event == "validate":
                socket.context.signup.validate(payload)
            elif event == "save":
                if result := socket.context.signup.submit(payload):
                    create_user(result.value)     # a real, typed Signup

and in the template::

    <form phx-change="validate" phx-submit="save">
      {{ signup.form.email | input }}
      {{ signup.form.password | input }}
    </form>
"""

from .form import (
    Changeset,
    FieldList,
    FormField,
    FormView,
    Result,
    changeset,
    errors_of,
    name_of,
    path_of,
)
from .messages import DEFAULT_MESSAGES, humanize, set_messages
from .params import decode, decode_target, encode_name, normalize_payload
from .paths import Path
from .schema import FieldSpec, field_specs, ui

__all__ = [
    "Changeset",
    "changeset",
    "FormView",
    "FormField",
    "errors_of",
    "name_of",
    "path_of",
    "FieldList",
    "Result",
    "Path",
    "FieldSpec",
    "field_specs",
    "ui",
    "humanize",
    "set_messages",
    "DEFAULT_MESSAGES",
    "decode",
    "decode_target",
    "encode_name",
    "normalize_payload",
]
