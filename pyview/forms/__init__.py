"""Forms for pyview - EXPERIMENTAL design spike.

Status: a prototype accompanying ``design/forms.md``. It is deliberately not
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

from .errors import FormUsageError
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
from .render import (
    TAILWIND,
    Theme,
    control,
    error_summary,
    errors,
    input,
    register_filters,
    render_form,
    set_theme,
)
from .schema import FieldSpec, field_specs, ui

# Template filters register themselves on import. A form library whose first two
# lines are setup has already spent its budget: importing it is the opt-in.
register_filters()

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
    "Theme",
    "TAILWIND",
    "set_theme",
    "input",
    "control",
    "errors",
    "render_form",
    "error_summary",
    "register_filters",
    "FormUsageError",
    "humanize",
    "set_messages",
    "DEFAULT_MESSAGES",
    "decode",
    "decode_target",
    "encode_name",
    "normalize_payload",
]
