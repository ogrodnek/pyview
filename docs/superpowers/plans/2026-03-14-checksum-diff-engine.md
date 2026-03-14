# Checksum Diff Engine Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `ChecksumDiffEngine` that produces identical diffs to the existing `calc_diff` but stores only a compact fingerprint tree instead of the full render tree.

**Architecture:** A new `checksum_diff.py` module containing `FingerprintNode` (dataclass), `_hash_val` (recursive hashing helper), `ChecksumDiffEngine` (stateful diff engine with `push()`), and `checksum_calc_diff` (drop-in wrapper). All existing code is untouched.

**Tech Stack:** Python 3.11+, pytest, dataclasses

**Spec:** `docs/superpowers/specs/2026-03-14-checksum-diff-engine-design.md`

---

## File Structure

```
pyview/template/
├── render_diff.py              # EXISTING — untouched
├── checksum_diff.py            # NEW — FingerprintNode, _hash_val, ChecksumDiffEngine, checksum_calc_diff

tests/template/
├── test_diff.py                # EXISTING — untouched
├── test_stream_diff.py         # EXISTING — untouched
├── test_checksum_diff.py       # NEW — all tests for checksum engine
```

## Chunk 1: Foundation

### Task 1: FingerprintNode dataclass and _hash_val helper

**Files:**
- Create: `pyview/template/checksum_diff.py`
- Create: `tests/template/test_checksum_diff.py`

- [ ] **Step 1: Write failing tests for `_hash_val`**

```python
# tests/template/test_checksum_diff.py
from pyview.template.checksum_diff import FingerprintNode, _hash_val


class TestHashVal:
    def test_hash_string(self):
        assert _hash_val("hello") == hash("hello")

    def test_hash_int(self):
        assert _hash_val(42) == hash(42)

    def test_hash_list_of_strings(self):
        """Statics arrays like ["<div>", "</div>"] must be hashable."""
        result = _hash_val(["<div>", "</div>"])
        assert isinstance(result, int)

    def test_hash_list_of_lists(self):
        """Dynamics arrays like [["item1"], ["item2"]] must be hashable."""
        result = _hash_val([["item1"], ["item2"]])
        assert isinstance(result, int)

    def test_hash_dict(self):
        """Nested dicts must be hashable."""
        result = _hash_val({"s": ["<div>", "</div>"], "0": "hello"})
        assert isinstance(result, int)

    def test_same_value_same_hash(self):
        assert _hash_val(["a", "b"]) == _hash_val(["a", "b"])

    def test_different_value_different_hash(self):
        assert _hash_val(["a", "b"]) != _hash_val(["a", "c"])

    def test_hash_empty_list(self):
        result = _hash_val([])
        assert isinstance(result, int)

    def test_hash_empty_dict(self):
        result = _hash_val({})
        assert isinstance(result, int)

    def test_hash_bool(self):
        assert _hash_val(True) == hash(True)

    def test_hash_empty_string(self):
        assert _hash_val("") == hash("")


class TestFingerprintNode:
    def test_create_node(self):
        node = FingerprintNode(fingerprint=123, children={"0": 456})
        assert node.fingerprint == 123
        assert node.children["0"] == 456

    def test_nested_node(self):
        child = FingerprintNode(fingerprint=789, children={"0": 111})
        parent = FingerprintNode(fingerprint=123, children={"1": child})
        assert isinstance(parent.children["1"], FingerprintNode)
        assert parent.children["1"].fingerprint == 789

    def test_int_keys(self):
        """Component CIDs use int keys."""
        node = FingerprintNode(fingerprint=123, children={1: 456, 2: 789})
        assert node.children[1] == 456
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/template/test_checksum_diff.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pyview.template.checksum_diff'`

- [ ] **Step 3: Implement FingerprintNode and _hash_val**

```python
# pyview/template/checksum_diff.py
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
        return hash(tuple((k, _hash_val(v)) for k in sorted(val, key=str) for v in [val[k]]))
    return hash(val)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/template/test_checksum_diff.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add pyview/template/checksum_diff.py tests/template/test_checksum_diff.py
git commit -m "feat: add FingerprintNode and _hash_val for checksum diff engine"
```

