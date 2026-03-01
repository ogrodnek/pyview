from .chart import aggregate_events, build_vega_spec, get_hover_detail


def test_aggregate_events_buckets_by_minute():
    raw_events = [
        {"type": "PushEvent", "created_at": "2026-02-15T12:00:15Z"},
        {"type": "PushEvent", "created_at": "2026-02-15T12:00:45Z"},
        {"type": "WatchEvent", "created_at": "2026-02-15T12:00:10Z"},
        {"type": "PushEvent", "created_at": "2026-02-15T12:01:30Z"},
    ]
    buckets = aggregate_events(raw_events)

    push_12_00 = [b for b in buckets if b["event_type"] == "PushEvent" and b["time"] == "2026-02-15T12:00:00"]
    assert len(push_12_00) == 1
    assert push_12_00[0]["count"] == 2

    push_12_01 = [b for b in buckets if b["event_type"] == "PushEvent" and b["time"] == "2026-02-15T12:01:00"]
    assert len(push_12_01) == 1
    assert push_12_01[0]["count"] == 1

    watch_12_00 = [b for b in buckets if b["event_type"] == "WatchEvent" and b["time"] == "2026-02-15T12:00:00"]
    assert len(watch_12_00) == 1
    assert watch_12_00[0]["count"] == 1


def test_aggregate_events_ignores_unknown_types():
    raw_events = [
        {"type": "UnknownEvent", "created_at": "2026-02-15T12:00:15Z"},
        {"type": "PushEvent", "created_at": "2026-02-15T12:00:15Z"},
    ]
    buckets = aggregate_events(raw_events)
    assert all(b["event_type"] != "UnknownEvent" for b in buckets)
    assert len(buckets) == 1


def test_build_vega_spec_produces_valid_spec():
    data = [
        {"time": "2026-02-15T12:00:00", "count": 5, "event_type": "PushEvent"},
        {"time": "2026-02-15T12:01:00", "count": 2, "event_type": "WatchEvent"},
    ]
    spec = build_vega_spec(data)
    assert spec["mark"]["type"] == "area"


def test_build_vega_spec_does_not_error_with_single_time_point():
    data = [
        {"time": "2026-02-15T12:05:00", "count": 10, "event_type": "PushEvent"},
    ]
    spec = build_vega_spec(data)
    assert spec["mark"]["type"] == "area"


def test_get_hover_detail_returns_sorted_matches():
    data = [
        {"time": "2026-02-15T12:00:00", "count": 2, "event_type": "WatchEvent"},
        {"time": "2026-02-15T12:00:00", "count": 5, "event_type": "PushEvent"},
        {"time": "2026-02-15T12:01:00", "count": 10, "event_type": "PushEvent"},
    ]
    detail = get_hover_detail(data, "2026-02-15T12:00:00")
    assert len(detail) == 2
    assert detail[0]["event_type"] == "PushEvent"
    assert detail[1]["event_type"] == "WatchEvent"


def test_get_hover_detail_returns_empty_for_missing_time():
    data = [
        {"time": "2026-02-15T12:00:00", "count": 5, "event_type": "PushEvent"},
    ]
    assert get_hover_detail(data, "2026-02-15T13:00:00") == []


def test_get_hover_detail_filters_by_active_types():
    data = [
        {"time": "2026-02-15T12:00:00", "count": 5, "event_type": "PushEvent"},
        {"time": "2026-02-15T12:00:00", "count": 3, "event_type": "WatchEvent"},
    ]
    detail = get_hover_detail(data, "2026-02-15T12:00:00", active_types={"PushEvent"})
    assert len(detail) == 1
    assert detail[0]["event_type"] == "PushEvent"
