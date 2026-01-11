"""Tests for payload parsing utilities."""

import pytest

from pyview.changesets.payload import (
    flatten_payload,
    parse_form_payload,
)


class TestParseFormPayload:
    def test_flat_payload(self):
        payload = {"name": ["John"], "_target": ["name"]}
        path, value = parse_form_payload(payload)
        assert path == "name"
        assert value == "John"

    def test_nested_via_target(self):
        payload = {"address.city": ["NYC"], "_target": ["address", "city"]}
        path, value = parse_form_payload(payload)
        assert path == "address.city"
        assert value == "NYC"

    def test_list_index(self):
        payload = {"tags.0": ["python"], "_target": ["tags", "0"]}
        path, value = parse_form_payload(payload)
        assert path == "tags.0"
        assert value == "python"

    def test_nested_list(self):
        payload = {
            "addresses.0.city": ["NYC"],
            "_target": ["addresses", "0", "city"],
        }
        path, value = parse_form_payload(payload)
        assert path == "addresses.0.city"
        assert value == "NYC"

    def test_empty_value_array(self):
        payload = {"name": [], "_target": ["name"]}
        path, value = parse_form_payload(payload)
        assert path == "name"
        assert value == ""

    def test_single_value_extracted_from_array(self):
        payload = {"email": ["test@example.com"], "_target": ["email"]}
        path, value = parse_form_payload(payload)
        assert value == "test@example.com"

    def test_multiple_values_preserved(self):
        # Multi-select scenario
        payload = {"tags": ["a", "b", "c"], "_target": ["tags"]}
        path, value = parse_form_payload(payload)
        assert value == ["a", "b", "c"]

    def test_no_target_uses_first_non_underscore_key(self):
        payload = {"name": ["John"]}
        path, value = parse_form_payload(payload)
        assert path == "name"
        assert value == "John"

    def test_empty_target(self):
        payload = {"_target": [], "name": ["John"]}
        path, value = parse_form_payload(payload)
        assert path == "name"
        assert value == "John"

    def test_fallback_to_first_segment(self):
        # When dot-notation key doesn't exist, try first segment
        payload = {"name": ["John"], "_target": ["name"]}
        path, value = parse_form_payload(payload)
        assert path == "name"
        assert value == "John"


class TestFlattenPayload:
    def test_already_flat(self):
        payload = {"name": "John", "email": "john@example.com"}
        result = flatten_payload(payload)
        assert result == {"name": "John", "email": "john@example.com"}

    def test_nested_dict(self):
        payload = {"user": {"name": "John", "email": "john@example.com"}}
        result = flatten_payload(payload)
        assert result == {
            "user.name": "John",
            "user.email": "john@example.com",
        }

    def test_deeply_nested(self):
        payload = {"user": {"address": {"city": "NYC", "zip": "10001"}}}
        result = flatten_payload(payload)
        assert result == {
            "user.address.city": "NYC",
            "user.address.zip": "10001",
        }

    def test_preserves_underscore_keys(self):
        payload = {"_target": ["name"], "_csrf": "token123", "name": "John"}
        result = flatten_payload(payload)
        assert result == {
            "_target": ["name"],
            "_csrf": "token123",
            "name": "John",
        }

    def test_mixed_flat_and_nested(self):
        payload = {
            "name": "John",
            "address": {"city": "NYC"},
        }
        result = flatten_payload(payload)
        assert result == {
            "name": "John",
            "address.city": "NYC",
        }
