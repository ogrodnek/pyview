defmodule StreamTestWeb.StreamLive do
  @moduledoc """
  Test LiveView for demonstrating and capturing stream wire protocol.

  This LiveView provides buttons to trigger all stream operations:
  - Append items (at: -1)
  - Prepend items (at: 0)
  - Insert at specific position (at: N)
  - Delete items
  - Update items
  - Reset stream
  - Operations with limits

  Use browser DevTools to capture the WebSocket messages.
  """
  use StreamTestWeb, :live_view

  @impl true
  def mount(_params, _session, socket) do
    items = [
      %{id: 1, name: "Item 1"},
      %{id: 2, name: "Item 2"},
      %{id: 3, name: "Item 3"}
    ]

    socket =
      socket
      |> assign(:counter, 3)
      |> stream(:items, items)

    {:ok, socket}
  end

  @impl true
  def render(assigns) do
    ~H"""
    <div class="container mx-auto p-4">
      <h1 class="text-2xl font-bold mb-4">Stream Wire Protocol Test</h1>

      <div class="mb-4 space-x-2">
        <button phx-click="append" class="bg-blue-500 text-white px-4 py-2 rounded">
          Append Item
        </button>
        <button phx-click="prepend" class="bg-green-500 text-white px-4 py-2 rounded">
          Prepend Item
        </button>
        <button phx-click="insert_middle" class="bg-yellow-500 text-white px-4 py-2 rounded">
          Insert at Index 1
        </button>
        <button phx-click="delete_first" class="bg-red-500 text-white px-4 py-2 rounded">
          Delete First
        </button>
        <button phx-click="delete_last" class="bg-red-500 text-white px-4 py-2 rounded">
          Delete Last
        </button>
        <button phx-click="update_first" class="bg-purple-500 text-white px-4 py-2 rounded">
          Update First
        </button>
        <button phx-click="reset" class="bg-gray-500 text-white px-4 py-2 rounded">
          Reset Stream
        </button>
        <button phx-click="move_last_to_first" class="bg-indigo-500 text-white px-4 py-2 rounded">
          Move Last to First
        </button>
      </div>

      <div class="mb-4 space-x-2">
        <button phx-click="append_with_limit" class="bg-teal-500 text-white px-4 py-2 rounded">
          Append (limit: 5)
        </button>
        <button phx-click="prepend_with_limit" class="bg-cyan-500 text-white px-4 py-2 rounded">
          Prepend (limit: -5)
        </button>
        <button phx-click="bulk_insert" class="bg-orange-500 text-white px-4 py-2 rounded">
          Bulk Insert (3 items)
        </button>
      </div>

      <div id="items" phx-update="stream" class="border rounded p-4 bg-gray-50">
        <div
          :for={{dom_id, item} <- @streams.items}
          id={dom_id}
          class="p-2 mb-2 bg-white rounded shadow"
        >
          <span class="font-mono text-sm text-gray-500"><%= dom_id %>:</span>
          <span class="ml-2"><%= item.name %></span>
        </div>
      </div>

      <div class="mt-4 text-sm text-gray-600">
        <p>Open browser DevTools → Network → WS to see wire format</p>
        <p>Counter: <%= @counter %></p>
      </div>
    </div>
    """
  end

  @impl true
  def handle_event("append", _params, socket) do
    counter = socket.assigns.counter + 1
    item = %{id: counter, name: "Item #{counter} (appended)"}

    socket =
      socket
      |> assign(:counter, counter)
      |> stream_insert(:items, item, at: -1)

    {:noreply, socket}
  end

  def handle_event("prepend", _params, socket) do
    counter = socket.assigns.counter + 1
    item = %{id: counter, name: "Item #{counter} (prepended)"}

    socket =
      socket
      |> assign(:counter, counter)
      |> stream_insert(:items, item, at: 0)

    {:noreply, socket}
  end

  def handle_event("insert_middle", _params, socket) do
    counter = socket.assigns.counter + 1
    item = %{id: counter, name: "Item #{counter} (at index 1)"}

    socket =
      socket
      |> assign(:counter, counter)
      |> stream_insert(:items, item, at: 1)

    {:noreply, socket}
  end

  def handle_event("delete_first", _params, socket) do
    # Delete by DOM ID (first item)
    {:noreply, stream_delete_by_dom_id(socket, :items, "items-1")}
  end

  def handle_event("delete_last", _params, socket) do
    # We need to track which items exist to delete the last one
    # For demo, we'll delete by counter
    counter = socket.assigns.counter
    {:noreply, stream_delete_by_dom_id(socket, :items, "items-#{counter}")}
  end

  def handle_event("update_first", _params, socket) do
    # Update item 1 (stays in same position)
    item = %{id: 1, name: "Item 1 (UPDATED at #{DateTime.utc_now()})"}
    {:noreply, stream_insert(socket, :items, item)}
  end

  def handle_event("reset", _params, socket) do
    new_items = [
      %{id: 100, name: "Reset Item A"},
      %{id: 101, name: "Reset Item B"},
      %{id: 102, name: "Reset Item C"}
    ]

    socket =
      socket
      |> assign(:counter, 102)
      |> stream(:items, new_items, reset: true)

    {:noreply, socket}
  end

  def handle_event("move_last_to_first", _params, socket) do
    counter = socket.assigns.counter
    item = %{id: counter, name: "Item #{counter} (moved to first)"}

    socket =
      socket
      |> stream_delete_by_dom_id(:items, "items-#{counter}")
      |> stream_insert(:items, item, at: 0)

    {:noreply, socket}
  end

  def handle_event("append_with_limit", _params, socket) do
    counter = socket.assigns.counter + 1
    item = %{id: counter, name: "Item #{counter} (limited)"}

    socket =
      socket
      |> assign(:counter, counter)
      |> stream_insert(:items, item, at: -1, limit: 5)

    {:noreply, socket}
  end

  def handle_event("prepend_with_limit", _params, socket) do
    counter = socket.assigns.counter + 1
    item = %{id: counter, name: "Item #{counter} (limited)"}

    socket =
      socket
      |> assign(:counter, counter)
      |> stream_insert(:items, item, at: 0, limit: -5)

    {:noreply, socket}
  end

  def handle_event("bulk_insert", _params, socket) do
    counter = socket.assigns.counter
    items = [
      %{id: counter + 1, name: "Bulk Item #{counter + 1}"},
      %{id: counter + 2, name: "Bulk Item #{counter + 2}"},
      %{id: counter + 3, name: "Bulk Item #{counter + 3}"}
    ]

    socket =
      socket
      |> assign(:counter, counter + 3)
      |> stream(:items, items, at: -1)

    {:noreply, socket}
  end
end
