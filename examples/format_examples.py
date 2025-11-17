from dataclasses import dataclass
from typing import Iterator, Optional

from pyview import LiveView


@dataclass
class ExampleEntry:
    url_path: str
    title: str
    src_path: str
    text: str


def format_example(url_path: str, lv: type[LiveView]) -> Optional[ExampleEntry]:
    if not lv.__doc__:
        return None

    # parse name and title from docstring, separated by blank line
    docs = lv.__doc__.strip().split("\n\n")
    title = docs[0]
    text = "".join(docs[1:])

    # get dirpectory path from module name
    src_path = "/".join(lv.__module__.split(".")[:-1])

    return ExampleEntry(url_path, title, src_path, text.strip())


def format_examples(
    routes: list[tuple[str, type[LiveView]]],
) -> Iterator[ExampleEntry]:
    for url, lv in routes:
        f = format_example(url, lv)
        if f:
            yield f
