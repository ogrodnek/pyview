"""Statics and dynamics must strictly alternate in the diff tree.

The client rebuilds markup as s[0] + d[0] + s[1] + d[1] + ... + s[-1], so a
template that emits two statics in a row silently shifts everything after it:
the connected render loses content that the first HTTP render showed. Template
comments trigger this, because they split one run of text into two TextNodes.
"""

import pytest

from pyview.vendor.ibis import Template


def assemble(tree: dict) -> str:
    """Rebuild the markup the way the LiveView JS client does."""
    statics = tree["s"]
    out = []
    for i in range(len(statics) - 1):
        out.append(statics[i])
        dynamic = tree.get(str(i), "")
        out.append(assemble(dynamic) if isinstance(dynamic, dict) else str(dynamic))
    out.append(statics[-1])
    return "".join(out)


@pytest.mark.parametrize(
    "source,context",
    [
        ("A{{x}}B", {"x": "1"}),
        ("A{# comment #}B{{x}}C", {"x": "1"}),
        ("{# lead #}A{{x}}{# mid #}B{{y}}{# tail #}", {"x": "1", "y": "2"}),
        ("A{% if f %}Y{% endif %}B{{x}}C", {"x": "1", "f": False}),
        ("{# only a comment #}", {}),
        ("A{# c1 #}{# c2 #}B{{x}}", {"x": "1"}),
    ],
)
def test_tree_assembles_to_the_same_string_as_render(source, context):
    template = Template(source)
    tree = template.tree(context)

    assert len(tree["s"]) == len([k for k in tree if k != "s"]) + 1
    assert assemble(tree) == template.render(context)
