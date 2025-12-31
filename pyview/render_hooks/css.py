"""
CSS injection render hook.

Automatically injects CSS <link> tags for views and components.
CSS files are discovered next to Python files and served with content hashes.
"""

import logging
from typing import TYPE_CHECKING, Any

from markupsafe import Markup

from pyview.css import CSSRegistry

from .base import HookContext

if TYPE_CHECKING:
    from pyview.template.root_template import RootTemplateContext

logger = logging.getLogger(__name__)


class CSSRenderHook:
    """
    Render hook that injects CSS <link> tags for views and components.

    For initial HTTP render:
        - Adds <link> tags to additional_head_elements in root template

    For live navigation (WebSocket):
        - Prepends <link> tags to rendered content for new CSS
        - Tracks loaded CSS on socket to avoid duplicates
    """

    def __init__(self, registry: CSSRegistry):
        self.registry = registry

    async def before_render(self, ctx: HookContext) -> None:
        """
        Register CSS for the view if not already registered.
        For connected sockets, determine if CSS needs to be injected.
        """
        view_class = ctx.view.__class__

        # Ensure view's CSS is registered
        entry = self.registry.register_for_class(view_class)

        if entry and ctx.is_connected:
            # Check if this CSS is already loaded on this socket
            loaded_css = self._get_loaded_css(ctx.socket)
            if entry.url not in loaded_css:
                ctx.add_prepend(entry.link_tag)
                loaded_css.add(entry.url)
                logger.debug(f"Injecting view CSS for live navigation: {entry.url}")

    def transform_tree(self, tree: dict[str, Any], ctx: HookContext) -> dict[str, Any]:
        """
        Prepend CSS link tags to the rendered tree.

        Collects CSS for components and modifies the first static segment.
        """
        # Collect component CSS if socket has a components manager
        if ctx.is_connected and hasattr(ctx.socket, "components"):
            loaded_css = self._get_loaded_css(ctx.socket)
            component_css = ctx.socket.components.collect_component_css(
                self.registry, loaded_css
            )
            for link_tag in component_css:
                ctx.add_prepend(link_tag)

        prepend = ctx.get_prepend_html()
        if prepend and "s" in tree and tree["s"]:
            tree["s"][0] = prepend + tree["s"][0]
        return tree

    async def on_initial_render(
        self, ctx: HookContext, template_context: "RootTemplateContext"
    ) -> None:
        """
        Add CSS to the root template's head elements for views and components.
        """
        view_class = ctx.view.__class__

        # Ensure view's CSS is registered and add to head
        entry = self.registry.register_for_class(view_class)
        if entry:
            template_context["additional_head_elements"].append(Markup(entry.link_tag))
            logger.debug(f"Adding view CSS to initial render: {entry.url}")

        # Collect component CSS
        if hasattr(ctx.socket, "components"):
            loaded_css = self._get_loaded_css(ctx.socket)
            component_css = ctx.socket.components.collect_component_css(
                self.registry, loaded_css
            )
            for link_tag in component_css:
                template_context["additional_head_elements"].append(Markup(link_tag))
                logger.debug(f"Adding component CSS to initial render: {link_tag}")

    def _get_loaded_css(self, socket: Any) -> set[str]:
        """Get or create the set of loaded CSS URLs on a socket."""
        if not hasattr(socket, "loaded_css"):
            socket.loaded_css = set()
        return socket.loaded_css


