from typing import TypedDict

from pyview.events import AutoEventDispatch, event
from pyview.live_view import LiveView, LiveViewSocket
from pyview.meta import PyViewMeta
from pyview.template.template_view import TemplateView
from string.templatelib import Template


class CountContext(TypedDict):
    count: int


class CounterAutoDispatchLiveView(AutoEventDispatch, TemplateView, LiveView[CountContext]):
    """
    Basic Counter (Auto-Dispatch Version)

    This example demonstrates the new AutoEventDispatch feature which allows you to:
    1. Use @event without explicit names (method name becomes event name)
    2. Reference methods directly in templates: phx-click={self.increment}
    3. Cleaner handler signatures without the 'event' parameter

    Compare this to count_tstring.py to see the differences!
    """

    async def mount(self, socket: LiveViewSocket[CountContext], session):
        socket.context = CountContext({"count": 0})

    # Notice: @event without arguments - uses method name "increment"
    @event
    async def increment(self, payload, socket: LiveViewSocket[CountContext]):
        """Increment the counter. Notice the cleaner signature (no 'event' param)."""
        socket.context["count"] += 1

    # You can also use @event() with parentheses
    @event()
    async def decrement(self, payload, socket: LiveViewSocket[CountContext]):
        """Decrement the counter."""
        socket.context["count"] -= 1

    # Or use a custom event name if you prefer
    @event("reset-counter")
    async def reset(self, payload, socket: LiveViewSocket[CountContext]):
        """Reset counter to zero."""
        socket.context["count"] = 0

    async def handle_params(self, url, params, socket: LiveViewSocket[CountContext]):
        if "c" in params:
            socket.context["count"] = int(params["c"][0])

    def button(self, label: str, event_ref, style: str = "primary") -> Template:
        """
        Reusable button component.

        event_ref can be:
        - A method reference: self.increment (auto-converts to "increment")
        - A string: "custom-event"
        """
        base = "w-16 h-16 rounded-full text-2xl font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
        if style == "primary":
            classes = f"{base} bg-blue-600 text-white hover:bg-blue-700"
        elif style == "secondary":
            classes = f"{base} bg-white border-2 border-gray-300 text-gray-700 hover:bg-gray-50 hover:border-gray-400"
        else:  # danger
            classes = f"{base} bg-red-600 text-white hover:bg-red-700"

        return t"""<button phx-click="{event_ref}" class="{classes}">{label}</button>"""

    def template(self, assigns: CountContext, meta: PyViewMeta) -> Template:
        count = assigns["count"]
        return t"""<div class="max-w-md mx-auto">
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-8">
        <h1 class="text-3xl font-bold text-center text-gray-900 mb-4">Auto-Dispatch Counter</h1>
        <p class="text-center text-sm text-gray-600 mb-8">
            Using <code class="px-2 py-1 bg-blue-50 rounded text-xs">phx-click={{'{self.increment}'}}</code>
        </p>

        <div class="text-center mb-8">
            <div class="text-6xl font-bold text-gray-800 tabular-nums">{count}</div>
        </div>

        <div class="flex items-center justify-center space-x-4">
            {self.button("−", self.decrement, "secondary")}
            {self.button("+", self.increment, "primary")}
        </div>

        <div class="mt-6 text-center">
            {self.button("Reset", self.reset, "danger")}
        </div>

        <div class="mt-8 text-center">
            <p class="text-sm text-gray-500">
                Try changing the URL to <code class="px-2 py-1 bg-gray-100 rounded text-xs">/counter_auto_dispatch?c=100</code>
            </p>
        </div>

        <div class="mt-6 p-4 bg-blue-50 rounded-lg">
            <h3 class="text-sm font-semibold text-blue-900 mb-2">How it works:</h3>
            <ul class="text-xs text-blue-800 space-y-1">
                <li>• Methods decorated with <code class="bg-blue-100 px-1 rounded">@event</code> auto-register</li>
                <li>• Reference methods directly: <code class="bg-blue-100 px-1 rounded">{{'{self.increment}'}}</code></li>
                <li>• Method name becomes event name automatically</li>
                <li>• Cleaner signatures: no 'event' parameter needed</li>
            </ul>
        </div>
    </div>
</div>"""
