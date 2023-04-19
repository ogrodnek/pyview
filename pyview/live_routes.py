from pyview.live_view import LiveView
from typing import Callable


class LiveViewLookup:
    def __init__(self):
        self.routes = {}

    def add(self, path: str, lv: Callable[[], LiveView]):
        self.routes[path] = lv

    def get(self, path: str) -> LiveView:
        lv = self.routes.get(path)
        if not lv and path.endswith("/"):
            lv = self.routes[path[:-1]]

        if not lv:
            raise ValueError("No LiveView found for path: " + path)

        return lv()
