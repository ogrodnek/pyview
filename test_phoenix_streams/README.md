# Phoenix Streams Test App

This directory contains files to create a minimal Phoenix LiveView app for testing the streams wire protocol.

## Prerequisites

- Elixir 1.14+ with Phoenix 1.7+
- OR Docker

## Quick Setup with Docker

```bash
# Create and run a Phoenix container
docker run -it --rm -p 4000:4000 -v $(pwd):/app -w /app elixir:1.16 bash

# Inside the container:
mix local.hex --force
mix local.rebar --force
mix archive.install hex phx_new --force

# Create new Phoenix project
mix phx.new stream_test --no-ecto --no-mailer --no-dashboard --no-gettext

cd stream_test
mix deps.get

# Copy our test LiveView
cp /app/stream_live.ex lib/stream_test_web/live/
# Add route (see below)

mix phx.server
```

## Manual Setup

1. Create a new Phoenix project:
   ```bash
   mix phx.new stream_test --no-ecto --no-mailer
   cd stream_test
   ```

2. Copy `stream_live.ex` to `lib/stream_test_web/live/stream_live.ex`

3. Add route to `lib/stream_test_web/router.ex`:
   ```elixir
   scope "/", StreamTestWeb do
     pipe_through :browser
     live "/streams", StreamLive
   end
   ```

4. Run the server:
   ```bash
   mix phx.server
   ```

5. Open browser dev tools (Network tab, filter by WS), go to http://localhost:4000/streams

## Capturing Wire Format

1. Open browser DevTools
2. Go to Network tab
3. Filter by "WS" (WebSocket)
4. Navigate to http://localhost:4000/streams
5. Click on the WebSocket connection
6. Go to "Messages" tab
7. Interact with the buttons to see stream operations

## Expected Wire Format Examples

The console will also log the payloads. Look for messages like:

### Initial Join Response
```json
["4","4","lv:phx-xxx","phx_reply",{
  "response": {
    "rendered": {
      "0": {
        "s": ["<li id=\"", "\">", "</li>"],
        "d": [["items-1", "Item 1"], ["items-2", "Item 2"]],
        "stream": ["items", [["items-1", -1, null, false], ["items-2", -1, null, false]], []]
      },
      "s": ["<div id=\"items\" phx-update=\"stream\">", "</div>..."]
    }
  },
  "status": "ok"
}]
```

### Append Item
```json
[null, null, "lv:phx-xxx", "diff", {
  "0": {
    "d": [["items-3", "Item 3"]],
    "stream": ["items", [["items-3", -1, null, false]], []]
  }
}]
```

### Prepend Item
```json
[null, null, "lv:phx-xxx", "diff", {
  "0": {
    "d": [["items-4", "Item 4"]],
    "stream": ["items", [["items-4", 0, null, false]], []]
  }
}]
```

### Delete Item
```json
[null, null, "lv:phx-xxx", "diff", {
  "0": {
    "stream": ["items", [], ["items-1"]]
  }
}]
```

### Reset Stream
```json
[null, null, "lv:phx-xxx", "diff", {
  "0": {
    "d": [["items-10", "Reset 1"], ["items-11", "Reset 2"]],
    "stream": ["items", [["items-10", -1, null, false], ["items-11", -1, null, false]], [], true]
  }
}]
```
