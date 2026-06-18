"""Rule-based baseline agent for ConnectX.

Decision logic (deterministic):
  1. If we have an immediate winning move, play it.
  2. Else if the opponent has an immediate winning move, block it.
  3. Else play the legal move closest to the centre column.

Board helpers (legal-move enumeration, drop, win check) live in this file so
that the agent is self-contained and easy to copy/freeze into an opponent pool.

I/O contract (Kaggle ConnectX):
  observation.board : list[int], length rows*columns, row-major
                      (0 = empty, 1 = player1, 2 = player2)
  observation.mark  : int, our piece (1 or 2)
  configuration     : has .rows, .columns, .inarow
  return            : int column index to play

IMPORTANT: never print/log inside this function — see package docstring.
"""

from __future__ import annotations

from typing import List, Optional, Sequence


# ---------------------------------------------------------------------------
# Board helpers (pure functions, no global state)
# ---------------------------------------------------------------------------
def legal_moves(board: Sequence[int], columns: int) -> List[int]:
    """Columns whose top cell is empty (i.e. playable), left-to-right."""
    return [c for c in range(columns) if board[c] == 0]


def drop(board: Sequence[int], col: int, piece: int, rows: int, columns: int) -> List[int]:
    """Return a new board with ``piece`` dropped into ``col``.

    The piece falls to the lowest empty cell of the column. Caller must ensure
    ``col`` is a legal move.
    """
    new_board = list(board)
    for r in range(rows - 1, -1, -1):  # bottom row -> top row
        idx = r * columns + col
        if new_board[idx] == 0:
            new_board[idx] = piece
            break
    return new_board


def is_win(board: Sequence[int], piece: int, rows: int, columns: int, inarow: int) -> bool:
    """True if ``piece`` has ``inarow`` in a row (horiz / vert / both diagonals)."""
    def cell(r: int, c: int) -> int:
        return board[r * columns + c]

    # Horizontal
    for r in range(rows):
        for c in range(columns - inarow + 1):
            if all(cell(r, c + i) == piece for i in range(inarow)):
                return True
    # Vertical
    for r in range(rows - inarow + 1):
        for c in range(columns):
            if all(cell(r + i, c) == piece for i in range(inarow)):
                return True
    # Diagonal "/" (going up-right): row decreases as col increases
    for r in range(inarow - 1, rows):
        for c in range(columns - inarow + 1):
            if all(cell(r - i, c + i) == piece for i in range(inarow)):
                return True
    # Diagonal "\" (going down-right): row increases as col increases
    for r in range(rows - inarow + 1):
        for c in range(columns - inarow + 1):
            if all(cell(r + i, c + i) == piece for i in range(inarow)):
                return True
    return False


def winning_move(
    board: Sequence[int], piece: int, rows: int, columns: int, inarow: int
) -> Optional[int]:
    """Lowest-index legal column where ``piece`` wins immediately, else None."""
    for col in legal_moves(board, columns):
        if is_win(drop(board, col, piece, rows, columns), piece, rows, columns, inarow):
            return col
    return None


def _centre_order(legal: Sequence[int], columns: int) -> List[int]:
    """Legal columns ordered by distance to centre (ties: lower index first)."""
    centre = (columns - 1) / 2.0
    return sorted(legal, key=lambda c: (abs(c - centre), c))


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------
def heuristic_agent(obs, config) -> int:
    """Return the column to play. See module docstring for the logic."""
    rows = config.rows
    columns = config.columns
    inarow = config.inarow
    board = obs.board
    me = obs.mark
    opp = 2 if me == 1 else 1

    legal = legal_moves(board, columns)
    if not legal:
        # No legal move (full board); ConnectX should not call us here, but
        # return a safe value rather than crash.
        return 0

    # 1. Win now if we can.
    win = winning_move(board, me, rows, columns, inarow)
    if win is not None:
        return win

    # 2. Block an immediate opponent win.
    block = winning_move(board, opp, rows, columns, inarow)
    if block is not None:
        return block

    # 3. Otherwise prefer the centre-most legal column (deterministic).
    return _centre_order(legal, columns)[0]
