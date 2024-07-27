from pyview import LiveView, LiveViewSocket
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
    async def mount(self, socket: LiveViewSocket[MapContext], _session):
        socket.context = MapContext(
            parks=national_parks, selected_park_name=national_parks[0]["name"]
        )

    async def handle_event(self, event, payload, socket: LiveViewSocket[MapContext]):
        print(event, payload)

        park = [p for p in national_parks if p["name"] == payload["name"]][0]
        socket.context.selected_park_name = park["name"]

        await socket.push_event("highlight-park", park)
