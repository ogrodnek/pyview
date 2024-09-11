from pyview.vendor.ibis import Template
from pyview.template.render_diff import calc_diff


def test_simple_diff_no_changes():
    t = Template("<div>{% if greeting %}<span>{{greeting}}</span>{% endif %}</div>")
    assert calc_diff(t.tree({"greeting": "Hello"}), t.tree({"greeting": "Hello"})) == {}


def test_simple_diff():
    t = Template("<div>{% if greeting %}<span>{{greeting}}</span>{% endif %}</div>")

    hello = t.tree({"greeting": "Hello"})
    goodbye = t.tree({"greeting": "Goodbye"})

    assert calc_diff(hello, goodbye) == {"0": {"0": "Goodbye"}}


def test_conditional_diff():
    t = Template("<div>{% if greeting %}<span>{{greeting}}</span>{% endif %}</div>")

    hello = t.tree({"greeting": "Hello"})
    empty = t.tree({})

    # Going from hello to empty
    assert calc_diff(hello, empty) == {"0": ""}

    # Going from empty to hello
    assert calc_diff(empty, hello) == {"0": {"s": ["<span>", "</span>"], "0": "Hello"}}


def test_loop_diff():
    t = Template("<div>{% for item in items %}<span>{{item}}</span>{% endfor %}</div>")

    old = t.tree({"items": ["One", "Two", "Three"]})
    new = t.tree({"items": ["One", "Two", "Four"]})

    # diffs for loops always return all values, regardless of changes
    # at least, I *think* that's the right behavior based on some qick liveview testing
    assert calc_diff(old, new) == {"0": {"d": [["One"], ["Two"], ["Four"]]}}


def test_loop_diff_no_change():
    t = Template("<div>{% for item in items %}<span>{{item}}</span>{% endfor %}</div>")

    old = t.tree({"items": ["One", "Two", "Three"]})
    new = t.tree({"items": ["One", "Two", "Three"]})

    assert calc_diff(old, new) == {}


def test_loop_diff_empty_to_nonempty():
    t = Template("<div>{% for item in items %}<span>{{item}}</span>{% endfor %}</div>")

    old = t.tree({"items": []})
    new = t.tree({"items": ["One", "Two", "Three"]})

    assert calc_diff(old, new) == {
        "0": {"d": [["One"], ["Two"], ["Three"]], "s": ["<span>", "</span>"]}
    }


def test_loop_diff_nonempty_to_empty():
    t = Template("<div>{% for item in items %}<span>{{item}}</span>{% endfor %}</div>")

    old = t.tree({"items": ["One", "Two", "Three"]})
    new = t.tree({"items": []})

    assert calc_diff(old, new) == {"0": ""}


def test_loop_diff_size_change():
    t = Template("<div>{% for item in items %}<span>{{item}}</span>{% endfor %}</div>")

    old = t.tree({"items": ["One", "Two", "Three"]})
    new = t.tree({"items": ["One"]})

    assert calc_diff(old, new) == {"0": {"d": [["One"]]}}


def test_loop_diff_static_change():
    t = Template("<div>{% for item in items %}<span>{{item}}</span>{% endfor %}</div>")
    t2 = Template("<div>{% for item in items %}<div>{{item}}</div>{% endfor %}</div>")

    old = t.tree({"items": ["One", "Two", "Three"]})
    new = t2.tree({"items": ["One", "Two", "Three", "Four"]})

    assert calc_diff(old, new) == {
        "0": {"s": ["<div>", "</div>"], "d": [["One"], ["Two"], ["Three"], ["Four"]]}
    }


def test_diff_template_change():
    t = Template("<div><span>{{greeting}}</span></div>")
    t2 = Template(
        "<div>{% if greeting %}<span>{{greeting}}</span>{% endif %}<p>{{farewell}}</p></div>"
    )

    r1 = t.tree({"greeting": "Hello"})
    r2 = t2.tree({"greeting": "Hello", "farewell": "Goodbye"})

    assert calc_diff(r1, r2) == r2


def test_statics_only_change():
    t = Template("<div><span>{{greeting}}</span></div>")
    t2 = Template("<div>{{greeting}}</div>")

    r1 = t.tree({"greeting": "Hello"})
    r2 = t2.tree({"greeting": "Hello"})

    assert calc_diff(r1, r2) == {"s": ["<div>", "</div>"]}
