"""Tests for ConverterRegistry."""

from dataclasses import dataclass
from typing import Optional, Union

import pytest

from pyview.binding.converters import ConversionError, ConverterRegistry


class TestConverterRegistry:
    """Test type conversion from raw values."""

    @pytest.fixture
    def converter(self) -> ConverterRegistry:
        return ConverterRegistry()

    # --- Scalar int conversions ---

    def test_int_from_string(self, converter: ConverterRegistry):
        assert converter.convert("42", int) == 42

    def test_int_from_list(self, converter: ConverterRegistry):
        assert converter.convert(["42"], int) == 42

    def test_int_from_list_picks_first(self, converter: ConverterRegistry):
        assert converter.convert(["42", "99"], int) == 42

    def test_negative_int(self, converter: ConverterRegistry):
        assert converter.convert("-10", int) == -10

    # --- Scalar float conversions ---

    def test_float_from_string(self, converter: ConverterRegistry):
        assert converter.convert("3.14", float) == pytest.approx(3.14)

    def test_float_from_list(self, converter: ConverterRegistry):
        assert converter.convert(["3.14"], float) == pytest.approx(3.14)

    def test_negative_float(self, converter: ConverterRegistry):
        assert converter.convert("-2.5", float) == pytest.approx(-2.5)

    # --- Scalar str conversions ---

    def test_str_passthrough(self, converter: ConverterRegistry):
        assert converter.convert("hello", str) == "hello"

    def test_str_from_list(self, converter: ConverterRegistry):
        assert converter.convert(["hello"], str) == "hello"

    # --- Boolean conversions ---

    def test_bool_true_string_values(self, converter: ConverterRegistry):
        for v in ["true", "True", "TRUE", "1", "yes", "on"]:
            assert converter.convert(v, bool) is True, f"Failed for {v}"

    def test_bool_false_string_values(self, converter: ConverterRegistry):
        for v in ["false", "False", "FALSE", "0", "no", "off", ""]:
            assert converter.convert(v, bool) is False, f"Failed for {v}"

    def test_bool_from_int(self, converter: ConverterRegistry):
        assert converter.convert(1, bool) is True
        assert converter.convert(0, bool) is False

    def test_bool_from_list(self, converter: ConverterRegistry):
        assert converter.convert(["true"], bool) is True
        assert converter.convert(["false"], bool) is False

    def test_bool_passthrough(self, converter: ConverterRegistry):
        assert converter.convert(True, bool) is True
        assert converter.convert(False, bool) is False

    def test_bool_invalid_raises(self, converter: ConverterRegistry):
        with pytest.raises(ConversionError, match="Cannot convert"):
            converter.convert("maybe", bool)

    # --- Optional conversions ---

    def test_optional_none(self, converter: ConverterRegistry):
        assert converter.convert(None, Optional[int]) is None

    def test_optional_empty_string(self, converter: ConverterRegistry):
        assert converter.convert("", Optional[int]) is None

    def test_optional_empty_string_list(self, converter: ConverterRegistry):
        assert converter.convert([""], Optional[int]) is None

    def test_optional_with_value(self, converter: ConverterRegistry):
        assert converter.convert("42", Optional[int]) == 42

    def test_optional_with_list_value(self, converter: ConverterRegistry):
        assert converter.convert(["42"], Optional[int]) == 42

    # --- Union conversions ---

    def test_union_first_match_int(self, converter: ConverterRegistry):
        assert converter.convert("42", Union[int, str]) == 42

    def test_union_fallback_to_str(self, converter: ConverterRegistry):
        assert converter.convert("hello", Union[int, str]) == "hello"

    def test_union_three_types(self, converter: ConverterRegistry):
        assert converter.convert("3.14", Union[int, float, str]) == pytest.approx(3.14)
        assert converter.convert("42", Union[int, float, str]) == 42
        assert converter.convert("hello", Union[int, float, str]) == "hello"

    def test_union_no_match_raises(self, converter: ConverterRegistry):
        # Union that can't match
        with pytest.raises(ConversionError, match="No union variant matched"):
            converter.convert("hello", Union[int, float])

    # --- Pipe union syntax (X | Y) conversions ---

    def test_pipe_optional_none(self, converter: ConverterRegistry):
        assert converter.convert(None, int | None) is None

    def test_pipe_optional_empty_string(self, converter: ConverterRegistry):
        assert converter.convert("", int | None) is None

    def test_pipe_optional_empty_string_list(self, converter: ConverterRegistry):
        assert converter.convert([""], int | None) is None

    def test_pipe_optional_with_value(self, converter: ConverterRegistry):
        assert converter.convert("42", int | None) == 42

    def test_pipe_optional_float(self, converter: ConverterRegistry):
        assert converter.convert("3.14", float | None) == pytest.approx(3.14)
        assert converter.convert("", float | None) is None

    def test_pipe_optional_str(self, converter: ConverterRegistry):
        assert converter.convert("hello", str | None) == "hello"
        assert converter.convert("", str | None) == ""  # Empty string is valid str
        assert converter.convert(None, str | None) is None

    def test_pipe_union_first_match(self, converter: ConverterRegistry):
        assert converter.convert("42", int | str) == 42

    def test_pipe_union_fallback(self, converter: ConverterRegistry):
        assert converter.convert("hello", int | str) == "hello"

    def test_pipe_union_three_types(self, converter: ConverterRegistry):
        assert converter.convert("3.14", int | float | str) == pytest.approx(3.14)
        assert converter.convert("42", int | float | str) == 42
        assert converter.convert("hello", int | float | str) == "hello"

    # --- Container list conversions ---

    def test_list_from_list(self, converter: ConverterRegistry):
        assert converter.convert(["a", "b"], list[str]) == ["a", "b"]

    def test_list_single_value(self, converter: ConverterRegistry):
        assert converter.convert("a", list[str]) == ["a"]

    def test_list_with_int_conversion(self, converter: ConverterRegistry):
        assert converter.convert(["1", "2", "3"], list[int]) == [1, 2, 3]

    def test_list_empty(self, converter: ConverterRegistry):
        assert converter.convert([], list[str]) == []

    # --- Container set conversions ---

    def test_set_from_list(self, converter: ConverterRegistry):
        assert converter.convert(["a", "b", "a"], set[str]) == {"a", "b"}

    def test_set_with_int_conversion(self, converter: ConverterRegistry):
        assert converter.convert(["1", "2", "1"], set[int]) == {1, 2}

    # --- Container tuple conversions ---

    # Homogeneous tuples (tuple[T, ...])
    def test_tuple_homogeneous_from_list(self, converter: ConverterRegistry):
        assert converter.convert(["1", "2"], tuple[int, ...]) == (1, 2)

    def test_tuple_homogeneous_single_value(self, converter: ConverterRegistry):
        assert converter.convert("1", tuple[int, ...]) == (1,)

    # Heterogeneous tuples (tuple[T1, T2, T3])
    def test_tuple_heterogeneous_two_types(self, converter: ConverterRegistry):
        assert converter.convert(["42", "hello"], tuple[int, str]) == (42, "hello")

    def test_tuple_heterogeneous_three_types(self, converter: ConverterRegistry):
        assert converter.convert(["1", "3.14", "yes"], tuple[int, float, bool]) == (
            1,
            pytest.approx(3.14),
            True,
        )

    def test_tuple_heterogeneous_wrong_length_raises(self, converter: ConverterRegistry):
        with pytest.raises(ConversionError, match="Expected 3 values"):
            converter.convert(["1", "2"], tuple[int, str, bool])

    # --- Error cases ---

    def test_invalid_int_raises(self, converter: ConverterRegistry):
        with pytest.raises(ConversionError, match="Cannot convert"):
            converter.convert("not-a-number", int)

    def test_empty_list_for_scalar_raises(self, converter: ConverterRegistry):
        with pytest.raises(ConversionError, match="Empty list"):
            converter.convert([], int)

    def test_required_none_raises(self, converter: ConverterRegistry):
        with pytest.raises(ConversionError, match="Value is required"):
            converter.convert(None, int)

    # --- Fallback behavior ---

    def test_unknown_type_passthrough(self, converter: ConverterRegistry):
        class CustomType:
            pass

        obj = CustomType()
        assert converter.convert(obj, CustomType) is obj

    def test_any_passthrough(self, converter: ConverterRegistry):
        from typing import Any

        assert converter.convert("hello", Any) == "hello"
        assert converter.convert(123, Any) == 123

    # --- Dataclass conversions ---

    def test_dataclass_from_dict(self, converter: ConverterRegistry):
        @dataclass
        class Point:
            x: int
            y: int

        result = converter.convert({"x": ["10"], "y": ["20"]}, Point)
        assert result == Point(x=10, y=20)

    def test_dataclass_with_optional_fields(self, converter: ConverterRegistry):
        @dataclass
        class PagingParams:
            page: Optional[int] = None
            perPage: Optional[int] = None

        # Both provided
        result = converter.convert({"page": ["1"], "perPage": ["10"]}, PagingParams)
        assert result == PagingParams(page=1, perPage=10)

        # Only one provided
        result = converter.convert({"page": ["5"]}, PagingParams)
        assert result == PagingParams(page=5, perPage=None)

        # Neither provided
        result = converter.convert({}, PagingParams)
        assert result == PagingParams(page=None, perPage=None)

    def test_dataclass_with_defaults(self, converter: ConverterRegistry):
        @dataclass
        class Config:
            limit: int = 100
            offset: int = 0

        # Override defaults
        result = converter.convert({"limit": ["50"]}, Config)
        assert result == Config(limit=50, offset=0)

        # Use all defaults
        result = converter.convert({}, Config)
        assert result == Config(limit=100, offset=0)

    def test_dataclass_with_string_field(self, converter: ConverterRegistry):
        @dataclass
        class SearchParams:
            query: str
            page: int = 1

        result = converter.convert({"query": ["hello world"], "page": ["2"]}, SearchParams)
        assert result == SearchParams(query="hello world", page=2)

    def test_dataclass_nested_types(self, converter: ConverterRegistry):
        @dataclass
        class FilterParams:
            tags: list[str]
            limit: Optional[int] = None

        result = converter.convert({"tags": ["a", "b", "c"], "limit": ["5"]}, FilterParams)
        assert result == FilterParams(tags=["a", "b", "c"], limit=5)

    def test_dataclass_non_dict_raises(self, converter: ConverterRegistry):
        @dataclass
        class Point:
            x: int
            y: int

        with pytest.raises(ConversionError, match="Expected dict"):
            converter.convert("not a dict", Point)

    def test_dataclass_missing_required_field_raises(self, converter: ConverterRegistry):
        @dataclass
        class Point:
            x: int
            y: int

        with pytest.raises(ConversionError, match="Missing required fields for Point: x, y"):
            converter.convert({}, Point)

    def test_dataclass_missing_one_required_field_raises(self, converter: ConverterRegistry):
        @dataclass
        class Point:
            x: int
            y: int

        with pytest.raises(ConversionError, match="Missing required fields for Point: y"):
            converter.convert({"x": ["1"]}, Point)
