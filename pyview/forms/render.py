"""Rendering: the escape-hatch ladder.

The thing that kills form libraries is not the first five minutes, it is month
three, when the design system wants markup the library does not emit. Every rung
of this ladder is a place you can stop, and stepping down one rung never costs
you the rungs below it:

    {{ signup | render_form }}                     everything, zero decisions
    {{ signup.form.email | input }}                one field, wrapper included
    {{ signup.form.email | input(class="...") }}   same, with overrides
    {{ signup.form.email | control }}              bare <input>, you write the wrapper
    <input name="{{ signup.form.email.name }}"     nothing of ours at all,
           value="{{ signup.form.email.value }}">  still correctly bound

The library owns *correctness* - name generation, value round-tripping, error
placement, and the accessibility wiring that is tedious to get right by hand.
It does not own *appearance*: there is not a single style class in this module.
Those live in :class:`Theme`, which you replace.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Optional, Union

from markupsafe import Markup, escape

from pyview.vendor.ibis import filters

from .form import Changeset, FieldList, FormField, FormView, errors_of, name_of
from .messages import humanize

__all__ = ["Theme", "DEFAULT_THEME", "set_theme", "control", "input", "errors", "render_form"]


@dataclass(frozen=True)
class Theme:
    """Every class name the renderer will ever emit, in one replaceable object.

    Hardcoding classes is the trap that crispy-forms, simple_form and rjsf all
    had to grow a plugin system to escape. Start with the seam.
    """

    wrapper: str = ""
    label: str = ""
    control: str = ""
    control_invalid: str = ""
    error: str = ""
    help: str = ""
    checkbox_wrapper: str = ""
    checkbox_label: str = ""
    checkbox_control: str = ""
    fieldset: str = ""
    legend: str = ""

    def for_control(self, invalid: bool) -> str:
        return f"{self.control} {self.control_invalid}".strip() if invalid else self.control


DEFAULT_THEME = Theme()
_theme = DEFAULT_THEME


def set_theme(theme: Theme) -> None:
    """Install the theme used when a call site does not pass one."""
    global _theme
    _theme = theme


def _attrs(pairs: dict[str, Any]) -> str:
    out: list[str] = []
    for key, value in pairs.items():
        if value is None or value is False or value == "":
            continue
        name = key.replace("_", "-") if key.startswith("phx_") or key.startswith("aria_") else key
        if value is True:
            out.append(escape(name))
        else:
            out.append(f'{escape(name)}="{escape(str(value))}"')
    return (" " + " ".join(out)) if out else ""


def _describedby(f: FormField) -> Optional[str]:
    """Wire the control to its error and help text, which is what a screen
    reader needs to read them out when the control takes focus."""
    ids = []
    if f.errors:
        ids.append(f"{f.id}_error")
    if f.help:
        ids.append(f"{f.id}_help")
    return " ".join(ids) or None


def control(
    f: FormField, opts: Optional[dict[str, Any]] = None, theme: Optional[Theme] = None
) -> Markup:
    """The bare control - ``<input>``, ``<select>`` or ``<textarea>`` - and nothing else.

    Type, constraints and choices come from the model; ``opts`` wins over all of
    them. ``opts`` is a dict rather than keyword arguments because ibis filters
    only accept positional literals: ``{{ f | control({"type": "password"}) }}``.
    """
    t = theme or _theme
    overrides = dict(opts or {})
    # "type" and "widget" mean the same thing at a call site: {"type": "password"}
    # is what anyone writes, and it has to actually win over the inferred type.
    explicit_widget = overrides.pop("widget", None)
    explicit_type = overrides.pop("type", None)
    widget = explicit_widget or explicit_type or f.widget
    css = overrides.pop("class", None)

    attrs: dict[str, Any] = {
        "id": f.id,
        "name": f.name,
        "class": css if css is not None else t.for_control(f.invalid),
        # aria-invalid is the machine-readable half of "this field is wrong";
        # the red border is only the half sighted users get.
        "aria-invalid": "true" if f.invalid else None,
        "aria-describedby": _describedby(f),
        **f.attrs,
    }
    attrs.update({k.rstrip("_"): v for k, v in overrides.items()})

    if widget == "textarea":
        rows = attrs.pop("rows", None)
        return Markup("<textarea{attrs}>{value}</textarea>").format(
            attrs=Markup(_attrs({**attrs, "rows": rows})), value=f.value
        )

    if widget == "select":
        options = [Markup('<option value=""></option>')] if not f.required else []
        for value, label in f.choices:
            options.append(
                Markup('<option value="{v}"{sel}>{l}</option>').format(
                    v=value, sel=Markup(" selected") if str(f.value) == str(value) else "", l=label
                )
            )
        return Markup("<select{attrs}>{opts}</select>").format(
            attrs=Markup(_attrs(attrs)), opts=Markup("").join(options)
        )

    if widget == "checkbox":
        checked = str(f.value).lower() in ("true", "on", "1", "yes")
        # The hidden input is not optional. An unchecked box sends *nothing*, so
        # without a false value ahead of it there is no way to distinguish
        # "unchecked" from "not on this form", and the box can never be cleared.
        return Markup('<input type="hidden" name="{name}" value="false" /><input{attrs} />').format(
            name=f.name,
            attrs=Markup(
                _attrs({**attrs, "type": "checkbox", "value": "true", "checked": checked})
            ),
        )

    return Markup("<input{attrs} />").format(
        attrs=Markup(_attrs({**attrs, "type": widget, "value": f.value}))
    )


def errors(
    target: Union[FormField, FormView, FieldList, Changeset], theme: Optional[Theme] = None
) -> Markup:
    """The error block for anything addressable, wired for assistive tech."""
    t = theme or _theme
    found = errors_of(target)
    if not found:
        return Markup("")

    anchor = getattr(target, "id", None) or name_of(target)
    label = getattr(target, "label", "") or "This field"
    return Markup("").join(
        # role=alert so a screen reader announces an error that appears after a
        # server round trip, rather than leaving it silently on screen
        Markup('<p id="{id}" class="{cls}" role="alert">{msg}</p>').format(
            id=f"{anchor}_error", cls=t.error, msg=humanize(e, label)
        )
        for e in found
    )


def input(  # noqa: A001
    f: FormField, opts: Optional[dict[str, Any]] = None, theme: Optional[Theme] = None
) -> Markup:
    """Label, control, help text and errors - the whole field, wrapped."""
    t = theme or _theme
    overrides = dict(opts or {})
    label_text = overrides.pop("label", None) or f.label

    if f.spec.hidden:
        return Markup("<input{attrs} />").format(
            attrs=Markup(_attrs({"type": "hidden", "name": f.name, "value": f.value}))
        )

    if f.widget == "checkbox":
        # a checkbox reads as "[x] Send me the newsletter", not as a labelled
        # field, so it gets its own wrapper rather than the block label
        opts = {"class": t.checkbox_control, **overrides}
        body = Markup('<label class="{lcls}" for="{id}">{ctl}<span>{label}</span></label>').format(
            lcls=t.checkbox_label, id=f.id, ctl=control(f, opts, t), label=label_text
        )
    else:
        body = Markup('<label class="{lcls}" for="{id}">{label}</label>{ctl}').format(
            lcls=t.label, id=f.id, label=label_text, ctl=control(f, overrides, t)
        )

    help_html = (
        Markup('<p id="{id}_help" class="{cls}">{txt}</p>').format(id=f.id, cls=t.help, txt=f.help)
        if f.help
        else Markup("")
    )

    # phx-feedback-for lets the *client* hide errors for inputs the user has not
    # touched yet, which complements the server's own touched-tracking: the
    # server knows what changed, the browser knows what has focus.
    return Markup('<div class="{cls}" phx-feedback-for="{name}">{body}{help}{errs}</div>').format(
        cls=t.checkbox_wrapper if f.widget == "checkbox" else t.wrapper,
        name=f.name,
        body=body,
        help=help_html,
        errs=errors(f, t),
    )


def render_form(
    source: Union[Changeset, FormView],
    opts: Optional[dict[str, Any]] = None,
    theme: Optional[Theme] = None,
) -> Markup:
    """Fields in declaration order - the rung you start on, and the one below it.

    ``opts`` takes ``only`` or ``exclude``, which is the rung most people actually
    need: *my* markup for the two fields I care about, the library's for the rest::

        {{ signup | render_form({"exclude": ["password", "confirm"]}) }}
        {{ signup | render_form({"only": ["street", "city", "zip"]}) }}

    Without it the ladder jumps straight from "everything" to "one field at a
    time", and the moment one field needs custom markup you hand-write all twenty.
    """
    t = theme or _theme
    settings = opts or {}
    only = settings.get("only")
    exclude = settings.get("exclude")
    view = source.form if isinstance(source, Changeset) else source

    parts: list[Markup] = []
    if isinstance(source, Changeset) and source.errors:
        parts.append(errors(source, t))

    for bound in view:
        name = bound.spec.name if hasattr(bound, "spec") else ""
        if only and name not in only:
            continue
        if exclude and name in exclude:
            continue

        if isinstance(bound, FormField):
            parts.append(input(bound, None, t))
        elif isinstance(bound, FieldList):
            parts.append(_render_list(bound, t))
        else:
            parts.append(
                _render_group(bound, t, bound.spec.label if hasattr(bound, "spec") else "")
            )

    return Markup("").join(parts)


def _render_group(view: FormView, t: Theme, legend: str) -> Markup:
    return Markup(
        "<fieldset class={cls}><legend class={lcls}>{legend}</legend>{body}</fieldset>"
    ).format(cls=t.fieldset, lcls=t.legend, legend=legend, body=render_form(view, None, t))


def _render_list(fl: FieldList, t: Theme) -> Markup:
    rows = Markup("").join(
        Markup('<fieldset class="{cls}">{body}</fieldset>').format(
            cls=t.fieldset, body=render_form(row, None, t)
        )
        for row in fl
    )
    return Markup(
        "<fieldset class={cls}><legend class={lcls}>{legend}</legend>{rows}</fieldset>"
    ).format(cls=t.fieldset, lcls=t.legend, legend=fl.label, rows=rows)


# ---------------------------------------------------------------------------
# template integration
# ---------------------------------------------------------------------------


def register_filters() -> None:
    """Expose the ladder to ibis templates as filters.

    ``{{ signup.form.email | input }}`` and ``{{ signup | render_form }}``.
    """
    filters.register("input")(input)
    filters.register("control")(control)
    filters.register("errors")(errors)
    filters.register("render_form")(render_form)


def themed(base: Theme, **changes: str) -> Theme:
    """A tweaked copy of a theme, for one form that needs to differ."""
    return replace(base, **changes)


#: A Tailwind starting point. Not imported by default - it is an example of what
#: a theme looks like, not a decision the library makes for you.
TAILWIND = Theme(
    wrapper="mb-4",
    label="block text-sm font-medium text-gray-700 mb-1",
    control="w-full px-3 py-2 border rounded-md shadow-sm focus:outline-none focus:ring-1 border-gray-300 focus:border-blue-500 focus:ring-blue-500",
    control_invalid="border-red-400 focus:border-red-500 focus:ring-red-500",
    error="mt-1 text-sm text-red-600",
    help="mt-1 text-sm text-gray-500",
    checkbox_wrapper="mb-4",
    checkbox_label="flex items-center gap-2 text-sm font-medium text-gray-700",
    checkbox_control="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500",
    fieldset="border border-gray-200 rounded-md p-4 mb-4",
    legend="text-sm font-semibold text-gray-900 px-1",
)
