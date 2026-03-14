# Checksum-Based Render Diff Engine

## Problem

pyview stores the full previous render tree (`prev_rendered` on `ConnectedLiveViewSocket`) and diffs it structurally against the new tree on every render. This keeps potentially large trees in memory per connected socket.

Phoenix LiveView avoids this with two systems: compile-time fingerprints on template statics, and `__changed__` tracking on assigns. pyview has neither, so we need a single system that hashes both statics and dynamics to detect changes efficiently.

## Goals

1. Build a standalone `ChecksumDiffEngine` that produces identical diffs to the existing `calc_diff` but stores only a compact fingerprint tree instead of the full render tree.
2. Provide a `checksum_calc_diff` drop-in wrapper so all existing tests can validate the new engine without any test changes.
3. No changes to existing code — `calc_diff`, `ConnectedLiveViewSocket`, templates, and wire format are untouched.

## Non-Goals (Future Work)

- Swapping the engine into `ConnectedLiveViewSocket` (requires `DiffStrategy` protocol).
- Configuration knobs (depth limits, size thresholds).
- Assign-level `__changed__` tracking (would enable statics-only fingerprinting like Phoenix).
- Template compile-time fingerprinting.

## Background: How Phoenix Does It

Phoenix LiveView uses two separate mechanisms (references to source at `/Users/logrodnek/src/github.com/phoenix_live_view`):

1. **Compile-time fingerprints** (`engine.ex:1327-1338`): MD5 hash of template block + static strings. Stored as a 128-bit integer on the `Rendered` struct (`engine.ex:108`). Identifies template *structure*, not values.

2. **`__changed__` map** (`utils.ex:96-112`): Tracks which assigns changed since last render. Dynamic expressions check this map and return `nil` (no change) if their assigns haven't changed.

These two mechanisms are supported by:

- **Fingerprint tree** (`diff.ex:40-42`): State is `{fingerprint, children_map}` — a tree of integers, not full rendered values. When fingerprints match (`diff.ex:389-407`), the entire subtree is skipped.
- **Static deduplication** (`diff.ex:752-762`): Statics with the same fingerprint are sent once and referenced by position integer thereafter.

pyview's approach must hash dynamics too since it lacks `__changed__` tracking — one system covering what Phoenix does with two.

## Design

### Data Structure: FingerprintNode

```python
@dataclass(slots=True)
class FingerprintNode:
    fingerprint: int
    children: dict[str | int, int | FingerprintNode]
```

The fingerprint tree is a compact shadow of the render tree:
- `fingerprint`: rollup hash of the entire subtree (enables O(1) skip when unchanged)
- `children`: maps wire format keys to either leaf hashes (`int`) or nested `FingerprintNode`s

Type of value in `children` tells you what it is:
- `int` → leaf hash, compare directly
- `FingerprintNode` → subtree, check rollup first then recurse

Example mapping:

```python
# Render tree:
{
    "s": ["<div>", " count: ", "</div>"],
    "0": "42",
    "1": {"s": ["<span>", "</span>"], "0": "hello"},
    "c": {1: {"s": ["<p>", "</p>"], "0": "component val"}}
}

# Fingerprint tree:
FingerprintNode(
    fingerprint=0xROLLUP,
    children={
        "s": 0xabc123,
        "0": 0xdef456,
        "1": FingerprintNode(
            fingerprint=0xNESTED,
            children={"s": 0x999888, "0": 0x111222},
        ),
        "c": FingerprintNode(
            fingerprint=0xCOMPS,
            children={
                1: FingerprintNode(
                    fingerprint=0xCOMP1,
                    children={"s": 0x333444, "0": 0x555666},
                ),
            },
        ),
    },
)
```

For comprehensions (`"s"` + `"d"` keys):
```python
# Render tree:
{"s": ["<li>", "</li>"], "d": [["item1"], ["item2"]]}

# Fingerprint tree:
FingerprintNode(
    fingerprint=0xROLLUP,
    children={"s": 0xSTATICS, "d": 0xDYNAMICS},
)
```

For streams: no fingerprint stored. Streams carry operations (inserts/deletes), not diffable state. Always included in diff — same as current behavior.

Note: the fingerprint tree does not encode what *kind* of node this is (comprehension vs regular dict vs component container). The diff algorithm always consults the new render tree's structure to determine which code path to follow. The fingerprint tree only provides hash comparisons for change detection.

### Hashing Strategy

