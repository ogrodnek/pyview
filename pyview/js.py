import json
from typing import Any, Optional
from pyview.vendor.ibis import filters
from pyview.template.context_processor import context_processor
from dataclasses import dataclass


@context_processor
def add_js(meta):
    return {"js": JsCommands([])}


@filters.register("js.add_class")
def js_add_class(js: "JsCommands", selector: str, *classes):
    return js.add_class(selector, *classes)


@filters.register("js.remove_class")
def js_remove_class(js: "JsCommands", selector: str, *classes):
    return js.remove_class(selector, *classes)


@filters.register("js.show")
def js_show(js: "JsCommands", selector: str):
    return js.show(selector)


@filters.register("js.hide")
def js_hide(js: "JsCommands", selector: str):
    return js.hide(selector)


@filters.register("js.toggle")
def js_toggle(js: "JsCommands", selector: str):
    return js.toggle(selector)


@filters.register("js.dispatch")
def js_dispatch(js: "JsCommands", event: str, selector: str):
    return js.dispatch(event, selector)


@filters.register("js.push")
def js_push(js: "JsCommands", event: str, payload: Optional[dict[str, Any]] = None):
    return js.push(event, payload)


@filters.register("js.focus")
def js_focus(js: "JsCommands", selector: str):
    return js.focus(selector)


@filters.register("js.focus_first")
def js_focus_first(js: "JsCommands", selector: str):
    return js.focus_first(selector)


@filters.register("js.transition")
def js_transition(js: "JsCommands", selector: str, transition: str, time: int = 200):
    return js.transition(selector, transition, time)


@dataclass
class JsCommand:
    cmd: str
    opts: dict[str, Any]


@dataclass
class JsCommands:
    commands: list[JsCommand]

    def add(self, cmd: JsCommand) -> "JsCommands":
        return JsCommands(self.commands + [cmd])

    def show(self, selector: str) -> "JsCommands":
        return self.add(JsCommand("show", {"to": selector}))

    def hide(self, selector: str) -> "JsCommands":
        return self.add(JsCommand("hide", {"to": selector}))

    def toggle(self, selector: str) -> "JsCommands":
        return self.add(JsCommand("toggle", {"to": selector}))

    def add_class(self, selector: str, *classes: str) -> "JsCommands":
        return self.add(JsCommand("add_class", {"to": selector, "names": classes}))

    def remove_class(self, selector: str, *classes: str) -> "JsCommands":
        return self.add(JsCommand("remove_class", {"to": selector, "names": classes}))

    def dispatch(self, event: str, selector: str) -> "JsCommands":
        return self.add(JsCommand("dispatch", {"to": selector, "event": event}))

    def push(
        self, event: str, payload: Optional[dict[str, Any]] = None
    ) -> "JsCommands":
        return self.add(
            JsCommand(
                "push", {"event": event} | ({"value": payload} if payload else {})
            )
        )

    def focus(self, selector: str) -> "JsCommands":
        return self.add(JsCommand("focus", {"to": selector}))

    def focus_first(self, selector: str) -> "JsCommands":
        return self.add(JsCommand("focus_first", {"to": selector}))

    def transition(
        self, selector: str, transition: str, time: int = 200
    ) -> "JsCommands":
        return self.add(
            JsCommand(
                "transition",
                {"to": selector, "time": time, "transition": [[transition], [], []]},
            )
        )

    def __str__(self):
        return json.dumps([(c.cmd, c.opts) for c in self.commands])
