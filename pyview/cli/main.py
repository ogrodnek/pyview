import click

from pyview.cli.commands.create_view import create_view
from pyview.cli.commands.freeze import freeze


@click.group()
@click.version_option(package_name="pyview-web")
def cli():
    """PyView CLI - Generate boilerplate for LiveView applications."""
    pass


cli.add_command(create_view)
cli.add_command(freeze)


if __name__ == "__main__":
    cli()
