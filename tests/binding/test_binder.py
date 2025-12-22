"""Tests for Binder core."""
from dataclasses import dataclass
from typing import Optional, Union
from unittest.mock import MagicMock

import pytest

from pyview.binding import BindContext, Params
from pyview.binding.binder import Binder


class TestBinder:
    """Test the core Binder class."""

    @pytest.fixture
    def binder(self) -> Binder:
        return Binder()

    @pytest.fixture
    def ctx(self) -> BindContext:
        return BindContext(
            params=Params({"page": ["5"], "name": ["alice"], "tags": ["a", "b"]}),
            payload={"amount": 10, "value": {"nested": "data"}},
            url=MagicMock(),
            socket=MagicMock(),
            event="test",
        )

    # --- Basic binding from params ---

    def test_bind_int_from_params(self, binder: Binder, ctx: BindContext):
        async def handler(page: int):
            pass

        result = binder.bind(handler, ctx)
        assert result.success
        assert result.bound_args["page"] == 5

    def test_bind_str_from_params(self, binder: Binder, ctx: BindContext):
        async def handler(name: str):
            pass

        result = binder.bind(handler, ctx)
        assert result.success
        assert result.bound_args["name"] == "alice"

    def test_bind_list_from_params(self, binder: Binder, ctx: BindContext):
        async def handler(tags: list[str]):
            pass

        result = binder.bind(handler, ctx)
        assert result.success
        assert result.bound_args["tags"] == ["a", "b"]

    # --- Optional and defaults ---

    def test_bind_optional_missing_returns_none(self, binder: Binder, ctx: BindContext):
        async def handler(missing: Optional[int]):
            pass

        result = binder.bind(handler, ctx)
        assert result.success
        assert result.bound_args["missing"] is None

    def test_bind_with_default(self, binder: Binder, ctx: BindContext):
        async def handler(missing: int = 42):
            pass

        result = binder.bind(handler, ctx)
        assert result.success
        assert result.bound_args["missing"] == 42

    def test_bind_optional_with_default(self, binder: Binder, ctx: BindContext):
        async def handler(missing: Optional[int] = 100):
            pass

        result = binder.bind(handler, ctx)
        assert result.success
        assert result.bound_args["missing"] == 100

    # --- Injectable binding ---

    def test_bind_socket_by_name(self, binder: Binder, ctx: BindContext):
        async def handler(socket):
            pass

        result = binder.bind(handler, ctx)
        assert result.success
        assert result.bound_args["socket"] is ctx.socket

    def test_bind_payload(self, binder: Binder, ctx: BindContext):
        async def handler(payload: dict):
            pass

        result = binder.bind(handler, ctx)
        assert result.success
        assert result.bound_args["payload"] == {"amount": 10, "value": {"nested": "data"}}

    def test_bind_event(self, binder: Binder, ctx: BindContext):
        async def handler(event: str):
            pass

        result = binder.bind(handler, ctx)
        assert result.success
        assert result.bound_args["event"] == "test"

    def test_bind_url(self, binder: Binder, ctx: BindContext):
        async def handler(url):
            pass

        result = binder.bind(handler, ctx)
        assert result.success
        assert result.bound_args["url"] is ctx.url

    def test_bind_params_as_Params(self, binder: Binder, ctx: BindContext):
        async def handler(params: Params):
            pass

        result = binder.bind(handler, ctx)
        assert result.success
        assert isinstance(result.bound_args["params"], Params)

    # --- Payload values ---

    def test_bind_from_payload(self, binder: Binder, ctx: BindContext):
        async def handler(amount: int):
            pass

        result = binder.bind(handler, ctx)
        assert result.success
        assert result.bound_args["amount"] == 10

    def test_params_takes_precedence_over_payload(self, binder: Binder, ctx: BindContext):
        # Both params and payload have "page"
        assert ctx.payload is not None
        ctx.payload["page"] = 999

        async def handler(page: int):
            pass

        result = binder.bind(handler, ctx)
        assert result.success
        assert result.bound_args["page"] == 5  # From params, not payload

    # --- Error cases ---

    def test_missing_required_param_error(self, binder: Binder, ctx: BindContext):
        async def handler(required: int):
            pass

        result = binder.bind(handler, ctx)
        assert not result.success
        assert len(result.errors) == 1
        assert result.errors[0].name == "required"
        assert "missing" in result.errors[0].reason

    def test_conversion_error(self, binder: Binder, ctx: BindContext):
        ctx.params = Params({"page": ["not-a-number"]})

        async def handler(page: int):
            pass

        result = binder.bind(handler, ctx)
        assert not result.success
        assert len(result.errors) == 1
        assert result.errors[0].name == "page"

    def test_multiple_errors(self, binder: Binder, ctx: BindContext):
        async def handler(required1: int, required2: int):
            pass

        result = binder.bind(handler, ctx)
        assert not result.success
        assert len(result.errors) == 2

    # --- Method binding (skip self) ---

    def test_skip_self_parameter(self, binder: Binder, ctx: BindContext):
        class MyView:
            async def handler(self, page: int):
                pass

        result = binder.bind(MyView().handler, ctx)
        assert result.success
        assert "self" not in result.bound_args
        assert result.bound_args["page"] == 5

    # --- Mixed parameters ---

    def test_mixed_injectable_and_params(self, binder: Binder, ctx: BindContext):
        async def handler(socket, page: int, name: str = "default"):
            pass

        result = binder.bind(handler, ctx)
        assert result.success
        assert result.bound_args["socket"] is ctx.socket
        assert result.bound_args["page"] == 5
        assert result.bound_args["name"] == "alice"

    def test_complex_signature(self, binder: Binder, ctx: BindContext):
        async def handler(
            socket,
            page: int,
            tags: list[str],
            filter: Optional[str] = None,
            limit: int = 10,
        ):
            pass

        result = binder.bind(handler, ctx)
        assert result.success
        assert result.bound_args["socket"] is ctx.socket
        assert result.bound_args["page"] == 5
        assert result.bound_args["tags"] == ["a", "b"]
        assert result.bound_args["filter"] is None
        assert result.bound_args["limit"] == 10

    # --- Union types ---

    def test_union_type(self, binder: Binder, ctx: BindContext):
        async def handler(page: Union[int, str]):
            pass

        result = binder.bind(handler, ctx)
        assert result.success
        assert result.bound_args["page"] == 5  # Converted to int

    # --- Dataclass parameter binding ---

    def test_bind_dataclass_from_params(self, binder: Binder, ctx: BindContext):
        @dataclass
        class PagingParams:
            page: int
            name: str

        async def handler(paging: PagingParams):
            pass

        result = binder.bind(handler, ctx)
        assert result.success
        assert result.bound_args["paging"] == PagingParams(page=5, name="alice")

    def test_bind_dataclass_with_optional_fields(self, binder: Binder, ctx: BindContext):
        @dataclass
        class FilterParams:
            page: Optional[int] = None
            limit: Optional[int] = None

        async def handler(filters: FilterParams):
            pass

        result = binder.bind(handler, ctx)
        assert result.success
        assert result.bound_args["filters"] == FilterParams(page=5, limit=None)

    def test_bind_dataclass_with_defaults(self, binder: Binder, ctx: BindContext):
        @dataclass
        class PagingParams:
            page: int = 1
            perPage: int = 10

        async def handler(paging: PagingParams):
            pass

        result = binder.bind(handler, ctx)
        assert result.success
        assert result.bound_args["paging"] == PagingParams(page=5, perPage=10)

    def test_bind_dataclass_with_socket(self, binder: Binder, ctx: BindContext):
        @dataclass
        class PagingParams:
            page: int = 1
            perPage: int = 10

        async def handler(paging: PagingParams, socket):
            pass

        result = binder.bind(handler, ctx)
        assert result.success
        assert result.bound_args["paging"] == PagingParams(page=5, perPage=10)
        assert result.bound_args["socket"] is ctx.socket

    def test_bind_dataclass_from_payload(self, binder: Binder):
        @dataclass
        class EventData:
            amount: int
            description: str = "default"

        ctx = BindContext(
            params=Params({}),
            payload={"amount": 42, "description": "test"},
            url=None,
            socket=MagicMock(),
            event="test",
        )

        async def handler(data: EventData):
            pass

        result = binder.bind(handler, ctx)
        assert result.success
        assert result.bound_args["data"] == EventData(amount=42, description="test")
