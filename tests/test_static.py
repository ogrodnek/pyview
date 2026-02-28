"""Tests for pyview.static — static rendering of LiveView routes."""

from dataclasses import dataclass
from pathlib import Path

from starlette.staticfiles import StaticFiles

from pyview import LiveView, LiveViewSocket, PyView
from pyview.meta import PyViewMeta
from pyview.static import _clean_html, _copy_static_assets, _list_static_routes, freeze, render_view
from pyview.template import LiveRender, LiveTemplate, RenderedContent
from pyview.vendor.ibis import Template

# ---------------------------------------------------------------------------
# Test views
# ---------------------------------------------------------------------------


@dataclass
class CountContext:
    count: int = 0


class CountView(LiveView[CountContext]):
    async def mount(self, socket: LiveViewSocket[CountContext], session):
        socket.context = CountContext(count=42)

    async def render(self, assigns: CountContext, meta: PyViewMeta) -> RenderedContent:
        t = LiveTemplate(Template("<div>Count: {{ count }}</div>"))
        return LiveRender(t, assigns, meta)


@dataclass
class HelloContext:
    name: str = "world"


class HelloView(LiveView[HelloContext]):
    async def mount(self, socket: LiveViewSocket[HelloContext], session):
        socket.context = HelloContext(name="pyview")

    async def render(self, assigns: HelloContext, meta: PyViewMeta) -> RenderedContent:
        t = LiveTemplate(Template("<h1>Hello {{ name }}!</h1>"))
        return LiveRender(t, assigns, meta)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(*routes: tuple[str, type]) -> PyView:
    app = PyView()
    for path, view in routes:
        app.add_live_view(path, view)
    return app


# ---------------------------------------------------------------------------
# _clean_html
# ---------------------------------------------------------------------------


class TestCleanHtml:
    def test_strips_app_js(self):
        html = '<script defer type="text/javascript" src="/static/assets/app.js"></script>'
        assert "app.js" not in _clean_html(html)

    def test_strips_csrf_meta(self):
        html = '<meta name="csrf-token" content="abc123" />'
        assert "csrf-token" not in _clean_html(html)

    def test_preserves_user_scripts(self):
        html = '<script src="https://cdn.tailwindcss.com"></script>'
        assert _clean_html(html) == html

    def test_preserves_user_meta(self):
        html = '<meta name="viewport" content="width=device-width">'
        assert _clean_html(html) == html

    def test_strip_phx_attrs_off_by_default(self):
        html = '<div data-phx-main="true" data-phx-session="abc">hi</div>'
        assert "data-phx-main" in _clean_html(html)

    def test_strip_phx_attrs_when_enabled(self):
        html = '<div data-phx-main="true" data-phx-session="abc">hi</div>'
        result = _clean_html(html, strip_phx_attrs=True)
        assert "data-phx-main" not in result
        assert "data-phx-session" not in result
        assert ">hi</div>" in result


# ---------------------------------------------------------------------------
# _list_static_routes
# ---------------------------------------------------------------------------


class TestListStaticRoutes:
    def test_lists_non_parameterized_routes(self):
        app = _make_app(("/", CountView), ("/hello", HelloView))
        routes = _list_static_routes(app)
        assert routes == ["/", "/hello"]

    def test_excludes_parameterized_routes(self):
        app = _make_app(("/", CountView), ("/users/{id}", HelloView))
        routes = _list_static_routes(app)
        assert routes == ["/"]

    def test_empty_app(self):
        app = PyView()
        assert _list_static_routes(app) == []


# ---------------------------------------------------------------------------
# render_view
# ---------------------------------------------------------------------------


class TestRenderView:
    async def test_renders_view_html(self):
        app = _make_app(("/", CountView))
        html = await render_view(app, "/")
        assert "Count: 42" in html

    async def test_html_is_full_page(self):
        app = _make_app(("/", CountView))
        html = await render_view(app, "/")
        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "</html>" in html

    async def test_no_app_js_in_output(self):
        app = _make_app(("/", CountView))
        html = await render_view(app, "/")
        assert "app.js" not in html

    async def test_no_csrf_in_output(self):
        app = _make_app(("/", CountView))
        html = await render_view(app, "/")
        assert "csrf-token" not in html

    async def test_renders_different_views(self):
        app = _make_app(("/", CountView), ("/hello", HelloView))
        html = await render_view(app, "/hello")
        assert "Hello pyview!" in html


