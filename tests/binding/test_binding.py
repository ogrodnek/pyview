from typing import Any, Optional, Union

import pytest

from pyview.binding import Binder, ConverterRegistry, InjectableRegistry, Params, call_handler


def test_converter_primitives() -> None:
    converter = ConverterRegistry()
    assert converter.convert("1", int) == 1
    assert converter.convert(["2"], int) == 2
    assert converter.convert("2.5", float) == 2.5
    assert converter.convert(3, str) == "3"
    assert converter.convert("true", bool) is True
    assert converter.convert("0", bool) is False


def test_converter_union_and_optional() -> None:
    converter = ConverterRegistry()
    assert converter.convert("1", Optional[int]) == 1
    assert converter.convert(None, Optional[int]) is None
    assert converter.convert("5", Union[int, str]) == 5
    assert converter.convert("hello", Union[int, str]) == "hello"


def test_converter_collections() -> None:
    converter = ConverterRegistry()
    assert converter.convert(["1", "2"], list[int]) == [1, 2]
    assert converter.convert(["a", "b"], set[str]) == {"a", "b"}
    assert converter.convert(["1", "2"], tuple[int, ...]) == (1, 2)
    assert converter.convert(["1", "x"], tuple[int, str]) == (1, "x")


@pytest.mark.asyncio
async def test_binder_params_unannotated_keeps_raw() -> None:
    async def handler(params):
        return params

    params = {"page": ["1"], "tags": ["a", "b"]}
    injectables = InjectableRegistry(params=params)
    assert await call_handler(handler, injectables) == params


@pytest.mark.asyncio
async def test_binder_params_marker_keeps_raw() -> None:
    async def handler(params: Params):
        return params

    params = {"page": ["1"]}
    injectables = InjectableRegistry(params=params)
    assert await call_handler(handler, injectables) == params


@pytest.mark.asyncio
async def test_binder_params_dict_any_flattens_singletons() -> None:
    async def handler(params: dict[str, Any]):
        return params

    params = {"page": ["1"], "tags": ["a", "b"]}
    injectables = InjectableRegistry(params=params)
    assert await call_handler(handler, injectables) == {"page": "1", "tags": ["a", "b"]}


@pytest.mark.asyncio
async def test_binder_params_dict_t_converts_values() -> None:
    async def handler(params: dict[str, int]):
        return params

    params = {"page": ["2"]}
    injectables = InjectableRegistry(params=params)
    assert await call_handler(handler, injectables) == {"page": 2}


@pytest.mark.asyncio
async def test_binder_params_dict_list_str_keeps_raw() -> None:
    async def handler(params: dict[str, list[str]]):
        return params

    params = {"page": ["1"]}
    injectables = InjectableRegistry(params=params)
    assert await call_handler(handler, injectables) == params


@pytest.mark.asyncio
async def test_binder_payload_value_conversion() -> None:
    async def handler(count: int):
        return count

    injectables = InjectableRegistry(payload={"count": ["3"]})
    assert await call_handler(handler, injectables) == 3


def test_binder_injectables_by_name() -> None:
    def handler(event, socket):
        return event, socket

    injectables = InjectableRegistry(event="click", socket=object())
    args, kwargs = Binder().bind(handler, injectables)
    assert args[0] == "click"
    assert args[1] is injectables.get("socket")
    assert kwargs == {}
