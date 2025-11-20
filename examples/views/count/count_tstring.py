from typing import TypedDict

from pyview.live_view import LiveView, LiveViewSocket
from pyview.template.template_view import TemplateView
from string.templatelib import Template
from pyview.meta import PyViewMeta


class CountContext(TypedDict):
    count: int


class CounterTStringLiveView(TemplateView, LiveView[CountContext]):
    """
    Basic Counter (T-String Version)

    Gotta start somewhere, right? This example shows how to send click events
    to the backend to update state.  We also snuck in handling URL params.
    """

    async def mount(self, socket: LiveViewSocket[CountContext], session):
        socket.context = CountContext({"count": 0})

    async def handle_event(self, event, payload, socket: LiveViewSocket[CountContext]):
        if event == "decrement":
            socket.context["count"] -= 1

        if event == "increment":
            socket.context["count"] += 1

    async def handle_params(self, url, params, socket: LiveViewSocket[CountContext]):
        if "c" in params:
            socket.context["count"] = int(params["c"][0])

    def button(self, label: str, event: str, style: str = "primary") -> Template:
        """Reusable button component demonstrating t-string composition."""
        base = "w-16 h-16 rounded-full text-2xl font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
        if style == "primary":
            classes = f"{base} bg-blue-600 text-white hover:bg-blue-700"
        else:
            classes = f"{base} bg-white border-2 border-gray-300 text-gray-700 hover:bg-gray-50 hover:border-gray-400"

        return t"""<button phx-click="{event}" class="{classes}">{label}</button>"""

    def template(self, assigns: CountContext, meta: PyViewMeta) -> Template:
        count = assigns["count"]
        return t"""<div class="max-w-md mx-auto">
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-8">
        <h1 class="text-3xl font-bold text-center text-gray-900 mb-8">Basic Counter</h1>

        <div class="text-center mb-8">
            <div class="text-6xl font-bold text-gray-800 tabular-nums">{count}</div>
        </div>

        <div class="flex items-center justify-center space-x-4">
            {self.button("−", "decrement", "secondary")}
            {self.button("+", "increment", "primary")}
        </div>

        <div class="mt-8 text-center">
            <p class="text-sm text-gray-500">
                Try changing the URL to <code class="px-2 py-1 bg-gray-100 rounded text-xs">/counter_tstring?c=100</code>
            </p>
        </div>
    </div>
</div>"""
