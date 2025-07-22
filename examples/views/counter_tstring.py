"""
Simple counter example using t-string templates.
Shows the clean API for accessing dataclass context.
"""

from dataclasses import dataclass
from pyview.live_view import LiveView
from pyview.template.template_view import TemplateView
from pyview.template.tstring_polyfill import t, Template
from pyview.meta import PyViewMeta


@dataclass
class CounterContext:
    count: int = 0


class CounterTStringLiveView(TemplateView, LiveView[CounterContext]):
    """Simple counter using t-string templates."""

    async def mount(self, socket, session):
        socket.context = CounterContext(count=0)

    async def handle_event(self, event, payload, socket):
        if event == "decrement":
            socket.context.count -= 1
        elif event == "increment":
            socket.context.count += 1

    async def handle_params(self, url, params, socket):
        # Handle URL params like /counter_tstring?c=100
        if "c" in params:
            socket.context.count = int(params["c"][0])

    def template(self, assigns: CounterContext, meta: PyViewMeta) -> Template:
        # Clean API: properly typed dataclass + access to meta!
        print(f"assigns type: {type(assigns)}, count: {assigns.count}")
        print(f"meta: {meta}")
        count = assigns.count

        return t(
            """
        <div class="max-w-md mx-auto">
            <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-8">
                <h1 class="text-3xl font-bold text-center text-gray-900 mb-4">
                    T-String Counter
                </h1>
                <p class="text-center text-gray-600 mb-8">
                    Same counter, but using t-string templates!
                </p>
                
                <div class="text-center mb-8">
                    <div class="text-6xl font-bold text-pyview-pink-600 tabular-nums">
                        {count}
                    </div>
                </div>
                
                <div class="flex items-center justify-center space-x-4">
                    <button phx-click="decrement" 
                            class="w-16 h-16 rounded-full bg-white border-2 border-gray-300 text-gray-700 text-2xl font-medium hover:bg-gray-50 hover:border-gray-400 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-pyview-pink-500 transition-colors">
                        −
                    </button>
                    <button phx-click="increment" 
                            class="w-16 h-16 rounded-full bg-pyview-pink-600 text-white text-2xl font-medium hover:bg-pyview-pink-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-pyview-pink-500 transition-colors">
                        +
                    </button>
                </div>
                
                {url_tip}
                            </div>
        </div>
        """,
            count=count,
            url_tip=self.url_tip(),
        )

    def url_tip(self):
        """Helper method for URL tip section."""
        return t("""
        <div class="mt-8 text-center">
            <p class="text-sm text-gray-500">
                Try changing the URL to 
                <code class="px-2 py-1 bg-gray-100 rounded text-xs">
                    /counter_tstring?c=100
                </code>
            </p>
        </div>
        """)
