from pyview import LiveView, LiveViewSocket
from dataclasses import dataclass, field
from .recipe_db import Recipe, all_recipes


@dataclass
class RecipesContext:
    recipes: list[Recipe]


class RecipesLiveView(LiveView[RecipesContext]):
    """
    Recipes

    This example shows how to use components to encapsulate functionality.
    """

    async def mount(self, socket: LiveViewSocket, session):
        socket.context = RecipesContext(recipes=all_recipes())
        socket.live_title = "Recipes"

    async def handle_event(self, event, payload, socket):
        if event == "bookmark" and "id" in payload:
            id = payload["id"]
            recipe = next((r for r in socket.context.recipes if r.id == id), None)
            if recipe is not None:
                recipe.bookmarked = not recipe.bookmarked
        if event == "rate" and "id" in payload and "rating" in payload:
            id = payload["id"]
            recipe = next((r for r in socket.context.recipes if r.id == id), None)
            if recipe is not None:
                print("Set rating", recipe.rating, "to", payload["rating"])

                recipe.rating = int(payload["rating"])
