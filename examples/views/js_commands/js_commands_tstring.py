"""
JS Commands example using t-string templates.

This demonstrates the new tstring API for JS commands using the `js` singleton.
"""

from typing import TypedDict

from string.templatelib import Template
from markupsafe import Markup
from pyview import LiveView, LiveViewSocket, js
from pyview.events import AutoEventDispatch, event
from pyview.meta import PyViewMeta
from pyview.template.template_view import TemplateView


class JsCommandsContext(TypedDict):
    value: int


class JsCommandsTStringLiveView(AutoEventDispatch, TemplateView, LiveView[JsCommandsContext]):
    """
    JS Commands (T-String Version)

    JS Commands let you update the DOM without making a trip to the server.
    This example demonstrates the new t-string API using the `js` singleton.
    """

    async def mount(self, socket: LiveViewSocket[JsCommandsContext], session):
        socket.context = JsCommandsContext({"value": 0})

    @event
    async def increment(self, event, payload, socket: LiveViewSocket[JsCommandsContext]):
        socket.context["value"] += 1

    @event
    async def delete_item(self, event, payload, socket: LiveViewSocket[JsCommandsContext]):
        # In a real app, you'd delete the item from the database here
        print(f"Deleting item: {payload}")

    close_modal = js.hide("#modal-dialog", transition=(
        "transition-all duration-200 ease-in", "opacity-100 scale-100", "opacity-0 scale-95"
    )).hide("#modal-backdrop").pop_focus()

    clipboard_script = Markup("""<script>
    window.addEventListener("copy-to-clipboard", function (event) {
        if ("clipboard" in navigator) {
            const text = event.target.textContent;
            navigator.clipboard.writeText(text);
        }
    });
</script>""")

    def template(self, assigns: JsCommandsContext, meta: PyViewMeta) -> Template:
        value = assigns["value"]

        return t"""
{self.clipboard_script}

<div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 sm:p-8">
        <h1 class="text-3xl font-bold text-gray-900 mb-6">JS Commands (t-string API)</h1>

        <div class="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-8">
            <p class="text-sm text-blue-900 mb-2">
                This example demonstrates the new t-string API for JS commands.
            </p>
            <p class="text-sm text-blue-900">
                Import <code class="px-1 bg-blue-100 rounded">js</code> from pyview and use it directly in your templates.
            </p>
        </div>

        <div class="space-y-8">
            <!-- Show/Hide Section -->
            <section>
                <h2 class="text-xl font-semibold text-gray-900 mb-4">Show/Hide</h2>
                <div class="flex gap-2 mb-4">
                    <button phx-click='{js.show("#quote-1")}'
                            class="px-4 py-2 bg-green-600 text-white text-sm font-medium rounded-md hover:bg-green-700 transition-colors">
                        Show
                    </button>
                    <button phx-click='{js.hide("#quote-1")}'
                            class="px-4 py-2 bg-red-600 text-white text-sm font-medium rounded-md hover:bg-red-700 transition-colors">
                        Hide
                    </button>
                    <button phx-click='{js.show("#quote-1", transition=("transition-all duration-300 ease-out", "opacity-0 scale-95", "opacity-100 scale-100"), time=300)}'
                            class="px-4 py-2 bg-purple-600 text-white text-sm font-medium rounded-md hover:bg-purple-700 transition-colors">
                        Show (animated)
                    </button>
                </div>
                <blockquote id="quote-1" class="bg-gray-50 border-l-4 border-gray-400 p-4 rounded-r-md">
                    <p class="text-gray-700 italic">JS Commands let you update the DOM without making a trip to the server.</p>
                </blockquote>
            </section>

            <hr class="border-gray-200">

            <!-- Toggle Section -->
            <section>
                <h2 class="text-xl font-semibold text-gray-900 mb-4">Toggle</h2>
                <button phx-click='{js.toggle("#quote-2")}'
                        class="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 transition-colors mb-4">
                    Toggle
                </button>
                <button phx-click='{js.toggle("#quote-2", in_transition=("transition-all duration-200 ease-out", "opacity-0", "opacity-100"), out_transition=("transition-all duration-200 ease-in", "opacity-100", "opacity-0"))}'
                        class="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-md hover:bg-indigo-700 transition-colors mb-4 ml-2">
                    Toggle (animated)
                </button>
                <blockquote id="quote-2" class="bg-gray-50 border-l-4 border-gray-400 p-4 rounded-r-md">
                    <p class="text-gray-700 italic">Toggle me!</p>
                </blockquote>
            </section>

            <hr class="border-gray-200">

            <!-- Add/Remove/Toggle Class Section -->
            <section>
                <h2 class="text-xl font-semibold text-gray-900 mb-4">Class Manipulation</h2>
                <div class="flex flex-wrap gap-2 mb-4">
                    <button phx-click='{js.add_class("hint", to="#quote-3")}'
                            class="px-4 py-2 bg-green-600 text-white text-sm font-medium rounded-md hover:bg-green-700 transition-colors">
                        Add "hint"
                    </button>
                    <button phx-click='{js.add_class("warn", to="#quote-3")}'
                            class="px-4 py-2 bg-yellow-600 text-white text-sm font-medium rounded-md hover:bg-yellow-700 transition-colors">
                        Add "warn"
                    </button>
                    <button phx-click='{js.remove_class(["warn", "hint", "highlight"], to="#quote-3")}'
                            class="px-4 py-2 bg-gray-600 text-white text-sm font-medium rounded-md hover:bg-gray-700 transition-colors">
                        Remove all
                    </button>
                    <button phx-click='{js.toggle_class("highlight", to="#quote-3")}'
                            class="px-4 py-2 bg-purple-600 text-white text-sm font-medium rounded-md hover:bg-purple-700 transition-colors">
                        Toggle "highlight"
                    </button>
                </div>
                <blockquote id="quote-3" class="bg-gray-50 border-l-4 border-gray-400 p-4 rounded-r-md">
                    <p class="text-gray-700 italic">Watch my classes change!</p>
                </blockquote>
            </section>

            <hr class="border-gray-200">

            <!-- Dispatch Section -->
            <section>
                <h2 class="text-xl font-semibold text-gray-900 mb-4">Dispatch (Custom Events)</h2>
                <div class="prose prose-sm text-gray-600 mb-4 max-w-none">
                    <p>Dispatch sends custom JavaScript events that you can listen to with <code class="px-2 py-1 bg-gray-100 rounded text-xs">window.addEventListener</code>.</p>
                    <p>This example also shows <strong>command chaining</strong> - dispatching an event AND adding a class in one click.</p>
                </div>
                <pre id="copy-text" class="bg-gray-100 p-4 rounded-md text-sm font-mono mb-4 overflow-x-auto">{js.dispatch("copy-to-clipboard", to="#copy-text")}</pre>
                <button id="copy-button"
                        phx-click='{js.dispatch("copy-to-clipboard", to="#copy-text").add_class("copied", to="#copy-button")}'
                        class="px-4 py-2 bg-purple-600 text-white text-sm font-medium rounded-md hover:bg-purple-700 transition-colors">
                    Copy to clipboard
                </button>
            </section>

            <hr class="border-gray-200">

            <!-- Push Section -->
            <section>
                <h2 class="text-xl font-semibold text-gray-900 mb-4">Push (Server Events + Transitions)</h2>
                <div class="prose prose-sm text-gray-600 mb-4 max-w-none">
                    <p>Push sends events to your LiveView, similar to <code class="px-2 py-1 bg-gray-100 rounded text-xs">phx-click</code>.</p>
                    <p>Chain it with other commands for optimistic UI updates!</p>
                </div>
                <div class="flex flex-col gap-4 items-start">
                    <div id="counter" class="inline-flex items-center bg-white border border-gray-200 rounded-lg px-4 py-2 shadow-sm">
                        <span class="text-sm font-medium text-gray-600 mr-2">Counter</span>
                        <div class="w-px h-5 bg-gray-300 mr-2"></div>
                        <span class="text-2xl font-bold text-gray-900 tabular-nums">{value}</span>
                    </div>
                    <button phx-click='{js.push("increment").transition("bounce", to="#counter")}'
                            class="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-md hover:bg-indigo-700 transition-colors">
                        Increment with bounce
                    </button>
                </div>
            </section>

            <hr class="border-gray-200">

            <!-- Optimistic Delete Section -->
            <section>
                <h2 class="text-xl font-semibold text-gray-900 mb-4">Optimistic Delete Pattern</h2>
                <div class="prose prose-sm text-gray-600 mb-4 max-w-none">
                    <p>A common pattern: hide the element immediately (optimistic UI) while sending the delete event to the server.</p>
                </div>
                <div id="delete-item" class="flex items-center justify-between bg-gray-50 p-4 rounded-md">
                    <span class="text-gray-700">Item to delete</span>
                    <button phx-click='{js.hide("#delete-item", transition=("transition-all duration-200 ease-in", "opacity-100", "opacity-0")).push("delete_item", value={"id": 123})}'
                            class="px-3 py-1 bg-red-600 text-white text-sm font-medium rounded-md hover:bg-red-700 transition-colors">
                        Delete
                    </button>
                </div>
            </section>

            <hr class="border-gray-200">

            <!-- Focus Section -->
            <section>
                <h2 class="text-xl font-semibold text-gray-900 mb-4">Focus Management</h2>
                <div class="flex gap-2 mb-4">
                    <button phx-click='{js.focus(to="#email")}'
                            class="px-4 py-2 bg-teal-600 text-white text-sm font-medium rounded-md hover:bg-teal-700 transition-colors">
                        Focus Email
                    </button>
                    <button phx-click='{js.focus_first(to="#focus-form")}'
                            class="px-4 py-2 bg-cyan-600 text-white text-sm font-medium rounded-md hover:bg-cyan-700 transition-colors">
                        Focus First
                    </button>
                </div>
                <form id="focus-form" autocomplete="off" class="space-y-4 max-w-sm">
                    <div>
                        <label for="name" class="block text-sm font-medium text-gray-700 mb-1">Name</label>
                        <input type="text" id="name"
                               class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" />
                    </div>
                    <div>
                        <label for="email" class="block text-sm font-medium text-gray-700 mb-1">Email</label>
                        <input type="text" id="email"
                               class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" />
                    </div>
                </form>
            </section>

            <hr class="border-gray-200">

            <!-- Attribute Section -->
            <section>
                <h2 class="text-xl font-semibold text-gray-900 mb-4">Attribute Manipulation</h2>
                <div class="flex gap-2 mb-4">
                    <button phx-click='{js.set_attribute(("disabled", "true"), to="#attr-button")}'
                            class="px-4 py-2 bg-red-600 text-white text-sm font-medium rounded-md hover:bg-red-700 transition-colors">
                        Disable
                    </button>
                    <button phx-click='{js.remove_attribute("disabled", to="#attr-button")}'
                            class="px-4 py-2 bg-green-600 text-white text-sm font-medium rounded-md hover:bg-green-700 transition-colors">
                        Enable
                    </button>
                    <button phx-click='{js.toggle_attribute(("aria-pressed", "true", "false"), to="#toggle-btn")}'
                            class="px-4 py-2 bg-purple-600 text-white text-sm font-medium rounded-md hover:bg-purple-700 transition-colors">
                        Toggle aria-pressed
                    </button>
                </div>
                <div class="flex gap-4">
                    <button id="attr-button"
                            class="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors">
                        Target Button
                    </button>
                    <button id="toggle-btn" aria-pressed="false"
                            class="px-4 py-2 bg-gray-600 text-white text-sm font-medium rounded-md hover:bg-gray-700 transition-colors aria-pressed:bg-green-600">
                        Toggle Button (check aria-pressed)
                    </button>
                </div>
            </section>

            <hr class="border-gray-200">

            <!-- Modal with Focus Management -->
            <section>
                <h2 class="text-xl font-semibold text-gray-900 mb-4">Modal with Focus Management</h2>
                <div class="prose prose-sm text-gray-600 mb-4 max-w-none">
                    <p>Chains show/hide with <code class="px-2 py-1 bg-gray-100 rounded text-xs">push_focus</code> / <code class="px-2 py-1 bg-gray-100 rounded text-xs">pop_focus</code> to save and restore focus for accessibility.</p>
                </div>
                <button id="modal-trigger"
                        phx-click='{js.show("#modal-backdrop").show("#modal-dialog", transition=("transition-all duration-200 ease-out", "opacity-0 scale-95", "opacity-100 scale-100"), display="flex").push_focus().focus_first(to="#modal-dialog")}'
                        class="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-md hover:bg-indigo-700">
                    Open Modal
                </button>

                <div id="modal-backdrop" style="display: none;"
                     phx-click='{self.close_modal}'
                     class="modal-backdrop">
                </div>

                <div id="modal-dialog" style="display: none;" class="modal-container">
                    <div class="modal-content">
                        <h3 class="text-lg font-semibold mb-2">Example Modal</h3>
                        <p class="text-gray-600 text-sm mb-4">Focus is pushed on open and popped on close. Try clicking outside or pressing Cancel.</p>
                        <input type="text" placeholder="Focus lands here..."
                               class="w-full px-3 py-2 border rounded-md mb-4 focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                        <div class="flex justify-end gap-2">
                            <button phx-click='{self.close_modal}'
                                    class="px-4 py-2 text-sm border rounded-md hover:bg-gray-50">
                                Cancel
                            </button>
                            <button phx-click='{self.close_modal}'
                                    class="px-4 py-2 text-sm text-white bg-indigo-600 rounded-md hover:bg-indigo-700">
                                Confirm
                            </button>
                        </div>
                    </div>
                </div>
            </section>
        </div>
    </div>
</div>
"""
