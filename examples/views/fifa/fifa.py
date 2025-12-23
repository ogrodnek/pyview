from dataclasses import dataclass
from typing import TypedDict

from pyview import ConnectedLiveViewSocket, LiveView, LiveViewSocket

from .data import FifaAudience, Paging, list_items


@dataclass
class PagingParams:
    page: int = 1
    perPage: int = 10


class FifaContext(TypedDict):
    audiences: list[FifaAudience]
    paging: Paging


class FifaAudienceLiveView(LiveView[FifaContext]):
    """
    Table Pagination

    Table Pagination, and updating the URL from the backend.
    """

    async def mount(self, socket: LiveViewSocket[FifaContext], session):
        paging = Paging(1, 10)
        socket.context = FifaContext({"audiences": list_items(paging), "paging": paging})

    async def handle_event(self, socket: ConnectedLiveViewSocket[FifaContext], perPage: int):
        paging = socket.context["paging"]
        paging.perPage = perPage
        paging.page = 1
        audiences = list_items(paging)

        socket.context["audiences"] = audiences

        await socket.push_patch("/fifa", {"page": paging.page, "perPage": paging.perPage})

    async def handle_params(self, socket: LiveViewSocket[FifaContext], paging_params: PagingParams):
        paging = socket.context["paging"]
        paging.page = paging_params.page
        paging.perPage = paging_params.perPage
        audiences = list_items(paging)
        socket.context["audiences"] = audiences
