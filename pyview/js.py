"""
Phoenix LiveView JS Commands implementation for PyView.

This module provides a Pythonic API for Phoenix LiveView's client-side JS commands.
Commands can be chained together and are executed by the Phoenix.js client library.

Usage with t-strings:
    from pyview.js import js

    def template(self, assigns, meta):
        return t'''
        <button phx-click="{js.show('#modal')}">Open</button>
        <button phx-click="{js.hide('#modal').push('close')}">Close</button>
        '''

Usage with Ibis templates:
    <button phx-click='{{ js.show("#modal") }}'>Open</button>
    <button phx-click='{{ js.hide("#modal") | js.push("close") }}'>Close</button>

See: https://hexdocs.pm/phoenix_live_view/Phoenix.LiveView.JS.html
"""

import json
from dataclasses import dataclass
from typing import Any, Sequence

from pyview.template.context_processor import context_processor
from pyview.template.html import escape_html
from pyview.vendor.ibis import filters

# Type alias for transition specifications
# Can be a simple string "fade-in" or a 3-tuple ("fade-in", "opacity-0", "opacity-100")
# Each element in the tuple can be a string (space-separated) or a list of strings.
_TransitionElement = str | Sequence[str]
Transition = str | tuple[_TransitionElement, _TransitionElement, _TransitionElement] | list[str]


def _format_transition(transition: Transition) -> list[list[str]]:
    """
    Format a transition for the Phoenix wire format.

    Phoenix expects transitions as a 3-element array:
    [[transition_classes], [start_classes], [end_classes]]

    Args:
        transition: Either a string "fade-in" or tuple ("fade-in", "opacity-0", "opacity-100")

    Returns:
        Formatted transition array for Phoenix.js
    """
    if isinstance(transition, str):
        # Simple transition string - split on spaces for multiple classes
        return [transition.split(), [], []]
    elif isinstance(transition, (tuple, list)) and len(transition) == 3:
        # Full 3-tuple: (transition, start, end)
        return [
            transition[0].split() if isinstance(transition[0], str) else list(transition[0]),
            transition[1].split() if isinstance(transition[1], str) else list(transition[1]),
            transition[2].split() if isinstance(transition[2], str) else list(transition[2]),
        ]
    elif isinstance(transition, list):
        # List of class names - treat as transition classes with no start/end
        return [transition, [], []]
    else:
        raise ValueError(f"Transition must be a string or 3-tuple, got: {transition!r}")


@dataclass
class JsCommand:
    """A single JS command with its options."""

    cmd: str
    opts: dict[str, Any]


