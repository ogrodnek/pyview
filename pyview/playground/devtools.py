import inspect
import json
import uuid
from pathlib import Path

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

PYVIEW_WORKSPACE_NAMESPACE = uuid.UUID("f47ac10b-58cc-4372-a567-0e02b2c3d479")


def get_workspace_uuid(path: str) -> str:
    """Generate a stable UUID for a given project path."""
    return str(uuid.uuid5(PYVIEW_WORKSPACE_NAMESPACE, path))


def devtools_json_response(project_root: str) -> dict:
    """
    Returns the JSON payload for /.well-known/appspecific/com.chrome.devtools.json
    """
    # Normalize to absolute path with forward slashes (Windows compat)
    root = Path(project_root).resolve().as_posix()

    return {"workspace": {"root": root, "uuid": get_workspace_uuid(root)}}


_LOCALHOST_HOSTS = ("localhost", "127.0.0.1", "::1")
_DEVTOOLS_PATH = "/.well-known/appspecific/com.chrome.devtools.json"
_PACKAGE_DIR = str(Path(__file__).parent.resolve())


def get_caller_directory() -> str:
    """Get the directory of the file that called playground()."""
    # Walk up the stack to find the first frame outside the playground package
    for frame_info in inspect.stack():
        if not str(Path(frame_info.filename).resolve()).startswith(_PACKAGE_DIR):
            return str(Path(frame_info.filename).parent.resolve())
    return str(Path.cwd())


def devtools_route(caller_dir: str) -> Route:
    """Create a Route for the Chrome DevTools workspace endpoint.

    Only responds to localhost requests to prevent information disclosure.
    """

    async def handler(request: Request) -> Response:
        host = request.url.hostname or ""
        if host not in _LOCALHOST_HOSTS:
            return Response(status_code=404)
        response = devtools_json_response(caller_dir)
        return Response(content=json.dumps(response), media_type="application/json")

    return Route(_DEVTOOLS_PATH, handler, methods=["GET"])
