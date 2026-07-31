"""Paths: the one address space shared by params, errors and the DOM.

Three separate systems have to agree on how to name a nested field:

* the browser, which sends ``owner[pets][0][age]`` (all segments are strings)
* pydantic, which reports errors at ``("pets", 0, "age")`` (list indexes are ints)
* the params tree, which is dicts of strings after decoding

If those representations are not normalized to one form, touched-tracking misses
on every list row and errors silently fail to render next to their input. So:
**a path is always a tuple of strings**, and everything converts on the way in.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional, Union

__all__ = ["Path", "canon", "get_in", "put_in", "delete_in", "normalize"]

Path = tuple[str, ...]


def canon(path: Union[Iterable[Any], None]) -> Path:
    """Canonical path: every segment stringified."""
    if path is None:
        return ()
    return tuple(str(p) for p in path)


def get_in(node: Any, path: Path) -> Any:
    """Read a value out of a raw params tree, tolerating missing branches."""
    for key in path:
        if isinstance(node, dict):
            node = node.get(key)
        elif isinstance(node, list) and key.isdigit() and int(key) < len(node):
            node = node[int(key)]
        else:
            return None
        if node is None:
            return None
    return node


def put_in(root: dict[str, Any], path: Path, value: Any) -> None:
    """Write a value into a raw params tree, creating intermediate dicts."""
    if not path:
        raise ValueError("cannot put_in at the empty path")
    node: Any = root
    for key in path[:-1]:
        nxt = node.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            node[key] = nxt
        node = nxt
    node[path[-1]] = value


def delete_in(root: dict[str, Any], path: Path) -> None:
    """Remove a value from a raw params tree if present."""
    if not path:
        return
    node: Any = root
    for key in path[:-1]:
        node = node.get(key) if isinstance(node, dict) else None
        if not isinstance(node, dict):
            return
    node.pop(path[-1], None)


def normalize(node: Any) -> Any:
    """Convert digit-keyed maps into ordered lists.

    ``pets[0][name]`` decodes to ``{"pets": {"0": {...}}}`` (see
    :mod:`pyview.forms.params`), but pydantic wants ``{"pets": [{...}]}``. The
    digit keys are sorted numerically, so deleting row 1 of 0/1/2 leaves 0/2 in
    the right order without renumbering the remaining inputs.
    """
    if isinstance(node, dict):
        keys = list(node)
        if keys and all(k.isdigit() for k in keys):
            return [normalize(node[k]) for k in sorted(keys, key=int)]
        return {k: normalize(v) for k, v in node.items()}
    if isinstance(node, list):
        return [normalize(v) for v in node]
    return node


def strip_meta(params: dict[str, Any]) -> dict[str, Any]:
    """Drop LiveView's bookkeeping keys (``_target``, ``_csrf_token``, ...)."""
    return {k: v for k, v in params.items() if not k.startswith("_")}


def unwrap(params: dict[str, Any], name: Optional[str]) -> dict[str, Any]:
    """Pull the form's own subtree out of the payload.

    A form named ``"owner"`` renders inputs called ``owner[...]``, so its data
    arrives nested under ``"owner"``. A form with no name reads the top level.
    """
    if name is None:
        return strip_meta(params)
    value = params.get(name)
    return value if isinstance(value, dict) else {}
