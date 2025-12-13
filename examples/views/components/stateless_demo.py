"""
Stateless Function Components Demo

This example demonstrates how to create reusable, composable UI components
using simple Python functions that return t-string Templates.

Stateless components:
- Are pure functions (no state, no lifecycle)
- Accept parameters and return Templates
- Can be composed/nested
- Events bubble up to the parent LiveView

This is the foundation for the component system - verifying that
function composition works with t-strings and event references.
"""

from string.templatelib import Template
from typing import TypedDict

from pyview.events import AutoEventDispatch, event
from pyview.live_view import LiveView, LiveViewSocket
from pyview.meta import PyViewMeta
from pyview.template.template_view import TemplateView

# =============================================================================
# Stateless Function Components
# =============================================================================


def Button(
    label: str,
    event_ref,
    *,
    style: str = "primary",
    size: str = "md",
    disabled: bool = False,
) -> Template:
    """
    A reusable button component.

    Args:
        label: Button text
        event_ref: Event reference (e.g., self.increment) - stringifies to event name
        style: "primary", "secondary", or "danger"
        size: "sm", "md", or "lg"
        disabled: Whether button is disabled
    """
    # Base classes
    base = "font-medium rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2"

    # Size variants
    sizes = {
        "sm": "px-3 py-1.5 text-sm",
        "md": "px-4 py-2 text-base",
        "lg": "px-6 py-3 text-lg",
    }

    # Style variants
    styles = {
        "primary": "bg-blue-600 text-white hover:bg-blue-700 focus:ring-blue-500",
        "secondary": "bg-gray-200 text-gray-800 hover:bg-gray-300 focus:ring-gray-500",
        "danger": "bg-red-600 text-white hover:bg-red-700 focus:ring-red-500",
    }

    classes = f"{base} {sizes.get(size, sizes['md'])} {styles.get(style, styles['primary'])}"

    if disabled:
        classes += " opacity-50 cursor-not-allowed"
        return t'<button class="{classes}" disabled>{label}</button>'

    return t'<button phx-click="{event_ref}" class="{classes}">{label}</button>'


def Card(title: str, children: Template, *, footer: Template | None = None) -> Template:
    """
    A card component with title, content, and optional footer.

    Args:
        title: Card header text
        children: Card body content (a Template)
        footer: Optional footer content (a Template)
    """
    footer_html = (
        t'<div class="px-6 py-4 bg-gray-50 border-t border-gray-200">{footer}</div>'
        if footer
        else t""
    )

    return t"""
        <div class="bg-white rounded-lg shadow-md border border-gray-200 overflow-hidden">
            <div class="px-6 py-4 border-b border-gray-200">
                <h3 class="text-lg font-semibold text-gray-900">{title}</h3>
            </div>
            <div class="px-6 py-4">
                {children}
            </div>
            {footer_html}
        </div>
    """


def Badge(text: str, *, color: str = "gray") -> Template:
    """
    A small badge/tag component.

    Args:
        text: Badge text
        color: "gray", "blue", "green", "red", "yellow"
    """
    colors = {
        "gray": "bg-gray-100 text-gray-800",
        "blue": "bg-blue-100 text-blue-800",
        "green": "bg-green-100 text-green-800",
        "red": "bg-red-100 text-red-800",
        "yellow": "bg-yellow-100 text-yellow-800",
    }
    color_classes = colors.get(color, colors["gray"])

    return t'<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium {color_classes}">{text}</span>'


def Counter(count: int, on_increment, on_decrement) -> Template:
    """
    A counter component with increment/decrement buttons.

    This demonstrates passing multiple event references to a component.

    Args:
        count: Current count value
        on_increment: Event reference for increment
        on_decrement: Event reference for decrement
    """
    return t"""
        <div class="flex items-center space-x-4">
            {Button("−", on_decrement, style="secondary", size="sm")}
            <span class="text-2xl font-bold tabular-nums w-16 text-center">{count}</span>
            {Button("+", on_increment, style="primary", size="sm")}
        </div>
    """


def Alert(message: str, *, variant: str = "info", on_dismiss=None) -> Template:
    """
    An alert/notification component.

    Args:
        message: Alert message
        variant: "info", "success", "warning", "error"
        on_dismiss: Optional event reference for dismiss button
    """
    variants = {
        "info": ("bg-blue-50 border-blue-200 text-blue-800", "text-blue-600"),
        "success": ("bg-green-50 border-green-200 text-green-800", "text-green-600"),
        "warning": ("bg-yellow-50 border-yellow-200 text-yellow-800", "text-yellow-600"),
        "error": ("bg-red-50 border-red-200 text-red-800", "text-red-600"),
    }
    bg_classes, btn_classes = variants.get(variant, variants["info"])

    dismiss_btn = (
        t"""<button phx-click="{on_dismiss}" class="ml-auto {btn_classes} hover:opacity-75">
            <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"/>
            </svg>
        </button>"""
        if on_dismiss
        else t""
    )

    return t"""
        <div class="flex items-center p-4 border rounded-lg {bg_classes}">
            <span>{message}</span>
            {dismiss_btn}
        </div>
    """


