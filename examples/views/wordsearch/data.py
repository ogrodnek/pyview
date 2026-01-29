import random
import string
from dataclasses import dataclass

# Directions: (row_delta, col_delta)
DIRECTIONS = [
    (0, 1),   # right
    (1, 0),   # down
    (1, 1),   # diagonal down-right
    (0, -1),  # left
    (-1, 0),  # up
    (-1, -1), # diagonal up-left
    (1, -1),  # diagonal down-left
    (-1, 1),  # diagonal up-right
]

# Word list for the puzzle
WORD_BANK = [
    "PYTHON", "CODE", "WEB", "LIVE", "VIEW", "SERVER",
    "ASYNC", "HTML", "EVENT", "GRID", "CLICK", "FIND",
    "WORD", "SEARCH", "GAME", "PLAY", "FUN", "PUZZLE",
    "SOCKET", "STATE", "RENDER", "MOUNT", "HOOK", "DATA",
]


@dataclass
class WordPlacement:
    word: str
    start_row: int
    start_col: int
    direction: tuple[int, int]

    def get_cells(self) -> list[tuple[int, int]]:
        """Return list of (row, col) tuples for this word."""
        cells = []
        row, col = self.start_row, self.start_col
        for _ in self.word:
            cells.append((row, col))
            row += self.direction[0]
            col += self.direction[1]
        return cells


def can_place_word(grid: list[list[str]], word: str, row: int, col: int, direction: tuple[int, int]) -> bool:
    """Check if a word can be placed at the given position and direction."""
    rows, cols = len(grid), len(grid[0])
    dr, dc = direction

    for i, letter in enumerate(word):
        r, c = row + i * dr, col + i * dc
        if r < 0 or r >= rows or c < 0 or c >= cols:
            return False
        if grid[r][c] != "" and grid[r][c] != letter:
            return False
    return True


def place_word(grid: list[list[str]], word: str, row: int, col: int, direction: tuple[int, int]) -> None:
    """Place a word on the grid."""
    dr, dc = direction
    for i, letter in enumerate(word):
        r, c = row + i * dr, col + i * dc
        grid[r][c] = letter


def generate_puzzle(rows: int = 12, cols: int = 12, num_words: int = 8) -> tuple[list[list[str]], list[WordPlacement]]:
    """Generate a word search puzzle."""
    grid = [["" for _ in range(cols)] for _ in range(rows)]
    placements: list[WordPlacement] = []

    # Select random words from the bank
    available_words = random.sample(WORD_BANK, min(num_words + 5, len(WORD_BANK)))

    for word in available_words:
        if len(placements) >= num_words:
            break

        # Try to place the word
        attempts = 0
        placed = False

        while attempts < 100 and not placed:
            direction = random.choice(DIRECTIONS)
            row = random.randint(0, rows - 1)
            col = random.randint(0, cols - 1)

            if can_place_word(grid, word, row, col, direction):
                place_word(grid, word, row, col, direction)
                placements.append(WordPlacement(word, row, col, direction))
                placed = True

            attempts += 1

    # Fill empty cells with random letters
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == "":
                grid[r][c] = random.choice(string.ascii_uppercase)

    return grid, placements


def check_selection(
    selected_cells: list[tuple[int, int]],
    placements: list[WordPlacement]
) -> WordPlacement | None:
    """Check if the selected cells match any word (forward or backward)."""
    if len(selected_cells) < 2:
        return None

    for placement in placements:
        word_cells = placement.get_cells()
        if selected_cells == word_cells or selected_cells == list(reversed(word_cells)):
            return placement

    return None


def get_cells_in_line(start: tuple[int, int], end: tuple[int, int]) -> list[tuple[int, int]] | None:
    """Get all cells in a straight line between start and end (inclusive).
    Returns None if the cells are not in a valid line (horizontal, vertical, or diagonal).
    """
    r1, c1 = start
    r2, c2 = end

    dr = 0 if r2 == r1 else (1 if r2 > r1 else -1)
    dc = 0 if c2 == c1 else (1 if c2 > c1 else -1)

    # Check if it's a valid line (horizontal, vertical, or 45-degree diagonal)
    if dr == 0 and dc == 0:
        return [(r1, c1)]

    row_diff = abs(r2 - r1)
    col_diff = abs(c2 - c1)

    # Must be horizontal, vertical, or 45-degree diagonal
    if row_diff != 0 and col_diff != 0 and row_diff != col_diff:
        return None

    cells = []
    r, c = r1, c1
    steps = max(row_diff, col_diff)

    for _ in range(steps + 1):
        cells.append((r, c))
        r += dr
        c += dc

    return cells
