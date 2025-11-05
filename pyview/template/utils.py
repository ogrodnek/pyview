from typing import Optional
import inspect
import os
from markupsafe import Markup


def find_associated_file(o: object, extension: str) -> Optional[str]:
    object_file = inspect.getfile(o.__class__)

    if object_file.endswith(".py"):
        object_file = object_file[:-3]

        associated_file = object_file + extension
        if os.path.isfile(associated_file):
            return associated_file


def find_associated_css(o: object | list[object]) -> list[Markup]:

    objects = o if isinstance(o, list) else [o]
    files = set(f for f in [find_associated_file(o, ".css") for o in objects] if f)

    ret = []
    for file in files:
        with open(file, "r") as css:
            source_comment = f"<!-- {os.path.basename(file)} -->"
            ret.append(Markup(f"\n{source_comment}\n<style>\n{css.read()}\n</style>"))

    return ret