# =============================================================================
# LiveView using Stateless Components
# =============================================================================


class DemoContext(TypedDict):
    count: int
    show_alert: bool
    items: list[str]


class StatelessComponentsDemo(AutoEventDispatch, TemplateView, LiveView[DemoContext]):
    """
    Stateless Components Demo

    Demonstrates reusable function components that compose together.
    All events are handled by this parent LiveView.
    """

    async def mount(self, socket: LiveViewSocket[DemoContext], session):
        socket.context = DemoContext(
            count=0,
            show_alert=True,
            items=["Python", "T-Strings", "Components"],
        )

    @event
    async def increment(self, event, payload, socket: LiveViewSocket[DemoContext]):
        socket.context["count"] += 1

    @event
    async def decrement(self, event, payload, socket: LiveViewSocket[DemoContext]):
        socket.context["count"] -= 1

    @event
    async def reset(self, event, payload, socket: LiveViewSocket[DemoContext]):
        socket.context["count"] = 0

    @event
    async def dismiss_alert(self, event, payload, socket: LiveViewSocket[DemoContext]):
        socket.context["show_alert"] = False

    @event
    async def show_alert(self, event, payload, socket: LiveViewSocket[DemoContext]):
        socket.context["show_alert"] = True

    @event
    async def add_item(self, event, payload, socket: LiveViewSocket[DemoContext]):
        socket.context["items"].append(f"Item {len(socket.context['items']) + 1}")

    def template(self, assigns: DemoContext, meta: PyViewMeta) -> Template:
        count = assigns["count"]
        show_alert = assigns["show_alert"]
        items = assigns["items"]

        # Compose the alert conditionally
        alert_section = (
            Alert(
                "This alert can be dismissed! Components can have optional event handlers.",
                variant="info",
                on_dismiss=self.dismiss_alert,
            )
            if show_alert
            else t'{Button("Show Alert", self.show_alert, style="secondary", size="sm")}'
        )

        # Compose badges from a list
        badges = [Badge(item, color="blue") for item in items]

        # Build card footer with buttons
        footer = t"""
            <div class="flex space-x-2">
                {Button("Reset", self.reset, style="danger", size="sm")}
            </div>
        """

        # Card content with counter
        card_content = t"""
            <div class="space-y-4">
                <p class="text-gray-600">
                    This counter is built from composable function components.
                    The Counter component uses two Button components internally.
                </p>
                {Counter(count, self.increment, self.decrement)}
            </div>
        """

        return t"""
            <div class="max-w-2xl mx-auto space-y-6">
                <div class="text-center mb-8">
                    <h1 class="text-3xl font-bold text-gray-900">Stateless Function Components</h1>
                    <p class="mt-2 text-gray-600">
                        Reusable UI components as simple Python functions
                    </p>
                </div>

                <!-- Alert Section -->
                <div>
                    {alert_section}
                </div>

                <!-- Counter Card -->
                {Card("Counter Example", card_content, footer=footer)}

                <!-- Badges Section -->
                {Card(
                    "Dynamic Badges",
                    t'''
                        <div class="space-y-4">
                            <p class="text-gray-600">
                                Components work with list comprehensions too!
                            </p>
                            <div class="flex flex-wrap gap-2">
                                {badges}
                            </div>
                            {Button("Add Badge", self.add_item, size="sm")}
                        </div>
                    '''
                )}

                <!-- Component Showcase -->
                {Card(
                    "Button Variants",
                    t'''
                        <div class="space-y-4">
                            <div class="space-y-2">
                                <p class="text-sm font-medium text-gray-700">Styles:</p>
                                <div class="flex flex-wrap gap-2">
                                    {Button("Primary", self.reset, style="primary")}
                                    {Button("Secondary", self.reset, style="secondary")}
                                    {Button("Danger", self.reset, style="danger")}
                                </div>
                            </div>
                            <div class="space-y-2">
                                <p class="text-sm font-medium text-gray-700">Sizes:</p>
                                <div class="flex flex-wrap items-center gap-2">
                                    {Button("Small", self.reset, size="sm")}
                                    {Button("Medium", self.reset, size="md")}
                                    {Button("Large", self.reset, size="lg")}
                                </div>
                            </div>
                            <div class="space-y-2">
                                <p class="text-sm font-medium text-gray-700">Disabled:</p>
                                <div class="flex flex-wrap gap-2">
                                    {Button("Disabled", self.reset, disabled=True)}
                                </div>
                            </div>
                        </div>
                    '''
                )}
            </div>
        """
