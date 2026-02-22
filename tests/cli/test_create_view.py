import shutil
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from pyview.cli.commands.create_view import detect_package_structure, normalize_project_name
from pyview.cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def temp_dir():
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


def test_create_view_basic(runner, temp_dir):
    """Test creating a basic view with all files."""
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["create-view", "Counter"])

        assert result.exit_code == 0
        assert "LiveView created successfully!" in result.output

        # Check that all files were created
        view_dir = Path("views/counter")
        assert view_dir.exists()
        assert (view_dir / "__init__.py").exists()
        assert (view_dir / "counter.py").exists()
        assert (view_dir / "counter.html").exists()
        assert (view_dir / "counter.css").exists()

        # Check Python file content
        py_content = (view_dir / "counter.py").read_text()
        assert "class CounterContext:" in py_content
        assert "class CounterLiveView(BaseEventHandler, LiveView[CounterContext]):" in py_content
        assert (
            "async def mount(self, socket: LiveViewSocket[CounterContext], session):" in py_content
        )
        assert "socket.context = CounterContext()" in py_content


def test_create_view_no_css(runner, temp_dir):
    """Test creating a view without CSS file."""
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["create-view", "Counter", "--no-css"])

        assert result.exit_code == 0

        view_dir = Path("views/counter")
        assert view_dir.exists()
        assert (view_dir / "__init__.py").exists()
        assert (view_dir / "counter.py").exists()
        assert (view_dir / "counter.html").exists()
        assert not (view_dir / "counter.css").exists()


def test_create_view_custom_path(runner, temp_dir):
    """Test creating a view in a custom directory."""
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["create-view", "MyView", "--path", "custom/views"])

        assert result.exit_code == 0

        view_dir = Path("custom/views/my_view")
        assert view_dir.exists()
        assert (view_dir / "my_view.py").exists()


def test_create_view_already_exists(runner, temp_dir):
    """Test error when view directory already exists."""
    with runner.isolated_filesystem():
        # Create the view first time
        result = runner.invoke(cli, ["create-view", "Counter"])
        assert result.exit_code == 0

        # Try to create again
        result = runner.invoke(cli, ["create-view", "Counter"])
        assert result.exit_code != 0
        assert "Error: Directory 'views/counter' already exists" in result.output


def test_pascal_case_conversion(runner, temp_dir):
    """Test that PascalCase names are converted properly."""
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["create-view", "UserProfile"])

        assert result.exit_code == 0

        view_dir = Path("views/user_profile")
        assert view_dir.exists()
        assert (view_dir / "user_profile.py").exists()

        # Check class names
        py_content = (view_dir / "user_profile.py").read_text()
        assert "class UserProfileContext:" in py_content
        assert "class UserProfileLiveView" in py_content


def test_detect_package_structure_poetry(temp_dir):
    """Test package structure detection with Poetry configuration."""
    test_dir = Path(temp_dir)

    # Create a pyproject.toml with Poetry packages configuration
    pyproject_content = """
[tool.poetry]
name = "test-project"
packages = [
    { include = "myapp", from = "src" }
]
"""
    (test_dir / "pyproject.toml").write_text(pyproject_content)

    package_name, views_path = detect_package_structure(test_dir)

    assert package_name == "myapp"
    assert views_path == "src/myapp/views"


def test_detect_package_structure_no_from(temp_dir):
    """Test package structure detection without 'from' specification."""
    test_dir = Path(temp_dir)

    # Create a pyproject.toml with packages at root
    pyproject_content = """
[tool.poetry]
name = "test-project"
packages = [
    { include = "myapp" }
]
"""
    (test_dir / "pyproject.toml").write_text(pyproject_content)

    package_name, views_path = detect_package_structure(test_dir)

    assert package_name == "myapp"
    assert views_path == "myapp/views"


