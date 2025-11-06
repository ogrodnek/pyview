"""Tests for parameter conversion functionality."""

import inspect
import pytest
from typing import Optional
from dataclasses import dataclass

from pyview.params import (
    convert_scalar,
    convert_value,
    convert_params,
    normalize_param_value,
    typed_params,
)
from pyview.params.inspection import (
    should_convert_params,
    get_skip_params_for_handler,
    get_conversion_strategy,
)


class TestNormalizeParamValue:
    """Tests for normalize_param_value function."""

    def test_string_to_list(self):
        """String values (path params) should be converted to single-item lists."""
        assert normalize_param_value("hello") == ["hello"]

    def test_list_passthrough(self):
        """List values (query params) should pass through unchanged."""
        assert normalize_param_value(["a", "b", "c"]) == ["a", "b", "c"]

    def test_empty_string(self):
        """Empty strings should become single-item lists."""
        assert normalize_param_value("") == [""]


class TestConvertScalar:
    """Tests for convert_scalar function."""

    def test_string_passthrough(self):
        """Strings should pass through unchanged."""
        assert convert_scalar("hello", str) == "hello"

    def test_int_conversion(self):
        """String numbers should convert to int."""
        assert convert_scalar("123", int) == 123
        assert convert_scalar("0", int) == 0
        assert convert_scalar("-42", int) == -42

    def test_int_conversion_error(self):
        """Invalid int strings should raise ValueError."""
        with pytest.raises(ValueError, match="Cannot convert 'hello' to int"):
            convert_scalar("hello", int)

    def test_float_conversion(self):
        """String numbers should convert to float."""
        assert convert_scalar("3.14", float) == 3.14
        assert convert_scalar("0.0", float) == 0.0
        assert convert_scalar("-1.5", float) == -1.5

    def test_float_conversion_error(self):
        """Invalid float strings should raise ValueError."""
        with pytest.raises(ValueError, match="Cannot convert 'hello' to float"):
            convert_scalar("hello", float)

    def test_bool_true_values(self):
        """Common truthy strings should convert to True."""
        for value in ["true", "True", "TRUE", "t", "T", "1", "yes", "on"]:
            assert convert_scalar(value, bool) is True, f"Failed for {value}"

    def test_bool_false_values(self):
        """Common falsy strings should convert to False."""
        for value in ["false", "False", "FALSE", "f", "F", "0", "no", "off", ""]:
            assert convert_scalar(value, bool) is False, f"Failed for {value}"

    def test_bool_other_values(self):
        """Other strings should be truthy (Python default behavior)."""
        assert convert_scalar("hello", bool) is True
        assert convert_scalar("anything", bool) is True


class TestConvertValue:
    """Tests for convert_value function."""

    def test_scalar_string_from_list(self):
        """String list should extract first value."""
        assert convert_value(["hello"], str) == "hello"

    def test_scalar_string_from_string(self):
        """String path param should work directly."""
        assert convert_value("hello", str) == "hello"

    def test_scalar_int(self):
        """Int conversion from list."""
        assert convert_value(["123"], int) == 123

    def test_scalar_int_from_string(self):
        """Int conversion from string (path param)."""
        assert convert_value("123", int) == 123

    def test_optional_present(self):
        """Optional with value should convert."""
        assert convert_value(["123"], Optional[int]) == 123

    def test_optional_empty_list(self):
        """Optional with empty list should return None."""
        assert convert_value([], Optional[int]) is None

    def test_optional_empty_string(self):
        """Optional with empty string should return None."""
        assert convert_value([""], Optional[int]) is None

    def test_optional_string(self):
        """Optional string should work."""
        assert convert_value(["hello"], Optional[str]) == "hello"
        assert convert_value([], Optional[str]) is None

    def test_list_int(self):
        """List of ints should convert all elements."""
        assert convert_value(["1", "2", "3"], list[int]) == [1, 2, 3]

    def test_list_str(self):
        """List of strings should pass through."""
        assert convert_value(["a", "b", "c"], list[str]) == ["a", "b", "c"]

    def test_list_empty(self):
        """Empty list should stay empty."""
        assert convert_value([], list[int]) == []

    def test_list_bool(self):
        """List of bools should convert."""
        assert convert_value(["true", "false", "1"], list[bool]) == [True, False, True]

    def test_required_missing(self):
        """Required parameter with no value should raise error."""
        with pytest.raises(ValueError, match="No value provided"):
            convert_value([], int)


