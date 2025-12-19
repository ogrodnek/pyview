"""
Slots Demo for LiveComponents

This example demonstrates the slots feature, which allows parent templates
to pass content into components - similar to React's children/slots or
Phoenix LiveView's slots.

Key concepts:
- slots() helper creates a slots dictionary
- Default slot: positional argument for main content
- Named slots: keyword arguments (header, actions, etc.)
- meta.slots['name'] accesses slot content in component template
- Slots can contain live components for nested interactivity
"""

from string.templatelib import Template
from typing import TypedDict

from pyview.components import ComponentMeta, ComponentSocket, LiveComponent, slots
from pyview.live_view import LiveView, LiveViewSocket
from pyview.meta import PyViewMeta
from pyview.template.live_view_template import live_component
from pyview.template.template_view import TemplateView


# =============================================================================
# Card Component - Uses Slots
# =============================================================================


class Card(LiveComponent):
    """
    A card component that uses slots for flexible content.

    Slots:
        header: Optional header content
        default: Main body content
        actions: Optional footer/actions area
    """

    async def mount(self, socket: ComponentSocket, assigns: dict):
        socket.context = {}

    def template(self, assigns: dict, meta: ComponentMeta) -> Template:
        # Get slots with fallbacks for optional ones
        header = meta.slots.get("header", t"")
        body = meta.slots.get("default", t"<p class='text-gray-400 italic'>No content</p>")
        actions = meta.slots.get("actions", t"")

        # Check if slots are provided (for conditional rendering)
        has_header = "header" in meta.slots
        has_actions = "actions" in meta.slots

        header_section = (
            t"""<div class="px-4 py-3 border-b border-gray-200 bg-gray-50">{header}</div>"""
            if has_header
            else t""
        )

        actions_section = (
            t"""<div class="px-4 py-3 border-t border-gray-200 bg-gray-50">{actions}</div>"""
            if has_actions
            else t""
        )

        return t"""
            <div class="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
                {header_section}
                <div class="p-4">
                    {body}
                </div>
                {actions_section}
            </div>
        """


# =============================================================================
# Counter Component - For Nesting Demo
# =============================================================================


class CounterContext(TypedDict):
    count: int


class Counter(LiveComponent[CounterContext]):
    """A simple counter to demonstrate live components inside slots."""

    async def mount(self, socket: ComponentSocket[CounterContext], assigns: dict):
        socket.context = CounterContext(count=assigns.get("initial", 0))

    async def handle_event(self, event: str, payload: dict, socket: ComponentSocket[CounterContext]):
        if event == "increment":
            socket.context["count"] += 1
        elif event == "decrement":
            socket.context["count"] -= 1

    def template(self, assigns: CounterContext, meta: ComponentMeta) -> Template:
        count = assigns["count"]
        myself = meta.myself

        return t"""
            <div class="flex items-center space-x-3">
                <button
                    phx-click="decrement"
                    phx-target="{myself}"
                    class="w-8 h-8 rounded-full bg-gray-200 hover:bg-gray-300 text-gray-700 font-bold"
                >-</button>
                <span class="text-xl font-bold tabular-nums w-12 text-center">{count}</span>
                <button
                    phx-click="increment"
                    phx-target="{myself}"
                    class="w-8 h-8 rounded-full bg-blue-500 hover:bg-blue-600 text-white font-bold"
                >+</button>
            </div>
        """


# =============================================================================
# Demo LiveView
# =============================================================================


class DemoContext(TypedDict):
    pass


