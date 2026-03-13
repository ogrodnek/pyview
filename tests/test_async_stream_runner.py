"""
Tests for AsyncStreamRunner - critical paths only.
"""

import asyncio
from typing import Optional

import pytest

from pyview.async_stream_runner import AsyncStreamRunner
from pyview.events.info_event import InfoEvent, InfoEventScheduler


class MockScheduler(InfoEventScheduler):
    """Mock scheduler that records scheduled events."""

    def __init__(self):
        self.events: list[InfoEvent] = []

    def schedule_info(self, event: InfoEvent, seconds: float):
        self.events.append(event)

    def schedule_info_once(self, event: InfoEvent, seconds: Optional[float] = None):
        self.events.append(event)


class TestAsyncStreamRunner:
    @pytest.fixture
    def scheduler(self) -> MockScheduler:
        return MockScheduler()

    @pytest.fixture
    def runner(self, scheduler: MockScheduler) -> AsyncStreamRunner:
        return AsyncStreamRunner(scheduler)

    async def test_yields_trigger_on_yield(
        self, runner: AsyncStreamRunner, scheduler: MockScheduler
    ):
        async def gen():
            yield "first"
            yield "second"

        runner.start_stream(
            gen(),
            on_yield=lambda x: InfoEvent("item", x),
            on_done=InfoEvent("done"),
        )
        await asyncio.sleep(0.05)

        assert scheduler.events == [
            InfoEvent("item", "first"),
            InfoEvent("item", "second"),
            InfoEvent("done"),
        ]

    async def test_error_triggers_on_error(
        self, runner: AsyncStreamRunner, scheduler: MockScheduler
    ):
        async def gen():
            yield "before"
            raise ValueError("boom")

        runner.start_stream(
            gen(),
            on_yield=lambda x: InfoEvent("item", x),
            on_error=lambda e: InfoEvent("error", str(e)),
        )
        await asyncio.sleep(0.05)

        assert scheduler.events == [
            InfoEvent("item", "before"),
            InfoEvent("error", "boom"),
        ]

    async def test_cancel_triggers_on_cancel(
        self, runner: AsyncStreamRunner, scheduler: MockScheduler
    ):
        async def slow_gen():
            await asyncio.sleep(10)
            yield "never"

        task_id = runner.start_stream(
            slow_gen(),
            on_yield=lambda x: InfoEvent("item", x),
            on_cancel=InfoEvent("cancelled"),
        )

        await asyncio.sleep(0.01)
        cancelled = runner.cancel_stream(task_id)
        await asyncio.sleep(0.05)

        assert cancelled is True
        assert scheduler.events == [InfoEvent("cancelled")]

    async def test_close_awaits_generator_cleanup(
        self, runner: AsyncStreamRunner, scheduler: MockScheduler
    ):
        cleaned_up = asyncio.Event()

        async def gen_with_finally():
            try:
                while True:
                    await asyncio.sleep(10)
                    yield "never"
            finally:
                cleaned_up.set()

        runner.start_stream(
            gen_with_finally(),
            on_yield=lambda x: InfoEvent("item", x),
        )
        await asyncio.sleep(0)

        await runner.close()
        # Generator finally block must have run by the time close() returns
        assert cleaned_up.is_set()
        assert runner._stream_tasks == {}

    async def test_close_suppresses_on_cancel(
        self, runner: AsyncStreamRunner, scheduler: MockScheduler
    ):
        async def slow_gen():
            await asyncio.sleep(10)
            yield "never"

        runner.start_stream(
            slow_gen(),
            on_yield=lambda x: InfoEvent("item", x),
            on_cancel=InfoEvent("cancelled"),
        )
        await asyncio.sleep(0)

        await runner.close()
        # on_cancel should NOT fire during teardown
        assert scheduler.events == []
