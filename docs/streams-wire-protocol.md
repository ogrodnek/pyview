# Phoenix LiveView Streams Wire Protocol

This document describes the wire protocol for Phoenix LiveView streams, based on analysis of the Phoenix LiveView source code. This is intended to guide the implementation of streams in pyview.

## Overview

Streams are a Phoenix LiveView feature that allows efficient rendering of large collections without keeping all items in server memory. The key characteristics are:

1. **Server doesn't keep stream items in memory** - only stream operations (inserts/deletes) are tracked
2. **Only changed items are sent over the wire** - inserting one item sends only that item
3. **Client-side DOM management** - the JavaScript client tracks stream items in the DOM

## Wire Protocol Format

### Diff Structure with Streams

Streams are embedded within comprehension (loop) structures in the diff. The `"stream"` key appears alongside the `"s"` (statics) and `"d"` (dynamics) keys for a comprehension:

```json
{
  "s": ["<div id=\"users\" phx-update=\"stream\">", "</div>"],
  "0": {
    "s": ["<div id=\"", "\">", "</div>"],
    "d": [
      ["users-1", "Alice"],
      ["users-2", "Bob"]
    ],
    "stream": ["users", [["users-1", -1, null, false], ["users-2", -1, null, false]], []]
  }
}
```

### Stream Data Array Format

The `"stream"` key contains an array with 3-4 elements:

```
[ref, inserts, deletes, reset?]
```

| Index | Name | Type | Description |
|-------|------|------|-------------|
| 0 | `ref` | string | Stream reference/name identifier (e.g., "users", "messages") |
| 1 | `inserts` | array | Array of insert operations |
| 2 | `deletes` | array | Array of DOM IDs to delete |
| 3 | `reset` | boolean (optional) | When `true`, clears all existing stream items before applying inserts |

### Insert Operation Format

Each insert in the `inserts` array is a 4-element array:

```
[dom_id, at, limit, update_only]
```