Python's built-in `hash()` only works on hashable types (strings, ints, tuples). Render tree values include lists and dicts which are not hashable. We need a helper that recursively converts to hashable form:

```python
def _hash_val(val: Any) -> int:
    """Hash any render tree value, including lists and dicts."""
    if isinstance(val, (str, int, float, bool)):
        return hash(val)
    if isinstance(val, list):
        return hash(tuple(_hash_val(v) for v in val))
    if isinstance(val, dict):
        return hash(tuple((k, _hash_val(v)) for k in sorted(val) for v in [val[k]]))
    return hash(val)
```

This handles `"s"` (list of strings), `"d"` (list of lists), and any nested structure. The recursive conversion to tuples is fast for the sizes we deal with.

For rollup hashes, combine children hashes deterministically:

```python
rollup = hash(tuple(sorted((k, child_hash) for k, child_hash in children.items())))
```

Sorting by key ensures consistent ordering. Using `tuple()` for the outer container keeps it hashable.

Hashes are process-local due to Python's hash randomization (`PYTHONHASHSEED`). Fingerprint trees must not be serialized or shared across processes.

### Core Class

```python
class ChecksumDiffEngine:
    def __init__(self):
        self._prints: FingerprintNode | None = None

    def push(self, tree: dict[str, Any]) -> dict[str, Any]:
        """Accept a new full render tree, return the diff."""
        if self._prints is None:
            self._prints = self._build_prints(tree)
            return tree  # first render sends everything

        diff, self._prints = self._diff_tree(tree, self._prints)
        return diff
```

### Diff Algorithm

The algorithm mirrors the existing `calc_diff` code paths but uses hash comparison instead of value comparison. There are 7 distinct cases matching `render_diff.py`:

```
push(new_tree):
  if no previous prints:
    build prints from new_tree
    return new_tree (full first render)

  diff, new_prints = diff_tree(new_tree, old_prints)
  store new_prints
  return diff

diff_tree(new_tree, old_prints):
  new_rollup = compute_rollup(new_tree)
  if new_rollup == old_prints.fingerprint:
    return {}, old_prints              # O(1) skip — nothing changed

  # something changed — walk keys to find what
  diff = {}
  new_children = {}

  for key in new_tree:
    new_val = new_tree[key]
    old_child = old_prints.children.get(key)

    # --- Case 1: Comprehension (dict with "s" + "d") ---
    if is_comprehension(new_val):

      # Case 1a: old was a string or component CID — structure changed
      if not isinstance(old_child, FingerprintNode):
        diff[key] = new_val
        new_children[key] = build_prints(new_val)
        continue

      has_stream = "stream" in new_val

      if has_stream:
        # Case 1b: Stream comprehension — always include stream ops
        comp_diff = {"stream": new_val["stream"]}
        if new_val["d"]:
          comp_diff["d"] = new_val["d"]
        new_s_hash = hash_val(new_val["s"])
        if new_s_hash != old_child.children.get("s"):
          comp_diff["s"] = new_val["s"]
        diff[key] = comp_diff
        new_children[key] = build_prints(new_val)
        continue

      # Case 1c: Regular comprehension
      new_s_hash = hash_val(new_val["s"])
      new_d_hash = hash_val(new_val["d"])
      old_s_hash = old_child.children.get("s")
      old_d_hash = old_child.children.get("d")

      if new_s_hash != old_s_hash:
        diff[key] = {"s": new_val["s"], "d": new_val["d"]}
      elif new_d_hash != old_d_hash:
        diff[key] = {"d": new_val["d"]}

      new_children[key] = FingerprintNode(
        fingerprint=hash_val(new_val),
        children={"s": new_s_hash, "d": new_d_hash},
      )

    # --- Case 2: Stream-only dict (has "stream" but no "s"/"d") ---
    elif isinstance(new_val, dict) and "stream" in new_val:
      diff[key] = new_val
      new_children[key] = build_prints(new_val)

    # --- Case 3: Stream → empty string transition ---
    elif new_val == "" and isinstance(old_child, FingerprintNode):
      # Don't report as change — client already has stream content
      # (Phoenix LiveView semantics: stream items persist on client)
      new_children[key] = hash_val(new_val)

    # --- Case 4: Regular nested dict ---
    elif isinstance(new_val, dict):
      if isinstance(old_child, FingerprintNode):
        child_diff, child_prints = diff_tree(new_val, old_child)
        if child_diff:
          diff[key] = child_diff
        new_children[key] = child_prints
      else:
        # Structure changed (e.g. leaf → dict)
        diff[key] = new_val
        new_children[key] = build_prints(new_val)

    # --- Case 5: Leaf value ---
    else:
      new_hash = hash_val(new_val)
      if new_hash != old_child:
        diff[key] = new_val
      new_children[key] = new_hash

  return diff, FingerprintNode(compute_rollup(new_tree), new_children)
```

