import pytest
from click.testing import CliRunner
from pathlib import Path
import tempfile
import shutil

from pyview.cli.main import cli
from pyview.cli.commands.create_view import detect_package_structure


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
        result = runner.invoke(cli, ['create-view', 'Counter'])
        
        assert result.exit_code == 0
        assert 'LiveView created successfully!' in result.output
        
        # Check that all files were created
        view_dir = Path('views/counter')
        assert view_dir.exists()
        assert (view_dir / '__init__.py').exists()
        assert (view_dir / 'counter.py').exists()
        assert (view_dir / 'counter.html').exists()
        assert (view_dir / 'counter.css').exists()
        
        # Check Python file content
        py_content = (view_dir / 'counter.py').read_text()
        assert 'class CounterContext:' in py_content
        assert 'class CounterLiveView(BaseEventHandler, LiveView[CounterContext]):' in py_content
        assert 'async def mount(self, socket: LiveViewSocket[CounterContext], session):' in py_content
        assert 'socket.context = CounterContext()' in py_content


def test_create_view_no_css(runner, temp_dir):
    """Test creating a view without CSS file."""
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ['create-view', 'Counter', '--no-css'])
        
        assert result.exit_code == 0
        
        view_dir = Path('views/counter')
        assert view_dir.exists()
        assert (view_dir / '__init__.py').exists()
        assert (view_dir / 'counter.py').exists()
        assert (view_dir / 'counter.html').exists()
        assert not (view_dir / 'counter.css').exists()


def test_create_view_custom_path(runner, temp_dir):
    """Test creating a view in a custom directory."""
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ['create-view', 'MyView', '--path', 'custom/views'])
        
        assert result.exit_code == 0
        
        view_dir = Path('custom/views/my_view')
        assert view_dir.exists()
        assert (view_dir / 'my_view.py').exists()


def test_create_view_already_exists(runner, temp_dir):
    """Test error when view directory already exists."""
    with runner.isolated_filesystem():
        # Create the view first time
        result = runner.invoke(cli, ['create-view', 'Counter'])
        assert result.exit_code == 0
        
        # Try to create again
        result = runner.invoke(cli, ['create-view', 'Counter'])
        assert result.exit_code != 0
        assert "Error: Directory 'views/counter' already exists" in result.output


def test_pascal_case_conversion(runner, temp_dir):
    """Test that PascalCase names are converted properly."""
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ['create-view', 'UserProfile'])
        
        assert result.exit_code == 0
        
        view_dir = Path('views/user_profile')
        assert view_dir.exists()
        assert (view_dir / 'user_profile.py').exists()
        
        # Check class names
        py_content = (view_dir / 'user_profile.py').read_text()
        assert 'class UserProfileContext:' in py_content
        assert 'class UserProfileLiveView' in py_content


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
        
        result = runner.invoke(cli, ['create-view', 'Counter'])
        
        assert result.exit_code == 0
        assert 'LiveView created successfully!' in result.output
        
        # Check that view was created in detected path
        view_dir = Path('src/myapp/views/counter')
        assert view_dir.exists()
        assert (view_dir / 'counter.py').exists()
        
        # Check import advice uses detected package
        assert 'from myapp.views.counter import CounterLiveView' in result.output