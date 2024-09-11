from pyview.vendor.ibis import Template
from markupsafe import Markup


def test_simple_substitution():
    a = Template("<div><span>{{greeting}}</span><span>{{name}}</span></div>")
    d = {"greeting": "Hello", "name": "Larry"}

    assert a.tree(d) == {
        "s": ["<div><span>", "</span><span>", "</span></div>"],
        "0": "Hello",
        "1": "Larry",
    }
    assert a.render(d) == "<div><span>Hello</span><span>Larry</span></div>"


def test_auto_escaping():
    a = Template("<div><span>{{greeting}}</span><span>{{name}}</span></div>")
    d = {"greeting": "Hello", "name": "<script>alert('XSS')</script>"}

    assert a.tree(d) == {
        "s": ["<div><span>", "</span><span>", "</span></div>"],
        "0": "Hello",
        "1": "&lt;script&gt;alert(&#39;XSS&#39;)&lt;/script&gt;",
    }
    assert (
        a.render(d)
        == "<div><span>Hello</span><span>&lt;script&gt;alert(&#39;XSS&#39;)&lt;/script&gt;</span></div>"
    )


def test_no_escaping():
    a = Template("<div><span>{{greeting}}</span><span>{{name}}</span></div>")
    d = {"greeting": "Hello", "name": Markup("<i>Larry</i>")}

    assert a.tree(d) == {
        "s": ["<div><span>", "</span><span>", "</span></div>"],
        "0": "Hello",
        "1": "<i>Larry</i>",
    }
    assert a.render(d) == "<div><span>Hello</span><span><i>Larry</i></span></div>"


def test_simple_if():
    a = Template("<div>{% if greeting %}<span>{{greeting}}</span>{% endif %}</div>")
    d = {"greeting": "Hello"}

    assert a.tree(d) == {
        "s": ["<div>", "</div>"],
        "0": {"s": ["<span>", "</span>"], "0": "Hello"},
    }
    assert a.render(d) == "<div><span>Hello</span></div>"

    d = {}

    assert a.tree(d) == {"s": ["<div>", "</div>"], "0": ""}
    assert a.render(d) == "<div></div>"


def test_multiple_ifs():
    a = Template(
        "<div>{% if greeting %}<span>{{greeting}}</span>{% endif %}{% if name %}<span>{{name}}</span>{% endif %}</div>"
    )

    d = {"greeting": "Hello", "name": "Larry"}

    #  ~H"<div><%= if @greeting do %><span><%= @greeting %></span><% end %><%= if @name do %><span><%= @name %></span><% end %></div>"
    assert a.tree(d) == {
        "0": {"0": "Hello", "s": ["<span>", "</span>"]},
        "1": {"0": "Larry", "s": ["<span>", "</span>"]},
        "s": ["<div>", "", "</div>"],
    }

    assert a.render(d) == "<div><span>Hello</span><span>Larry</span></div>"

    d = {"greeting": "Hello"}
    assert a.tree(d) == {
        "s": ["<div>", "", "</div>"],
        "0": {"s": ["<span>", "</span>"], "0": "Hello"},
        "1": "",
    }
    assert a.render(d) == "<div><span>Hello</span></div>"

    d = {"name": "Larry"}
    assert a.tree(d) == {
        "s": ["<div>", "", "</div>"],
        "0": "",
        "1": {"s": ["<span>", "</span>"], "0": "Larry"},
    }
    assert a.render(d) == "<div><span>Larry</span></div>"

    d = {}
    assert a.tree(d) == {"s": ["<div>", "", "</div>"], "0": "", "1": ""}
    assert a.render(d) == "<div></div>"


def test_loop():
    a = Template("<div>{% for v in users %}<span>{{v.name}}</span>{% endfor %}</div>")
    d = {"users": [{"name": "Larry"}, {"name": "Sally"}]}

    assert a.tree(d) == {
        "s": ["<div>", "</div>"],
        "0": {"s": ["<span>", "</span>"], "d": [["Larry"], ["Sally"]]},
    }
    assert a.render(d) == "<div><span>Larry</span><span>Sally</span></div>"


def test_loop_single_element():
    a = Template("<div>{% for v in users %}<span>{{v.name}}</span>{% endfor %}</div>")
    d = {"users": [{"name": "Larry"}]}

    assert a.tree(d) == {
        "s": ["<div>", "</div>"],
        "0": {"s": ["<span>", "</span>"], "d": [["Larry"]]},
    }
    assert a.render(d) == "<div><span>Larry</span></div>"


def test_loop_empty():
    a = Template("<div>{% for v in users %}<span>{{v.name}}</span>{% endfor %}</div>")

    d = {"users": []}
    assert a.tree(d) == {"s": ["<div>", "</div>"], "0": ""}
    assert a.render(d) == "<div></div>"


def test_contains_one_static_at_beginning_ane_one_dynamic():
    a = Template("Hello {{name}}")
    d = {"name": "World"}

    assert a.tree(d) == {"s": ["Hello ", ""], "0": "World"}
    assert a.render(d) == "Hello World"


def test_contains_one_static_at_end_and_one_dynamic():
    a = Template("{{greeting}} World")
    d = {"greeting": "Hello"}

    assert a.tree(d) == {"s": ["", " World"], "0": "Hello"}
    assert a.render(d) == "Hello World"


def test_contains_one_dynamic_only():
    a = Template("{{greeting}}")
    d = {"greeting": "Hello"}

    assert a.tree(d) == {"s": ["", ""], "0": "Hello"}
    assert a.render(d) == "Hello"


def test_contains_two_dynamics_only():
    a = Template("{{greeting}}{{name}}")
    d = {"greeting": "Hello", "name": "World"}

    assert a.tree(d) == {"s": ["", "", ""], "0": "Hello", "1": "World"}
    assert a.render(d) == "HelloWorld"


def test_contains_two_statics_and_two_dyanmics():
    a = Template("Hello {{first}}{{last}}!")
    d = {"first": "Jane", "last": "Smith"}

    assert a.tree(d) == {"s": ["Hello ", "", "!"], "0": "Jane", "1": "Smith"}
    assert a.render(d) == "Hello JaneSmith!"


# is this a real test case
def test_if_no_statics():
    a = Template("{% if display %}{{greeting}}{% endif %}")
    d = {"greeting": "Hello", "display": True}

    assert a.render(d) == "Hello"
    assert a.tree(d) == {"0": {"0": "Hello", "s": ["", ""]}, "s": ["", ""]}
