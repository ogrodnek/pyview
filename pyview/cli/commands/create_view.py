import click
from pathlib import Path
import tomllib
from typing import Optional


def snake_case(name: str) -> str:
    """Convert PascalCase or camelCase to snake_case."""
    import re

    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def pascal_case(name: str) -> str:
    """Convert snake_case or other formats to PascalCase."""
    # If already in PascalCase or camelCase, convert to snake_case first
    snake_name = snake_case(name)
    return "".join(word.capitalize() for word in snake_name.split("_"))


def kebab_case(name: str) -> str:
    """Convert any case to kebab-case."""
    return snake_case(name).replace("_", "-")


def generate_python_file(name: str) -> str:
    """Generate the Python LiveView file content."""
    class_name = f"{pascal_case(name)}LiveView"
    context_name = f"{pascal_case(name)}Context"

    return f"""from pyview import LiveView, LiveViewSocket
from dataclasses import dataclass
from pyview.events import event, BaseEventHandler


@dataclass
class {context_name}:
    pass


class {class_name}(BaseEventHandler, LiveView[{context_name}]):
    async def mount(self, socket: LiveViewSocket[{context_name}], session):
        socket.context = {context_name}()
"""


def generate_html_file(name: str) -> str:
    """Generate the HTML template file content."""
    css_class = kebab_case(name)
    return f'''<div class="{css_class}-container">
    <h1>{pascal_case(name)}</h1>
    
    <div class="content">
        <!-- Add your content here -->
    </div>
</div>
'''


def generate_css_file(name: str) -> str:
    """Generate the CSS file content."""
    css_class = kebab_case(name)
    return f""".{css_class}-container {{
    padding: 1rem;
}}

.{css_class}-container h1 {{
    margin-bottom: 1rem;
}}

.{css_class}-container .content {{
    /* Add your styles here */
}}
"""


def generate_init_file(name: str) -> str:
    """Generate the __init__.py file content."""
    module_name = snake_case(name)
    class_name = f"{pascal_case(name)}LiveView"

    return f'''from .{module_name} import {class_name}

__all__ = ["{class_name}"]
'''


def detect_package_structure(directory: Optional[Path] = None):
    """Detect the package structure from pyproject.toml.

    Args:
        directory: Directory to look for pyproject.toml in. Defaults to current directory.

    Returns:
        tuple: (package_name, views_path)
    """
    if directory is None:
        directory = Path.cwd()

    pyproject_path = directory / "pyproject.toml"

    if not pyproject_path.exists():
        return None, "views"

    try:
        with open(pyproject_path, "rb") as f:
            config = tomllib.load(f)
    except Exception:
        return None, "views"

    # Check for packages configuration
    packages = config.get("tool", {}).get("poetry", {}).get("packages", [])
    if not packages:
        # Check for modern pyproject.toml structure
        packages = config.get("project", {}).get("packages", [])

    if not packages:
        return None, "views"

    # Find the first package entry
    for package in packages:
        if isinstance(package, dict) and "include" in package:
            package_name = package["include"]
            from_dir = package.get("from", ".")

            # Construct the path where views should go
            if from_dir == ".":
                package_path = Path(package_name)
            else:
                package_path = Path(from_dir) / package_name

            views_path = package_path / "views"
            return package_name, str(views_path)

    return None, "views"


@click.command()
@click.argument("name")
@click.option(
    "--path",
    "-p",
    default=None,
    help="Directory to create the view in (default: auto-detect from pyproject.toml)",
)
@click.option("--no-css", is_flag=True, help="Skip creating CSS file")
def create_view(name: str, path: Optional[str], no_css: bool):
    """Create a new LiveView with boilerplate files.

    Example: pv create-view Counter
    """
    module_name = snake_case(name)

    # Always try to detect package structure for import advice
    package_name, detected_path = detect_package_structure()

    # Use detected path if no path specified, otherwise use provided path
    if path is None:
        path = detected_path

    view_dir = Path(path) / module_name

    # Check if directory already exists
    if view_dir.exists():
        click.secho(f"Error: Directory '{view_dir}' already exists", fg="red")
        raise click.Abort()

    view_dir.mkdir(parents=True, exist_ok=True)
    click.secho(f"Created directory: {view_dir}", fg="green")

    # Generate files
    files_to_create = [
        ("__init__.py", generate_init_file(name)),
        (f"{module_name}.py", generate_python_file(name)),
        (f"{module_name}.html", generate_html_file(name)),
    ]

    if not no_css:
        files_to_create.append((f"{module_name}.css", generate_css_file(name)))

    # Create files
    for filename, content in files_to_create:
        file_path = view_dir / filename
        file_path.write_text(content)
        click.secho(f"Created: {file_path}", fg="green")

    class_name = f"{pascal_case(name)}LiveView"
    click.echo("\nLiveView created successfully! 🎉")
    click.echo("\nTo use this view, add it to your app:")

    # import statement based on detected package structure
    if package_name:
        import_path = f"{package_name}.views.{module_name}"
    else:
        import_path = f"{path.replace('/', '.')}.{module_name}"

    click.echo(f"  from {import_path} import {class_name}")
    click.echo(f"  app.add_live_view('/{module_name}', {class_name})")
