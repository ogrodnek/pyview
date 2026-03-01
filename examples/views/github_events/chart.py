import datetime
from collections import defaultdict

import altair as alt


EVENT_TYPES = {
    "PushEvent": "#6366f1",
    "PullRequestEvent": "#f59e0b",
    "IssuesEvent": "#ef4444",
    "WatchEvent": "#10b981",
    "ForkEvent": "#8b5cf6",
    "CreateEvent": "#06b6d4",
}

EVENT_LABELS = {
    "PushEvent": "Push",
    "PullRequestEvent": "Pull Request",
    "IssuesEvent": "Issues",
    "WatchEvent": "Stars",
    "ForkEvent": "Forks",
    "CreateEvent": "Create",
}


def aggregate_events(raw_events: list[dict]) -> list[dict]:
    """Aggregate raw GitHub events into per-minute buckets by event type."""
    counts: dict[tuple[str, str], int] = defaultdict(int)

    for ev in raw_events:
        event_type = ev.get("type", "")
        if event_type not in EVENT_TYPES:
            continue
        created_at = ev.get("created_at", "")
        if not created_at:
            continue
        try:
            dt = datetime.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            minute_key = dt.strftime("%Y-%m-%dT%H:%M:00")
        except (ValueError, AttributeError):
            continue
        counts[(minute_key, event_type)] += 1

    return [
        {"time": time, "count": count, "event_type": event_type}
        for (time, event_type), count in sorted(counts.items())
    ]


def get_hover_detail(
    all_data: list[dict],
    hovered_time: str,
    active_types: set[str] | None = None,
) -> list[dict]:
    """Get event counts for a specific time bucket, sorted by count descending."""
    matches = [d for d in all_data if d["time"] == hovered_time]
    if active_types is not None:
        matches = [d for d in matches if d["event_type"] in active_types]
    return sorted(matches, key=lambda d: d["count"], reverse=True)


def build_vega_spec(
    data: list[dict],
    active_types: set[str] | None = None,
) -> dict:
    """Build a Vega-Lite stacked area chart spec using Altair."""
    if active_types is not None:
        data = [d for d in data if d["event_type"] in active_types]

    # Area chart needs at least 2 time points - pad with an adjacent minute if needed
    times = {d["time"] for d in data}
    if len(times) == 1:
        only_time = next(iter(times))
        prev_time = (
            datetime.datetime.fromisoformat(only_time) - datetime.timedelta(minutes=1)
        ).strftime("%Y-%m-%dT%H:%M:00")
        types_present = {d["event_type"] for d in data}
        data = data + [{"time": prev_time, "count": 0, "event_type": et} for et in types_present]

    chart = (
        alt.Chart({"values": data})
        .mark_area(opacity=0.7, interpolate="monotone")
        .encode(
            alt.X("time:T").axis(title=None, format="%H:%M", labelAngle=0),
            alt.Y("count:Q").stack("zero").axis(title="Events per minute"),
            alt.Color("event_type:N")
            .scale(domain=list(EVENT_TYPES.keys()), range=list(EVENT_TYPES.values()))
            .legend(None),
            tooltip=[
                alt.Tooltip("event_type:N", title="Event"),
                alt.Tooltip("count:Q", title="Count"),
                alt.Tooltip("time:T", title="Time", format="%H:%M"),
            ],
        )
        .properties(width="container", height=350, padding=5)
    )

    return chart.to_dict()
