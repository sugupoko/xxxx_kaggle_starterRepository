"""Frozen opponent v1 — self-contained heuristic agent.

This is a FROZEN copy of agents/heuristic.py with the board helpers inlined so
it has NO imports from the reference_sim package. It is part of the opponent
pool (the simulation-competition analogue of a fold definition): once frozen it
must not change, so that win-rates measured against it stay comparable over
time. See opponents/README.md.

Exposes ``agent(observation, configuration) -> int`` (the name evaluate.py /
kaggle_environments expect). Never print/log inside ``agent``.

Logic: (1) win now if possible, (2) else block opponent's immediate win,
(3) else play the centre-most legal column. Deterministic.
"""

from __future__ import annotations


def _legal_moves(board, columns):
    return [c for c in range(columns) if board[c] == 0]


def _drop(board, col, piece, rows, columns):
    new_board = list(board)
    for r in range(rows - 1, -1, -1):
        idx = r * columns + col
        if new_board[idx] == 0:
            new_board[idx] = piece
            break
    return new_board


def _is_win(board, piece, rows, columns, inarow):
    def cell(r, c):
        return board[r * columns + c]

    for r in range(rows):
        for c in range(columns - inarow + 1):
            if all(cell(r, c + i) == piece for i in range(inarow)):
                return True
    for r in range(rows - inarow + 1):
        for c in range(columns):
            if all(cell(r + i, c) == piece for i in range(inarow)):
                return True
    for r in range(inarow - 1, rows):
        for c in range(columns - inarow + 1):
            if all(cell(r - i, c + i) == piece for i in range(inarow)):
                return True
    for r in range(rows - inarow + 1):
        for c in range(columns - inarow + 1):
            if all(cell(r + i, c + i) == piece for i in range(inarow)):
                return True
    return False


def _winning_move(board, piece, rows, columns, inarow):
    for col in _legal_moves(board, columns):
        if _is_win(_drop(board, col, piece, rows, columns), piece, rows, columns, inarow):
            return col
    return None


def agent(observation, configuration):
    rows = configuration.rows
    columns = configuration.columns
    inarow = configuration.inarow
    board = observation.board
    me = observation.mark
    opp = 2 if me == 1 else 1

    legal = _legal_moves(board, columns)
    if not legal:
        return 0

    win = _winning_move(board, me, rows, columns, inarow)
    if win is not None:
        return win

    block = _winning_move(board, opp, rows, columns, inarow)
    if block is not None:
        return block

    centre = (columns - 1) / 2.0
    return sorted(legal, key=lambda c: (abs(c - centre), c))[0]
