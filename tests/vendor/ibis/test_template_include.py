import pytest

import pyview.vendor.ibis as ibis
from pyview.vendor.ibis import Template
from pyview.vendor.ibis.loaders import DictLoader


@pytest.fixture
def template_loader():
    ibis.loader = DictLoader(
        {
            "header.html": "<p>{{gr}}, World!</p>",
        }
    )

def test_template_include(template_loader):
    a = Template("<div>{% include 'header.html' with gr=greeting %}</div>")
    d = {"greeting": "Hello"}

    assert a.tree(d) == {
        "s": ["<div>", "</div>"],
        "0": {"s": ["<p>", ", World!</p>"], "0": "Hello"},
    }
    assert a.render(d) == "<div><p>Hello, World!</p></div>"
