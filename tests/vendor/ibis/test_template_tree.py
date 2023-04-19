from pyview.vendor.ibis import Template
from pyview.vendor.ibis.tree import PartsTree


def test_simple_print():
    a = Template("{{greeting}}")
    d = {"greeting": "Hello"}

    # TODO not sure if this is right or if statics should be empty?
    assert a.tree_parts(d) == PartsTree(statics=["", ""], dynamics=["Hello"])
    assert a.render(d) == "Hello"
    assert a.tree_parts(d).render_parts() == {"0": "Hello", "s": ["", ""]}


def test_with_statics():
    a = Template("{{greeting}} World")
    d = {"greeting": "Hello"}

    assert a.tree_parts(d) == PartsTree(statics=["", " World"], dynamics=["Hello"])
    assert a.render(d) == "Hello World"


def test_with_statics_and_if():
    a = Template("{{greeting}} {% if display %}World{% endif %}")
    d = {"greeting": "Hello", "display": True}

    assert a.tree_parts(d) == PartsTree(
        statics=["", " ", ""], dynamics=["Hello", "World"]
    )
    assert a.render(d) == "Hello World"
