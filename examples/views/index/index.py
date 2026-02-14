from dataclasses import dataclass
from typing import Optional

from pyview import ConnectedLiveViewSocket, LiveView, LiveViewSocket
from pyview.events import AutoEventDispatch, event

from ...example_registry import get_all_examples
from ...format_examples import ExampleEntry

TAG_META: dict[str, tuple[str, str]] = {
    "basics": ("Getting Started", "bg-emerald-50 text-emerald-700 border-emerald-200"),
    "forms": ("Forms", "bg-blue-50 text-blue-700 border-blue-200"),
    "realtime": ("Realtime", "bg-amber-50 text-amber-700 border-amber-200"),
    "components": ("Components", "bg-violet-50 text-violet-700 border-violet-200"),
    "integrations": ("JS & Integrations", "bg-cyan-50 text-cyan-700 border-cyan-200"),
    "advanced": ("Advanced", "bg-pyview-pink-50 text-pyview-pink-700 border-pyview-pink-200"),
}

TAG_ORDER = ["basics", "forms", "realtime", "components", "integrations", "advanced"]


@dataclass
class TagInfo:
    label: str
    classes: str


@dataclass
class ExampleCard:
    url_path: str
    title: str
    text: str
    src_link: str
    tags: list[TagInfo]
    tag_keys: list[str]


@dataclass
class FilterPill:
    key: str
    label: str
    count: int
    is_active: bool


@dataclass
class IndexContext:
    all_cards: list[ExampleCard]
    filtered: list[ExampleCard]
    tag_filters: list[FilterPill]
    result_count: int

    search: str = ""
    active_tag: str = "all"


def _build_cards(examples: list[ExampleEntry]) -> list[ExampleCard]:
    result = []
    for ex in examples:
        tag_infos = []
        for tag in ex.tags:
            label, classes = TAG_META.get(tag, (tag, "bg-gray-50 text-gray-700 border-gray-200"))
            tag_infos.append(TagInfo(label=label, classes=classes))
        src_link = f"https://github.com/ogrodnek/pyview/tree/main/{ex.src_path}"
        result.append(
            ExampleCard(
                url_path=ex.url_path,
                title=ex.title,
                text=ex.text,
                src_link=src_link,
                tags=tag_infos,
                tag_keys=ex.tags,
            )
        )
    return result


def _build_filters(search_filtered: list[ExampleCard], active_tag: str) -> list[FilterPill]:
    """Build filter pills with counts based on search-filtered cards (tag filter not applied)."""
    counts: dict[str, int] = {}
    for card in search_filtered:
        for tag in card.tag_keys:
            counts[tag] = counts.get(tag, 0) + 1

    pills = [
        FilterPill(
            key="all", label="All", count=len(search_filtered), is_active=active_tag == "all"
        ),
    ]
    for key in TAG_ORDER:
        if key in counts:
            label, _ = TAG_META[key]
            pills.append(
                FilterPill(
                    key=key,
                    label=label,
                    count=counts[key],
                    is_active=active_tag == key,
                )
            )
    return pills


def _filter_cards(cards: list[ExampleCard], active_tag: str, search: str) -> list[ExampleCard]:
    filtered = cards
    if active_tag != "all":
        filtered = [c for c in filtered if active_tag in c.tag_keys]
    if search:
        q = search.lower().strip()
        filtered = [
            c
            for c in filtered
            if q in c.title.lower()
            or q in c.text.lower()
            or any(q in t.label.lower() for t in c.tags)
        ]
    return filtered


class IndexLiveView(AutoEventDispatch, LiveView[IndexContext]):
    """PyView Examples Index"""

    async def mount(self, socket: LiveViewSocket[IndexContext], session):
        socket.live_title = "PyView Live Demos"
        all_cards = _build_cards(get_all_examples())
        socket.context = IndexContext(
            all_cards=all_cards,
            filtered=all_cards,
            tag_filters=_build_filters(all_cards, "all"),
            result_count=len(all_cards),
        )

    @event("search")
    async def handle_search(self, socket: ConnectedLiveViewSocket[IndexContext], q: str = ""):
        socket.context.search = q
        await self._push_url(socket)

    @event("clear_search")
    async def handle_clear_search(self, socket: ConnectedLiveViewSocket[IndexContext]):
        socket.context.search = ""
        await self._push_url(socket)

    @event("filter_tag")
    async def handle_filter_tag(
        self, socket: ConnectedLiveViewSocket[IndexContext], tag: str = "all"
    ):
        socket.context.active_tag = tag
        await self._push_url(socket)

    @event("clear_filters")
    async def handle_clear_filters(self, socket: ConnectedLiveViewSocket[IndexContext]):
        socket.context.search = ""
        socket.context.active_tag = "all"
        await self._push_url(socket)

    async def handle_params(
        self,
        socket: LiveViewSocket[IndexContext],
        tag: Optional[str] = None,
        q: Optional[str] = None,
    ):
        if tag is not None:
            socket.context.active_tag = tag
        if q is not None:
            socket.context.search = q
        self._apply_filters(socket)

    async def _push_url(self, socket: ConnectedLiveViewSocket[IndexContext]):
        ctx = socket.context
        params: dict[str, str] = {}
        if ctx.active_tag != "all":
            params["tag"] = ctx.active_tag
        if ctx.search:
            params["q"] = ctx.search
        await socket.push_patch("/", params)

    def _apply_filters(self, socket: LiveViewSocket[IndexContext]):
        ctx = socket.context
        # Filter by search only (for tag counts), then apply tag filter for final results
        search_only = _filter_cards(ctx.all_cards, "all", ctx.search)
        ctx.filtered = _filter_cards(ctx.all_cards, ctx.active_tag, ctx.search)
        ctx.result_count = len(ctx.filtered)
        ctx.tag_filters = _build_filters(search_only, ctx.active_tag)
