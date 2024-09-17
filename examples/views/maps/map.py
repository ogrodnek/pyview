from pyview import LiveView, LiveViewSocket, ConnectedLiveViewSocket
from dataclasses import dataclass
from .parks import national_parks
from pyview.vendor.ibis import filters
from typing import Any
import json


@filters.register
def json_encode(val: Any) -> str:
    return json.dumps(val)


@dataclass
class MapContext:
    parks: list[dict]
    selected_park_name: str


class MapLiveView(LiveView[MapContext]):
    """
    Maps

    A simple example of using Leaflet.js with PyView, and sending information back and
    forth between the liveview and the JS library.
    """

    async def mount(self, socket: LiveViewSocket[MapContext], session):
        socket.context = MapContext(
            parks=national_parks, selected_park_name=national_parks[0]["name"]
        )

    async def handle_event(
        self, event, payload, socket: ConnectedLiveViewSocket[MapContext]
    ):
        print(event, payload)

        park = [p for p in national_parks if p["name"] == payload["name"]][0]
        socket.context.selected_park_name = park["name"]

        await socket.push_event("highlight-park", park)