---

### Task 2: _build_prints helper

**Files:**
- Modify: `pyview/template/checksum_diff.py`
- Modify: `tests/template/test_checksum_diff.py`

- [ ] **Step 1: Write failing tests for `_build_prints`**

Append to `tests/template/test_checksum_diff.py`:

```python
from pyview.template.checksum_diff import _build_prints


class TestBuildPrints:
    def test_simple_tree(self):
        tree = {"s": ["<div>", "</div>"], "0": "hello"}
        prints = _build_prints(tree)
        assert isinstance(prints, FingerprintNode)
        assert isinstance(prints.fingerprint, int)
        assert isinstance(prints.children["s"], int)
        assert isinstance(prints.children["0"], int)

    def test_nested_tree(self):
        tree = {
            "s": ["<div>", "</div>"],
            "0": {"s": ["<span>", "</span>"], "0": "hello"},
        }
        prints = _build_prints(tree)
        assert isinstance(prints.children["0"], FingerprintNode)
        assert isinstance(prints.children["0"].children["0"], int)

    def test_comprehension_tree(self):
        tree = {"s": ["<li>", "</li>"], "d": [["item1"], ["item2"]]}
        prints = _build_prints(tree)
        # Comprehensions are stored as FingerprintNode with s and d as leaf hashes
        assert isinstance(prints, FingerprintNode)
        assert isinstance(prints.children["s"], int)
        assert isinstance(prints.children["d"], int)

    def test_empty_tree(self):
        prints = _build_prints({})
        assert isinstance(prints, FingerprintNode)
        assert prints.children == {}

    def test_component_tree(self):
        tree = {
            "s": ["<div>", "</div>"],
            "0": "content",
            "c": {1: {"s": ["<p>", "</p>"], "0": "comp"}},
        }
        prints = _build_prints(tree)
        assert isinstance(prints.children["c"], FingerprintNode)
        assert isinstance(prints.children["c"].children[1], FingerprintNode)

    def test_no_full_values_stored(self):
        """Prints should contain only ints and FingerprintNodes, never strings or lists."""
        tree = {"s": ["<div>", "</div>"], "0": "hello world this is a long string"}
        prints = _build_prints(tree)
        for v in prints.children.values():
            assert isinstance(v, (int, FingerprintNode))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/template/test_checksum_diff.py::TestBuildPrints -v`
Expected: FAIL — `ImportError: cannot import name '_build_prints'`

- [ ] **Step 3: Implement _build_prints**

Add to `pyview/template/checksum_diff.py`:

```python
def _build_prints(tree: dict[str, Any]) -> FingerprintNode:
    """Build a fingerprint tree from a render tree."""
    children: dict[str | int, int | FingerprintNode] = {}

    for key, val in tree.items():
        if isinstance(val, dict):
            children[key] = _build_prints(val)
        else:
            children[key] = _hash_val(val)

    rollup = hash(tuple(sorted(
        (k, v.fingerprint if isinstance(v, FingerprintNode) else v)
        for k, v in children.items()
    )))
    return FingerprintNode(fingerprint=rollup, children=children)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/template/test_checksum_diff.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add pyview/template/checksum_diff.py tests/template/test_checksum_diff.py
git commit -m "feat: add _build_prints to construct fingerprint tree from render tree"
```

---

## Chunk 2: Core Diff Engine

### Task 3: ChecksumDiffEngine with basic leaf diffing

**Files:**
- Modify: `pyview/template/checksum_diff.py`
- Modify: `tests/template/test_checksum_diff.py`

- [ ] **Step 1: Write failing tests for basic engine behavior**

Append to `tests/template/test_checksum_diff.py`:

