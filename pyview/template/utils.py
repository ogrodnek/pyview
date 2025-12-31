import inspect
import os
import warnings
from typing import Optional

from markupsafe import Markup


def find_associated_file(o: object, extension: str) -> Optional[str]:
    """
    Find a file with the given extension colocated with an object's class definition.

    Args:
        o: Object whose class file to look next to
        extension: File extension to look for (e.g., ".css", ".html")

    Returns:
        Path to the file if found, None otherwise
    """
    object_file = inspect.getfile(o.__class__)

    if object_file.endswith(".py"):
        object_file = object_file[:-3]

        associated_file = object_file + extension
        if os.path.isfile(associated_file):
            return associated_file

    return None


def find_associated_css(o: object) -> list[Markup]:
    """
    Find CSS file colocated with an object's class and return as inline style tags.

    .. deprecated::
        This function injects CSS as inline <style> tags. For better caching
        and live navigation support, CSS is now automatically discovered and
        served via <link> tags through the CSS registry and render hooks.
        This function is kept for backward compatibility.

    Args:
        o: Object whose class file to look next to for a .css file

    Returns:
        List containing a Markup with inline <style> tag, or empty list
    """
    warnings.warn(
        "find_associated_css is deprecated. CSS is now automatically handled "
        "via CSSRegistry and render hooks with content-hashed <link> tags.",
        DeprecationWarning,
        stacklevel=2,
    )
    css_file = find_associated_file(o, ".css")
    if css_file:
        with open(css_file) as css:
            return [Markup(f"<style>{css.read()}</style>")]

    return []
