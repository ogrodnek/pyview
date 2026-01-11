"""Tests for path utilities."""

import pytest

from pyview.changesets.paths import get_nested, join_path, parse_path, set_nested


class TestParsePath:
    def test_simple_field(self):
        assert parse_path("name") == ["name"]

    def test_nested_field(self):
        assert parse_path("address.city") == ["address", "city"]

    def test_deeply_nested(self):
        assert parse_path("a.b.c.d") == ["a", "b", "c", "d"]

    def test_list_index(self):
        assert parse_path("tags.0") == ["tags", 0]

    def test_nested_list(self):
        assert parse_path("addresses.0.city") == ["addresses", 0, "city"]

    def test_multiple_indices(self):
        assert parse_path("matrix.0.1") == ["matrix", 0, 1]

    def test_empty_path(self):
        assert parse_path("") == []


class TestGetNested:
    def test_simple_field(self):
        data = {"name": "John"}
        assert get_nested(data, "name") == "John"

    def test_nested_field(self):
        data = {"address": {"city": "NYC", "zip": "10001"}}
        assert get_nested(data, "address.city") == "NYC"

    def test_deeply_nested(self):
        data = {"a": {"b": {"c": {"d": "value"}}}}
        assert get_nested(data, "a.b.c.d") == "value"

    def test_list_index(self):
        data = {"tags": ["python", "web", "async"]}
        assert get_nested(data, "tags.0") == "python"
        assert get_nested(data, "tags.1") == "web"
        assert get_nested(data, "tags.2") == "async"

    def test_nested_list(self):
        data = {"addresses": [{"city": "NYC"}, {"city": "LA"}]}
        assert get_nested(data, "addresses.0.city") == "NYC"
        assert get_nested(data, "addresses.1.city") == "LA"

    def test_missing_key_returns_default(self):
        data = {"name": "John"}
        assert get_nested(data, "email") is None
        assert get_nested(data, "email", "default") == "default"

    def test_missing_nested_returns_default(self):
        data = {"address": {}}
        assert get_nested(data, "address.city") is None
        assert get_nested(data, "address.city", "Unknown") == "Unknown"

    def test_list_index_out_of_bounds(self):
        data = {"tags": ["a", "b"]}
        assert get_nested(data, "tags.5") is None
        assert get_nested(data, "tags.5", "default") == "default"

    def test_none_value_in_path(self):
        data = {"address": None}
        assert get_nested(data, "address.city") is None


class TestSetNested:
    def test_simple_field(self):
        data: dict = {}
        set_nested(data, "name", "John")
        assert data == {"name": "John"}

    def test_nested_field_creates_intermediate(self):
        data: dict = {}
        set_nested(data, "address.city", "NYC")
        assert data == {"address": {"city": "NYC"}}

    def test_deeply_nested(self):
        data: dict = {}
        set_nested(data, "a.b.c.d", "value")
        assert data == {"a": {"b": {"c": {"d": "value"}}}}

    def test_list_index_creates_list(self):
        data: dict = {}
        set_nested(data, "tags.0", "python")
        assert data == {"tags": ["python"]}

    def test_list_index_extends_list(self):
        data = {"tags": ["python"]}
        set_nested(data, "tags.2", "async")
        assert data == {"tags": ["python", None, "async"]}

    def test_nested_list(self):
        data: dict = {}
        set_nested(data, "addresses.0.city", "NYC")
        assert data == {"addresses": [{"city": "NYC"}]}

    def test_update_existing_nested(self):
        data = {"address": {"city": "NYC", "zip": "10001"}}
        set_nested(data, "address.city", "LA")
        assert data == {"address": {"city": "LA", "zip": "10001"}}

    def test_returns_modified_dict(self):
        data: dict = {}
        result = set_nested(data, "name", "John")
        assert result is data
        assert result == {"name": "John"}


class TestJoinPath:
    def test_simple(self):
        assert join_path("name") == "name"

    def test_multiple_strings(self):
        assert join_path("address", "city") == "address.city"

    def test_with_integer(self):
        assert join_path("tags", 0) == "tags.0"

    def test_mixed(self):
        assert join_path("addresses", 0, "city") == "addresses.0.city"
