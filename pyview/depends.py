"""Simple dependency injection for PyView.

This module provides a minimal Depends() marker for declaring dependencies
that should be injected into LiveView methods, plus injectable types like Session.

Example:
    from pyview import LiveView, LiveViewSocket, Depends, Session

    async def get_auth_token(session: Session) -> AuthToken:
        return AuthToken(session["id_token"])

    async def get_user_service(token: AuthToken = Depends(get_auth_token)) -> UserService:
        return UserService(auth_token=token)

    class MyView(LiveView[MyContext]):
        async def mount(
            self,
            socket: LiveViewSocket,
            user_service: UserService = Depends(get_user_service),
        ):
            socket.context = {"users": await user_service.list_users()}

Testing:
    Dependencies are just default values. Pass mocks directly in tests:

        await view.mount(socket=mock_socket, user_service=mock_service)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any, Callable, Coroutine, TypeVar, overload

_T = TypeVar("_T")


class _SessionInjector:
    """Marker for session injection via type annotation."""

    pass


# Type marker for session injection.
Session = Annotated[dict[str, Any], _SessionInjector()]


@dataclass(frozen=True)
class _DependsMarker:
    """Runtime marker for dependency injection.

    This is the actual class used at runtime. The public `Depends` name
    is typed as a function returning T for better type inference.
    """

    dependency: Callable[..., Any]
    use_cache: bool = True


if TYPE_CHECKING:
    # At type-check time, Depends() returns the dependency's return type.
    # This allows: `token: AuthToken = Depends(get_auth_token)` to type-check.
    # The first overload handles async functions (unwraps Coroutine).
    @overload
    def Depends(
        dependency: Callable[..., Coroutine[Any, Any, _T]], use_cache: bool = True
    ) -> _T: ...
    @overload
    def Depends(dependency: Callable[..., _T], use_cache: bool = True) -> _T: ...

    # Implementation stub required by @overload (never actually called)
    def Depends(dependency: Callable[..., Any], use_cache: bool = True) -> Any: ...

else:
    # At runtime, Depends is the actual dataclass
    Depends = _DependsMarker
