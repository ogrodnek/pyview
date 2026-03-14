import asyncio
import logging
import uuid
from typing import Any, AsyncGenerator, Callable, Optional

from pyview.events.info_event import InfoEvent, InfoEventScheduler

logger = logging.getLogger(__name__)


class AsyncStreamRunner:
    def __init__(self, scheduler: InfoEventScheduler):
        self._stream_tasks: dict[str, asyncio.Task] = {}
        self._scheduler = scheduler
        self._closing = False

    def start_stream(
        self,
        gen: AsyncGenerator[Any, None],
        *,
        on_yield: Callable[[Any], InfoEvent],
        on_done: Optional[InfoEvent] = None,
        on_error: Optional[Callable[[Exception], InfoEvent]] = None,
        on_cancel: Optional[InfoEvent] = None,
    ) -> str:
        """
        Run `gen` in the background, returning an op_id you can later use
        to cancel.  Hooks:

        - on_yield(item)  → scheduled per chunk
        - on_done        → scheduled once at normal completion
        - on_error(exc)  → scheduled on unexpected exception
        - on_cancel      → scheduled if the task is cancelled
        """
        task_id = uuid.uuid4().hex

        async def driver():
            try:
                async for item in gen:
                    self._scheduler.schedule_info_once(on_yield(item))
            except asyncio.CancelledError:
                if on_cancel and not self._closing:
                    self._scheduler.schedule_info_once(on_cancel)
            except Exception as exc:
                if on_error:
                    self._scheduler.schedule_info_once(on_error(exc))
                else:
                    logging.exception(f"Error in stream {task_id}", exc_info=True)
            else:
                if on_done:
                    self._scheduler.schedule_info_once(on_done)
            finally:
                self._stream_tasks.pop(task_id, None)

        task = asyncio.create_task(driver())
        self._stream_tasks[task_id] = task
        return task_id

    def cancel_stream(self, task_id: str) -> bool:
        """
        Cancel a running stream.  Returns True if a task was found & cancelled.
        """
        task = self._stream_tasks.get(task_id)
        if not task:
            return False
        task.cancel()
        return True

    async def close(self) -> None:
        """Cancel all running stream tasks."""
        self._closing = True
        for task in self._stream_tasks.values():
            task.cancel()