```python
from pyview.template.checksum_diff import ChecksumDiffEngine, checksum_calc_diff


class TestChecksumDiffEngineBasics:
    def test_first_push_returns_full_tree(self):
        engine = ChecksumDiffEngine()
        tree = {"s": ["<div>", "</div>"], "0": "hello"}
        result = engine.push(tree)
        assert result == tree

    def test_identical_push_returns_empty_diff(self):
        engine = ChecksumDiffEngine()
        tree = {"s": ["<div>", "</div>"], "0": "hello"}
        engine.push(tree)
        assert engine.push(tree) == {}

    def test_leaf_change(self):
        engine = ChecksumDiffEngine()
        engine.push({"s": ["<div>", "</div>"], "0": "hello"})
        diff = engine.push({"s": ["<div>", "</div>"], "0": "goodbye"})
        assert diff == {"0": "goodbye"}

    def test_statics_change(self):
        engine = ChecksumDiffEngine()
        engine.push({"s": ["<div>", "</div>"], "0": "hello"})
        diff = engine.push({"s": ["<span>", "</span>"], "0": "hello"})
        assert diff == {"s": ["<span>", "</span>"]}

    def test_new_key(self):
        engine = ChecksumDiffEngine()
        engine.push({"s": ["<div>", "</div>"], "0": "hello"})
        diff = engine.push({"s": ["<div>", "</div>"], "0": "hello", "1": "world"})
        assert diff == {"1": "world"}

    def test_nested_dict_change(self):
        engine = ChecksumDiffEngine()
        engine.push({"s": ["<div>", "</div>"], "0": {"s": ["<span>", "</span>"], "0": "hello"}})
        diff = engine.push({"s": ["<div>", "</div>"], "0": {"s": ["<span>", "</span>"], "0": "goodbye"}})
        assert diff == {"0": {"0": "goodbye"}}

    def test_nested_no_change(self):
        engine = ChecksumDiffEngine()
        tree = {"s": ["<div>", "</div>"], "0": {"s": ["<span>", "</span>"], "0": "hello"}}
        engine.push(tree)
        assert engine.push(tree) == {}


class TestChecksumCalcDiffWrapper:
    def test_wrapper_basic(self):
        old = {"s": ["<div>", "</div>"], "0": "hello"}
        new = {"s": ["<div>", "</div>"], "0": "goodbye"}
        assert checksum_calc_diff(old, new) == {"0": "goodbye"}

    def test_wrapper_no_change(self):
        tree = {"s": ["<div>", "</div>"], "0": "hello"}
        assert checksum_calc_diff(tree, tree) == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/template/test_checksum_diff.py::TestChecksumDiffEngineBasics -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement ChecksumDiffEngine core and checksum_calc_diff**

Add to `pyview/template/checksum_diff.py`:

```python
def _is_comprehension(val: Any) -> bool:
    """Check if a value is a comprehension (dict with "s" and "d" keys)."""
    return isinstance(val, dict) and "s" in val and "d" in val


class ChecksumDiffEngine:
    def __init__(self):
        self._prints: FingerprintNode | None = None

    def push(self, tree: dict[str, Any]) -> dict[str, Any]:
        """Accept a new full render tree, return the diff."""
        if self._prints is None:
            self._prints = _build_prints(tree)
            return tree

        diff, self._prints = self._diff_tree(tree, self._prints)
        return diff

    def _diff_tree(
        self, new_tree: dict[str, Any], old_prints: FingerprintNode
    ) -> tuple[dict[str, Any], FingerprintNode]:
        new_prints = _build_prints(new_tree)

        if new_prints.fingerprint == old_prints.fingerprint:
            return {}, old_prints

        diff: dict[str, Any] = {}

        for key in new_tree:
            new_val = new_tree[key]
            old_child = old_prints.children.get(key)

            # Case 1: Comprehension (dict with "s" + "d")
            if _is_comprehension(new_val):
                self._diff_comprehension(key, new_val, old_child, diff)

            # Case 2: Stream-only dict (has "stream" but no "s"/"d")
            elif isinstance(new_val, dict) and "stream" in new_val:
                diff[key] = new_val

            # Case 3: Stream → empty string transition
            elif (
                new_val == ""
                and isinstance(old_child, FingerprintNode)
                and "stream" in old_child.children
            ):
                pass  # suppress — client retains stream content

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
        key: str,
        new_val: dict[str, Any],
        old_child: int | FingerprintNode | None,
        diff: dict[str, Any],
    ) -> None:
        # Case 1a: old was not a FingerprintNode — structure changed
        if not isinstance(old_child, FingerprintNode):
            diff[key] = new_val
            return

        has_stream = "stream" in new_val

        if has_stream:
            # Case 1b: Stream comprehension — always include stream ops
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
    old_tree: dict[str, Any], new_tree: dict[str, Any]
) -> dict[str, Any]:
    """Drop-in replacement for calc_diff using checksum engine."""
    engine = ChecksumDiffEngine()
    engine.push(old_tree)
    return engine.push(new_tree)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/template/test_checksum_diff.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add pyview/template/checksum_diff.py tests/template/test_checksum_diff.py
