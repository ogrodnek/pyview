import sys

from .format_examples import ExampleEntry, ExampleRoute, format_examples
from .views import (
    CollabEditorLiveView,
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

routes: list[ExampleRoute] = [
    ExampleRoute("/count", CountLiveView, ("basics",)),
    ExampleRoute("/count_pubsub", CountLiveViewPubSub, ("basics", "realtime")),
    ExampleRoute("/volume", VolumeLiveView, ("basics",)),
    ExampleRoute("/registration", RegistrationLiveView, ("forms",)),
    ExampleRoute("/plants", PlantsLiveView, ("forms",)),
    ExampleRoute("/fifa", FifaAudienceLiveView, ("advanced",)),
    ExampleRoute("/podcasts", PodcastLiveView, ("advanced",)),
    ExampleRoute("/status", StatusLiveView, ("realtime",)),
    ExampleRoute("/js_commands", JsCommandsLiveView, ("integrations",)),
    ExampleRoute("/webping", PingLiveView, ("realtime",)),
    ExampleRoute("/presence", PresenceLiveView, ("realtime",)),
    ExampleRoute("/maps", MapLiveView, ("integrations",)),
    ExampleRoute("/file_upload", FileUploadDemoLiveView, ("forms",)),
    ExampleRoute("/kanban", KanbanLiveView, ("integrations",)),
    ExampleRoute("/includes", IncludesLiveView, ("basics",)),
    ExampleRoute("/streams", StreamsDemoLiveView, ("realtime", "advanced")),
    ExampleRoute("/flash", FlashDemoLiveView, ("basics",)),
    ExampleRoute(
        "/collab_editor",
        CollabEditorLiveView,
        ("realtime", "integrations"),
        additional_paths=("/collab_editor/{document_id:uuid}",),
    ),
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
            ExampleRoute("/counter_tstring", CounterTStringLiveView, ("basics", "advanced")),
            ExampleRoute("/streams_tstring", StreamsTStringLiveView, ("realtime", "advanced")),
            ExampleRoute("/flash_tstring", FlashDemoTStringLiveView, ("basics", "advanced")),
            ExampleRoute(
                "/js_commands_tstring",
                JsCommandsTStringLiveView,
                ("integrations", "advanced"),
            ),
            ExampleRoute("/components/stateless", StatelessComponentsDemo, ("components",)),
            ExampleRoute("/components/stateful", StatefulComponentsDemo, ("components",)),
            ExampleRoute("/components/slots", SlotsDemo, ("components",)),
        ]
    )


def get_all_examples() -> list[ExampleEntry]:
    return list(format_examples(routes))
