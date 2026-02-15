import os

from markupsafe import Markup
from starlette.staticfiles import StaticFiles

from pyview import PyView, defaultRootTemplate
from pyview.vendor import ibis
from pyview.vendor.ibis.loaders import FileReloader

from .example_registry import routes
from .views.index import IndexLiveView

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


def content_wrapper(context, content: Markup) -> Markup:
    # The index page renders its own header — skip the nav wrapper
    if context.get("title") == "PyView Live Demos":
        return content

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

app.add_live_view("/", IndexLiveView)

for path, view, _tags in routes:
    app.add_live_view(path, view)
