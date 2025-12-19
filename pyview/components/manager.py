"""
ComponentsManager - Manages component lifecycle and state.

The manager is attached to a ConnectedLiveViewSocket and handles:
- Component registration and CID assignment
- External storage of component state (contexts)
- Lifecycle orchestration (mount, update)
- Event routing to specific components
- Component rendering

Key design: Components are identified by (module, id) tuple.
Same module + id = same component instance across re-renders.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Protocol

from .base import ComponentMeta, ComponentSocket, LiveComponent
from .slots import Slots

if TYPE_CHECKING:
    from pyview.meta import PyViewMeta

logger = logging.getLogger(__name__)


class LiveViewProtocol(Protocol):
    """Protocol for LiveView's handle_event method."""

    async def handle_event(self, event: str, payload: dict[str, Any], socket: Any) -> None: ...


class ParentSocketProtocol(Protocol):
    """Protocol defining what ComponentsManager needs from its parent socket.

    ComponentsManager only uses parent_socket.liveview.handle_event() for
    sending events from components to their parent LiveView.
    """

    @property
    def liveview(self) -> LiveViewProtocol: ...


class ComponentsManager:
    """
    Manages LiveComponent instances, state, and lifecycle.

    Components are stored by CID (Component ID), an integer assigned
    on first registration. The (component_class, component_id) tuple
    maps to a CID, allowing components to persist across re-renders.

    Attributes:
        parent_socket: The parent LiveView's socket
        _components: CID -> LiveComponent instance mapping
        _contexts: CID -> component context (state) mapping
        _by_key: (class, id) -> CID mapping for identity
        _pending_mounts: CIDs that need mount() called
        _pending_updates: CIDs that need update() called with new assigns
    """

    def __init__(self, parent_socket: ParentSocketProtocol):
        self.parent_socket = parent_socket
        self._components: dict[int, LiveComponent] = {}
        self._contexts: dict[int, Any] = {}
        self._slots: dict[int, Slots] = {}  # Slot content keyed by CID
        self._by_key: dict[tuple[type, str], int] = {}
        self._pending_mounts: list[tuple[int, dict[str, Any]]] = []
        self._pending_updates: list[tuple[int, dict[str, Any]]] = []
        self._next_cid = 1
        self._seen_this_render: set[int] = set()  # Track CIDs seen during current render

    def register(
        self, component_class: type[LiveComponent], component_id: str, assigns: dict[str, Any]
    ) -> int:
        """
        Register a component, returning its CID.

        If this (class, id) combination already exists, returns the existing CID
        and queues an update. Otherwise, creates a new component and queues mount.

        Args:
            component_class: The LiveComponent subclass
            component_id: User-provided unique ID for this component instance
            assigns: Props/assigns passed from parent template

        Returns:
            The component's CID (integer)
        """
        key = (component_class, component_id)

        # Extract slots from assigns (if present) without mutating caller's dict
        component_slots = assigns.get("slots", {})
        if "slots" in assigns:
            assigns = {k: v for k, v in assigns.items() if k != "slots"}

        if key in self._by_key:
            # Existing component - queue update with new assigns
            cid = self._by_key[key]
            self._slots[cid] = component_slots  # Update slots
            self._pending_updates.append((cid, assigns))
            self._seen_this_render.add(cid)
            logger.debug(
                f"Component {component_class.__name__}:{component_id} (cid={cid}) queued for update"
            )
            return cid

        # New component - assign CID and create instance
        cid = self._next_cid
        self._next_cid += 1

        component = component_class()
        self._components[cid] = component
        self._contexts[cid] = {}  # Empty initial context
        self._slots[cid] = component_slots  # Store slots
        self._by_key[key] = cid

        # Queue mount with initial assigns
        self._pending_mounts.append((cid, assigns))
        self._seen_this_render.add(cid)
        logger.debug(
            f"Component {component_class.__name__}:{component_id} (cid={cid}) registered and queued for mount"
        )

        return cid

    def get_component(self, cid: int) -> tuple[LiveComponent, Any] | None:
        """
        Get a component and its context by CID.

        Args:
            cid: Component ID

        Returns:
            Tuple of (component, context) or None if not found
        """
        if cid not in self._components:
            return None
        return (self._components[cid], self._contexts[cid])

    def get_context(self, cid: int) -> Any:
        """Get a component's context by CID."""
        return self._contexts.get(cid)

    def set_context(self, cid: int, context: Any) -> None:
        """Set a component's context by CID."""
        self._contexts[cid] = context

    async def run_pending_lifecycle(self) -> None:
        """
        Execute pending mount and update calls.

        Should be called after template rendering to process any
        components that were registered during the render.
        """
        # Process mounts first
        while self._pending_mounts:
            cid, assigns = self._pending_mounts.pop(0)
            await self._run_mount(cid, assigns)

        # Then process updates
        while self._pending_updates:
            cid, assigns = self._pending_updates.pop(0)
            await self._run_update(cid, assigns)

    async def _run_mount(self, cid: int, assigns: dict[str, Any]) -> None:
        """Run mount lifecycle for a component."""
        if cid not in self._components:
            logger.warning(f"Cannot mount component cid={cid}: not found")
            return

        component = self._components[cid]
        socket = self._create_socket(cid)

        component_name = component.__class__.__name__
        try:
            # Pass assigns to mount so component can initialize from parent props
            await component.mount(socket, assigns)
            # Persist context changes
            self._contexts[cid] = socket.context
            logger.debug(f"Component {component_name} (cid={cid}) mounted successfully")
        except Exception as e:
            logger.error(f"Error in {component_name}.mount() (cid={cid}): {e}", exc_info=True)
            raise

        # After mount, run update with initial assigns (Phoenix pattern)
        await self._run_update(cid, assigns)

    async def _run_update(self, cid: int, assigns: dict[str, Any]) -> None:
        """Run update lifecycle for a component."""
        if cid not in self._components:
            logger.warning(f"Cannot update component cid={cid}: not found")
            return

        component = self._components[cid]
        socket = self._create_socket(cid)

        component_name = component.__class__.__name__
        try:
            await component.update(socket, assigns)
            # Persist context changes
            self._contexts[cid] = socket.context
            logger.debug(
                f"Component {component_name} (cid={cid}) updated with assigns: {list(assigns.keys())}"
            )
        except Exception as e:
            logger.error(f"Error in {component_name}.update() (cid={cid}): {e}", exc_info=True)
            raise

    async def handle_event(self, cid: int, event: str, payload: dict[str, Any]) -> None:
        """
        Route an event to a specific component.

        Called when an event has phx-target pointing to this component's CID.

        Args:
            cid: Target component's CID
            event: Event name
            payload: Event payload
        """
        if cid not in self._components:
            logger.warning(f"Event '{event}' targeted non-existent component cid={cid}")
            return

        component = self._components[cid]
        socket = self._create_socket(cid)

        component_name = component.__class__.__name__
        try:
            await component.handle_event(event, payload, socket)
            # Persist context changes
            self._contexts[cid] = socket.context
            logger.debug(f"Component {component_name} (cid={cid}) handled event '{event}'")
        except Exception as e:
            logger.error(
                f"Error in {component_name}.handle_event('{event}') (cid={cid}): {e}", exc_info=True
            )
            raise

    def render_component(self, cid: int, parent_meta: PyViewMeta) -> Any:
        """
        Render a component and return its template result.

        Args:
            cid: Component's CID
            parent_meta: Parent LiveView's meta

        Returns:
            The result of component.template()
        """
        if cid not in self._components:
            logger.warning(f"Cannot render component cid={cid}: not found")
            return None

        component = self._components[cid]
        context = self._contexts[cid]
        component_slots = self._slots.get(cid, {})
        meta = ComponentMeta(cid=cid, parent_meta=parent_meta, slots=component_slots)

        return component.template(context, meta)

    async def send_to_parent(self, event: str, payload: dict[str, Any]) -> None:
        """
        Send an event to the parent LiveView.

        Called by ComponentSocket.send_parent().

        Args:
            event: Event name
            payload: Event payload
        """
        await self.parent_socket.liveview.handle_event(event, payload, self.parent_socket)

    def _create_socket(self, cid: int) -> ComponentSocket:
        """Create a ComponentSocket for lifecycle/event calls."""
        return ComponentSocket(
            context=self._contexts.get(cid, {}),
            cid=cid,
            manager=self,
        )

    def unregister(self, cid: int) -> None:
        """
        Remove a component from the manager.

        Called when a component is removed from the DOM.

        Args:
            cid: Component's CID
        """
        if cid in self._components:
            del self._components[cid]
        if cid in self._contexts:
            del self._contexts[cid]
        if cid in self._slots:
            del self._slots[cid]

        # Remove from key mapping
        key_to_remove = None
        for key, stored_cid in self._by_key.items():
            if stored_cid == cid:
                key_to_remove = key
                break
        if key_to_remove:
            del self._by_key[key_to_remove]

        logger.debug(f"Component cid={cid} unregistered")

    def clear(self) -> None:
        """Clear all components. Called on socket close."""
        self._components.clear()
        self._contexts.clear()
        self._slots.clear()
        self._by_key.clear()
        self._pending_mounts.clear()
        self._pending_updates.clear()
        self._seen_this_render.clear()
        logger.debug("ComponentsManager cleared")

    def begin_render(self) -> None:
        """
        Start a new render cycle.

        Clears the set of seen components. Call this before rendering
        the parent LiveView template.
        """
        self._seen_this_render.clear()

    def prune_stale_components(self) -> list[int]:
        """
        Remove components that weren't seen during this render cycle.

        Components not referenced in the current render are considered
        removed from the DOM and should be cleaned up.

        Returns:
            List of CIDs that were pruned
        """
        all_cids = set(self._components.keys())
        stale_cids = all_cids - self._seen_this_render

        for cid in stale_cids:
            self.unregister(cid)

        if stale_cids:
            logger.debug(f"Pruned {len(stale_cids)} stale components: {stale_cids}")

        return list(stale_cids)

    @property
    def component_count(self) -> int:
        """Number of registered components."""
        return len(self._components)

    def get_all_cids(self) -> list[int]:
        """Get all registered CIDs."""
        return list(self._components.keys())

    def get_seen_cids(self) -> set[int]:
        """Get CIDs that were seen (registered) during the current render cycle."""
        return self._seen_this_render.copy()

    def has_pending_lifecycle(self) -> bool:
        """Check if there are components waiting for mount/update."""
        return bool(self._pending_mounts) or bool(self._pending_updates)