| Index | Name | Type | Description |
|-------|------|------|-------------|
| 0 | `dom_id` | string | The DOM element ID (e.g., "users-123") |
| 1 | `at` | integer | Position: `-1` = append, `0` = prepend, `N` = specific index |
| 2 | `limit` | integer \| null | Max items constraint: positive = ceiling, negative = floor |
| 3 | `update_only` | boolean | When `true`, only updates existing items (doesn't add new) |

## Operation Examples

### 1. Initial Render with Multiple Items

When a stream is first rendered with items:

```json
{
  "0": {
    "s": ["<div id=\"", "\" class=\"user\">", "</div>"],
    "d": [
      ["users-1", "Alice"],
      ["users-2", "Bob"],
      ["users-3", "Charlie"]
    ],
    "stream": [
      "users",
      [
        ["users-1", -1, null, false],
        ["users-2", -1, null, false],
        ["users-3", -1, null, false]
      ],
      []
    ]
  }
}
```

### 2. Append Item (at: -1)

Adding a new item to the end of the stream:

```elixir
# Server-side (Phoenix)
socket |> stream_insert(:users, %{id: 4, name: "Diana"})
```

Wire format:
```json
{
  "0": {
    "d": [["users-4", "Diana"]],
    "stream": ["users", [["users-4", -1, null, false]], []]
  }
}
```

### 3. Prepend Item (at: 0)

Adding a new item to the beginning of the stream:

```elixir
# Server-side (Phoenix)
socket |> stream_insert(:users, %{id: 5, name: "Eve"}, at: 0)
```

Wire format:
```json
{
  "0": {
    "d": [["users-5", "Eve"]],
    "stream": ["users", [["users-5", 0, null, false]], []]
  }
}
```

### 4. Insert at Specific Position (at: N)

Adding a new item at a specific index:

```elixir
# Server-side (Phoenix)
socket |> stream_insert(:users, %{id: 6, name: "Frank"}, at: 2)
```

Wire format:
```json
{
  "0": {
    "d": [["users-6", "Frank"]],
    "stream": ["users", [["users-6", 2, null, false]], []]
  }
}
```

### 5. Delete Item

Removing an item from the stream:

```elixir
# Server-side (Phoenix)
socket |> stream_delete(:users, user)
# or
socket |> stream_delete_by_dom_id(:users, "users-2")
```

Wire format (no dynamic data needed for deletes):
```json
{
  "0": {
    "stream": ["users", [], ["users-2"]]
  }
}
```

### 6. Update Existing Item

Updating an item's content without changing its position:

```elixir
# Server-side (Phoenix)
socket |> stream_insert(:users, %{id: 1, name: "Alice Updated"})
```

Wire format:
```json
{
  "0": {
    "d": [["users-1", "Alice Updated"]],
    "stream": ["users", [["users-1", -1, null, false]], []]
  }
}
```

Note: When updating, the item stays in its current DOM position even though `at: -1` is sent. The JavaScript client recognizes the item already exists and updates in place.

### 7. Update Only Mode

Only update items that already exist (ignore if not present):

```elixir
# Server-side (Phoenix)
socket |> stream_insert(:users, user, update_only: true)
```

Wire format:
```json
{
  "0": {
    "d": [["users-1", "Updated Name"]],
    "stream": ["users", [["users-1", -1, null, true]], []]
  }
}
```

### 8. Reset Stream

Clear all existing items and replace with new ones:

```elixir
# Server-side (Phoenix)
socket |> stream(:users, new_users, reset: true)
```

Wire format:
```json
{
  "0": {
    "s": ["<div id=\"", "\" class=\"user\">", "</div>"],
    "d": [
      ["users-10", "New User 1"],
      ["users-11", "New User 2"]
    ],
    "stream": [
      "users",
      [
        ["users-10", -1, null, false],
        ["users-11", -1, null, false]
      ],
      [],
      true
    ]
  }
}
```

Note the 4th element `true` indicating reset.

### 9. With Limit (Positive - Keep First N)

Limit the stream to keep only the first N items when appending:

```elixir
# Server-side (Phoenix)
socket |> stream(:messages, messages, at: -1, limit: 100)
```

Wire format:
```json
{
  "0": {
    "d": [["msg-500", "New message"]],
    "stream": ["messages", [["msg-500", -1, 100, false]], []]
  }
}
```

When inserting at the end with a positive limit, items are removed from the beginning if limit is exceeded.

### 10. With Limit (Negative - Keep Last N)

Limit the stream to keep only the last N items when prepending:

```elixir
# Server-side (Phoenix)
socket |> stream(:messages, messages, at: 0, limit: -100)
```

Wire format:
```json
{
  "0": {
    "d": [["msg-1", "Older message"]],
    "stream": ["messages", [["msg-1", 0, -100, false]], []]
  }
}
```

When inserting at the beginning with a negative limit, items are removed from the end if limit is exceeded.

### 11. Move Item (Delete + Insert)

To move an item to a different position:

```elixir
# Server-side (Phoenix)
socket
|> stream_delete(:users, user)
|> stream_insert(:users, user, at: 0)
```

Wire format:
```json
{
  "0": {
    "d": [["users-3", "Charlie"]],
    "stream": ["users", [["users-3", 0, null, false]], ["users-3"]]
  }
}
```

### 12. Bulk Operations

Multiple inserts and deletes in one update:

```json
{
  "0": {
    "d": [
      ["users-10", "New User 1"],
      ["users-11", "New User 2"]
    ],
    "stream": [
      "users",
      [
        ["users-10", -1, null, false],
        ["users-11", -1, null, false]
      ],
      ["users-1", "users-2"]
    ]
  }
}
```

## HTML Template Requirements

### Container Element

The stream container must have:
1. A unique `id` attribute
2. `phx-update="stream"` attribute

```html
<div id="users" phx-update="stream">
  <!-- stream items rendered here -->
</div>
```

### Item Elements

Each stream item must have:
1. A unique `id` attribute matching the DOM ID from the stream

```html
<div :for={{dom_id, user} <- @streams.users} id={dom_id}>
  <%= user.name %>
</div>
```

### DOM ID Generation

Phoenix generates DOM IDs using the `:dom_id` option or a default function:

```elixir
# Default: uses the item's :id field
stream(socket, :users, users)  # => "users-1", "users-2", etc.

# Custom dom_id function
stream(socket, :users, users, dom_id: &"user-#{&1.uuid}")
```

## Client-Side Processing

The JavaScript client processes streams in `dom_patch.js`:

1. **Parse stream data**: Extract `[ref, inserts, deleteIds, reset]`
2. **Handle reset**: If reset is true, remove all existing stream children with matching `data-phx-stream` ref
3. **Process deletes**: Remove elements matching IDs in `deleteIds`
4. **Process inserts**: For each insert `[key, streamAt, limit, updateOnly]`:
   - Mark element with `data-phx-stream` attribute
   - Position based on `streamAt`:
     - `0`: Insert at beginning (`insertAdjacentElement('afterbegin')`)
     - `-1`: Insert at end (append)
     - `N`: Insert at specific index
   - Apply limit constraints if specified
   - Skip insert if `updateOnly` and element doesn't exist

## Key Differences from Regular Comprehensions

| Aspect | Regular Comprehension | Stream Comprehension |
|--------|----------------------|---------------------|
| Server memory | All items kept | Only operations tracked |
| Wire format | Full `"d"` array | Only changed items in `"d"` + `"stream"` metadata |
| DOM updates | Replace entire list | Targeted insert/delete/update |
| `phx-update` | Not required | Required: `phx-update="stream"` |
| Item IDs | Optional | Required on each item |

## Implementation Notes for pyview

### Server-Side Requirements

1. **Stream struct**: Track pending inserts and deletes
2. **stream()** function: Initialize stream with items
3. **stream_insert()** function: Add/update items with position control
4. **stream_delete()** function: Remove items by value or DOM ID
5. **Template integration**: Support `@streams.name` access pattern
6. **Diff generation**: Include `"stream"` key in comprehension diffs

### Data Structures

```python
@dataclass
class StreamInsert:
    dom_id: str
    at: int  # -1 for append, 0 for prepend, N for index
    limit: Optional[int]
    update_only: bool

@dataclass
class LiveStream:
    ref: str  # stream name
    inserts: list[StreamInsert]
    deletes: list[str]  # DOM IDs to delete
    reset: bool = False
```

### Rendering Flow

1. In `mount()`: Initialize stream with `stream(socket, :name, items)`
2. Track insert/delete operations on the socket
3. During render: Generate stream metadata alongside comprehension
4. In diff: Include `"stream"` key when stream operations exist
5. After render: Clear pending operations

## References

- [Phoenix LiveView Source - live_stream.ex](https://github.com/phoenixframework/phoenix_live_view/blob/main/lib/phoenix_live_view/live_stream.ex)
- [Phoenix LiveView Source - diff.ex](https://github.com/phoenixframework/phoenix_live_view/blob/main/lib/phoenix_live_view/diff.ex)
- [Phoenix LiveView Source - dom_patch.js](https://github.com/phoenixframework/phoenix_live_view/blob/main/assets/js/phoenix_live_view/dom_patch.js)
- [Phoenix LiveView Source - rendered.js](https://github.com/phoenixframework/phoenix_live_view/blob/main/assets/js/phoenix_live_view/rendered.js)
- [Phoenix Dev Blog - Streams](https://fly.io/phoenix-files/phoenix-dev-blog-streams/)
- [Phoenix LiveView Streams Documentation](https://hexdocs.pm/phoenix_live_view/Phoenix.LiveView.html#module-streams)
