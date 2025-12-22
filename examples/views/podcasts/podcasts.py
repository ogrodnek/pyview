from dataclasses import dataclass
from typing import Optional

from pyview import LiveView, LiveViewSocket

from .data import Podcast, podcasts


@dataclass
class PodcastContext:
    currentPodcast: Podcast
    podcasts: list[Podcast]


class PodcastLiveView(LiveView):
    """
    Podcasts

    URL Parameters, client navigation updates, and dynamic page titles.
    """

    async def mount(self, socket: LiveViewSocket[PodcastContext], session):
        casts = podcasts()
        socket.context = PodcastContext(casts[0], casts)

    async def handle_params(self, socket: LiveViewSocket[PodcastContext], id: Optional[int] = None):
        def _current_podcast():
            sel: Optional[Podcast] = None
            if id is not None:
                sel = next((s for s in socket.context.podcasts if s.id == id), None)
            if sel is not None:
                return sel

            return socket.context.podcasts[0]

        p = _current_podcast()
        socket.context.currentPodcast = p
        socket.live_title = p.title
