from pyview import LiveView, LiveViewSocket
from pyview.events import event, BaseEventHandler
from dataclasses import dataclass, field
from .tasks import TaskRepository, TaskList
from pyview.vendor.ibis import filters


@filters.register
def priority_icon(priority: str) -> str:
    if priority == "high":
        return "🔥"
    if priority == "mid":
        return "👌"
    if priority == "low":
        return "🐢"
    return ""


@dataclass
class KanbanContext:
    task_repository: TaskRepository = field(default_factory=TaskRepository)
    task_lists: list[TaskList] = field(default_factory=list)

    def __post_init__(self):
        self.task_lists = self.task_repository.task_lists


class KanbanLiveView(BaseEventHandler, LiveView[KanbanContext]):
    """
    Kanban Board

    A simple Kanban board example with drag and drop
    (another hooks example showing integration w/ SortableJS).
    """

    async def mount(self, socket: LiveViewSocket[KanbanContext], session):
        socket.context = KanbanContext()
        socket.live_title = "Kanban"

    @event("task-moved")
    async def handle_task_moved(
        self, event, payload, socket: LiveViewSocket[KanbanContext]
    ):
        task_id = payload["taskId"]

        socket.context.task_repository.move_task(
            task_id, payload["from"], payload["to"], payload["order"]
        )

    @event("add_task")
    async def handle_add_task(
        self, event, payload, socket: LiveViewSocket[KanbanContext]
    ):
        target_list = payload["task_list"]
        socket.context.task_repository.random_task(target_list)
