from pyview.live_view import LiveView
from typing import Callable, Any
from starlette.routing import compile_path


class LiveViewLookup:
    def __init__(self):
        self.routes = []  # [(path_format, path_regex, param_convertors, lv)]

    def add(self, path: str, lv: Callable[[], LiveView]):
        path_regex, path_format, param_convertors = compile_path(path)
        self.routes.append((path_format, path_regex, param_convertors, lv))

    def get(self, path: str) -> tuple[LiveView, dict[str, Any]]:
        # Find all matching routes
        matches = []

        for path_format, path_regex, param_convertors, lv in self.routes:
            match_obj = path_regex.match(path)
            if match_obj is not None:
                params = match_obj.groupdict()

                # Convert path params using Starlette's convertors
                for param_name, convertor in param_convertors.items():
                    if param_name in params:
                        params[param_name] = convertor.convert(params[param_name])

                # Store the match with its priority information
                has_params = bool(param_convertors)
                matches.append((lv, params, has_params))

        # Sort matches by priority: static routes (has_params=False) come first
        matches.sort(key=lambda x: x[2])  # Sort by has_params (False comes before True)

        if matches:
            lv, params, _ = matches[0]
            return lv(), params

        # Check for trailing slash
        if path.endswith("/"):
            try:
                return self.get(path[:-1])
            except ValueError:
                pass

        # No matches found
        raise ValueError(f"No LiveView found for path: {path}")
