from typing import Any


def calc_diff(old_tree: dict[str, Any], new_tree: dict[str, Any]) -> dict[str, Any]:
    diff = {}
    for key in new_tree:
        if key not in old_tree:
            diff[key] = new_tree[key]
        elif (
            isinstance(new_tree[key], dict)
            and "s" in new_tree[key]
            and ("d" in new_tree[key] or "k" in new_tree[key])
        ):
            if isinstance(old_tree[key], str):
                diff[key] = new_tree[key]
                continue

            # Handle special case of for loop (regular or keyed comprehension)
            old_static = old_tree[key].get("s", [])
            new_static = new_tree[key]["s"]

            # Check if it's a keyed comprehension (streams) or regular
            is_keyed = "k" in new_tree[key]
            dynamic_key = "k" if is_keyed else "d"

            old_dynamic = old_tree[key].get(dynamic_key, [])
            new_dynamic = new_tree[key][dynamic_key]

            if old_static != new_static:
                diff[key] = {"s": new_static, dynamic_key: new_dynamic}
                continue

            if old_dynamic != new_dynamic:
                diff[key] = {dynamic_key: new_dynamic}

        elif isinstance(new_tree[key], dict) and isinstance(old_tree[key], dict):
            nested_diff = calc_diff(old_tree[key], new_tree[key])
            if nested_diff:
                diff[key] = nested_diff
        elif old_tree[key] != new_tree[key]:
            diff[key] = new_tree[key]

    return diff
