"""Simple dependency injection for PyView.

This module provides a minimal Depends() marker for declaring dependencies
that should be injected into LiveView methods.

Example:
    from pyview import LiveView, LiveViewSocket, Depends

    async def get_auth_token(session: dict) -> AuthToken:
        return AuthToken(session["id_token"])

    async def get_user_service(token: AuthToken = Depends(get_auth_token)) -> UserService:
        return UserService(auth_token=token)

    class MyView(LiveView[MyContext]):
        async def mount(
            self,
            socket: LiveViewSocket,
            session: dict,
            user_service: UserService = Depends(get_user_service),
        ):
            socket.context = {"users": await user_service.list_users()}

Testing:
    Dependencies are just default values. Pass mocks directly in tests:

        await view.mount(socket=mock_socket, session={}, user_service=mock_service)
"""

from dataclasses import dataclass
from typing import Any, Callable


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
