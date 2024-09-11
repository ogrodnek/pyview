from dataclasses import dataclass, field
from typing import Any, Union

Part = Union[str, "PartsTree", "PartsComprehension"]


@dataclass
class PartsComprehension:
    parts: list[Part]

    def __init__(self, parts: list[Part]):
        self.parts = parts

    def render_parts(self) -> Union[dict[str, Any], str]:
        if len(self.parts) == 0:
            return ""

        if len(self.parts) == 1:
            if isinstance(self.parts[0], PartsTree) and self.parts[0].is_empty():
                return ""

        def render(p: Part) -> Any:
            if isinstance(p, str):
                return p
            return p.render_parts()

        statics = self.parts[0].statics
        dynamics = [[render(d) for d in p.dynamics] for p in self.parts]

        return {
            "s": statics,
            "d": dynamics,
        }


@dataclass
class PartsTree:
    statics: list[str] = field(default_factory=list)
    dynamics: list[Part] = field(default_factory=list)

    def add_static(self, s: str):
        self.statics.append(s)

    def add_dynamic(self, d: Union[Part, list[Part]]):
        if len(self.statics) < len(self.dynamics) + 1:
            self.statics.append("")

        if isinstance(d, str):
            self.dynamics.append(d)
        elif isinstance(d, list):
            self.dynamics.append(PartsComprehension(d))
        else:
            self.dynamics.append(d.flatten())

    def flatten(self) -> Part:
        if len(self.statics) == 1 and len(self.dynamics) == 0:
            return self.statics[0]

        if len(self.statics) == 0 and len(self.dynamics) == 0:
            return ""

        return self

    def finish(self) -> "PartsTree":
        if len(self.statics) <= len(self.dynamics):
            self.statics.append("")

        return self

    def render_parts(self) -> dict[str, Any]:
        """
        Renders a Phoenix LiveView compatible render object.
        """

        if len(self.statics) <= len(self.dynamics):
            self.statics.append("")

        resp = {"s": self.statics}

        if len(self.dynamics) > 0:
            for i, dynamic in enumerate(self.dynamics):
                if isinstance(dynamic, str):
                    resp[f"{i}"] = dynamic
                else:
                    resp[f"{i}"] = dynamic.render_parts()

        return resp

    def is_empty(self) -> bool:
        return len(self.dynamics) == 0 and (
            len(self.statics) == 0 or (len(self.statics) == 1 and self.statics[0] == "")
        )