# ---------------------------------------------------------------------------
# freeze
# ---------------------------------------------------------------------------


class TestFreeze:
    async def test_writes_html_files(self, tmp_path: Path):
        app = _make_app(("/", CountView), ("/hello", HelloView))
        files = await freeze(app, str(tmp_path))

        assert len(files) == 2
        assert (tmp_path / "index.html").exists()
        assert (tmp_path / "hello.html").exists()

    async def test_file_contents(self, tmp_path: Path):
        app = _make_app(("/", CountView))
        await freeze(app, str(tmp_path))

        html = (tmp_path / "index.html").read_text()
        assert "Count: 42" in html
        assert "<!DOCTYPE html>" in html

    async def test_creates_output_dir(self, tmp_path: Path):
        output = tmp_path / "nested" / "build"
        app = _make_app(("/", CountView))
        await freeze(app, str(output))
        assert output.exists()

    async def test_explicit_paths(self, tmp_path: Path):
        app = _make_app(("/", CountView), ("/hello", HelloView))
        files = await freeze(app, str(tmp_path), paths=["/hello"])

        assert len(files) == 1
        assert (tmp_path / "hello.html").exists()
        assert not (tmp_path / "index.html").exists()

    async def test_no_routes_returns_empty(self, tmp_path: Path):
        app = PyView()
        files = await freeze(app, str(tmp_path))
        assert files == []

    async def test_nested_path_naming(self, tmp_path: Path):
        app = _make_app(("/docs/guide", CountView))
        await freeze(app, str(tmp_path), paths=["/docs/guide"])
        assert (tmp_path / "docs_guide.html").exists()

    async def test_copies_static_assets(self, tmp_path: Path):
        # Set up a fake static directory with a CSS file
        static_src = tmp_path / "src_static"
        static_src.mkdir()
        (static_src / "styles.css").write_text("body { color: red; }")
        (static_src / "app.js").write_text("console.log('hi')")

        app = _make_app(("/", CountView))
        app.mount("/app-static", StaticFiles(directory=str(static_src)), name="app-static")

        build = tmp_path / "build"
        await freeze(app, str(build))

        # Static assets should be copied under the mount prefix
        assert (build / "app-static" / "styles.css").exists()
        assert (build / "app-static" / "app.js").exists()
        assert (build / "app-static" / "styles.css").read_text() == "body { color: red; }"


# ---------------------------------------------------------------------------
# _copy_static_assets
# ---------------------------------------------------------------------------


class TestCopyStaticAssets:
    def test_copies_directory_mount(self, tmp_path: Path):
        static_src = tmp_path / "static"
        static_src.mkdir()
        (static_src / "main.css").write_text(".a{}")

        app = PyView()
        app.mount("/assets", StaticFiles(directory=str(static_src)), name="assets")

        output = tmp_path / "build"
        output.mkdir()
        _copy_static_assets(app, output)

        assert (output / "assets" / "main.css").exists()
        assert (output / "assets" / "main.css").read_text() == ".a{}"

    def test_copies_nested_files(self, tmp_path: Path):
        static_src = tmp_path / "static"
        (static_src / "sub").mkdir(parents=True)
        (static_src / "sub" / "deep.js").write_text("// deep")

        app = PyView()
        app.mount("/static", StaticFiles(directory=str(static_src)), name="static")

        output = tmp_path / "build"
        output.mkdir()
        _copy_static_assets(app, output)

        assert (output / "static" / "sub" / "deep.js").read_text() == "// deep"

    def test_skips_non_staticfiles_mounts(self, tmp_path: Path):
        app = _make_app(("/", CountView))
        output = tmp_path / "build"
        output.mkdir()
        # Should not crash when there are no StaticFiles mounts
        _copy_static_assets(app, output)
