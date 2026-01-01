---
title: HTML Templates
---

# HTML Templates (Ibis)

> **Note:** PyView supports two templating approaches. See [Templating Overview](overview.md) to compare options, or check out [T-String Templates](t-string-templates.md) for the Python 3.14+ alternative.

PyView uses a modified version of the [ibis template engine](https://www.dmulholl.com/docs/ibis/master/) with additional LiveView-specific features. This guide covers template syntax, variables, control structures, filters, and the rendering system.

## Template Basics

### Template Location

PyView automatically finds templates by looking for `.html` files in the same directory as your LiveView class:

```
views/
├── counter.py          # CounterLiveView class
├── counter.html        # Template for CounterLiveView
├── counter.css         # Optional - automatically included
├── user_list.py        # UserListLiveView class
└── user_list.html      # Template for UserListLiveView
```

### Automatic CSS Inclusion

If you create a `.css` file with the same name as your LiveView, PyView automatically includes it in the page:

```
views/
├── counter.py
├── counter.html
└── counter.css         # Automatically wrapped in <style> tags
```

This makes it easy to keep component-specific styles alongside your templates without manually managing style imports.

### Basic Template Structure

Templates combine HTML with template syntax for dynamic content:

```html
<!-- counter.html -->
<div class="counter">
    <h1>Count: {{count}}</h1>
    <button phx-click="increment">+</button>
    <button phx-click="decrement">-</button>
</div>
```

The corresponding LiveView provides the `count` variable:

```python
# counter.py
class CounterLiveView(LiveView[CountContext]):
    async def mount(self, socket: LiveViewSocket[CountContext], session):
        socket.context = {"count": 0}  # Available as {{count}} in template
```

## Template Syntax

### Variables

Display values using double curly braces:

```html
<!-- Basic variables -->
<h1>{{title}}</h1>
<p>Welcome, {{user.name}}!</p>
<span>{{item.price}}</span>

<!-- Nested access -->
<div>{{user.profile.bio}}</div>
<img src="{{user.avatar.url}}" alt="{{user.name}}'s avatar">
```

### Comments

Template comments are not rendered in the output:

```html
{# This is a comment - won't appear in HTML #}
<div>{{content}}</div>
{# TODO: Add pagination controls #}
```

## Control Structures

See the [ibis tag reference](https://www.dmulholl.com/docs/ibis/master/tags.html) for complete documentation.

### Conditional Rendering (`if`)

Show/hide content based on conditions:

```html
<!-- Basic if -->
{% if user.is_admin %}
    <button>Admin Panel</button>
{% endif %}

<!-- if/else -->
{% if items %}
    <ul>
        {% for item in items %}
            <li>{{item.name}}</li>
        {% endfor %}
    </ul>
{% else %}
    <p>No items found.</p>
{% endif %}

<!-- Multiple conditions -->
{% if user.is_authenticated %}
    {% if user.has_permission %}
        <button>Edit</button>
    {% else %}
        <span>View Only</span>
    {% endif %}
{% else %}
    <a href="/login">Login</a>
{% endif %}
```

### Loops (`for`)

Iterate over lists and collections:

```html
<!-- Basic loop -->
<ul>
    {% for user in users %}
        <li>{{user.name}} - {{user.email}}</li>
    {% endfor %}
</ul>

<!-- Loop with conditionals -->
<div class="user-list">
    {% for user in users %}
        <div class="user-card {% if user.is_active %}active{% else %}inactive{% endif %}">
            <h3>{{user.name}}</h3>
            <p>{{user.email}}</p>
            {% if user.is_admin %}
                <span class="badge">Admin</span>
            {% endif %}
        </div>
    {% endfor %}
</div>

<!-- Empty list handling -->
{% for message in messages %}
    <div class="message">{{message.text}}</div>
{% empty %}
    <p>No messages yet.</p>
{% endfor %}
```

### Loop Variables

Access loop metadata with the built-in `loop` variable:

```html
<table>
    {% for item in items %}
        <tr>
            <td>{{loop.count}}</td>
            <td>{{item.name}}</td>
            <td>
                {% if loop.is_first %}First{% endif %}
                {% if loop.is_last %}Last{% endif %}
            </td>
        </tr>
    {% endfor %}
</table>
```

**Available loop variables:**
- `loop.index` - Current iteration (0-indexed)
- `loop.count` - Current iteration (1-indexed)
- `loop.length` - Total number of items in the sequence
- `loop.is_first` - True if first iteration
- `loop.is_last` - True if last iteration
- `loop.parent` - For nested loops, the loop variable of the parent loop

## Filters

See the [ibis filter reference](https://www.dmulholl.com/docs/ibis/master/filters.html) for complete documentation.

Transform values using the pipe operator:

### Built-in Filters

```html
<!-- Text formatting -->
<h1>{{title | upper}}</h1>
<p>{{description | lower}}</p>
<span>{{name | title}}</span>

<!-- Date/time formatting -->
<time>{{created_at | dtformat:"%Y-%m-%d %H:%M"}}</time>
<span>{{updated | dtformat:"%b %d, %Y"}}</span>

<!-- Lists and sequences -->
<p>{{tags | join:", "}}</p>
<span>{{users | len}} users</span>
<div>{{items | first}}</div>
<div>{{items | last}}</div>

<!-- HTML and safety -->
<div>{{content | escape}}</div>
<div>{{html_content | striptags}}</div>

<!-- Default values -->
<span>{{optional_field | default:"Not provided"}}</span>
<img src="{{avatar | default:"/static/default-avatar.png"}}">
```

### Common Filters Reference

| Filter | Purpose | Example |
|--------|---------|---------|
| `upper` | Uppercase text | `{{name \| upper}}` |
| `lower` | Lowercase text | `{{name \| lower}}` |
| `title` | Title case | `{{name \| title}}` |
| `len` | Get length | `{{items \| len}}` |
| `join` | Join with separator | `{{tags \| join:", "}}` |
| `default` | Default value | `{{field \| default:"None"}}` |
| `escape` | HTML escape | `{{content \| escape}}` |
| `dtformat` | Date formatting | `{{date \| dtformat:"%Y-%m-%d"}}` |
| `truncatechars` | Truncate characters | `{{text \| truncatechars:50}}` |
| `truncatewords` | Truncate words | `{{text \| truncatewords:10}}` |
| `first` | First item | `{{items \| first}}` |
| `last` | Last item | `{{items \| last}}` |

### Custom Filters

Register your own filters using the `@register` decorator:

```python
from pyview.vendor.ibis.filters import register

@register
def currency(value, symbol="$"):
    """Format a number as currency."""
    return f"{symbol}{value:,.2f}"

@register("pluralize")
def pluralize_filter(count, suffix="s"):
    """Add suffix if count != 1."""
    return "" if count == 1 else suffix
```

Use in templates:

```html
<span>{{price | currency}}</span>              <!-- $1,234.56 -->
<span>{{price | currency:"€"}}</span>          <!-- €1,234.56 -->
<span>{{count}} item{{count | pluralize}}</span>  <!-- 5 items -->
```

## Template Includes

See [ibis template inheritance](https://www.dmulholl.com/docs/ibis/master/inheritance.html) for more on includes and extends.

Reuse template code with includes:

### Basic Include

```html
<!-- main.html -->
<div class="layout">
    {% include "shared/header.html" %}
    
    <main>
        <h1>{{page_title}}</h1>
        <div>{{content}}</div>
    </main>
    
    {% include "shared/footer.html" %}
</div>
```

### Include with Parameters

Pass specific data to included templates using `with`. Note that multiple parameters are separated by `&` (not commas):

```html
<!-- user_list.html -->
{% for user in users %}
    {% include "user_card.html" with user=user & show_admin=true %}
{% endfor %}

<!-- Alternative: include in navbar with avatar -->
{% include "shared/navbar.html" with avatar_url=current_user.avatar_url %}
```

**user_card.html:**
```html
<div class="user-card">
    <h3>{{user.name}}</h3>
    <p>{{user.email}}</p>
    {% if show_admin and user.is_admin %}
        <span class="admin-badge">Admin</span>
    {% endif %}
</div>
```

## Context Variables

Templates automatically have access to additional context:

### Built-in Context

```html
<!-- JavaScript commands (always available) -->
<button phx-click="toggle" data-js="{{js | js.toggle('#sidebar')}}">
    Toggle Sidebar
</button>

<!-- LiveView metadata -->
<div data-live-view="{{live_view_id}}">
    <!-- Template content -->
</div>
```

### Custom Context Processors

Add global template variables:

```python
# In your application setup
from pyview.template.context_processor import context_processor

@context_processor
def add_app_context(meta):
    return {
        "app_name": "My PyView App",
        "version": "1.0.0",
        "current_year": datetime.now().year
    }
```

Use in templates:

```html
<footer>
    <p>&copy; {{current_year}} {{app_name}} v{{version}}</p>
</footer>
```
