from typing import Protocol, TypeVar, Callable
from starlette.websockets import WebSocket
from pyview import LiveView

_CallableType = TypeVar("_CallableType", bound=Callable)


class AuthProvider(Protocol):
    async def has_required_auth(self, websocket: WebSocket) -> bool:
        ...

    def wrap(self, func: _CallableType) -> _CallableType:
        ...


class AllowAllAuthProvider(AuthProvider):
    async def has_required_auth(self, websocket: WebSocket) -> bool:
        return True

    def wrap(self, func: _CallableType) -> _CallableType:
        return func


class AuthProviderFactory:
    @classmethod
    def get(cls, lv: type[LiveView]) -> AuthProvider:
        return getattr(lv, "__pyview_auth_provider__", AllowAllAuthProvider())

    @classmethod
    def set(cls, lv: type[LiveView], auth_provider: AuthProvider) -> type[LiveView]:
        setattr(lv, "__pyview_auth_provider__", auth_provider)
        return lv
