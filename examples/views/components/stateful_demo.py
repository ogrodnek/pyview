"""
Stateful LiveComponents Demo

This example demonstrates stateful LiveComponents that:
- Maintain their own isolated state
- Handle their own events via phx-target={meta.myself}
- Have lifecycle methods (mount, update)
- Can communicate with parent via send_parent()

Each component instance is identified by (class, id) and persists across re-renders.
"""

from typing import TypedDict

from string.templatelib import Template

from pyview.components import LiveComponent, ComponentMeta, ComponentSocket
from pyview.events import AutoEventDispatch, event
from pyview.live_view import LiveView, LiveViewSocket
from pyview.meta import PyViewMeta
from pyview.template.live_view_template import live_component
from pyview.template.template_view import TemplateView


# =============================================================================
# Stateful LiveComponents
# =============================================================================


class CounterContext(TypedDict):
    count: int
    label: str


class Counter(LiveComponent[CounterContext]):
    """
    A stateful counter component.

    Each Counter instance maintains its own count, independent of siblings.
    Events are handled locally via phx-target={meta.myself}.
    """

    async def mount(self, socket: ComponentSocket[CounterContext]):
        """Initialize component state on first render."""
        socket.context = CounterContext(count=0, label="Counter")

    async def update(self, assigns: dict, socket: ComponentSocket[CounterContext]):
        """Handle new assigns from parent."""
        # Update label if provided
        if "label" in assigns:
            socket.context["label"] = assigns["label"]
        # Set initial count if provided (only on first update)
        if "initial" in assigns and socket.context["count"] == 0:
            socket.context["count"] = assigns["initial"]

    async def handle_event(self, event: str, payload: dict, socket: ComponentSocket[CounterContext]):
        """Handle events targeted at this component."""
        if event == "increment":
            socket.context["count"] += 1
        elif event == "decrement":
            socket.context["count"] -= 1
        elif event == "reset":
            socket.context["count"] = 0
        elif event == "notify_parent":
            # Demonstrate communication with parent
            await socket.send_parent("counter_updated", {
                "cid": socket.cid,
                "count": socket.context["count"],
            })

    def template(self, assigns: CounterContext, meta: ComponentMeta) -> Template:
        """Render the component template."""
        count = assigns["count"]
        label = assigns["label"]
        myself = meta.myself  # CID for event targeting

        return t"""
            <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
                <div class="flex items-center justify-between mb-3">
                    <h3 class="font-medium text-gray-900">{label}</h3>
                    <span class="text-xs text-gray-400">CID: {myself}</span>
                </div>

                <div class="flex items-center justify-center space-x-4 mb-4">
                    <button
                        phx-click="decrement"
                        phx-target="{myself}"
                        class="w-10 h-10 rounded-full bg-gray-100 hover:bg-gray-200 text-gray-700 font-bold transition-colors"
                    >−</button>

                    <span class="text-3xl font-bold tabular-nums w-16 text-center">{count}</span>

                    <button
                        phx-click="increment"
                        phx-target="{myself}"
                        class="w-10 h-10 rounded-full bg-blue-100 hover:bg-blue-200 text-blue-700 font-bold transition-colors"
                    >+</button>
                </div>

                <div class="flex justify-center space-x-2">
                    <button
                        phx-click="reset"
                        phx-target="{myself}"
                        class="px-3 py-1 text-sm bg-red-50 text-red-600 rounded hover:bg-red-100 transition-colors"
                    >Reset</button>
                    <button
                        phx-click="notify_parent"
                        phx-target="{myself}"
                        class="px-3 py-1 text-sm bg-green-50 text-green-600 rounded hover:bg-green-100 transition-colors"
                    >Notify Parent</button>
                </div>
            </div>
        """


class ToggleContext(TypedDict):
    enabled: bool
    label: str
    _initial_applied: bool


class Toggle(LiveComponent[ToggleContext]):
    """
    A stateful toggle component.

    Demonstrates a simple boolean state component with its own event handling.
    """

    async def mount(self, socket: ComponentSocket[ToggleContext]):
        socket.context = ToggleContext(enabled=False, label="Toggle", _initial_applied=False)

    async def update(self, assigns: dict, socket: ComponentSocket[ToggleContext]):
        if "label" in assigns:
            socket.context["label"] = assigns["label"]
        # Only apply initial value once (on first update after mount)
        if "initial" in assigns and not socket.context.get("_initial_applied"):
            socket.context["enabled"] = assigns["initial"]
            socket.context["_initial_applied"] = True

    async def handle_event(self, event: str, payload: dict, socket: ComponentSocket[ToggleContext]):
        if event == "toggle":
            socket.context["enabled"] = not socket.context["enabled"]

    def template(self, assigns: ToggleContext, meta: ComponentMeta) -> Template:
        enabled = assigns["enabled"]
        label = assigns["label"]
        myself = meta.myself

        # Dynamic classes based on state
        bg_class = "bg-blue-600" if enabled else "bg-gray-200"
        translate_class = "translate-x-5" if enabled else "translate-x-0"
        status = "ON" if enabled else "OFF"

        return t"""
            <div class="flex items-center space-x-3">
                <span class="text-sm font-medium text-gray-700">{label}</span>
                <button
                    phx-click="toggle"
                    phx-target="{myself}"
                    class="relative inline-flex h-6 w-11 items-center rounded-full transition-colors {bg_class}"
                >
                    <span class="inline-block h-4 w-4 transform rounded-full bg-white transition-transform {translate_class}"></span>
                </button>
                <span class="text-sm text-gray-500">{status}</span>
            </div>
        """


