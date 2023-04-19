import json
from typing import Union
from pyview.vendor.ibis import filters


JsArgs = Union[tuple[str, str], tuple[str, str, list[str]]]


@filters.register
def js(args: JsArgs):
    if len(args) > 2:
        cmd, id, names = args  # type: ignore
        return Js(cmd, id, names)
    cmd, id = args  # type: ignore
    return Js(cmd, id)


class Js:
    def __init__(self, cmd: str, id: str, names: list[str] = []):
        self.cmd = cmd
        self.id = id
        self.names = names

    def __str__(self):
        opts = {
            "to": self.id,
            "time": 200,
            "transition": [[], [], []],
        }

        if len(self.names) > 0:
            opts["names"] = self.names

        return json.dumps([[self.cmd, opts]])
