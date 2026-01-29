from dataclasses import dataclass, field

from pyview import LiveView, LiveViewSocket
from pyview.events import BaseEventHandler, event

from .data import (
    WordPlacement,
    check_selection,
    generate_puzzle,
    get_cells_in_line,
)


@dataclass
class WordSearchContext:
    grid: list[list[str]] = field(default_factory=list)
    placements: list[WordPlacement] = field(default_factory=list)
    found_words: set[str] = field(default_factory=set)
    found_cells: set[tuple[int, int]] = field(default_factory=set)
    selection_start: tuple[int, int] | None = None
    hover_cells: list[tuple[int, int]] = field(default_factory=list)
    message: str = ""

    @property
    def words_to_find(self) -> list[str]:
        return sorted([p.word for p in self.placements])

    @property
    def all_found(self) -> bool:
        return len(self.found_words) == len(self.placements)

    def is_cell_found(self, row: int, col: int) -> bool:
        return (row, col) in self.found_cells

    def is_cell_selected(self, row: int, col: int) -> bool:
        if self.selection_start and self.selection_start == (row, col):
            return True
        return (row, col) in self.hover_cells

    def cell_class(self, row: int, col: int) -> str:
        classes = ["cell"]
        if self.is_cell_found(row, col):
            classes.append("found")
        if self.is_cell_selected(row, col):
            classes.append("selected")
        return " ".join(classes)


class WordSearchLiveView(BaseEventHandler, LiveView[WordSearchContext]):
    """
    Word Search

    A classic word search puzzle game. Click a starting letter,
    then click an ending letter to find hidden words.
    """

    async def mount(self, socket: LiveViewSocket[WordSearchContext], session):
        grid, placements = generate_puzzle(rows=12, cols=12, num_words=8)
        socket.context = WordSearchContext(grid=grid, placements=placements)

    @event("select_cell")
    async def handle_select_cell(self, event, payload, socket: LiveViewSocket[WordSearchContext]):
        row = int(payload["row"])
        col = int(payload["col"])
        ctx = socket.context

        if ctx.selection_start is None:
            # Start new selection
            ctx.selection_start = (row, col)
            ctx.hover_cells = [(row, col)]
            ctx.message = ""
        else:
            # Complete selection
            start = ctx.selection_start
            end = (row, col)

            cells = get_cells_in_line(start, end)
            if cells is None:
                # Invalid line - reset
                ctx.selection_start = None
                ctx.hover_cells = []
                ctx.message = "Select in a straight line!"
                return

            # Check if this matches a word
            found_placement = check_selection(cells, ctx.placements)
            if found_placement and found_placement.word not in ctx.found_words:
                ctx.found_words.add(found_placement.word)
                ctx.found_cells.update(cells)
                ctx.message = f"Found: {found_placement.word}!"

                if ctx.all_found:
                    ctx.message = "Congratulations! You found all words!"
            else:
                ctx.message = "No word there. Try again!"

            ctx.selection_start = None
            ctx.hover_cells = []

    @event("hover_cell")
    async def handle_hover_cell(self, event, payload, socket: LiveViewSocket[WordSearchContext]):
        ctx = socket.context
        if ctx.selection_start is None:
            return

        row = int(payload["row"])
        col = int(payload["col"])

        cells = get_cells_in_line(ctx.selection_start, (row, col))
        ctx.hover_cells = cells if cells else [ctx.selection_start]

    @event("new_game")
    async def handle_new_game(self, event, payload, socket: LiveViewSocket[WordSearchContext]):
        grid, placements = generate_puzzle(rows=12, cols=12, num_words=8)
        socket.context = WordSearchContext(grid=grid, placements=placements)
