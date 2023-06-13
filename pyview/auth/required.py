import typing
from dataclasses import dataclass
from starlette.websockets import WebSocket
from starlette.authentication import requires as starlette_requires, has_required_scope
from .provider import AuthProvider, AuthProviderFactory
from pyview import LiveView

_CallableType = typing.TypeVar("_CallableType", bound=typing.Callable)


@dataclass
class RequiredScopeAuthProvider(AuthProvider):
    scopes: typing.Sequence[str]
    status_code: int = 403
    redirect: typing.Optional[str] = None

    def wrap(self, func: _CallableType) -> _CallableType:
        return starlette_requires(self.scopes, self.status_code, self.redirect)(func)

    def has_required_auth(self, websocket: WebSocket) -> bool:
        return has_required_scope(websocket, self.scopes)


def requires(
    scopes: typing.Union[str, typing.Sequence[str]],
    status_code: int = 403,
    redirect: typing.Optional[str] = None,
) -> typing.Callable[[type[LiveView]], type[LiveView]]:
    def decorator(cls: type[LiveView]) -> type[LiveView]:
        scopes_list = [scopes] if isinstance(scopes, str) else list(scopes)
        return AuthProviderFactory.set(cls, RequiredScopeAuthProvider(scopes_list, status_code, redirect))

    return decorator
