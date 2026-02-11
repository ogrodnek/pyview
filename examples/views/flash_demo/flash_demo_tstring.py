from dataclasses import dataclass
from pyview.live_view import LiveView, LiveViewSocket
from pyview.events import AutoEventDispatch, event
from pyview.template.template_view import TemplateView
from string.templatelib import Template
from pyview.meta import PyViewMeta
from typing import Optional


@dataclass
class FlashDemoContext:
    name: str = ""


class FlashDemoTStringLiveView(AutoEventDispatch, TemplateView, LiveView[FlashDemoContext]):
    """
    Flash Messages (T-String Version)

    Show and dismiss user feedback with flash messages. Flash values live on the
    socket and are automatically available in your template.
    """

    async def mount(self, socket: LiveViewSocket[FlashDemoContext], session):
        socket.context = FlashDemoContext()

    @event
    async def save(self, name: Optional[str], socket: LiveViewSocket[FlashDemoContext]):
        if not name:
            socket.put_flash("error", "Name cannot be blank.")
            return

        socket.context.name = name
        socket.clear_flash()
        socket.put_flash("info", f"Saved — welcome, {name}!")

    @event
    async def danger(self, socket: LiveViewSocket[FlashDemoContext]):
        socket.put_flash("error", "Something went wrong.")

    def flash_banner(self, key: str, message: str) -> Template:
        if key == "info":
            bg = "bg-green-50 border-green-200 hover:bg-green-100"
            text = "text-green-800"
            dismiss = "text-green-400"
        else:
            bg = "bg-red-50 border-red-200 hover:bg-red-100"
            text = "text-red-800"
            dismiss = "text-red-400"

        return t"""<div id="flash-{key}"
             phx-click="lv:clear-flash" phx-value-key="{key}"
             class="mb-6 flex items-center justify-between border rounded-lg px-4 py-3 cursor-pointer transition-colors {bg}">
            <span class="text-sm {text}">{message}</span>
            <span class="{dismiss} text-xs ml-3">dismiss</span>
        </div>"""

    def template(self, assigns: FlashDemoContext, meta: PyViewMeta) -> Template:
        name = assigns.name
        
        banners = [
            self.flash_banner(key, message) for key, message in meta.flash.items()
        ]

        return t"""<div class="max-w-md mx-auto">
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-8">
        <h1 class="text-3xl font-bold text-center text-gray-900 mb-8">Flash Messages</h1>

        {banners}

        <form phx-submit="save" class="space-y-4 mb-6">
            <div>
                <label for="name" class="block text-sm font-medium text-gray-700 mb-1">Name</label>
                <input type="text" id="name" name="name" value="{name}"
                       class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
            </div>
            <button type="submit"
                    class="w-full px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors">
                Save
            </button>
        </form>

        <button phx-click="danger"
                class="w-full px-4 py-2 bg-white border border-gray-300 text-gray-700 text-sm font-medium rounded-md hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 transition-colors">
            Trigger Error
        </button>
    </div>
</div>"""
