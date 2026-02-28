"""Static rendering for pyview LiveViews.

Renders registered LiveView routes to static HTML files, stripping
LiveView-specific JS/WebSocket machinery while preserving user scripts,
CSS, and web components.

Usage:
    import asyncio
    from pyview.static import freeze

    from myapp import app
    asyncio.run(freeze(app, "./build"))

Or via CLI:
    pv freeze --app myapp:app --output ./build
"""

import logging
import re
import shutil
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

from pyview.binding import call_handle_params, call_mount, create_view
from pyview.components.lifecycle import run_nested_component_lifecycle
from pyview.live_socket import UnconnectedSocket
from pyview.meta import PyViewMeta
from pyview.template import find_associated_css

logger = logging.getLogger(__name__)

# Matches the pyview LiveView client script tag
_PYVIEW_JS_RE = re.compile(
    r'<script[^>]*\bsrc="/static/assets/app\.js"[^>]*></script>\s*', re.IGNORECASE
)

# Matches data-phx-* attributes
_PHX_ATTR_RE = re.compile(r'\s+data-phx-[\w-]+="[^"]*"')

# Matches CSRF meta tag
_CSRF_META_RE = re.compile(r'<meta\s+name="csrf-token"[^>]*/?\s*>\s*', re.IGNORECASE)


def _clean_html(html: str, strip_phx_attrs: bool = False) -> str:
    """Strip LiveView-specific scripts from rendered HTML.

    Args:
        html: Raw HTML from the root template.
        strip_phx_attrs: If True, also remove data-phx-* attributes.
            These are inert without the LiveView JS client, so stripping
            is cosmetic. Defaults to False.
    """
    html = _PYVIEW_JS_RE.sub("", html)
    html = _CSRF_META_RE.sub("", html)
    if strip_phx_attrs:
        html = _PHX_ATTR_RE.sub("", html)
    return html


async def render_view(app, path: str) -> str:
    """Render a single LiveView route to static HTML.

    Runs the full LiveView lifecycle (mount → handle_params → render)
    using an unconnected socket, then strips LiveView-specific markup.

    Args:
        app: A PyView application instance.
        path: The URL path to render (e.g. "/" or "/counter").

    Returns:
        Clean static HTML string.
    """
    lv_class, path_params = app.view_lookup.get(path)

    session: dict = {}
    lv = create_view(lv_class, session)

    socket = UnconnectedSocket()
    await call_mount(lv, socket, session)
    await call_handle_params(lv, urlparse(path), path_params, socket)

    meta = PyViewMeta(socket=socket)
    rendered = await lv.render(socket.context, meta)
    await run_nested_component_lifecycle(socket, meta)

    content = rendered.text(socket=socket)
    liveview_css = find_associated_css(lv)

    # Build the page using the app's root template so user CSS/JS is preserved
    context = {
        "id": str(uuid.uuid4()),
        "content": content,
        "title": socket.live_title,
        "csrf_token": "",
        "session": "",
        "additional_head_elements": liveview_css,
    }

    html = app.rootTemplate(context)
    return _clean_html(html)


def _copy_static_assets(app, output_dir: Path) -> None:
    """Copy static file mounts into the build directory.

    Walks the app's routes looking for Starlette StaticFiles mounts and
    copies their directories into the output, preserving the URL prefix
    structure. For example, a mount at ``/app-static`` serving from
    ``./static`` will be copied to ``<output_dir>/app-static/``.
    """
    for route in app.routes:
        if not isinstance(route, Mount) or not isinstance(route.app, StaticFiles):
            continue

        prefix = route.path.strip("/")
        if not prefix:
            continue

        dest = output_dir / prefix
        for src_dir in route.app.all_directories:
            src = Path(src_dir)
            if not src.is_dir():
                continue
            logger.info("Copying static assets %s -> %s", src, dest)
            shutil.copytree(src, dest, dirs_exist_ok=True)


def _list_static_routes(app) -> list[str]:
    """List routes that can be statically rendered (no path parameters)."""
    paths = []
    for path_format, _regex, param_convertors, _lv in app.view_lookup.routes:
        if not param_convertors:
            paths.append(path_format)
    return sorted(paths)


async def freeze(
    app,
    output_dir: str,
    paths: Optional[list[str]] = None,
    screenshot: bool = False,
) -> list[Path]:
    """Render LiveView routes to static HTML files.

    Args:
        app: A PyView application instance.
        output_dir: Directory to write output files.
        paths: Specific paths to render. If None, renders all
               non-parameterized routes.
        screenshot: If True, also capture PNG screenshots (requires playwright).

    Returns:
        List of output file paths.
    """
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    if paths is None:
        paths = _list_static_routes(app)

    if not paths:
        logger.warning("No routes to render")
        return []

    output_files: list[Path] = []

    for path in paths:
        logger.info("Rendering %s", path)
        html = await render_view(app, path)

        # Convert path to filename: "/" -> "index.html", "/foo" -> "foo.html"
        name = path.strip("/")
        if not name:
            name = "index"
        name = name.replace("/", "_")

        html_path = output / f"{name}.html"
        html_path.write_text(html)
        output_files.append(html_path)
        logger.info("  -> %s", html_path)

    # Copy static file mounts (CSS, JS, images, etc.)
    _copy_static_assets(app, output)

    if screenshot:
        screenshot_files = await _capture_screenshots(output_files, output)
        output_files.extend(screenshot_files)

    return output_files


async def _capture_screenshots(html_files: list[Path], output_dir: Path) -> list[Path]:
    """Capture PNG screenshots of HTML files using playwright."""
    try:
        from playwright.async_api import async_playwright  # noqa: PLC0415
    except ImportError:
        logger.warning(
            "playwright not installed — skipping screenshots. "
            "Install with: pip install playwright && playwright install chromium"
        )
        return []

    screenshots: list[Path] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 720})

        for html_file in html_files:
            url = html_file.resolve().as_uri()
            await page.goto(url)
            # Give JS a moment to execute (Tailwind, web components, etc.)
            await page.wait_for_timeout(1000)

            png_path = output_dir / f"{html_file.stem}.png"
            await page.screenshot(path=str(png_path), full_page=True)
            screenshots.append(png_path)
            logger.info("  -> %s", png_path)

        await browser.close()

    return screenshots