@dataclass
class JsCommands:
    """
    A chain of JS commands to be executed client-side.

    This class is immutable - each method returns a new JsCommands instance
    with the additional command appended. Commands are executed in order
    by the Phoenix.js client library.

    Example:
        commands = JsCommands([])
        commands = commands.show("#modal").push("opened")
        # or more commonly via the js singleton:
        js.show("#modal").push("opened")
    """

    commands: list[JsCommand]

    def add(self, cmd: JsCommand) -> "JsCommands":
        """Add a command and return a new JsCommands instance."""
        return JsCommands(self.commands + [cmd])

    # Visibility Commands

    def show(
        self,
        to: str | None = None,
        *,
        transition: Transition | None = None,
        time: int = 200,
        display: str | None = None,
        blocking: bool = True,
    ) -> "JsCommands":
        """
        Show element(s).

        Args:
            to: CSS selector for target element(s). Defaults to current element.
            transition: CSS transition classes. Either a string or 3-tuple
                       (transition, start_classes, end_classes).
            time: Transition duration in milliseconds (default: 200).
            display: CSS display value when shown (default: "block").
            blocking: Whether to block subsequent commands until complete.

        Example:
            js.show("#modal")
            js.show("#modal", transition="fade-in", time=300)
            js.show("#modal", transition=("fade-in", "opacity-0", "opacity-100"))
        """
        opts: dict[str, Any] = {}
        if to:
            opts["to"] = to
        if transition:
            opts["transition"] = _format_transition(transition)
            opts["time"] = time
        if display:
            opts["display"] = display
        if not blocking:
            opts["blocking"] = False
        return self.add(JsCommand("show", opts))

    def hide(
        self,
        to: str | None = None,
        *,
        transition: Transition | None = None,
        time: int = 200,
        blocking: bool = True,
    ) -> "JsCommands":
        """
        Hide element(s).

        Args:
            to: CSS selector for target element(s). Defaults to current element.
            transition: CSS transition classes for hiding animation.
            time: Transition duration in milliseconds (default: 200).
            blocking: Whether to block subsequent commands until complete.

        Example:
            js.hide("#modal")
            js.hide("#modal", transition="fade-out", time=300)
        """
        opts: dict[str, Any] = {}
        if to:
            opts["to"] = to
        if transition:
            opts["transition"] = _format_transition(transition)
            opts["time"] = time
        if not blocking:
            opts["blocking"] = False
        return self.add(JsCommand("hide", opts))

    def toggle(
        self,
        to: str | None = None,
        *,
        in_transition: Transition | None = None,
        out_transition: Transition | None = None,
        time: int = 200,
        display: str | None = None,
        blocking: bool = True,
    ) -> "JsCommands":
        """
        Toggle element visibility.

        Args:
            to: CSS selector for target element(s). Defaults to current element.
            in_transition: Transition classes for showing (the "in" transition).
            out_transition: Transition classes for hiding (the "out" transition).
            time: Transition duration in milliseconds (default: 200).
            display: CSS display value when shown.
            blocking: Whether to block subsequent commands until complete.

        Example:
            js.toggle("#menu")
            js.toggle("#menu", in_transition="fade-in", out_transition="fade-out")
        """
        opts: dict[str, Any] = {}
        if to:
            opts["to"] = to
        if in_transition:
            opts["ins"] = _format_transition(in_transition)
            opts["time"] = time
        if out_transition:
            opts["outs"] = _format_transition(out_transition)
            opts["time"] = time
        if display:
            opts["display"] = display
        if not blocking:
            opts["blocking"] = False
        return self.add(JsCommand("toggle", opts))

    # Class Commands

    def add_class(
        self,
        names: str | Sequence[str],
        *,
        to: str | None = None,
        transition: Transition | None = None,
        time: int = 200,
        blocking: bool = True,
    ) -> "JsCommands":
        """
        Add CSS class(es) to element(s).

        Args:
            names: Class name(s) to add. Can be a string or sequence of strings.
            to: CSS selector for target element(s). Defaults to current element.
            transition: Transition classes for the class change animation.
            time: Transition duration in milliseconds (default: 200).
            blocking: Whether to block subsequent commands until complete.

        Example:
            js.add_class("active", to="#tab-1")
            js.add_class(["highlight", "pulse"], to="#alert")
        """
        if isinstance(names, str):
            names = [names]
        else:
            names = list(names)

        opts: dict[str, Any] = {"names": names}
        if to:
            opts["to"] = to
        if transition:
            opts["transition"] = _format_transition(transition)
            opts["time"] = time
        if not blocking:
            opts["blocking"] = False
        return self.add(JsCommand("add_class", opts))

    def remove_class(
        self,
        names: str | Sequence[str],
        *,
        to: str | None = None,
        transition: Transition | None = None,
        time: int = 200,
        blocking: bool = True,
    ) -> "JsCommands":
        """
        Remove CSS class(es) from element(s).

        Args:
            names: Class name(s) to remove. Can be a string or sequence of strings.
            to: CSS selector for target element(s). Defaults to current element.
            transition: Transition classes for the class change animation.
            time: Transition duration in milliseconds (default: 200).
            blocking: Whether to block subsequent commands until complete.

        Example:
            js.remove_class("active", to="#tab-1")
            js.remove_class(["highlight", "pulse"], to="#alert")
        """
        if isinstance(names, str):
            names = [names]
        else:
            names = list(names)

        opts: dict[str, Any] = {"names": names}
        if to:
            opts["to"] = to
        if transition:
            opts["transition"] = _format_transition(transition)
            opts["time"] = time
        if not blocking:
            opts["blocking"] = False
        return self.add(JsCommand("remove_class", opts))

    def toggle_class(
        self,
        names: str | Sequence[str],
        *,
        to: str | None = None,
        transition: Transition | None = None,
        time: int = 200,
        blocking: bool = True,
    ) -> "JsCommands":
        """
        Toggle CSS class(es) on element(s).

        Args:
            names: Class name(s) to toggle. Can be a string or sequence of strings.
            to: CSS selector for target element(s). Defaults to current element.
            transition: Transition classes for the class change animation.
            time: Transition duration in milliseconds (default: 200).
            blocking: Whether to block subsequent commands until complete.

        Example:
            js.toggle_class("expanded", to="#sidebar")
        """
        if isinstance(names, str):
            names = [names]
        else:
            names = list(names)

        opts: dict[str, Any] = {"names": names}
        if to:
            opts["to"] = to
        if transition:
            opts["transition"] = _format_transition(transition)
            opts["time"] = time
        if not blocking:
            opts["blocking"] = False
        return self.add(JsCommand("toggle_class", opts))

    def transition(
        self,
        transition: Transition,
        *,
        to: str | None = None,
        time: int = 200,
        blocking: bool = True,
    ) -> "JsCommands":
        """
        Apply a CSS transition to element(s).

        Args:
            transition: CSS transition classes. Either a string or 3-tuple
                       (transition, start_classes, end_classes).
            to: CSS selector for target element(s). Defaults to current element.
            time: Transition duration in milliseconds (default: 200).
            blocking: Whether to block subsequent commands until complete.

        Example:
            js.transition("shake", to="#form")
            js.transition(("transition-opacity", "opacity-0", "opacity-100"), to="#el")
        """
        opts: dict[str, Any] = {
            "transition": _format_transition(transition),
            "time": time,
        }
        if to:
            opts["to"] = to
        if not blocking:
            opts["blocking"] = False
        return self.add(JsCommand("transition", opts))

    # Attribute Commands

    def set_attribute(
        self,
        attr: str | tuple[str, str],
        *,
        to: str | None = None,
    ) -> "JsCommands":
        """
        Set an attribute on element(s).

        Args:
            attr: Either a tuple (name, value) or just the attribute name
                  (value will be empty string).
            to: CSS selector for target element(s). Defaults to current element.

        Example:
            js.set_attribute(("disabled", "true"), to="#submit")
            js.set_attribute(("aria-expanded", "true"), to="#menu")
        """
        if isinstance(attr, str):
            attr_tuple = [attr, ""]
        else:
            attr_tuple = list(attr)

        opts: dict[str, Any] = {"attr": attr_tuple}
        if to:
            opts["to"] = to
        return self.add(JsCommand("set_attr", opts))

    def remove_attribute(
        self,
        attr: str,
        *,
        to: str | None = None,
    ) -> "JsCommands":
        """
        Remove an attribute from element(s).

        Args:
            attr: The attribute name to remove.
            to: CSS selector for target element(s). Defaults to current element.

        Example:
            js.remove_attribute("disabled", to="#submit")
        """
        opts: dict[str, Any] = {"attr": attr}
        if to:
            opts["to"] = to
        return self.add(JsCommand("remove_attr", opts))

    def toggle_attribute(
        self,
        attr: str | tuple[str, str] | tuple[str, str, str],
        *,
        to: str | None = None,
    ) -> "JsCommands":
        """
        Toggle an attribute on element(s).

        Args:
            attr: The attribute specification:
                  - string: Toggle presence of attribute
                  - (name, val): Toggle between having value and not having attribute
                  - (name, val1, val2): Toggle between val1 and val2
            to: CSS selector for target element(s). Defaults to current element.

        Example:
            js.toggle_attribute("disabled", to="#submit")
            js.toggle_attribute(("aria-expanded", "true", "false"), to="#menu")
        """
        if isinstance(attr, str):
            attr_list = [attr, ""]
        else:
            attr_list = list(attr)

        opts: dict[str, Any] = {"attr": attr_list}
        if to:
            opts["to"] = to
        return self.add(JsCommand("toggle_attr", opts))

    # Event Commands

    def push(
        self,
        event: str,
        *,
        target: str | None = None,
        value: dict[str, Any] | None = None,
        loading: str | None = None,
        page_loading: bool = False,
    ) -> "JsCommands":
        """
        Push an event to the server.

        Args:
            event: The event name to push.
            target: CSS selector for the target LiveView/Component.
            value: Additional data to send with the event.
            loading: CSS selector for element(s) to apply loading classes to.
            page_loading: Whether to show page loading indicator.

        Example:
            js.push("increment")
            js.push("delete", value={"id": 123})
            js.push("save", target="#form", loading="#spinner")
        """
        opts: dict[str, Any] = {"event": event}
        if target:
            opts["target"] = target
        if value:
            opts["value"] = value
        if loading:
            opts["loading"] = loading
        if page_loading:
            opts["page_loading"] = True
        return self.add(JsCommand("push", opts))

    def dispatch(
        self,
        event: str,
        to: str | None = None,
        *,
        detail: dict[str, Any] | None = None,
        bubbles: bool = True,
    ) -> "JsCommands":
        """
        Dispatch a custom DOM event.

        Args:
            event: The event name to dispatch.
            to: CSS selector for target element(s). Defaults to current element.
            detail: Custom data to include in event.detail.
            bubbles: Whether the event bubbles up through the DOM (default: True).

        Example:
            js.dispatch("copy-to-clipboard", to="#text")
            js.dispatch("modal:open", detail={"id": "confirm-dialog"})
        """
        opts: dict[str, Any] = {"event": event}
        if to:
            opts["to"] = to
        if detail:
            opts["detail"] = detail
        if not bubbles:
            opts["bubbles"] = False
        return self.add(JsCommand("dispatch", opts))

    # Focus Commands

    def focus(
        self,
        *,
        to: str | None = None,
    ) -> "JsCommands":
        """
        Focus an element.

        Args:
            to: CSS selector for target element. Defaults to current element.

        Example:
            js.focus(to="#email-input")
        """
        opts: dict[str, Any] = {}
        if to:
            opts["to"] = to
        return self.add(JsCommand("focus", opts))

    def focus_first(
        self,
        *,
        to: str | None = None,
    ) -> "JsCommands":
        """
        Focus the first focusable child element.

        Args:
            to: CSS selector for container element. Defaults to current element.

        Example:
            js.focus_first(to="#form")
        """
        opts: dict[str, Any] = {}
        if to:
            opts["to"] = to
        return self.add(JsCommand("focus_first", opts))

    def push_focus(
        self,
        *,
        to: str | None = None,
    ) -> "JsCommands":
        """
        Push current focus onto the focus stack and focus an element.

        Used with pop_focus() to restore focus after a modal/dialog closes.

        Args:
            to: CSS selector for element to focus. Defaults to current element.

        Example:
            js.push_focus(to="#modal")
        """
        opts: dict[str, Any] = {}
        if to:
            opts["to"] = to
        return self.add(JsCommand("push_focus", opts))

    def pop_focus(self) -> "JsCommands":
        """
        Pop and focus the previously pushed element from the focus stack.

        Used with push_focus() to restore focus after a modal/dialog closes.

        Example:
            js.pop_focus()
        """
        return self.add(JsCommand("pop_focus", {}))

    # Navigation Commands

    def navigate(
        self,
        href: str,
        *,
        replace: bool = False,
    ) -> "JsCommands":
        """
        Navigate to a new page using LiveView navigation.

        This performs a live navigation, maintaining the WebSocket connection
        when navigating between LiveViews.

        Args:
            href: The URL to navigate to.
            replace: Whether to replace the current history entry (default: False).

        Example:
            js.navigate("/users/123")
            js.navigate("/dashboard", replace=True)
        """
        opts: dict[str, Any] = {"href": href}
        if replace:
            opts["replace"] = True
        return self.add(JsCommand("navigate", opts))

    def patch(
        self,
        href: str,
        *,
        replace: bool = False,
    ) -> "JsCommands":
        """
        Patch the current LiveView with new URL parameters.

        This updates the URL and triggers handle_params without a full navigation.

        Args:
            href: The URL to patch to.
            replace: Whether to replace the current history entry (default: False).

        Example:
            js.patch("/users?page=2")
            js.patch("/search?q=hello", replace=True)
        """
        opts: dict[str, Any] = {"href": href}
        if replace:
            opts["replace"] = True
        return self.add(JsCommand("patch", opts))

    # Utility Commands

    def exec(
        self,
        attr: str,
        *,
        to: str | None = None,
    ) -> "JsCommands":
        """
        Execute JS commands stored in an element's attribute.

        This allows storing JS commands in data attributes and executing them
        dynamically.

        Args:
            attr: The attribute name containing JS commands (e.g., "data-confirm").
            to: CSS selector for target element. Defaults to current element.

        Example:
            # In template: <div id="el" data-on-success='[["show", {"to": "#msg"}]]'>
            js.exec("data-on-success", to="#el")
        """
        opts: dict[str, Any] = {"attr": attr}
        if to:
            opts["to"] = to
        return self.add(JsCommand("exec", opts))

    # Serialization

    def __str__(self) -> str:
        """Serialize commands to JSON for use in HTML attributes."""
        return json.dumps([(c.cmd, c.opts) for c in self.commands])

    def __html__(self) -> str:
        """
        Return HTML-escaped JSON for safe insertion into HTML attributes.

        This method is called by template engines (including LiveViewTemplate
        for t-strings) to get the HTML-safe representation. The JSON is
        HTML-entity-escaped so that characters like " don't break attribute
        quoting. The browser decodes the entities, so phx-click etc. still
        receive the correct JSON value.
        """
        return escape_html(self.__str__())


