import random
from dataclasses import dataclass, field

from pyview import LiveView


@dataclass
class User:
    user_id: int = field(default_factory=lambda: random.randint(1, 100))

    @property
    def avatar_url(self):
        return f"https://avatar.iran.liara.run/public/{self.user_id}"


@dataclass
class IncludesContext:
    user: User = field(default_factory=User)
    pages: list[str] = field(default_factory=lambda: ["home", "about", "contact"])
    current_page: str = "home"


class IncludesLiveView(LiveView):
    """
    Template Includes

    This example shows how to include templates in other templates.
    """

    async def mount(self, socket, session):
        socket.context = IncludesContext()

    async def handle_params(self, url, params, socket):
        if "page" in params:
            socket.context.current_page = params["page"][0]
