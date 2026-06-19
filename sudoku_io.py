from __future__ import annotations

"""
Sudoku board I/O utilities.

- Reads 9x9 Sudoku boards from plain-text files (9 lines of 9 digits).
- `0` represents an empty cell.
- Provides a simple pretty-printer for console output.
"""

from sudoku_solver import Grid


def _cells_in_box(box_r: int, box_c: int) -> list[tuple[int, int]]:
    """Return the 9 (row,col) cells inside a 3x3 box."""
    return [(r, c) for r in range(box_r, box_r + 3) for c in range(box_c, box_c + 3)]


def find_conflicting_cells(board: Grid) -> set[tuple[int, int]]:
    """
    Return a set of cells that violate Sudoku constraints (duplicate non-zero digits).

    A cell is marked conflicting if its value duplicates another value in:
    - the same row, or
    - the same column, or
    - the same 3x3 box.
    """
    conflicts: set[tuple[int, int]] = set()

    # Rows
    for r in range(9):
        seen: dict[int, tuple[int, int]] = {}
        for c in range(9):
            v = board[r][c]
            if v == 0:
                continue
            if v in seen:
                conflicts.add((r, c))
                conflicts.add(seen[v])
            else:
                seen[v] = (r, c)

    # Cols
    for c in range(9):
        seen = {}
        for r in range(9):
            v = board[r][c]
            if v == 0:
                continue
            if v in seen:
                conflicts.add((r, c))
                conflicts.add(seen[v])
            else:
                seen[v] = (r, c)

    # Boxes
    for br in range(0, 9, 3):
        for bc in range(0, 9, 3):
            seen = {}
            for (r, c) in _cells_in_box(br, bc):
                v = board[r][c]
                if v == 0:
                    continue
                if v in seen:
                    conflicts.add((r, c))
                    conflicts.add(seen[v])
                else:
                    seen[v] = (r, c)

    return conflicts


def autofix_inconsistent_clues(board: Grid) -> tuple[Grid, int]:
    """
    Make a board consistent by clearing conflicting clue cells to 0.

    Returns (fixed_board, cleared_count).
    This is used to "fix" inconsistent provided boards so the solver/game can proceed.
    """
    fixed = [row[:] for row in board]
    conflicts = find_conflicting_cells(fixed)
    for (r, c) in conflicts:
        fixed[r][c] = 0
    return fixed, len(conflicts)


def read_board(file_path: str) -> Grid:
    """Read a Sudoku board from a text file and return it as a 9x9 integer grid."""
    with open(file_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    if len(lines) != 9:
        raise ValueError(f"{file_path}: board must contain exactly 9 non-empty lines.")

    board: Grid = []
    for i, line in enumerate(lines, start=1):
        if len(line) != 9 or any(ch < "0" or ch > "9" for ch in line):
            raise ValueError(
                f"{file_path}: line {i} must contain exactly 9 digits (0-9)."
            )
        board.append([int(ch) for ch in line])
    return board


def board_to_string(board: Grid) -> str:
    """Format a Sudoku board into a human-readable string with 3x3 separators."""
    lines: list[str] = []
    for r in range(9):
        row_parts: list[str] = []
        for c in range(9):
            row_parts.append(str(board[r][c]))
            if c in (2, 5):
                row_parts.append("|")
        lines.append(" ".join(row_parts))
        if r in (2, 5):
            lines.append("-" * 21)
    return "\n".join(lines)