# JS Builder Singleton (for t-string API)


class _JsBuilder:
    """
    Singleton namespace for creating JS commands.

    This provides a clean entry point for creating JS command chains in t-string
    templates. Each method returns a new JsCommands instance that can be chained.

    Usage:
        from pyview.js import js

        def template(self, assigns, meta):
            return t'''
            <button phx-click="{js.show('#modal')}">Open</button>
            <button phx-click="{js.hide('#modal').push('close')}">Close</button>
            '''
    """

    def show(
        self,
        to: str | None = None,
        *,
        transition: Transition | None = None,
        time: int = 200,
        display: str | None = None,
        blocking: bool = True,
    ) -> JsCommands:
        """Show element(s). See JsCommands.show() for details."""
        return JsCommands([]).show(
            to, transition=transition, time=time, display=display, blocking=blocking
        )

    def hide(
        self,
        to: str | None = None,
        *,
        transition: Transition | None = None,
        time: int = 200,
        blocking: bool = True,
    ) -> JsCommands:
        """Hide element(s). See JsCommands.hide() for details."""
        return JsCommands([]).hide(to, transition=transition, time=time, blocking=blocking)

    def toggle(
        self,
        to: str | None = None,
        *,
        in_transition: Transition | None = None,
        out_transition: Transition | None = None,
        time: int = 200,
        display: str | None = None,
        blocking: bool = True,
    ) -> JsCommands:
        """Toggle element visibility. See JsCommands.toggle() for details."""
        return JsCommands([]).toggle(
            to,
            in_transition=in_transition,
            out_transition=out_transition,
            time=time,
            display=display,
            blocking=blocking,
        )

    def add_class(
        self,
        names: str | Sequence[str],
        *,
        to: str | None = None,
        transition: Transition | None = None,
        time: int = 200,
        blocking: bool = True,
    ) -> JsCommands:
        """Add CSS class(es). See JsCommands.add_class() for details."""
        return JsCommands([]).add_class(
            names, to=to, transition=transition, time=time, blocking=blocking
        )

    def remove_class(
        self,
        names: str | Sequence[str],
        *,
        to: str | None = None,
        transition: Transition | None = None,
        time: int = 200,
        blocking: bool = True,
    ) -> JsCommands:
        """Remove CSS class(es). See JsCommands.remove_class() for details."""
        return JsCommands([]).remove_class(
            names, to=to, transition=transition, time=time, blocking=blocking
        )

    def toggle_class(
        self,
        names: str | Sequence[str],
        *,
        to: str | None = None,
        transition: Transition | None = None,
        time: int = 200,
        blocking: bool = True,
    ) -> JsCommands:
        """Toggle CSS class(es). See JsCommands.toggle_class() for details."""
        return JsCommands([]).toggle_class(
            names, to=to, transition=transition, time=time, blocking=blocking
        )

    def transition(
        self,
        transition: Transition,
        *,
        to: str | None = None,
        time: int = 200,
        blocking: bool = True,
    ) -> JsCommands:
        """Apply CSS transition. See JsCommands.transition() for details."""
        return JsCommands([]).transition(transition, to=to, time=time, blocking=blocking)

    def set_attribute(
        self,
        attr: str | tuple[str, str],
        *,
        to: str | None = None,
    ) -> JsCommands:
        """Set an attribute. See JsCommands.set_attribute() for details."""
        return JsCommands([]).set_attribute(attr, to=to)

    def remove_attribute(
        self,
        attr: str,
        *,
        to: str | None = None,
    ) -> JsCommands:
        """Remove an attribute. See JsCommands.remove_attribute() for details."""
        return JsCommands([]).remove_attribute(attr, to=to)

    def toggle_attribute(
        self,
        attr: str | tuple[str, str] | tuple[str, str, str],
        *,
        to: str | None = None,
    ) -> JsCommands:
        """Toggle an attribute. See JsCommands.toggle_attribute() for details."""
        return JsCommands([]).toggle_attribute(attr, to=to)

    def push(
        self,
        event: str,
        *,
        target: str | None = None,
        value: dict[str, Any] | None = None,
        loading: str | None = None,
        page_loading: bool = False,
    ) -> JsCommands:
        """Push an event to server. See JsCommands.push() for details."""
        return JsCommands([]).push(
            event, target=target, value=value, loading=loading, page_loading=page_loading
        )

    def dispatch(
        self,
        event: str,
        to: str | None = None,
        *,
        detail: dict[str, Any] | None = None,
        bubbles: bool = True,
    ) -> JsCommands:
        """Dispatch DOM event. See JsCommands.dispatch() for details."""
        return JsCommands([]).dispatch(event, to=to, detail=detail, bubbles=bubbles)

    def focus(
        self,
        *,
        to: str | None = None,
    ) -> JsCommands:
        """Focus an element. See JsCommands.focus() for details."""
        return JsCommands([]).focus(to=to)

    def focus_first(
        self,
        *,
        to: str | None = None,
    ) -> JsCommands:
        """Focus first focusable child. See JsCommands.focus_first() for details."""
        return JsCommands([]).focus_first(to=to)

    def push_focus(
        self,
        *,
        to: str | None = None,
    ) -> JsCommands:
        """Push focus stack. See JsCommands.push_focus() for details."""
        return JsCommands([]).push_focus(to=to)

    def pop_focus(self) -> JsCommands:
        """Pop focus stack. See JsCommands.pop_focus() for details."""
        return JsCommands([]).pop_focus()

    def navigate(
        self,
        href: str,
        *,
        replace: bool = False,
    ) -> JsCommands:
        """Navigate to URL. See JsCommands.navigate() for details."""
        return JsCommands([]).navigate(href, replace=replace)

    def patch(
        self,
        href: str,
        *,
        replace: bool = False,
    ) -> JsCommands:
        """Patch current URL. See JsCommands.patch() for details."""
        return JsCommands([]).patch(href, replace=replace)

    def exec(
        self,
        attr: str,
        *,
        to: str | None = None,
    ) -> JsCommands:
        """Execute JS from attribute. See JsCommands.exec() for details."""
        return JsCommands([]).exec(attr, to=to)


