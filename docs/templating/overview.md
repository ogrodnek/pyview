# Templating

PyView currently offers two approaches to templating: a lightweight templating language based on [ibis](https://www.dmulholl.com/docs/ibis/master/) (similar to Jinja2), and Python 3.14+ [t-string templates](https://peps.python.org/pep-0750/).

Both compile templates into a **diff tree** structure that enables efficient real-time updates. Instead of re-rendering entire pages, PyView tracks which parts of your template are static vs. dynamic, sending only the changed values over WebSocket. This is why PyView uses its own templating rather than standard engines like Jinja2.

## Templating Options

| Approach                                    | Python Version | Files                              |
| ------------------------------------------- | -------------- | ---------------------------------- |
| [HTML Templates](html-templates.md)         | 3.11+          | `.html` files alongside views      |
| [T-String Templates](t-string-templates.md) | 3.14+          | Python code in `template()` method |

## HTML Templates (Ibis)

The traditional approach uses `.html` template files with Jinja2-like syntax based on [ibis](https://www.dmulholl.com/docs/ibis/master/):

```
views/
├── counter.py       # CounterLiveView class
└── counter.html     # Template file
```

```html
<!-- counter.html -->
<div>
    <h1>Count: {{count}}</h1>
    <button phx-click="increment">+</button>
</div>
```

**Advantages:**
- Familiar syntax for anyone who's used Django, Jinja2, or similar
- Clear separation between Python logic and HTML
- Works with any Python 3.11+ installation

See [HTML Templates](html-templates.md) for the full guide.

## T-String Templates (Python 3.14+)

The newer approach uses Python's t-string literals (PEP 750) directly in your view class:

```python
from pyview.template import TemplateView

class CounterLiveView(TemplateView, LiveView[CountContext]):
    def template(self, assigns: CountContext, meta: PyViewMeta) -> Template:
        count = assigns["count"]
        return t"""<div>
            <h1>Count: {count}</h1>
            <button phx-click="increment">+</button>
        </div>"""
```

**Advantages:**
- Full Python syntax and IDE support (autocomplete, type checking)
- Composable helper methods that return template fragments
- No separate template files to manage
- Method references work directly: `phx-click={self.increment}`

See [T-String Templates](t-string-templates.md) for the full guide.

## Which Should I Use?

**Use HTML Templates if:**
- You're on Python 3.11-3.13
- You prefer separation between code and markup
- You're collaborating with designers who edit HTML directly
- You're migrating from Django, Flask, or similar frameworks

**Use T-String Templates if:**
- You're on Python 3.14+
- You want maximum type safety and IDE support
- You prefer keeping everything in Python
- You're building component-based UIs with reusable pieces

## Mixing Approaches

You can use both approaches in the same project. Each LiveView can independently choose its templating method:

```python
# Traditional HTML template (uses counter.html)
class CounterLiveView(LiveView[CountContext]):
    pass

# T-string template (uses template() method)
class AnotherCounterLiveView(TemplateView, LiveView[CountContext]):
    def template(self, assigns, meta):
        return t"<div>...</div>"
```

This makes it easy to try t-strings on new views while keeping existing HTML templates.