class SlotsDemo(TemplateView, LiveView[DemoContext]):
    """
    Slots Demo

    Demonstrates how to use slots to pass content into components.
    """

    async def mount(self, socket: LiveViewSocket[DemoContext], session):
        socket.context = DemoContext()

    def template(self, assigns: DemoContext, meta: PyViewMeta) -> Template:
        return t"""
            <div class="max-w-4xl mx-auto space-y-8">
                <div class="text-center mb-8">
                    <h1 class="text-3xl font-bold text-gray-900">Component Slots</h1>
                    <p class="mt-2 text-gray-600">
                        Pass content into components using slots
                    </p>
                </div>

                <!-- Example 1: Card with all slots -->
                <div>
                    <h2 class="text-lg font-semibold text-gray-800 mb-3">Card with All Slots</h2>
                    <p class="text-sm text-gray-500 mb-3">
                        Header, body (default), and actions slots are all provided.
                    </p>
                    {live_component(Card, id="card-full", slots=slots(
                        t"<p class='text-gray-700'>This is the card body content passed via the default slot.</p>",
                        header=t"<h3 class='font-semibold text-gray-900'>Card Title</h3>",
                        actions=t'''
                            <div class="flex justify-end space-x-2">
                                <button class="px-3 py-1 text-sm bg-gray-200 text-gray-700 rounded hover:bg-gray-300">Cancel</button>
                                <button class="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700">Save</button>
                            </div>
                        '''
                    ))}
                </div>

                <!-- Example 2: Card with nested Counter -->
                <div>
                    <h2 class="text-lg font-semibold text-gray-800 mb-3">Nested Live Component</h2>
                    <p class="text-sm text-gray-500 mb-3">
                        Slots can contain live components! The counter below is fully interactive.
                    </p>
                    {live_component(Card, id="card-counter", slots=slots(
                        t'''
                            <div class="space-y-3">
                                <p class="text-gray-700">This card contains a nested Counter component:</p>
                                <div class="flex justify-center">
                                    {live_component(Counter, id="nested-counter", initial=5)}
                                </div>
                            </div>
                        ''',
                        header=t"<h3 class='font-semibold text-gray-900'>Interactive Card</h3>"
                    ))}
                </div>

                <!-- Example 3: Card with only default slot -->
                <div>
                    <h2 class="text-lg font-semibold text-gray-800 mb-3">Simple Card (Default Slot Only)</h2>
                    <p class="text-sm text-gray-500 mb-3">
                        When header and actions slots aren't provided, they're simply not rendered.
                    </p>
                    {live_component(Card, id="card-simple", slots=slots(
                        t'''
                            <p class="text-gray-700">
                                This card only uses the default slot. No header or actions.
                                The component handles missing slots gracefully.
                            </p>
                        '''
                    ))}
                </div>

                <!-- How It Works -->
                <div class="bg-blue-50 rounded-lg p-6">
                    <h2 class="text-lg font-semibold text-blue-800 mb-3">How Slots Work</h2>
                    <div class="text-sm text-blue-700 space-y-3">
                        <div>
                            <strong>Creating slots:</strong>
                            <pre class="mt-1 bg-blue-100 p-2 rounded text-xs overflow-x-auto">slots(
    t"Default content",        # positional = default slot
    header=t"Header content",  # named slot
    actions=t"Footer content"  # named slot
)</pre>
                        </div>
                        <div>
                            <strong>Accessing in component:</strong>
                            <pre class="mt-1 bg-blue-100 p-2 rounded text-xs overflow-x-auto">def template(self, assigns, meta):
    header = meta.slots.get("header", t"")
    body = meta.slots.get("default", t"Fallback")
    return t"&lt;div&gt;{{header}}{{body}}&lt;/div&gt;"</pre>
                        </div>
                        <div>
                            <strong>Key points:</strong>
                            <ul class="list-disc list-inside mt-1 space-y-1">
                                <li>Use <code class="bg-blue-100 px-1 rounded">slots()</code> helper to create slot dict</li>
                                <li>Access via <code class="bg-blue-100 px-1 rounded">meta.slots['name']</code> or <code class="bg-blue-100 px-1 rounded">.get()</code></li>
                                <li>Slots can contain any template content, including live components</li>
                                <li>Use <code class="bg-blue-100 px-1 rounded">.get()</code> with fallback for optional slots</li>
                            </ul>
                        </div>
                    </div>
                </div>
            </div>
        """
