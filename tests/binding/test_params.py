"""Tests for Params container."""
import pytest

from pyview.binding import Params


class TestParams:
    """Test the Params multi-value container."""

    def test_get_single_value(self):
        p = Params({"c": ["5"]})
        assert p.get("c") == "5"

    def test_get_missing_returns_none(self):
        p = Params({})
        assert p.get("c") is None

    def test_get_missing_returns_default(self):
        p = Params({})
        assert p.get("c", "default") == "default"

    def test_get_empty_list_returns_default(self):
        p = Params({"c": []})
        assert p.get("c") is None
        assert p.get("c", "default") == "default"

    def test_getlist_returns_all_values(self):
        p = Params({"tags": ["a", "b", "c"]})
        assert p.getlist("tags") == ["a", "b", "c"]

    def test_getlist_missing_returns_empty(self):
        p = Params({})
        assert p.getlist("tags") == []

    def test_getone_success(self):
        p = Params({"id": ["123"]})
        assert p.getone("id") == "123"

    def test_getone_missing_raises(self):
        p = Params({})
        with pytest.raises(KeyError, match="Expected exactly one"):
            p.getone("id")

    def test_getone_multiple_raises(self):
        p = Params({"id": ["1", "2"]})
        with pytest.raises(KeyError, match="Expected exactly one"):
            p.getone("id")

    def test_getone_empty_raises(self):
        p = Params({"id": []})
        with pytest.raises(KeyError, match="Expected exactly one"):
            p.getone("id")

    def test_has_existing_key(self):
        p = Params({"a": ["1"]})
        assert p.has("a") is True

    def test_has_missing_key(self):
        p = Params({"a": ["1"]})
        assert p.has("b") is False

    def test_contains_dunder(self):
        p = Params({"a": ["1"]})
        assert "a" in p
        assert "b" not in p

    def test_keys(self):
        p = Params({"a": ["1"], "b": ["2"]})
        assert set(p.keys()) == {"a", "b"}

    def test_items_returns_first_values(self):
        p = Params({"a": ["1", "2"], "b": ["3"]})
        result = dict(p.items())
        assert result == {"a": "1", "b": "3"}

    def test_items_skips_empty(self):
        p = Params({"a": ["1"], "b": []})
        result = dict(p.items())
        assert result == {"a": "1"}

    def test_multi_items(self):
        p = Params({"a": ["1", "2"], "b": ["3"]})
        result = list(p.multi_items())
        assert ("a", "1") in result
        assert ("a", "2") in result
        assert ("b", "3") in result
        assert len(result) == 3

    def test_raw_returns_underlying_dict(self):
        data = {"a": ["1"], "b": ["2", "3"]}
        p = Params(data)
        assert p.raw() is data

    def test_to_flat_dict_single_values_become_scalars(self):
        p = Params({"a": ["1"], "b": ["2"]})
        assert p.to_flat_dict() == {"a": "1", "b": "2"}

    def test_to_flat_dict_multi_values_remain_lists(self):
        p = Params({"a": ["1"], "b": ["2", "3"]})
        assert p.to_flat_dict() == {"a": "1", "b": ["2", "3"]}

    def test_len(self):
        p = Params({"a": ["1"], "b": ["2"]})
        assert len(p) == 2

    def test_repr(self):
        p = Params({"a": ["1"]})
        assert repr(p) == "Params({'a': ['1']})"
