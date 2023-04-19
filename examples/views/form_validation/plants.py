from pyview import LiveView, LiveViewSocket
from dataclasses import dataclass, field
from .data import plants, Plant
from datetime import datetime
from pyview.changesets import change_set, ChangeSet


@dataclass
class PlantsContext:
    plants: list[Plant]
    changeset: ChangeSet[Plant] = field(default_factory=lambda: change_set(Plant))

    class Config:
        error_msg_templates = {
            "value_error.any_str.min_length": "Name must be at least 3 characters",
            "value_error.any_str.max_length": "Name must be at most 20 characters",
        }


class PlantsLiveView(LiveView[PlantsContext]):
    async def mount(self, socket: LiveViewSocket[PlantsContext]):
        socket.context = PlantsContext(plants())

    async def handle_event(self, event, payload, socket: LiveViewSocket[PlantsContext]):
        if event == "water":
            plant = next(
                (p for p in socket.context.plants if p.id == payload["id"]), None
            )
            if plant:
                print(f"Watering {plant.name}...")
                plant.last_watered = datetime.now()
        if event == "reset":
            socket.context.plants = plants(reset=True)

        if event == "save":
            # TODO: should really look at the model...
            v = socket.context.changeset.model
            if v:
                socket.context.plants.append(v)
                socket.context = PlantsContext(plants=socket.context.plants)
            return

        if event == "validate":
            socket.context.changeset.apply(payload)
