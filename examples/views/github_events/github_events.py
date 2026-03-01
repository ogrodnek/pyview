import datetime
import json
from typing import TypedDict

from string.templatelib import Template

from pyview import LiveView, LiveViewSocket, is_connected
from pyview.events import AutoEventDispatch, InfoEvent, event, info
from pyview.meta import PyViewMeta
from pyview.template.template_view import TemplateView

from .chart import EVENT_LABELS, EVENT_TYPES, aggregate_events, build_vega_spec, get_hover_detail
from .github_api import fetch_events


class GitHubEventsContext(TypedDict):
    chart_spec_json: str
    all_data: list[dict]
    active_types: set[str]
    last_updated: str
    hovered_time: str
    hovered_detail: list[dict]


class GitHubEventsLiveView(AutoEventDispatch, TemplateView, LiveView[GitHubEventsContext]):
    """
    GitHub Event Stream

    A live-updating Vega-Lite chart showing public GitHub activity.
    Server polls the GitHub Events API every 30 seconds and displays
    a stacked area chart of events by type, with toggle filters.
    """

    async def mount(self, socket: LiveViewSocket[GitHubEventsContext], session):
        socket.context = GitHubEventsContext(
            chart_spec_json="{}",
            all_data=[],
            active_types=set(EVENT_TYPES.keys()),
            last_updated="",
            hovered_time="",
            hovered_detail=[],
        )

        await self._fetch_and_update(socket)

        if is_connected(socket):
            socket.schedule_info(InfoEvent("tick"), 30)

    @info("tick")
    async def handle_tick(self, event, socket: LiveViewSocket[GitHubEventsContext]):
        await self._fetch_and_update(socket)

    @event
    async def toggle_event_type(self, event, payload, socket: LiveViewSocket[GitHubEventsContext]):
        event_type = payload.get("type", "")
        ctx = socket.context
        active = ctx["active_types"]
        if event_type in active:
            if len(active) > 1:
                active.discard(event_type)
        else:
            active.add(event_type)
        ctx["chart_spec_json"] = json.dumps(
            build_vega_spec(ctx["all_data"], active_types=active)
        )

    @event("chart-hover")
    async def handle_chart_hover(self, event, payload, socket: LiveViewSocket[GitHubEventsContext]):
        time_str = payload.get("time", "")
        if not time_str:
            return
        ctx = socket.context
        ctx["hovered_time"] = time_str
        ctx["hovered_detail"] = get_hover_detail(ctx["all_data"], time_str, active_types=ctx["active_types"])

    @event("chart-hover-clear")
    async def handle_chart_hover_clear(self, event, payload, socket: LiveViewSocket[GitHubEventsContext]):
        ctx = socket.context
        ctx["hovered_time"] = ""
        ctx["hovered_detail"] = []

    async def _fetch_and_update(self, socket: LiveViewSocket[GitHubEventsContext]):
        raw_events = await fetch_events()
        new_data = aggregate_events(raw_events)

        ctx = socket.context
        existing = ctx["all_data"]
        all_data = existing + new_data

        # Deduplicate by (time, event_type) keeping max count
        seen: dict[tuple[str, str], dict] = {}
        for d in all_data:
            key = (d["time"], d["event_type"])
            if key in seen:
                seen[key]["count"] = max(seen[key]["count"], d["count"])
            else:
                seen[key] = d
        all_data = sorted(seen.values(), key=lambda d: d["time"])

        # Trim to 30-minute window
        if all_data:
            cutoff = datetime.datetime.fromisoformat(all_data[-1]["time"]) - datetime.timedelta(minutes=30)
            all_data = [d for d in all_data if datetime.datetime.fromisoformat(d["time"]) >= cutoff]

        ctx["all_data"] = all_data
        ctx["chart_spec_json"] = json.dumps(
            build_vega_spec(all_data, active_types=ctx["active_types"])
        )
        ctx["last_updated"] = datetime.datetime.now().strftime("%H:%M:%S")

    def template(self, assigns: GitHubEventsContext, meta: PyViewMeta) -> Template:
        spec_json = assigns["chart_spec_json"]
        active_types = assigns["active_types"]
        last_updated = assigns["last_updated"]
        hovered_time = assigns["hovered_time"]
        hovered_detail = assigns["hovered_detail"]

        def toggle_button(event_type: str, color: str, label: str) -> Template:
            is_active = event_type in active_types
            opacity = "opacity-100" if is_active else "opacity-30"
            return t"""<button phx-click="toggle_event_type" phx-value-type="{event_type}"
                class="px-3 py-1.5 rounded-full text-sm font-medium text-white transition-opacity {opacity}"
                style="background-color: {color}">
                {label}
            </button>"""

        buttons = [
            toggle_button(et, color, EVENT_LABELS[et])
            for et, color in EVENT_TYPES.items()
        ]

        def detail_row(d: dict) -> Template:
            color = EVENT_TYPES.get(d["event_type"], "#6b7280")
            label = EVENT_LABELS.get(d["event_type"], d["event_type"])
            count = d["count"]
            return t"""<div class="flex items-center justify-between py-1">
                <div class="flex items-center gap-2">
                    <span class="w-3 h-3 rounded-full inline-block" style="background-color: {color}"></span>
                    <span class="text-sm text-gray-700">{label}</span>
                </div>
                <span class="text-sm font-semibold text-gray-900">{count}</span>
            </div>"""

        def format_hover_time(time_str: str) -> str:
            try:
                dt = datetime.datetime.fromisoformat(time_str)
                return dt.strftime("%H:%M")
            except (ValueError, AttributeError):
                return time_str

        detail_rows = [detail_row(d) for d in hovered_detail] if hovered_detail else []
        display_time = format_hover_time(hovered_time) if hovered_time else ""

        hover_panel = t"""<div class="bg-gray-50 rounded-lg border border-gray-200 p-4 mb-4">
            <div class="text-sm font-medium text-gray-500 mb-2">Events at {display_time}</div>
            <div class="divide-y divide-gray-100">
                {detail_rows}
            </div>
        </div>""" if hovered_time else t"""<div></div>"""

        return t"""<div class="max-w-4xl mx-auto px-4">
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <div class="flex items-center justify-between mb-4">
            <h1 class="text-2xl font-bold text-gray-900">GitHub Event Stream</h1>
            <span class="text-sm text-gray-400">{("Last updated: " + last_updated) if last_updated else "Loading..."}</span>
        </div>

        <p class="text-sm text-gray-600 mb-4">
            Live public activity across all of GitHub, visualized as a stacked area chart using
            <a href="https://vega.github.io/vega-lite/" target="_blank" class="text-blue-600 hover:underline">Vega-Lite</a>.
            Data is sourced from the
            <a href="https://docs.github.com/en/rest/activity/events#list-public-events" target="_blank" class="text-blue-600 hover:underline">GitHub Events API</a>
            and refreshes every 30 seconds. Hover over the chart to see event details. Toggle event types below to filter.
        </p>

        <div id="github-chart" phx-hook="VegaChart" data-chart-spec="{spec_json}" class="w-full mb-4">
            <div class="chart-loading flex items-center justify-center h-[350px] text-gray-400">
                Loading chart...
            </div>
        </div>

        {hover_panel}

        <div class="flex flex-wrap gap-2 justify-center">
            {buttons}
        </div>
    </div>
</div>"""
