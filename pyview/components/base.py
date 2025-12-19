"""
Base classes for PyView LiveComponents.

LiveComponents are stateful, reusable UI components that can handle their own
events and maintain isolated state. They are inspired by Phoenix LiveComponents.

Key concepts:
- LiveComponent: Base class defining component behavior (lifecycle, events, template)
- ComponentMeta: Metadata passed to template(), includes `myself` (CID) for event targeting
- ComponentSocket: Handle passed to lifecycle methods for state access

CID (Component ID) is stored externally in ComponentsManager, not on the component
instance. This keeps components clean and testable.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generic, Optional, TypeVar

if TYPE_CHECKING:
    from string.templatelib import Template  # type: ignore[import-not-found]

    from pyview.meta import PyViewMeta

    # Avoid circular import - manager imports this module
    from .manager import ComponentsManager

T = TypeVar("T")


@dataclass
class ComponentMeta:
    """
    Metadata passed to component's template() method.

    Contains the component's CID (Component ID) which is used for event targeting
    via phx-target={meta.myself}, and any slots passed from the parent.

    Attributes:
        cid: The component's unique identifier (assigned by ComponentsManager)
        parent_meta: The parent LiveView's PyViewMeta
        slots: Dictionary of slot content passed from parent template
    """

    cid: int
    parent_meta: "PyViewMeta"
    slots: "dict[str, Template]" = field(default_factory=dict)

    @property
    def myself(self) -> int:
        """
        Returns the CID for use in phx-target.

        This is the Python equivalent of Phoenix's @myself.
        Use it in templates: phx-target="{meta.myself}"
        """
        return self.cid


@dataclass
class ComponentSocket(Generic[T]):
    """
    Socket passed to component lifecycle methods.

    This is an ephemeral handle created for each lifecycle call (mount, update,
    handle_event). The context is the persistent state, stored externally in
    ComponentsManager.

    Attributes:
        context: The component's current state (read/write)
        cid: The component's unique identifier
        manager: Reference to the ComponentsManager for advanced operations
    """

    context: T
    cid: int
    manager: "ComponentsManager"

    @property
    def myself(self) -> int:
        """Returns the CID for use in templates/events."""
        return self.cid

    async def send_parent(self, event: str, payload: Optional[dict[str, Any]] = None) -> None:
        """
        Send an event to the parent LiveView.

        This allows components to communicate upward to their parent.
        The parent's handle_event will be called with this event.

        Args:
            event: Event name
            payload: Optional event payload
        """
        if payload is None:
            payload = {}
        await self.manager.send_to_parent(event, payload)


class LiveComponent(Generic[T]):
    """
    Base class for stateful live components.

    LiveComponents have their own state and can handle events targeted at them
    via phx-target={meta.myself}. They are identified by a unique CID assigned
    by the ComponentsManager.

    Lifecycle:
        1. mount(socket, assigns) - Called once when component first appears
        2. update(socket, assigns) - Called when parent passes new assigns
        3. template(assigns, meta) - Called to render the component
        4. handle_event(event, payload, socket) - Called for targeted events

    Error Handling:
        Errors in lifecycle methods (mount, update, handle_event) are logged with
        full context (component class name, CID, method) and then re-raised. This
        matches Phoenix LiveView behavior where component errors crash the parent
        LiveView process. The client-side JavaScript will automatically attempt
        to reconnect and remount the view.

        This "let it crash" approach ensures:
        - Errors are visible during development
        - No partial/inconsistent UI state
        - Automatic recovery via reconnection

    Example:
        class Counter(LiveComponent[CounterContext]):
            async def mount(self, socket: ComponentSocket[CounterContext], assigns: dict):
                # Initialize state from parent assigns
                socket.context = {
                    "count": assigns.get("initial", 0),
                    "label": assigns.get("label", "Counter")
                }

            async def update(self, socket: ComponentSocket[CounterContext], assigns: dict):
                # React to changed assigns from parent (e.g., label updates)
                if "label" in assigns:
                    socket.context["label"] = assigns["label"]

            def template(self, assigns: CounterContext, meta: ComponentMeta):
                return t'''
                    <div>
                        <span>{assigns["count"]}</span>
                        <button phx-click="increment" phx-target="{meta.myself}">+</button>
                    </div>
                '''

            async def handle_event(self, event: str, payload: dict, socket: ComponentSocket):
                if event == "increment":
                    socket.context["count"] += 1
    """

    async def mount(self, socket: ComponentSocket[T], assigns: dict[str, Any]) -> None:
        """
        Called once when the component is first added to the page.

        Use this to initialize the component's state (socket.context) from
        the initial assigns passed by the parent.

        Args:
            socket: ComponentSocket for state access
            assigns: Initial assigns from parent (e.g., label, initial values)
        """
        pass

    async def update(self, socket: ComponentSocket[T], assigns: dict[str, Any]) -> None:
        """
        Called after mount() and on subsequent renders with new assigns.

        This is called:
        1. Immediately after mount() with the initial assigns
        2. On re-renders when the parent passes new assigns via live_component()

        Override to handle assigns that should update component state.
        The default is a no-op - components explicitly decide what affects their state.

        Args:
            socket: ComponentSocket for state access
            assigns: Assigns passed from parent via live_component()
        """
        pass

    def template(self, assigns: T, meta: ComponentMeta) -> Any:
        """
        Render the component's template.

        Must return a Template (t-string). The meta parameter provides
        access to `myself` for event targeting.

        Args:
            assigns: The component's current context/state
            meta: ComponentMeta with cid/myself for event targeting

        Returns:
            A t-string Template
        """
        raise NotImplementedError("LiveComponent subclasses must implement template()")

    async def handle_event(
        self, event: str, payload: dict[str, Any], socket: ComponentSocket[T]
    ) -> None:
        """
        Handle events targeted at this component.

        Events are targeted via phx-target="{meta.myself}" in templates.
        Without phx-target, events go to the parent LiveView instead.

        Args:
            event: Event name (e.g., "increment", "submit")
            payload: Event payload/value
            socket: ComponentSocket for state access
        """
        pass
