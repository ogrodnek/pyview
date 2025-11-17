from typing import TypedDict

from pyview import ConnectedLiveViewSocket, LiveView, LiveViewSocket

from .data import FifaAudience, Paging, list_items


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
        socket.context = FifaContext(
            {"audiences": list_items(paging), "paging": paging}
        )

    async def handle_event(
        self, event, payload, socket: ConnectedLiveViewSocket[FifaContext]
    ):
        paging = socket.context["paging"]
        paging.perPage = int(payload["perPage"][0])
        paging.page = 1
        audiences = list_items(paging)

        socket.context["audiences"] = audiences

        await socket.push_patch(
            "/fifa", {"page": paging.page, "perPage": paging.perPage}
        )

    async def handle_params(self, url, params, socket: LiveViewSocket[FifaContext]):
        paging = socket.context["paging"]
        if "page" in params:
            paging.page = int(params["page"][0])
        if "perPage" in params:
            paging.perPage = int(params["perPage"][0])

        audiences = list_items(paging)
        socket.context["audiences"] = audiences
