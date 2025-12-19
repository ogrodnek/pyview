"""
Slots support for LiveComponents.

Slots allow parent templates to pass content into component slots,
similar to React's children/slots or Phoenix LiveView's slots.

Usage:
    from pyview.components import live_component, slots

    # Default slot only
    live_component(Card, id="card-1", slots=slots(
        t"<p>This is the card body content</p>"
    ))

    # Named slots
    live_component(Card, id="card-1", slots=slots(
        t"<p>Default body content</p>",
        header=t"<h2>Card Title</h2>",
        footer=t"<button>Submit</button>"
    ))

    # In the component template
    class Card(LiveComponent[CardContext]):
        def template(self, assigns: CardContext, meta: ComponentMeta):
            return t'''
                <div class="card">
                    <header>{meta.slots['header']}</header>
                    <main>{meta.slots['default']}</main>
                    <footer>{meta.slots['footer']}</footer>
                </div>
            '''
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from string.templatelib import Template  # type: ignore[import-not-found]
    from typing import TypeAlias

    Slots: TypeAlias = dict[str, Template]
else:
    # Runtime: use Any to avoid import errors on Python < 3.14
    Slots = dict[str, Any]


def slots(__default: Template | None = None, **named: Template) -> Slots:
    """
    Create a slots dictionary for component children.

    Args:
        __default: The default/unnamed slot content (positional argument)
        **named: Named slots (header, footer, etc.)

    Returns:
        Dictionary mapping slot names to template content

    Examples:
        # Default slot only
        slots(t"<p>Body content</p>")

        # Named slots only
        slots(header=t"<h2>Title</h2>", footer=t"<button>OK</button>")

        # Both default and named slots
        slots(t"<p>Body</p>", header=t"<h2>Title</h2>")
    """
    result: Slots = {}
    if __default is not None:
        result["default"] = __default
    result.update(named)
    return result
