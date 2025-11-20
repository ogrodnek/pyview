"""
Pytest configuration for pyview tests.
"""

import sys

import pytest


def pytest_collection_modifyitems(config, items):
    """Skip t-string tests on Python < 3.14."""
    if sys.version_info >= (3, 14):
        return

    skip_marker = pytest.mark.skip(reason="T-string tests require Python 3.14+")
    for item in items:
        if "test_live_view_template" in item.nodeid or "test_template_view" in item.nodeid:
            item.add_marker(skip_marker)


def pytest_ignore_collect(collection_path, path, config):
    """
    Prevent pytest from even trying to parse t-string test files on Python < 3.14.
    This happens before AST parsing, so it prevents SyntaxErrors.
    """
    if sys.version_info >= (3, 14):
        return False

    # Skip files that contain t-string literals
    return collection_path.name in ("test_live_view_template.py", "test_template_view.py")