# =============================================================================
# Parent LiveView
# =============================================================================


class DemoContext(TypedDict):
    messages: list[str]
    counter_count: int


class StatefulComponentsDemo(AutoEventDispatch, TemplateView, LiveView[DemoContext]):
    """
    Stateful Components Demo

    Shows multiple independent component instances and parent-child communication.
    """

    async def mount(self, socket: LiveViewSocket[DemoContext], session):
        socket.context = DemoContext(
            messages=[],
            counter_count=3,
        )

    @event
    async def counter_updated(self, event, payload, socket: LiveViewSocket[DemoContext]):
        """Handle messages from child Counter components."""
        cid = payload.get("cid")
        count = payload.get("count")
        message = f"Counter {cid} reported count: {count}"
        socket.context["messages"].append(message)
        # Keep only last 5 messages
        socket.context["messages"] = socket.context["messages"][-5:]

    @event
    async def add_counter(self, event, payload, socket: LiveViewSocket[DemoContext]):
        """Add another counter."""
        socket.context["counter_count"] += 1

    @event
    async def clear_messages(self, event, payload, socket: LiveViewSocket[DemoContext]):
        """Clear all messages."""
        socket.context["messages"] = []

    def template(self, assigns: DemoContext, meta: PyViewMeta) -> Template:
        messages = assigns["messages"]
        counter_count = assigns["counter_count"]

        # Generate counter components dynamically
        counters = [
            live_component(Counter, id=f"counter-{i}", label=f"Counter {i+1}", initial=i * 10)
            for i in range(counter_count)
        ]

        # Messages display
        message_items = [
            t'<li class="text-sm text-gray-600">{msg}</li>'
            for msg in messages
        ] if messages else [t'<li class="text-sm text-gray-400 italic">No messages yet</li>']

        return t"""
            <div class="max-w-4xl mx-auto space-y-6">
                <div class="text-center mb-8">
                    <h1 class="text-3xl font-bold text-gray-900">Stateful LiveComponents</h1>
                    <p class="mt-2 text-gray-600">
                        Independent components with isolated state and event handling
                    </p>
                </div>

                <!-- Counters Section -->
                <div class="bg-gray-50 rounded-lg p-6">
                    <div class="flex items-center justify-between mb-4">
                        <h2 class="text-lg font-semibold text-gray-800">Counter Components</h2>
                        <button
                            phx-click="add_counter"
                            class="px-3 py-1 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 transition-colors"
                        >+ Add Counter</button>
                    </div>
                    <p class="text-sm text-gray-500 mb-4">
                        Each counter is an independent component with its own state.
                        Click "Notify Parent" to see parent-child communication.
                    </p>
                    <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                        {counters}
                    </div>
                </div>

                <!-- Toggles Section -->
                <div class="bg-gray-50 rounded-lg p-6">
                    <h2 class="text-lg font-semibold text-gray-800 mb-4">Toggle Components</h2>
                    <p class="text-sm text-gray-500 mb-4">
                        Simple boolean state components. Each toggle maintains its own state.
                    </p>
                    <div class="space-y-3">
                        {live_component(Toggle, id="toggle-notifications", label="Notifications")}
                        {live_component(Toggle, id="toggle-dark-mode", label="Dark Mode")}
                        {live_component(Toggle, id="toggle-sound", label="Sound Effects", initial=True)}
                    </div>
                </div>

                <!-- Messages from Components -->
                <div class="bg-gray-50 rounded-lg p-6">
                    <div class="flex items-center justify-between mb-4">
                        <h2 class="text-lg font-semibold text-gray-800">Messages from Components</h2>
                        <button
                            phx-click="clear_messages"
                            class="px-3 py-1 bg-gray-200 text-gray-700 text-sm rounded hover:bg-gray-300 transition-colors"
                        >Clear</button>
                    </div>
                    <p class="text-sm text-gray-500 mb-4">
                        Components can send events to their parent via send_parent().
                    </p>
                    <ul class="space-y-1 bg-white rounded border border-gray-200 p-3 min-h-[100px]">
                        {message_items}
                    </ul>
                </div>

                <!-- How It Works -->
                <div class="bg-blue-50 rounded-lg p-6">
                    <h2 class="text-lg font-semibold text-blue-800 mb-3">How It Works</h2>
                    <div class="text-sm text-blue-700 space-y-2">
                        <p><strong>1. Component Definition:</strong> Extend LiveComponent with mount(), update(), handle_event(), and template()</p>
                        <p><strong>2. Event Targeting:</strong> Use phx-target="{{meta.myself}}" to route events to the component</p>
                        <p><strong>3. State Isolation:</strong> Each component instance has its own context, stored externally by CID</p>
                        <p><strong>4. Parent Communication:</strong> Components can call send_parent() to send events up</p>
                    </div>
                </div>
            </div>
        """
