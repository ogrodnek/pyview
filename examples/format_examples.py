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


@dataclass(frozen=True)
class ExampleRoute:
    entry_path: str
    view: type[LiveView]
    tags: tuple[str, ...] = ()
    additional_paths: tuple[str, ...] = ()

    @property
    def registered_paths(self) -> tuple[str, ...]:
        return (self.entry_path, *self.additional_paths)


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
    routes: list[ExampleRoute],
) -> Iterator[ExampleEntry]:
    for route in routes:
        f = format_example(route.entry_path, route.view, list(route.tags))
        if f:
            yield f
