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

from dataclasses import dataclass
from typing import Annotated, Any, Callable


class _SessionInjector:
    """Marker for session injection via type annotation."""

    pass


# Type-based session injection.
# Use this type annotation to receive the session dict:
#
#     async def get_user(session: Session) -> User:
#         return await User.get(session["user_id"])
#
# This is cleaner than name-based injection for dependency functions.
Session = Annotated[dict[str, Any], _SessionInjector()]


@dataclass(frozen=True)
class Depends:
    """
    Declare a dependency to be injected.

    Args:
        dependency: A callable (sync or async) that returns the dependency value.
        use_cache: If True (default), cache the result for this request.
                   The same dependency called multiple times returns the cached value.

    The dependency callable can itself declare Depends() parameters,
    forming a dependency chain that is resolved automatically.
    """

    dependency: Callable[..., Any]
    use_cache: bool = True