# Singleton instance for t-string usage
js = _JsBuilder()


# Ibis Template Integration (backwards compatibility)


@context_processor
def add_js(meta) -> dict[str, JsCommands]:
    """Inject empty JsCommands into template context for filter chaining."""
    return {"js": JsCommands([])}


# Register filters for Ibis template pipe syntax: {{ js.show("#id") | js.push("event") }}


@filters.register("js.show")
def js_show(js_cmds: JsCommands, selector: str) -> JsCommands:
    return js_cmds.show(selector)


@filters.register("js.hide")
def js_hide(js_cmds: JsCommands, selector: str) -> JsCommands:
    return js_cmds.hide(selector)


@filters.register("js.toggle")
def js_toggle(js_cmds: JsCommands, selector: str) -> JsCommands:
    return js_cmds.toggle(selector)


@filters.register("js.add_class")
def js_add_class(js_cmds: JsCommands, selector: str, *classes: str) -> JsCommands:
    # Legacy API: selector as first arg, classes as rest
    return js_cmds.add_class(list(classes), to=selector)


@filters.register("js.remove_class")
def js_remove_class(js_cmds: JsCommands, selector: str, *classes: str) -> JsCommands:
    # Legacy API: selector as first arg, classes as rest
    return js_cmds.remove_class(list(classes), to=selector)


