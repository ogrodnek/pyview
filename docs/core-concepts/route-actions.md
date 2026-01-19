---
title: Route Actions
sidebar:
  order: 5
---

# Route Actions

Route actions let you group multiple URL patterns under a single LiveView, keeping the same instance alive as users navigate between them. This is perfect for views that handle related content—like a music app where browsing artists, albums, and search results all share the same player state.

## The Problem

Normally, each route gets its own LiveView instance. Navigate from `/articles` to `/articles/123/edit`, and you get a fresh instance with `mount()` called again:

```python
app.add_live_view("/articles", ArticleLiveView)
app.add_live_view("/articles/{id:int}/edit", ArticleLiveView)
```

That works, but what if you've loaded expensive data or want to preserve UI state across those navigations?

## The Solution: Actions

Add an `action` parameter to group routes together:

```python
app.add_live_view("/articles", ArticleLiveView, action="index")
app.add_live_view("/articles/new", ArticleLiveView, action="new")
app.add_live_view("/articles/{id:int}/edit", ArticleLiveView, action="edit")
```

Now when you `push_patch` between these routes, PyView reuses the same LiveView instance. Only `handle_params` is called—not `mount`.

## Accessing the Action

The action is available as an injectable parameter in `handle_params`:

```python
class ArticleLiveView(LiveView[ArticleContext]):
    async def mount(self, socket: LiveViewSocket[ArticleContext], session):
        # Called once, even when navigating between actions
        socket.context = {
            "articles": await load_articles(),
            "article": None,
        }

    async def handle_params(self, socket: LiveViewSocket[ArticleContext], action: str, id: int = None):
        match action:
            case "index":
                socket.live_title = "All Articles"
            case "new":
                socket.context["article"] = Article()
                socket.live_title = "New Article"
            case "edit":
                socket.context["article"] = await load_article(id)
                socket.live_title = f"Edit Article {id}"
```

The `action` parameter is just a string—use `match`, `if/elif`, or whatever pattern suits your code.

## Navigation Between Actions

Use `push_patch` to navigate within an action group:

```python
async def handle_event(self, event, payload, socket):
    if event == "edit_article":
        article_id = payload["id"]
        await socket.push_patch(f"/articles/{article_id}/edit")

    elif event == "back_to_list":
        await socket.push_patch("/articles")
```

The LiveView instance stays alive, your loaded data persists, and only `handle_params` runs with the new action.

## Real-World Example: Media Browser

Here's a pattern for apps where users browse related content:

```python
# Route registration
app.add_live_view("/browse/artists", BrowseLiveView, action="artists")
app.add_live_view("/browse/artists/{id:int}", BrowseLiveView, action="artist")
app.add_live_view("/browse/albums/{id:int}", BrowseLiveView, action="album")
app.add_live_view("/browse/search", BrowseLiveView, action="search")

# The LiveView
class BrowseLiveView(LiveView[BrowseContext]):
    async def mount(self, socket, session):
        socket.context = {
            "player_state": PlayerState(),  # Persists across navigation
            "content": None,
        }

    async def handle_params(self, socket, action: str, id: int = None, q: str = None):
        match action:
            case "artists":
                socket.context["content"] = await load_artists()
            case "artist":
                socket.context["content"] = await load_artist(id)
            case "album":
                socket.context["content"] = await load_album(id)
            case "search":
                socket.context["content"] = await search(q) if q else []
```

The player keeps playing while users browse. No state lost, no extra API calls for shared data.

## When to Use Actions vs. Separate LiveViews

**Use actions when:**
- Views share significant state (loaded data, UI state, player, etc.)
- Navigation should feel instant without re-mounting
- The views are conceptually part of the same feature

**Use separate LiveViews when:**
- Views are genuinely independent
- You want clean separation of concerns
- State shouldn't persist between views

## Routes Without Actions

Routes registered without an `action` work exactly as before—backward compatible. Each navigation creates a new instance:

```python
# These are independent, no instance sharing
app.add_live_view("/settings", SettingsLiveView)
app.add_live_view("/profile", ProfileLiveView)
```

You can mix both patterns in the same app. Actions are opt-in.

## Action is None When Not Defined

If you request the `action` parameter on a route that wasn't registered with one, you'll get `None`:

```python
async def handle_params(self, socket, action: str = None, page: int = 1):
    if action is None:
        # Route wasn't registered with an action
        pass
```

## Related

- [Routing](routing.md) – Basic route registration and path parameters
- [Socket and Context - Navigation](socket-and-context.md#navigation) – `push_patch`, `push_navigate`, and other navigation methods
- [LiveView Lifecycle](liveview-lifecycle.md) – When `mount` vs `handle_params` is called
