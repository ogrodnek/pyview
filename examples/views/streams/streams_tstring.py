from dataclasses import dataclass
from typing import TypedDict
from string.templatelib import Template

from pyview import LiveView, LiveViewSocket, Stream
from pyview.events import AutoEventDispatch, event
from pyview.template.template_view import TemplateView
from pyview.template.live_view_template import stream_for
from pyview.meta import PyViewMeta


@dataclass
class Task:
    id: int
    text: str


class TasksContext(TypedDict):
    tasks: Stream[Task]
    next_id: int


class StreamsTStringLiveView(AutoEventDispatch, TemplateView, LiveView[TasksContext]):
    """
    Streams Demo (T-String Version)

    This example demonstrates streams using Python 3.14+ t-string templates.
    """

    async def mount(self, socket: LiveViewSocket[TasksContext], session):
        initial_tasks = [
            Task(id=1, text="Learn about streams"),
            Task(id=2, text="Try append and prepend"),
            Task(id=3, text="Delete some items"),
        ]

        socket.context = TasksContext(
            tasks=Stream(initial_tasks, name="tasks"),
            next_id=4,
        )

    @event
    async def append(self, event, payload, socket: LiveViewSocket[TasksContext]):
        ctx = socket.context
        task = Task(id=ctx["next_id"], text=f"Task #{ctx['next_id']}")
        ctx["tasks"].insert(task, at=-1)
        ctx["next_id"] += 1

    @event
    async def prepend(self, event, payload, socket: LiveViewSocket[TasksContext]):
        ctx = socket.context
        task = Task(id=ctx["next_id"], text=f"Task #{ctx['next_id']}")
        ctx["tasks"].insert(task, at=0)
        ctx["next_id"] += 1

    @event
    async def delete(self, event, payload, socket: LiveViewSocket[TasksContext]):
        dom_id = payload.get("id")
        if dom_id:
            socket.context["tasks"].delete_by_id(dom_id)

    def template(self, assigns: TasksContext, meta: PyViewMeta) -> Template:
        tasks = assigns["tasks"]

        return t"""<div class="max-w-md mx-auto">
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <h1 class="text-2xl font-bold text-gray-900 mb-4">Streams (T-String)</h1>
        <p class="text-gray-600 mb-4 text-sm">
            Using Python 3.14+ t-string templates with streams.
        </p>

        <div class="flex gap-2 mb-6">
            <button phx-click="append"
                    class="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors">
                Append
            </button>
            <button phx-click="prepend"
                    class="flex-1 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors">
                Prepend
            </button>
        </div>

        <div id="tasks" phx-update="stream" class="space-y-2 min-h-[100px]">
            {stream_for(tasks, lambda dom_id, task: t'''
                <div id="{dom_id}" class="flex items-center justify-between p-3 bg-gray-50 rounded-lg border border-gray-200">
                    <span class="text-gray-800">{task.text}</span>
                    <button phx-click="delete" phx-value-id="{dom_id}"
                            class="text-gray-400 hover:text-red-500 transition-colors">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                        </svg>
                    </button>
                </div>
            ''')}
        </div>
    </div>
</div>"""
