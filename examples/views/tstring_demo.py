"""
T-String Template Demo View.
Demonstrates the new t-string template system for PyView.
"""
from dataclasses import dataclass
from typing import List
from pyview.live_view import LiveView
from pyview.template.template_view import TemplateView
from pyview.template.tstring_polyfill import t, Template
from pyview.meta import PyViewMeta


@dataclass
class TodoItem:
    id: int
    text: str
    completed: bool = False


@dataclass 
class TStringDemoContext:
    todos: List[TodoItem]
    new_todo: str = ""
    filter: str = "all"  # "all", "active", "completed"


class TStringDemoLiveView(TemplateView, LiveView[TStringDemoContext]):
    """Demo view showing t-string templates in action."""
    
    async def mount(self, socket, session):
        socket.context = TStringDemoContext(
            todos=[
                TodoItem(1, "Learn PyView", True),
                TodoItem(2, "Try t-string templates", False),
                TodoItem(3, "Build something awesome", False),
            ]
        )
    
    async def handle_event(self, event, params, socket):
        if event == "add_todo":
            text = params.get("new_todo", "").strip()
            if text:
                new_id = max([todo.id for todo in socket.context.todos], default=0) + 1
                socket.context.todos.append(TodoItem(new_id, text))
                socket.context.new_todo = ""
        
        elif event == "toggle_todo":
            todo_id = int(params.get("id"))
            for todo in socket.context.todos:
                if todo.id == todo_id:
                    todo.completed = not todo.completed
                    break
        
        elif event == "delete_todo":
            todo_id = int(params.get("id"))
            socket.context.todos = [t for t in socket.context.todos if t.id != todo_id]
        
        elif event == "set_filter":
            socket.context.filter = params.get("filter", "all")
        
        elif event == "clear_completed":
            socket.context.todos = [t for t in socket.context.todos if not t.completed]
    
    def filtered_todos(self, todos: List[TodoItem], filter_type: str) -> List[TodoItem]:
        """Filter todos based on current filter."""
        if filter_type == "active":
            return [todo for todo in todos if not todo.completed]
        elif filter_type == "completed":
            return [todo for todo in todos if todo.completed]
        else:
            return todos
    
    def todo_item(self, todo: TodoItem):
        """Template for individual todo item."""
        checkbox_class = "text-green-500" if todo.completed else "text-gray-400"
        text_class = "line-through text-gray-500" if todo.completed else "text-gray-900"
        
        return t("""
        <li class="flex items-center p-3 border-b border-gray-200 group hover:bg-gray-50">
            <button phx-click="toggle_todo" phx-value-id="{id}" 
                    class="mr-3 p-1 rounded-full hover:bg-gray-200 transition-colors">
                <svg class="w-5 h-5 {checkbox_class}" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
                </svg>
            </button>
            <span class="flex-1 {text_class}">{text}</span>
            <button phx-click="delete_todo" phx-value-id="{id}"
                    class="opacity-0 group-hover:opacity-100 ml-2 p-1 text-red-500 hover:bg-red-100 rounded transition-all">
                <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
                </svg>
            </button>
        </li>
        """, 
        id=todo.id, 
        checkbox_class=checkbox_class, 
        text_class=text_class, 
        text=todo.text
        )
    
    def filter_button(self, filter_name: str, label: str, current_filter: str):
        """Template for filter buttons."""
        is_active = filter_name == current_filter
        button_class = ("bg-pyview-pink-500 text-white" if is_active 
                       else "bg-white text-gray-700 hover:bg-gray-50")
        
        return t("""
        <button phx-click="set_filter" phx-value-filter="{filter_name}"
                class="px-4 py-2 text-sm font-medium border border-gray-300 {button_class} transition-colors">
            {label}
        </button>
        """, 
        filter_name=filter_name, 
        button_class=button_class, 
        label=label
        )
    
    def template(self, assigns: TStringDemoContext, meta: PyViewMeta) -> Template:
        # Clean typed access to assigns!
        todos = assigns.todos
        filter_type = assigns.filter
        new_todo = assigns.new_todo
        
        filtered_todos = self.filtered_todos(todos, filter_type)
        active_count = len([t for t in todos if not t.completed])
        completed_count = len([t for t in todos if t.completed])
        
        # Generate todo items
        todo_items = [self.todo_item(todo) for todo in filtered_todos]
        
        # Generate filter buttons
        all_button = self.filter_button("all", "All", filter_type)
        active_button = self.filter_button("active", "Active", filter_type)
        completed_button = self.filter_button("completed", "Completed", filter_type)
        
        # Show clear completed button only if there are completed items
        clear_button = (t("""
        <button phx-click="clear_completed" 
                class="text-sm text-red-600 hover:text-red-800 transition-colors">
            Clear Completed ({count})
        </button>
        """, count=completed_count) if completed_count > 0 else t(""))
        
        return t("""
        <div class="max-w-2xl mx-auto">
            <div class="bg-white rounded-lg shadow-sm border border-gray-200">
                <!-- Header -->
                <div class="p-6 border-b border-gray-200">
                    <h1 class="text-2xl font-display font-semibold text-gray-900 mb-4">
                        T-String Templates Demo
                    </h1>
                    <p class="text-gray-600 mb-6">
                        This todo app demonstrates PyView's new t-string template system. 
                        Notice how templates are written in Python code with full type safety!
                    </p>
                    
                    <!-- Add Todo Form -->
                    <form phx-submit="add_todo" class="flex gap-2">
                        <input type="text" name="new_todo" value="{new_todo}" 
                               placeholder="Add a new todo..." 
                               class="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-pyview-pink-500 focus:border-transparent" />
                        <button type="submit" 
                                class="px-6 py-2 bg-pyview-pink-500 text-white font-medium rounded-lg hover:bg-pyview-pink-600 transition-colors">
                            Add
                        </button>
                    </form>
                </div>
                
                <!-- Filter Buttons -->
                <div class="p-4 border-b border-gray-200 flex items-center justify-between">
                    <div class="flex rounded-lg overflow-hidden border border-gray-300">
                        {all_button}
                        {active_button}
                        {completed_button}
                    </div>
                    <div class="text-sm text-gray-500">
                        {active_count} active · {completed_count} completed
                    </div>
                </div>
                
                <!-- Todo List -->
                <div class="min-h-[200px]">
                    {todo_list}
                </div>
                
                <!-- Footer -->
                <div class="p-4 border-t border-gray-200 flex justify-between items-center">
                    <div class="text-sm text-gray-500">
                        {total_count} total items
                    </div>
                    {clear_button}
                </div>
            </div>
            
            <!-- Features Highlight -->
            <div class="mt-8 p-6 bg-blue-50 rounded-lg border border-blue-200">
                <h3 class="text-lg font-semibold text-blue-900 mb-3">
                    T-String Template Features
                </h3>
                <div class="grid md:grid-cols-2 gap-4 text-sm text-blue-800">
                    <div class="flex items-start">
                        <span class="text-green-600 mr-2">✓</span>
                        <span>Full Python expressions in templates</span>
                    </div>
                    <div class="flex items-start">
                        <span class="text-green-600 mr-2">✓</span>
                        <span>Type safety and IDE support</span>
                    </div>
                    <div class="flex items-start">
                        <span class="text-green-600 mr-2">✓</span>
                        <span>Helper methods for template composition</span>
                    </div>
                    <div class="flex items-start">
                        <span class="text-green-600 mr-2">✓</span>
                        <span>No separate .html files needed</span>
                    </div>
                </div>
            </div>
        </div>
        """,
        new_todo=new_todo,
        all_button=all_button,
        active_button=active_button, 
        completed_button=completed_button,
        active_count=active_count,
        completed_count=completed_count,
        todo_list=t("<ul>{items}</ul>", items=todo_items) if todo_items else t('<div class="p-8 text-center text-gray-500">No todos yet. Add one above!</div>'),
        total_count=len(todos),
        clear_button=clear_button
        )