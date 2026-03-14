from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class FingerprintNode:
    fingerprint: int
    children: dict[str | int, int | FingerprintNode]


def _hash_val(val: Any) -> int:
    """Hash any render tree value, including lists and dicts."""
    if isinstance(val, (str, int, float, bool)):
        return hash(val)
    if isinstance(val, list):
        return hash(tuple(_hash_val(v) for v in val))
    if isinstance(val, dict):
        return hash(tuple((k, _hash_val(val[k])) for k in sorted(val, key=str)))
    return hash(val)


def _build_prints(tree: dict[str | int, Any]) -> FingerprintNode:
    """Build a fingerprint tree from a render tree."""
    children: dict[str | int, int | FingerprintNode] = {}

    for key, val in tree.items():
        if isinstance(val, dict):
            children[key] = _build_prints(val)
        else:
            children[key] = _hash_val(val)

    rollup = hash(
        tuple(
            sorted(
                (k, v.fingerprint if isinstance(v, FingerprintNode) else v)
                for k, v in children.items()
            )
        )
    )
    return FingerprintNode(fingerprint=rollup, children=children)


def _is_comprehension(val: Any) -> bool:
    """Check if a value is a comprehension (dict with "s" and "d" keys)."""
    return isinstance(val, dict) and "s" in val and "d" in val


class ChecksumDiffEngine:
    def __init__(self):
        self._prints: FingerprintNode | None = None

    def push(self, tree: dict[str | int, Any]) -> dict[str | int, Any]:
        """Accept a new full render tree, return the diff."""
        if self._prints is None:
            self._prints = _build_prints(tree)
            return tree

        diff, self._prints = self._diff_tree(tree, self._prints)
        return diff

    def _diff_tree(
        self, new_tree: dict[str | int, Any], old_prints: FingerprintNode
    ) -> tuple[dict[str | int, Any], FingerprintNode]:
        new_prints = _build_prints(new_tree)

        if new_prints.fingerprint == old_prints.fingerprint:
            return {}, old_prints

        diff: dict[str | int, Any] = {}

        for key in new_tree:
            new_val = new_tree[key]
            old_child = old_prints.children.get(key)

            # Case 1: Comprehension (dict with "s" + "d")
            if _is_comprehension(new_val):
                self._diff_comprehension(key, new_val, old_child, diff)

            # Case 2: Stream-only dict (has "stream" but no "s"/"d")
            elif isinstance(new_val, dict) and "stream" in new_val:
                diff[key] = new_val

            # Case 3: Stream -> empty string transition
            elif (
                new_val == ""
                and isinstance(old_child, FingerprintNode)
                and "stream" in old_child.children
            ):
                pass  # suppress -- client retains stream content

            # Case 4: Regular nested dict
            elif isinstance(new_val, dict):
                if isinstance(old_child, FingerprintNode):
                    child_diff, _ = self._diff_tree(new_val, old_child)
                    if child_diff:
                        diff[key] = child_diff
                else:
                    diff[key] = new_val

            # Case 5: Leaf value
            else:
                new_hash = _hash_val(new_val)
                if new_hash != old_child:
                    diff[key] = new_val

        return diff, new_prints

    def _diff_comprehension(
        self,
        key: str | int,
        new_val: dict[str, Any],
        old_child: int | FingerprintNode | None,
        diff: dict[str | int, Any],
    ) -> None:
        # Case 1a: old was not a FingerprintNode -- structure changed
        if not isinstance(old_child, FingerprintNode):
            diff[key] = new_val
            return

        has_stream = "stream" in new_val

        if has_stream:
            # Case 1b: Stream comprehension -- always include stream ops
            comp_diff: dict[str, Any] = {"stream": new_val["stream"]}
            if new_val["d"]:
                comp_diff["d"] = new_val["d"]
            new_s_hash = _hash_val(new_val["s"])
            if new_s_hash != old_child.children.get("s"):
                comp_diff["s"] = new_val["s"]
            diff[key] = comp_diff
            return

        # Case 1c: Regular comprehension
        new_s_hash = _hash_val(new_val["s"])
        new_d_hash = _hash_val(new_val["d"])
        old_s_hash = old_child.children.get("s")
        old_d_hash = old_child.children.get("d")

        if new_s_hash != old_s_hash:
            diff[key] = {"s": new_val["s"], "d": new_val["d"]}
        elif new_d_hash != old_d_hash:
            diff[key] = {"d": new_val["d"]}


def checksum_calc_diff(
    old_tree: dict[str | int, Any], new_tree: dict[str | int, Any]
) -> dict[str | int, Any]:
    """Drop-in replacement for calc_diff using checksum engine."""
    engine = ChecksumDiffEngine()
    engine.push(old_tree)
    return engine.push(new_tree)