class TestConvertParams:
    """Tests for convert_params function."""

    def test_simple_int_params(self):
        """Simple int parameters should convert."""

        def dummy(count: int, page: int):
            pass

        sig = inspect.signature(dummy)
        result = convert_params({"count": ["5"], "page": ["2"]}, sig)
        assert result == {"count": 5, "page": 2}

    def test_with_defaults(self):
        """Missing parameters should use defaults."""

        def dummy(count: int = 0, page: int = 1):
            pass

        sig = inspect.signature(dummy)
        result = convert_params({"count": ["5"]}, sig)
        assert result == {"count": 5, "page": 1}

    def test_all_defaults(self):
        """All parameters with defaults, none provided."""

        def dummy(count: int = 0, page: int = 1):
            pass

        sig = inspect.signature(dummy)
        result = convert_params({}, sig)
        assert result == {"count": 0, "page": 1}

    def test_skip_params(self):
        """Skipped parameters should not be in result."""

        def dummy(self, count: int, socket):
            pass

        sig = inspect.signature(dummy)
        result = convert_params({"count": ["5"]}, sig, skip_params={"self", "socket"})
        assert result == {"count": 5}
        assert "self" not in result
        assert "socket" not in result

    def test_optional_present(self):
        """Optional parameters with values."""

        def dummy(name: Optional[str], age: int):
            pass

        sig = inspect.signature(dummy)
        result = convert_params({"name": ["John"], "age": ["30"]}, sig)
        assert result == {"name": "John", "age": 30}

    def test_optional_missing(self):
        """Optional parameters without values should default to None."""

        def dummy(name: Optional[str], age: int = 0):
            pass

        sig = inspect.signature(dummy)
        result = convert_params({"age": ["30"]}, sig)
        assert result == {"name": None, "age": 30}

    def test_list_params(self):
        """List parameters should work."""

        def dummy(tags: list[str], ids: list[int]):
            pass

        sig = inspect.signature(dummy)
        result = convert_params(
            {"tags": ["python", "web"], "ids": ["1", "2", "3"]}, sig
        )
        assert result == {"tags": ["python", "web"], "ids": [1, 2, 3]}

    def test_missing_required(self):
        """Missing required parameter should raise error."""

        def dummy(count: int):
            pass

        sig = inspect.signature(dummy)
        with pytest.raises(ValueError, match="Missing required parameter: 'count'"):
            convert_params({}, sig)

    def test_conversion_error(self):
        """Conversion error on required param should raise."""

        def dummy(count: int):
            pass

        sig = inspect.signature(dummy)
        with pytest.raises(ValueError, match="Error converting required parameter 'count'"):
            convert_params({"count": ["not-a-number"]}, sig)

    def test_conversion_error_with_default(self, caplog):
        """Conversion error with default should use default and log warning."""

        def dummy(count: int = 0, page: int = 1):
            pass

        sig = inspect.signature(dummy)

        # Should not raise, should use defaults
        result = convert_params({"count": ["not-a-number"], "page": ["also-bad"]}, sig)
        assert result == {"count": 0, "page": 1}

        # Should log warnings
        assert "Cannot convert" in caplog.text
        assert "Using default: 0" in caplog.text

    def test_conversion_error_with_optional(self, caplog):
        """Conversion error on Optional param should use None and log warning."""

        def dummy(name: Optional[str], count: Optional[int]):
            pass

        sig = inspect.signature(dummy)

        # For Optional[int], invalid value should become None
        result = convert_params({"count": ["not-a-number"], "name": ["validstr"]}, sig)
        assert result == {"count": None, "name": "validstr"}

        # Should log warning for count
        assert "Using None" in caplog.text

    def test_conversion_error_partial(self, caplog):
        """Conversion errors should not affect valid params."""

        def dummy(count: int = 0, page: int = 1, search: str = ""):
            pass

        sig = inspect.signature(dummy)

        # count fails, but page and search should work
        result = convert_params(
            {"count": ["invalid"], "page": ["5"], "search": ["hello"]},
            sig
        )
        assert result == {"count": 0, "page": 5, "search": "hello"}

        # Only count should have warning
        assert "Cannot convert" in caplog.text
        assert "'count'" in caplog.text

    def test_path_param_string(self):
        """Path params (strings, not lists) should work."""

        def dummy(user_id: int, page: int):
            pass

        sig = inspect.signature(dummy)
        # Simulate mixed path param (str) and query param (list)
        result = convert_params({"user_id": "123", "page": ["2"]}, sig)
        assert result == {"user_id": 123, "page": 2}

    def test_no_annotations(self):
        """Parameters without annotations should pass through."""

        def dummy(value):
            pass

        sig = inspect.signature(dummy)
        result = convert_params({"value": ["hello"]}, sig)
        assert result == {"value": ["hello"]}  # Pass through as-is


