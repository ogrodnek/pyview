import random
import uuid
from dataclasses import dataclass, field
from typing import Literal, Optional

TaskStatus = Literal["Backlog", "In Progress", "Done"]


@dataclass
class Task:
    title: str
    description: str
    category: str
    status: TaskStatus
    priority: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    avatar: str = field(
        default_factory=lambda: "https://avatar.iran.liara.run/public?t="
        + str(random.randint(1, 5))
    )


@dataclass
class TaskList:
    title: TaskStatus
    color: str
    wip_limit: Optional[int] = None
    tasks: list[Task] = field(default_factory=list)

    @property
    def wip_exceeded(self):
        return self.wip_limit is not None and len(self.tasks) > self.wip_limit


class TaskRepository:
    """
    Demo task repository that loads tasks from a hardcoded list and allows moving tasks between lists
    in memory.
    """

    _task_lists_by_status: dict[TaskStatus, TaskList]
    _tasks_by_id: dict[str, Task] = {}

    def __init__(self):
        self._task_lists_by_status = {
            t.title: t
            for t in [
                TaskList("Backlog", "#FFC5A1", wip_limit=5),
                TaskList("In Progress", "#BFA2DB", wip_limit=3),
                TaskList("Done", "#A3D9B1"),
            ]
        }

        for task in load_tasks():
            self.add_task(task, task.status)

    @property
    def task_lists(self):
        return [tl for tl in self._task_lists_by_status.values()]

    def add_task(self, task: Task, status: TaskStatus):
        self._tasks_by_id[task.id] = task
        self._task_lists_by_status[status].tasks.append(task)

    def move_task(
        self, task_id: str, from_status: TaskStatus, to_status: TaskStatus, order
    ):
        from_list = self._task_lists_by_status[from_status]
        to_list = self._task_lists_by_status[to_status]

        task = self._tasks_by_id[task_id]

        from_list.tasks.remove(task)
        to_list.tasks.append(task)

        task_order = {o["id"]: o["order"] for o in order}
        to_list.tasks = sorted(to_list.tasks, key=lambda t: task_order[t.id])

    def random_task(self, status: TaskStatus) -> Task:
        task = Task(
            title="Task Title",
            description="Task Description",
            category=random.choice(["Marketing", "Design", "Development"]),
            status=status,
            priority=random.choice(["high", "mid", "low"]),
        )

        self.add_task(task, status)
        return task


def load_tasks() -> list[Task]:
    tasks = [
        Task(
            "Define Core Features",
            "Decide on essential features like workout tracking, progress visualization, and personalized workout plans. Include social features like challenges and leaderboards.",
            "Feature Planning",
            "Backlog",
            "high",
        ),
        Task(
            "Design User Interface",
            "Create a clean and intuitive UI that appeals to fitness enthusiasts. Focus on ease of use, with clear buttons and navigation.",
            "Design",
            "Backlog",
            "high",
        ),
        Task(
            "Plan a Launch Party",
            "Organize a launch party to celebrate the app's release. Decide on the venue, guest list, and entertainment. Keep it simple and within budget.",
            "Event Planning",
            "Backlog",
            "low",
        ),
        Task(
            "Build a Prototype",
            "Develop a working prototype with the core features implemented. Test the prototype for usability and functionality.",
            "Development",
            "In Progress",
            "high",
        ),
        Task(
            "Conduct User Testing",
            "Recruit a group of beta testers to try out the app. Gather feedback on the user experience and feature set.",
            "Testing",
            "In Progress",
            "mid",
        ),
        Task(
            "Develop a Marketing Strategy",
            "Plan a launch campaign that includes social media ads, influencer partnerships, and email marketing. Offer limited-time discounts for early adopters.",
            "Marketing",
            "Done",
            "high",
        ),
        Task(
            "Integrate Payment System",
            "Set up a secure payment gateway for in-app purchases and subscriptions. Ensure compliance with payment regulations.",
            "Development",
            "Done",
            "high",
        ),
        Task(
            "Launch an App Store Page",
            "Create an app store listing with screenshots, descriptions, and promotional videos. Optimize the page for search visibility and downloads.",
            "Launch",
            "Done",
            "mid",
        ),
    ]

    return tasks
