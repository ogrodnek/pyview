import asyncio
import importlib
import logging
import sys

import click


@click.command()
@click.option("--app", required=True, help="App import path, e.g. 'myapp:app' or 'myapp.main:app'")
@click.option("--output", "-o", default="./build", help="Output directory (default: ./build)")
@click.option(
    "--path",
    "-p",
    "paths",
    multiple=True,
    help="Specific path(s) to render. Can be repeated. If omitted, renders all static routes.",
)
@click.option("--screenshot", is_flag=True, help="Also capture PNG screenshots (requires playwright)")
@click.option("--clean-attrs", is_flag=True, help="Strip data-phx-* attributes from output HTML")
@click.option("-v", "--verbose", is_flag=True, help="Verbose logging")
def freeze(app, output, paths, screenshot, clean_attrs, verbose):
    """Render LiveView routes to static HTML files."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
    )

    # Import the app
    pyview_app = _import_app(app)

    from pyview.static import freeze as do_freeze  # noqa: PLC0415

    path_list = list(paths) if paths else None
    files = asyncio.run(
        do_freeze(pyview_app, output, paths=path_list, screenshot=screenshot)
    )

    if files:
        click.echo(f"\nFroze {len(files)} file(s) to {output}/")
    else:
        click.echo("No files generated.")


def _import_app(app_path: str):
    """Import a PyView app from a module:attribute path.

    Adds the current directory to sys.path so that both top-level modules
    (``app:app``) and package-relative modules (``mypackage.app:app``)
    resolve correctly when running from the project root.
    """
    if ":" not in app_path:
        raise click.BadParameter(
            f"Expected format 'module:attribute' (e.g. 'myapp:app'), got '{app_path}'",
            param_hint="--app",
        )

    module_path, attr_name = app_path.rsplit(":", 1)

    # Add cwd (as absolute path) to sys.path so top-level imports work
    import os  # noqa: PLC0415

    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    try:
        module = importlib.import_module(module_path)
    except ImportError as e:
        raise click.BadParameter(
            f"Could not import module '{module_path}': {e}\n"
            f"Hint: run from your project root, or use the full dotted path "
            f"(e.g. 'mypackage.app:app')",
        ) from e

    try:
        return getattr(module, attr_name)
    except AttributeError as e:
        raise click.BadParameter(
            f"Module '{module_path}' has no attribute '{attr_name}'"
        ) from e