Note: `is_comprehension(val)` checks `isinstance(val, dict) and "s" in val and "d" in val`, matching the condition on line 9 of the existing `calc_diff`.

Keys present in old_prints but absent from the new tree are intentionally not included in the diff, matching existing `calc_diff` behavior. The fingerprint tree is rebuilt from the new tree's keys only.

### Key Behaviors

| Scenario | Behavior |
|----------|----------|
| Unchanged subtree | Rollup matches → skip in O(1), empty diff |
| Leaf value change | Hash differs → include new value |
| Statics change (`"s"`) in comprehension | Statics hash differs → include both `"s"` and `"d"` |
| Dynamics change (`"d"`) in comprehension | Dynamics hash differs → include only `"d"` |
| Stream comprehension | Always include `"stream"` ops, `"d"` if non-empty, `"s"` if changed |
| Stream-only dict (no `"s"`/`"d"`) | Always include full value |
| Stream → empty string | Suppress — client retains stream content |
| Structure change (str → dict, int → dict) | Include full new value, rebuild prints |
| New key in tree | No old hash → always included |
| Key removed from tree | Not included in diff (matching existing behavior) |
| Component containers (`"c"`) | Diffed via generic nested-dict recursion (Case 4) |
| Unknown/future keys (e.g. `"k"`) | Fall through to leaf (Case 5) or nested dict (Case 4) |

### Compatibility Wrapper

```python
def checksum_calc_diff(
    old_tree: dict[str, Any], new_tree: dict[str, Any]
) -> dict[str, Any]:
    """Drop-in replacement for calc_diff using checksum engine.

    Creates an engine, pushes the old tree (establishes baseline),
    then pushes the new tree (returns the diff).
    """
    engine = ChecksumDiffEngine()
    engine.push(old_tree)
    return engine.push(new_tree)
```

Note: `_build_prints({})` produces `FingerprintNode(fingerprint=hash_of_empty, children={})`, so diffing against it naturally includes all keys from the new tree (every key is "new").

## Test Strategy

### Phase 1: Validate Against Existing Tests

Run all existing test cases through both engines and assert identical output:

- `tests/template/test_diff.py` (17 tests) — basic diffs, conditionals, loops, component transitions
- `tests/template/test_stream_diff.py` (19 tests) — stream operations, combined ops, edge cases

New file `test_checksum_diff.py` imports the same test scenarios and runs them through `checksum_calc_diff`, asserting identical results. Existing test files are not modified.

### Phase 2: Checksum-Specific Tests

- **Multi-push sequences**: push 3+ trees through the engine, verify each diff is correct
- **Fingerprint tree compactness**: verify the stored state is `FingerprintNode`s and ints, not full values
- **Rollup skip verification**: push the same tree twice, verify second push returns `{}` (empty diff)
- **Structure transitions**: value → dict, dict → value, comprehension → stream

## File Layout

```
pyview/template/
├── render_diff.py              # existing, untouched
├── checksum_diff.py            # NEW: ChecksumDiffEngine, FingerprintNode, checksum_calc_diff

tests/template/
├── test_diff.py                # existing, untouched
├── test_stream_diff.py         # existing, untouched
├── test_checksum_diff.py       # NEW: tests for checksum engine
```

## What This Doesn't Change

- `render_diff.py` / `calc_diff()` — untouched
- `ConnectedLiveViewSocket.diff()` — still uses `prev_rendered` + `calc_diff`
- Template compilation (ibis / tstring) — no changes
- Wire format — identical output
- Stream handling — same semantics

## Future Path

1. **`DiffStrategy` protocol** — wrap both engines behind a common interface
2. **Socket integration** — `ConnectedLiveViewSocket` picks strategy via configuration
3. **Parallel verification** — run both engines simultaneously, compare results, log discrepancies
4. **Configuration knobs** — depth limits, size thresholds (skip diffing for large/deep subtrees)
5. **Assign-level change tracking** — `__changed__` map would enable statics-only fingerprinting like Phoenix
