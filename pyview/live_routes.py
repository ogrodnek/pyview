from collections import defaultdict
from typing import Any, Callable

from starlette.routing import compile_path

from pyview.live_view import LiveView


class LiveViewLookup:
    def __init__(self):
        self.routes = []  # [(path_format, path_regex, param_convertors, lv, action)]
        self._action_groups: dict[type[LiveView], set[str]] = defaultdict(set)

    def add(self, path: str, lv: Callable[[], LiveView], action: str | None = None):
        path_regex, path_format, param_convertors = compile_path(path)
        self.routes.append((path_format, path_regex, param_convertors, lv, action))

        # Track action groups for same-class detection
        if action is not None:
            self._action_groups[lv].add(path_format)

    def get(self, path: str) -> tuple[LiveView, dict[str, Any], str | None]:
        # Find all matching routes
        matches = []

        for _path_format, path_regex, param_convertors, lv, action in self.routes:
            match_obj = path_regex.match(path)
            if match_obj is not None:
                params = match_obj.groupdict()

                # Convert path params using Starlette's convertors
                for param_name, convertor in param_convertors.items():
                    if param_name in params:
                        params[param_name] = convertor.convert(params[param_name])

                # Store the match with its priority information
                has_params = bool(param_convertors)
                matches.append((lv, params, has_params, action))

        # Sort matches by priority: static routes (has_params=False) come first
        matches.sort(key=lambda x: x[2])  # Sort by has_params (False comes before True)

        if matches:
            lv, params, _, action = matches[0]
            return lv(), params, action

        # Check for trailing slash
        if path.endswith("/"):
            try:
                return self.get(path[:-1])
            except ValueError:
                pass

        # No matches found
        raise ValueError(f"No LiveView found for path: {path}")

    def is_same_action_group(self, lv_class: type[LiveView], path: str) -> bool:
        """Check if a path belongs to the same action group as the given LiveView class."""
        if lv_class not in self._action_groups:
            return False

        # Find the route for the given path
        for path_format, path_regex, _, lv, action in self.routes:
            if path_regex.match(path) and action is not None:
                return lv == lv_class

        return False