@filters.register("js.toggle_class")
def js_toggle_class(js_cmds: JsCommands, selector: str, *classes: str) -> JsCommands:
    return js_cmds.toggle_class(list(classes), to=selector)


@filters.register("js.dispatch")
def js_dispatch(js_cmds: JsCommands, event: str, selector: str) -> JsCommands:
    # Legacy API: event first, selector second
    return js_cmds.dispatch(event, to=selector)


@filters.register("js.push")
def js_push(js_cmds: JsCommands, event: str, payload: dict[str, Any] | None = None) -> JsCommands:
    return js_cmds.push(event, value=payload)


@filters.register("js.focus")
def js_focus(js_cmds: JsCommands, selector: str) -> JsCommands:
    return js_cmds.focus(to=selector)


@filters.register("js.focus_first")
def js_focus_first(js_cmds: JsCommands, selector: str) -> JsCommands:
    return js_cmds.focus_first(to=selector)


@filters.register("js.transition")
def js_transition(
    js_cmds: JsCommands, selector: str, transition: str, time: int = 200
) -> JsCommands:
    # Legacy API: selector first
    return js_cmds.transition(transition, to=selector, time=time)


@filters.register("js.navigate")
def js_navigate(js_cmds: JsCommands, href: str) -> JsCommands:
    return js_cmds.navigate(href)


