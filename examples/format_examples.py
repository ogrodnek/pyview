from dataclasses import dataclass, field
from typing import Iterator, Optional

from pyview import LiveView


@dataclass
class ExampleEntry:
    url_path: str
    title: str
    src_path: str
    text: str
    tags: list[str] = field(default_factory=list)


def format_example(
    url_path: str, lv: type[LiveView], tags: list[str] | None = None
) -> Optional[ExampleEntry]:
    if not lv.__doc__:
        return None

    # parse name and title from docstring, separated by blank line
    docs = lv.__doc__.strip().split("\n\n")
    title = docs[0]
    text = "".join(docs[1:])

    # get dirpectory path from module name
    src_path = "/".join(lv.__module__.split(".")[:-1])

    return ExampleEntry(url_path, title, src_path, text.strip(), tags or [])


def format_examples(
    routes: list[tuple[str, type[LiveView], list[str]]],
) -> Iterator[ExampleEntry]:
    for url, lv, tags in routes:
        f = format_example(url, lv, tags)
        if f:
            yield f
