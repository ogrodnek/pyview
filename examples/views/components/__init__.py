"""Components examples for pyview."""

import sys

if sys.version_info >= (3, 14):
    from .stateless_demo import StatelessComponentsDemo

    __all__ = ["StatelessComponentsDemo"]
else:
    __all__ = []
