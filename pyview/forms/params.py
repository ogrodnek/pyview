"""Phoenix-compatible decoding of urlencoded form bodies into nested data.

The LiveView JS client serializes the *entire* form on every ``phx-change`` and
``phx-submit`` and sends it as a urlencoded string. Nested inputs use bracket
notation::

    owner[address][city]=Portland&owner[pets][0][name]=Rex&_target=owner%5Bname%5D

``urllib.parse.parse_qs`` decodes that to flat keys with literal brackets, which
is why nested forms are currently out of reach. This module implements the same
semantics as Elixir's ``Plug.Conn.Query.decode/1``, which is what Phoenix uses.

Rules (matching Plug):

* ``a=1``            -> ``{"a": "1"}``           scalar, last value wins
* ``a[b]=1``         -> ``{"a": {"b": "1"}}``    map
* ``a[]=1&a[]=2``    -> ``{"a": ["1", "2"]}``    list, ``[]`` suffix only
* ``a[0][b]=1``      -> ``{"a": {"0": {"b": "1"}}}``

Note the last one: numeric subscripts produce a **map keyed by digit strings**,
not a list. That is deliberate and matches Plug/Ecto - it makes a row removable
without renumbering every sibling input. :func:`pyview.forms.paths.normalize`
converts those maps to ordered lists before validation.
"""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import unquote_plus

__all__ = ["decode", "decode_target", "encode_name"]

_SUBKEY = re.compile(r"\[([^\[\]]*)\]")


def _split_path(key: str) -> Optional[tuple[str, list[str]]]:
    """Split ``"a[b][]"`` into ``("a", ["b", ""])``.

    Returns ``None`` when the key is not well-formed bracket notation, in which
    case the caller treats it as a literal key (Plug does the same).
    """
    i = key.find("[")
    if i == -1:
        return key, []

    root, rest = key[:i], key[i:]
    parts = _SUBKEY.findall(rest)
    if "".join(f"[{p}]" for p in parts) != rest:
        return None
    return root, parts


def _assign(acc: dict[str, Any], root: str, path: list[str], value: str) -> None:
    if not path:
        acc[root] = value
        return

    head, *tail = path

    if head == "":
        current = acc.get(root)
        if not isinstance(current, list):
            current = []
            acc[root] = current
        if not tail:
            current.append(value)
        else:
            # a[][b]=1&a[][b]=2 -> [{"b": "1"}, {"b": "2"}]: start a new entry
            # once the key we are about to write is already present in the last one.
            if not current or (isinstance(current[-1], dict) and tail[0] in current[-1]):
                current.append({})
            _assign(current[-1], tail[0], tail[1:], value)
        return

    current = acc.get(root)
    if not isinstance(current, dict):
        current = {}
        acc[root] = current
    _assign(current, head, tail, value)


def decode(query: str) -> dict[str, Any]:
    """Decode a urlencoded form body into nested dicts and lists."""
    acc: dict[str, Any] = {}

    for pair in query.split("&"):
        if not pair:
            continue
        raw_key, _, raw_value = pair.partition("=")
        key = unquote_plus(raw_key)
        value = unquote_plus(raw_value)

        split = _split_path(key)
        if split is None:
            acc[key] = value
            continue

        root, path = split
        _assign(acc, root, path, value)

    return acc


def decode_target(target: str) -> list[str]:
    """Turn LiveView's ``_target`` into a path.

    The client sends the changed input's ``name`` attribute verbatim, e.g.
    ``"owner[pets][0][age]"``. Phoenix converts it to ``["owner", "pets", "0",
    "age"]`` before handing it to the view; so do we.
    """
    split = _split_path(target)
    if split is None:
        return [target]
    root, path = split
    return [root, *(p for p in path if p != "")]


def encode_name(path: tuple[str, ...]) -> str:
    """Inverse of :func:`decode_target`: ``("owner", "pets", "0", "age")`` ->
    ``"owner[pets][0][age]"``."""
    if not path:
        return ""
    head, *rest = path
    return head + "".join(f"[{p}]" for p in rest)


def normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept whatever pyview hands a handler and produce a nested tree.

    pyview currently decodes form events with :func:`urllib.parse.parse_qs`, which
    is flat: a nested input arrives as the literal key ``"owner[address][city]"``
    with a *list* value. Phoenix decodes the same body into nested maps. Until the
    socket layer changes, this re-folds the flat shape into the nested one so the
    rest of the form code has a single input format to reason about. Already-nested
    payloads pass through untouched.
    """
    if not isinstance(payload, dict):
        return payload

    out: dict[str, Any] = {}
    for key, value in payload.items():
        # `_target` is a path, not form data: a list here is already decoded and
        # must not be collapsed to its last element like a repeated input would be
        if key == "_target":
            out[key] = value
            continue

        values = value if isinstance(value, list) else [value]
        if not values:
            continue

        split = _split_path(key)
        if split is None:
            out[key] = values[-1]
            continue

        root, path = split
        if path and path[-1] == "":
            for item in values:
                _assign(out, root, path, item)
        else:
            # last value wins, which is what makes the hidden-input-before-checkbox
            # trick work: "false" then "true" collapses to "true"
            _assign(out, root, path, values[-1])

    target = out.get("_target")
    if isinstance(target, str):
        out["_target"] = decode_target(target)
    elif isinstance(target, list) and len(target) == 1 and isinstance(target[0], str):
        # parse_qs wraps it: ["owner[name]"] is a bracket-name, not a path
        out["_target"] = decode_target(target[0])

    return out