def test_detect_package_structure_no_file(temp_dir):
    """Test package structure detection with no pyproject.toml."""
    test_dir = Path(temp_dir)

    package_name, views_path = detect_package_structure(test_dir)

    assert package_name is None
    assert views_path == "views"


def test_create_view_with_package_detection(runner, temp_dir):
    """Test creating a view with automatic package detection."""
    with runner.isolated_filesystem():
        # Create pyproject.toml with package structure
        pyproject_content = """
[tool.poetry]
name = "test-project"
packages = [
    { include = "myapp", from = "src" }
]
"""
        Path("pyproject.toml").write_text(pyproject_content)

        result = runner.invoke(cli, ["create-view", "Counter"])

        assert result.exit_code == 0
        assert "LiveView created successfully!" in result.output

        # Check that view was created in detected path
        view_dir = Path("src/myapp/views/counter")
        assert view_dir.exists()
        assert (view_dir / "counter.py").exists()

        # Check import advice uses detected package
        assert "from myapp.views.counter import CounterLiveView" in result.output


def test_normalize_project_name():
    """Test PEP 503 project name normalization."""
    assert normalize_project_name("myapp") == "myapp"
    assert normalize_project_name("my-app") == "my_app"
    assert normalize_project_name("my.app") == "my_app"
    assert normalize_project_name("My-App") == "my_app"
    assert normalize_project_name("my-cool.app") == "my_cool_app"


def test_detect_package_structure_uv_build(temp_dir):
    """Test package structure detection with uv_build backend."""
    test_dir = Path(temp_dir)

    pyproject_content = """
[project]
name = "myapp"

[build-system]
requires = ["uv_build>=0.10.4,<0.11.0"]
build-backend = "uv_build"
"""
    (test_dir / "pyproject.toml").write_text(pyproject_content)
    (test_dir / "src" / "myapp").mkdir(parents=True)

    package_name, views_path = detect_package_structure(test_dir)

    assert package_name == "myapp"
    assert views_path == "src/myapp/views"


def test_detect_package_structure_uv_build_dashed_name(temp_dir):
    """Test uv_build detection normalizes dashed project names."""
    test_dir = Path(temp_dir)

    pyproject_content = """
[project]
name = "my-cool-app"

[build-system]
requires = ["uv_build>=0.10.4,<0.11.0"]
build-backend = "uv_build"
"""
    (test_dir / "pyproject.toml").write_text(pyproject_content)
    (test_dir / "src" / "my_cool_app").mkdir(parents=True)

    package_name, views_path = detect_package_structure(test_dir)

    assert package_name == "my_cool_app"
    assert views_path == "src/my_cool_app/views"


def test_detect_package_structure_uv_build_custom_module(temp_dir):
    """Test uv_build detection with custom module-name and module-root."""
    test_dir = Path(temp_dir)

    pyproject_content = """
[project]
name = "my-app"

[build-system]
requires = ["uv_build>=0.10.4,<0.11.0"]
build-backend = "uv_build"

[tool.uv.build-backend]
module-name = "myapp"
module-root = "lib"
"""
    (test_dir / "pyproject.toml").write_text(pyproject_content)
    (test_dir / "lib" / "myapp").mkdir(parents=True)

    package_name, views_path = detect_package_structure(test_dir)

    assert package_name == "myapp"
    assert views_path == "lib/myapp/views"


def test_detect_package_structure_uv_build_no_module_root(temp_dir):
    """Test uv_build detection with empty module-root (root directory)."""
    test_dir = Path(temp_dir)

    pyproject_content = """
[project]
name = "myapp"

[build-system]
requires = ["uv_build>=0.10.4,<0.11.0"]
build-backend = "uv_build"

[tool.uv.build-backend]
module-root = ""
"""
    (test_dir / "pyproject.toml").write_text(pyproject_content)
    (test_dir / "myapp").mkdir(parents=True)

    package_name, views_path = detect_package_structure(test_dir)

    assert package_name == "myapp"
    assert views_path == "myapp/views"


