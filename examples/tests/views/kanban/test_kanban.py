"""Tests for kanban LiveView example."""

import pytest

from pyview.testing import TestSocket
from views.kanban.kanban import KanbanContext, KanbanLiveView
from views.kanban.tasks import Task, TaskStatus


class TestKanbanLiveViewMount:
    """Tests for KanbanLiveView mount lifecycle."""

    @pytest.mark.asyncio
    async def test_mount_initializes_context(self):
        """Test that mount initializes the kanban context."""
        view = KanbanLiveView()
        socket = TestSocket[KanbanContext]()

        await view.mount(socket, session={})

        assert socket.context is not None
        assert hasattr(socket.context, "task_repository")
        assert hasattr(socket.context, "task_lists")

    @pytest.mark.asyncio
    async def test_mount_loads_task_lists(self):
        """Test that mount loads the three task lists."""
        view = KanbanLiveView()
        socket = TestSocket[KanbanContext]()

        await view.mount(socket, session={})

        assert len(socket.context.task_lists) == 3
        statuses = [task_list.title for task_list in socket.context.task_lists]
        assert "Backlog" in statuses
        assert "In Progress" in statuses
        assert "Done" in statuses


class TestKanbanLiveViewTaskMovement:
    """Tests for moving tasks between lists."""

    @pytest.mark.asyncio
    async def test_move_task_to_different_list(self):
        """Test moving a task from one list to another."""
        view = KanbanLiveView()
        socket = TestSocket[KanbanContext]()
        await view.mount(socket, session={})

        # Get a task from backlog
        backlog_tasks = socket.context.task_repository._task_lists_by_status["Backlog"].tasks
        if not backlog_tasks:
            pytest.skip("No tasks in backlog for this test")

        task = backlog_tasks[0]
        task_id = task.id
        original_status = task.status

        # Move task to "In Progress"
        payload = {
            "taskId": task_id,
            "from": original_status,
            "to": "In Progress",
            "order": 0,
        }

        await view.handle_task_moved("task-moved", payload, socket)

        # Verify task moved
        moved_task = socket.context.task_repository._tasks_by_id.get(task_id)
        assert moved_task is not None
        assert moved_task.status == "In Progress"

    @pytest.mark.asyncio
    async def test_task_moved_event_handler(self):
        """Test that task-moved event is properly handled."""
        view = KanbanLiveView()
        socket = TestSocket[KanbanContext]()
        await view.mount(socket, session={})

        # Get first task from any list
        task = None
        for task_list in socket.context.task_lists:
            if task_list.tasks:
                task = task_list.tasks[0]
                break

        if not task:
            pytest.skip("No tasks available for testing")

        original_count_in_progress = len(
            socket.context.task_repository._task_lists_by_status["In Progress"].tasks
        )

        # Move to In Progress
        payload = {
            "taskId": task.id,
            "from": task.status,
            "to": "In Progress",
            "order": 0,
        }

        await view.handle_task_moved("task-moved", payload, socket)

        # Verify list sizes changed appropriately
        new_count_in_progress = len(
            socket.context.task_repository._task_lists_by_status["In Progress"].tasks
        )

        if task.status != "In Progress":
            assert new_count_in_progress == original_count_in_progress + 1


class TestKanbanLiveViewAddTask:
    """Tests for adding tasks to lists."""

    @pytest.mark.asyncio
    async def test_add_task_to_backlog(self):
        """Test adding a random task to the backlog."""
        view = KanbanLiveView()
        socket = TestSocket[KanbanContext]()
        await view.mount(socket, session={})

        original_count = len(
            socket.context.task_repository._task_lists_by_status["Backlog"].tasks
        )

        payload = {"task_list": "Backlog"}
        await view.handle_add_task("add_task", payload, socket)

        new_count = len(socket.context.task_repository._task_lists_by_status["Backlog"].tasks)
        assert new_count == original_count + 1

    @pytest.mark.asyncio
    async def test_add_task_to_in_progress(self):
        """Test adding a random task to In Progress."""
        view = KanbanLiveView()
        socket = TestSocket[KanbanContext]()
        await view.mount(socket, session={})

        original_count = len(
            socket.context.task_repository._task_lists_by_status["In Progress"].tasks
        )

        payload = {"task_list": "In Progress"}
        await view.handle_add_task("add_task", payload, socket)

        new_count = len(
            socket.context.task_repository._task_lists_by_status["In Progress"].tasks
        )
        assert new_count == original_count + 1

    @pytest.mark.asyncio
    async def test_add_task_to_done(self):
        """Test adding a random task to Done."""
        view = KanbanLiveView()
        socket = TestSocket[KanbanContext]()
        await view.mount(socket, session={})

        original_count = len(socket.context.task_repository._task_lists_by_status["Done"].tasks)

        payload = {"task_list": "Done"}
        await view.handle_add_task("add_task", payload, socket)

        new_count = len(socket.context.task_repository._task_lists_by_status["Done"].tasks)
        assert new_count == original_count + 1


class TestKanbanLiveViewEventDecorators:
    """Tests for BaseEventHandler decorator usage."""

    @pytest.mark.asyncio
    async def test_event_decorator_routes_to_handler(self):
        """Test that @event decorator properly routes events."""
        view = KanbanLiveView()
        socket = TestSocket[KanbanContext]()
        await view.mount(socket, session={})

        # Get a task to work with
        task = None
        for task_list in socket.context.task_lists:
            if task_list.tasks:
                task = task_list.tasks[0]
                break

        if not task:
            pytest.skip("No tasks available")

        payload = {
            "taskId": task.id,
            "from": task.status,
            "to": "Done",
            "order": 0,
        }

        # This should work through the @event decorator routing
        await view.handle_event("task-moved", payload, socket)

        # Verify it was handled
        moved_task = socket.context.task_repository._tasks_by_id.get(task.id)
        assert moved_task.status == "Done"


class TestKanbanLiveViewIntegration:
    """Integration tests for full KanbanLiveView workflow."""

    @pytest.mark.asyncio
    async def test_complete_task_workflow(self):
        """Test a complete workflow: add task, move it through stages."""
        view = KanbanLiveView()
        socket = TestSocket[KanbanContext]()

        # Mount
        await view.mount(socket, session={})

        # Add a task to Backlog
        await view.handle_add_task("add_task", {"task_list": "Backlog"}, socket)

        # Get the newly added task
        backlog = socket.context.task_repository._task_lists_by_status["Backlog"]
        new_task = backlog.tasks[-1]  # Last added
        task_id = new_task.id

        # Move to In Progress
        await view.handle_task_moved(
            "task-moved",
            {"taskId": task_id, "from": "Backlog", "to": "In Progress", "order": 0},
            socket,
        )

        # Verify in In Progress
        task = socket.context.task_repository._tasks_by_id[task_id]
        assert task.status == "In Progress"

        # Move to Done
        await view.handle_task_moved(
            "task-moved",
            {"taskId": task_id, "from": "In Progress", "to": "Done", "order": 0},
            socket,
        )

        # Verify in Done
        task = socket.context.task_repository._tasks_by_id[task_id]
        assert task.status == "Done"
