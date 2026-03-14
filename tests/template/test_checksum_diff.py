from dataclasses import dataclass as dc

from pyview.stream import Stream
from pyview.template.checksum_diff import (
    ChecksumDiffEngine,
    FingerprintNode,
    _build_prints,
    _hash_val,
    checksum_calc_diff,
)
from pyview.template.render_diff import calc_diff
from pyview.vendor.ibis import Template


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
        diff = engine.push(
            {"s": ["<div>", "</div>"], "0": {"s": ["<span>", "</span>"], "0": "goodbye"}}
        )
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
        engine.push(
            {
                "s": ["<div>", " long content here ", "</div>"],
                "0": "a very long dynamic string value",
                "1": {"s": ["<span>", "</span>"], "0": "nested value"},
            }
        )

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
        diff = engine.push(
            {"s": ["<div>", "</div>"], "0": {"s": ["<span>", "</span>"], "0": "nested"}}
        )
        assert diff == {"0": {"s": ["<span>", "</span>"], "0": "nested"}}

    def test_structure_transition_dict_to_leaf(self):
        engine = ChecksumDiffEngine()
        engine.push({"s": ["<div>", "</div>"], "0": {"s": ["<span>", "</span>"], "0": "nested"}})
        diff = engine.push({"s": ["<div>", "</div>"], "0": ""})
        assert diff == {"0": ""}

    def test_stream_to_empty_suppressed(self):
        """Stream → empty string should NOT produce a diff (client retains content)."""
        old = {
            "s": ["<ul>", "</ul>"],
            "0": {
                "s": ["<li>", "</li>"],
                "d": [["Alice"]],
                "stream": ["users", [["users-1", -1, None]], []],
            },
        }
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
