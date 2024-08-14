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


def find_associated_css(o: object) -> list[Markup]:
    css_file = find_associated_file(o, ".css")
    if css_file:
        with open(css_file, "r") as css:
            return [Markup(f"<style>{css.read()}</style>")]

    return []