class TestInspection:
    """Tests for signature inspection helpers."""

    def test_should_convert_traditional_handle_params(self):
        """Traditional handle_params should not convert."""

        def handle_params(self, url, params, socket):
            pass

        assert should_convert_params(handle_params) is False

    def test_should_convert_typed_params(self):
        """Typed parameters should trigger conversion."""

        def handle_params(self, count: int, page: int):
            pass

        assert should_convert_params(handle_params) is True

    def test_should_convert_traditional_handle_event(self):
        """Traditional handle_event should not convert."""

        def handle_event(self, event, payload, socket):
            pass

        assert should_convert_params(handle_event) is False

    def test_get_skip_params_handle_params(self):
        """Skip params for handle_params should include special params."""

        def handle_params(self, url, params, socket):
            pass

        skip = get_skip_params_for_handler(handle_params, "handle_params")
        assert "self" in skip
        assert "url" in skip
        assert "socket" in skip

    def test_get_skip_params_handle_event(self):
        """Skip params for handle_event should include special params."""

        def handle_event(self, event, payload, socket):
            pass

        skip = get_skip_params_for_handler(handle_event, "handle_event")
        assert "self" in skip
        assert "event" in skip
        assert "socket" in skip

    def test_conversion_strategy_none(self):
        """Traditional signature should have 'none' strategy."""

        def handle_params(self, url, params, socket):
            pass

        strategy, obj_type = get_conversion_strategy(handle_params)
        assert strategy == "none"
        assert obj_type is None

    def test_conversion_strategy_individual(self):
        """Individual typed params should have 'individual' strategy."""

        def handle_params(self, count: int, page: int):
            pass

        strategy, obj_type = get_conversion_strategy(handle_params)
        assert strategy == "individual"
        assert obj_type is None


class TestTypedParamsDecorator:
    """Tests for typed_params decorator."""

    @pytest.mark.asyncio
    async def test_basic_conversion(self):
        """Basic parameter conversion should work."""

        @typed_params
        async def handle_params(self, count: int = 0, page: int = 1):
            return {"count": count, "page": page}

        # Simulate calling with raw params
        result = await handle_params(None, count=["5"], page=["2"])
        assert result == {"count": 5, "page": 2}

    @pytest.mark.asyncio
    async def test_with_defaults(self):
        """Defaults should work."""

        @typed_params
        async def handle_params(self, count: int = 0, page: int = 1):
            return {"count": count, "page": page}

        result = await handle_params(None, count=["5"])
        assert result == {"count": 5, "page": 1}

    @pytest.mark.asyncio
    async def test_traditional_signature_passthrough(self):
        """Traditional signature should pass through unchanged."""

        @typed_params
        async def handle_params(self, url, params, socket):
            return params

        raw_params = {"count": ["5"]}
        result = await handle_params(None, None, raw_params, None)
        assert result == raw_params  # Should not be converted

    @pytest.mark.asyncio
    async def test_preserves_function_attributes(self):
        """Decorator should preserve function name, docstring, etc."""

        @typed_params
        async def my_handler(self, count: int):
            """My docstring."""
            pass

        assert my_handler.__name__ == "my_handler"
        assert my_handler.__doc__ == "My docstring."

    @pytest.mark.asyncio
    async def test_compatible_with_other_decorators(self):
        """Should work with other decorators."""

        def my_decorator(func):
            func._decorated = True
            return func

        @my_decorator
        @typed_params
        async def handle_params(self, count: int):
            return count

        assert hasattr(handle_params, "_decorated")
        assert handle_params._decorated is True

        result = await handle_params(None, count=["42"])
        assert result == 42


class TestRealWorldScenarios:
    """Tests for real-world usage scenarios."""

    @pytest.mark.asyncio
    async def test_handle_params_scenario(self):
        """Simulate real handle_params usage."""

        class MyView:
            @typed_params
            async def handle_params(self, count: int = 0, search: Optional[str] = None):
                return {"count": count, "search": search}

        view = MyView()

        # Simulate URL: /view?count=5&search=hello
        result = await view.handle_params(count=["5"], search=["hello"])
        assert result == {"count": 5, "search": "hello"}

        # Simulate URL: /view?count=10 (no search)
        result = await view.handle_params(count=["10"])
        assert result == {"count": 10, "search": None}

    @pytest.mark.asyncio
    async def test_handle_event_scenario(self):
        """Simulate real handle_event usage with typed payload."""

        class MyView:
            @typed_params
            async def handle_event(self, event, item_id: int, enabled: bool = True):
                return {"event": event, "item_id": item_id, "enabled": enabled}

        view = MyView()

        # Simulate event with payload
        result = await view.handle_event("toggle", item_id=["5"], enabled=["true"])
        assert result == {"event": "toggle", "item_id": 5, "enabled": True}

    @pytest.mark.asyncio
    async def test_mixed_path_and_query_params(self):
        """Simulate mixed path params (str) and query params (list[str])."""

        class MyView:
            @typed_params
            async def handle_params(self, user_id: int, page: int = 1):
                return {"user_id": user_id, "page": page}

        view = MyView()

        # user_id from path (string), page from query (list)
        result = await view.handle_params(user_id="123", page=["2"])
        assert result == {"user_id": 123, "page": 2}

    @pytest.mark.asyncio
    async def test_list_parameters(self):
        """Test with list parameters (e.g., ?tags=python&tags=web)."""

        class MyView:
            @typed_params
            async def handle_params(self, tags: list[str], page: int = 1):
                return {"tags": tags, "page": page}

        view = MyView()

        result = await view.handle_params(tags=["python", "web", "liveview"], page=["2"])
        assert result == {"tags": ["python", "web", "liveview"], "page": 2}
