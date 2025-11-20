import os
import sys

from markupsafe import Markup
from starlette.responses import HTMLResponse
from starlette.routing import Route
from starlette.staticfiles import StaticFiles

from pyview import PyView, defaultRootTemplate
from pyview.vendor import ibis
from pyview.vendor.ibis.loaders import FileReloader

from .format_examples import ExampleEntry, format_examples
from .views import (
    CountLiveView,
    CountLiveViewPubSub,
    FifaAudienceLiveView,
    FileUploadDemoLiveView,
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
    VolumeLiveView,
)

# T-string example is only available on Python 3.14+
if sys.version_info >= (3, 14):
    from .views.count.count_tstring import CounterTStringLiveView
    from .views.count.count_auto_dispatch import CounterAutoDispatchLiveView

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
<script src="https://cdn.tailwindcss.com"></script>
<script>
  tailwind.config = {
    theme: {
      extend: {
        colors: {
          'pyview-pink': {
            50: '#fdf2f8',
            100: '#fce7f3',
            200: '#fbcfe8',
            300: '#f9a8d4',
            400: '#f472b6',
            500: '#ec4899',
            600: '#db2777',
            700: '#be185d',
            800: '#9d174d',
            900: '#831843'
          }
        },
        fontFamily: {
          'sans': ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
          'display': ['Poppins', 'system-ui', '-apple-system', 'sans-serif']
        }
      }
    }
  }
</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Poppins:wght@600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/nprogress@0.2.0/nprogress.css" />

<!-- Leaflet CSS + JS for maps example -->
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
    integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="" />

 <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
     integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
     crossorigin=""></script>

<script defer type="text/javascript" src="/static/map.js"></script>

<!-- Sortable JS for kanban example -->
<script src="https://unpkg.com/sortablejs@1.15.0/Sortable.min.js"></script>
<script src="/static/kanban.js"></script>
"""


def content_wrapper(_context, content: Markup) -> Markup:
    return (
        Markup(
            """
    <div class="min-h-screen bg-gray-50">
        <nav class="bg-white shadow-sm border-b border-gray-200">
            <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div class="flex justify-between h-16">
                    <div class="flex items-center">
                        <a href="/" class="text-gray-900 hover:text-gray-600 font-medium">← All Examples</a>
                    </div>
                </div>
            </div>
        </nav>
        <div class="py-8">
    """
        )
        + content
        + Markup("</div></div>")
    )


app.rootTemplate = defaultRootTemplate(css=Markup(css), content_wrapper=content_wrapper)

current_file_dir = os.path.dirname(os.path.abspath(__file__))
ibis.loader = FileReloader(os.path.join(current_file_dir, "views"))

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
    ("/includes", IncludesLiveView),
]

# Add t-string example on Python 3.14+
if sys.version_info >= (3, 14):
    routes.append(("/counter_tstring", CounterTStringLiveView))
    routes.append(("/counter_auto_dispatch", CounterAutoDispatchLiveView))


async def get(request):
    def render_example(e: ExampleEntry):
        src_link = f"https://github.com/ogrodnek/pyview/tree/main/{e.src_path}"
        return f"""
        <div class="relative bg-white rounded-lg shadow-sm border border-gray-200 p-6 flex flex-col h-full hover:shadow-md hover:border-pyview-pink-300 transition-all group">
            <a href='{e.url_path}' class="absolute inset-0 z-10" aria-label="View {e.title} demo"></a>
            <h3 class="text-lg font-display font-semibold text-gray-900 mb-2 group-hover:text-pyview-pink-600 transition-colors">
                {e.title}
            </h3>
            <p class="text-gray-600 text-sm mb-4 flex-grow">{e.text}</p>
            <div class="flex items-center justify-between mt-auto">
                <span class="text-sm font-medium text-pyview-pink-600 group-hover:text-pyview-pink-800 inline-flex items-center">
                    <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                    View Demo →
                </span>
                <a target="_blank" href="{src_link}" class="relative z-20 text-sm text-gray-500 hover:text-gray-700 inline-flex items-center">
                    <svg class="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M12.316 3.051a1 1 0 01.633 1.265l-4 12a1 1 0 11-1.898-.632l4-12a1 1 0 011.265-.633zM5.707 6.293a1 1 0 010 1.414L3.414 10l2.293 2.293a1 1 0 11-1.414 1.414l-3-3a1 1 0 010-1.414l3-3a1 1 0 011.414 0zm8.586 0a1 1 0 011.414 0l3 3a1 1 0 010 1.414l-3 3a1 1 0 11-1.414-1.414L16.586 10l-2.293-2.293a1 1 0 010-1.414z" clip-rule="evenodd" />
                    </svg>
                    Source
                </a>
            </div>
        </div>
        """

    return HTMLResponse(
        f"""
        <html>
        <head>
          <title>PyView Examples</title>
          <meta name="viewport" content="width=device-width, initial-scale=1">
          {css}
        </head>
        <body class="bg-gray-50">
        <div class="min-h-screen">
            <!-- Header -->
            <header class="bg-white shadow-sm border-b border-gray-200">
                <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div class="flex justify-between items-center py-6">
                        <div class="flex items-center space-x-4">
                            <img src="https://pyview.rocks/images/pyview_logo_512.png" alt="PyView" class="h-12 w-12" />
                            <div>
                                <h1 class="text-2xl font-display text-gray-900">PyView Live Demos</h1>
                            </div>
                        </div>
                        <a href="https://github.com/ogrodnek/pyview" target="_blank"
                           class="inline-flex items-center px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50">
                            <svg class="w-5 h-5 mr-2" fill="currentColor" viewBox="0 0 20 20">
                                <path fill-rule="evenodd" d="M10 0C4.477 0 0 4.484 0 10.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0110 4.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.203 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.942.359.31.678.921.678 1.856 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0020 10.017C20 4.484 15.522 0 10 0z" clip-rule="evenodd"/>
                            </svg>
                            GitHub
                        </a>
                    </div>
                </div>
            </header>

            <!-- Main Content -->
            <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
                <div class="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
                    {"".join([render_example(e) for e in format_examples(routes)])}
                </div>
            </main>
        </div>
        </body>
        </html>
        """
    )


app.routes.append(Route("/", get, methods=["GET"]))

for path, view in routes:
    app.add_live_view(path, view)
