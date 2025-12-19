"""Components examples for pyview."""

import sys

if sys.version_info >= (3, 14):
    from .slots_demo import SlotsDemo
    from .stateful_demo import StatefulComponentsDemo
    from .stateless_demo import StatelessComponentsDemo

    __all__ = ["StatelessComponentsDemo", "StatefulComponentsDemo", "SlotsDemo"]
else:
    __all__ = []
