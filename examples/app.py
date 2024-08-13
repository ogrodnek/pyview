from starlette.responses import HTMLResponse
from starlette.staticfiles import StaticFiles
from starlette.routing import Route
from pyview import PyView, defaultRootTemplate
from markupsafe import Markup
from .format_examples import ExampleEntry, format_examples

from .views import (
    CountLiveView,
    CountLiveViewPubSub,
    VolumeLiveView,
    FifaAudienceLiveView,
    StatusLiveView,
    PodcastLiveView,
    PlantsLiveView,
    RegistrationLiveView,
    JsCommandsLiveView,
    PingLiveView,
    CheckboxLiveView,
    PresenceLiveView,
    MapLiveView,
    FileUploadDemoLiveView,
    KanbanLiveView,
)

app = PyView()
app.mount(
    "/static",
    StaticFiles(
        packages=[
            ("pyview", "static"),
            ("examples.views.maps", "static"),
            ("examples.views.kanban", "static"),
        ]
    ),
    name="static",
)

css = """
<link rel="stylesheet" href="https://classless.de/classless.css">
<link rel="stylesheet" href="https://unpkg.com/nprogress@0.2.0/nprogress.css" />

<!-- Leaflet CSS + JS for maps example -->
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
    integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="" />
    
 <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
     integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
     crossorigin=""></script>

<script defer type="text/javascript" src="/static/map.js"></script>

<!-- Sortable JS for kanban example -->
<script src="https://cdn.jsdelivr.net/npm/sortablejs@1.15.0/Sortable.min.js"></script>
<script src="/static/kanban.js"></script>
"""


def content_wrapper(_context, content: Markup) -> Markup:
    return Markup("<a href='/'>Home</a>") + content


app.rootTemplate = defaultRootTemplate(css=Markup(css), content_wrapper=content_wrapper)

routes = [
    ("/count", CountLiveView),
    ("/count_pubsub", CountLiveViewPubSub),
    ("/volume", VolumeLiveView),
    ("/registration", RegistrationLiveView),
    ("/plants", PlantsLiveView),
    ("/fifa", FifaAudienceLiveView),
    ("/podcasts", PodcastLiveView),
    ("/status", StatusLiveView),
    ("/js_commands", JsCommandsLiveView),
    ("/webping", PingLiveView),
    # (
    #     "/checkboxes",
    #     CheckboxLiveView,
    #     "Checkboxes",
    #     "checkboxes",
    #     """
    #     A silly multi-user game where you can click checkboxes.
    #     """,
    # ),
    ("/presence", PresenceLiveView),
    ("/maps", MapLiveView),
    ("/file_upload", FileUploadDemoLiveView),
    ("/kanban", KanbanLiveView),
]


async def get(request):
    def render_example(e: ExampleEntry):
        src_link = f"https://github.com/ogrodnek/pyview/tree/main/{e.src_path}"
        return f"""
        <div class="card">
        <p><a href='{e.url_path}'>{e.title}</a></p>
        <p>{e.text}</p>
        <p><a target="_main" style="font-size: 12px" href="{src_link}"><i>Source Code</i></a></p>
        </div>
        """

    return HTMLResponse(
        f"""
        <html>
        <head>
          <title>PyView Examples</title>
          {css}
        </head>
        <body>
        <div style='display: flex; justify-content: space-between; align-items: center'>
          <img src="https://pyview.rocks/images/pyview_logo_512.png" width="96px" />
          <a href="https://github.com/ogrodnek/pyview">Github</a>
        </div>
        <div>
        <h1 style='padding-bottom: 8px'>PyView Examples</h1>
        {"".join([render_example(e) for e in format_examples(routes)])}
        </div>
        </body>
        </html>
        """
    )


app.routes.append(Route("/", get, methods=["GET"]))

for path, view in routes:
    app.add_live_view(path, view)
