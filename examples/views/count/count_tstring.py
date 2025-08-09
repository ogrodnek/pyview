from dataclasses import dataclass
from pyview.live_view import LiveView
from pyview.template.template_view import TemplateView
from string.templatelib import Template
from pyview.meta import PyViewMeta


@dataclass
class CounterContext:
    count: int = 0


class CounterTStringLiveView(TemplateView, LiveView[CounterContext]):
    """Simple counter using Python 3.14 t-strings."""
    
    async def mount(self, socket, session):
        socket.context = CounterContext(count=0)
    
    async def handle_event(self, event, payload, socket):
        if event == "decrement":
            socket.context.count -= 1
        elif event == "increment":
            socket.context.count += 1
    
    async def handle_params(self, url, params, socket):
        if "c" in params:
            socket.context.count = int(params["c"][0])
    
    def template(self, assigns: CounterContext, meta: PyViewMeta) -> Template:
        return t"""
        <div class="max-w-md mx-auto">
            <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-8">
                <h1 class="text-3xl font-bold text-center text-gray-900 mb-4">
                    T-String Counter
                </h1>
                <p class="text-center text-gray-600 mb-8">
                    Using Python 3.14 t-strings!
                </p>
                
                <div class="text-center mb-8">
                    <div class="text-6xl font-bold text-pyview-pink-600 tabular-nums">
                        {assigns.count}
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
                
                {self.url_tip()}
                
                {self.template_features()}
            </div>
        </div>
        """
    
    def url_tip(self) -> Template:
        return t"""
        <div class="mt-8 text-center">
            <p class="text-sm text-gray-500">
                Try changing the URL to 
                <code class="px-2 py-1 bg-gray-100 rounded text-xs">
                    /counter_tstring?c=100
                </code>
            </p>
        </div>
        """
    
    def template_features(self) -> Template:
        return t"""
        <div class="mt-6 p-4 bg-green-50 rounded-lg border border-green-200">
            <h3 class="text-sm font-semibold text-green-800 mb-2">
                T-String Benefits:
            </h3>
            <div class="text-xs text-green-700 space-y-1">
                <div>• Real Python 3.14 t-string literals</div>
                <div>• Direct variable access: {'{assigns.count}'}</div>
                <div>• Full IDE support and syntax highlighting</div>
                <div>• Type-safe template composition</div>
            </div>
        </div>
        """