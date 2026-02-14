import sys

from pyview import LiveView

from .format_examples import ExampleEntry, format_examples
from .views import (
    CountLiveView,
    CountLiveViewPubSub,
    FifaAudienceLiveView,
    FileUploadDemoLiveView,
    FlashDemoLiveView,
    IncludesLiveView,
    JsCommandsLiveView,
    KanbanLiveView,
    MapLiveView,
    PingLiveView,
    PlantsLiveView,
    PodcastLiveView,
    PresenceLiveView,
    RegistrationLiveView,
    StatusLiveView,
    StreamsDemoLiveView,
    VolumeLiveView,
)

routes: list[tuple[str, type[LiveView], list[str]]] = [
    ("/count", CountLiveView, ["basics"]),
    ("/count_pubsub", CountLiveViewPubSub, ["basics", "realtime"]),
    ("/volume", VolumeLiveView, ["basics"]),
    ("/registration", RegistrationLiveView, ["forms"]),
    ("/plants", PlantsLiveView, ["forms"]),
    ("/fifa", FifaAudienceLiveView, ["advanced"]),
    ("/podcasts", PodcastLiveView, ["advanced"]),
    ("/status", StatusLiveView, ["realtime"]),
    ("/js_commands", JsCommandsLiveView, ["integrations"]),
    ("/webping", PingLiveView, ["realtime"]),
    ("/presence", PresenceLiveView, ["realtime"]),
    ("/maps", MapLiveView, ["integrations"]),
    ("/file_upload", FileUploadDemoLiveView, ["forms"]),
    ("/kanban", KanbanLiveView, ["integrations"]),
    ("/includes", IncludesLiveView, ["basics"]),
    ("/streams", StreamsDemoLiveView, ["realtime", "advanced"]),
    ("/flash", FlashDemoLiveView, ["basics"]),
]

# T-string examples are only available on Python 3.14+
if sys.version_info >= (3, 14):
    from .views.components import SlotsDemo, StatefulComponentsDemo, StatelessComponentsDemo
    from .views.count.count_tstring import CounterTStringLiveView
    from .views.flash_demo.flash_demo_tstring import FlashDemoTStringLiveView
    from .views.js_commands.js_commands_tstring import JsCommandsTStringLiveView
    from .views.streams.streams_tstring import StreamsTStringLiveView

    routes.extend(
        [
            ("/counter_tstring", CounterTStringLiveView, ["basics", "advanced"]),
            ("/streams_tstring", StreamsTStringLiveView, ["realtime", "advanced"]),
            ("/flash_tstring", FlashDemoTStringLiveView, ["basics", "advanced"]),
            ("/js_commands_tstring", JsCommandsTStringLiveView, ["integrations", "advanced"]),
            ("/components/stateless", StatelessComponentsDemo, ["components"]),
            ("/components/stateful", StatefulComponentsDemo, ["components"]),
            ("/components/slots", SlotsDemo, ["components"]),
        ]
    )


def get_all_examples() -> list[ExampleEntry]:
    return list(format_examples(routes))
