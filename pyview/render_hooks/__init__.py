"""
Render hooks for PyView.

Render hooks allow customization of the rendering process at key points:
- before_render: Called before template rendering
- transform_tree: Called after rendering to transform the Phoenix wire format

This is used for CSS injection, but can be extended for other purposes.
"""

from .base import HookContext, RenderHook, RenderHookRunner

__all__ = ["RenderHook", "RenderHookRunner", "HookContext"]
