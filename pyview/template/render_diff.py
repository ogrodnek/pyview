from typing import Any


def calc_diff(old_tree: dict[str, Any], new_tree: dict[str, Any]) -> dict[str, Any]:
    diff = {}
    for key in new_tree:
        if key not in old_tree:
            diff[key] = new_tree[key]
        elif isinstance(new_tree[key], dict) and "s" in new_tree[key] and "d" in new_tree[key]:
            if isinstance(old_tree[key], str):
                diff[key] = new_tree[key]
                continue

            # Handle special case of for loop (comprehension)
            old_static = old_tree[key].get("s", [])
            new_static = new_tree[key]["s"]

            old_dynamic = old_tree[key].get("d", [])
            new_dynamic = new_tree[key]["d"]

            # Check for stream metadata - always include if present
            has_stream = "stream" in new_tree[key]

            if has_stream:
                # For streams, always include the stream operations
                # The stream metadata contains insert/delete operations since last render
                comp_diff: dict[str, Any] = {"stream": new_tree[key]["stream"]}

                # Include dynamics if there are items being inserted
                if new_dynamic:
                    comp_diff["d"] = new_dynamic

                # Include statics on first render or if changed
                if old_static != new_static:
                    comp_diff["s"] = new_static

                diff[key] = comp_diff
                continue

            # Regular comprehension (non-stream)
            if old_static != new_static:
                diff[key] = {"s": new_static, "d": new_dynamic}
                continue

            if old_dynamic != new_dynamic:
                diff[key] = {"d": new_dynamic}

        elif isinstance(new_tree[key], dict) and "stream" in new_tree[key]:
            # Handle stream-only diff (no "s" or "d", just stream operations like delete-only)
            diff[key] = new_tree[key]

        elif new_tree[key] == "" and isinstance(old_tree[key], dict) and "stream" in old_tree[key]:
            # Stream went from having items to no pending operations
            # Don't report this as a change - client already has the content
            # This is Phoenix LiveView semantics: stream items persist on client
            pass

        elif isinstance(new_tree[key], dict) and isinstance(old_tree[key], dict):
            nested_diff = calc_diff(old_tree[key], new_tree[key])
            if nested_diff:
                diff[key] = nested_diff
        elif old_tree[key] != new_tree[key]:
            diff[key] = new_tree[key]

    return diff
