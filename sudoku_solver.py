from __future__ import annotations

"""
Sudoku CSP solver.

Implements:
- AC-3 arc consistency (constraint propagation)
- Backtracking search with MRV + forward checking (optionally with AC-3 inference)

The GUI can select between running AC-3 only or running backtracking search.
"""

from collections import deque
import copy
from dataclasses import dataclass
from typing import Literal

Grid = list[list[int]]
Cell = tuple[int, int]
Domains = dict[Cell, set[int]]
Algorithm = Literal["ac3", "backtracking"]


def _peers_of(cell: Cell) -> set[Cell]:
    """Return all peer cells (row, column, and 3x3 box neighbors)."""
    row, col = cell
    peers: set[Cell] = set()

    for c in range(9):
        if c != col:
            peers.add((row, c))
    for r in range(9):
        if r != row:
            peers.add((r, col))

    box_r = (row // 3) * 3
    box_c = (col // 3) * 3
    for r in range(box_r, box_r + 3):
        for c in range(box_c, box_c + 3):
            if (r, c) != cell:
                peers.add((r, c))
    return peers


ALL_CELLS: list[Cell] = [(r, c) for r in range(9) for c in range(9)]
PEERS: dict[Cell, set[Cell]] = {cell: _peers_of(cell) for cell in ALL_CELLS}


@dataclass
class SolverStats:
    """Solver statistics required by the assignment."""

    backtrack_calls: int = 0
    backtrack_failures: int = 0


def board_to_domains(board: Grid) -> Domains:
    """Convert a 9x9 grid into CSP domains (0 => {1..9}, else singleton)."""
    domains: Domains = {}
    for r in range(9):
        for c in range(9):
            val = board[r][c]
            domains[(r, c)] = {val} if val != 0 else set(range(1, 10))
    return domains


def revise(domains: Domains, xi: Cell, xj: Cell) -> bool:
    """AC-3 revise step: prune values from `xi` that conflict with `xj`."""
    revised = False
    if len(domains[xi]) == 1 and len(domains[xj]) == 1:
        if next(iter(domains[xi])) == next(iter(domains[xj])):
            domains[xi].clear()
            return True
    if len(domains[xj]) == 1:
        only = next(iter(domains[xj]))
        if only in domains[xi] and len(domains[xi]) > 1:
            domains[xi].remove(only)
            revised = True
    return revised


def ac3(domains: Domains, queue: deque[tuple[Cell, Cell]] | None = None) -> bool:
    """Enforce arc consistency. Returns False if any domain becomes empty."""
    if queue is None:
        queue = deque()
        for xi in ALL_CELLS:
            for xj in PEERS[xi]:
                queue.append((xi, xj))

    while queue:
        xi, xj = queue.popleft()
        if revise(domains, xi, xj):
            if not domains[xi]:
                return False
            for xk in PEERS[xi]:
                if xk != xj:
                    queue.append((xk, xi))
    return True


def is_consistent_assignment(domains: Domains, cell: Cell, value: int) -> bool:
    """Check if assigning `value` to `cell` violates any already-singleton peer."""
    for peer in PEERS[cell]:
        if len(domains[peer]) == 1 and value in domains[peer]:
            return False
    return True


def select_unassigned_variable(domains: Domains) -> Cell | None:
    """MRV heuristic: choose the unassigned cell with the smallest domain."""
    unassigned = [cell for cell in ALL_CELLS if len(domains[cell]) > 1]
    if not unassigned:
        return None
    return min(unassigned, key=lambda cell: len(domains[cell]))


def order_domain_values(domains: Domains, cell: Cell) -> list[int]:
    """Return domain values in a deterministic order."""
    return sorted(domains[cell])


def forward_check(domains: Domains, cell: Cell, value: int) -> bool:
    """Forward checking: remove `value` from peer domains. False if any becomes empty."""
    for peer in PEERS[cell]:
        if len(domains[peer]) > 1 and value in domains[peer]:
            domains[peer].remove(value)
            if not domains[peer]:
                return False
    return True


def backtrack(domains: Domains, stats: SolverStats, *, enforce_ac3: bool) -> Domains | None:
    """Backtracking search with MRV + forward checking (and optional AC-3 inference)."""
    stats.backtrack_calls += 1

    var = select_unassigned_variable(domains)
    if var is None:
        return domains

    for value in order_domain_values(domains, var):
        if not is_consistent_assignment(domains, var, value):
            continue

        next_domains = copy.deepcopy(domains)
        next_domains[var] = {value}

        if not forward_check(next_domains, var, value):
            continue

        if enforce_ac3:
            q = deque((peer, var) for peer in PEERS[var])
            if not ac3(next_domains, q):
                continue

        result = backtrack(next_domains, stats, enforce_ac3=enforce_ac3)
        if result is not None:
            return result

    stats.backtrack_failures += 1
    return None


def domains_to_board(domains: Domains) -> Grid:
    """Convert singleton domains into a concrete 9x9 solved grid."""
    board: Grid = [[0 for _ in range(9)] for _ in range(9)]
    for (r, c), values in domains.items():
        if len(values) != 1:
            raise ValueError("Unresolved board domains.")
        board[r][c] = next(iter(values))
    return board


def solve_board(board: Grid, *, algorithm: Algorithm = "backtracking") -> tuple[Grid | None, SolverStats]:
    """
    Solve a Sudoku board using the selected algorithm.

    - algorithm="ac3": run AC-3 propagation first, then backtracking if unresolved
    - algorithm="backtracking": backtracking + forward checking with AC-3 inference
    """
    stats = SolverStats()
    domains = board_to_domains(board)

    if algorithm == "ac3":
        if not ac3(domains):
            return None, stats
        # AC-3 alone often leaves multiple candidates; finish with search.
        if any(len(domains[cell]) != 1 for cell in ALL_CELLS):
            solved = backtrack(domains, stats, enforce_ac3=True)
            if solved is None:
                return None, stats
            solved_board = domains_to_board(solved)
        else:
            solved_board = domains_to_board(domains)
        if not _is_complete_solution(solved_board):
            return None, stats
        return solved_board, stats

    # Backtracking mode: run AC-3 first for pruning, then search with inference.
    # (This keeps "AC-3 only" as a separate option while making backtracking correct/fast.)
    if not ac3(domains):
        return None, stats
    solved = backtrack(domains, stats, enforce_ac3=True)
    if solved is None:
        return None, stats
    solved_board = domains_to_board(solved)
    if not _is_complete_solution(solved_board):
        return None, stats
    return solved_board, stats


def _is_complete_solution(board: Grid) -> bool:
    """Validate that a filled grid is a correct Sudoku solution."""
    target = set(range(1, 10))

    for r in range(9):
        if set(board[r]) != target:
            return False

    for c in range(9):
        col_vals = {board[r][c] for r in range(9)}
        if col_vals != target:
            return False

    for br in range(0, 9, 3):
        for bc in range(0, 9, 3):
            box_vals = set()
            for r in range(br, br + 3):
                for c in range(bc, bc + 3):
                    box_vals.add(board[r][c])
            if box_vals != target:
                return False

    return True
