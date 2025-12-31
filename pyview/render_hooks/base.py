"""
Base classes for render hooks.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pyview.live_view import LiveView
    from pyview.template.root_template import RootTemplateContext


@dataclass
class HookContext:
    """
    Context passed to render hooks.

    Provides access to the current view, socket, and metadata needed
    for hook operations.
    """

    view: "LiveView"
    socket: Any  # ConnectedLiveViewSocket or UnconnectedSocket
    is_connected: bool
    # Content to prepend to rendered output (accumulated by hooks)
    prepend_content: list[str] = field(default_factory=list)

    def add_prepend(self, content: str) -> None:
        """Add content to prepend to the rendered output."""
        self.prepend_content.append(content)

    def get_prepend_html(self) -> str:
        """Get all prepended content as a single string."""
        return "".join(self.prepend_content)


@runtime_checkable
class RenderHook(Protocol):
    """
    Protocol for render hooks.

    Render hooks are called at specific points during the render lifecycle
    to allow customization of the output.
    """

    async def before_render(self, ctx: HookContext) -> None:
        """
        Called before template rendering.

        Use this to prepare data, register CSS, etc.
        Can add content to prepend via ctx.add_prepend().

        Args:
            ctx: The hook context
        """
        ...

    def transform_tree(self, tree: dict[str, Any], ctx: HookContext) -> dict[str, Any]:
        """
        Transform the rendered tree before sending.

        Called after rendering for connected sockets (live navigation).
        The tree is in Phoenix wire format: {"s": [...], "0": ..., ...}

        Args:
            tree: The rendered tree in Phoenix wire format
            ctx: The hook context

        Returns:
            The transformed tree
        """
        ...

    async def on_initial_render(
        self, ctx: HookContext, template_context: "RootTemplateContext"
    ) -> None:
        """
        Called during initial HTTP render.

        Can modify the template context (e.g., add to additional_head_elements).

        Args:
            ctx: The hook context
            template_context: The root template context (mutable)
        """
        ...


class RenderHookRunner:
    """
    Runs render hooks in sequence.
    """

    def __init__(self):
        self._hooks: list[RenderHook] = []

    def add(self, hook: RenderHook) -> None:
        """Add a render hook."""
        self._hooks.append(hook)

    def remove(self, hook: RenderHook) -> None:
        """Remove a render hook."""
        self._hooks.remove(hook)

    async def run_before_render(self, ctx: HookContext) -> None:
        """Run all before_render hooks."""
        for hook in self._hooks:
            if hasattr(hook, "before_render"):
                await hook.before_render(ctx)

    def run_transform_tree(self, tree: dict[str, Any], ctx: HookContext) -> dict[str, Any]:
        """Run all transform_tree hooks."""
        result = tree
        for hook in self._hooks:
            if hasattr(hook, "transform_tree"):
                result = hook.transform_tree(result, ctx)
        return result

    async def run_on_initial_render(
        self, ctx: HookContext, template_context: "RootTemplateContext"
    ) -> None:
        """Run all on_initial_render hooks."""
        for hook in self._hooks:
            if hasattr(hook, "on_initial_render"):
                await hook.on_initial_render(ctx, template_context)

    def __len__(self) -> int:
        return len(self._hooks)

    def __iter__(self):
        return iter(self._hooks)