git commit -m "feat: implement ChecksumDiffEngine core with leaf, nested, and comprehension diffing"
```

---

## Chunk 3: Validate Against Existing Tests

### Task 4: Run all existing diff test scenarios through checksum engine

**Files:**
- Modify: `tests/template/test_checksum_diff.py`

The existing tests in `test_diff.py` and `test_stream_diff.py` use `calc_diff(old, new)` and assert specific results. We replicate every scenario using `checksum_calc_diff` and assert identical output.

- [ ] **Step 1: Write tests mirroring test_diff.py scenarios**

Append to `tests/template/test_checksum_diff.py`:

```python
from pyview.template.render_diff import calc_diff
from pyview.vendor.ibis import Template


class TestChecksumMatchesCalcDiff:
    """Every test from test_diff.py, run through both engines, asserting identical output."""

    def test_simple_diff_no_changes(self):
        t = Template("<div>{% if greeting %}<span>{{greeting}}</span>{% endif %}</div>")
        old = t.tree({"greeting": "Hello"})
        new = t.tree({"greeting": "Hello"})
        assert checksum_calc_diff(old, new) == calc_diff(old, new)

    def test_simple_diff(self):
        t = Template("<div>{% if greeting %}<span>{{greeting}}</span>{% endif %}</div>")
        old = t.tree({"greeting": "Hello"})
        new = t.tree({"greeting": "Goodbye"})
        assert checksum_calc_diff(old, new) == calc_diff(old, new)

    def test_conditional_diff_hello_to_empty(self):
        t = Template("<div>{% if greeting %}<span>{{greeting}}</span>{% endif %}</div>")
        old = t.tree({"greeting": "Hello"})
        new = t.tree({})
        assert checksum_calc_diff(old, new) == calc_diff(old, new)

    def test_conditional_diff_empty_to_hello(self):
        t = Template("<div>{% if greeting %}<span>{{greeting}}</span>{% endif %}</div>")
        old = t.tree({})
        new = t.tree({"greeting": "Hello"})
        assert checksum_calc_diff(old, new) == calc_diff(old, new)

    def test_loop_diff(self):
        t = Template("<div>{% for item in items %}<span>{{item}}</span>{% endfor %}</div>")
        old = t.tree({"items": ["One", "Two", "Three"]})
        new = t.tree({"items": ["One", "Two", "Four"]})
        assert checksum_calc_diff(old, new) == calc_diff(old, new)

    def test_loop_diff_no_change(self):
        t = Template("<div>{% for item in items %}<span>{{item}}</span>{% endfor %}</div>")
        old = t.tree({"items": ["One", "Two", "Three"]})
        new = t.tree({"items": ["One", "Two", "Three"]})
        assert checksum_calc_diff(old, new) == calc_diff(old, new)

    def test_loop_diff_empty_to_nonempty(self):
        t = Template("<div>{% for item in items %}<span>{{item}}</span>{% endfor %}</div>")
        old = t.tree({"items": []})
        new = t.tree({"items": ["One", "Two", "Three"]})
        assert checksum_calc_diff(old, new) == calc_diff(old, new)

    def test_loop_diff_nonempty_to_empty(self):
        t = Template("<div>{% for item in items %}<span>{{item}}</span>{% endfor %}</div>")
        old = t.tree({"items": ["One", "Two", "Three"]})
        new = t.tree({"items": []})
        assert checksum_calc_diff(old, new) == calc_diff(old, new)

    def test_loop_diff_size_change(self):
        t = Template("<div>{% for item in items %}<span>{{item}}</span>{% endfor %}</div>")
        old = t.tree({"items": ["One", "Two", "Three"]})
        new = t.tree({"items": ["One"]})
        assert checksum_calc_diff(old, new) == calc_diff(old, new)

    def test_loop_diff_static_change(self):
        t = Template("<div>{% for item in items %}<span>{{item}}</span>{% endfor %}</div>")
        t2 = Template("<div>{% for item in items %}<div>{{item}}</div>{% endfor %}</div>")
        old = t.tree({"items": ["One", "Two", "Three"]})
        new = t2.tree({"items": ["One", "Two", "Three", "Four"]})
        assert checksum_calc_diff(old, new) == calc_diff(old, new)

    def test_diff_template_change(self):
        t = Template("<div><span>{{greeting}}</span></div>")
        t2 = Template(
            "<div>{% if greeting %}<span>{{greeting}}</span>{% endif %}<p>{{farewell}}</p></div>"
        )
        old = t.tree({"greeting": "Hello"})
        new = t2.tree({"greeting": "Hello", "farewell": "Goodbye"})
        assert checksum_calc_diff(old, new) == calc_diff(old, new)

    def test_statics_only_change(self):
        t = Template("<div><span>{{greeting}}</span></div>")
        t2 = Template("<div>{{greeting}}</div>")
        old = t.tree({"greeting": "Hello"})
        new = t2.tree({"greeting": "Hello"})
        assert checksum_calc_diff(old, new) == calc_diff(old, new)

    def test_nested_string_to_dict(self):
        old = {"a": {"b": "some string with s inside"}}
        new = {"a": {"b": {"s": [42]}}}
        assert checksum_calc_diff(old, new) == calc_diff(old, new)

    def test_dict_missing_d_key(self):
        old = {"0": {"s": ["<span>", "</span>"]}}
        new = {"0": {"s": ["<span>", "</span>"], "d": [["Item1"], ["Item2"]]}}
        assert checksum_calc_diff(old, new) == calc_diff(old, new)

    def test_dict_missing_both_s_and_d(self):
        old = {"0": {"foo": "bar", "baz": 123}}
        new = {"0": {"s": ["<div>", "</div>"], "d": [["A"]]}}
        assert checksum_calc_diff(old, new) == calc_diff(old, new)

    def test_component_cid_to_comprehension(self):
        old = {"0": 1}
        new = {"0": {"s": ["<span>", "</span>"], "d": [["Item1"], ["Item2"]]}}
        assert checksum_calc_diff(old, new) == calc_diff(old, new)

    def test_comprehension_to_component_cid(self):
        old = {"0": {"s": ["<span>", "</span>"], "d": [["Item1"], ["Item2"]]}}
        new = {"0": 2}
        assert checksum_calc_diff(old, new) == calc_diff(old, new)
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/template/test_checksum_diff.py::TestChecksumMatchesCalcDiff -v`
Expected: All PASS. If any fail, debug and fix the engine — the existing `calc_diff` output is the source of truth.

- [ ] **Step 3: Commit**

```bash
git add tests/template/test_checksum_diff.py
git commit -m "test: validate checksum engine against all existing diff test scenarios"
```

---

### Task 5: Run all existing stream diff test scenarios through checksum engine

**Files:**
- Modify: `tests/template/test_checksum_diff.py`

- [ ] **Step 1: Write tests mirroring test_stream_diff.py scenarios**

Append to `tests/template/test_checksum_diff.py`:

```python
from dataclasses import dataclass as dc
from pyview.stream import Stream