@filters.register("js.patch")
def js_patch(js_cmds: JsCommands, href: str) -> JsCommands:
    return js_cmds.patch(href)


@filters.register("js.set_attribute")
def js_set_attribute(
    js_cmds: JsCommands, attr: str | tuple[str, str], selector: str | None = None
) -> JsCommands:
    return js_cmds.set_attribute(attr, to=selector)


@filters.register("js.remove_attribute")
def js_remove_attribute(js_cmds: JsCommands, attr: str, selector: str | None = None) -> JsCommands:
    return js_cmds.remove_attribute(attr, to=selector)


@filters.register("js.toggle_attribute")
def js_toggle_attribute(
    js_cmds: JsCommands,
    attr: str | tuple[str, str] | tuple[str, str, str],
    selector: str | None = None,
) -> JsCommands:
    return js_cmds.toggle_attribute(attr, to=selector)


@filters.register("js.push_focus")
def js_push_focus(js_cmds: JsCommands, selector: str | None = None) -> JsCommands:
    return js_cmds.push_focus(to=selector)


@filters.register("js.pop_focus")
def js_pop_focus(js_cmds: JsCommands) -> JsCommands:
    return js_cmds.pop_focus()


@filters.register("js.exec")
def js_exec(js_cmds: JsCommands, attr: str, selector: str | None = None) -> JsCommands:
    return js_cmds.exec(attr, to=selector)