def test_detect_package_structure_uv_build_dir_missing(temp_dir):
    """Test build-backend detection falls through when package dir doesn't exist."""
    test_dir = Path(temp_dir)

    pyproject_content = """
[project]
name = "myapp"

[build-system]
requires = ["uv_build>=0.10.4,<0.11.0"]
build-backend = "uv_build"
"""
    (test_dir / "pyproject.toml").write_text(pyproject_content)
    # No src/myapp/ directory created

    package_name, views_path = detect_package_structure(test_dir)

    assert package_name is None
    assert views_path == "views"


def test_detect_package_structure_src_layout_fallback(temp_dir):
    """Test filesystem fallback with [project] name and src/ directory."""
    test_dir = Path(temp_dir)

    # uv-style pyproject.toml: no packages, no build-system
    pyproject_content = """
[project]
name = "myapp"

[tool.uv]
package = false
"""
    (test_dir / "pyproject.toml").write_text(pyproject_content)

    # Create src/myapp/ directory
    (test_dir / "src" / "myapp").mkdir(parents=True)

    package_name, views_path = detect_package_structure(test_dir)

    assert package_name == "myapp"
    assert views_path == "src/myapp/views"


def test_detect_package_structure_src_layout_name_normalization(temp_dir):
    """Test filesystem fallback normalizes dashed project names."""
    test_dir = Path(temp_dir)

    pyproject_content = """
[project]
name = "my-app"

[tool.uv]
package = false
"""
    (test_dir / "pyproject.toml").write_text(pyproject_content)

    # Directory uses underscores (Python convention)
    (test_dir / "src" / "my_app").mkdir(parents=True)

    package_name, views_path = detect_package_structure(test_dir)

    assert package_name == "my_app"
    assert views_path == "src/my_app/views"


def test_detect_package_structure_src_layout_no_name(temp_dir):
    """Test filesystem fallback without [project] name falls back to views/."""
    test_dir = Path(temp_dir)

    # pyproject.toml without project name
    pyproject_content = """
[tool.uv]
package = false
"""
    (test_dir / "pyproject.toml").write_text(pyproject_content)

    (test_dir / "src" / "myapp").mkdir(parents=True)

    package_name, views_path = detect_package_structure(test_dir)

    assert package_name is None
    assert views_path == "views"


def test_detect_package_structure_src_layout_no_matching_dir(temp_dir):
    """Test filesystem fallback when src/ dir doesn't match project name."""
    test_dir = Path(temp_dir)

    pyproject_content = """
[project]
name = "myapp"

[tool.uv]
package = false
"""
    (test_dir / "pyproject.toml").write_text(pyproject_content)

    # src/ exists but with a different directory name
    (test_dir / "src" / "other_package").mkdir(parents=True)

    package_name, views_path = detect_package_structure(test_dir)

    assert package_name is None
    assert views_path == "views"


def test_create_view_with_uv_project(runner):
    """End-to-end test: create-view with uv-style project (matching cookiecutter)."""
    with runner.isolated_filesystem():
        # Replicate the uv cookiecutter structure
        pyproject_content = """
[project]
name = "myapp"

[tool.uv]
package = false
"""
        Path("pyproject.toml").write_text(pyproject_content)
        Path("src/myapp/views").mkdir(parents=True)
        Path("src/myapp/__init__.py").write_text("")

        result = runner.invoke(cli, ["create-view", "Temperature"])

        assert result.exit_code == 0
        assert "LiveView created successfully!" in result.output

        # Check that view was created in the correct path
        view_dir = Path("src/myapp/views/temperature")
        assert view_dir.exists()
        assert (view_dir / "temperature.py").exists()
        assert (view_dir / "temperature.html").exists()
        assert (view_dir / "temperature.css").exists()

        # Check import advice
        assert "from myapp.views.temperature import TemperatureLiveView" in result.output