@dc
class _User:
    id: int
    name: str


class TestChecksumMatchesStreamDiff:
    """Every test from test_stream_diff.py, run through both engines."""

    def test_first_render_includes_full_tree(self):
        template = Template(
            """{% for dom_id, user in users %}<div id="{{ dom_id }}">{{ user.name }}</div>{% endfor %}"""
        )
        stream = Stream([_User(id=1, name="Alice")], name="users")
        tree = template.tree({"users": stream})
        assert checksum_calc_diff({}, tree) == calc_diff({}, tree)

    def test_same_stream_no_ops_empty_diff(self):
        template = Template(
            """{% for dom_id, user in users %}<div id="{{ dom_id }}">{{ user.name }}</div>{% endfor %}"""
        )
        stream = Stream([_User(id=1, name="Alice")], name="users")
        tree1 = template.tree({"users": stream})
        tree2 = template.tree({"users": stream})
        assert checksum_calc_diff(tree1, tree2) == calc_diff(tree1, tree2)

    def test_new_insert_produces_diff(self):
        template = Template(
            """{% for dom_id, user in users %}<div id="{{ dom_id }}">{{ user.name }}</div>{% endfor %}"""
        )
        stream = Stream([_User(id=1, name="Alice")], name="users")
        tree1 = template.tree({"users": stream})
        stream.insert(_User(id=2, name="Bob"))
        tree2 = template.tree({"users": stream})
        assert checksum_calc_diff(tree1, tree2) == calc_diff(tree1, tree2)

    def test_delete_operation_in_diff(self):
        template = Template(
            """{% for dom_id, user in users %}<div id="{{ dom_id }}">{{ user.name }}</div>{% endfor %}"""
        )
        stream = Stream([_User(id=1, name="Alice")], name="users")
        tree1 = template.tree({"users": stream})
        stream.delete_by_id("users-1")
        tree2 = template.tree({"users": stream})
        assert checksum_calc_diff(tree1, tree2) == calc_diff(tree1, tree2)

    def test_reset_operation_in_diff(self):
        template = Template(
            """{% for dom_id, user in users %}<div id="{{ dom_id }}">{{ user.name }}</div>{% endfor %}"""
        )
        stream = Stream([_User(id=1, name="Alice")], name="users")
        tree1 = template.tree({"users": stream})
        stream.reset([_User(id=10, name="New User")])
        tree2 = template.tree({"users": stream})
        assert checksum_calc_diff(tree1, tree2) == calc_diff(tree1, tree2)

    def test_sequential_inserts(self):
        template = Template(
            """{% for dom_id, user in users %}<li id="{{ dom_id }}">{{ user.name }}</li>{% endfor %}"""
        )
        stream = Stream(name="users")
        tree1 = template.tree({"users": stream})
        stream.insert(_User(id=1, name="Alice"))
        tree2 = template.tree({"users": stream})
        # Note: for sequential, we test both steps
        assert checksum_calc_diff(tree1, tree2) == calc_diff(tree1, tree2)
        stream.insert(_User(id=2, name="Bob"))
        tree3 = template.tree({"users": stream})
        assert checksum_calc_diff(tree2, tree3) == calc_diff(tree2, tree3)

    def test_insert_then_delete_sequence(self):
        template = Template(
            """{% for dom_id, user in users %}<li id="{{ dom_id }}">{{ user.name }}</li>{% endfor %}"""
        )
        stream = Stream([_User(id=1, name="Alice")], name="users")
        tree1 = template.tree({"users": stream})
        stream.delete_by_id("users-1")
        tree2 = template.tree({"users": stream})
        assert checksum_calc_diff(tree1, tree2) == calc_diff(tree1, tree2)

    def test_insert_and_delete_same_render(self):
        template = Template(
            """{% for dom_id, user in users %}<li id="{{ dom_id }}">{{ user.name }}</li>{% endfor %}"""
        )
        stream = Stream([_User(id=1, name="Alice")], name="users")
        tree1 = template.tree({"users": stream})
        stream.insert(_User(id=2, name="Bob"))
        stream.delete_by_id("users-1")
        tree2 = template.tree({"users": stream})
        assert checksum_calc_diff(tree1, tree2) == calc_diff(tree1, tree2)

    def test_empty_to_populated(self):
        template = Template(
            """{% for dom_id, user in users %}<li id="{{ dom_id }}">{{ user.name }}</li>{% endfor %}"""
        )
        stream = Stream(name="users")
        tree1 = template.tree({"users": stream})
        stream.insert(_User(id=1, name="Alice"))
        stream.insert(_User(id=2, name="Bob"))
        tree2 = template.tree({"users": stream})
        assert checksum_calc_diff(tree1, tree2) == calc_diff(tree1, tree2)

    def test_populated_to_empty_via_reset(self):
        template = Template(
            """{% for dom_id, user in users %}<li id="{{ dom_id }}">{{ user.name }}</li>{% endfor %}"""
        )
        stream = Stream([_User(id=1, name="Alice")], name="users")
        tree1 = template.tree({"users": stream})
        stream.reset()
        tree2 = template.tree({"users": stream})
        assert checksum_calc_diff(tree1, tree2) == calc_diff(tree1, tree2)

    def test_stream_with_surrounding_content(self):
        template = Template(
            """<h1>{{ title }}</h1><ul>{% for dom_id, user in users %}<li id="{{ dom_id }}">{{ user.name }}</li>{% endfor %}</ul>"""
        )
        stream = Stream([_User(id=1, name="Alice")], name="users")
        tree1 = template.tree({"title": "Users", "users": stream})
        stream.insert(_User(id=2, name="Bob"))
        tree2 = template.tree({"title": "Active Users", "users": stream})
        assert checksum_calc_diff(tree1, tree2) == calc_diff(tree1, tree2)

    def test_nested_template_with_stream(self):
        template = Template(
            """{% if show %}<div>{% for dom_id, user in users %}<span id="{{ dom_id }}">{{ user.name }}</span>{% endfor %}</div>{% endif %}"""
        )
        stream = Stream([_User(id=1, name="Alice")], name="users")
        tree1 = template.tree({"show": True, "users": stream})
        stream.insert(_User(id=2, name="Bob"))
        tree2 = template.tree({"show": True, "users": stream})
        assert checksum_calc_diff(tree1, tree2) == calc_diff(tree1, tree2)

    def test_regular_loop_no_stream_key(self):
        template = Template("""{% for user in users %}<li>{{ user.name }}</li>{% endfor %}""")
        users1 = [_User(id=1, name="Alice")]
        tree1 = template.tree({"users": users1})
        users2 = [_User(id=1, name="Alice"), _User(id=2, name="Bob")]
        tree2 = template.tree({"users": users2})
        assert checksum_calc_diff(tree1, tree2) == calc_diff(tree1, tree2)
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/template/test_checksum_diff.py::TestChecksumMatchesStreamDiff -v`
Expected: All PASS. If any fail, debug and fix the engine.

- [ ] **Step 3: Commit**

```bash
git add tests/template/test_checksum_diff.py
git commit -m "test: validate checksum engine against all existing stream diff scenarios"
```

---

## Chunk 4: Checksum-Specific Tests and Polish

### Task 6: Multi-push and engine-specific tests

**Files:**
- Modify: `tests/template/test_checksum_diff.py`

- [ ] **Step 1: Write checksum-specific tests**

Append to `tests/template/test_checksum_diff.py`:

```python
class TestChecksumEngineSpecific:
    """Tests for behaviors unique to the stateful checksum engine."""

    def test_three_push_sequence(self):
        engine = ChecksumDiffEngine()
        t = Template("<div>{{greeting}}</div>")

        d1 = engine.push(t.tree({"greeting": "Hello"}))
        assert "0" in d1  # first render, full tree

        d2 = engine.push(t.tree({"greeting": "Hi"}))
        assert d2 == {"0": "Hi"}

        d3 = engine.push(t.tree({"greeting": "Hey"}))
        assert d3 == {"0": "Hey"}

    def test_push_same_tree_three_times(self):
        engine = ChecksumDiffEngine()
        tree = {"s": ["<div>", "</div>"], "0": "hello"}
        engine.push(tree)
        assert engine.push(tree) == {}
        assert engine.push(tree) == {}

    def test_push_change_then_revert(self):
        engine = ChecksumDiffEngine()
        tree_a = {"s": ["<div>", "</div>"], "0": "hello"}
        tree_b = {"s": ["<div>", "</div>"], "0": "goodbye"}
        engine.push(tree_a)
        assert engine.push(tree_b) == {"0": "goodbye"}
        assert engine.push(tree_a) == {"0": "hello"}

    def test_fingerprint_tree_compactness(self):
        """Verify internal state contains no full values."""
        engine = ChecksumDiffEngine()
        engine.push({
            "s": ["<div>", " long content here ", "</div>"],
            "0": "a very long dynamic string value",
            "1": {"s": ["<span>", "</span>"], "0": "nested value"},
        })

        def assert_compact(node):
            assert isinstance(node, FingerprintNode)
            assert isinstance(node.fingerprint, int)
            for v in node.children.values():
                if isinstance(v, FingerprintNode):
                    assert_compact(v)
                else:
                    assert isinstance(v, int), f"Expected int hash, got {type(v)}: {v}"

        assert_compact(engine._prints)

    def test_structure_transition_leaf_to_dict(self):
        engine = ChecksumDiffEngine()
        engine.push({"s": ["<div>", "</div>"], "0": "plain string"})
        diff = engine.push({"s": ["<div>", "</div>"], "0": {"s": ["<span>", "</span>"], "0": "nested"}})
        assert diff == {"0": {"s": ["<span>", "</span>"], "0": "nested"}}

    def test_structure_transition_dict_to_leaf(self):
        engine = ChecksumDiffEngine()
        engine.push({"s": ["<div>", "</div>"], "0": {"s": ["<span>", "</span>"], "0": "nested"}})
        diff = engine.push({"s": ["<div>", "</div>"], "0": ""})
        assert diff == {"0": ""}

    def test_stream_to_empty_suppressed(self):
        """Stream → empty string should NOT produce a diff (client retains content)."""
        # Simulate a stream comprehension tree
        old = {
            "s": ["<ul>", "</ul>"],
            "0": {
                "s": ["<li>", "</li>"],
                "d": [["Alice"]],
                "stream": ["users", [["users-1", -1, None]], []],
            },
        }
        # After stream ops consumed, slot becomes empty string
        new = {"s": ["<ul>", "</ul>"], "0": ""}
        assert checksum_calc_diff(old, new) == calc_diff(old, new)

    def test_regular_comprehension_to_empty_not_suppressed(self):
        """Regular comprehension (no stream) → empty string SHOULD produce a diff."""
        old = {
            "s": ["<div>", "</div>"],
            "0": {"s": ["<span>", "</span>"], "d": [["One"], ["Two"]]},
        }
        new = {"s": ["<div>", "</div>"], "0": ""}
        result = checksum_calc_diff(old, new)
        assert result == {"0": ""}
        assert result == calc_diff(old, new)
```

- [ ] **Step 2: Run all tests**

Run: `uv run pytest tests/template/test_checksum_diff.py -v`
Expected: All PASS

- [ ] **Step 3: Also verify existing tests still pass**

Run: `uv run pytest tests/template/test_diff.py tests/template/test_stream_diff.py -v`
Expected: All PASS (these files were never modified)

- [ ] **Step 4: Commit**

```bash
git add tests/template/test_checksum_diff.py
git commit -m "test: add checksum engine-specific tests for multi-push, compactness, transitions"
```

---

### Task 7: Run full test suite

- [ ] **Step 1: Run entire project test suite**

Run: `uv run pytest -vvvs`
Expected: All PASS — no regressions anywhere.

- [ ] **Step 2: Final commit if any fixes were needed**

Only if changes were made during debugging.
