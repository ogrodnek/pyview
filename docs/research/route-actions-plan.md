# Route Actions for PyView

## Problem Statement

In PyView, when you register the same LiveView class to multiple routes with different path patterns, navigating between them creates new LiveView instances. This is problematic for scenarios like a music app where you want the same view to handle:

- `/artist/{id}`
- `/album/{id}`
- `/genre/{name}`
- `/search?q=...`

Phoenix LiveView solves this with "actions" - an optional identifier that groups routes together:

```elixir
live "/articles", ArticleLive.Index, :index
live "/articles/new", ArticleLive.Index, :new
live "/articles/:id/edit", ArticleLive.Index, :edit
```

When navigating via `push_patch` between routes sharing the same LiveView and action group, Phoenix reuses the instance and only calls `handle_params`.

## Proposed Solution

Add optional `action` parameter to route registration. Routes sharing the same LiveView class **and** having actions specified will share instances when navigating via `push_patch`. Action is passed as a parameter to `handle_params`.

### API Design

**Registration:**
```python
# Grouped routes (share instances)
app.add_live_view("/articles", ArticleLiveView, action="index")
app.add_live_view("/articles/new", ArticleLiveView, action="new")
app.add_live_view("/articles/{id:int}/edit", ArticleLiveView, action="edit")

# Independent routes (no action = current behavior, no instance sharing)
app.add_live_view("/other", OtherView)
```

**Usage in LiveView:**
```python
class ArticleLiveView(LiveView):
    async def handle_params(self, socket, action: str, id: int = None):
        match action:
            case "index":
                socket.assign(articles=await load_articles())
            case "new":
                socket.assign(article=Article())
            case "edit":
                socket.assign(article=await load_article(id))
```

### Key Design Decisions

1. **Backward compatible**: Routes without actions work exactly as before (no instance sharing across different paths)

2. **Opt-in grouping**: Adding `action` parameter explicitly opts routes into instance sharing

3. **Action as method parameter**: More Pythonic than storing on socket. If needed elsewhere (templates, handle_event), user can `socket.assign(action=action)`

4. **Same class required**: Only routes pointing to the same LiveView class can share instances

## Implementation Plan

### Files to Modify

#### 1. `pyview/live_routes.py` - LiveViewLookup

**Current storage:** `(path_format, path_regex, param_convertors, lv_factory)`

**New storage:** `(path_format, path_regex, param_convertors, lv_factory, action)`

```python
def add(self, path: str, lv: type[LiveView], action: str | None = None):
    # ... existing compilation ...
    self.routes.append((path_format, path_regex, param_convertors, lv, action))

    # Track action groups for same-class detection
    if action is not None:
        self._action_groups[lv].add(path_format)

def get(self, path: str) -> tuple[LiveView, dict[str, Any], str | None]:
    # ... existing matching ...
    return lv_instance, path_params, action
```

#### 2. `pyview/pyview.py` - add_live_view

```python
def add_live_view(self, path: str, view: type[LiveView], action: str | None = None):
    # ...
    self.view_lookup.add(path, view, action)
    # ...
```

#### 3. `pyview/binding/injectables.py` - Add action injectable

```python
INJECTABLES = {
    "socket": lambda ctx: ctx.socket,
    "event": lambda ctx: ctx.event,
    "url": lambda ctx: ctx.url,
    "params": _get_params,
    "payload": lambda ctx: ctx.payload,
    "action": lambda ctx: ctx.action,  # NEW
}
```

#### 4. `pyview/binding/helpers.py` - call_handle_params

```python
async def call_handle_params(
    lv, url: ParseResult, params: dict[str, list[str]], socket: LiveViewSocket, action: str | None = None
):
    ctx = BindContext(
        url=url,
        params=Params(params),
        socket=socket,
        action=action,  # NEW
    )
    # ... Binder will inject action if in signature
```

#### 5. `pyview/live_socket.py` - push_patch

```python
async def push_patch(self, path: str, params: Optional[dict[str, Any]] = None):
    # ... existing code ...

    # Get route info for target path (now includes action)
    if self.routes:
        with suppress(ValueError):
            _, path_params, action = self.routes.get(parsed_url.path)

    merged_params = {**params_for_handler, **path_params}

    # Call handle_params with action
    await call_handle_params(self.liveview, parsed_url, merged_params, self, action)
```

#### 6. `pyview/ws_handler.py` - live_patch event

```python
async def _handle_live_patch(self, socket, payload):
    url = urlparse(payload["url"])

    # Get target route info
    target_lv_class, path_params, action = self.routes.get(url.path)
    current_lv_class = type(socket.liveview)

    if target_lv_class == current_lv_class:
        # Same class - reuse instance, call handle_params with action
        # ...
    else:
        # Different class - warn or trigger full navigation
        # ...
```

#### 7. BindContext - Add action field

```python
@dataclass
class BindContext:
    url: ParseResult | None = None
    params: Params | None = None
    socket: LiveViewSocket | None = None
    event: str | None = None
    payload: dict | None = None
    action: str | None = None  # NEW
```

## Behavior Matrix

| Scenario | Behavior |
|----------|----------|
| Same class, both have actions, `push_patch` | Reuse instance, call `handle_params` with new action |
| Same class, no actions, `push_patch` | Current behavior (reuse if same path pattern only) |
| Different classes, `push_patch` | Should not happen / warn / fallback to navigate |
| `push_navigate` | Always creates new instance regardless of actions |

## Tests to Add

1. Register same class with multiple actions → verify instance reuse on push_patch
2. Register same class without actions → verify independent behavior
3. Action parameter binding in handle_params
4. Mixed scenario (some routes with actions, some without)
5. push_navigate always creates new instance regardless of actions
6. Action is `None` when route has no action defined

## References

- [Phoenix LiveView Router](https://hexdocs.pm/phoenix_live_view/Phoenix.LiveView.Router.html)
- [Phoenix Live Navigation](https://hexdocs.pm/phoenix_live_view/live-navigation.html)
