from starlette.responses import HTMLResponse
from starlette.staticfiles import StaticFiles
from starlette.routing import Route
from pyview import PyView, defaultRootTemplate
from markupsafe import Markup

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
)

app = PyView()
app.mount("/static", StaticFiles(packages=[("pyview", "static")]), name="static")

css = """
<link rel="stylesheet" href="https://classless.de/classless.css">
<link rel="stylesheet" href="https://unpkg.com/nprogress@0.2.0/nprogress.css" />
"""


def content_wrapper(_context, content: Markup) -> Markup:
    return Markup("<a href='/'>Home</a>") + content


app.rootTemplate = defaultRootTemplate(css=Markup(css), content_wrapper=content_wrapper)

routes = [
    (
        "/count",
        CountLiveView,
        "Basic Counter",
        "count.py",
        """
        Gotta start somewhere, right? This example shows how to send click events
        to the backend to update state.  We also snuck in handling URL params.
        """,
    ),
    (
        "/count_pubsub",
        CountLiveViewPubSub,
        "Basic Counter with PubSub",
        "count_pubsub.py",
        """
        The counter example, but with PubSub.  Open this example in multiple windows
        to see the state update in real time across all windows.
        """,
    ),
    ("/volume", VolumeLiveView, "Volume Control", "volume.py", "Keyboard events!"),
    (
        "/registration",
        RegistrationLiveView,
        "Registration Form Validation",
        "registration",
        "Form validation using Pydantic",
    ),
    ("/plants", PlantsLiveView, "Form Validation 2", "form_validation", ""),
    (
        "/fifa",
        FifaAudienceLiveView,
        "Table Pagination",
        "fifa",
        "Table Pagination, and updating the URL from the backend.",
    ),
    (
        "/podcasts",
        PodcastLiveView,
        "Podcasts",
        "podcasts",
        """
     URL Parameters, client navigation updates, and dynamic page titles.
     """,
    ),
    (
        "/status",
        StatusLiveView,
        "Realtime Status Dashboard",
        "status",
        "Pushing updates from the backend to the client.",
    ),
    (
        "/js_commands",
        JsCommandsLiveView,
        "JS Commands",
        "js_commands",
        """
        JS Commands let you update the DOM without making a trip to the server.
     """,
    ),
    (
        "/webping",
        PingLiveView,
        "Web Ping",
        "webping",
        """
     Another example of pushing updates from the backend to the client.
     """,
    ),
    (
        "/checkboxes",
        CheckboxLiveView,
        "Checkboxes",
        "checkboxes",
        """
        A silly multi-user game where you can click checkboxes.
        """,
    ),
    (
        "/presence",
        PresenceLiveView,
        "Presence",
        "presence",
        """
        A simple example of presence tracking.  Open this example in multiple windows
        """,
    ),
]

for path, view, _, _, _ in routes:
    app.add_live_view(path, view)


async def get(request):
    def render_example(path, title, src_file, text):
        src_link = (
            f"https://github.com/ogrodnek/pyview/tree/main/examples/views/{src_file}"
        )
        return f"""
        <div class="card">
        <p><a href='{path}'>{title}</a></p>
        <p>{text}</p>
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
        {"".join([render_example(k,t,src, text) for k, _, t, src, text in routes])}
        </div>
        </body>
        </html>
        """
    )


app.routes.append(Route("/", get, methods=["GET"]))
